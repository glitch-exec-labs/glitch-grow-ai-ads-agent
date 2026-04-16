"""FastAPI entrypoint.

Endpoints:
  GET  /healthz                    -> liveness + git sha
  POST /shopify/webhook/{shop}     -> HMAC-verified Shopify webhook receiver (v1+)
  POST /telegram/webhook           -> python-telegram-bot Update receiver (v1+)
  POST /agent/run                  -> LangGraph entrypoint for Telegram handlers (v0+)
  POST /jobs/reconcile             -> Cloud Scheduler nightly reconciliation (v2+)
  POST /jobs/daily_digest          -> Cloud Scheduler morning digest (v2+)

v0: only /healthz is wired. Everything else returns 501 until its milestone lands.
"""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI, HTTPException

from ads_agent import __version__
from ads_agent.config import settings

log = logging.getLogger(__name__)

app = FastAPI(
    title="Glitch Grow Ads Agent",
    version=__version__,
    description="Systematic ads ops agent for Glitch Grow Shopify stores.",
)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {
        "status": "ok",
        "version": __version__,
        "git_sha": os.environ.get("GIT_SHA", "dev"),
        "public_base_url": settings().public_base_url,
    }


@app.post("/shopify/webhook/{shop}")
async def shopify_webhook(shop: str) -> dict[str, str]:
    # TODO(v1): move to ads_agent.shopify.webhooks router with HMAC verify.
    raise HTTPException(status_code=501, detail="Shopify webhook receiver lands in v1")


@app.post("/telegram/webhook")
async def telegram_webhook() -> dict[str, str]:
    # TODO(v0): wire python-telegram-bot Application.update_queue.put_nowait(Update.de_json(...))
    raise HTTPException(status_code=501, detail="Telegram webhook wiring lands in v0 slice 2")


@app.post("/agent/run")
async def agent_run() -> dict[str, str]:
    # TODO(v0): invoke LangGraph graph from ads_agent.agent.graph
    raise HTTPException(status_code=501, detail="Agent run endpoint lands in v0 slice 2")


@app.post("/jobs/reconcile")
async def job_reconcile() -> dict[str, str]:
    raise HTTPException(status_code=501, detail="Nightly reconciliation lands in v2")


@app.post("/jobs/daily_digest")
async def job_daily_digest() -> dict[str, str]:
    raise HTTPException(status_code=501, detail="Daily digest lands in v2")
