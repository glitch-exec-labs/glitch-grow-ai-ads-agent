"""Daily Meta ads snapshot → ads_agent.meta_ads_daily.

Walks STORE_AD_ACCOUNTS_JSON in .env, fetches ad-level insights at
per-day granularity (time_increment=1) plus creative metadata (destination
URL, CTA, body, title), and UPSERTs one row per (date, ad_id) per account.

Primary purpose: persist `destination_url` on every Meta ad alongside its
daily spend/clicks/impressions — enables Meta → Amazon attribution analysis
by filtering rows where destination_url matches 'amazon.in' / 'amazon.ae'
and correlating against ads_agent.amazon_daily_v / amazon_traffic_daily_v.

Typical use:
    python ops/scripts/sync_meta_ads.py                    # all accounts, 7d window
    python ops/scripts/sync_meta_ads.py --days 30          # wider backfill
    python ops/scripts/sync_meta_ads.py --account act_X    # one account only
    python ops/scripts/sync_meta_ads.py --dry-run          # no writes, log only

Safe to re-run — UPSERT on (date, ad_id). Backfill on first deploy is
expected to pull last 30 days by default (overridable via --days).

Rate limits: Meta's Marketing API is stingy. We bound concurrency (3 parallel
accounts) and use one bulk /insights call per account per window — no
per-ad fan-out — so a typical ayurpet sync is < 30s.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import date as _date_cls, datetime, timedelta, timezone

sys.path.insert(0, "src")

from dotenv import load_dotenv

load_dotenv()

import asyncpg
import httpx

log = logging.getLogger("sync_meta_ads")

GRAPH_BASE = "https://graph.facebook.com/v21.0"
MAX_CONCURRENT = 3
HTTP_TIMEOUT_S = 60.0

# Which Meta pixel action-types count as purchases / ATC / content-view.
# Matches the same taxonomy used in src/ads_agent/meta/graph_client.py.
PURCHASE_ACTION_TYPES = {
    "purchase",
    "offsite_conversion.fb_pixel_purchase",
    "omni_purchase",
    "onsite_web_purchase",
    "onsite_web_app_purchase",
}
ATC_ACTION_TYPES = {
    "add_to_cart",
    "offsite_conversion.fb_pixel_add_to_cart",
    "omni_add_to_cart",
}
VIEW_ACTION_TYPES = {
    "view_content",
    "offsite_conversion.fb_pixel_view_content",
    "omni_view_content",
}


@dataclass
class SyncResult:
    ad_account_id: str
    store_slugs: list[str]
    rows_written: int
    error: str | None = None


# ── Config ────────────────────────────────────────────────────────────────────

def _store_ad_accounts() -> dict[str, list[str]]:
    """Load STORE_AD_ACCOUNTS_JSON: {store_slug: [act_id, ...]}."""
    raw = os.environ.get("STORE_AD_ACCOUNTS_JSON", "").strip()
    if not raw:
        log.warning("STORE_AD_ACCOUNTS_JSON empty; nothing to sync")
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        log.error("STORE_AD_ACCOUNTS_JSON is not valid JSON")
        return {}


def _accounts_to_slugs() -> dict[str, list[str]]:
    """Invert STORE_AD_ACCOUNTS_JSON → {act_id: [slug, slug, ...]}.

    A single Meta account can be shared across stores (e.g. Ayurpet's
    act_654879327196107 drives both ayurpet-ind and ayurpet-global).
    """
    out: dict[str, list[str]] = {}
    for slug, accts in _store_ad_accounts().items():
        for a in accts:
            out.setdefault(a, []).append(slug)
    return out


# ── HTTP ──────────────────────────────────────────────────────────────────────

async def _get(client: httpx.AsyncClient, path: str, params: dict) -> dict:
    token = os.environ.get("META_ACCESS_TOKEN", "")
    if not token:
        raise RuntimeError("META_ACCESS_TOKEN not set in env")
    params = {**params, "access_token": token}
    r = await client.get(f"{GRAPH_BASE}/{path}", params=params, timeout=HTTP_TIMEOUT_S)
    body = r.json()
    if r.status_code != 200 or body.get("error"):
        raise RuntimeError(f"meta {path}: {body.get('error') or r.text[:300]}")
    return body


async def _paginate(client: httpx.AsyncClient, path: str, params: dict) -> list[dict]:
    """Exhaust `paging.next` cursors."""
    out: list[dict] = []
    body = await _get(client, path, params)
    out.extend(body.get("data", []))
    next_url = (body.get("paging") or {}).get("next")
    while next_url:
        r = await client.get(next_url, timeout=HTTP_TIMEOUT_S)
        nb = r.json()
        if r.status_code != 200 or nb.get("error"):
            log.warning("pagination stopped on %s: %s", path, nb.get("error"))
            break
        out.extend(nb.get("data", []))
        next_url = (nb.get("paging") or {}).get("next")
    return out


# ── Creative parsing ──────────────────────────────────────────────────────────

def _extract_destination_url(creative: dict) -> tuple[str | None, str | None]:
    """Walk Meta's many creative shapes to find the landing URL + CTA type.

    Returns (destination_url, cta_type) or (None, None) if not discoverable.
    """
    if not creative:
        return None, None

    # 1) object_story_spec.link_data (single-image / link ad)
    oss = creative.get("object_story_spec") or {}
    ld = oss.get("link_data") or {}
    if ld.get("link"):
        cta = (ld.get("call_to_action") or {}).get("type")
        return ld["link"], cta

    # 2) object_story_spec.video_data.call_to_action.value.link (video ad)
    vd = oss.get("video_data") or {}
    vcta = vd.get("call_to_action") or {}
    v_link = (vcta.get("value") or {}).get("link")
    if v_link:
        return v_link, vcta.get("type")

    # 3) object_story_spec.template_data (carousel parent)
    td = oss.get("template_data") or {}
    if td.get("link"):
        cta = (td.get("call_to_action") or {}).get("type")
        return td["link"], cta

    # 4) asset_feed_spec.link_urls (dynamic creative)
    afs = creative.get("asset_feed_spec") or {}
    link_urls = afs.get("link_urls") or []
    if link_urls:
        ws = link_urls[0].get("website_url")
        if ws:
            ctas = (afs.get("call_to_action_types") or [])
            return ws, (ctas[0] if ctas else None)

    return None, None


# ── Insights extraction ───────────────────────────────────────────────────────

def _sum_actions(row: dict, types: set[str], field: str = "actions") -> float:
    total = 0.0
    for a in row.get(field, []) or []:
        if a.get("action_type") in types:
            try:
                total += float(a.get("value", 0) or 0)
            except (TypeError, ValueError):
                continue
    return total


# ── One-account sync ──────────────────────────────────────────────────────────

async def sync_one_account(
    pool: asyncpg.Pool,
    client: httpx.AsyncClient,
    ad_account_id: str,
    store_slugs: list[str],
    days: int,
    dry_run: bool,
) -> SyncResult:
    log.info("sync %s · stores=%s · days=%d", ad_account_id, ",".join(store_slugs), days)

    # Step 1 — fetch daily insights for last N days (one row per ad per day).
    # Insights-first: this surfaces only ads that actually spent in the window,
    # so subsequent creative fetches stay small. Bulk /{account}/ads hits Meta's
    # payload cap on large accounts (Ayurpet: 'reduce the amount of data').
    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    try:
        insights = await _paginate(
            client,
            f"{ad_account_id}/insights",
            {
                "level": "ad",
                "time_increment": 1,  # per-day granularity
                "time_range": json.dumps({"since": start, "until": end}),
                "fields": (
                    "date_start,date_stop,ad_id,ad_name,campaign_id,campaign_name,"
                    "adset_id,adset_name,spend,impressions,clicks,reach,frequency,"
                    "ctr,cpc,cpm,actions,action_values,account_currency"
                ),
                "limit": 500,
            },
        )
    except Exception as e:
        msg = f"insights fetch failed: {e}"
        log.warning("  %s: %s", ad_account_id, msg[:200])
        return SyncResult(ad_account_id, store_slugs, 0, error=msg)

    log.info("  %s: %d insight rows", ad_account_id, len(insights))

    # Step 2 — fetch creative + ad metadata for ONLY the ads that appeared in
    # insights. Meta's ?ids= batch endpoint caps at ~50 per call, so we chunk.
    active_ad_ids = sorted({r["ad_id"] for r in insights if r.get("ad_id")})
    ad_by_id: dict[str, dict] = {}
    CHUNK = 50
    creative_fields = (
        "id,name,status,effective_status,campaign_id,adset_id,"
        "creative{id,thumbnail_url,body,title,object_type,"
        "object_story_spec{link_data{link,call_to_action},"
        "video_data{call_to_action},"
        "template_data{link,call_to_action}},"
        "asset_feed_spec{link_urls,call_to_action_types}}"
    )
    for i in range(0, len(active_ad_ids), CHUNK):
        chunk = active_ad_ids[i:i + CHUNK]
        try:
            body = await _get(client, "", {"ids": ",".join(chunk), "fields": creative_fields})
            # /?ids=a,b,c returns {a: {...}, b: {...}} (NOT a "data" envelope)
            for k, v in body.items():
                if isinstance(v, dict) and v.get("id"):
                    ad_by_id[v["id"]] = v
        except Exception as e:
            log.warning("  %s: creative batch %d-%d failed: %s",
                        ad_account_id, i, i + len(chunk), str(e)[:200])
            continue

    log.info("  %s: %d ads have creative loaded (from %d active)",
             ad_account_id, len(ad_by_id), len(active_ad_ids))

    if dry_run:
        # Log a sample with resolved destination for eyeballing
        amz_cnt = 0
        for row in insights[:20]:
            ad = ad_by_id.get(row.get("ad_id", ""), {})
            url, cta = _extract_destination_url(ad.get("creative") or {})
            tag = "AMZ" if url and "amazon." in url else "   "
            if tag == "AMZ":
                amz_cnt += 1
            log.info("    [%s] %s · %s · %s → %s",
                     tag, row.get("date_start"), row.get("ad_id"),
                     (ad.get("name") or "")[:30], (url or "")[:60])
        amz_total = sum(
            1 for row in insights
            if (u := _extract_destination_url((ad_by_id.get(row.get("ad_id",""), {}).get("creative") or {}))[0])
            and "amazon." in u
        )
        log.info("  %s: %d/%d insight rows point to amazon.*", ad_account_id, amz_total, len(insights))
        return SyncResult(ad_account_id, store_slugs, 0)

    # Step 3 — UPSERT rows.
    written = 0
    async with pool.acquire() as conn:
        for row in insights:
            dt_str = (row.get("date_start") or "")[:10]
            ad_id = row.get("ad_id")
            if not dt_str or not ad_id:
                continue
            try:
                dt = _date_cls.fromisoformat(dt_str)
            except ValueError:
                continue

            ad = ad_by_id.get(ad_id, {})
            creative = ad.get("creative") or {}
            dest_url, cta = _extract_destination_url(creative)

            await conn.execute(
                """INSERT INTO ads_agent.meta_ads_daily (
                        date, ad_account_id,
                        campaign_id, campaign_name, adset_id, adset_name,
                        ad_id, ad_name, effective_status,
                        destination_url, call_to_action,
                        creative_id, creative_body, creative_title, object_type,
                        spend, impressions, clicks, reach, frequency, ctr, cpc, cpm,
                        purchases, purchase_value, add_to_cart, content_view,
                        currency, raw_json, synced_at
                   ) VALUES (
                        $1, $2,
                        $3, $4, $5, $6,
                        $7, $8, $9,
                        $10, $11,
                        $12, $13, $14, $15,
                        $16, $17, $18, $19, $20, $21, $22, $23,
                        $24, $25, $26, $27,
                        $28, $29::jsonb, NOW()
                   )
                   ON CONFLICT (date, ad_id) DO UPDATE SET
                       ad_account_id    = EXCLUDED.ad_account_id,
                       campaign_id      = EXCLUDED.campaign_id,
                       campaign_name    = EXCLUDED.campaign_name,
                       adset_id         = EXCLUDED.adset_id,
                       adset_name       = EXCLUDED.adset_name,
                       ad_name          = EXCLUDED.ad_name,
                       effective_status = EXCLUDED.effective_status,
                       destination_url  = EXCLUDED.destination_url,
                       call_to_action   = EXCLUDED.call_to_action,
                       creative_id      = EXCLUDED.creative_id,
                       creative_body    = EXCLUDED.creative_body,
                       creative_title   = EXCLUDED.creative_title,
                       object_type      = EXCLUDED.object_type,
                       spend            = EXCLUDED.spend,
                       impressions      = EXCLUDED.impressions,
                       clicks           = EXCLUDED.clicks,
                       reach            = EXCLUDED.reach,
                       frequency        = EXCLUDED.frequency,
                       ctr              = EXCLUDED.ctr,
                       cpc              = EXCLUDED.cpc,
                       cpm              = EXCLUDED.cpm,
                       purchases        = EXCLUDED.purchases,
                       purchase_value   = EXCLUDED.purchase_value,
                       add_to_cart      = EXCLUDED.add_to_cart,
                       content_view     = EXCLUDED.content_view,
                       currency         = EXCLUDED.currency,
                       raw_json         = EXCLUDED.raw_json,
                       synced_at        = NOW()""",
                dt, ad_account_id,
                row.get("campaign_id"), row.get("campaign_name"),
                row.get("adset_id"), row.get("adset_name"),
                ad_id, row.get("ad_name") or ad.get("name"),
                ad.get("effective_status"),
                dest_url, cta,
                (creative.get("id") if creative else None),
                creative.get("body"),
                creative.get("title"),
                creative.get("object_type"),
                float(row.get("spend", 0) or 0),
                int(row.get("impressions", 0) or 0),
                int(row.get("clicks", 0) or 0),
                int(row.get("reach", 0) or 0),
                float(row.get("frequency", 0) or 0),
                float(row.get("ctr", 0) or 0),
                float(row.get("cpc", 0) or 0),
                float(row.get("cpm", 0) or 0),
                int(_sum_actions(row, PURCHASE_ACTION_TYPES)),
                _sum_actions(row, PURCHASE_ACTION_TYPES, "action_values"),
                int(_sum_actions(row, ATC_ACTION_TYPES)),
                int(_sum_actions(row, VIEW_ACTION_TYPES)),
                row.get("account_currency"),
                json.dumps(row),
            )
            written += 1

    log.info("  %s: upserted %d rows", ad_account_id, written)
    return SyncResult(ad_account_id, store_slugs, written)


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    p = argparse.ArgumentParser(description="Daily Meta ads snapshot → ads_agent.meta_ads_daily")
    p.add_argument("--account", help="single act_<id>; default: all in STORE_AD_ACCOUNTS_JSON")
    p.add_argument("--days", type=int, default=7,
                   help="lookback window in days (default 7; use 30 for first backfill)")
    p.add_argument("--dry-run", action="store_true",
                   help="log Amazon-linked ad count, no DB writes")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    accts_map = _accounts_to_slugs()
    if args.account:
        accts_map = {args.account: accts_map.get(args.account, ["?"])}
    if not accts_map:
        log.error("no Meta accounts to sync — check STORE_AD_ACCOUNTS_JSON")
        return

    dsn = os.environ.get("POSTGRES_INSIGHTS_RO_URL")
    if not dsn:
        log.error("POSTGRES_INSIGHTS_RO_URL not set")
        return

    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=4, command_timeout=60.0)
    results: list[SyncResult] = []
    try:
        sem = asyncio.Semaphore(MAX_CONCURRENT)
        async with httpx.AsyncClient() as client:
            async def _bounded(acct: str, slugs: list[str]) -> SyncResult:
                async with sem:
                    return await sync_one_account(pool, client, acct, slugs, args.days, args.dry_run)
            results = await asyncio.gather(*[_bounded(a, s) for a, s in accts_map.items()])
    finally:
        await pool.close()

    total = sum(r.rows_written for r in results)
    errs = [r for r in results if r.error]
    log.info("=== sync complete: %d rows, %d errors across %d accounts ===",
             total, len(errs), len(results))
    for r in errs:
        log.warning("  %s (%s): %s", r.ad_account_id, ",".join(r.store_slugs), r.error[:200])


if __name__ == "__main__":
    asyncio.run(main())
