"""Action layer data model + MCP tool routing."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Action kinds we support in v1 — Meta write-actions only, Amazon is blocked
# on LWA app approval so those proposals are client-executed for now.
SUPPORTED_ACTION_KINDS: set[str] = {
    "pause_adset",           # effective_status → PAUSED on an adset
    "resume_adset",          # effective_status → ACTIVE on an adset
    "pause_ad",              # effective_status → PAUSED on a single ad
    "update_adset_budget",   # change daily_budget on an adset (params: new_daily_budget in minor units)
}

# Map action_kind → (meta_mcp_tool_name, params_builder_fn)
# params_builder_fn takes the action row and returns the dict to pass to MCP.


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


ACTION_TO_MCP: dict[str, tuple[str, Any]] = {
    "pause_adset":          ("update_adset", _pause_adset_params),
    "resume_adset":         ("update_adset", _resume_adset_params),
    "pause_ad":             ("update_ad",    _pause_ad_params),
    "update_adset_budget":  ("update_adset", _update_adset_budget_params),
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
        "pause_adset":          "⏸ Pause ad set",
        "resume_adset":         "▶️ Resume ad set",
        "pause_ad":             "⏸ Pause ad",
        "update_adset_budget":  "💰 Update ad-set daily budget",
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
