"""log_turn: fire-and-forget writer of command turns to ads_agent.agent_memory.

Never blocks a Telegram reply — called after the reply is sent, errors swallowed
with a warning. Writes are async via asyncpg; a single shared connection pool
is created on first use.

Week 1 scope: just write. Embeddings + recall come in Week 2.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import asyncpg

from ads_agent.config import settings

log = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None
_pool_lock = asyncio.Lock()


async def _get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        async with _pool_lock:
            if _pool is None:
                _pool = await asyncpg.create_pool(
                    settings().postgres_insights_ro_url,
                    min_size=1,
                    max_size=4,
                    command_timeout=5.0,
                )
    return _pool


async def log_turn(
    *,
    command: str,
    store_slug: str | None,
    user_tg_id: int | None,
    args: dict[str, Any] | None,
    reply_text: str,
    key_metrics: dict[str, Any] | None = None,
    agent_reasoning: str | None = None,
    kind: str = "insight",
) -> int | None:
    """Insert one row into ads_agent.agent_memory. Returns the new id or None on failure.

    All arguments are keyword-only to prevent positional mistakes. Never raises
    — failures are logged and swallowed since this is always a post-reply write.
    """
    try:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            row_id: int = await conn.fetchval(
                """
                INSERT INTO ads_agent.agent_memory
                    (user_tg_id, store_slug, command, args, reply_text, key_metrics, agent_reasoning, kind)
                VALUES
                    ($1, $2, $3, $4::jsonb, $5, $6::jsonb, $7, $8)
                RETURNING id
                """,
                user_tg_id,
                store_slug,
                command,
                json.dumps(args or {}),
                reply_text,
                json.dumps(key_metrics) if key_metrics is not None else None,
                agent_reasoning,
                kind,
            )
            return row_id
    except Exception:
        log.exception("log_turn failed (command=%s store=%s)", command, store_slug)
        return None


def fire_and_forget(
    *,
    command: str,
    store_slug: str | None,
    user_tg_id: int | None,
    args: dict[str, Any] | None,
    reply_text: str,
    key_metrics: dict[str, Any] | None = None,
    agent_reasoning: str | None = None,
    kind: str = "insight",
) -> None:
    """Schedule a log_turn call on the running loop without awaiting.

    Use this from Telegram handlers so writes never delay user-visible reply.
    """
    coro = log_turn(
        command=command,
        store_slug=store_slug,
        user_tg_id=user_tg_id,
        args=args,
        reply_text=reply_text,
        key_metrics=key_metrics,
        agent_reasoning=agent_reasoning,
        kind=kind,
    )
    asyncio.ensure_future(coro)
