"""Tests for the Phase A+B audit upgrades:
  - Health Score parsing
  - severity / effort / check_id action fields
  - Quick Wins extraction + sorting
  - Andromeda (M15) text-similarity diversity check
  - playbook reference loader
"""
from __future__ import annotations

import pytest


def test_load_ref_resolves_checklist_and_changes():
    from ads_agent.playbook import load_ref
    chk = load_ref("meta-audit-checklist")
    chg = load_ref("2025-platform-changes")
    assert "M01" in chk and "Critical-checks" in chk
    assert "Andromeda" in chg and "iOS 14.5" in chg


def test_load_ref_missing_returns_empty():
    from ads_agent.playbook import load_ref
    assert load_ref("not-a-real-ref-name-xyzzy") == ""


def test_diversity_flags_near_duplicates():
    from ads_agent.actions.diversity import diversity_report
    ads = [
        {"ad_id": "A", "ad_name": "Mama your dog scratching paw licking goodgut"},
        {"ad_id": "B", "ad_name": "Mama your dog scratching paw licking goodgut"},
        {"ad_id": "C", "ad_name": "HOJ joint pain Indian doctor walks shorter"},
        {"ad_id": "D", "ad_name": "CoolCalm anxiety vet recommended"},
    ]
    d = diversity_report(ads)
    # A and B are identical text → similarity 1.0 → both flagged high
    assert d["n_high"] >= 2
    assert d["max_observed"] >= 0.95
    # Top of the list is one of the duplicates
    assert d["ads"][0]["ad_id"] in ("A", "B")


def test_diversity_distinct_ads_score_low():
    from ads_agent.actions.diversity import diversity_report
    ads = [
        {"ad_id": "1", "ad_name": "before after dog joint mobility"},
        {"ad_id": "2", "ad_name": "vet testimonial digestive enzyme"},
        {"ad_id": "3", "ad_name": "free shipping limited offer banner"},
    ]
    d = diversity_report(ads)
    assert d["n_high"] == 0
    assert d["max_observed"] < 0.55


def test_diversity_handles_empty_input():
    from ads_agent.actions.diversity import diversity_report
    assert diversity_report([])["n_high"] == 0
    assert diversity_report([{"ad_id": "1", "ad_name": "single"}])["max_observed"] == 0.0


def test_parse_health_extracts_score_and_grade():
    from ads_agent.agent.analysis.meta_audit_analyst import _parse_health
    txt = (
        "## HEALTH SCORE\n"
        "Total: 64/100 (Grade: D)\n"
        "Pixel/CAPI: 35/100  bar\n"
        "Creative:   72/100  bar\n"
        "Structure:  85/100  bar\n"
        "Audience:   52/100  bar\n"
    )
    h = _parse_health(txt)
    assert h["total"] == 64
    assert h["grade"] == "D"
    assert h["pixel_capi"] == 35
    assert h["creative"] == 72
    assert h["structure"] == 85
    assert h["audience"] == 52


def test_parse_health_grade_letter_boundaries():
    from ads_agent.agent.analysis.meta_audit_analyst import _parse_health
    boundaries = [(95, "A"), (85, "B"), (75, "C"), (65, "D"), (40, "F")]
    for total, expected in boundaries:
        txt = (
            "## HEALTH SCORE\n"
            f"Total: {total}/100 (Grade: ?)\n"
            "Pixel/CAPI: 50/100\n"
            "Creative:   50/100\n"
            "Structure:  50/100\n"
            "Audience:   50/100\n"
        )
        h = _parse_health(txt)
        assert h["grade"] == expected, f"{total} → expected {expected}, got {h['grade']}"


def test_parse_report_quick_wins_sort():
    """severity DESC, effort ASC; quick_wins = critical/high × low effort."""
    from ads_agent.agent.analysis.meta_audit_analyst import _parse_report
    txt = (
        "## ACCOUNT SUMMARY\nblah\n"
        "### 1. PAUSE · big-spender low-roas\n"
        "- target_level: ad\n"
        "- target_id: aaa\n"
        "- check_id: M01\n"
        "- severity: medium\n"
        "- effort: low\n"
        "- rationale: x\n"
        "- expected_impact: y\n"
        "- safety_check: none\n"
        "### 2. PAUSE · pixel-broken\n"
        "- target_level: campaign\n"
        "- target_id: bbb\n"
        "- check_id: M01,M02\n"
        "- severity: critical\n"
        "- effort: low\n"
        "- rationale: y\n"
        "- expected_impact: z\n"
        "- safety_check: none\n"
        "### 3. REFRESH · fatigue case\n"
        "- target_level: ad\n"
        "- target_id: ccc\n"
        "- check_id: M12\n"
        "- severity: high\n"
        "- effort: high\n"
        "- rationale: y\n"
        "- expected_impact: z\n"
        "- safety_check: none\n"
    )
    r = _parse_report(txt)
    # Sorted: critical-low first, then medium-low (since high-high beats medium-low? no,
    # sort key is (severity, effort) so order is:
    #   critical-low → high-high → medium-low
    assert [a["target_id"] for a in r["actions"]] == ["bbb", "ccc", "aaa"]
    # Quick Wins = severity in critical/high AND effort low → only "bbb"
    assert [a["target_id"] for a in r["quick_wins"]] == ["bbb"]
    # check_id parsed
    assert r["actions"][0]["check_id"] == "M01,M02"


def test_parse_report_default_fields_when_missing():
    from ads_agent.agent.analysis.meta_audit_analyst import _parse_report
    txt = (
        "## ACCOUNT SUMMARY\nfoo\n"
        "### 1. PAUSE · ad with no metadata\n"
        "- target_level: ad\n"
        "- target_id: aaa\n"
        "- rationale: x\n"
        "- expected_impact: y\n"
        "- safety_check: none\n"
    )
    r = _parse_report(txt)
    assert len(r["actions"]) == 1
    a = r["actions"][0]
    assert a["check_id"] == ""              # absent → empty
    assert a["severity"] == "medium"        # absent → default
    assert a["effort"] == "medium"
    assert r["quick_wins"] == []            # not critical/high+low


def test_node_imports_and_compiles():
    from ads_agent.agent.graph import build_graph
    build_graph()


def test_emq_stub_returns_unmeasured_when_no_pixel():
    import asyncio
    from ads_agent.meta.emq import fetch_emq
    r = asyncio.get_event_loop().run_until_complete(fetch_emq(None))
    assert r.measured is False
    assert r.score is None
    assert r.grade == "unknown"
