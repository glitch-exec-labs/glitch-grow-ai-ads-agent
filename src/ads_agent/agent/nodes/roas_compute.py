"""roas_compute: true ROAS = Shopify paid revenue / Meta spend, vs Meta-reported ROAS.

Cross-currency aware: Shopify store currency and Meta ad account currency often
differ (e.g. Urban family sells in INR but runs ads in CAD). We convert Meta
spend into the Shopify store's currency using live FX before computing ROAS,
so the ratio is apples-to-apples.

Pulls:
  - Shopify paid revenue (from PostHog, last N days, in store.currency)
  - Meta spend + Meta-reported purchase_value (from Graph API, in each account's currency)
  - For stores with multiple ad accounts, sums converted spend across ALL linked accounts.

Store → ad-account multimap is loaded from STORE_AD_ACCOUNTS_JSON env var
via `ads_agent.config.STORE_AD_ACCOUNTS`. Never hard-code account IDs here.
"""
from __future__ import annotations

from ads_agent.config import STORE_AD_ACCOUNTS, get_store
from ads_agent.fx import convert
from ads_agent.meta.graph_client import MetaGraphError, account_spend
from ads_agent.posthog.queries import store_insights


# Per-store CAC threshold (ad-account native currency, per pipeline order).
# "Pipeline order" = paid + pending orders (real-world conversions; `paid`
# alone is artificially low because the delivery partner's status-integration
# to Shopify is currently broken — see user note 2026-04-16).
#
# Urban family: ~$3 CAD CAC is within threshold (10 orders / $30 CAD spend).
CAC_THRESHOLDS: dict[str, tuple[float, str]] = {
    "urban": (3.0, "CAD"),
    "storico": (3.0, "CAD"),
    "classicoo": (3.0, "CAD"),
    "trendsetters": (3.0, "CAD"),
    # Ayurpet and Mokshya thresholds TBD — fall back to no verdict
}


async def roas_compute_node(state: dict) -> dict:
    slug = state["store_slug"]
    days = int(state.get("days", 7))
    store = get_store(slug)
    if store is None:
        return {**state, "reply_text": f"Unknown store: `{slug}`"}

    shop_ccy = store.currency  # Shopify/native reporting currency
    shopify = await store_insights(store.slug, days)

    ad_accounts = STORE_AD_ACCOUNTS.get(store.slug, [])
    if not ad_accounts:
        return {**state, "reply_text": f"No Meta ad accounts mapped for `{slug}` yet."}

    # Aggregate in SHOP CURRENCY via FX, also keep Meta-native totals
    total_spend_shop = 0.0
    total_meta_value_shop = 0.0
    total_spend_native = 0.0
    total_meta_purchases = 0
    native_ccy: str | None = None
    account_lines: list[str] = []
    fx_notes: set[str] = set()

    for act in ad_accounts:
        try:
            d = await account_spend(act, days=days)
        except MetaGraphError as e:
            account_lines.append(f"  {act}: error ({str(e)[:60]})")
            continue

        meta_ccy = d["currency"]
        spend_native = d["spend"]
        value_native = d["purchase_value"]

        spend_shop = await convert(spend_native, meta_ccy, shop_ccy)
        value_shop = await convert(value_native, meta_ccy, shop_ccy)

        total_spend_shop += spend_shop
        total_meta_value_shop += value_shop
        total_spend_native += spend_native
        total_meta_purchases += d["purchases"]
        if native_ccy is None:
            native_ccy = meta_ccy

        if meta_ccy != shop_ccy:
            fx_notes.add(f"{meta_ccy}→{shop_ccy}")

        if d["spend"] > 0 or d["purchases"] > 0:
            if meta_ccy == shop_ccy:
                account_lines.append(
                    f"  {act}: spend {spend_native:,.2f} {meta_ccy} · "
                    f"{d['purchases']} purchases · reported rev {value_native:,.2f} {meta_ccy}"
                )
            else:
                account_lines.append(
                    f"  {act}: spend {spend_native:,.2f} {meta_ccy} (≈ {spend_shop:,.2f} {shop_ccy}) · "
                    f"{d['purchases']} purchases · reported rev {value_native:,.2f} {meta_ccy} (≈ {value_shop:,.2f} {shop_ccy})"
                )

    # Paid-only view (conservative floor — current "financial_status=paid" count)
    paid_roas = (shopify.paid_revenue / total_spend_shop) if total_spend_shop > 0 else 0.0

    # Pipeline view (paid + pending = all real conversions, since the delivery-partner
    # integration that promotes COD orders to paid is currently broken upstream)
    pipeline_orders = shopify.pipeline_orders
    pipeline_revenue = shopify.pipeline_revenue
    pipeline_roas = (pipeline_revenue / total_spend_shop) if total_spend_shop > 0 else 0.0

    # Customer Acquisition Cost per pipeline order, in Meta's native currency
    cac_native = (total_spend_native / pipeline_orders) if pipeline_orders > 0 else 0.0
    threshold = CAC_THRESHOLDS.get(store.slug)
    cac_verdict = ""
    if threshold and native_ccy == threshold[1] and cac_native > 0:
        target, t_ccy = threshold
        if cac_native <= target:
            cac_verdict = f" ✅ within threshold (≤ {target:.2f} {t_ccy})"
        elif cac_native <= target * 1.5:
            cac_verdict = f" 🟡 above threshold (target ≤ {target:.2f} {t_ccy}, +{(cac_native/target-1)*100:.0f}%)"
        else:
            cac_verdict = f" 🔴 well above threshold (target ≤ {target:.2f} {t_ccy}, +{(cac_native/target-1)*100:.0f}%)"

    meta_roas = (total_meta_value_shop / total_spend_shop) if total_spend_shop > 0 else 0.0

    fx_tag = ""
    if fx_notes:
        fx_tag = f"  (FX: {', '.join(sorted(fx_notes))})"

    lines = [
        f"*{store.brand}* · last {days}d · ROAS",
        "",
        f"Pipeline orders (paid+pending): *{pipeline_orders}*  ·  paid: {shopify.paid_orders}  ·  pending: {shopify.pending_orders}  ·  cancelled: {shopify.cancelled_orders}",
        f"Pipeline revenue: {pipeline_revenue:,.2f} {shop_ccy}  (paid: {shopify.paid_revenue:,.2f}, pending: {shopify.pending_revenue:,.2f})",
        f"Meta spend: {total_spend_native:,.2f} {native_ccy or '?'}  (≈ {total_spend_shop:,.2f} {shop_ccy}){fx_tag}",
        "",
        f"*Pipeline ROAS: {pipeline_roas:.2f}x*  (pipeline revenue / Meta spend, same-currency — use this as the truth until delivery-partner payment status is fixed)",
        f"Paid-only ROAS: {paid_roas:.2f}x  (conservative floor, under-reports because courier→Shopify status sync is broken)",
        f"Meta-reported ROAS: {meta_roas:.2f}x  (inflated by pixel/CAPI dedup issue)",
        "",
        f"*CAC per pipeline order: {cac_native:,.2f} {native_ccy or '?'}*{cac_verdict}",
    ]
    if account_lines:
        lines.append("")
        lines.append("Per-account breakdown (native currency first):")
        lines.extend(account_lines)

    return {**state, "reply_text": "\n".join(lines)}
