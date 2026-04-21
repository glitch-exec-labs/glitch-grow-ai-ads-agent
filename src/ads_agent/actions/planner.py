"""Planner — scans live Meta data and emits ActionProposals.

Runs every 4 hours. For each enabled store:
  1. Fetch active adsets + spend + purchase_roas (last 14d) from Meta Graph API.
  2. Apply the configured RULES to find pause / budget-change candidates.
  3. Dedup against existing pending/approved/executed actions in the last
     DEDUP_HOURS — never re-propose the same target_id twice within that
     window. Rows with status IN ('notify_failed','expired') are excluded
     from dedup so a Telegram outage or TTL can't black-hole a target.
  4. Persist survivors as pending_approval rows via notifier.post_proposal —
     notifier then sends the Telegram approval prompt.

## Public engine / private playbook split

The **orchestration** lives here in the public repo (fetching Meta data,
dedup, posting proposals, handling notify_failed). The **calibrated
business logic** — which rules fire, what thresholds they use, what
rationale copy appears in the Telegram approval prompt — lives in the
private package `glitch_grow_ads_playbook`.

At import time we try to load RULES + DEDUP_HOURS from the playbook and
fall back to the generic stub (`ads_agent.actions.rules_stub`) if the
playbook isn't installed. That keeps this repo runnable end-to-end for
a public cloner while keeping the tuned numbers proprietary.

See: https://github.com/glitch-exec-labs/glitch-grow-ads-agent-private
"""
from __future__ import annotations

import json
import logging
import os
from typing import Callable

import asyncpg
import httpx

from ads_agent.actions.models import ActionProposal, AYURPET_CHAT_ID
from ads_agent.actions.notifier import TelegramNotifyError, post_proposal

log = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.facebook.com/v21.0"


# ---------------------------------------------------------------------------
# Rule set resolution — private playbook first, generic stub as fallback
# ---------------------------------------------------------------------------
try:
    from glitch_grow_ads_playbook.rules import (  # type: ignore[import-not-found]
        DEDUP_HOURS,
        RULES,
    )
    _RULE_SOURCE = "glitch_grow_ads_playbook (private, tuned)"
except ImportError:
    from ads_agent.actions.rules_stub import DEDUP_HOURS, RULES  # noqa: F401
    _RULE_SOURCE = "rules_stub (public demo — calibration not installed)"

log.info("planner: loaded %d rule(s) from %s", len(RULES), _RULE_SOURCE)


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

            for rule in RULES:
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
                    log.warning(
                        "notify failed for %s (will retry next tick): %s",
                        r["adset_id"], e,
                    )
                    break
                except Exception as e:
                    log.exception("post_proposal failed for %s: %s", r["adset_id"], e)
    return posted
