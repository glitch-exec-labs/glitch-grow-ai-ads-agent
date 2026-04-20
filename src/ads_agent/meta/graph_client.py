"""Direct Meta Marketing API (Graph API) client.

Uses META_ACCESS_TOKEN directly. Cleaner + faster for our read-heavy workload
than going through MCP protocol wrapping.

Scope: just the 3-4 endpoints the agent actually needs:
  - /{act_id}/insights        — spend + impressions + clicks + conversions per date range
  - /{act_id}                 — account metadata (name, currency, status)
"""
from __future__ import annotations

import httpx

from ads_agent.config import settings

GRAPH_BASE = "https://graph.facebook.com/v21.0"


class MetaGraphError(RuntimeError):
    pass


async def _get(path: str, params: dict) -> dict:
    token = settings().meta_access_token
    if not token:
        raise MetaGraphError("META_ACCESS_TOKEN not set")
    params = {**params, "access_token": token}
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(f"{GRAPH_BASE}/{path}", params=params)
    body = r.json()
    if r.status_code != 200 or body.get("error"):
        raise MetaGraphError(f"meta {path}: {body.get('error') or r.text[:300]}")
    return body


async def account_spend(ad_account_id: str, days: int = 7) -> dict:
    """Return {spend, impressions, clicks, purchases, purchase_value, currency}
    for the past N days (inclusive of today)."""
    params = {
        "level": "account",
        "fields": "spend,impressions,clicks,actions,action_values,account_currency",
        "date_preset": f"last_{days}_d" if days in (7, 14, 28, 30, 90) else None,
    }
    # For arbitrary windows, use time_range instead of date_preset
    if params["date_preset"] is None:
        from datetime import datetime, timedelta, timezone
        end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        params.pop("date_preset")
        params["time_range"] = f'{{"since":"{start}","until":"{end}"}}'
    else:
        # Canonical preset names: last_7d, last_14d, last_28d, last_30d, last_90d
        params["date_preset"] = f"last_{days}d"

    body = await _get(f"{ad_account_id}/insights", params)
    rows = body.get("data", [])
    if not rows:
        return {"spend": 0.0, "impressions": 0, "clicks": 0, "purchases": 0, "purchase_value": 0.0, "currency": "?"}
    row = rows[0]

    # Use omni_purchase ONLY — Meta's canonical dedup action type (matches
    # Ads Manager's "Purchase ROAS" column). The other aliases (purchase,
    # fb_pixel_purchase, onsite_web_*_purchase) represent the same events
    # viewed through different attribution lenses; summing them 3-5× inflates
    # the ROAS number. See PURCHASE_ACTION_TYPES above for full rationale.
    purchases = 0
    purchase_value = 0.0
    for a in row.get("actions", []) or []:
        if a.get("action_type") == "omni_purchase":
            purchases += int(a.get("value", 0) or 0)
    for av in row.get("action_values", []) or []:
        if av.get("action_type") == "omni_purchase":
            purchase_value += float(av.get("value", 0) or 0)

    return {
        "spend": float(row.get("spend", 0) or 0),
        "impressions": int(row.get("impressions", 0) or 0),
        "clicks": int(row.get("clicks", 0) or 0),
        "purchases": purchases,
        "purchase_value": purchase_value,
        "currency": row.get("account_currency", "?"),
    }


async def account_info(ad_account_id: str) -> dict:
    body = await _get(ad_account_id, {"fields": "name,currency,account_status,amount_spent"})
    return body


# ---------------------------------------------------------------------------
# Ad-level insights + creative fetch (v1 /ads /creative /ideas substrate)
# ---------------------------------------------------------------------------

# Meta returns the same purchase event under multiple `action_type` aliases —
# `purchase`, `omni_purchase`, `offsite_conversion.fb_pixel_purchase`,
# `onsite_web_purchase`, `onsite_web_app_purchase` — all representing the
# same underlying conversions. Summing across them double-counts by 3-5×.
#
# `omni_purchase` is Meta's canonical cross-device deduplicated parent
# metric and is the same number shown in Ads Manager's "Purchase ROAS"
# column. Use ONLY that.
#
# Confirmed 2026-04-20 via raw API call against act_654879327196107:
#   purchase_roas.omni_purchase = 1.22×  (matches dashboard)
#   summing all 5 aliases = 3.67×         (wrong — earlier bug in this code)
PURCHASE_ACTION_TYPES = {
    "omni_purchase",
}


def _sum_purchases(row: dict) -> tuple[int, float]:
    purchases = 0
    purchase_value = 0.0
    for a in row.get("actions", []) or []:
        if a.get("action_type") in PURCHASE_ACTION_TYPES:
            purchases += int(a.get("value", 0) or 0)
    for av in row.get("action_values", []) or []:
        if av.get("action_type") in PURCHASE_ACTION_TYPES:
            purchase_value += float(av.get("value", 0) or 0)
    return purchases, purchase_value


async def ads_for_account(ad_account_id: str, days: int = 7, limit: int = 200) -> list[dict]:
    """Return joined ad metadata + ad-level insights for every ad in this account.

    One row per ad, metrics over last N days.
    """
    # 1) ad metadata + creative
    ads_body = await _get(
        f"{ad_account_id}/ads",
        {
            "fields": "id,name,status,effective_status,created_time,creative{id,thumbnail_url,body,title,object_type,video_id}",
            "limit": limit,
        },
    )
    ad_by_id: dict[str, dict] = {a["id"]: a for a in ads_body.get("data", [])}

    # 2) insights at ad level
    if days in (7, 14, 28, 30, 90):
        time_params = {"date_preset": f"last_{days}d"}
    else:
        from datetime import datetime, timedelta, timezone
        end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        time_params = {"time_range": f'{{"since":"{start}","until":"{end}"}}'}

    insights_body = await _get(
        f"{ad_account_id}/insights",
        {
            "level": "ad",
            "fields": "ad_id,ad_name,spend,impressions,clicks,ctr,cpc,cpm,frequency,reach,actions,action_values,account_currency",
            "limit": limit,
            **time_params,
        },
    )

    results: list[dict] = []
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    for row in insights_body.get("data", []):
        ad_id = row.get("ad_id")
        ad = ad_by_id.get(ad_id, {})
        purchases, purchase_value = _sum_purchases(row)
        spend = float(row.get("spend", 0) or 0)

        # Parse created_time (ISO 8601 with TZ) → days live
        days_live: float = 0.0
        created = ad.get("created_time")
        if created:
            try:
                ts = datetime.fromisoformat(created.replace("Z", "+00:00"))
                days_live = max(0.0, (now - ts).total_seconds() / 86400.0)
            except Exception:
                pass

        results.append({
            "ad_account_id": ad_account_id,
            "ad_id": ad_id,
            "ad_name": ad.get("name") or row.get("ad_name", ""),
            "status": ad.get("status", ""),
            "effective_status": ad.get("effective_status", ""),
            "creative": ad.get("creative", {}),
            "created_time": created or "",
            "days_live": days_live,
            "spend": spend,
            "currency": row.get("account_currency", "?"),
            "impressions": int(row.get("impressions", 0) or 0),
            "clicks": int(row.get("clicks", 0) or 0),
            "ctr": float(row.get("ctr", 0) or 0),
            "cpc": float(row.get("cpc", 0) or 0),
            "cpm": float(row.get("cpm", 0) or 0),
            "frequency": float(row.get("frequency", 0) or 0),
            "reach": int(row.get("reach", 0) or 0),
            "purchases": purchases,
            "purchase_value": purchase_value,
            "reported_roas": (purchase_value / spend) if spend > 0 else 0.0,
        })
    return results


async def creative_details(ad_id: str, days: int = 7) -> dict:
    """Return one ad's creative + last-N-days metrics (for /creative vision critique)."""
    ad_info = await _get(
        ad_id,
        {"fields": "id,name,status,effective_status,adset_id,campaign_id,"
                   "creative{id,thumbnail_url,body,title,video_id,image_url,object_type,object_story_spec,effective_object_story_id}"},
    )

    if days in (7, 14, 28, 30, 90):
        time_params = {"date_preset": f"last_{days}d"}
    else:
        from datetime import datetime, timedelta, timezone
        end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        time_params = {"time_range": f'{{"since":"{start}","until":"{end}"}}'}

    insights_body = await _get(
        f"{ad_id}/insights",
        {
            "fields": "spend,impressions,clicks,ctr,cpc,cpm,frequency,reach,actions,action_values,account_currency",
            **time_params,
        },
    )
    rows = insights_body.get("data", [])
    m = rows[0] if rows else {}
    purchases, purchase_value = _sum_purchases(m)
    spend = float(m.get("spend", 0) or 0)

    return {
        "ad_id": ad_id,
        "ad_name": ad_info.get("name", ""),
        "status": ad_info.get("status", ""),
        "effective_status": ad_info.get("effective_status", ""),
        "creative": ad_info.get("creative", {}),
        "currency": m.get("account_currency", "?"),
        "spend": spend,
        "impressions": int(m.get("impressions", 0) or 0),
        "clicks": int(m.get("clicks", 0) or 0),
        "ctr": float(m.get("ctr", 0) or 0),
        "cpc": float(m.get("cpc", 0) or 0),
        "cpm": float(m.get("cpm", 0) or 0),
        "frequency": float(m.get("frequency", 0) or 0),
        "reach": int(m.get("reach", 0) or 0),
        "purchases": purchases,
        "purchase_value": purchase_value,
        "reported_roas": (purchase_value / spend) if spend > 0 else 0.0,
    }
