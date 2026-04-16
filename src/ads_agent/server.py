"""FastAPI entrypoint.

Endpoints:
  GET  /healthz                    liveness + git sha
  POST /shopify/webhook/{shop}     HMAC-verified Shopify webhook receiver
  POST /telegram/webhook           python-telegram-bot Update receiver (v1+)
  POST /agent/run                  LangGraph entrypoint (v0+)
  POST /jobs/reconcile             Cloud Scheduler nightly reconciliation (v2+)
  POST /jobs/daily_digest          Cloud Scheduler morning digest (v2+)
"""
from __future__ import annotations

import json
import logging
import os

from fastapi import FastAPI, HTTPException, Request

from ads_agent import __version__
from ads_agent.config import settings
from ads_agent.shopify.webhooks import HmacVerificationError, handle_webhook, verify_hmac

log = logging.getLogger(__name__)

app = FastAPI(
    title="Glitch Grow Ads Agent",
    version=__version__,
    description="Systematic ads ops agent for Shopify stores.",
)


@app.get("/healthz")
async def healthz() -> dict:
    return {
        "status": "ok",
        "version": __version__,
        "git_sha": os.environ.get("GIT_SHA", "dev"),
        "public_base_url": settings().public_base_url,
    }


@app.post("/shopify/webhook/{shop}")
async def shopify_webhook(shop: str, request: Request) -> dict:
    """Receive and process a Shopify webhook.

    Shopify sends the shop as the path param (we use the myshopify domain).
    The raw body must be read before any JSON parsing so HMAC can be verified
    against the original bytes.
    """
    raw_body = await request.body()
    hmac_header = request.headers.get("X-Shopify-Hmac-Sha256", "")
    topic = request.headers.get("X-Shopify-Topic", "")

    # --- HMAC verification ---
    try:
        verify_hmac(shop_domain=shop, raw_body=raw_body, header_hmac_b64=hmac_header)
    except HmacVerificationError as exc:
        log.warning("hmac fail shop=%s topic=%s err=%s", shop, topic, exc)
        raise HTTPException(status_code=401, detail="hmac verification failed")

    # --- Parse + route (fire-and-forget; Shopify needs 200 within 5s) ---
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="invalid json body")

    # Don't await — let it run in background so we return 200 immediately
    import asyncio
    asyncio.ensure_future(
        handle_webhook(topic=topic, shop_domain=shop, payload=payload)
    )
    return {"ok": True}


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request) -> dict:
    """Receive Telegram Update and hand to python-telegram-bot."""
    # TODO(v1): wire to bot Application.update_queue
    raise HTTPException(status_code=501, detail="Telegram webhook wiring lands in v1")


@app.post("/agent/run")
async def agent_run(request: Request) -> dict:
    """Run a LangGraph agent command."""
    body = await request.json()
    from ads_agent.agent.graph import build_graph
    graph = build_graph()
    state = await graph.ainvoke(body)
    return {"reply": state.get("reply_text", ""), "state": state}


@app.post("/jobs/reconcile")
async def job_reconcile() -> dict:
    raise HTTPException(status_code=501, detail="Nightly reconciliation lands in v2")


@app.post("/jobs/daily_digest")
async def job_daily_digest() -> dict:
    raise HTTPException(status_code=501, detail="Daily digest lands in v2")
