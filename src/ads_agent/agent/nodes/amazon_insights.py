"""amazon_insights: Amazon Seller + Amazon Ads rollup for a store.

Mixed-source since 2026-04-22:
  - Seller Central block → Airbyte warehouse (ads_agent.amazon_daily_v).
    The SP-API connection is separate and syncs cleanly; leave it alone.
  - Amazon Ads block → MAP (Marketplace Ad Pros MCP).
    Airbyte's Amazon Ads EU connection has a ~56% data-loss bug (see
    diagnostic notes in the Apr-22 chat transcript). MAP proxies Amazon's
    Partner Network API directly and returns authoritative totals, fresh
    within the hour. Plan-gated behind AI Connect ($10/wk).

When MAP is unavailable (plan lapse, server down), we fall back to the
Airbyte warehouse — same query path as before — so the node degrades
gracefully but flags the output with a `(airbyte fallback — may be stale)`
tag so downstream readers know to treat numbers as approximate.

Architecture:
  Amazon Seller Partner → Airbyte Cloud → Postgres → ads_agent.amazon_daily_v
                                                       │
                                                       ├── Seller block (THIS NODE)
                                                       └── Ads fallback (THIS NODE)

  Amazon Ads API (via MAP's Partner creds) ── MAP MCP ── THIS NODE (primary)
"""
from __future__ import annotations

import logging

import asyncpg

from ads_agent.amazon.ads_api import AmazonAdsError, ads_totals, profile_id_for
from ads_agent.config import get_store, settings
# Backward alias so existing except-clauses keep working
MapMcpError = AmazonAdsError

log = logging.getLogger(__name__)


async def amazon_insights_node(state: dict) -> dict:
    slug = state["store_slug"]
    days = int(state.get("days", 30))
    store = get_store(slug)
    if store is None:
        return {**state, "reply_text": f"Unknown store: `{slug}`"}

    conn = await asyncpg.connect(settings().postgres_insights_ro_url)
    try:
        rows = await conn.fetch(
            """SELECT source, report_type, marketplace, account_id, currency,
                      SUM(impressions) AS impressions,
                      SUM(clicks)      AS clicks,
                      SUM(cost)        AS cost,
                      SUM(sales)       AS sales,
                      SUM(orders)      AS orders,
                      MAX(synced_at)   AS last_synced
               FROM ads_agent.amazon_daily_v
               WHERE store_slug = $1
                 AND date > (CURRENT_DATE - ($2::int * INTERVAL '1 day'))
               GROUP BY source, report_type, marketplace, account_id, currency
               ORDER BY source, sales DESC NULLS LAST, cost DESC NULLS LAST""",
            slug, days,
        )
    except asyncpg.UndefinedTableError:
        return {**state, "reply_text": (
            f"*{store.brand}* · Amazon insights\n\n"
            f"`ads_agent.amazon_daily_v` view doesn't exist. "
            f"Apply `ops/scripts/migrate_airbyte_amazon_view_v4.sql` and retry."
        )}
    finally:
        await conn.close()

    if not rows:
        return {**state, "reply_text": (
            f"*{store.brand}* · Amazon (last {days}d)\n\n"
            f"No rows in the normalization view for this store. Either Airbyte hasn't "
            f"synced yet OR no data for this store in the window. Check Airbyte Cloud "
            f"connection status."
        )}

    lines = [f"*{store.brand}* · Amazon (last {days}d)", ""]

    seller_rows = [r for r in rows if r["source"] == "seller"]
    ads_rows    = [r for r in rows if r["source"] == "ads"]

    # ── Seller Central ────────────────────────────────────────────────────────
    if seller_rows:
        total_orders = sum(int(r["orders"] or 0) for r in seller_rows)
        total_sales  = sum(float(r["sales"] or 0) for r in seller_rows)
        ccy = seller_rows[0]["currency"] or ""
        aov = (total_sales / total_orders) if total_orders else 0
        lines.append("*Seller Central (paying orders only)*")
        lines.append(
            f"  total: {total_orders} orders · {total_sales:,.2f} {ccy} revenue · AOV {aov:,.2f}"
        )
        for r in seller_rows:
            orders = int(r["orders"] or 0)
            sales = float(r["sales"] or 0)
            r_aov = (sales / orders) if orders else 0
            lines.append(
                f"• {r['marketplace'] or r['account_id']}: "
                f"{orders} orders · {sales:,.2f} {r['currency'] or ''} · AOV {r_aov:,.2f}"
            )
        lines.append("")

    # ── Amazon Ads — native LWA (primary) with Airbyte fallback ──────────────
    used_source = "amazon_native"
    ads_block_rendered = False
    has_profile = False
    try:
        await profile_id_for(slug)
        has_profile = True
    except AmazonAdsError:
        pass

    if has_profile:
        try:
            t = await ads_totals(slug, days)
        except AmazonAdsError as e:
            log.warning("native ads_totals failed for %s: %s; falling back to Airbyte", slug, e)
            t = None
            used_source = "airbyte-fallback"

        if t:
            cost  = float(t.get("spend") or 0)
            sales = float(t.get("sales14d") or 0)
            roas = (sales / cost) if cost else 0
            lines.append(
                f"*Amazon Ads (native LWA · authoritative)*"
            )
            ccy = (store.currency or "")
            lines.append(
                f"  spend {cost:,.2f} {ccy} · sales14d {sales:,.2f} {ccy} · "
                f"ROAS {roas:.2f}x · purchases14d {t.get('purchases14d', 0)} · "
                f"clicks {t.get('clicks', 0):,} · imp {t.get('impressions', 0):,}"
            )
            lines.append(
                f"  _for multi-market breakdown, use_ `/amazon_recs {slug}`"
            )
            lines.append("")
            ads_block_rendered = True

    if not ads_block_rendered:
        # Airbyte fallback — same logic as before, but flagged as approximate
        if ads_rows:
            total_cost   = sum(float(r["cost"]   or 0) for r in ads_rows)
            total_sales  = sum(float(r["sales"]  or 0) for r in ads_rows)
            total_orders = sum(int  (r["orders"] or 0) for r in ads_rows)
            family_roas = (total_sales / total_cost) if total_cost else 0
            lines.append("*Amazon Ads (airbyte fallback — may be stale/partial)*")
            lines.append(
                f"  total: spend {total_cost:,.2f} · sales {total_sales:,.2f} · "
                f"ROAS {family_roas:.2f}x · orders {total_orders}"
            )
            for r in ads_rows:
                cost  = float(r["cost"]  or 0)
                sales = float(r["sales"] or 0)
                if cost == 0 and (r["orders"] or 0) == 0:
                    continue
                r_roas = (sales / cost) if cost else 0
                lines.append(
                    f"• {r['marketplace'] or r['account_id']} [{r['report_type']}]: "
                    f"spend {cost:,.2f} · sales {sales:,.2f} · ROAS {r_roas:.2f}x · "
                    f"orders {r['orders']}"
                )
        else:
            lines.append("*Amazon Ads:* no data yet in the window")
            lines.append(
                "  — neither MAP nor Airbyte returned data. Check MAP plan status "
                "or `airbyte_amazon.sponsored_*` tables."
            )
        lines.append("")

    # Source footer — be explicit about where each block came from
    last_synced = max((r["last_synced"] for r in rows if r["last_synced"]), default=None)
    footer_bits = []
    if seller_rows and last_synced:
        from datetime import datetime, timezone
        age_h = (datetime.now(timezone.utc) - last_synced).total_seconds() / 3600
        footer_bits.append(f"Seller: Airbyte ({age_h:.1f}h old)")
    if used_source == "map":
        footer_bits.append("Ads: MAP (≤1h old, authoritative)")
    elif used_source == "airbyte-fallback":
        footer_bits.append("Ads: Airbyte fallback (MAP unreachable — numbers may be ~50% low)")
    if footer_bits:
        lines.append("_" + " · ".join(footer_bits) + "_")

    return {**state, "reply_text": "\n".join(lines)}
