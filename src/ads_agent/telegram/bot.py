"""Telegram bot bootstrap.

Runs as its own systemd service on the VM (NOT inside Cloud Run), because
reconciliation / MCP calls need localhost access to 127.0.0.1:3103 and
127.0.0.1:5432.

Use webhook mode behind nginx (your PUBLIC_BASE_URL -> 127.0.0.1:3110 or whatever local port you run on).
For v0 local dev, long-poll mode is fine; flip via env.
"""
from __future__ import annotations

import asyncio
import logging

from telegram.ext import Application, AIORateLimiter, CommandHandler

from ads_agent.config import settings
from ads_agent.telegram.handlers import cmd_help, cmd_insights, cmd_start, cmd_stores

log = logging.getLogger(__name__)


def build_app() -> Application:
    s = settings()
    if not s.telegram_bot_token_ads:
        raise RuntimeError("TELEGRAM_BOT_TOKEN_ADS is not set")
    app = (
        Application.builder()
        .token(s.telegram_bot_token_ads)
        .rate_limiter(AIORateLimiter())
        .build()
    )
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("stores", cmd_stores))
    app.add_handler(CommandHandler("insights", cmd_insights))
    return app


def run_polling() -> None:
    """Local dev entrypoint: `python -m ads_agent.telegram.bot`."""
    logging.basicConfig(level=settings().log_level)
    app = build_app()
    app.run_polling()


if __name__ == "__main__":
    run_polling()
