"""Idempotently register Shopify webhooks for every configured store.

For each store:
  1. Load its offline session token from the auth-hub Session table.
  2. List existing webhook subscriptions.
  3. Create any missing topics pointing at {PUBLIC_BASE_URL}/shopify/webhook/{shop_domain}.

Topics: ORDERS_CREATE, ORDERS_PAID, ORDERS_FULFILLED, ORDERS_CANCELLED, REFUNDS_CREATE.

Usage:
    python ops/scripts/register_webhooks.py
    python ops/scripts/register_webhooks.py --store urban   # single store
    python ops/scripts/register_webhooks.py --dry-run       # preview only
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

sys.path.insert(0, "src")

from dotenv import load_dotenv

load_dotenv()

from ads_agent.config import STORES, get_store, settings
from ads_agent.shopify.admin_gql import ShopifyAdminClient, ShopifyAdminError
from ads_agent.shopify.sessions import get_session

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

TOPICS = [
    "ORDERS_CREATE",
    "ORDERS_PAID",
    "ORDERS_FULFILLED",
    "ORDERS_CANCELLED",
    "REFUNDS_CREATE",
]

LIST_WEBHOOKS = """
query listWebhooks($first: Int!) {
  webhookSubscriptions(first: $first) {
    edges {
      node {
        id
        topic
        endpoint { ... on WebhookHttpEndpoint { callbackUrl } }
      }
    }
  }
}
"""

CREATE_WEBHOOK = """
mutation createWebhook($topic: WebhookSubscriptionTopic!, $url: URL!) {
  webhookSubscriptionCreate(
    topic: $topic
    webhookSubscription: { callbackUrl: $url, format: JSON }
  ) {
    userErrors { field message }
    webhookSubscription { id topic }
  }
}
"""

DELETE_WEBHOOK = """
mutation deleteWebhook($id: ID!) {
  webhookSubscriptionDelete(id: $id) {
    userErrors { field message }
    deletedWebhookSubscriptionId
  }
}
"""


async def register_for_store(store_slug: str, dry_run: bool = False) -> None:
    store = get_store(store_slug)
    if store is None:
        log.error("unknown store: %s", store_slug)
        return

    sess = await get_session(store.shop_domain)
    if sess is None:
        log.error("no session for %s — app not installed", store.shop_domain)
        return

    gql = ShopifyAdminClient(store.shop_domain, sess.access_token)
    base_url = settings().public_base_url.rstrip("/")
    callback_url = f"{base_url}/shopify/webhook/{store.shop_domain}"

    # List existing
    try:
        data = await gql.query(LIST_WEBHOOKS, variables={"first": 50})
    except ShopifyAdminError as e:
        log.error("could not list webhooks for %s: %s", store_slug, e)
        return

    existing: dict[str, str] = {}  # topic -> webhook_id
    stale: list[str] = []          # ids pointing at wrong URL

    for edge in data.get("webhookSubscriptions", {}).get("edges", []):
        node = edge["node"]
        topic = node["topic"]
        url = node.get("endpoint", {}).get("callbackUrl", "")
        wid = node["id"]
        if topic in TOPICS:
            if url == callback_url:
                existing[topic] = wid
            else:
                log.info("  stale webhook %s topic=%s url=%s", wid, topic, url)
                stale.append(wid)

    # Remove stale hooks pointing at old URLs
    for wid in stale:
        if dry_run:
            log.info("[DRY-RUN] would delete stale webhook %s", wid)
            continue
        try:
            await gql.query(DELETE_WEBHOOK, variables={"id": wid})
            log.info("  deleted stale webhook %s", wid)
        except ShopifyAdminError as e:
            log.warning("  could not delete %s: %s", wid, e)

    # Create missing
    missing = [t for t in TOPICS if t not in existing]
    if not missing:
        log.info("%s — all %d webhooks already registered ✓", store_slug, len(TOPICS))
        return

    for topic in missing:
        if dry_run:
            log.info("[DRY-RUN] would create %s -> %s", topic, callback_url)
            continue
        try:
            result = await gql.query(CREATE_WEBHOOK, variables={"topic": topic, "url": callback_url})
            errors = result.get("webhookSubscriptionCreate", {}).get("userErrors", [])
            if errors:
                log.error("  error creating %s: %s", topic, errors)
            else:
                wid = result["webhookSubscriptionCreate"]["webhookSubscription"]["id"]
                log.info("  created %s -> %s (%s)", topic, callback_url, wid)
        except ShopifyAdminError as e:
            log.error("  could not create %s: %s", topic, e)

    log.info("%s — done: %d created, %d stale removed", store_slug, len(missing), len(stale))


async def main(slugs: list[str], dry_run: bool) -> None:
    for slug in slugs:
        await register_for_store(slug, dry_run=dry_run)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Register Shopify webhooks for all Glitch Grow stores")
    parser.add_argument("--store", help="Single store slug (default: all stores)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without making changes")
    args = parser.parse_args()

    slugs = [args.store] if args.store else [s.slug for s in STORES]
    asyncio.run(main(slugs, dry_run=args.dry_run))
