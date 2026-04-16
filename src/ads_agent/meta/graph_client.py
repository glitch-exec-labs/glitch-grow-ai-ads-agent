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

    purchases = 0
    purchase_value = 0.0
    for a in row.get("actions", []) or []:
        if a.get("action_type") in ("purchase", "offsite_conversion.fb_pixel_purchase", "omni_purchase"):
            purchases += int(a.get("value", 0) or 0)
    for av in row.get("action_values", []) or []:
        if av.get("action_type") in ("purchase", "offsite_conversion.fb_pixel_purchase", "omni_purchase"):
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
