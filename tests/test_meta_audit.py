"""Meta audit: import surface + parser + brand mapping + graph wiring.

No live Meta Graph API or LLM calls — network is off for unit tests.
"""
from __future__ import annotations

import asyncio

import pytest


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_imports_and_graph_compiles():
    from ads_agent.agent.graph import build_graph
    from ads_agent.agent.nodes.meta_audit import meta_audit_node  # noqa: F401
    from ads_agent.agent.analysis.meta_audit_analyst import audit_meta_account  # noqa: F401
    from ads_agent.agent.analysis.meta_decomposer import (  # noqa: F401
        MetaAccountHierarchy, decompose_meta_account,
    )
    from ads_agent.meta.graph_client import (  # noqa: F401
        ads_for_account_lean, adsets_for_account, campaigns_for_account,
    )
    build_graph()


def test_brand_mapping(monkeypatch):
    """brand_for() is now driven by STORE_BRAND_REGISTRY_JSON.
    Inject a fixture registry and verify the slug→brand_key resolution."""
    import json
    monkeypatch.setenv(
        "STORE_BRAND_REGISTRY_JSON",
        json.dumps({
            "store-a": {"brand_key": "lighthouse", "primary_market": "IN",
                        "shop_host": "example.com", "amazon_marketplace": "amazon.in",
                        "currency": "INR"},
            "store-b": {"brand_key": "lighthouse", "primary_market": "AE",
                        "shop_host": "example.store", "amazon_marketplace": "amazon.ae",
                        "currency": "AED"},
            "store-c": {"brand_key": "alpha", "primary_market": "IN",
                        "shop_host": "alpha.in", "amazon_marketplace": "amazon.in",
                        "currency": "INR"},
        }),
    )
    from ads_agent.brand_registry import reset_registry
    reset_registry()
    from ads_agent.agent.nodes.meta_audit import _brand_for
    assert _brand_for("store-a") == "lighthouse"
    assert _brand_for("store-b") == "lighthouse"
    assert _brand_for("store-c") == "alpha"
    # Unmapped slug → "default"
    assert _brand_for("unknown-slug") == "default"


def test_analyst_parser_actions():
    from ads_agent.agent.analysis.meta_audit_analyst import _parse_report
    sample = """## PRE-FLIGHT
Attribution 7d-click. 14-day window. Pixel ok.

## ACCOUNT SUMMARY
Two campaigns, spend 40k INR, ROAS 1.2×.

## ADS TO PAUSE TODAY
- 12345 · HOJ video · spend 4200 · ROAS 0.8 · well below breakeven

### 1. PAUSE · HOJ video ad
- target_level: ad
- target_id: 12345
- rationale: spend ₹4,200, ROAS 0.8× vs breakeven 1.6×
- expected_impact: save ~₹2,100/week
- safety_check: none

### 2. REFRESH · GoodGut+ mama voice v1
- target_level: ad
- target_id: 67890
- rationale: frequency 3.1, 7d-ctr dropped 42% vs peak — fatigue not failure
- expected_impact: restore ctr, retain learning
- safety_check: produce new hook variant in <72h
"""
    parsed = _parse_report(sample)
    assert len(parsed["actions"]) == 2
    assert parsed["actions"][0]["action_kind"] == "PAUSE"
    assert parsed["actions"][0]["target_id"] == "12345"
    assert parsed["actions"][1]["action_kind"] == "REFRESH"
    assert "fatigue" in parsed["actions"][1]["rationale"]
    # Narrative retains pre-action sections
    assert "PRE-FLIGHT" in parsed["diagnosis"]
    assert "ADS TO PAUSE" in parsed["diagnosis"]


def test_playbook_meta_audit_briefs_resolve():
    """If private playbooks are mounted, they expose meta_audit briefs.
    Test is a no-op when no playbooks are deployed (open-source / CI default)."""
    from pathlib import Path

    from ads_agent.playbook import PLAYBOOK_DIR, node_brief
    if not PLAYBOOK_DIR.exists():
        pytest.skip("no playbooks/ directory — private playbook repo not mounted")
    md_files = list(Path(PLAYBOOK_DIR).glob("*.md"))
    if not md_files:
        pytest.skip("no playbook .md files mounted")
    # Every mounted playbook should expose a meta_audit brief.
    for md in md_files:
        brand = md.stem
        brief = node_brief("meta_audit", brand)
        assert brief, f"{brand} missing meta_audit brief"
        assert all(v in brief for v in ("SCALE", "REFRESH", "PAUSE", "WATCH"))
        assert "breakeven_roas" in brief and "target_roas" in brief


def test_concentration_carried_by_one():
    from ads_agent.agent.analysis.meta_decomposer import AdRow, _mk_concentration
    ads = [
        AdRow(ad_id="1", ad_name="winner", status="", effective_status="",
              spend=1000, impressions=10000, clicks=200, ctr=2.0, cpc=5, cpm=10,
              frequency=1.5, reach=8000, purchases=20, purchase_value=40000, roas=40, days_live=14),
        AdRow(ad_id="2", ad_name="noise", status="", effective_status="",
              spend=200, impressions=5000, clicks=50, ctr=1.0, cpc=4, cpm=8,
              frequency=1.2, reach=4000, purchases=0, purchase_value=0, roas=0, days_live=14),
    ]
    c = _mk_concentration(ads, campaign_revenue=40000)
    assert c.carried_by_one_ad is True
    assert c.top_ad_label == "winner"
    assert c.zero_purchase_ads_count == 1
