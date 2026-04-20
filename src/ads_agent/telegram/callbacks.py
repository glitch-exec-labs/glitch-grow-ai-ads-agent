"""Telegram inline-button callback handler for action approvals.

Callback data format: `act:<verb>:<action_id>`
  verb ∈ {approve, reject}
  action_id: int

Security model (issue #2):
  1. Callback is admin-gated: only user ids in TELEGRAM_ADMIN_IDS can
     approve/reject. Non-admin clicks get a Telegram toast and no state
     change. Command handlers already gate this way; the approval path was
     the remaining hole.
  2. State transition is first-click-wins via a single atomic UPDATE
     guarded by `WHERE status='pending_approval'`. If two admins click
     Approve/Reject within the same second, Postgres serializes the writes;
     the second one sees `rowcount == 0` and is told "already resolved".
     This replaces the prior read-then-write race.

Also addresses issue #3: this module writes to `ads_agent.agent_actions` —
the connection must use the RW DSN, not the documented read-only one.
"""
from __future__ import annotations

import datetime as _dt
import logging

import asyncpg
from telegram import Update
from telegram.ext import ContextTypes

from ads_agent.actions.notifier import edit_message_remove_buttons
from ads_agent.config import settings
from ads_agent.telegram.auth import is_admin

log = logging.getLogger(__name__)


async def _pg() -> asyncpg.Connection:
    # RW DSN — approvals mutate agent_actions (issue #3).
    return await asyncpg.connect(settings().postgres_rw_dsn)


async def action_button_handler(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if not q or not q.data or not q.data.startswith("act:"):
        return

    # Admin-only: reject callback clicks from non-admin users (issue #2).
    # Silent to keep the approval prompt uncluttered for onlookers; admin
    # clicks still resolve it. Return BEFORE any DB work.
    if not is_admin(update):
        user_id = update.effective_user.id if update.effective_user else "?"
        log.warning("non-admin callback click rejected: user=%s data=%s", user_id, q.data)
        await q.answer(
            "Not authorized. Only configured admins can approve or reject actions.",
            show_alert=True,
        )
        return

    parts = q.data.split(":")
    if len(parts) != 3:
        await q.answer("malformed callback", show_alert=False)
        return
    _, verb, action_id_str = parts
    try:
        action_id = int(action_id_str)
    except ValueError:
        await q.answer("bad action id", show_alert=False)
        return

    user_id = update.effective_user.id if update.effective_user else None
    now = _dt.datetime.utcnow()

    conn = await _pg()
    try:
        # Step 1: load row for context + expiry check. We still do this read
        # so we have telegram_chat_id/message_id to edit after resolution,
        # but the authoritative status transition happens atomically below.
        row = await conn.fetchrow(
            "SELECT * FROM ads_agent.agent_actions WHERE id=$1",
            action_id,
        )
        if not row:
            await q.answer("Action not found.", show_alert=True)
            return

        # Expiry short-circuit — mark expired atomically only if still pending.
        # This also uses the pending_approval guard, so two concurrent expiries
        # are safe.
        if row["expires_at"] and row["expires_at"].replace(tzinfo=None) < now:
            await conn.execute(
                """UPDATE ads_agent.agent_actions
                   SET status='expired'
                   WHERE id=$1 AND status='pending_approval'""",
                action_id,
            )
            await q.answer("Proposal expired (72h). Re-plan to retry.", show_alert=True)
            return

        if verb == "approve":
            result = await conn.execute(
                """UPDATE ads_agent.agent_actions
                   SET status='approved', approved_by=$1, approved_at=NOW()
                   WHERE id=$2 AND status='pending_approval'""",
                user_id, action_id,
            )
            verdict_line = (
                f"✅ *Approved by user `{user_id}`* at "
                f"{now.strftime('%Y-%m-%d %H:%M UTC')}. "
                f"Executor will run within 5 minutes."
            )
            toast = "Approved — executor will run shortly."
        elif verb == "reject":
            result = await conn.execute(
                """UPDATE ads_agent.agent_actions
                   SET status='rejected', rejected_by=$1, rejected_at=NOW()
                   WHERE id=$2 AND status='pending_approval'""",
                user_id, action_id,
            )
            verdict_line = (
                f"❌ *Rejected by user `{user_id}`* at "
                f"{now.strftime('%Y-%m-%d %H:%M UTC')}. "
                f"No change will be applied."
            )
            toast = "Rejected."
        else:
            await q.answer("unknown action", show_alert=True)
            return

        # Parse "UPDATE N" — N=0 means some other click won the race or the
        # row was already resolved/expired between load and update.
        try:
            rows_affected = int(result.split()[-1])
        except (ValueError, IndexError):
            rows_affected = 0

        if rows_affected == 0:
            # Re-read to show the user what happened.
            fresh = await conn.fetchrow(
                "SELECT status FROM ads_agent.agent_actions WHERE id=$1",
                action_id,
            )
            status_now = fresh["status"] if fresh else "unknown"
            await q.answer(
                f"Already {status_now}. No change.",
                show_alert=True,
            )
            return

        await q.answer(toast)

        # Edit the original message to remove buttons + show verdict.
        # Fire-and-forget: if this fails (Telegram hiccup), the DB state is
        # still authoritative.
        try:
            original = q.message.text or ""
            await edit_message_remove_buttons(
                chat_id=row["telegram_chat_id"],
                message_id=row["telegram_message_id"],
                new_text=f"{original}\n\n{verdict_line}",
            )
        except Exception:
            log.exception("edit_message_remove_buttons failed for action %s", action_id)
    finally:
        await conn.close()
