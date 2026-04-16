"""roas_compute: true ROAS = Shopify paid revenue / Meta spend, vs Meta-reported ROAS.

Pulls:
  - Shopify paid revenue (from PostHog, last N days)
  - Meta spend + Meta-reported purchase_value (from Graph API, same window)
  - For stores with multiple ad accounts (Urban, Storico, Mokshya — see
    SHOPIFY_STORES_INFRA.md), sums spend across ALL listed accounts for the store.
"""
from __future__ import annotations

from ads_agent.config import get_store
from ads_agent.meta.graph_client import MetaGraphError, account_spend
from ads_agent.posthog.queries import store_insights

# Each store -> list of Meta ad account IDs to sum across. Sourced from
# SHOPIFY_STORES_INFRA.md Reverse-view table. Server-only; not committed to public repo.
STORE_AD_ACCOUNTS: dict[str, list[str]] = {
    "urban": [
        "act_1765937727381511",  # URBAN-CAD-IST (primary)
        "act_1909845012991177",  # Urban-CAD-IST (secondary)
        "act_769104785114570",   # urban global (legacy)
    ],
    "storico": [
        "act_1072546905038329",  # Storico-New-CAD-IST (primary)
        "act_1134191618602887",  # STORICO-IST-CAD
        "act_755235000581939",   # Storico-New-CAD
        "act_3446595268850626",  # Storico-CAD-IST (disabled but may have historical data)
    ],
    "classicoo": ["act_1231977889107681"],
    "trendsetters": ["act_1445770643706149"],
    "ayurpet-ind": ["act_654879327196107"],
    "ayurpet-global": ["act_654879327196107"],  # same as India
    "mokshya": [
        "act_507013211846013",   # MOKSHYA-CAD-EST
        "act_30237311672580998", # Mokshya-INR-IST
    ],
}


async def roas_compute_node(state: dict) -> dict:
    slug = state["store_slug"]
    days = int(state.get("days", 7))
    store = get_store(slug)
    if store is None:
        return {**state, "reply_text": f"Unknown store: `{slug}`"}

    # Shopify side (PostHog)
    shopify = await store_insights(store.slug, days)

    # Meta side (Graph API, summed across all linked accounts)
    ad_accounts = STORE_AD_ACCOUNTS.get(store.slug, [])
    if not ad_accounts:
        return {**state, "reply_text": f"No Meta ad accounts mapped for `{slug}` yet."}

    total_spend = 0.0
    total_meta_purchases = 0
    total_meta_purchase_value = 0.0
    meta_currency = "?"
    account_lines: list[str] = []

    for act in ad_accounts:
        try:
            d = await account_spend(act, days=days)
        except MetaGraphError as e:
            account_lines.append(f"  {act}: error ({str(e)[:60]})")
            continue
        total_spend += d["spend"]
        total_meta_purchases += d["purchases"]
        total_meta_purchase_value += d["purchase_value"]
        meta_currency = d["currency"] if d["currency"] != "?" else meta_currency
        if d["spend"] > 0 or d["purchases"] > 0:
            account_lines.append(
                f"  {act}: spend {d['spend']:,.2f} {d['currency']} · {d['purchases']} purchases · reported rev {d['purchase_value']:,.2f}"
            )

    # ROAS maths (same-currency assumption — mismatch flagged explicitly)
    true_roas = (shopify.paid_revenue / total_spend) if total_spend > 0 else 0.0
    meta_roas = (total_meta_purchase_value / total_spend) if total_spend > 0 else 0.0
    delta_pct = ((meta_roas - true_roas) / true_roas * 100) if true_roas > 0 else 0.0

    currency_flag = ""
    if meta_currency != "?" and meta_currency != store.currency:
        currency_flag = f"  ⚠ currency mismatch: Shopify={store.currency}, Meta={meta_currency} — compare with care"

    lines = [
        f"*{store.brand}* · last {days}d · ROAS",
        "",
        f"Shopify paid revenue: {shopify.paid_revenue:,.2f} {store.currency}  ({shopify.paid_orders} paid orders)",
        f"Meta spend (all accounts): {total_spend:,.2f} {meta_currency}",
        f"Meta reported purchases: {total_meta_purchases} · reported value: {total_meta_purchase_value:,.2f} {meta_currency}",
        "",
        f"*True ROAS: {true_roas:.2f}x*",
        f"Meta-reported ROAS: {meta_roas:.2f}x",
        f"Delta: Meta over/under-reports by {delta_pct:+.1f}%",
    ]
    if account_lines:
        lines.append("")
        lines.append("Per-account breakdown:")
        lines.extend(account_lines)
    if currency_flag:
        lines.append("")
        lines.append(currency_flag)

    return {**state, "reply_text": "\n".join(lines)}
