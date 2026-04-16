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
