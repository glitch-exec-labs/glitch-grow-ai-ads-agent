"""Supermetrics API client — Amazon Seller Central + Amazon Ads.

Supermetrics wraps many data sources (incl. Amazon MWS + Amazon Ads API) behind
a single REST endpoint. We use it for Ayurpet's Amazon channel since direct
Amazon SP-API / Amazon Ads API require individual OAuth apps per marketplace.

Base URL:        https://api.supermetrics.com/enterprise/v2/
Auth:            Authorization: Bearer <api_key> (starts with api_)
Query endpoint:  /query/data/json?json=<url-encoded-JSON-query>
Logins list:     /ds/logins
Login accounts:  /ds/login/<login_id>/accounts

**Known gotcha:** Amazon OAuth tokens have a 1h lifetime. Supermetrics is
supposed to refresh them silently when `is_refreshable=true`, but in practice
this sometimes fails and the query returns `QUERY_AUTH_UNAVAILABLE`. Fix:
re-authenticate the connection in the Supermetrics web dashboard (Team →
Data source logins → reconnect).

Data source IDs we use:
- ASELL — Amazon Seller Central (orders, sales, units, sessions)
- AA    — Amazon Ads (spend, impressions, clicks, sales, ACOS, ROAS)
- ADSP  — Amazon DSP
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.parse
from typing import Any

import httpx

log = logging.getLogger(__name__)

BASE = "https://api.supermetrics.com/enterprise/v2"


class SupermetricsError(RuntimeError):
    pass


def _api_key() -> str:
    key = os.environ.get("SUPERMETRICS_API_KEY", "").strip()
    if not key:
        raise SupermetricsError("SUPERMETRICS_API_KEY is not set")
    return key


def _store_accounts_map() -> dict:
    raw = os.environ.get("AMAZON_ACCOUNTS_JSON", "").strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        log.warning("AMAZON_ACCOUNTS_JSON invalid")
        return {}


def amazon_accounts_for_store(store_slug: str) -> list[dict]:
    """Return [{ds_id, login_id, account_id, name}, ...] for this store."""
    return _store_accounts_map().get(store_slug, [])


async def _request(path: str, *, method: str = "GET", params: dict | None = None) -> Any:
    headers = {"Authorization": f"Bearer {_api_key()}"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.request(method, f"{BASE}{path}", headers=headers, params=params)
    try:
        body = r.json()
    except Exception:
        raise SupermetricsError(f"{path}: HTTP {r.status_code} body was not JSON")
    if "error" in body:
        raise SupermetricsError(f"{path}: {body['error'].get('code')} — {body['error'].get('description','')}")
    return body


async def list_logins() -> list[dict]:
    """Return all data-source logins visible to this API key.

    Each login object has: login_id, login_type, username, display_name, ds_info.ds_id,
    ds_info.name, auth_time, expiry_time, is_refreshable, is_shared.
    """
    body = await _request("/ds/logins")
    return body.get("data", [])


async def list_login_accounts(login_id: str, *, limit: int = 100) -> list[dict]:
    """Return accounts (marketplaces / profiles) under a given login."""
    body = await _request(f"/ds/login/{login_id}/accounts", params={"limit": limit})
    return body.get("data", [])


async def query(
    *,
    ds_id: str,
    login_id: str,
    account_id: str,
    fields: list[str] | str,
    date_range_type: str = "last_30_days",
    start_date: str | None = None,
    end_date: str | None = None,
    max_rows: int = 1000,
    extra: dict | None = None,
    timeout_s: float = 180.0,
) -> list[dict]:
    """Run a Supermetrics data query. Returns a list of row dicts.

    Amazon Ads queries hit Amazon's async report API and can take 60-180s.
    Supermetrics waits on our connection and then streams results back.

    Query params:
      ds_login = the per-login identifier `dsl_*` (NOT ds_user — that was our
        earlier misread of the API).
      fields = list or comma-separated string of field IDs.
      date_range_type = last_7_days / last_30_days / last_90_days / custom.
    """
    if isinstance(fields, list):
        fields = ",".join(fields)

    q: dict = {
        "ds_id": ds_id,
        "ds_login": login_id,
        "ds_accounts": account_id,
        "fields": fields,
        "date_range_type": date_range_type,
        "max_rows": max_rows,
    }
    if date_range_type == "custom":
        if not (start_date and end_date):
            raise SupermetricsError("custom date_range_type needs start_date + end_date")
        q["start_date"] = start_date
        q["end_date"] = end_date
    if extra:
        q.update(extra)

    json_param = urllib.parse.quote(json.dumps(q, separators=(",", ":")))
    headers = {"Authorization": f"Bearer {_api_key()}"}
    url = f"{BASE}/query/data/json?json={json_param}"

    async with httpx.AsyncClient(timeout=timeout_s) as client:
        r = await client.get(url, headers=headers)
    try:
        body = r.json()
    except Exception:
        raise SupermetricsError(f"query: HTTP {r.status_code} body was not JSON")
    if "error" in body:
        raise SupermetricsError(
            f"{body['error'].get('code')} — {body['error'].get('description','')}"
        )

    # Supermetrics returns `data` in one of two shapes:
    #   A) {"result": [ {field:value, ...}, ... ]}
    #   B) [[header1, header2, ...], [v1, v2, ...], [v1, v2, ...]]   (table form, most common)
    # Normalize both into list[dict].
    data = body.get("data")
    if isinstance(data, dict) and "result" in data:
        return data["result"]
    if isinstance(data, list) and data:
        # Table form: first row is the header
        if all(isinstance(r, list) for r in data):
            header = data[0]
            return [dict(zip(header, row)) for row in data[1:]]
        # Already list of dicts?
        if all(isinstance(r, dict) for r in data):
            return data
    return []


# ---------------------------------------------------------------------------
# High-level helpers per store
# ---------------------------------------------------------------------------

# Amazon Seller Central (ASELL) — only `Sessions` confirmed valid; other obvious
# field names (UnitsOrdered, Orders, TotalOrderItems, OrderedProductSales) were
# all rejected. Supermetrics's ASELL schema uses different names we haven't
# discovered yet. Keep minimal for now; revisit with docs.
DEFAULT_SELLER_FIELDS = ["Date", "Sessions"]

# Canonical Amazon Ads (AA) fields — verified valid 2026-04-16
# Note: Supermetrics uses "Cost" not "Spend".
DEFAULT_ADS_FIELDS = [
    "Date",
    "Impressions",
    "Clicks",
    "Cost",
    "Sales",
    "Orders",
    "ACOS",
    "ROAS",
]


async def seller_stats(
    store_slug: str,
    *,
    days: int = 30,
) -> list[dict]:
    """Return daily Amazon Seller Central rows for all marketplaces linked to this store."""
    accounts = [a for a in amazon_accounts_for_store(store_slug) if a["ds_id"] == "ASELL"]
    if not accounts:
        raise SupermetricsError(f"no Amazon Seller accounts mapped for store {store_slug!r}")

    date_range_type = f"last_{days}_days" if days in (7, 14, 30, 90) else "custom"
    return await _gather_account_queries(accounts, "ASELL", DEFAULT_SELLER_FIELDS, date_range_type)


async def ads_stats(
    store_slug: str,
    *,
    days: int = 30,
) -> list[dict]:
    """Return daily Amazon Ads rows for all ad-accounts linked to this store.

    Runs per-account queries in parallel since each one calls Amazon's async
    report API (60-120s latency). Sequential would take minutes for a
    multi-market brand like Ayurpet Global (9 ad accounts).
    """
    accounts = [a for a in amazon_accounts_for_store(store_slug) if a["ds_id"] in ("AA", "ADSP")]
    if not accounts:
        raise SupermetricsError(f"no Amazon Ads accounts mapped for store {store_slug!r}")

    date_range_type = f"last_{days}_days" if days in (7, 14, 30, 90) else "custom"
    return await _gather_account_queries(accounts, None, DEFAULT_ADS_FIELDS, date_range_type)


async def _one_account_query(acct: dict, ds_id: str | None, fields: list[str], date_range_type: str) -> list[dict]:
    """Query one account; on timeout/error, return [] and log — never raise."""
    effective_ds = ds_id or acct["ds_id"]
    try:
        rows = await query(
            ds_id=effective_ds,
            login_id=acct["login_id"],
            account_id=acct["account_id"],
            fields=fields,
            date_range_type=date_range_type,
            timeout_s=240.0,
        )
    except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.TimeoutException):
        log.warning("Supermetrics query timed out for %s (%s)", acct.get("name"), acct["account_id"])
        return []
    except SupermetricsError as e:
        log.warning("Supermetrics query failed for %s: %s", acct.get("name"), e)
        return []
    except Exception:
        log.exception("unexpected error querying %s", acct.get("name"))
        return []
    for r in rows:
        r["_marketplace"] = acct.get("name", acct["account_id"])
        r["_account_id"] = acct["account_id"]
    return rows


async def _gather_account_queries(
    accounts: list[dict],
    ds_id: str | None,
    fields: list[str],
    date_range_type: str,
) -> list[dict]:
    """Run per-account queries concurrently, merge results. Individual failures
    (timeouts, auth expiry, per-market issues) don't take down the whole call."""
    results = await asyncio.gather(
        *[_one_account_query(a, ds_id, fields, date_range_type) for a in accounts],
        return_exceptions=False,
    )
    merged: list[dict] = []
    for r in results:
        merged.extend(r)
    return merged
