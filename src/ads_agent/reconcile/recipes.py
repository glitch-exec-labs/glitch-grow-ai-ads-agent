"""Remediation recipes. Strings only — HITL via Telegram, no auto-apply in v1.

The agent picks which of these to surface based on metrics from `metrics.py`.
Recipes intentionally name the specific file/location to edit so the operator
can act without further investigation.
"""
from __future__ import annotations

RECIPES: dict[str, str] = {
    "low_utm_coverage": (
        "UTM coverage is low. Enable Meta auto-tagging on ad URLs; verify the storefront "
        "theme preserves query params through add-to-cart redirects (common loss: "
        "cart.js forms strip the URL)."
    ),
    "capi_gap_no_order_id": (
        "Meta is not receiving order_id on Purchase events. Edit /var/www/glitchexecutor/capi_server.py "
        "to include custom_data.order_id AND a shared event_id matching the client-side Pixel. "
        "Without this, reconciliation falls back to fuzzy matching (lower confidence)."
    ),
    "pixel_only_on_ios": (
        "iOS conversions show Pixel-only (no CAPI). Enable Shopify's native Meta channel "
        "Conversions API as a redundant server-side path; it coexists with our CAPI server "
        "as long as event_id dedup is configured on both."
    ),
    "no_dedup_event_id": (
        "Pixel and CAPI events are not sharing an event_id, so Meta is double-counting "
        "conversions. Emit a UUID from the checkout page, pass it to both the Pixel "
        "Purchase and CAPI Purchase payloads. See theme snippet sections/checkout-thankyou.liquid "
        "(or equivalent) for the client-side hook."
    ),
    "spend_up_revenue_flat": (
        "Spend has increased >20% week-over-week while Shopify revenue is flat. Likely paths: "
        "(a) tracking regression (run /tracking_audit), (b) refund spike (check Shopify admin > "
        "Orders > filter refunded), (c) audience saturation / creative fatigue on the top-spend ad set."
    ),
}
