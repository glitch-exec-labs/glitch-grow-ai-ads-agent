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
    for tok in ("M40", "RECLAIM", "amazon_halo", "destination = amazon"):
        assert tok in brief, f"ayurpet brief missing token {tok!r}"


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
