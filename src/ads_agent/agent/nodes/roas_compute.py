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

    # Aggregate in SHOP CURRENCY via FX
    total_spend_shop = 0.0
    total_meta_value_shop = 0.0
    total_meta_purchases = 0
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
        total_meta_purchases += d["purchases"]

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

    # ROAS math — all in shop currency
    true_roas = (shopify.paid_revenue / total_spend_shop) if total_spend_shop > 0 else 0.0
    meta_roas = (total_meta_value_shop / total_spend_shop) if total_spend_shop > 0 else 0.0
    delta_pct = ((meta_roas - true_roas) / true_roas * 100) if true_roas > 0 else 0.0

    fx_tag = ""
    if fx_notes:
        fx_tag = f"  (FX: {', '.join(sorted(fx_notes))})"

    lines = [
        f"*{store.brand}* · last {days}d · ROAS",
        "",
        f"Shopify paid revenue: {shopify.paid_revenue:,.2f} {shop_ccy}  ({shopify.paid_orders} paid orders)",
        f"Meta spend (all accounts, in {shop_ccy}): {total_spend_shop:,.2f}{fx_tag}",
        f"Meta reported purchases: {total_meta_purchases} · reported value (in {shop_ccy}): {total_meta_value_shop:,.2f}",
        "",
        f"*True ROAS: {true_roas:.2f}x*  (Shopify paid revenue / Meta spend, same-currency)",
        f"Meta-reported ROAS: {meta_roas:.2f}x",
        f"Delta: Meta over/under-reports by {delta_pct:+.1f}%",
    ]
    if account_lines:
        lines.append("")
        lines.append("Per-account breakdown (native currency first):")
        lines.extend(account_lines)

    return {**state, "reply_text": "\n".join(lines)}
