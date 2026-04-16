"""Backfill historical Shopify orders into PostHog.

Pulls orders from Shopify Admin GraphQL for a given store + lookback window
and fires them as PostHog `order_paid` events. Idempotent — PostHog dedupes
on (distinct_id, event, timestamp) within a short window, but duplicate events
for backfill are harmless (they carry the same order_id so you can dedupe in SQL).

Usage:
    python ops/scripts/backfill_posthog.py --store urban --days 90
    python ops/scripts/backfill_posthog.py --store ayurpet-ind --days 90
    python ops/scripts/backfill_posthog.py --all --days 90

Requires:
    - POSTGRES_INSIGHTS_RO_URL in .env (to load access tokens from Session table)
    - POSTHOG_API_KEY in .env
    - Store must be installed (session present in DB)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone

sys.path.insert(0, "src")

from dotenv import load_dotenv

load_dotenv()

from ads_agent.config import STORES, get_store
from ads_agent.posthog.client import capture_order_event, client as ph_client
from ads_agent.shopify.admin_gql import ShopifyAdminClient
from ads_agent.shopify.sessions import get_session

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Pagination: 250 orders per page (Shopify max for REST; GraphQL bulk handles more)
ORDERS_PAGE_SIZE = 250

GQL_ORDERS = """
query orders($query: String!, $first: Int!, $after: String) {
  orders(first: $first, after: $after, query: $query, sortKey: CREATED_AT) {
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        id
        name
        createdAt
        displayFinancialStatus
        currentTotalPriceSet { shopMoney { amount currencyCode } }
        customer { id email }
        lineItems(first: 50) {
          edges {
            node { title sku quantity originalUnitPriceSet { shopMoney { amount } } }
          }
        }
        customerJourneySummary {
          firstVisit {
            landingPageHtml
            utmParameters { source medium campaign content term }
          }
        }
        sourceName
        tags
      }
    }
  }
}
"""


def _node_to_order(node: dict, currency: str) -> dict:
    money = node.get("currentTotalPriceSet", {}).get("shopMoney", {})
    customer = node.get("customer") or {}
    customer_id = str(customer.get("id", "")).replace("gid://shopify/Customer/", "") or node.get("id", "")
    email = customer.get("email", "")

    utm_raw = (
        (node.get("customerJourneySummary") or {})
        .get("firstVisit") or {}
    ).get("utmParameters") or {}
    utm = {k: v for k, v in {
        "source": utm_raw.get("source"),
        "medium": utm_raw.get("medium"),
        "campaign": utm_raw.get("campaign"),
        "content": utm_raw.get("content"),
        "term": utm_raw.get("term"),
    }.items() if v}

    line_items = [
        {
            "title": e["node"].get("title"),
            "sku": e["node"].get("sku"),
            "quantity": e["node"].get("quantity"),
            "price": e["node"].get("originalUnitPriceSet", {}).get("shopMoney", {}).get("amount"),
        }
        for e in node.get("lineItems", {}).get("edges", [])
    ]

    return {
        "order_id": node["id"].replace("gid://shopify/Order/", ""),
        "order_name": node.get("name", ""),
        "value": float(money.get("amount", 0)),
        "currency": money.get("currencyCode", currency),
        "customer_id": customer_id,
        "email": email,
        "financial_status": node.get("displayFinancialStatus", "").lower(),
        "fulfillment_status": "unknown",
        "utm": utm,
        "line_items": line_items,
        "tags": node.get("tags", ""),
        "source_name": node.get("sourceName", ""),
    }


async def backfill_store(store_slug: str, days: int) -> int:
    store = get_store(store_slug)
    if store is None:
        log.error("unknown store: %s", store_slug)
        return 0

    sess = await get_session(store.shop_domain)
    if sess is None:
        log.error("no session for %s — is the app installed?", store.shop_domain)
        return 0

    gql = ShopifyAdminClient(store.shop_domain, sess.access_token)
    query = f"created_at:>-{days}d financial_status:paid"
    cursor = None
    total = 0

    log.info("backfilling %s (%s) last %d days...", store_slug, store.shop_domain, days)

    while True:
        data = await gql.query(GQL_ORDERS, variables={"query": query, "first": ORDERS_PAGE_SIZE, "after": cursor})
        orders_data = data.get("orders", {})
        edges = orders_data.get("edges", [])

        for edge in edges:
            order = _node_to_order(edge["node"], store.currency)
            capture_order_event(
                "order_paid",
                shop_domain=store.shop_domain,
                store_slug=store.slug,
                order=order,
            )
            total += 1

        page_info = orders_data.get("pageInfo", {})
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")
        log.info("  ...%d orders captured so far, fetching next page", total)

    ph_client().flush()
    log.info("done: %s — %d orders sent to PostHog", store_slug, total)
    return total


async def main(slugs: list[str], days: int) -> None:
    grand_total = 0
    for slug in slugs:
        grand_total += await backfill_store(slug, days)
    log.info("TOTAL: %d orders sent to PostHog across %d store(s)", grand_total, len(slugs))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill Shopify orders into PostHog")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--store", help="Store slug (e.g. urban, ayurpet-ind)")
    group.add_argument("--all", action="store_true", help="Backfill all configured stores")
    parser.add_argument("--days", type=int, default=90, help="Lookback window in days (default 90)")
    args = parser.parse_args()

    slugs = [s.slug for s in STORES] if args.all else [args.store]
    asyncio.run(main(slugs, args.days))
