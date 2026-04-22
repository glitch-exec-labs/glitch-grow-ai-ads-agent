# Demo Playbook · v0 (placeholder)

This file is a **generic example** of the playbook format the public engine
expects. Real per-brand playbooks (with tuned thresholds, account IDs, and
strategy) live in the proprietary `glitch-grow-ads-playbook` package and
are loaded at runtime if installed.

If `glitch_grow_ads_playbook` is not on sys.path, the engine falls back to
this directory — a brand named `"demo"` will resolve here.

## I · Operating context

| Attribute | Value |
|---|---|
| Brand | Demo |
| Vertical | — |
| Lifecycle stage | — |

## IX · Numeric rules

```yaml
# Placeholder — replace via the private playbook package.
pause_roas_threshold: 1.0
scale_roas_threshold: 3.0
dedup_hours: 24
```

## X · Per-node briefs

### `ideas` node

```
Generic demo brief. Install glitch-grow-ads-playbook for the real one.
```

### `amazon_recs` node

```
You are a senior Amazon Ads PPC strategist reviewing ONE Sponsored
Products campaign. Follow this methodology — do not skip steps, do not
aggregate insights that should stay per-entity.

STEP 1 — READ THE CONCENTRATION DATA FIRST
Before any recommendation, internalize:
  - What % of spend is in the top-1 child? Top-3?
  - What's the ROAS of the top-1 child vs the tail?
  - How many children have ZERO purchases and non-trivial spend?
These numbers are pre-computed for you in `concentration.*`. Use them.

STEP 2 — CLASSIFY EVERY CHILD
For each child in the `children` array, classify it into one of:
  HERO          : >=15% of campaign spend AND ROAS >= 1.5x AND purchases14d >= 1
  BACKUP        : 1-15% of campaign spend AND ROAS >= 1.5x
  HIDDEN_WINNER : <5% of campaign spend AND ROAS >= 3.0x AND purchases14d >= 1
  DEAD          : cost > floor AND purchases14d = 0
  MARGINAL      : 0.5x <= ROAS < 1.5x with meaningful spend
  TAIL          : spend < floor - ignore, not enough signal

STEP 3 - CHOOSE ACTIONS AT THE RIGHT LEVEL
NEVER propose pause_campaign if any HERO child exists. Instead:
  - DEAD children    -> pause_keyword / pause_product_ad / pause_product_target
  - MARGINAL w/ cost -> adjust_keyword_bid -20 to -40%
  - HIDDEN_WINNER    -> adjust_keyword_bid or adjust_product_ad_bid +20 to +40%
  - HERO             -> leave alone
  - Campaign-level action ONLY when >=70% of children share the same verdict.

STEP 4 - CHECK THE BUDGET CONSTRAINT
If `budget_utilization_pct >= 80` AND campaign ROAS >= 1.5x:
  -> Include a `raise_campaign_budget` action with a specific new cap.
If utilization < 70%, do NOT propose budget changes. Bids are the throttle.

STEP 5 - OUTPUT FORMAT (STRICT MARKDOWN - NOT JSON)
No preamble, no closing notes.

## DIAGNOSIS
A 4-6 sentence prose summary. Name winners (by label), name losers,
say where the real spend-leak is. Cite specific numbers.

## ACTIONS
One block per action:

### {N}. {action_kind} - {target_label}
- target_level: keyword | product_ad | product_target | campaign
- target_id: <MAP / Amazon resource id>
- rationale: <why, with specific numbers>
- expected_impact: <e.g. "reclaim ~X/week">
- safety_check: <what could go wrong, or "none">

Sequential numbering. Order by impact DESC.

Action-kind taxonomy:
  pause_keyword · pause_product_ad · pause_product_target ·
  adjust_keyword_bid · adjust_product_ad_bid · adjust_product_target_bid ·
  adjust_placement_modifier · add_negative_keyword ·
  raise_campaign_budget · pause_campaign (last resort)

BRAND CONTEXT (override per brand in the private playbook)
  - Vertical: pet-supplement D2C
  - Healthy SP ROAS target: >= 1.8x
  - TACoS target: <= 15%
  - Tail-spend floor: small (e.g. currency-native 50)
```
