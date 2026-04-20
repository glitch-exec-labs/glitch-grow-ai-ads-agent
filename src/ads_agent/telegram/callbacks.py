"""Telegram inline-button callback handler for action approvals.

Callback data format: `act:<verb>:<action_id>`
  verb ∈ {approve, reject}
  action_id: int

The handler:
  1. Looks up the action row
  2. Validates state (still pending_approval, not expired)
  3. Flips status + records approver tg_id / timestamp
  4. Edits the original Telegram message to remove buttons + show verdict
  5. On approve: executor picks it up within 5 minutes (next timer tick)
"""
from __future__ import annotations

import logging
import os

import asyncpg
from telegram import Update
from telegram.ext import ContextTypes

from ads_agent.actions.notifier import edit_message_remove_buttons
from ads_agent.config import settings

log = logging.getLogger(__name__)


async def _pg() -> asyncpg.Connection:
    return await asyncpg.connect(os.environ["POSTGRES_INSIGHTS_RO_URL"])


async def action_button_handler(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if not q or not q.data or not q.data.startswith("act:"):
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

    conn = await _pg()
    try:
        row = await conn.fetchrow(
            "SELECT * FROM ads_agent.agent_actions WHERE id=$1",
            action_id,
        )
        if not row:
            await q.answer("Action not found.", show_alert=True)
            return
        if row["status"] != "pending_approval":
            await q.answer(
                f"Already {row['status']}. No change.",
                show_alert=True,
            )
            return
        if row["expires_at"] and row["expires_at"].replace(tzinfo=None) < __import__("datetime").datetime.utcnow():
            await q.answer("Proposal expired (72h). Re-plan to retry.", show_alert=True)
            await conn.execute(
                "UPDATE ads_agent.agent_actions SET status='expired' WHERE id=$1",
                action_id,
            )
            return

        if verb == "approve":
            await conn.execute(
                """UPDATE ads_agent.agent_actions
                   SET status='approved', approved_by=$1, approved_at=NOW()
                   WHERE id=$2""",
                user_id, action_id,
            )
            verdict_line = f"✅ *Approved by user `{user_id}`* at {__import__('datetime').datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}. Executor will run within 5 minutes."
            await q.answer("Approved — executor will run shortly.")
        elif verb == "reject":
            await conn.execute(
                """UPDATE ads_agent.agent_actions
                   SET status='rejected', rejected_by=$1, rejected_at=NOW()
                   WHERE id=$2""",
                user_id, action_id,
            )
            verdict_line = f"❌ *Rejected by user `{user_id}`* at {__import__('datetime').datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}. No change will be applied."
            await q.answer("Rejected.")
        else:
            await q.answer("unknown action", show_alert=True)
            return

        # Edit the original message to remove buttons + show verdict
        new_text = (q.message.text_markdown_v2_urled if False else q.message.text or "")
        new_text = f"{new_text}\n\n{verdict_line}"
        await edit_message_remove_buttons(
            chat_id=row["telegram_chat_id"],
            message_id=row["telegram_message_id"],
            new_text=new_text,
        )
    finally:
        await conn.close()
