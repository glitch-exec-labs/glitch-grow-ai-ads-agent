"""Regression tests for issue #5 — guest-order distinct_id fallback.

Null customer.id must not leak as the literal string "None" into PostHog.
"""
from __future__ import annotations

from ads_agent.shopify.webhooks import _extract_order


def test_null_customer_id_falls_back_to_email():
    payload = {
        "id": 987654321,
        "name": "#GUEST-1",
        "current_total_price": "499.00",
        "currency": "INR",
        "customer": {"id": None, "email": "guest1@example.com"},
        "email": "guest1@example.com",
        "line_items": [],
    }
    out = _extract_order(payload)
    assert out["customer_id"] == "guest1@example.com"
    # Critical: the literal string "None" must never appear.
    assert out["customer_id"] != "None"


def test_null_customer_id_and_email_falls_back_to_order_id():
    payload = {
        "id": 123456789,
        "name": "#GUEST-2",
        "current_total_price": "200.00",
        "currency": "INR",
        "customer": {"id": None, "email": None},
        "email": None,
        "line_items": [],
    }
    out = _extract_order(payload)
    assert out["customer_id"] == "123456789"
    assert out["customer_id"] != "None"


def test_present_customer_id_is_used():
    payload = {
        "id": 123,
        "name": "#A-1",
        "current_total_price": "10.00",
        "currency": "USD",
        "customer": {"id": 42, "email": "real@example.com"},
        "email": "real@example.com",
        "line_items": [],
    }
    out = _extract_order(payload)
    assert out["customer_id"] == "42"


def test_posthog_capture_rejects_none_string_customer_id():
    """If an upstream caller slips `customer_id="None"` into the order dict,
    the PostHog wrapper must still resolve a meaningful distinct_id instead
    of collapsing all such orders together."""
    from ads_agent.posthog import client as ph

    captured: dict = {}

    class _Fake:
        disabled = False

        def capture(self, **kw):
            captured.update(kw)

    # Monkey-patch the module-level client factory.
    ph.client.cache_clear()  # type: ignore[attr-defined]
    ph.client = lambda: _Fake()  # type: ignore[assignment]

    ph.capture_order_event(
        "order_paid",
        shop_domain="x.myshopify.com",
        store_slug="x",
        order={
            "customer_id": "None",
            "order_id": "ORDER-999",
            "email": "",
            "order_name": "#X-1",
            "value": 10.0,
            "currency": "USD",
            "financial_status": "paid",
            "fulfillment_status": "",
            "source_name": "",
            "tags": "",
            "utm": {},
            "line_items": [],
        },
    )
    assert captured["distinct_id"] == "ORDER-999"
    assert captured["distinct_id"] != "None"
