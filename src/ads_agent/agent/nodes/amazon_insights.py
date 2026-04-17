"""amazon_insights: summarize Amazon Seller + Amazon Ads data for a store.

Currently wired for Ayurpet India + Ayurpet Global (UAE marketplace).
Other stores can be added by populating their entry in AMAZON_ACCOUNTS_JSON.
"""
from __future__ import annotations

import logging

from ads_agent.amazon.supermetrics_client import (
    SupermetricsError,
    amazon_accounts_for_store,
    ads_stats,
    seller_stats,
)
from ads_agent.config import get_store

log = logging.getLogger(__name__)


async def amazon_insights_node(state: dict) -> dict:
    slug = state["store_slug"]
    days = int(state.get("days", 30))
    store = get_store(slug)
    if store is None:
        return {**state, "reply_text": f"Unknown store: `{slug}`"}

    accts = amazon_accounts_for_store(slug)
    if not accts:
        return {**state, "reply_text": (
            f"*{store.brand}* · Amazon insights\n\n"
            f"No Amazon accounts mapped for `{slug}`. "
            f"Add entries to `AMAZON_ACCOUNTS_JSON` in `.env` after connecting "
            f"the Amazon Seller Central / Amazon Ads login in Supermetrics."
        )}

    lines = [f"*{store.brand}* · Amazon (last {days}d)", ""]

    # Seller Central
    try:
        seller_rows = await seller_stats(slug, days=days)
    except SupermetricsError as e:
        seller_rows = []
        lines.append(f"🟡 Seller Central fetch error: `{str(e)[:100]}`")
        lines.append(
            "  → Supermetrics OAuth likely expired. Re-authenticate in the Supermetrics dashboard: "
            "Team → Data source logins → reconnect the Amazon Seller Central login."
        )
        lines.append("")

    if seller_rows:
        # aggregate by marketplace. Supermetrics ASELL returns the column name
        # as seen in the UI (e.g. "Sessions - total"), so we tolerate case + suffix variants.
        def _f(row: dict, *keys: str) -> float:
            for k in keys:
                for rk, v in row.items():
                    if rk.lower().startswith(k.lower()):
                        try:
                            return float(v or 0)
                        except (TypeError, ValueError):
                            return 0
            return 0

        by_mp: dict[str, dict] = {}
        for r in seller_rows:
            mp = r["_marketplace"]
            b = by_mp.setdefault(mp, {"sessions": 0.0})
            b["sessions"] += _f(r, "sessions")
        lines.append("*Seller Central (per marketplace)*")
        for mp, b in by_mp.items():
            lines.append(f"• {mp}: sessions {b['sessions']:,.0f}")
        lines.append(
            "  _(Seller Central schema discovery partial — only `Sessions` validated. "
            "Revenue + unit fields need Supermetrics docs lookup.)_"
        )
        lines.append("")

    # Amazon Ads
    try:
        ads_rows = await ads_stats(slug, days=days)
    except SupermetricsError as e:
        ads_rows = []
        if "no Amazon Ads accounts" not in str(e):
            lines.append(f"🟡 Amazon Ads fetch error: `{str(e)[:100]}`")
            lines.append("")

    if ads_rows:
        def _f(row: dict, *keys: str) -> float:
            for k in keys:
                for rk, v in row.items():
                    if rk.lower() == k.lower():
                        try:
                            return float(v or 0)
                        except (TypeError, ValueError):
                            return 0
            return 0

        by_acct: dict[str, dict] = {}
        for r in ads_rows:
            k = r["_marketplace"]
            b = by_acct.setdefault(k, {"cost": 0.0, "sales": 0.0, "impr": 0, "clicks": 0, "orders": 0})
            b["cost"] += _f(r, "cost", "Cost")
            b["sales"] += _f(r, "sales", "Sales")
            b["impr"] += _f(r, "impressions", "Impressions")
            b["clicks"] += _f(r, "clicks", "Clicks")
            b["orders"] += _f(r, "orders", "Orders")

        # Sort by cost desc so top-spend markets surface first
        ordered = sorted(by_acct.items(), key=lambda kv: kv[1]["cost"], reverse=True)
        # Family totals
        total_cost = sum(b["cost"] for _, b in ordered)
        total_sales = sum(b["sales"] for _, b in ordered)
        total_orders = sum(b["orders"] for _, b in ordered)
        family_roas = (total_sales / total_cost) if total_cost > 0 else 0
        lines.append(f"*Amazon Ads (per market, top-spend first)*")
        lines.append(f"  total: spend {total_cost:,.2f} · sales {total_sales:,.2f} · ROAS {family_roas:.2f}x · orders {total_orders}")
        for k, b in ordered:
            if b["cost"] == 0 and b["orders"] == 0:
                continue  # skip markets with no activity
            ctr = (b["clicks"] / b["impr"] * 100) if b["impr"] else 0
            roas = (b["sales"] / b["cost"]) if b["cost"] > 0 else 0
            lines.append(
                f"• {k}: spend {b['cost']:,.2f} · sales {b['sales']:,.2f} · "
                f"ROAS {roas:.2f}x · orders {b['orders']} · CTR {ctr:.2f}%"
            )

    if len(lines) == 2:  # header + empty
        lines.append("(no data returned — check Supermetrics OAuth connections)")

    return {**state, "reply_text": "\n".join(lines)}
