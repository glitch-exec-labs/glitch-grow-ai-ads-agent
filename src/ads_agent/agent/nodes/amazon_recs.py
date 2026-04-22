"""amazon_recs: Amazon's own recommendations for a store's SP account via MAP.

Complements `amazon_insights_node` (which reads our own Airbyte warehouse)
with three things that warehouse doesn't have:

  1. Enabled campaign roster with bid strategy + placement modifiers
     (list_resources sp_campaigns — free tier).
  2. Account-level bid/budget/targeting recommendations
     (get_amazon_ads_account_recs — paid, needs AI Connect plan).
  3. Per-campaign budget-exhaustion analysis with missed-opp estimates
     (get_amazon_ads_campaigns_budget_recs — paid).

If the account has no MAP mapping, returns a clean "not configured" reply
rather than raising — keeps the graph deterministic.

If the plan is not active, we still show the free-tier campaign roster
and flag the gated blocks with an upgrade hint.
"""
from __future__ import annotations

import logging

from ads_agent.config import STORE_MAP_ACCOUNTS, get_store
from ads_agent.map.mcp_client import (
    MapMcpError,
    account_recs,
    budget_recs,
    list_sp_campaigns,
)

log = logging.getLogger(__name__)


async def amazon_recs_node(state: dict) -> dict:
    slug = state["store_slug"]
    store = get_store(slug)
    if store is None:
        return {**state, "reply_text": f"Unknown store: `{slug}`"}

    mapping = STORE_MAP_ACCOUNTS.get(slug)
    if not mapping:
        return {**state, "reply_text": (
            f"*{store.brand}* · Amazon recs\n\n"
            f"No MAP account mapping for `{slug}`. "
            f"Add it to `STORE_MAP_ACCOUNTS_JSON` in .env to enable this command."
        )}

    iid, aid, country = mapping["integration_id"], mapping["account_id"], mapping["country"]
    lines = [f"*{store.brand} · Amazon {country}* · recommendations", ""]

    # 1. Campaign roster (free tier)
    try:
        campaigns = await list_sp_campaigns(iid, aid)
    except MapMcpError as e:
        return {**state, "reply_text": f"MAP error on campaign list: {e}"}

    if not campaigns:
        lines.append("No enabled Sponsored Products campaigns found.")
    else:
        total_budget = sum(
            float((c.get("budget") or {}).get("budget", 0) or 0) for c in campaigns
        )
        ccy = "INR" if country == "IN" else ("AED" if country == "AE" else "")
        lines.append(f"*Enabled SP campaigns:* {len(campaigns)} · "
                     f"total daily budget {total_budget:,.0f} {ccy}")
        # Top 5 by budget
        top = sorted(campaigns, key=lambda c: (c.get("budget") or {}).get("budget", 0) or 0, reverse=True)[:5]
        for c in top:
            b = (c.get("budget") or {}).get("budget", 0)
            strat = (c.get("dynamicBidding") or {}).get("strategy", "?")
            ttype = c.get("targetingType", "?")
            lines.append(f"  • {c['name'][:55]} · {b:.0f}/d · {strat} · {ttype}")
        if len(campaigns) > 5:
            lines.append(f"  …+{len(campaigns) - 5} more")
        lines.append("")

    # 2. Account recommendations (paid)
    try:
        recs = await account_recs(iid, aid)
    except MapMcpError as e:
        recs = {"error": str(e)}

    if recs.get("_plan_gated"):
        lines.append("*Account recs:* plan-gated (upgrade MAP to AI Connect)")
    elif "error" in recs:
        lines.append(f"*Account recs:* error — {recs['error'][:100]}")
    else:
        # MAP returns error strings under `text` for unsupported endpoints
        # (e.g. account_recs is US-only — other marketplaces get a helpful
        # "use ask_report_analyst instead" message).
        text_msg = recs.get("text") or ""
        if text_msg and ("error" in text_msg.lower() or "not available" in text_msg.lower()):
            lines.append(f"*Account recs:* not available for {country} market")
            lines.append(f"  _{text_msg[:200]}_")
        else:
            items = (
                recs.get("recommendations")
                or recs.get("items")
                or (recs.get("data") or {}).get("recommendations")
                or []
            )
            if not items:
                preview = str(recs)[:250]
                lines.append(f"*Account recs:* {preview}")
            else:
                lines.append(f"*Account recs:* {len(items)} surfaced")
                for r in items[:5]:
                    kind = r.get("recommendationType") or r.get("type") or "?"
                    desc = r.get("description") or r.get("message") or ""
                    lines.append(f"  • [{kind}] {str(desc)[:110]}")
                if len(items) > 5:
                    lines.append(f"  …+{len(items) - 5} more")
    lines.append("")

    # 3. Budget recommendations (paid)
    try:
        brecs = await budget_recs(iid, aid)
    except MapMcpError as e:
        brecs = {"error": str(e)}

    if brecs.get("_plan_gated"):
        lines.append("*Budget recs:* plan-gated (upgrade MAP to AI Connect)")
    elif "error" in brecs:
        lines.append(f"*Budget recs:* error — {brecs['error'][:100]}")
    else:
        items = (
            brecs.get("campaigns")
            or brecs.get("items")
            or (brecs.get("data") or {}).get("campaigns")
            or []
        )
        # Filter to campaigns at risk of running out (MAP surfaces this signal
        # under various keys depending on the API version we hit — cover bases)
        at_risk = [
            i for i in items
            if i.get("missedOpportunity") or i.get("outOfBudgetProb")
            or (i.get("budgetRecommendation") or {}).get("recommendedBudget")
        ]
        if not at_risk and items:
            at_risk = items  # show everything if we can't filter
        if not at_risk:
            lines.append("*Budget recs:* no campaigns flagged as at-risk")
        else:
            lines.append(f"*Budget recs:* {len(at_risk)} campaign(s) may need more budget")
            for r in at_risk[:5]:
                name = r.get("campaignName") or r.get("name") or r.get("campaignId", "?")
                miss = r.get("missedOpportunity") or r.get("estimatedMissedImpressions")
                rec = (r.get("budgetRecommendation") or {}).get("recommendedBudget")
                extras = []
                if rec:
                    extras.append(f"→ bump to {rec}")
                if miss:
                    extras.append(f"miss {miss}")
                lines.append(f"  • {str(name)[:55]} {' · '.join(extras)}")
            if len(at_risk) > 5:
                lines.append(f"  …+{len(at_risk) - 5} more")

    lines.append("")
    lines.append("_source: Marketplace Ad Pros (MAP) · proxied Amazon Ads Partner API_")
    return {**state, "reply_text": "\n".join(lines)}
