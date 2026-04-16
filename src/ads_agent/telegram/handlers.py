"""Telegram command handlers. Each command invokes the LangGraph agent and
posts the resulting `reply_text`.

v0 commands wired: /start, /help, /stores, /insights.
v1 adds: /roas, /tracking_audit, /scopes_check, /daily_digest_toggle.
v2 adds: /ads (HITL-gated write-actions).
"""
from __future__ import annotations

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from ads_agent.agent.graph import build_graph
from ads_agent.config import STORES
from ads_agent.telegram.auth import is_admin

_graph = build_graph()


async def cmd_start(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        return
    await update.message.reply_text(
        "Glitch Grow Ads Agent. Try /help for commands."
    )


async def cmd_help(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        return
    msg = (
        "/stores — list configured stores\n"
        "/insights <store> [days]  — GMV / AOV / order count\n"
        "/help — this message"
    )
    await update.message.reply_text(msg)


async def cmd_stores(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        return
    lines = [f"• `{s.slug}` — {s.brand} ({s.shop_domain})" for s in STORES]
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def cmd_insights(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        return
    args = ctx.args or []
    if not args:
        await update.message.reply_text("usage: /insights <store> [days]")
        return
    slug = args[0]
    days = int(args[1]) if len(args) > 1 and args[1].isdigit() else 7

    state = await _graph.ainvoke({"command": "insights", "store_slug": slug, "days": days})
    reply = state.get("reply_text", "(no reply)")
    await update.message.reply_text(reply, parse_mode=ParseMode.MARKDOWN)
