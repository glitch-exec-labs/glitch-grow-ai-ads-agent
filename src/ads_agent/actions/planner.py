"""Planner — scans live Meta data and emits ActionProposals.

Runs every 4 hours. For each enabled store:
  1. Fetch active adsets + spend + purchase_roas (last 14d) from Meta Graph API.
  2. Apply rules to find pause / budget-change candidates.
  3. Dedup against existing pending/approved/executed actions in the last 72h —
     we never re-propose the same target_id twice within that window.
  4. Persist survivors as pending_approval rows via notifier.post_proposal —
     notifier then sends the Telegram approval prompt.

V1 rule set (conservative — every action still requires human approval):

  R1. Pause if 14d spend > ₹5,000 AND purchase_roas < 0.9
        → evidence: spend_14d, roas_14d; expected_impact: monthly ₹ saved
  R2. Pause if 14d spend > ₹3,000 AND clicks > 500 AND purchase_roas is null
        → adset burning on traffic with zero tracked conversions
  R3. Scale budget +30% if 14d spend > ₹20,000 AND purchase_roas > 2.0
        → expected_impact: incremental monthly ₹ at current ROAS × 1.3

The rules are deliberately tight — better to under-propose than spam the
Telegram group. Once trust builds, thresholds relax in v2.1.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, timedelta, timezone, datetime
from typing import Any

import asyncpg
import httpx

from ads_agent.actions.models import ActionProposal, AYURPET_CHAT_ID
from ads_agent.actions.notifier import TelegramNotifyError, post_proposal

log = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.facebook.com/v21.0"

# Thresholds (INR)
PAUSE_SPEND_MIN      = 5000   # only flag adsets that actually spent meaningfully
PAUSE_ROAS_CEIL      = 0.9    # hard kill — losing money
NOSIGNAL_SPEND_MIN   = 3000
NOSIGNAL_CLICKS_MIN  = 500
SCALE_SPEND_MIN      = 20000
SCALE_ROAS_FLOOR     = 2.0
SCALE_MULTIPLIER     = 1.3

# Dedup window — don't re-propose the same target within this many hours
DEDUP_HOURS          = 72


def _meta_token() -> str:
    tok = os.environ.get("META_ACCESS_TOKEN", "").strip()
    if not tok:
        raise RuntimeError("META_ACCESS_TOKEN not set")
    return tok


def _store_to_account(store_slug: str) -> list[str]:
    """Map store slug → Meta ad account IDs. Reads STORE_AD_ACCOUNTS_JSON."""
    raw = os.environ.get("STORE_AD_ACCOUNTS_JSON", "").strip()
    if not raw:
        return []
    try:
        m = json.loads(raw)
    except Exception:
        return []
    return list(m.get(store_slug, []))


async def _fetch_adset_snapshot(ad_account_id: str) -> list[dict]:
    """Pull last-14-day adset-level spend + purchase_roas from Meta Graph API."""
    async with httpx.AsyncClient(timeout=60.0) as c:
        # insights with purchase_roas (omni_purchase)
        ins = (await c.get(
            f"{GRAPH_BASE}/{ad_account_id}/insights",
            params={
                "level": "adset",
                "date_preset": "last_14d",
                "fields": "adset_id,adset_name,campaign_name,spend,clicks,impressions,purchase_roas",
                "limit": 500,
                "access_token": _meta_token(),
            },
        )).json().get("data", [])

        if not ins:
            return []

        # Metadata for each adset (effective_status, daily_budget)
        ids = [r["adset_id"] for r in ins]
        meta_by_id: dict[str, dict] = {}
        CHUNK = 30
        for i in range(0, len(ids), CHUNK):
            chunk = ids[i:i + CHUNK]
            body = (await c.get(
                f"{GRAPH_BASE}/",
                params={
                    "ids": ",".join(chunk),
                    "fields": "id,name,effective_status,daily_budget,lifetime_budget,campaign{name}",
                    "access_token": _meta_token(),
                },
            )).json()
            for k, v in body.items():
                if isinstance(v, dict) and v.get("id"):
                    meta_by_id[v["id"]] = v

    rows: list[dict] = []
    for r in ins:
        m = meta_by_id.get(r["adset_id"], {})
        eff = m.get("effective_status", "UNKNOWN")
        # Skip: archived/deleted (obvious) AND campaign-paused (pausing an
        # already-effectively-paused adset would be a no-op). Keep adset-level
        # PAUSED because the planner may want to RESUME it.
        if eff not in ("ACTIVE", "ADSET_PAUSED", "PAUSED"):
            continue
        if eff == "CAMPAIGN_PAUSED":
            continue  # won't consider until campaign is un-paused
        roas = None
        for pr in r.get("purchase_roas", []) or []:
            if pr.get("action_type") == "omni_purchase":
                roas = float(pr.get("value", 0) or 0)
        rows.append({
            "adset_id":      r["adset_id"],
            "adset_name":    r.get("adset_name"),
            "campaign_name": r.get("campaign_name"),
            "spend_14d":     float(r.get("spend", 0) or 0),
            "clicks_14d":    int(r.get("clicks", 0) or 0),
            "impressions_14d": int(r.get("impressions", 0) or 0),
            "roas":          roas,
            "effective_status": eff,
            "daily_budget":  int(m.get("daily_budget") or 0),  # Meta returns minor units (paise)
        })
    return rows


async def _recent_targets(pool: asyncpg.Pool, hours: int = DEDUP_HOURS) -> set[str]:
    """Return set of target_object_id strings with a still-relevant action row
    created within N hours.

    Issue #6: rows with status='notify_failed' represent proposals where the
    database row exists but no human ever saw the approval prompt. Those
    MUST NOT block re-proposal — otherwise a transient Telegram outage can
    black-hole a target for 72 hours. We exclude them here so the next
    planner tick gets another shot at posting. Same rationale for 'expired'
    rows (human never acted, TTL elapsed).
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT DISTINCT target_object_id
               FROM ads_agent.agent_actions
               WHERE created_at > NOW() - ($1 || ' hours')::interval
                 AND status NOT IN ('notify_failed', 'expired')""",
            str(hours),
        )
    return {r["target_object_id"] for r in rows}


def _rule_pause(r: dict) -> ActionProposal | None:
    """R1 + R2: pause losing adsets or zero-signal burners."""
    if r["effective_status"] not in ("ACTIVE",):
        return None  # already paused

    spend = r["spend_14d"]
    roas = r["roas"]
    clicks = r["clicks_14d"]

    losing = spend > PAUSE_SPEND_MIN and roas is not None and roas < PAUSE_ROAS_CEIL
    nosignal = spend > NOSIGNAL_SPEND_MIN and clicks > NOSIGNAL_CLICKS_MIN and roas is None

    if not (losing or nosignal):
        return None

    if losing:
        rationale = (
            f"Losing money at scale: ₹{spend:,.0f} spend in last 14 days at "
            f"{roas:.2f}× Meta-reported ROAS. Threshold is < 0.9× on > ₹5,000 spend. "
            f"Pausing to stop the bleed; evaluate creative/targeting before relaunch."
        )
    else:
        rationale = (
            f"Zero tracked purchases on ₹{spend:,.0f} spend and {clicks:,} clicks in "
            f"last 14 days. Either the pixel isn't firing, or this adset is generating "
            f"click traffic with no buyer intent. Pausing is the safe move."
        )

    # Expected impact: monthly ₹ reclaimed if pause holds
    monthly_reclaim = spend * (30.0 / 14.0)

    return ActionProposal(
        store_slug=r.get("_store_slug", "unknown"),
        action_kind="pause_adset",
        target_object_id=r["adset_id"],
        target_object_name=(r["adset_name"] or r["adset_id"])[:60],
        rationale=rationale,
        params={},
        evidence={
            "spend_14d_inr":  f"₹{spend:,.0f}",
            "roas_14d":       f"{roas:.2f}×" if roas is not None else "—",
            "clicks_14d":     f"{clicks:,}",
            "campaign":       r.get("campaign_name") or "",
        },
        expected_impact={
            "monthly_budget_reclaimed": f"₹{monthly_reclaim:,.0f}",
            "revenue_at_risk_if_wrong": f"₹{spend * (roas or 0):,.0f} / 14d (refundable via resume_adset)",
        },
    )


def _rule_scale(r: dict) -> ActionProposal | None:
    """R3: raise daily budget on over-performers."""
    if r["effective_status"] != "ACTIVE":
        return None
    spend, roas, db = r["spend_14d"], r["roas"], r["daily_budget"]
    if spend < SCALE_SPEND_MIN or not roas or roas < SCALE_ROAS_FLOOR or db == 0:
        return None

    new_budget = int(db * SCALE_MULTIPLIER)
    incremental_monthly = (new_budget - db) / 100.0 * 30 * roas

    return ActionProposal(
        store_slug=r.get("_store_slug", "unknown"),
        action_kind="update_adset_budget",
        target_object_id=r["adset_id"],
        target_object_name=(r["adset_name"] or r["adset_id"])[:60],
        rationale=(
            f"Strong performer: ₹{spend:,.0f} spend in last 14d at {roas:.2f}× ROAS, "
            f"well above 2.0× scale threshold. Raising daily budget by 30% to "
            f"capture more of this demand; watch for ROAS decay over next 7 days."
        ),
        params={"new_daily_budget": new_budget, "old_daily_budget": db},
        evidence={
            "spend_14d_inr":  f"₹{spend:,.0f}",
            "roas_14d":       f"{roas:.2f}×",
            "current_daily_budget_inr": f"₹{db/100:,.0f}",
            "campaign":       r.get("campaign_name") or "",
        },
        expected_impact={
            "expected_incremental_monthly_revenue": f"₹{incremental_monthly:,.0f}",
            "expected_incremental_monthly_spend":   f"₹{(new_budget - db)/100*30:,.0f}",
        },
    )


async def plan_for_store(pool: asyncpg.Pool, store_slug: str, chat_id: int) -> int:
    """Generate + post proposals for one store. Returns count posted."""
    recent = await _recent_targets(pool)
    posted = 0
    for acct in _store_to_account(store_slug):
        try:
            snapshot = await _fetch_adset_snapshot(acct)
        except Exception as e:
            log.warning("snapshot fetch failed for %s: %s", acct, e)
            continue

        for r in snapshot:
            r["_store_slug"] = store_slug
            if r["adset_id"] in recent:
                continue  # dedup

            for rule in (_rule_pause, _rule_scale):
                prop = rule(r)
                if prop is None:
                    continue
                try:
                    await post_proposal(pool, prop, chat_id)
                    posted += 1
                    recent.add(r["adset_id"])  # don't double-propose same target
                    break  # one proposal per adset per planner run
                except TelegramNotifyError as e:
                    # Row exists as 'notify_failed' — do NOT add to `recent`
                    # so the next planner tick can retry. Issue #6.
                    log.warning("notify failed for %s (will retry next tick): %s",
                                r["adset_id"], e)
                    break
                except Exception as e:
                    log.exception("post_proposal failed for %s: %s", r["adset_id"], e)
    return posted
