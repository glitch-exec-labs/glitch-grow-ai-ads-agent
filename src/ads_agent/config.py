"""Central configuration for the Glitch Grow Ads Agent.

Single source of truth for:
  - Store registry (shop domain -> custom app slug + Meta ad account)
  - Meta ad-account multimap (one store may spend through several Meta accounts)
  - Required Shopify scope matrix per Custom App
  - Env-derived runtime settings (DB, Meta, PostHog, Telegram, LLM)

**Real store data loads from env vars at runtime** — the committed file carries
only an illustrative placeholder so the repo can serve as a public showcase
without leaking client myshopify domains or Meta act_... IDs.

Point STORES_JSON and STORE_AD_ACCOUNTS_JSON in .env at the real data.
See .env.example for the exact shape.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Store:
    """One Shopify storefront in the Glitch Grow fleet."""

    slug: str  # short handle used in Telegram commands (e.g. "urban")
    brand: str  # human-facing brand name
    shop_domain: str  # *.myshopify.com
    custom_app: str  # matches *_CLIENT_ID prefix in multi-store-theme-manager/.env
    meta_ad_account: str | None  # act_... primary; all linked accounts live in STORE_AD_ACCOUNTS
    currency: str
    notes: str = ""


# Placeholder registry (public showcase). The real registry loads from
# STORES_JSON in .env at runtime — see _load_stores() below.
_PLACEHOLDER_STORES: tuple[Store, ...] = (
    Store(
        slug="store-a",
        brand="Store A (Example)",
        shop_domain="your-store-a.myshopify.com",
        custom_app="store-a",
        meta_ad_account="act_REPLACE_WITH_YOUR_ACCOUNT_ID",
        currency="USD",
        notes="Placeholder — replace via STORES_JSON env var.",
    ),
    Store(
        slug="store-b-india",
        brand="Store B (India)",
        shop_domain="your-store-b.myshopify.com",
        custom_app="store-b-ind",
        meta_ad_account="act_REPLACE_WITH_YOUR_ACCOUNT_ID",
        currency="INR",
        notes="Example of a shared-ad-account sibling.",
    ),
    Store(
        slug="store-b-global",
        brand="Store B (Global)",
        shop_domain="your-store-b-global.myshopify.com",
        custom_app="store-b",
        meta_ad_account="act_REPLACE_WITH_YOUR_ACCOUNT_ID",
        currency="INR",
        notes="Shares ad account with Store B India; reconcile ROAS across both.",
    ),
)


def _load_stores() -> tuple[Store, ...]:
    """Load STORES from STORES_JSON env var; fall back to placeholders."""
    raw = os.environ.get("STORES_JSON", "").strip()
    if not raw:
        return _PLACEHOLDER_STORES
    try:
        entries = json.loads(raw)
        return tuple(
            Store(
                slug=e["slug"],
                brand=e.get("brand", e["slug"]),
                shop_domain=e["shop_domain"],
                custom_app=e["custom_app"],
                meta_ad_account=e.get("meta_ad_account"),
                currency=e.get("currency", "USD"),
                notes=e.get("notes", ""),
            )
            for e in entries
        )
    except (json.JSONDecodeError, KeyError) as ex:
        log.warning("STORES_JSON invalid, using placeholders: %s", ex)
        return _PLACEHOLDER_STORES


STORES: tuple[Store, ...] = _load_stores()


def _load_store_ad_accounts() -> dict[str, list[str]]:
    """Map store_slug -> list of Meta ad account IDs to sum spend across.

    Loads from STORE_AD_ACCOUNTS_JSON env var (JSON object). Empty map if unset;
    roas_compute will then reply "no Meta accounts mapped for <slug>" gracefully.
    """
    raw = os.environ.get("STORE_AD_ACCOUNTS_JSON", "").strip()
    if not raw:
        return {}
    try:
        return {k: list(v) for k, v in json.loads(raw).items()}
    except (json.JSONDecodeError, TypeError, ValueError) as ex:
        log.warning("STORE_AD_ACCOUNTS_JSON invalid, returning empty map: %s", ex)
        return {}


STORE_AD_ACCOUNTS: dict[str, list[str]] = _load_store_ad_accounts()


# Scopes we need above the existing write_orders baseline to do analytics reads.
# Apply these by bumping *_SCOPES csv in /home/support/multi-store-theme-manager/.env
# then forcing merchant re-auth.
REQUIRED_ANALYTICS_SCOPES: tuple[str, ...] = (
    "read_orders",
    "read_customers",
    "read_products",
    "read_analytics",  # Plus-only; agent should gracefully degrade if denied
    "read_reports",
)


def get_store(slug_or_domain: str) -> Store | None:
    """Resolve by slug or shop_domain. Case-insensitive on slug."""
    s = slug_or_domain.strip().lower()
    for store in STORES:
        if store.slug.lower() == s or store.shop_domain.lower() == s:
            return store
    return None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Postgres (auth-hub Session table, read-only role)
    postgres_insights_ro_url: str = "postgresql://insights_ro:changeme@127.0.0.1:5432/your_db_name"

    # Shopify per-app webhook HMAC secrets — JSON map { custom_app_slug: secret }
    shopify_webhook_secrets: str = "{}"

    # Meta Ads MCP (local, streamable-http) + direct SDK
    meta_ads_mcp_url: str = "http://127.0.0.1:3103"
    meta_access_token: str = ""
    meta_app_id: str = ""
    meta_app_secret: str = ""

    # PostHog Cloud
    posthog_api_key: str = ""
    posthog_host: str = "https://us.i.posthog.com"

    # Telegram
    telegram_bot_token_ads: str = ""
    telegram_admin_ids: str = ""  # csv of int ids

    # LLMs (LiteLLM routes to these)
    anthropic_api_key: str = ""
    google_api_key: str = ""
    openai_api_key: str = ""
    vertex_project: str = ""
    vertex_location: str = "us-central1"

    # Runtime
    public_base_url: str = "https://ads.yourdomain.com"
    log_level: str = "INFO"

    @property
    def shopify_webhook_secret_map(self) -> dict[str, str]:
        try:
            return json.loads(self.shopify_webhook_secrets or "{}")
        except json.JSONDecodeError:
            return {}

    @property
    def admin_telegram_ids(self) -> set[int]:
        out: set[int] = set()
        for raw in (self.telegram_admin_ids or "").split(","):
            raw = raw.strip()
            if raw.isdigit():
                out.add(int(raw))
        return out


@lru_cache
def settings() -> Settings:
    return Settings()
