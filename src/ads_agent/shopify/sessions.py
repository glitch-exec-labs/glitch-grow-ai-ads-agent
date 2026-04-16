"""Read-only access to the multi-store-theme-manager Prisma Session table.

DB: 127.0.0.1:5432/shopify_app
Role: insights_ro (SELECT only on "Session") — must be created manually:

    CREATE USER insights_ro WITH PASSWORD '...';
    GRANT CONNECT ON DATABASE shopify_app TO insights_ro;
    GRANT USAGE ON SCHEMA public TO insights_ro;
    GRANT SELECT ON "Session" TO insights_ro;
"""
from __future__ import annotations

from dataclasses import dataclass

import asyncpg

from ads_agent.config import settings


@dataclass(frozen=True)
class ShopifySession:
    shop: str
    access_token: str
    scope: str
    is_online: bool


async def get_session(shop_domain: str) -> ShopifySession | None:
    """Fetch the offline session for a shop. Returns None if not installed."""
    conn = await asyncpg.connect(settings().postgres_insights_ro_url)
    try:
        row = await conn.fetchrow(
            '''SELECT shop, "accessToken", scope, "isOnline"
               FROM "Session"
               WHERE shop = $1 AND "isOnline" = false
               ORDER BY expires DESC NULLS FIRST
               LIMIT 1''',
            shop_domain,
        )
    finally:
        await conn.close()
    if row is None:
        return None
    return ShopifySession(
        shop=row["shop"],
        access_token=row["accessToken"],
        scope=row["scope"] or "",
        is_online=row["isOnline"],
    )


async def list_sessions() -> list[ShopifySession]:
    """All offline sessions. Used by /scopes_check."""
    conn = await asyncpg.connect(settings().postgres_insights_ro_url)
    try:
        rows = await conn.fetch(
            '''SELECT DISTINCT ON (shop) shop, "accessToken", scope, "isOnline"
               FROM "Session"
               WHERE "isOnline" = false
               ORDER BY shop, expires DESC NULLS FIRST'''
        )
    finally:
        await conn.close()
    return [
        ShopifySession(
            shop=r["shop"], access_token=r["accessToken"], scope=r["scope"] or "", is_online=r["isOnline"]
        )
        for r in rows
    ]
