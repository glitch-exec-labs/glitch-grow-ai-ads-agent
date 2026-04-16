"""Idempotently register Shopify webhooks for every configured store (v1).

For each store in ads_agent.config.STORES:
  - Load its offline session token (asyncpg on 127.0.0.1:5432, insights_ro)
  - GraphQL webhookSubscriptions query, create the missing topics pointing at
    {PUBLIC_BASE_URL}/shopify/webhook/{shop_domain}

Topics: ORDERS_CREATE, ORDERS_PAID, ORDERS_FULFILLED, ORDERS_CANCELLED, REFUNDS_CREATE.

Stub in v0. Full impl lands in v1 once the /shopify/webhook/{shop} FastAPI route is wired.
"""
from __future__ import annotations

TOPICS = (
    "ORDERS_CREATE",
    "ORDERS_PAID",
    "ORDERS_FULFILLED",
    "ORDERS_CANCELLED",
    "REFUNDS_CREATE",
)


async def main() -> int:
    raise SystemExit("register_webhooks lands in v1")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
