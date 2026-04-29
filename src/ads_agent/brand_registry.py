"""Per-store brand metadata — env-driven, single source of truth.

The engine code is brand-neutral. Anything that previously branched on
slug prefixes, hardcoded shop-host strings, or per-slug currency /
marketplace fallbacks now resolves through this registry.

Operators populate `STORE_BRAND_REGISTRY_JSON` in `.env`:

    STORE_BRAND_REGISTRY_JSON={
      "store-a": {
        "brand_key":          "lighthouse",
        "primary_market":     "IN",
        "shop_host":          "yourdomain.com",
        "amazon_marketplace": "amazon.in",
        "currency":           "INR"
      },
      "store-b": {
        "brand_key":          "lighthouse",
        "primary_market":     "AE",
        "shop_host":          "yourdomain.store",
        "amazon_marketplace": "amazon.ae",
        "currency":           "AED"
      }
    }

`brand_key` is the playbook lookup key (the engine loads
`playbooks/<brand_key>.md` from the private playbook repo).
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class BrandEntry:
    slug: str
    brand_key: str
    primary_market: str
    shop_host: str
    amazon_marketplace: str
    currency: str

    @property
    def amazon_country(self) -> str:
        """ISO-2 country code derived from amazon_marketplace ('amazon.in'→'IN')."""
        suffix = self.amazon_marketplace.rsplit(".", 1)[-1].upper()
        return {"COM": "US", "AE": "AE", "IN": "IN", "UK": "GB", "DE": "DE",
                "FR": "FR", "IT": "IT", "ES": "ES", "CA": "CA"}.get(suffix, suffix)


# Module-level cache; reset_registry() for tests.
_REGISTRY: dict[str, BrandEntry] | None = None


def _load() -> dict[str, BrandEntry]:
    global _REGISTRY
    if _REGISTRY is not None:
        return _REGISTRY
    raw = os.environ.get("STORE_BRAND_REGISTRY_JSON", "").strip()
    if not raw:
        log.warning("STORE_BRAND_REGISTRY_JSON not set — brand-aware nodes "
                    "will fall back to defaults.")
        _REGISTRY = {}
        return _REGISTRY
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        log.error("STORE_BRAND_REGISTRY_JSON invalid: %s", e)
        _REGISTRY = {}
        return _REGISTRY
    out: dict[str, BrandEntry] = {}
    for slug, val in (parsed or {}).items():
        if not isinstance(val, dict):
            continue
        out[slug] = BrandEntry(
            slug=slug,
            brand_key=str(val.get("brand_key", "default")),
            primary_market=str(val.get("primary_market", "")).upper(),
            shop_host=str(val.get("shop_host", "")).lower(),
            amazon_marketplace=str(val.get("amazon_marketplace", "")).lower(),
            currency=str(val.get("currency", "USD")).upper(),
        )
    _REGISTRY = out
    return out


def reset_registry() -> None:
    """For tests + after env reload."""
    global _REGISTRY
    _REGISTRY = None


def entry_for(slug: str) -> BrandEntry | None:
    return _load().get(slug)


def brand_for(slug: str) -> str:
    """Playbook lookup key. Falls back to 'default' if unmapped."""
    e = entry_for(slug)
    return e.brand_key if e else "default"


def shop_host_for(slug: str) -> str:
    e = entry_for(slug)
    return e.shop_host if e else ""


def amazon_marketplace_for(slug: str) -> str:
    """e.g. 'amazon.in', 'amazon.ae', 'amazon.com'. Empty if not mapped."""
    e = entry_for(slug)
    return e.amazon_marketplace if e else ""


def currency_for(slug: str, default: str = "USD") -> str:
    e = entry_for(slug)
    return e.currency if e else default


def primary_market_for(slug: str, default: str = "") -> str:
    e = entry_for(slug)
    return e.primary_market if e else default


def all_slugs() -> list[str]:
    return list(_load().keys())


def slugs_with_brand(brand_key: str) -> list[str]:
    return [s for s, e in _load().items() if e.brand_key == brand_key]


def host_to_slug() -> dict[str, str]:
    """Reverse map: shop_host → slug. Used by URL classifiers."""
    return {e.shop_host: s for s, e in _load().items() if e.shop_host}
