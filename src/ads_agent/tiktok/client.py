"""Thin async wrapper around the forked TikTok Business API Python SDK."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from ads_agent.config import settings

_IMPORT_ERROR: Exception | None = None

try:
    from business_api_client.api.account_management_api import AccountManagementApi
    from business_api_client.api.reporting_api import ReportingApi
except Exception as exc:  # pragma: no cover - exercised implicitly by runtime imports
    AccountManagementApi = None  # type: ignore[assignment]
    ReportingApi = None  # type: ignore[assignment]
    _IMPORT_ERROR = exc


class TikTokError(RuntimeError):
    pass


def _require_sdk() -> None:
    if _IMPORT_ERROR is not None or AccountManagementApi is None or ReportingApi is None:
        raise TikTokError(
            "TikTok SDK is unavailable. Install project dependencies to pull "
            "glitch-exec-labs/tiktok-business-api-sdk."
        )


def _access_token(override: str | None = None) -> str:
    token = (override or settings().tiktok_access_token).strip()
    if not token:
        raise TikTokError("TikTok access token not set")
    return token


def _unwrap(response: Any) -> dict[str, Any]:
    if hasattr(response, "to_dict"):
        body = response.to_dict()
        if isinstance(body, dict):
            return body
    if isinstance(response, dict):
        return response
    raise TikTokError(f"Unexpected TikTok SDK response type: {type(response).__name__}")


def _expect_ok(response: Any) -> dict[str, Any]:
    body = _unwrap(response)
    code = body.get("code")
    if code not in (0, None):
        msg = body.get("message") or "unknown error"
        req = body.get("request_id") or "n/a"
        raise TikTokError(f"TikTok API error {code}: {msg} (request_id={req})")
    data = body.get("data")
    return data if isinstance(data, dict) else {}


def _date_window(days: int) -> tuple[str, str]:
    days = max(1, int(days))
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days - 1)
    return start.isoformat(), end.isoformat()


def _to_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _to_int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


async def advertiser_info(advertiser_id: str, *, access_token: str | None = None) -> dict[str, Any]:
    _require_sdk()

    def _call() -> dict[str, Any]:
        try:
            response = AccountManagementApi().advertiser_info(
                [advertiser_id],
                _access_token(access_token),
                fields=["name", "currency", "status"],
            )
        except Exception as exc:
            raise TikTokError(f"advertiser_info: {exc}") from exc
        return _expect_ok(response)

    data = await asyncio.to_thread(_call)
    rows = data.get("list") if isinstance(data, dict) else None
    if isinstance(rows, list) and rows:
        first = rows[0]
        return first if isinstance(first, dict) else {}
    return {}


async def advertiser_spend(
    advertiser_id: str,
    days: int = 7,
    *,
    access_token: str | None = None,
) -> dict[str, Any]:
    _require_sdk()
    start_date, end_date = _date_window(days)

    def _call() -> dict[str, Any]:
        try:
            response = ReportingApi().report_integrated_get(
                "BASIC",
                _access_token(access_token),
                advertiser_id=advertiser_id,
                service_type="AUCTION",
                data_level="AUCTION_ADVERTISER",
                dimensions=["stat_time_day"],
                metrics=["spend", "impressions", "clicks"],
                start_date=start_date,
                end_date=end_date,
                page=1,
                page_size=max(30, days),
                enable_total_metrics=True,
            )
        except Exception as exc:
            raise TikTokError(f"report_integrated_get: {exc}") from exc
        return _expect_ok(response)

    data = await asyncio.to_thread(_call)
    totals = data.get("total_metrics") if isinstance(data.get("total_metrics"), dict) else {}
    rows = data.get("list") if isinstance(data.get("list"), list) else []
    if not totals and rows:
        totals = {
            "spend": sum(_to_float(r.get("spend")) for r in rows if isinstance(r, dict)),
            "impressions": sum(_to_int(r.get("impressions")) for r in rows if isinstance(r, dict)),
            "clicks": sum(_to_int(r.get("clicks")) for r in rows if isinstance(r, dict)),
        }

    spend = _to_float(totals.get("spend"))
    impressions = _to_int(totals.get("impressions"))
    clicks = _to_int(totals.get("clicks"))
    ctr = (clicks / impressions * 100.0) if impressions else 0.0
    cpc = (spend / clicks) if clicks else 0.0
    return {
        "spend": spend,
        "impressions": impressions,
        "clicks": clicks,
        "ctr": ctr,
        "cpc": cpc,
        "start_date": start_date,
        "end_date": end_date,
        "raw_total_metrics": totals,
    }
