"""Action layer data model + MCP tool routing."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Action kinds we support. v1 added Meta write-actions; v2 extends with
# Amazon write-actions routed through the MAP MCP (no direct LWA needed).
SUPPORTED_ACTION_KINDS: set[str] = {
    # --- Meta (glitch-ads-mcp) ---
    "pause_adset",                 # effective_status → PAUSED on an adset
    "resume_adset",                # effective_status → ACTIVE on an adset
    "pause_ad",                    # effective_status → PAUSED on a single ad
    "update_adset_budget",         # change daily_budget on an adset (params: new_daily_budget in minor units)
    # --- Amazon Ads (MAP MCP) ---
    "amazon_pause_ad",             # state → PAUSED on a sp_product_ads row (target_object_id = adId)
    "amazon_add_negative_keyword", # create sp_negative_keywords row (target_object_id = adGroupId;
                                   # params: keyword_text, match_type in {NEGATIVE_EXACT, NEGATIVE_PHRASE})
}

# Map action_kind → (mcp_client_tag, mcp_tool_name, params_builder_fn).
#
# mcp_client_tag routes the call to the right MCP at execute-time:
#   "meta" → ads_agent.meta.mcp_client.call_tool (local glitch-ads-mcp :3103)
#   "map"  → ads_agent.map.mcp_client.call_tool  (remote MAP, Bearer-auth)
#
# params_builder_fn takes the action row (as dict) and returns the kwargs
# dict to hand to that tool. Executor handles prior-state snapshotting and
# no-op guards based on client_tag + action_kind.


# ---- Meta param builders (unchanged from v1) ----

def _pause_adset_params(action: dict) -> dict:
    return {"adset_id": action["target_object_id"], "status": "PAUSED"}


def _resume_adset_params(action: dict) -> dict:
    return {"adset_id": action["target_object_id"], "status": "ACTIVE"}


def _pause_ad_params(action: dict) -> dict:
    return {"ad_id": action["target_object_id"], "status": "PAUSED"}


def _update_adset_budget_params(action: dict) -> dict:
    params = action.get("params") or {}
    return {
        "adset_id": action["target_object_id"],
        "daily_budget": params.get("new_daily_budget"),
    }


# ---- Amazon / MAP param builders ----
#
# MAP's `update_resources` and `create_resources` tools take:
#   { integration_id, account_id, resource_type, resources: [{...}] }
# where `resources` is the Amazon-Ads-API-native resource shape. We stash
# integration_id + account_id in the action's params dict at proposal time
# (populated by planner from STORE_MAP_ACCOUNTS).


def _amazon_pause_ad_params(action: dict) -> dict:
    """Flip a single sp_product_ads row to paused state.

    Amazon SP API accepts `state: "paused"` (lowercase) on update.
    """
    params = action.get("params") or {}
    return {
        "integration_id": params["integration_id"],
        "account_id":     params["account_id"],
        "resource_type":  "sp_product_ads",
        "resources": [
            {"adId": action["target_object_id"], "state": "paused"},
        ],
    }


def _amazon_add_negative_keyword_params(action: dict) -> dict:
    """Create a NEGATIVE_EXACT or NEGATIVE_PHRASE negative keyword on an
    ad group to prevent future spend on a wasteful search term."""
    params = action.get("params") or {}
    return {
        "integration_id": params["integration_id"],
        "account_id":     params["account_id"],
        "resource_type":  "sp_negative_keywords",
        "resources": [{
            "campaignId":  params["campaign_id"],
            "adGroupId":   action["target_object_id"],
            "keywordText": params["keyword_text"],
            "matchType":   params.get("match_type", "NEGATIVE_EXACT"),
            "state":       "enabled",
        }],
    }


# Tuple is (mcp_client_tag, tool_name, params_fn).
ACTION_TO_MCP: dict[str, tuple[str, str, Any]] = {
    "pause_adset":                 ("meta", "update_adset",     _pause_adset_params),
    "resume_adset":                ("meta", "update_adset",     _resume_adset_params),
    "pause_ad":                    ("meta", "update_ad",        _pause_ad_params),
    "update_adset_budget":         ("meta", "update_adset",     _update_adset_budget_params),
    "amazon_pause_ad":             ("map",  "update_resources", _amazon_pause_ad_params),
    "amazon_add_negative_keyword": ("map",  "create_resources", _amazon_add_negative_keyword_params),
}


# Chat that receives approval prompts. Hardcoded for Ayurpet v1 — when we
# onboard a second brand this moves into STORES config.
# Group was upgraded to supergroup on 2026-04-20, chat_id shifted accordingly.
AYURPET_CHAT_ID = -1003881144191   # "Ayurpet X Glitch Grow" (supergroup)


@dataclass
class ActionProposal:
    """In-memory proposal shape — planner emits these, notifier persists them."""
    store_slug: str
    action_kind: str
    target_object_id: str
    target_object_name: str
    rationale: str
    params: dict = field(default_factory=dict)
    evidence: dict = field(default_factory=dict)
    expected_impact: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.action_kind not in SUPPORTED_ACTION_KINDS:
            raise ValueError(f"unsupported action_kind: {self.action_kind}")


def format_telegram_message(
    *,
    action_id: int,
    store_slug: str,
    action_kind: str,
    target_name: str,
    rationale: str,
    params: dict,
    evidence: dict,
    expected_impact: dict,
) -> str:
    """Render the Telegram post. Must be < 4096 chars (Telegram limit)."""
    verb = {
        "pause_adset":                 "⏸ Pause ad set",
        "resume_adset":                "▶️ Resume ad set",
        "pause_ad":                    "⏸ Pause ad",
        "update_adset_budget":         "💰 Update ad-set daily budget",
        "amazon_pause_ad":             "🛒⏸ Pause Amazon product ad",
        "amazon_add_negative_keyword": "🛒🚫 Add Amazon negative keyword",
    }.get(action_kind, action_kind)

    lines = [
        f"*Action proposal #{action_id}*",
        f"{verb}: `{target_name}`",
        f"_Store: {store_slug}_",
        "",
        "*Why:*",
        rationale,
        "",
    ]

    if evidence:
        lines.append("*Evidence:*")
        for k, v in evidence.items():
            lines.append(f"  • {k.replace('_',' ')}: {v}")
        lines.append("")

    if action_kind == "update_adset_budget":
        new_b = params.get("new_daily_budget")
        old_b = params.get("old_daily_budget")
        if old_b and new_b:
            pct = (new_b - old_b) / old_b * 100
            lines.append(f"*Change:* ₹{old_b/100:,.0f}/day → ₹{new_b/100:,.0f}/day ({pct:+.0f}%)")
            lines.append("")

    if expected_impact:
        lines.append("*Expected impact:*")
        for k, v in expected_impact.items():
            lines.append(f"  • {k.replace('_',' ')}: {v}")
        lines.append("")

    lines.append("_Approve or Reject below. Auto-expires in 72h._")

    return "\n".join(lines)[:4000]
