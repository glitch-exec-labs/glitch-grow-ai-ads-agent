"""amazon_insights: Amazon Seller + Amazon Ads rollup for a store.

Reads from `ads_agent.amazon_daily_v` — a Postgres view that normalises the
Airbyte-written `airbyte_amazon.*` tables into our canonical shape. Sub-second.

Architecture:
  Amazon Seller Partner + Amazon Ads → Airbyte Cloud → SSH tunnel → our Postgres
    → airbyte_amazon.Orders / sponsored_*_report_stream_daily
    → ads_agent.amazon_daily_v (UNION + marketplace → store_slug mapping)
    → THIS NODE

The OLD Supermetrics sync cron (glitch-amazon-sync.timer) is retired — it
served as the bridge before Airbyte was wired. Supermetrics MCP tools in
amazon-ads-mcp remain for ad-hoc Claude Code exploration only.
"""
from __future__ import annotations

import logging

import asyncpg

from ads_agent.config import get_store, settings

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
        fin = await conn.fetchrow(
            """SELECT SUM(gross_revenue)        AS gross,
                      SUM(fees)                 AS fees,
                      SUM(refunds)              AS refunds,
                      SUM(refund_fee_reversal)  AS refund_fee_reversal,
                      SUM(ads_deducted)         AS ads_deducted,
                      SUM(service_fees)         AS service_fees,
                      SUM(net_amount)           AS net,
                      MAX(currency)             AS currency,
                      COUNT(*)                  AS days_settled
               FROM ads_agent.amazon_financials_daily_v
               WHERE store_slug = $1
                 AND date > (CURRENT_DATE - ($2::int * INTERVAL '1 day'))""",
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

    # ── Amazon Ads (Sponsored Products/Brands/Display) ────────────────────────
    if ads_rows:
        total_cost   = sum(float(r["cost"]   or 0) for r in ads_rows)
        total_sales  = sum(float(r["sales"]  or 0) for r in ads_rows)
        total_orders = sum(int  (r["orders"] or 0) for r in ads_rows)
        family_roas = (total_sales / total_cost) if total_cost else 0
        lines.append("*Amazon Ads (per report/market, top-spend first)*")
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
        lines.append("")
    else:
        lines.append("*Amazon Ads:* no data yet in the window")
        lines.append(
            "  — Airbyte ad report streams may still be backfilling, or the Ads "
            "source config needs widening. Check `airbyte_amazon.sponsored_*` tables."
        )
        lines.append("")

    # ── Net Profit (settlement-basis, from Finances API) ──────────────────────
    # Keyed on PostedDate (when money hits the settlement ledger), NOT PurchaseDate.
    # So totals here may diverge from Seller Central Orders above by a few days' lag.
    if fin and fin["net"] is not None:
        ccy = fin["currency"] or ""
        gross = float(fin["gross"] or 0)
        fees  = float(fin["fees"]  or 0)
        refs  = float(fin["refunds"] or 0)
        ads_d = float(fin["ads_deducted"] or 0)
        svc   = float(fin["service_fees"] or 0)
        net   = float(fin["net"] or 0)
        margin = (net / gross * 100) if gross else 0
        lines.append("*Net Profit (settlement-basis, Finances API)*")
        lines.append(
            f"  net {net:,.2f} {ccy} on gross {gross:,.2f} "
            f"({margin:.1f}% margin · {fin['days_settled']} settled days)"
        )
        lines.append(
            f"  fees {fees:,.2f} · refunds {refs:,.2f} · "
            f"ads {ads_d:,.2f} · service {svc:,.2f}"
        )
        lines.append("")

    # Cache freshness
    last_synced = max((r["last_synced"] for r in rows if r["last_synced"]), default=None)
    if last_synced:
        from datetime import datetime, timezone
        age_h = (datetime.now(timezone.utc) - last_synced).total_seconds() / 3600
        lines.append(f"_cache last synced: {age_h:.1f}h ago · source: Airbyte Cloud → Postgres_")

    return {**state, "reply_text": "\n".join(lines)}
