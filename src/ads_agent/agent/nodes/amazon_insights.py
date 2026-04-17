"""amazon_insights: summarize Amazon Ads + Seller data for a store via the
amazon-ads-mcp MCP server (port 3105).

Architecture note: the agent does NOT talk to Supermetrics or Amazon's APIs
directly. All Amazon data passes through the amazon-ads-mcp sibling repo at
glitch-exec-labs/amazon-ads-mcp. That MCP owns both the native Amazon Ads
API path (pending LWA approval) and the Supermetrics fallback tools.

IMPORTANT latency caveat:
  Live MCP calls to `supermetrics_ads_performance` take 120–180s per account
  because Amazon's async Reports API is slow. This command reads from a
  local cache (ads_agent.amazon_daily, populated nightly by a sync cron).
  When the cache is empty or stale, the fallback surface is a plain error
  message pointing at the sync job — never a 3-minute hang.

Until the cache-sync job lands, this node reports whatever's in the cache
and flags freshness.
"""
from __future__ import annotations

import logging
from typing import Any

from ads_agent.config import get_store

log = logging.getLogger(__name__)

# Per-store Amazon account mapping is held in .env AMAZON_ACCOUNTS_JSON and
# consumed by the sync cron + this node. See docs in README + the
# amazon-ads-mcp repo for the shape.
import json
import os


def _amazon_accounts_for_store(slug: str) -> list[dict]:
    raw = os.environ.get("AMAZON_ACCOUNTS_JSON", "").strip()
    if not raw:
        return []
    try:
        return json.loads(raw).get(slug, [])
    except json.JSONDecodeError:
        return []


async def amazon_insights_node(state: dict) -> dict:
    slug = state["store_slug"]
    days = int(state.get("days", 30))
    store = get_store(slug)
    if store is None:
        return {**state, "reply_text": f"Unknown store: `{slug}`"}

    accts = _amazon_accounts_for_store(slug)
    if not accts:
        return {**state, "reply_text": (
            f"*{store.brand}* · Amazon insights\n\n"
            f"No Amazon accounts mapped for `{slug}`. "
            f"Add an entry to `AMAZON_ACCOUNTS_JSON` in `.env` once the store "
            f"has Amazon Seller Central / Amazon Ads connected in Supermetrics "
            f"(temporary) or via our LWA app (after approval)."
        )}

    # Read from the cache table. If table doesn't exist yet, give a clear pointer.
    import asyncpg
    from ads_agent.config import settings

    lines = [f"*{store.brand}* · Amazon (last {days}d)", ""]
    try:
        conn = await asyncpg.connect(settings().postgres_insights_ro_url)
        try:
            rows = await conn.fetch(
                """SELECT source, account_id, marketplace, report_type,
                          SUM(impressions) AS impressions,
                          SUM(clicks) AS clicks,
                          SUM(cost) AS cost,
                          SUM(sales) AS sales,
                          SUM(orders) AS orders,
                          MAX(synced_at) AS last_synced
                   FROM ads_agent.amazon_daily
                   WHERE store_slug = $1
                     AND date > (CURRENT_DATE - ($2::int * INTERVAL '1 day'))
                   GROUP BY source, account_id, marketplace, report_type
                   ORDER BY cost DESC NULLS LAST""",
                slug, days,
            )
        finally:
            await conn.close()
    except asyncpg.UndefinedTableError:
        return {**state, "reply_text": (
            f"*{store.brand}* · Amazon insights\n\n"
            f"Cache table `ads_agent.amazon_daily` doesn't exist yet. "
            f"The nightly sync job (`ops/scripts/sync_amazon.py`) needs to be "
            f"deployed first — it's a sibling to our PostHog sync pattern for Shopify. "
            f"Direct live queries to amazon-ads-mcp take 2–3 min per account so we "
            f"can't serve them inline; cache-and-read is the only viable architecture."
        )}
    except Exception as e:
        return {**state, "reply_text": f"*{store.brand}* · Amazon insights\n\nDB error: `{str(e)[:150]}`"}

    if not rows:
        return {**state, "reply_text": (
            f"*{store.brand}* · Amazon (last {days}d)\n\n"
            f"No cached Amazon rows. The sync job hasn't populated this store yet "
            f"OR the window has no data. Run `ops/scripts/sync_amazon.py --store {slug}` "
            f"manually to backfill."
        )}

    ads_rows = [r for r in rows if r["source"] == "ads"]
    seller_rows = [r for r in rows if r["source"] == "seller"]

    if ads_rows:
        total_cost = sum(float(r["cost"] or 0) for r in ads_rows)
        total_sales = sum(float(r["sales"] or 0) for r in ads_rows)
        total_orders = sum(int(r["orders"] or 0) for r in ads_rows)
        family_roas = (total_sales / total_cost) if total_cost else 0
        lines.append("*Amazon Ads (per market, top-spend first)*")
        lines.append(
            f"  total: spend {total_cost:,.2f} · sales {total_sales:,.2f} · "
            f"ROAS {family_roas:.2f}x · orders {total_orders}"
        )
        for r in ads_rows:
            cost = float(r["cost"] or 0)
            sales = float(r["sales"] or 0)
            if cost == 0 and (r["orders"] or 0) == 0:
                continue
            roas = sales / cost if cost else 0
            lines.append(
                f"• {r['marketplace'] or r['account_id']} [{r['report_type']}]: "
                f"spend {cost:,.2f} · sales {sales:,.2f} · ROAS {roas:.2f}x · "
                f"orders {r['orders']}"
            )
        lines.append("")

    if seller_rows:
        lines.append("*Seller Central (per marketplace)*")
        for r in seller_rows:
            # Seller-side metrics are sessions-only for now (schema TBD on native path)
            lines.append(f"• {r['marketplace'] or r['account_id']}: sessions {int(r['orders'] or 0):,}")
        lines.append("")

    # Cache freshness
    last_synced = max((r["last_synced"] for r in rows), default=None)
    if last_synced:
        from datetime import datetime, timezone
        age_h = (datetime.now(timezone.utc) - last_synced).total_seconds() / 3600
        lines.append(f"_cache last synced: {age_h:.1f}h ago · source: amazon-ads-mcp_")

    return {**state, "reply_text": "\n".join(lines)}
