"""Remediation recipes. Strings only — HITL via Telegram, no auto-apply in v1.

The agent picks which of these to surface based on metrics from `metrics.py`.
Recipes intentionally name the specific file/admin-panel location to edit so
the operator can act without further investigation.

**3rd-party checkout note:** Urban family stores use Shiprocket (Classicoo,
Storico) or Flexipe (Urban Classics, Trendsetters) as external checkout
providers. Meta Pixel + CAPI fire from THOSE admin panels, NOT from Shopify
theme or a Shopify-adjacent CAPI server. Several recipes below reflect that.
"""
from __future__ import annotations

RECIPES: dict[str, str] = {
    "low_utm_coverage": (
        "UTM coverage is low. Enable Meta auto-tagging (\"URL parameters\" in Ads Manager → Ad level). "
        "Also verify the 3rd-party checkout (Shiprocket / Flexipe) preserves query params when "
        "redirecting customers from Shopify → 3rd-party → thank-you. If the 3rd-party strips UTMs "
        "on handoff, the Purchase event they fire can't attribute back to the ad."
    ),
    "capi_gap_no_order_id": (
        "Meta is not receiving Shopify `order_id` on Purchase events. In the 3rd-party checkout "
        "admin (Shiprocket or Flexipe) → Meta/Facebook integration → enable \"Send order ID in "
        "custom_data\". If the 3rd-party doesn't expose this, ask them to add `custom_data.order_id` "
        "to their CAPI payload so reconciliation against Shopify orders becomes exact, not fuzzy."
    ),
    "pixel_not_firing": (
        "Meta reports 0 Purchase events but Shopify has real orders (e.g. Classicoo: 0 Meta "
        "purchases vs 11 pending Shopify orders last 14d). Root cause is usually one of: "
        "(1) 3rd-party checkout's Meta integration not enabled — turn on Pixel + CAPI in "
        "Shiprocket / Flexipe admin, paste your Pixel ID and Meta Access Token; "
        "(2) Pixel base code missing from Shopify theme (needed for ViewContent / AddToCart). "
        "Diff the theme.liquid of the broken store against a working sibling store to find the gap."
    ),
    "no_dedup_event_id": (
        "Browser Pixel and server CAPI are both firing Purchase but Meta isn't deduplicating — "
        "that's why Meta-reported purchases run 10–20× higher than Shopify-confirmed orders. "
        "In the 3rd-party checkout admin (Shiprocket / Flexipe), enable `event_id` generation "
        "and verify BOTH the browser Pixel call AND the server CAPI call emit the SAME "
        "event_id per order. Meta dedups within a 48h window on matching event_id + event_name."
    ),
    "third_party_pixel_mismatch": (
        "Checkout is on a 3rd-party domain (Shiprocket / Flexipe), so the Meta Pixel configured "
        "in your Shopify theme NEVER fires Purchase — only ViewContent / AddToCart. All Purchase "
        "events come from the 3rd-party's server-side CAPI. Audit the 3rd-party's Meta integration "
        "to ensure it's attached to the RIGHT Pixel (matching the one on your Shopify theme) — "
        "a mismatch here produces Pixel-only ViewContent data and CAPI-only Purchase data, both "
        "orphaned from each other in Meta's attribution model."
    ),
    "spend_up_revenue_flat": (
        "Spend has increased >20% week-over-week while Shopify revenue is flat (in the same currency). "
        "Likely paths: (a) tracking regression (Pixel/CAPI event drop from 3rd-party), "
        "(b) COD accept-rate drop (check `glitch-cod-confirm` health), (c) audience saturation / "
        "creative fatigue on the top-spend ad set (run /ads <store> and check frequency)."
    ),
    "delivery_status_not_updating": (
        "Shopify orders stay `financial_status=pending` indefinitely — the delivery-partner → "
        "Shopify status sync is broken. COD orders never promote to `paid` even after cash is "
        "collected on delivery. Agent treats pipeline (paid+pending) as the truth until this is "
        "fixed. Follow-up with Shiprocket / Flexipe / courier to restore the delivered-and-paid "
        "status webhook back to Shopify."
    ),
}
