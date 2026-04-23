"""tiktok_insights: TikTok advertiser snapshot + paid media totals."""
from __future__ import annotations

from ads_agent.config import STORE_TIKTOK_ACCOUNTS, get_store, settings
from ads_agent.tiktok.client import TikTokError, advertiser_info, advertiser_spend
from ads_agent.tiktok.oauth import resolve_access_token


async def tiktok_insights_node(state: dict) -> dict:
    slug = state["store_slug"]
    days = int(state.get("days", 7))
    store = get_store(slug)
    if store is None:
        return {**state, "reply_text": f"Unknown store: `{slug}`. Try /stores."}

    cfg = STORE_TIKTOK_ACCOUNTS.get(slug)
    if not cfg:
        return {
            **state,
            "reply_text": (
                f"*{store.brand}* · TikTok\n\n"
                f"No TikTok advertiser is mapped for `{slug}`.\n"
                "Set `STORE_TIKTOK_ACCOUNTS_JSON` with an `advertiser_id` for this store."
            ),
        }

    advertiser_id = cfg["advertiser_id"]
    oauth_token = await resolve_access_token(slug)
    auth_source = "oauth" if oauth_token else "env"
    try:
        info = await advertiser_info(advertiser_id, access_token=oauth_token)
        metrics = await advertiser_spend(advertiser_id, days=days, access_token=oauth_token)
    except TikTokError as exc:
        return {
            **state,
            "reply_text": (
                f"*{store.brand}* · TikTok\n\n"
                f"Could not query TikTok yet: {exc}\n"
                "Required now: either complete TikTok OAuth via "
                f"`/api/tiktok/consent-url?account_ref={slug}` or set "
                "`TIKTOK_ACCESS_TOKEN` manually."
            ),
        }

    name = info.get("name") or f"Advertiser {advertiser_id}"
    currency = info.get("currency") or store.currency
    status = info.get("status") or "unknown"
    country = cfg.get("country") or "n/a"
    env_label = settings().tiktok_env.strip() or "sandbox"

    lines = [
        f"*{store.brand}* · TikTok (last {days}d)",
        "",
        f"Advertiser: `{name}` · ID `{advertiser_id}`",
        f"Status: `{status}` · Country: `{country}` · Env: `{env_label}` · Auth: `{auth_source}`",
        (
            f"Spend: {metrics['spend']:,.2f} {currency} · "
            f"Impressions: {metrics['impressions']:,} · Clicks: {metrics['clicks']:,}"
        ),
        f"CTR: {metrics['ctr']:.2f}% · CPC: {metrics['cpc']:.2f} {currency}",
        (
            f"_Source: TikTok Business API via "
            f"`glitch-exec-labs/tiktok-business-api-sdk` · "
            f"{metrics['start_date']} → {metrics['end_date']}_"
        ),
    ]
    return {
        **state,
        "reply_text": "\n".join(lines),
        "orders_summary": {
            "channel": "tiktok",
            "advertiser_id": advertiser_id,
            "spend": metrics["spend"],
            "impressions": metrics["impressions"],
            "clicks": metrics["clicks"],
            "ctr": metrics["ctr"],
            "cpc": metrics["cpc"],
            "currency": currency,
            "auth_source": auth_source,
        },
    }
