"""meta_audit: operator-grade D2C Meta Ads account audit.

Runs the per-brand methodology prompt (playbooks/<brand>.md Section X →
`meta_audit`) against a decomposed MetaAccountHierarchy. Output is the
four-verb action list: SCALE / REFRESH / PAUSE / WATCH.

Trigger:
  Telegram — /meta_audit <store> [days]
  Discord  — /meta_audit <store> [days]

Dispatcher route key: "meta_audit".

Pipeline cost: 4 Meta Graph API pulls (≈3-6 s) + 1 LLM complete
(≈12-25 s on Gemini 2.5 Pro with 16k max_tokens). Total ~20-35 s per run
for an account with <50 campaigns and <500 ads. Cached per (account, day).
"""
from __future__ import annotations

import logging

from ads_agent.agent.analysis.meta_audit_analyst import audit_meta_account
from ads_agent.agent.analysis.meta_decomposer import decompose_meta_account
from ads_agent.config import get_store
from ads_agent.meta.graph_client import MetaGraphError

log = logging.getLogger(__name__)


def _brand_for(slug: str) -> str:
    """Store slug → brand playbook key (for node_brief lookup)."""
    if slug.startswith("ayurpet"):
        return "ayurpet"
    if slug == "mokshya":
        return "mokshya"
    if slug in {"urban", "storico", "classicoo", "trendsetters"}:
        return "urban"
    return slug


async def meta_audit_node(state: dict) -> dict:
    slug = state["store_slug"]
    days = int(state.get("days", 14))
    store = get_store(slug)
    if store is None:
        return {**state, "reply_text": f"Unknown store: `{slug}`. /stores for list."}

    ad_account_id = store.meta_ad_account
    if not ad_account_id:
        return {
            **state,
            "reply_text": (
                f"*{store.brand}* · no Meta ad account mapped for `{slug}`. "
                "Add it to STORES_JSON in .env."
            ),
        }

    try:
        hierarchy = await decompose_meta_account(ad_account_id, days=days)
    except MetaGraphError as e:
        return {**state, "reply_text": f"*{store.brand}* · Meta audit failed at decompose: `{e}`"}
    except Exception as e:  # noqa: BLE001
        log.exception("meta_audit decompose unexpected")
        return {**state, "reply_text": f"*{store.brand}* · Meta audit unexpected decompose error: `{e}`"}

    if hierarchy.summary.spend == 0 and hierarchy.summary.impressions == 0:
        return {
            **state,
            "reply_text": (
                f"*{store.brand}* · Meta audit\n\n"
                f"No delivery in the last {days} days (account `{ad_account_id}` "
                f"had 0 spend, 0 impressions). Nothing to audit."
            ),
        }

    try:
        report = await audit_meta_account(hierarchy, brand=_brand_for(slug))
    except Exception as e:  # noqa: BLE001
        log.exception("meta_audit analyst unexpected")
        return {
            **state,
            "reply_text": (
                f"*{store.brand}* · Meta audit — decompose ok, analyst failed: `{e}`\n"
                f"Account snapshot: {hierarchy.summary.n_campaigns} campaigns · "
                f"{hierarchy.summary.spend:,.0f} {hierarchy.summary.currency} spend · "
                f"{hierarchy.summary.blended_roas:.2f}× blended ROAS."
            ),
        }

    body = (report.get("diagnosis") or "").strip()
    n_actions = len(report.get("actions") or [])
    # Header with account-level anchor
    header = (
        f"*{store.brand} · Meta audit* · account `{ad_account_id}` · "
        f"{days}d · {hierarchy.summary.n_campaigns} campaigns · "
        f"{hierarchy.summary.spend:,.0f} {hierarchy.summary.currency} spent · "
        f"ROAS {hierarchy.summary.blended_roas:.2f}×\n"
        f"_methodology: playbooks/{_brand_for(slug)}.md · Section X · "
        f"{n_actions} rule-qualified actions_\n\n"
    )
    return {**state, "reply_text": header + body}
