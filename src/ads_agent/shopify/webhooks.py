"""Shopify webhook receiver (v1+).

For each shop, HMAC is verified with that shop's Custom App client secret
(from settings().shopify_webhook_secret_map, keyed by custom_app slug —
NOT by shop domain, because one Custom App can install across multiple stores).

This module is a stub in v0; wire to FastAPI in v1.
"""
from __future__ import annotations

import base64
import hashlib
import hmac

from ads_agent.config import get_store, settings


class HmacVerificationError(RuntimeError):
    pass


def verify_hmac(*, shop_domain: str, raw_body: bytes, header_hmac_b64: str) -> None:
    """Raise HmacVerificationError on mismatch. Returns None on success."""
    store = get_store(shop_domain)
    if store is None:
        raise HmacVerificationError(f"unknown shop: {shop_domain}")

    secret = settings().shopify_webhook_secret_map.get(store.custom_app)
    if not secret:
        raise HmacVerificationError(f"no webhook secret configured for app {store.custom_app}")

    mac = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256)
    expected = base64.b64encode(mac.digest()).decode("utf-8")
    if not hmac.compare_digest(expected, header_hmac_b64):
        raise HmacVerificationError("hmac mismatch")
