"""attribution: Meta → Amazon attribution report.

Reads ads_agent.amazon_attribution_daily_v, which uses the subtraction model:
  meta_attributed = amazon_total − amazon_sp_ads
Assumes organic Amazon traffic ≈ 0 (valid while Ayurpet < ~20 orders/day).

Output is a structured Telegram block:
  - Store header (brand + currency)
  - Meta spend / clicks bucketed to Amazon vs Shopify
  - Amazon attribution table (orders, gross, ROAS)
  - Top-5 ASINs by Meta-to-Amazon spend
  - Caveats block

Model caveats in every reply — Ayurpet must understand the assumptions.
"""
from __future__ import annotations

import logging

import asyncpg

from ads_agent.config import get_store, settings

log = logging.getLogger(__name__)


async def attribution_node(state: dict) -> dict:
    slug = state["store_slug"]
    days = int(state.get("days", 30))
    store = get_store(slug)
    if store is None:
        return {**state, "reply_text": f"Unknown store: `{slug}`"}

    conn = await asyncpg.connect(settings().postgres_insights_ro_url)
    try:
        # Store-level totals
        agg = await conn.fetchrow(
            """SELECT
                   SUM(amz_orders)                  AS amz_orders,
                   SUM(amz_gross)                   AS amz_gross,
                   SUM(sp_orders)                   AS sp_orders,
                   SUM(sp_sales1d)                  AS sp_sales,
                   SUM(sp_cost)                     AS sp_cost,
                   SUM(meta_spend)                  AS meta_spend,
                   SUM(meta_clicks)                 AS meta_clicks,
                   SUM(meta_attributed_orders)      AS meta_orders,
                   SUM(meta_attributed_gross)       AS meta_gross_native,
                   SUM(meta_attributed_gross_inr)   AS meta_gross_inr,
                   MAX(currency)                    AS currency
               FROM ads_agent.amazon_attribution_daily_v
               WHERE store_slug = $1
                 AND date > (CURRENT_DATE - ($2::int * INTERVAL '1 day'))""",
            slug, days,
        )

        # Shopify-side Meta from meta_ads_daily (destination matches this store's
        # custom domain). Hardcoded per-slug mapping — simple and explicit.
        shopify_domain = {
            "ayurpet-ind":    "theayurpet.com",
            "ayurpet-global": "theayurpet.store",
        }.get(slug)

        shopify_row = None
        if shopify_domain:
            shopify_row = await conn.fetchrow(
                """SELECT
                       SUM(spend)          AS meta_spend,
                       SUM(clicks)         AS meta_clicks,
                       SUM(purchases)      AS meta_purchases,
                       SUM(purchase_value) AS meta_purchase_value
                   FROM ads_agent.meta_ads_daily
                   WHERE date > (CURRENT_DATE - ($1::int * INTERVAL '1 day'))
                     AND destination_url ILIKE '%' || $2 || '%'""",
                days, shopify_domain,
            )

        # Top-5 ASINs by Meta-to-Amazon spend
        top_asins = await conn.fetch(
            """SELECT
                   asin,
                   SUM(amz_orders)               AS amz_orders,
                   SUM(amz_gross)                AS amz_gross,
                   SUM(meta_spend)               AS meta_spend,
                   SUM(meta_clicks)              AS meta_clicks,
                   SUM(meta_attributed_orders)   AS meta_orders,
                   SUM(meta_attributed_gross)    AS meta_gross,
                   SUM(meta_attributed_gross_inr) AS meta_gross_inr
               FROM ads_agent.amazon_attribution_daily_v
               WHERE store_slug = $1
                 AND date > (CURRENT_DATE - ($2::int * INTERVAL '1 day'))
                 AND asin IS NOT NULL
                 AND meta_spend > 0
               GROUP BY asin
               ORDER BY meta_spend DESC
               LIMIT 5""",
            slug, days,
        )
    except asyncpg.UndefinedTableError:
        return {**state, "reply_text": (
            f"*{store.brand}* · attribution\n\n"
            f"`amazon_attribution_daily_v` view missing. Apply "
            f"`ops/scripts/migrate_amazon_attribution_view.sql` and retry."
        )}
    finally:
        await conn.close()

    if not agg or not agg["amz_orders"]:
        return {**state, "reply_text": (
            f"*{store.brand}* · attribution (last {days}d)\n\n"
            f"No Amazon orders in the window. Either Airbyte hasn't synced, or "
            f"this store's Seller Central source isn't configured."
        )}

    ccy = agg["currency"] or ("INR" if slug == "ayurpet-ind" else "AED")
    amz_gross = float(agg["amz_gross"] or 0)
    sp_sales = float(agg["sp_sales"] or 0)
    sp_cost = float(agg["sp_cost"] or 0)
    meta_spend = float(agg["meta_spend"] or 0)
    meta_clicks = int(agg["meta_clicks"] or 0)
    meta_orders = int(agg["meta_orders"] or 0)
    meta_gross_native = float(agg["meta_gross_native"] or 0)
    meta_gross_inr = float(agg["meta_gross_inr"] or 0)

    roas_inr = (meta_gross_inr / meta_spend) if meta_spend > 0 else 0
    cpo_inr = (meta_spend / meta_orders) if meta_orders > 0 else 0

    lines: list[str] = []
    lines.append(f"*{store.brand}* · Meta→Amazon attribution (last {days}d)")
    lines.append("")

    # ── Amazon side ─────────────────────────────────────────────────────────
    lines.append("*Amazon Seller*")
    lines.append(f"  orders: {int(agg['amz_orders'])} · gross: {amz_gross:,.0f} {ccy}")
    lines.append(f"  SP Ads: {int(agg['sp_orders'])} orders · {sp_sales:,.0f} {ccy} sales · {sp_cost:,.0f} {ccy} spend")
    lines.append("")

    lines.append("*Meta → Amazon (subtraction model)*")
    lines.append(f"  spend: ₹{meta_spend:,.0f} · clicks: {meta_clicks:,}")
    lines.append(f"  attributed orders: {meta_orders} · gross: {meta_gross_native:,.0f} {ccy}"
                 + (f" (~₹{meta_gross_inr:,.0f})" if ccy != "INR" else ""))
    lines.append(f"  *ROAS: {roas_inr:.2f}× · CPO: ₹{cpo_inr:,.0f}*")
    lines.append("")

    # ── Shopify side (Meta-reported; not attribution-model) ─────────────────
    if shopify_row and shopify_row["meta_spend"] and float(shopify_row["meta_spend"]) > 0:
        sh_spend = float(shopify_row["meta_spend"] or 0)
        sh_purch = int(shopify_row["meta_purchases"] or 0)
        sh_pv    = float(shopify_row["meta_purchase_value"] or 0)
        sh_roas  = (sh_pv / sh_spend) if sh_spend > 0 else 0
        sh_cpo   = (sh_spend / sh_purch) if sh_purch > 0 else 0
        lines.append(f"*Meta → Shopify ({shopify_domain}, Meta-reported)*")
        lines.append(f"  spend: ₹{sh_spend:,.0f} · purchases: {sh_purch} · value: ₹{sh_pv:,.0f}")
        lines.append(f"  reported ROAS: {sh_roas:.2f}× · CPO: ₹{sh_cpo:,.0f}")
        lines.append(f"  _note: Meta-side conversions known to over-report on this account; "
                     f"/roas {slug} for PostHog-ground-truth cross-check_")
        lines.append("")

        # Channel comparison
        total_spend = meta_spend + sh_spend
        if total_spend > 0:
            amz_share = meta_spend / total_spend * 100
            lines.append("*Channel split*")
            lines.append(f"  Amazon: ₹{meta_spend:,.0f} ({amz_share:.1f}% of Meta budget) → {roas_inr:.1f}× ROAS")
            lines.append(f"  Shopify: ₹{sh_spend:,.0f} ({100-amz_share:.1f}% of Meta budget) → {sh_roas:.1f}× ROAS (reported)")
            if roas_inr > sh_roas * 1.5 and meta_spend < sh_spend:
                lines.append(f"  ⚡ Amazon ROAS appears {roas_inr/max(sh_roas,0.01):.1f}× higher — consider reallocation")
            lines.append("")

    # ── Top ASINs by Meta-to-Amazon spend ───────────────────────────────────
    if top_asins:
        lines.append("*Top ASINs by Meta-to-Amazon spend*")
        for r in top_asins:
            ms = float(r["meta_spend"] or 0)
            mg_inr = float(r["meta_gross_inr"] or 0)
            mg_native = float(r["meta_gross"] or 0)
            asin_roas = (mg_inr / ms) if ms > 0 else 0
            lines.append(
                f"• `{r['asin']}`: spend ₹{ms:,.0f} · {int(r['meta_clicks'] or 0):,} clicks · "
                f"{int(r['meta_orders'] or 0)} orders · {mg_native:,.0f} {ccy} gross · {asin_roas:.1f}× ROAS"
            )
        lines.append("")

    # ── Caveats (always printed; methodology transparency) ──────────────────
    lines.append("_Method: Meta credited only for orders on ASINs it advertised "
                 f"(non-advertised ASIN orders classed as organic/halo). ROAS is INR/INR "
                 f"(AED→INR @ 22.7). **Upper bound** — repeat-buyer dedup blocked by "
                 f"PII-off config. Sessions refinement pending Airbyte SALES_AND_TRAFFIC sync._")

    return {**state, "reply_text": "\n".join(lines)}
