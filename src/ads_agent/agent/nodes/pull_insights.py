"""pull_insights: deterministic Shopify summary for a store + lookback window.

v0: called by /insights Telegram command. No LLM — just SQL/GraphQL roll-up.
v1: gains LLM summarization via ads_agent.agent.llm.pick('cheap').
"""
from __future__ import annotations

from ads_agent.config import get_store
from ads_agent.shopify.admin_gql import ORDERS_LAST_N_DAYS, ShopifyAdminClient
from ads_agent.shopify.sessions import get_session


async def pull_insights_node(state: dict) -> dict:
    slug = state["store_slug"]
    days = int(state.get("days", 7))
    store = get_store(slug)
    if store is None:
        return {**state, "reply_text": f"unknown store: {slug}"}

    sess = await get_session(store.shop_domain)
    if sess is None:
        return {**state, "reply_text": f"no Shopify session found for {store.shop_domain}"}

    client = ShopifyAdminClient(store.shop_domain, sess.access_token)
    data = await client.query(
        ORDERS_LAST_N_DAYS,
        variables={
            "query": f"created_at:>-{days}d",
            "first": 250,
            "after": None,
        },
    )
    edges = data.get("orders", {}).get("edges", [])

    count = len(edges)
    gross = 0.0
    currency = store.currency
    for e in edges:
        node = e["node"]
        amt = node.get("currentTotalPriceSet", {}).get("shopMoney", {}).get("amount")
        if amt is not None:
            gross += float(amt)
        currency = (
            node.get("currentTotalPriceSet", {}).get("shopMoney", {}).get("currencyCode")
            or currency
        )

    aov = (gross / count) if count else 0.0
    summary = {
        "store_slug": slug,
        "shop_domain": store.shop_domain,
        "days": days,
        "order_count": count,
        "gross_revenue": round(gross, 2),
        "currency": currency,
        "avg_order_value": round(aov, 2),
    }
    reply = (
        f"*{store.brand}* ({store.shop_domain}) — last {days}d\n"
        f"Orders: {count}\n"
        f"Revenue: {gross:,.2f} {currency}\n"
        f"AOV: {aov:,.2f} {currency}"
    )
    return {**state, "orders_summary": summary, "reply_text": reply}
