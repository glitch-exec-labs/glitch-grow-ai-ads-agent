"""Run the per-brand Meta audit prompt (playbook Section X → meta_audit)
against a decomposed MetaAccountHierarchy.

Output contract: returns {diagnosis, actions[]} where every action is one
of the four verbs SCALE / REFRESH / PAUSE / WATCH at the correct entity
level (ad / adset / campaign), with rationale and expected_impact tied
to numbers from the decomposition.

Falls back to a minimal hardcoded prompt if the brand's playbook doesn't
carry a meta_audit brief yet — so a fresh install still produces
something useful, just less brand-tuned.
"""
from __future__ import annotations

import json
import logging
import re

from ads_agent.agent.analysis.meta_decomposer import MetaAccountHierarchy
from ads_agent.agent.llm import complete
from ads_agent.playbook import node_brief

log = logging.getLogger(__name__)


_FALLBACK_METHODOLOGY = """\
You are a world-class D2C Meta Ads operator. Audit this account at
campaign / ad-set / ad level. Output actions only: SCALE, REFRESH,
PAUSE, or WATCH. Never say "monitor closely". Four strict verbs.

Pause rule: spend ≥ 3 × target_cpa AND ROAS < breakeven_roas.
Fatigue rule: frequency > 2.5 OR 7d-CTR drop > 30% → REFRESH, not PAUSE.
ASC+ campaigns: judge campaign-level only, no ad drill.
One-ad-carried campaigns: isolate the winner, pause the rest.

Defaults if brand config missing: target_roas=3.0, breakeven_roas=2.0,
assume AOV=₹1000 → target_cpa=₹333 → spend_enough=₹1000.

Output this exact structure:

## PRE-FLIGHT
One paragraph — attribution window, date range, pixel hygiene, ASC+ split.

## ACCOUNT SUMMARY
<one sentence verdict>

## CAMPAIGN TABLE
Markdown table: campaign | type | spend | rev | ROAS | purch | CTR | verdict | reason

## ADS TO PAUSE TODAY
## ADS TO REFRESH
## ADS TO SCALE
## CAMPAIGNS TO PAUSE

## 7-DAY OPERATING PLAN
- pause today (ids)
- refresh this week (concepts)
- scale (ids + ramp mode)
- creative briefs (3-5)

Then the ACTIONS block (one per rule-qualified recommendation):

### {N}. {verb} · {target_label}
- target_level: ad | adset | campaign
- target_id:   <meta id>
- rationale:   <why, with specific numbers>
- expected_impact: <e.g. "save ~₹480/week" or "scale ~2× over 7d">
- safety_check: <what could go wrong, or "none">
"""


def _parse_report(text: str) -> dict:
    """Split the markdown report into (narrative_body, parsed actions list)."""
    # Actions block begins at first `### N. verb · label`
    actions_start = re.search(r"(?m)^###\s*\d+\.", text)
    narrative = text[: actions_start.start()].strip() if actions_start else text.strip()

    actions: list[dict] = []
    for block in re.finditer(
        r"###\s*\d+\.\s*(\S+)\s*·\s*([^\n]+)\n(.*?)(?=\n###\s*\d+\.|\Z)",
        text, re.DOTALL,
    ):
        verb = block.group(1).strip().upper()
        target_label = block.group(2).strip()
        body = block.group(3)

        def _field(name: str) -> str:
            m = re.search(rf"-\s*{re.escape(name)}\s*:\s*(.*?)(?=\n\s*-\s|\Z)",
                          body, re.DOTALL | re.IGNORECASE)
            return m.group(1).strip() if m else ""

        actions.append({
            "action_kind":     verb,
            "target_label":    target_label,
            "target_level":    _field("target_level"),
            "target_id":       _field("target_id"),
            "rationale":       _field("rationale"),
            "expected_impact": _field("expected_impact"),
            "safety_check":    _field("safety_check"),
        })
    return {"diagnosis": narrative, "actions": actions}


async def audit_meta_account(
    hierarchy: MetaAccountHierarchy,
    *,
    brand: str = "ayurpet",
    model_tier: str = "smart",
) -> dict:
    """Run the brand-tuned prompt against the decomposed account.

    Returns {diagnosis, actions} with diagnosis = the full markdown report
    (minus the parsed actions block) so the Telegram/Discord layer can
    just print it, while `actions` stays available for downstream write
    flows.
    """
    methodology = node_brief("meta_audit", brand)
    if not methodology:
        log.warning("no meta_audit brief for brand %r — using fallback", brand)
        methodology = _FALLBACK_METHODOLOGY

    payload = hierarchy.to_dict()
    # Trim creative thumbnail URLs (they can be huge) — not needed for the
    # analyst, only the downstream display layer
    for c in payload.get("campaigns", []):
        for s in c.get("ad_sets", []):
            for a in s.get("ads", []):
                a.pop("creative_thumbnail", None)

    data_block = json.dumps(payload, indent=2, default=str)
    prompt = methodology + "\n\nThe account to analyse (JSON):\n" + data_block

    raw = await complete(
        prompt,
        tier=model_tier,
        max_tokens=16000,
        system=(
            "You are a senior D2C Meta Ads operator. Output ONLY the markdown "
            "report as specified — no preamble, no JSON fences. Every "
            "number you cite must trace to the supplied JSON. If the "
            "pre-flight Pixel hygiene is broken (pixel_hygiene_ok=false), "
            "STOP after the PRE-FLIGHT section and produce no further "
            "recommendations."
        ),
    )
    return _parse_report(raw)
