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
    ask_analyst,
    budget_recs,
    list_sp_campaigns,
)

# Templated analyst prompt used when Amazon's native account_recs endpoint
# isn't available (currently US-only). Asks for specific, action-oriented
# output matching what account_recs would have produced.
_ANALYST_FALLBACK_QUESTION = (
    "For the last 14 days on this account, list the 5 highest-impact "
    "optimization opportunities across Sponsored Products. For each one, "
    "include: (a) the specific campaign name / ad group name / keyword / ASIN "
    "the opportunity concerns, (b) a concrete metric that justifies it "
    "(e.g. 'cost 520 with 0 sales14d' or 'impression share 18%'), (c) the "
    "recommended action in one verb phrase (pause / lower bid to X / "
    "increase budget to Y / add negative keyword). Rank by estimated "
    "weekly savings or incremental sales. Be concise — no preamble."
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
        # MAP's account_recs endpoint is US-only. Non-US markets (IN + AE for
        # Ayurpet) get a text message pointing at the report_analyst fallback.
        # We take that hint: call ask_report_analyst with a templated question
        # so IN + AE still get actionable recommendations instead of a dead
        # "not available" line.
        text_msg = recs.get("text") or ""
        is_unsupported = bool(
            text_msg
            and ("not available" in text_msg.lower() or "error" in text_msg.lower())
        )

        if is_unsupported:
            # Fallback: ask the analyst the same question Amazon's native
            # endpoint would have answered.
            try:
                analyst = await ask_analyst(iid, aid, _ANALYST_FALLBACK_QUESTION)
            except MapMcpError as e:
                analyst = {"error": str(e)}

            if analyst.get("_plan_gated"):
                lines.append(f"*Recs (analyst fallback):* plan-gated — upgrade MAP to unlock")
            elif "error" in analyst:
                lines.append(f"*Recs (analyst fallback):* error — {analyst['error'][:120]}")
            else:
                # Analyst replies as either structured JSON or free-form text
                # under the top-level `text` key. Treat as free-form for now —
                # let the LLM-side formatting carry through.
                answer = analyst.get("text") or analyst.get("answer") or str(analyst)
                lines.append(f"*Recs* (via Amazon report analyst · {country}):")
                # Truncate very long answers so the Telegram message stays
                # readable; full content is still available via /amazon_recs
                # follow-ups or MAP's web UI.
                if len(answer) > 1500:
                    answer = answer[:1500] + "\n…(truncated; drill-down via MAP UI)"
                for line in answer.splitlines():
                    if line.strip():
                        lines.append(f"  {line}")
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
