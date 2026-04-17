"""Nightly Amazon cache sync.

Walks AMAZON_ACCOUNTS_JSON in .env, invokes amazon-ads-mcp tools via the
MCP JSON-RPC client, and upserts rows into ads_agent.amazon_daily.

Typical use:
    python ops/scripts/sync_amazon.py                   # all stores, last 7 days
    python ops/scripts/sync_amazon.py --days 30         # widen window
    python ops/scripts/sync_amazon.py --store ayurpet-ind
    python ops/scripts/sync_amazon.py --dry-run         # print what would happen

Why a cron and not live queries:
    Each Supermetrics Amazon Ads query takes 2-3 min (Amazon async Reports API).
    9 accounts for ayurpet-global takes ~6-8 min even parallel. Inline Telegram
    replies are infeasible; caching is the only viable UX pattern.

On OAuth expiry (`QUERY_AUTH_UNAVAILABLE`):
    Per-account error is recorded in ads_agent.amazon_sync_errors and a Telegram
    alert fires (if TELEGRAM_BOT_TOKEN_ADS + TELEGRAM_ADMIN_IDS set). User
    reconnects the Amazon OAuth in Supermetrics dashboard, re-runs the sync.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass
from typing import Any

sys.path.insert(0, "src")

from dotenv import load_dotenv

load_dotenv()

import asyncpg
import httpx

from ads_agent.amazon.mcp_client import AmazonMcpError, call_tool
from ads_agent.config import STORES, settings

log = logging.getLogger("sync_amazon")

# Concurrency cap — Supermetrics 502s on too-many-concurrent-Amazon-reports
# from the same account, so bound parallelism tightly.
MAX_CONCURRENT = 3

# Per-call timeout inside the MCP client — slightly longer than Amazon's worst case
MCP_TIMEOUT_S = 420.0


@dataclass
class SyncResult:
    store_slug: str
    account_id: str
    marketplace: str
    report_type: str
    source: str
    rows_written: int
    error: str | None = None


# ── Account config loading ────────────────────────────────────────────────────

def _amazon_accounts() -> dict[str, list[dict]]:
    raw = os.environ.get("AMAZON_ACCOUNTS_JSON", "").strip()
    if not raw:
        log.warning("AMAZON_ACCOUNTS_JSON empty; nothing to sync")
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        log.error("AMAZON_ACCOUNTS_JSON is not valid JSON")
        return {}


# ── Row normalization ─────────────────────────────────────────────────────────

def _f(row: dict, *keys: str) -> float | None:
    """Try each key (case-insensitive); return first non-null value as float."""
    for k in keys:
        for rk, v in row.items():
            if rk.lower() == k.lower() and v not in (None, ""):
                try:
                    return float(v)
                except (TypeError, ValueError):
                    continue
    return None


def _i(row: dict, *keys: str) -> int | None:
    v = _f(row, *keys)
    return int(v) if v is not None else None


def _date(row: dict) -> str | None:
    for k in ("date", "Date"):
        if k in row and row[k]:
            return str(row[k])[:10]  # trim time if present
    return None


# ── One-account sync ──────────────────────────────────────────────────────────

async def _record_error(
    pool: asyncpg.Pool,
    store_slug: str,
    account_id: str,
    report_type: str,
    error_msg: str,
) -> None:
    kind = "other"
    m = error_msg.upper()
    if "QUERY_AUTH_UNAVAILABLE" in m or "AUTH" in m and "EXPIRED" in m:
        kind = "auth_expired"
    elif "TIMEOUT" in m or "TimeoutException" in error_msg:
        kind = "timeout"
    elif "502" in m:
        kind = "502"
    elif "FIELD_NOT_FOUND" in m or "SCHEMA" in m:
        kind = "schema"

    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO ads_agent.amazon_sync_errors
               (store_slug, account_id, report_type, error_kind, error_msg)
               VALUES ($1, $2, $3, $4, $5)""",
            store_slug, account_id, report_type, kind, error_msg[:1000],
        )


async def sync_one_account(
    pool: asyncpg.Pool,
    store_slug: str,
    acct: dict,
    days: int,
    dry_run: bool,
) -> SyncResult:
    ds_id = acct["ds_id"]
    account_id = acct["account_id"]
    marketplace = acct.get("name", account_id)
    login_id = acct["login_id"]
    report_type = acct.get("report_type", "seller" if ds_id == "ASELL" else "SponsoredProduct")
    source = "ads" if ds_id in ("AA", "ADSP") else "seller"

    log.info("sync %s · %s · %s · days=%d", store_slug, marketplace, report_type, days)

    if dry_run:
        log.info("  [DRY-RUN] would call MCP for %s %s", ds_id, account_id)
        return SyncResult(store_slug, account_id, marketplace, report_type, source, 0)

    # Pick the right MCP tool
    if ds_id in ("AA", "ADSP"):
        tool_name = "supermetrics_ads_performance"
        arguments = {
            "ds_user": login_id,
            "account_id": account_id,
            "days": days,
            "report_type": report_type,
        }
    elif ds_id == "ASELL":
        tool_name = "supermetrics_seller_sessions"
        arguments = {"ds_user": login_id, "account_id": account_id, "days": days}
    else:
        return SyncResult(store_slug, account_id, marketplace, report_type, source, 0,
                          error=f"unknown ds_id {ds_id}")

    # Invoke the MCP
    try:
        result = await call_tool(tool_name, arguments, timeout_s=MCP_TIMEOUT_S)
    except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.TimeoutException) as e:
        msg = f"MCP timeout after {MCP_TIMEOUT_S}s"
        log.warning("  %s: %s", marketplace, msg)
        await _record_error(pool, store_slug, account_id, report_type, msg)
        return SyncResult(store_slug, account_id, marketplace, report_type, source, 0, error=msg)
    except AmazonMcpError as e:
        msg = str(e)
        log.warning("  %s: MCP error: %s", marketplace, msg[:200])
        await _record_error(pool, store_slug, account_id, report_type, msg)
        return SyncResult(store_slug, account_id, marketplace, report_type, source, 0, error=msg)
    except Exception as e:
        msg = f"unexpected: {e}"
        log.exception("  %s: %s", marketplace, msg)
        await _record_error(pool, store_slug, account_id, report_type, msg)
        return SyncResult(store_slug, account_id, marketplace, report_type, source, 0, error=msg)

    # Tool wrapper put error into result dict
    if isinstance(result, dict) and result.get("error"):
        msg = str(result["error"])
        log.warning("  %s: tool error: %s", marketplace, msg[:200])
        await _record_error(pool, store_slug, account_id, report_type, msg)
        return SyncResult(store_slug, account_id, marketplace, report_type, source, 0, error=msg)

    rows = (result or {}).get("rows", []) if isinstance(result, dict) else []
    if not rows:
        log.info("  %s: 0 rows", marketplace)
        return SyncResult(store_slug, account_id, marketplace, report_type, source, 0)

    # UPSERT rows
    written = 0
    async with pool.acquire() as conn:
        for row in rows:
            dt = _date(row)
            if not dt:
                continue
            await conn.execute(
                """INSERT INTO ads_agent.amazon_daily
                   (date, store_slug, account_id, marketplace, report_type, source,
                    impressions, clicks, cost, sales, orders, acos, roas, raw_json, synced_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14::jsonb, NOW())
                   ON CONFLICT (date, account_id, report_type, source) DO UPDATE SET
                     impressions = EXCLUDED.impressions,
                     clicks      = EXCLUDED.clicks,
                     cost        = EXCLUDED.cost,
                     sales       = EXCLUDED.sales,
                     orders      = EXCLUDED.orders,
                     acos        = EXCLUDED.acos,
                     roas        = EXCLUDED.roas,
                     raw_json    = EXCLUDED.raw_json,
                     synced_at   = NOW()""",
                dt, store_slug, account_id, marketplace, report_type, source,
                _i(row, "impressions"), _i(row, "clicks"),
                _f(row, "cost", "spend"), _f(row, "sales"), _i(row, "orders"),
                _f(row, "acos"), _f(row, "roas"),
                json.dumps(row),
            )
            written += 1
    log.info("  %s: upserted %d rows", marketplace, written)
    return SyncResult(store_slug, account_id, marketplace, report_type, source, written)


# ── Store sync ────────────────────────────────────────────────────────────────

async def sync_store(
    pool: asyncpg.Pool,
    store_slug: str,
    days: int,
    dry_run: bool,
) -> list[SyncResult]:
    accounts_map = _amazon_accounts()
    accts = accounts_map.get(store_slug, [])
    if not accts:
        log.warning("no Amazon accounts mapped for store %s", store_slug)
        return []

    sem = asyncio.Semaphore(MAX_CONCURRENT)

    async def _bounded(acct: dict) -> SyncResult:
        async with sem:
            return await sync_one_account(pool, store_slug, acct, days, dry_run)

    return await asyncio.gather(*[_bounded(a) for a in accts])


# ── Alerts ────────────────────────────────────────────────────────────────────

async def _telegram_alert(text: str) -> None:
    tok = os.environ.get("TELEGRAM_BOT_TOKEN_ADS", "")
    admin = os.environ.get("TELEGRAM_ADMIN_IDS", "").split(",")[0].strip()
    if not tok or not admin:
        return
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            await c.post(
                f"https://api.telegram.org/bot{tok}/sendMessage",
                json={"chat_id": int(admin), "text": text[:4000]},
            )
    except Exception:
        log.exception("Telegram alert failed")


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    p = argparse.ArgumentParser(description="Nightly Amazon cache sync via amazon-ads-mcp")
    p.add_argument("--store", help="single store slug; default: all mapped stores")
    p.add_argument("--days", type=int, default=7, help="lookback window (1, 7, 14, 30, 90; default 7)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    stores = [args.store] if args.store else sorted(_amazon_accounts().keys())
    if not stores:
        log.error("no stores to sync (AMAZON_ACCOUNTS_JSON empty?)")
        return

    pool = await asyncpg.create_pool(
        settings().postgres_insights_ro_url,
        min_size=1, max_size=6, command_timeout=30.0,
    )

    all_results: list[SyncResult] = []
    try:
        for slug in stores:
            log.info("=== store: %s ===", slug)
            results = await sync_store(pool, slug, args.days, args.dry_run)
            all_results.extend(results)
    finally:
        await pool.close()

    # Summary
    total_written = sum(r.rows_written for r in all_results)
    errors = [r for r in all_results if r.error]
    auth_expired = [r for r in errors if "QUERY_AUTH_UNAVAILABLE" in (r.error or "")]
    log.info("=== sync complete: %d rows written, %d errors ===", total_written, len(errors))

    # Telegram alert if OAuth expiry detected
    if auth_expired and not args.dry_run:
        affected = ", ".join(sorted({r.marketplace for r in auth_expired}))
        msg = (
            f"🔴 Amazon sync — Supermetrics OAuth expired\n\n"
            f"Affected accounts: {affected}\n"
            f"Fix: go to Supermetrics dashboard → Team → Data source logins → "
            f"reconnect the expired Amazon login, then re-run "
            f"`ops/scripts/sync_amazon.py`."
        )
        await _telegram_alert(msg)


if __name__ == "__main__":
    asyncio.run(main())
