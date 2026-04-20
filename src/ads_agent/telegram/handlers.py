"""Telegram command handlers — all commands invoke the LangGraph agent."""
from __future__ import annotations

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from ads_agent.agent.graph import build_graph
from ads_agent.config import STORES, get_store
from ads_agent.memory.store import fire_and_forget as log_turn
from ads_agent.telegram.auth import is_admin

_graph = build_graph()


async def cmd_start(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        return
    await update.message.reply_text(
        "Glitch Grow Ads Agent is live. Try /help for commands."
    )


async def cmd_help(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        return
    msg = (
        "*Commands*\n\n"
        "`/insights <store> [days]` — order counts, revenue, AOV, coverage\n"
        "`/roas <store> [days]` — true ROAS vs Meta-reported, spend across all linked accounts\n"
        "`/tracking_audit <store> [days]` — LLM-picked remediation recipes for tracking gaps\n"
        "`/ads <store> [days]` — top ads by spend, with CTR/CPC/ROAS per ad\n"
        "`/creative <ad_id> [store]` — structured critique of one ad's creative (Gemini vision)\n"
        "`/ideas <store> [days]` — 5 numbered creative briefs based on winning patterns\n"
        "`/alerts <store>` — CPC drift, spend anomalies, tracking gaps, premature-kill reminders\n"
        "`/amazon <store> [days]` — Amazon Seller + Amazon Ads rollup via Supermetrics (Ayurpet only for now)\n"
        "`/attribution <store> [days]` — Meta → Amazon attribution (subtraction model, Ayurpet)\n"
        "`/stores` — list configured stores\n"
        "`/help` — this message"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def cmd_stores(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        return
    lines = [f"• `{s.slug}` — {s.brand} ({s.shop_domain})" for s in STORES]
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def _run_and_reply(update: Update, command: str, days_default: int, args: list[str]) -> None:
    if not args:
        await update.message.reply_text(f"usage: /{command} <store> [days]")
        return
    slug = args[0]
    days = int(args[1]) if len(args) > 1 and args[1].isdigit() else days_default

    if get_store(slug) is None:
        await update.message.reply_text(f"Unknown store `{slug}`. /stores for list.", parse_mode=ParseMode.MARKDOWN)
        return

    # Placeholder "working..." so the user sees activity during LLM calls
    status_msg = await update.message.reply_text(f"Running /{command} {slug} {days}d…")

    state: dict = {}
    try:
        state = await _graph.ainvoke({"command": command, "store_slug": slug, "days": days})
        reply = state.get("reply_text", "(no reply)")
    except Exception as e:
        reply = f"error: {e}"

    try:
        await status_msg.edit_text(reply, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        # Markdown parse fail → send as plain so the reply still lands
        await status_msg.edit_text(reply)

    # Fire-and-forget memory log (post-reply so it never delays user-visible output)
    log_turn(
        command=command,
        store_slug=slug,
        user_tg_id=update.effective_user.id if update.effective_user else None,
        args={"days": days},
        reply_text=reply,
        key_metrics=state.get("orders_summary") if isinstance(state.get("orders_summary"), dict) else None,
    )


async def cmd_insights(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        return
    await _run_and_reply(update, "insights", 7, ctx.args or [])


async def cmd_roas(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        return
    await _run_and_reply(update, "roas", 7, ctx.args or [])


async def cmd_tracking_audit(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        return
    await _run_and_reply(update, "tracking_audit", 30, ctx.args or [])


async def cmd_ads(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        return
    await _run_and_reply(update, "ads", 7, ctx.args or [])


async def cmd_ideas(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        return
    await _run_and_reply(update, "ideas", 30, ctx.args or [])


async def cmd_alerts(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        return
    await _run_and_reply(update, "alerts", 7, ctx.args or [])


async def cmd_amazon(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        return
    await _run_and_reply(update, "amazon", 30, ctx.args or [])


async def cmd_attribution(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        return
    await _run_and_reply(update, "attribution", 30, ctx.args or [])


# ─── v2 action layer: /plan + /actions ──────────────────────────────────────

async def cmd_plan(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Show pending action proposals for a store. Usage: /plan <store>"""
    if not is_admin(update):
        return
    import asyncpg, os
    args = ctx.args or []
    slug = args[0] if args else None

    conn = await asyncpg.connect(os.environ["POSTGRES_INSIGHTS_RO_URL"])
    try:
        if slug:
            rows = await conn.fetch(
                """SELECT id, action_kind, target_object_name, rationale, created_at,
                          expires_at, status
                   FROM ads_agent.agent_actions
                   WHERE store_slug=$1 AND status='pending_approval'
                   ORDER BY created_at DESC""",
                slug,
            )
        else:
            rows = await conn.fetch(
                """SELECT id, store_slug, action_kind, target_object_name, rationale,
                          created_at, expires_at, status
                   FROM ads_agent.agent_actions
                   WHERE status='pending_approval'
                   ORDER BY created_at DESC"""
            )
    finally:
        await conn.close()

    if not rows:
        await update.message.reply_text(
            f"No pending proposals{' for `'+slug+'`' if slug else ''}.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    lines = [f"*Pending proposals{' · '+slug if slug else ''}*", ""]
    for r in rows:
        ttl_h = max(0, int((r["expires_at"] - r["created_at"]).total_seconds() / 3600))
        lines.append(
            f"#`{r['id']}` · *{r['action_kind']}* on `{(r['target_object_name'] or '?')[:40]}`"
            + (f" ({r.get('store_slug')})" if not slug else "")
        )
        lines.append(f"  _{r['rationale'][:180]}_")
        lines.append(f"  created {r['created_at'].strftime('%Y-%m-%d %H:%M')} UTC · TTL {ttl_h}h")
        lines.append("")

    await update.message.reply_text("\n".join(lines)[:4000], parse_mode=ParseMode.MARKDOWN)


async def cmd_actions(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Show recent action history. Usage: /actions [store] [status]"""
    if not is_admin(update):
        return
    import asyncpg, os
    args = ctx.args or []
    slug = args[0] if args else None
    status = args[1] if len(args) > 1 else None

    conn = await asyncpg.connect(os.environ["POSTGRES_INSIGHTS_RO_URL"])
    try:
        where = ["1=1"]
        vals: list = []
        if slug:
            vals.append(slug); where.append(f"store_slug=${len(vals)}")
        if status:
            vals.append(status); where.append(f"status=${len(vals)}")
        sql = f"""SELECT id, store_slug, action_kind, target_object_name, status,
                         created_at, executed_at
                  FROM ads_agent.agent_actions
                  WHERE {' AND '.join(where)}
                  ORDER BY created_at DESC LIMIT 15"""
        rows = await conn.fetch(sql, *vals)
    finally:
        await conn.close()

    if not rows:
        await update.message.reply_text("No actions in history.")
        return

    lines = ["*Recent actions (last 15)*", ""]
    status_emoji = {
        "pending_approval": "⏳",
        "approved":         "✅",
        "executing":        "🔄",
        "executed":         "✔️",
        "rejected":         "❌",
        "expired":          "⌛",
        "failed":           "⚠️",
        "rolled_back":      "↩️",
    }
    for r in rows:
        e = status_emoji.get(r["status"], "•")
        lines.append(
            f"{e} #`{r['id']}` · {r['action_kind']} · `{(r['target_object_name'] or '?')[:30]}` "
            f"({r['store_slug']}) · {r['status']}"
        )
    await update.message.reply_text("\n".join(lines)[:4000], parse_mode=ParseMode.MARKDOWN)


async def cmd_creative(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Usage: /creative <ad_id> [store_slug]. store_slug injects per-family context."""
    if not is_admin(update):
        return
    args = ctx.args or []
    if not args:
        await update.message.reply_text("usage: /creative <ad_id> [store_slug]")
        return
    ad_id = args[0]
    slug = args[1] if len(args) > 1 else ""

    status_msg = await update.message.reply_text(f"Analyzing creative `{ad_id}`…", parse_mode=ParseMode.MARKDOWN)
    try:
        state = await _graph.ainvoke({"command": "creative", "ad_id": ad_id, "store_slug": slug})
        reply = state.get("reply_text", "(no reply)")
    except Exception as e:
        reply = f"error: {e}"

    # Telegram markdown can break on unescaped chars; send as MARKDOWN but fall back to plain
    try:
        await status_msg.edit_text(reply, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        await status_msg.edit_text(reply)

    log_turn(
        command="creative",
        store_slug=slug or None,
        user_tg_id=update.effective_user.id if update.effective_user else None,
        args={"ad_id": ad_id},
        reply_text=reply,
    )
