"""Destination classification + ASIN parsing + Ayurpet-only methodology
fence. The engine-level helpers are brand-neutral; the M40/RECLAIM
methodology lives only in the Ayurpet playbook brief — verify it
doesn't leak into other brand briefs.
"""
from __future__ import annotations

import pytest


# ----- destinations module --------------------------------------------------

def test_classify_amazon_canonical():
    from ads_agent.meta.destinations import classify_destination
    assert classify_destination("https://www.amazon.ae/dp/B0FDKW4FD8") == "amazon"
    assert classify_destination("https://amazon.in/dp/B0G48Q6NZV") == "amazon"
    assert classify_destination("http://amazon.com/gp/product/B07XYZ") == "amazon"


def test_classify_amazon_shortlink():
    from ads_agent.meta.destinations import classify_destination
    assert classify_destination("https://amzn.eu/d/0g4CoI9t") == "amazon"
    assert classify_destination("https://amzn.to/abc123") == "amazon"


def test_classify_shopify_buckets():
    from ads_agent.meta.destinations import classify_destination
    assert classify_destination("https://theayurpet.store/products/x") == "shopify-global"
    assert classify_destination("https://theayurpet.com/products/x") == "shopify-ind"
    assert classify_destination("https://random-other-brand.myshopify.com/x") == "shopify-other"


def test_classify_other_and_unknown():
    from ads_agent.meta.destinations import classify_destination
    assert classify_destination("") == "unknown"
    assert classify_destination(None) == "unknown"
    assert classify_destination("https://landerly.io/p/12") == "other"


def test_parse_asin_canonical_paths():
    from ads_agent.meta.destinations import parse_asin
    assert parse_asin("https://amazon.ae/dp/B0FDKW4FD8") == "B0FDKW4FD8"
    assert parse_asin("https://amazon.in/dp/B0G48Q6NZV?ref=xyz") == "B0G48Q6NZV"
    assert parse_asin("https://amazon.com/gp/product/B07XYZQ123") == "B07XYZQ123"
    assert parse_asin("https://amazon.com/Some-Product/product/B0HHHHHHHH") == "B0HHHHHHHH"


def test_parse_asin_shortlink_returns_none():
    from ads_agent.meta.destinations import parse_asin
    assert parse_asin("https://amzn.eu/d/0g4CoI9t") is None


def test_parse_asin_invalid_inputs():
    from ads_agent.meta.destinations import parse_asin
    assert parse_asin("") is None
    assert parse_asin(None) is None
    assert parse_asin("https://example.com/dp/notanASIN") is None  # lowercase
    assert parse_asin("https://amazon.ae/dp/SHORT") is None         # <10 chars


def test_extract_destination_link_walks_all_shapes():
    from ads_agent.meta.destinations import extract_destination_link
    # video_data.call_to_action.value.link
    assert extract_destination_link({
        "object_story_spec": {"video_data": {
            "call_to_action": {"value": {"link": "https://a.com/dp/B0FDKW4FD8"}}
        }}
    }) == "https://a.com/dp/B0FDKW4FD8"
    # link_data.link
    assert extract_destination_link({
        "object_story_spec": {"link_data": {"link": "https://b.com/x"}}
    }) == "https://b.com/x"
    # object_url
    assert extract_destination_link({"object_url": "https://c.com/y"}) == "https://c.com/y"
    # asset_feed_spec.link_urls[0].website_url
    assert extract_destination_link({
        "asset_feed_spec": {"link_urls": [{"website_url": "https://d.com/z"}]}
    }) == "https://d.com/z"
    # Nothing → None
    assert extract_destination_link({}) is None
    assert extract_destination_link(None) is None


# ----- AdRow extension + decomposer fields ---------------------------------

def test_adrow_carries_destination_fields():
    from ads_agent.agent.analysis.meta_decomposer import AdRow
    a = AdRow(
        ad_id="1", ad_name="x", status="", effective_status="",
        spend=100, impressions=1000, clicks=10, ctr=1.0, cpc=10, cpm=100,
        frequency=1.0, reach=900, purchases=1, purchase_value=300, roas=3.0,
        days_live=14, destination="amazon", destination_url="https://amazon.ae/dp/B0FDKW4FD8",
        target_asin="B0FDKW4FD8",
    )
    assert a.destination == "amazon"
    assert a.target_asin == "B0FDKW4FD8"


def test_hierarchy_carries_amazon_halo_field():
    from ads_agent.agent.analysis.meta_decomposer import (
        AccountSummary, MetaAccountHierarchy, PreFlight,
    )
    h = MetaAccountHierarchy(
        summary=AccountSummary(
            ad_account_id="x", account_name="y", currency="INR",
            days=14, generated_at="2026-04-25", n_campaigns=0,
            n_adsets=0, n_ads=0, spend=0, impressions=0, clicks=0,
            purchases=0, purchase_value=0, blended_roas=0,
            blended_ctr=0, blended_cpc=0,
        ),
        pre_flight=PreFlight(
            attribution_window="7d_click", days_window=14,
            day_of_week_skew_risk=False, purchase_event_count_7d=0,
            purchase_event_value_sum_7d=0, purchase_event_currency_sane=True,
            pixel_hygiene_ok=True, asc_plus_campaign_count=0,
            manual_campaign_count=0,
        ),
    )
    assert h.amazon_halo == {}
    assert h.destination_mix == {}


# ----- Ayurpet-only methodology fence --------------------------------------

def test_ayurpet_brief_has_m40_and_reclaim():
    from ads_agent.playbook import node_brief
    brief = node_brief("meta_audit", "ayurpet")
    assert brief, "Ayurpet brief missing"
    for tok in ("M40", "RECLAIM", "amazon_halo", "destination = amazon",
                "target_asin_halo_roas"):
        assert tok in brief, f"ayurpet brief missing token {tok!r}"


def test_adrow_carries_halo_stamp_fields():
    """Halo stamp fields must default to 0.0/0 so non-Amazon ads don't
    accidentally inherit halo data."""
    from ads_agent.agent.analysis.meta_decomposer import AdRow
    a = AdRow(
        ad_id="1", ad_name="x", status="", effective_status="",
        spend=100, impressions=1000, clicks=10, ctr=1.0, cpc=10, cpm=100,
        frequency=1.0, reach=900, purchases=1, purchase_value=300, roas=3.0,
        days_live=14,
    )
    assert a.target_asin_halo_roas == 0.0
    assert a.target_asin_meta_orders == 0
    assert a.target_asin_meta_gross_inr == 0.0
    assert a.target_asin_meta_clicks == 0


def test_halo_stamping_picks_correct_asin_row():
    """Synthesise a hierarchy + halo, run the stamping logic, verify
    each Amazon-destined ad gets the row matching its target_asin."""
    from ads_agent.agent.analysis.meta_decomposer import AdRow

    # Two ads — one targets B0FDKW4FD8 (halo 6.78×), other B0G48Q6NZV (halo 0.0×).
    ads = [
        AdRow(ad_id="A", ad_name="a", status="", effective_status="",
              spend=100, impressions=1000, clicks=10, ctr=1, cpc=10, cpm=100,
              frequency=1, reach=900, purchases=0, purchase_value=0, roas=0,
              days_live=14, destination="amazon", target_asin="B0FDKW4FD8"),
        AdRow(ad_id="B", ad_name="b", status="", effective_status="",
              spend=200, impressions=2000, clicks=20, ctr=1, cpc=10, cpm=100,
              frequency=1, reach=1800, purchases=0, purchase_value=0, roas=0,
              days_live=14, destination="amazon", target_asin="B0G48Q6NZV"),
        # Shopify-destined: must NOT get halo stamp
        AdRow(ad_id="C", ad_name="c", status="", effective_status="",
              spend=300, impressions=3000, clicks=30, ctr=1, cpc=10, cpm=100,
              frequency=1, reach=2700, purchases=2, purchase_value=400, roas=1.33,
              days_live=14, destination="shopify-global", target_asin=""),
    ]

    halo = {
        "per_asin": [
            {"asin": "B0FDKW4FD8", "halo_roas": 6.78, "meta_orders": 21,
             "meta_gross_inr": 79972.0, "meta_clicks": 250},
            {"asin": "B0G48Q6NZV", "halo_roas": 0.0,  "meta_orders": 0,
             "meta_gross_inr": 0.0, "meta_clicks": 100},
        ]
    }

    # Inline the stamping logic from decompose_meta_account so we can unit-test
    # without hitting Postgres for the halo or Graph for the decompose.
    asin_halo = {row["asin"]: row for row in halo["per_asin"]}
    for a in ads:
        if a.destination != "amazon" or not a.target_asin:
            continue
        row = asin_halo.get(a.target_asin)
        if not row: continue
        a.target_asin_halo_roas      = float(row["halo_roas"])
        a.target_asin_meta_orders    = int(row["meta_orders"])
        a.target_asin_meta_gross_inr = float(row["meta_gross_inr"])
        a.target_asin_meta_clicks    = int(row["meta_clicks"])

    # A → B0FDKW4FD8 row stamped
    assert ads[0].target_asin_halo_roas == 6.78
    assert ads[0].target_asin_meta_orders == 21
    # B → B0G48Q6NZV row stamped (zero halo, but row exists)
    assert ads[1].target_asin_halo_roas == 0.0
    assert ads[1].target_asin_meta_orders == 0
    # C → Shopify, no stamp
    assert ads[2].target_asin_halo_roas == 0.0
    assert ads[2].target_asin_meta_orders == 0


def test_other_brand_briefs_do_not_have_m40_or_reclaim():
    """RECLAIM + M40 is Ayurpet-only tuning. Urban / Mokshya MUST NOT
    inherit it — they don't run Amazon halo."""
    from ads_agent.playbook import node_brief
    for brand in ("urban", "mokshya"):
        brief = node_brief("meta_audit", brand)
        assert brief, f"{brand} brief missing"
        assert "M40" not in brief, f"{brand} brief leaked M40"
        assert "RECLAIM" not in brief, f"{brand} brief leaked RECLAIM"
        assert "amazon_halo" not in brief, f"{brand} brief leaked amazon_halo"


def test_global_checklist_does_not_have_m40():
    """M40 is Ayurpet-tuned; the global checklist (M01-M35) must not
    advertise it as a generic check."""
    from ads_agent.playbook import load_ref
    chk = load_ref("meta-audit-checklist")
    assert chk, "global checklist missing"
    assert "M40" not in chk, "global checklist leaked M40 — that's Ayurpet-only"


# ----- Phase A: campaign-level halo stamping -------------------------------

def test_campaign_row_default_halo_fields():
    """Campaign halo fields default to 0/empty string for non-Amazon campaigns."""
    from ads_agent.agent.analysis.meta_decomposer import CampaignRow
    c = CampaignRow(
        campaign_id="x", name="x", status="", effective_status="",
        objective="", buying_type="", is_asc_plus=False,
        daily_budget=0, lifetime_budget=0, currency="INR",
        spend=0, impressions=0, clicks=0, ctr=0, cpc=0, cpm=0,
        frequency=0, reach=0, purchases=0, purchase_value=0, roas=0,
    )
    assert c.amazon_halo_blended == 0.0
    assert c.amazon_halo_summary == ""
    assert c.amazon_destined_spend_pct == 0.0


# ----- Phase B: halo-citation verifier -------------------------------------

def test_halo_citation_passes_when_quoted_correctly():
    from ads_agent.agent.analysis.meta_audit_analyst import _verify_halo_citations
    actions = [{
        "action_kind": "RECLAIM", "severity": "critical", "effort": "low",
        "rationale": "ASIN halo is 6.68 — well above breakeven of 1.6.",
    }]
    hierarchy = {"amazon_halo": {"per_asin": [
        {"asin": "B0FDKW4FD8", "halo_roas": 6.68},
    ]}}
    n = _verify_halo_citations(actions, hierarchy)
    assert n == 0
    assert actions[0]["severity"] == "critical"  # not downgraded


def test_halo_citation_downgrades_when_fabricated():
    from ads_agent.agent.analysis.meta_audit_analyst import _verify_halo_citations
    actions = [{
        "action_kind": "RECLAIM", "severity": "critical", "effort": "low",
        "rationale": "Halo ROAS for this ASIN is 5.98×, well above breakeven.",
    }]
    hierarchy = {"amazon_halo": {"per_asin": [
        {"asin": "B0G48Q6NZV", "halo_roas": 0.0},
    ]}}
    n = _verify_halo_citations(actions, hierarchy)
    assert n == 1
    assert actions[0]["severity"] == "low"
    assert actions[0]["_original_severity"] == "critical"
    assert "[HALO_UNVERIFIED" in actions[0]["rationale"]


def test_halo_citation_passes_when_no_halo_word():
    """Don't trigger on numbers that aren't halo claims."""
    from ads_agent.agent.analysis.meta_audit_analyst import _verify_halo_citations
    actions = [{
        "action_kind": "PAUSE", "severity": "high", "effort": "low",
        "rationale": "ROAS 0.75 is below breakeven 1.6 — pure bleed.",
    }]
    hierarchy = {"amazon_halo": {"per_asin": [{"asin": "X", "halo_roas": 9.0}]}}
    n = _verify_halo_citations(actions, hierarchy)
    assert n == 0


def test_halo_citation_tolerance_allows_rounding():
    """Within 0.10 of a supplied number is fine — analyst rounding-error
    shouldn't blow up the action."""
    from ads_agent.agent.analysis.meta_audit_analyst import _verify_halo_citations
    actions = [{
        "action_kind": "SCALE", "severity": "high", "effort": "low",
        "rationale": "Halo of 6.7× makes this a clear scale.",
    }]
    hierarchy = {"amazon_halo": {"per_asin": [{"asin": "X", "halo_roas": 6.68}]}}
    n = _verify_halo_citations(actions, hierarchy)
    assert n == 0


def test_halo_citation_accepts_campaign_blended_value():
    """The campaign.amazon_halo_blended is also a valid number to cite."""
    from ads_agent.agent.analysis.meta_audit_analyst import _verify_halo_citations
    actions = [{
        "action_kind": "SCALE", "severity": "critical", "effort": "low",
        "rationale": "Weighted blended halo for the campaign is 4.68× — scale.",
    }]
    hierarchy = {
        "amazon_halo": {"per_asin": []},
        "campaigns": [{"amazon_halo_blended": 4.68}],
    }
    n = _verify_halo_citations(actions, hierarchy)
    assert n == 0
