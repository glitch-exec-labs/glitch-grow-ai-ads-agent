"""FastAPI entrypoint.

Endpoints:
  GET  /healthz
  POST /shopify/webhook/{shop}     — HMAC-verified Shopify webhook receiver
  POST /telegram/webhook           — Telegram Update receiver (webhook mode)
  POST /agent/run                  — direct LangGraph entrypoint (for curl testing)
"""
from __future__ import annotations

import hmac
import json
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from telegram import Update

from ads_agent import __version__
from ads_agent.config import settings
from ads_agent.shopify.webhooks import HmacVerificationError, handle_webhook, verify_hmac
from ads_agent.telegram.bot import build_app as build_telegram_app

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize the Telegram Application in webhook mode (no polling).
    tg_app = build_telegram_app()
    await tg_app.initialize()
    await tg_app.start()
    app.state.tg = tg_app
    log.info("Telegram bot started in webhook mode (token ...%s)", settings().telegram_bot_token_ads[-6:])
    try:
        yield
    finally:
        await tg_app.stop()
        await tg_app.shutdown()


app = FastAPI(
    title="Glitch Grow Ads Agent",
    version=__version__,
    description="Systematic ads ops agent for Shopify stores.",
    lifespan=lifespan,
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
    raw_body = await request.body()
    hmac_header = request.headers.get("X-Shopify-Hmac-Sha256", "")
    topic = request.headers.get("X-Shopify-Topic", "")

    try:
        verify_hmac(shop_domain=shop, raw_body=raw_body, header_hmac_b64=hmac_header)
    except HmacVerificationError as exc:
        log.warning("hmac fail shop=%s topic=%s err=%s", shop, topic, exc)
        raise HTTPException(status_code=401, detail="hmac verification failed")

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="invalid json body")

    import asyncio
    asyncio.ensure_future(handle_webhook(topic=topic, shop_domain=shop, payload=payload))
    return {"ok": True}


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request) -> dict:
    """Receive Telegram Updates. Parsed + queued to the python-telegram-bot Application.

    Security (issue #1): we require the `X-Telegram-Bot-Api-Secret-Token`
    header to match the secret we configured when calling Telegram's
    `setWebhook?secret_token=...`. Without this, anyone who reaches the
    public endpoint can forge Updates with spoofed user ids / callback
    payloads — which would bypass the admin gate entirely.

    The expected secret is read from TELEGRAM_WEBHOOK_SECRET. If unset we
    refuse to accept updates at all (fail closed): running this endpoint
    on the public internet without a secret is never correct.
    """
    expected = settings().telegram_webhook_secret
    if not expected:
        log.error("TELEGRAM_WEBHOOK_SECRET is unset — refusing webhook updates")
        raise HTTPException(status_code=503, detail="telegram webhook not configured")

    supplied = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    # Constant-time compare to avoid timing oracles.
    if not hmac.compare_digest(supplied, expected):
        # Log but return 401 plainly — don't give shape hints to attackers.
        log.warning("telegram webhook: bad/missing secret token header")
        raise HTTPException(status_code=401, detail="unauthorized")

    body = await request.json()
    update = Update.de_json(body, app.state.tg.bot)
    await app.state.tg.update_queue.put(update)
    return {"ok": True}


@app.get("/api/amazon/consent-url")
async def api_amazon_consent_url(request: Request) -> dict:
    """Generate an LWA consent URL for authorizing Amazon Ads API access.

    Gated by the same AGENT_RUN_TOKEN bearer as /agent/run (admin-only).
    Query params:
      account_ref — logical key for which advertiser this consent is for
                    (e.g. "ayurpet", "nuraveda-self"). Required.
      notes       — optional free-text to label the state row.

    Returns {url: "...", state_expires_in_seconds: 600}.
    """
    expected = settings().agent_run_token
    if not expected:
        raise HTTPException(status_code=503, detail="endpoint disabled (no token)")
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or not hmac.compare_digest(auth[len("Bearer "):], expected):
        raise HTTPException(status_code=401, detail="unauthorized")

    account_ref = request.query_params.get("account_ref", "").strip()
    if not account_ref:
        raise HTTPException(status_code=400, detail="account_ref required")
    notes = request.query_params.get("notes")

    import asyncpg
    from ads_agent.amazon.oauth import generate_consent_url

    pool = await asyncpg.create_pool(
        os.environ.get("POSTGRES_RW_URL") or settings().postgres_insights_ro_url,
        min_size=1, max_size=2,
    )
    try:
        url = await generate_consent_url(pool, account_ref=account_ref, notes=notes)
    finally:
        await pool.close()
    return {"url": url, "state_expires_in_seconds": 600, "account_ref": account_ref}


@app.post("/api/amazon/oauth/receive")
async def api_amazon_oauth_receive(request: Request) -> dict:
    """Callback landing — called by the Cloudflare Pages Function at
    grow.glitchexecutor.com/amazon/oauth/callback after Amazon redirects the
    user back with ?code=X&state=Y.

    Gated by INTERNAL_API_SECRET (shared between CF Function and this server).
    Body: {"code": "...", "state": "..."}
    """
    expected = os.environ.get("INTERNAL_API_SECRET", "").strip()
    if not expected:
        log.error("INTERNAL_API_SECRET is unset — refusing amazon oauth callback")
        raise HTTPException(status_code=503, detail="oauth receiver disabled")
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or not hmac.compare_digest(auth[len("Bearer "):], expected):
        raise HTTPException(status_code=401, detail="unauthorized")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json body")
    code  = (body.get("code")  or "").strip()
    state = (body.get("state") or "").strip()
    if not code or not state:
        raise HTTPException(status_code=400, detail="code and state are required")

    import asyncpg
    from ads_agent.amazon.oauth import receive_callback, OAuthError

    pool = await asyncpg.create_pool(
        os.environ.get("POSTGRES_RW_URL") or settings().postgres_insights_ro_url,
        min_size=1, max_size=2,
    )
    try:
        try:
            result = await receive_callback(pool, code=code, state=state)
        except OAuthError as e:
            log.warning("oauth receive failed: %s", e)
            raise HTTPException(status_code=400, detail=f"oauth: {e}")
    finally:
        await pool.close()
    return result


@app.post("/agent/run")
async def agent_run(request: Request) -> dict:
    """Direct LangGraph entrypoint.

    Security (issue #4): this endpoint executes the full LangGraph
    pipeline, which drives paid LLM calls and reads internal store
    analytics. It MUST NOT be publicly callable. We require a bearer
    token via `Authorization: Bearer <AGENT_RUN_TOKEN>`. If AGENT_RUN_TOKEN
    is unset, the endpoint is disabled (fail closed). In Cloud Run we
    additionally recommend gating it with IAM — do NOT deploy with
    `--allow-unauthenticated`.
    """
    expected = settings().agent_run_token
    if not expected:
        log.error("AGENT_RUN_TOKEN is unset — /agent/run is disabled")
        raise HTTPException(status_code=503, detail="agent run endpoint disabled")

    auth = request.headers.get("Authorization", "")
    prefix = "Bearer "
    if not auth.startswith(prefix) or not hmac.compare_digest(auth[len(prefix):], expected):
        raise HTTPException(status_code=401, detail="unauthorized")

    body = await request.json()
    from ads_agent.agent.graph import build_graph
    from ads_agent.memory.store import fire_and_forget as log_turn

    graph = build_graph()
    state = await graph.ainvoke(body)
    reply = state.get("reply_text", "")

    # Log the turn so curl-driven tests also accumulate in agent_memory.
    # user_tg_id=None → these show up as "non-Telegram / API" calls.
    log_turn(
        command=str(body.get("command", "unknown")),
        store_slug=body.get("store_slug") or None,
        user_tg_id=None,
        args={k: v for k, v in body.items() if k not in ("command", "store_slug")},
        reply_text=reply,
        key_metrics=state.get("orders_summary") if isinstance(state.get("orders_summary"), dict) else None,
    )
    return {"reply": reply, "state": state}
