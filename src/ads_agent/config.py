"""Central configuration for the Glitch Grow Ads Agent.

Single source of truth for:
  - Store registry (shop domain -> custom app slug + Meta ad account)
  - Required Shopify scope matrix per Custom App
  - Env-derived runtime settings (DB, Meta, PostHog, Telegram, LLM)

STORES below is a TEMPLATE with example values. In your deployment:
  1. Replace every shop_domain, meta_ad_account, and slug with your real values.
  2. Alternatively, load STORES from an env-var JSON blob so nothing is hard-coded.
  3. Never commit real myshopify domains or Meta act_... IDs to a public repo.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


@dataclass(frozen=True)
class Store:
    """One Shopify storefront in the Glitch Grow fleet."""

    slug: str  # short handle used in Telegram commands (e.g. "urban")
    brand: str  # human-facing brand name
    shop_domain: str  # *.myshopify.com
    custom_app: str  # matches *_CLIENT_ID prefix in multi-store-theme-manager/.env
    meta_ad_account: str | None  # act_... or None if not linked
    currency: str
    notes: str = ""


# Live store registry — server-only, never committed to public repo.
# Grouped by client family (Urban CAD / Ayurpet INR / Mokshya standalone).
STORES: tuple[Store, ...] = (
    # --- Urban family (CAD) ---
    Store(
        slug="urban",
        brand="Urban Classics",
        shop_domain="f51039.myshopify.com",
        custom_app="urban",
        meta_ad_account="act_1765937727381511",
        currency="CAD",
    ),
    Store(
        slug="storico",
        brand="Storico",
        shop_domain="ys4n0u-ys.myshopify.com",
        custom_app="storico",
        meta_ad_account=None,
        currency="CAD",
        notes="Creds issued 2026-04-16. Pending merchant install.",
    ),
    Store(
        slug="classicoo",
        brand="Classicoo",
        shop_domain="52j1ga-hz.myshopify.com",
        custom_app="classicoo",
        meta_ad_account="act_1231977889107681",
        currency="CAD",
        notes="Scope bump pending (needs merchant re-consent for read/write_orders).",
    ),
    Store(
        slug="trendsetters",
        brand="Trendsetters",
        shop_domain="acmsuy-g0.myshopify.com",
        custom_app="trendsetters",
        meta_ad_account=None,
        currency="CAD",
        notes="Creds issued 2026-04-16. Pending merchant install.",
    ),
    # --- Ayurpet family (INR, one ad account across both storefronts) ---
    Store(
        slug="ayurpet-ind",
        brand="Ayurpet (India)",
        shop_domain="1ygbmd-pr.myshopify.com",
        custom_app="ayurpet-ind",
        meta_ad_account="act_654879327196107",
        currency="INR",
        notes="India-market. Shares ad account with Ayurpet Global.",
    ),
    Store(
        slug="ayurpet-global",
        brand="Ayurpet (Global)",
        shop_domain="2684sq-mt.myshopify.com",
        custom_app="ayurpet",
        meta_ad_account="act_654879327196107",
        currency="INR",
        notes="Global storefront. Same ad account as India; reconcile ROAS across both.",
    ),
    # --- Mokshya (standalone) ---
    # NOTE: placeholder entry — update shop_domain and custom_app once credentials issued.
)


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
