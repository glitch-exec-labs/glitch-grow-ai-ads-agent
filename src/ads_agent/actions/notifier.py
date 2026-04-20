"""Telegram notifier for the action approval loop.

One entry point: `post_proposal(...)` inserts a row into ads_agent.agent_actions
and posts it to the configured Telegram group with Approve/Reject inline buttons.
The message_id + chat_id are persisted so the button handler can find the row.

Button handler lives in src/ads_agent/telegram/callbacks.py.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

import asyncpg
import httpx

from ads_agent.actions.models import ActionProposal, format_telegram_message

log = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"


def _bot_token() -> str:
    tok = os.environ.get("TELEGRAM_BOT_TOKEN_ADS", "").strip()
    if not tok:
        raise RuntimeError("TELEGRAM_BOT_TOKEN_ADS not set")
    return tok


def _inline_keyboard(action_id: int) -> dict:
    return {
        "inline_keyboard": [[
            {"text": "✅ Approve",   "callback_data": f"act:approve:{action_id}"},
            {"text": "❌ Reject",    "callback_data": f"act:reject:{action_id}"},
        ]]
    }


async def post_proposal(
    pool: asyncpg.Pool,
    prop: ActionProposal,
    chat_id: int,
) -> int:
    """Insert action row, post to Telegram, return action_id."""
    # 1) Insert (status defaults to pending_approval)
    async with pool.acquire() as conn:
        action_id = await conn.fetchval(
            """INSERT INTO ads_agent.agent_actions (
                   store_slug, action_kind, target_object_id, target_object_name,
                   params, rationale, evidence, expected_impact, telegram_chat_id
               ) VALUES ($1,$2,$3,$4,$5::jsonb,$6,$7::jsonb,$8::jsonb,$9)
               RETURNING id""",
            prop.store_slug, prop.action_kind, prop.target_object_id,
            prop.target_object_name, json.dumps(prop.params),
            prop.rationale, json.dumps(prop.evidence), json.dumps(prop.expected_impact),
            chat_id,
        )

    # 2) Format + send to Telegram
    text = format_telegram_message(
        action_id=action_id,
        store_slug=prop.store_slug,
        action_kind=prop.action_kind,
        target_name=prop.target_object_name,
        rationale=prop.rationale,
        params=prop.params,
        evidence=prop.evidence,
        expected_impact=prop.expected_impact,
    )
    async with httpx.AsyncClient(timeout=15.0) as c:
        resp = await c.post(
            f"{TELEGRAM_API}/bot{_bot_token()}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
                "reply_markup": _inline_keyboard(action_id),
            },
        )
    body = resp.json()
    if not body.get("ok"):
        log.error("Telegram post failed for action %s: %s", action_id, body)
        return action_id

    msg_id = body["result"]["message_id"]
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE ads_agent.agent_actions SET telegram_message_id=$1 WHERE id=$2",
            msg_id, action_id,
        )
    log.info("Posted action %s to chat %s as msg %s", action_id, chat_id, msg_id)
    return action_id


async def post_text(chat_id: int, text: str, parse_mode: str = "Markdown") -> Optional[int]:
    """Free-form outbound message — used for action-executed confirmations,
    daily digests, alerts. No admin gating; the bot can speak whenever.
    """
    async with httpx.AsyncClient(timeout=15.0) as c:
        resp = await c.post(
            f"{TELEGRAM_API}/bot{_bot_token()}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text[:4000],
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            },
        )
    body = resp.json()
    if body.get("ok"):
        return body["result"]["message_id"]
    log.warning("post_text failed: %s", body)
    return None


async def edit_message_remove_buttons(
    chat_id: int, message_id: int, new_text: str
) -> None:
    """After Approve/Reject click, edit the original prompt to show resolution."""
    async with httpx.AsyncClient(timeout=15.0) as c:
        await c.post(
            f"{TELEGRAM_API}/bot{_bot_token()}/editMessageText",
            json={
                "chat_id": chat_id,
                "message_id": message_id,
                "text": new_text[:4000],
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
                "reply_markup": {"inline_keyboard": []},
            },
        )
