"""PostHog Cloud client wrapper.

Using the managed free tier (1M events/mo) for the full event/attribution/CAPI
layer — see plan Risk #1 and #9. Self-host path stays open if we outgrow it.

PostHog Python SDK is fire-and-forget for ingest; queries go via the HTTP API.
"""
from __future__ import annotations

from functools import lru_cache

import posthog as _posthog

from ads_agent.config import settings


@lru_cache
def client() -> _posthog.Posthog:
    s = settings()
    return _posthog.Posthog(
        project_api_key=s.posthog_api_key,
        host=s.posthog_host,
    )


def capture_order_completed(
    *,
    distinct_id: str,
    shop_domain: str,
    order_id: str,
    value: float,
    currency: str,
    utm: dict | None = None,
) -> None:
    """Fire-and-forget `order_completed` event. Feeds PostHog's Meta CAPI destination.

    distinct_id: prefer customer_id; fall back to anon_id from PostHog cookie if
    we ever cross-wire the storefront pixel. For webhook-only v1, customer_id.
    """
    props = {
        "shop": shop_domain,
        "order_id": order_id,
        "value": value,
        "currency": currency,
    }
    if utm:
        props.update({f"utm_{k}": v for k, v in utm.items() if v})
    client().capture(
        distinct_id=distinct_id,
        event="order_completed",
        properties=props,
    )
