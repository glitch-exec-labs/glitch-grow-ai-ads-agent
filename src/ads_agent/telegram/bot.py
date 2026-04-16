"""Telegram bot — used in webhook mode inside the FastAPI server.

Usage pattern:
  - `build_app()` returns a configured `telegram.ext.Application` (not started).
  - `server.py` calls `app.initialize()` + `app.start()` on FastAPI startup.
  - Incoming POST /telegram/webhook → parsed into Update → app.update_queue.put(update)

For local polling (dev only): `python -m ads_agent.telegram.bot`.
"""
from __future__ import annotations

import logging

from telegram.ext import AIORateLimiter, Application, CommandHandler

from ads_agent.config import settings
from ads_agent.telegram.handlers import (
    cmd_ads,
    cmd_alerts,
    cmd_amazon,
    cmd_creative,
    cmd_help,
    cmd_ideas,
    cmd_insights,
    cmd_roas,
    cmd_start,
    cmd_stores,
    cmd_tracking_audit,
)

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
    app.add_handler(CommandHandler("roas", cmd_roas))
    app.add_handler(CommandHandler("tracking_audit", cmd_tracking_audit))
    app.add_handler(CommandHandler("ads", cmd_ads))
    app.add_handler(CommandHandler("creative", cmd_creative))
    app.add_handler(CommandHandler("ideas", cmd_ideas))
    app.add_handler(CommandHandler("alerts", cmd_alerts))
    app.add_handler(CommandHandler("amazon", cmd_amazon))
    return app


def run_polling() -> None:
    """Local dev entrypoint only — `python -m ads_agent.telegram.bot`."""
    logging.basicConfig(level=settings().log_level)
    app = build_app()
    app.run_polling()


if __name__ == "__main__":
    run_polling()
