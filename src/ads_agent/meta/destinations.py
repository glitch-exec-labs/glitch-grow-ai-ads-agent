"""Classify Meta-ad destination URLs.

Engine-level helper that's brand-neutral: every ad gets tagged
`amazon | shopify-ind | shopify-global | shopify-other | other`
plus an `ASIN` when the destination is an Amazon PDP. This lives in the
engine because the *data* is brand-agnostic; the *methodology* (whether
to use the halo number or pause on Meta-ROAS) lives per-brand in
`playbooks/<brand>.md` Section X.

Why we do this:
  - Meta has no visibility into Amazon orders, so any Amazon-destined ad
    structurally reads `omni_purchase = 0` in the Graph API insights —
    Meta-reported ROAS on those ads is a floor, not the truth.
  - A brand-tuned audit (e.g. Ayurpet's) needs to identify Amazon ads
    and use the cross-channel halo number from
    `ads_agent.amazon_attribution_daily_v` instead of Meta-ROAS, then
    propose `RECLAIM` rather than `PAUSE`.
  - Other brands without an `amazon` destination just see all ads tagged
    `shopify-*` and the existing methodology runs unchanged.

We do NOT follow `amzn.eu/d/<short>` redirects here — the resolver lives
inside `agent/analysis/meta_decomposer.py` so the network round-trip
stays in one place.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

# Compiled once. Matches /dp/ASIN, /gp/product/ASIN, /product/ASIN paths.
_ASIN_RE = re.compile(r"/(?:dp|gp/product|product)/([A-Z0-9]{10})(?:[/?]|$)")


def classify_destination(url: str | None) -> str:
    """Bucket a Meta destination URL into a stable label.

    Returns one of: amazon | shopify-ind | shopify-global | shopify-other |
    other | unknown
    """
    if not url:
        return "unknown"
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return "unknown"
    if "amazon." in host or host.endswith("amzn.eu") or host.endswith("amzn.to"):
        return "amazon"
    if "theayurpet.com" in host:
        return "shopify-ind"
    if "theayurpet.store" in host:
        return "shopify-global"
    if "myshopify.com" in host:
        return "shopify-other"
    return "other"


def parse_asin(url: str | None) -> str | None:
    """Extract a 10-character ASIN from an Amazon URL, if present.

    Handles the canonical /dp/{ASIN}, /gp/product/{ASIN}, /product/{ASIN}
    paths. Returns None for amzn.eu/d/<short> short links — those need a
    one-shot redirect resolution upstream.
    """
    if not url:
        return None
    m = _ASIN_RE.search(url)
    return m.group(1) if m else None


def extract_destination_link(creative: dict | None) -> str | None:
    """Walk the four Meta object_story_spec shapes that carry the
    landing-page URL. Returns None if the creative omits all of them
    (rare — usually means the ad is using an inactive deep-link).
    """
    if not creative:
        return None
    os_spec = creative.get("object_story_spec") or {}
    # 1) video_data.call_to_action.value.link
    vd = os_spec.get("video_data") or {}
    cta = (vd.get("call_to_action") or {}).get("value") or {}
    if cta.get("link"):
        return cta["link"]
    # 2) link_data.link (image/link ads)
    ld = os_spec.get("link_data") or {}
    if ld.get("link"):
        return ld["link"]
    # 3) object_url (legacy)
    if creative.get("object_url"):
        return creative["object_url"]
    # 4) asset_feed_spec.link_urls (Dynamic Creative Optimization)
    afs = creative.get("asset_feed_spec") or {}
    link_urls = afs.get("link_urls") or []
    if link_urls and isinstance(link_urls, list):
        first = link_urls[0]
        if isinstance(first, dict) and first.get("website_url"):
            return first["website_url"]
    return None
