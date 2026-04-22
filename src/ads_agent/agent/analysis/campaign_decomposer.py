"""Decompose an Amazon SP campaign into its full child hierarchy with
14-day metrics per child, then compute concentration ratios.

Output shape is designed to be fed directly into an LLM prompt. Every
field name is human-readable so the analyst LLM can read it verbatim.

Hierarchy we expose:
    campaign
      ├── ad_group
      │     ├── keyword  (text, match_type, bid, 14d metrics)
      │     └── product_target  (expression, bid, 14d metrics)
      └── ad_group  …

Plus:
    concentration: summary of who's burning the spend
      - top_child_pct_spend           (spend share of #1 child)
      - top_3_children_pct_spend
      - tail_count                     (# children in bottom 20% spend)
      - tail_pct_spend                 (total spend share of tail)
      - tail_roas                      (aggregate ROAS of tail)

Data source: MAP's `list_resources` for structure + `ask_report_analyst`
for metrics. One analyst call per campaign, batched.

This decomposer is Amazon-specific for v1. A Meta equivalent would pull
from Graph API; shares the same output schema.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from typing import Any

from ads_agent.map.mcp_client import MapMcpError, ask_analyst, call_tool as map_call

log = logging.getLogger(__name__)


@dataclass
class Metrics14d:
    """14-day performance for any entity in the hierarchy."""
    cost: float = 0.0
    sales14d: float = 0.0
    purchases14d: int = 0
    clicks: int = 0
    impressions: int = 0

    @property
    def roas(self) -> float:
        return (self.sales14d / self.cost) if self.cost > 0 else 0.0

    @property
    def acos_pct(self) -> float:
        return (self.cost / self.sales14d * 100) if self.sales14d > 0 else float("inf")

    @property
    def ctr_pct(self) -> float:
        return (self.clicks / self.impressions * 100) if self.impressions > 0 else 0.0


@dataclass
class Child:
    """A keyword, product_target, or product_ad — any leaf in the tree."""
    kind: str                     # "keyword" | "product_target" | "product_ad"
    id: str
    label: str                    # human-readable: keyword text, ASIN, expression
    match_type: str | None = None  # EXACT | PHRASE | BROAD | ... (keywords only)
    state: str = "enabled"
    bid: float | None = None
    ad_group_id: str = ""
    ad_group_name: str = ""
    metrics: Metrics14d = field(default_factory=Metrics14d)
    pct_of_campaign_spend: float = 0.0
    pct_of_campaign_sales: float = 0.0


@dataclass
class AdGroup:
    id: str
    name: str
    state: str
    metrics: Metrics14d = field(default_factory=Metrics14d)
    children: list[Child] = field(default_factory=list)


@dataclass
class Campaign:
    id: str
    name: str
    state: str
    bidding_strategy: str
    daily_budget: float
    placement_modifiers: list[dict] = field(default_factory=list)
    metrics: Metrics14d = field(default_factory=Metrics14d)
    actual_avg_daily_spend: float = 0.0

    @property
    def utilization_pct(self) -> float:
        if not self.daily_budget:
            return 0.0
        return self.actual_avg_daily_spend / self.daily_budget * 100


@dataclass
class Concentration:
    """Pre-computed so the LLM doesn't have to calculate it itself."""
    n_children: int = 0
    n_active_children: int = 0
    top_child_pct_spend: float = 0.0
    top_child_label: str = ""
    top_child_roas: float = 0.0
    top_3_children_pct_spend: float = 0.0
    tail_count: int = 0          # children in the bottom 20% of spend
    tail_pct_spend: float = 0.0
    tail_roas: float = 0.0
    zero_purchase_children_count: int = 0
    zero_purchase_children_spend: float = 0.0


@dataclass
class CampaignHierarchy:
    campaign: Campaign
    ad_groups: list[AdGroup] = field(default_factory=list)
    flat_children: list[Child] = field(default_factory=list)  # denormalized for convenience
    concentration: Concentration = field(default_factory=Concentration)

    def to_dict(self) -> dict:
        """Serialize for prompt injection or JSON transport."""
        out = {
            "campaign": {
                "id": self.campaign.id,
                "name": self.campaign.name,
                "state": self.campaign.state,
                "bidding_strategy": self.campaign.bidding_strategy,
                "daily_budget": self.campaign.daily_budget,
                "actual_avg_daily_spend_14d": round(self.campaign.actual_avg_daily_spend, 2),
                "budget_utilization_pct": round(self.campaign.utilization_pct, 1),
                "placement_modifiers": self.campaign.placement_modifiers,
                "metrics_14d": {
                    "cost": round(self.campaign.metrics.cost, 2),
                    "sales14d": round(self.campaign.metrics.sales14d, 2),
                    "purchases14d": self.campaign.metrics.purchases14d,
                    "clicks": self.campaign.metrics.clicks,
                    "impressions": self.campaign.metrics.impressions,
                    "roas": round(self.campaign.metrics.roas, 2),
                    "acos_pct": round(self.campaign.metrics.acos_pct, 1),
                    "ctr_pct": round(self.campaign.metrics.ctr_pct, 2),
                },
            },
            "ad_groups": [
                {
                    "id": ag.id, "name": ag.name, "state": ag.state,
                    "metrics_14d": asdict(ag.metrics),
                    "child_count": len(ag.children),
                }
                for ag in self.ad_groups
            ],
            "children": [
                {
                    "kind": c.kind,
                    "id": c.id,
                    "label": c.label,
                    "match_type": c.match_type,
                    "state": c.state,
                    "bid": c.bid,
                    "ad_group": c.ad_group_name,
                    "cost_14d": round(c.metrics.cost, 2),
                    "sales14d": round(c.metrics.sales14d, 2),
                    "purchases14d": c.metrics.purchases14d,
                    "clicks": c.metrics.clicks,
                    "impressions": c.metrics.impressions,
                    "roas_14d": round(c.metrics.roas, 2),
                    "acos_pct": round(c.metrics.acos_pct, 1) if c.metrics.acos_pct != float("inf") else None,
                    "pct_of_campaign_spend": round(c.pct_of_campaign_spend, 1),
                    "pct_of_campaign_sales": round(c.pct_of_campaign_sales, 1),
                }
                for c in self.flat_children
            ],
            "concentration": asdict(self.concentration),
        }
        return out


# --- Fetch helpers ----------------------------------------------------------

async def _list_resource(integration_id: str, account_id: str,
                         resource_type: str, filters: dict) -> list[dict]:
    """Thin wrapper around MAP's list_resources with MAP's required
    filters-in-filters shape."""
    try:
        data, gated = await map_call("list_resources", {
            "integration_id": integration_id,
            "account_id": account_id,
            "resource_type": resource_type,
            "filters": filters,
        })
        if gated:
            log.warning("MAP list_resources %s plan-gated", resource_type)
            return []
        if isinstance(data, dict) and data.get("error"):
            log.warning("MAP list_resources %s error: %s", resource_type, data["error"])
            return []
        return (data or {}).get("items", []) if isinstance(data, dict) else []
    except MapMcpError as e:
        log.warning("MAP list_resources %s failed: %s", resource_type, e)
        return []


async def _metrics_per_child(integration_id: str, account_id: str,
                             campaign_id: str, days: int) -> tuple[list[dict], list[dict]]:
    """Ask MAP's analyst for AGGREGATED keyword-level + ASIN-level 14d metrics.

    Critical: the analyst defaults to per-day rows. We MUST demand
    aggregation over the date window explicitly, or we'll sum daily
    fragments as if they were per-entity totals and get bogus numbers.

    Returns (keyword_rows, product_ad_rows):
      keyword_rows — one row per (keyword_id | targeting_expression, match_type)
      product_ad_rows — one row per (ad_id, asin)
    """
    from datetime import date, timedelta
    end = date.today()
    start = end - timedelta(days=days)

    q_keywords = (
        f"For campaignId={campaign_id}, date range {start} to {end}, "
        f"AGGREGATE by (keyword, matchType) across the entire window — "
        f"one row per unique bid target. Include both match-typed keywords "
        f"(EXACT/PHRASE/BROAD) AND targeting expressions. Return columns: "
        f"keyword, matchType, adGroupName, adGroupId, keywordBid, "
        f"SUM(cost), SUM(sales14d), SUM(purchases14d), SUM(clicks), "
        f"SUM(impressions). Exclude rows with zero cost. Sort by SUM(cost) "
        f"descending. Return compact structured data."
    )
    q_ads = (
        f"For campaignId={campaign_id}, date range {start} to {end}, "
        f"AGGREGATE by (advertisedAsin, adId) across the entire window. "
        f"Return columns: advertisedAsin, adId, adGroupName, adGroupId, "
        f"SUM(cost), SUM(sales14d), SUM(purchases14d), SUM(clicks), "
        f"SUM(impressions). Exclude zero-cost rows. Sort by SUM(cost) desc. "
        f"Structured data only."
    )

    async def _one(q: str, label: str) -> list[dict]:
        try:
            data = await ask_analyst(integration_id, account_id, q)
        except MapMcpError as e:
            log.warning("analyst %s failed: %s", label, e)
            return []
        if data.get("_plan_gated"):
            return []
        return data.get("data", []) if isinstance(data, dict) else []

    kw_rows  = await _one(q_keywords, "keywords")
    ad_rows  = await _one(q_ads,      "product_ads")
    return kw_rows, ad_rows


def _build_children_from_rows(
    rows: list[dict], ag_index: dict[str, AdGroup],
) -> list[Child]:
    """Turn analyst rows into typed Child objects + attach to ad groups."""
    out: list[Child] = []
    for r in rows:
        kw   = (r.get("keyword_text") or r.get("keyword") or "").strip()
        mt   = (r.get("match_type") or "").strip()
        expr = (r.get("targeting_expression") or r.get("target_expression") or "").strip()
        asin = (r.get("asin") or r.get("advertised_asin") or "").strip()

        # Decide which kind of child this row represents
        if kw and mt and not mt.upper().startswith("TARGETING"):
            kind, label, mt_out = "keyword", kw, mt.upper()
        elif expr or (mt and mt.upper().startswith("TARGETING")):
            kind, label, mt_out = "product_target", (expr or kw or "(expression)"), mt.upper()
        elif asin:
            kind, label, mt_out = "product_ad", asin, None
        else:
            continue  # junk row

        m = Metrics14d(
            cost         = float(r.get("cost") or 0),
            sales14d     = float(r.get("sales14d") or r.get("sales") or 0),
            purchases14d = int(float(r.get("purchases14d") or r.get("purchases") or 0)),
            clicks       = int(float(r.get("clicks") or 0)),
            impressions  = int(float(r.get("impressions") or 0)),
        )
        ag_id   = str(r.get("ad_group_id") or "")
        ag_name = (r.get("ad_group_name") or "").strip()
        bid     = float(r["bid"]) if r.get("bid") not in (None, "") else None

        child = Child(
            kind=kind, id=str(r.get("keyword_id") or r.get("target_id") or r.get("ad_id") or label),
            label=label, match_type=mt_out,
            state=(r.get("state") or "enabled"),
            bid=bid,
            ad_group_id=ag_id, ad_group_name=ag_name,
            metrics=m,
        )
        out.append(child)

        # Attach to its ad group if we have the index
        if ag_id and ag_id in ag_index:
            ag_index[ag_id].children.append(child)

    return out


def _compute_ad_group_metrics(ad_groups: list[AdGroup]) -> None:
    """Aggregate child metrics into per-ad-group totals."""
    for ag in ad_groups:
        agg = Metrics14d()
        for c in ag.children:
            agg.cost         += c.metrics.cost
            agg.sales14d     += c.metrics.sales14d
            agg.purchases14d += c.metrics.purchases14d
            agg.clicks       += c.metrics.clicks
            agg.impressions  += c.metrics.impressions
        ag.metrics = agg


def _compute_concentration(campaign_metrics: Metrics14d,
                           children: list[Child]) -> Concentration:
    """Distill the spend-share + tail structure into a few numbers."""
    active = [c for c in children if c.metrics.cost > 0]
    total_cost = sum(c.metrics.cost for c in active) or 1.0
    # Sort by cost descending
    by_cost = sorted(active, key=lambda c: c.metrics.cost, reverse=True)

    # Share of #1 and top-3
    top1 = (by_cost[0].metrics.cost / total_cost * 100) if by_cost else 0.0
    top3 = (sum(c.metrics.cost for c in by_cost[:3]) / total_cost * 100) if by_cost else 0.0

    # Tail = children in bottom 20% of total spend
    sorted_asc = sorted(active, key=lambda c: c.metrics.cost)
    cum = 0.0
    tail_boundary = total_cost * 0.20
    tail: list[Child] = []
    for c in sorted_asc:
        if cum + c.metrics.cost > tail_boundary:
            break
        tail.append(c)
        cum += c.metrics.cost
    tail_cost  = sum(c.metrics.cost for c in tail)
    tail_sales = sum(c.metrics.sales14d for c in tail)
    tail_roas  = (tail_sales / tail_cost) if tail_cost > 0 else 0.0

    # Zero-purchase children with meaningful spend
    zero_purch = [c for c in active if c.metrics.purchases14d == 0]
    zero_purch_spend = sum(c.metrics.cost for c in zero_purch)

    return Concentration(
        n_children=len(children),
        n_active_children=len(active),
        top_child_pct_spend=round(top1, 1),
        top_child_label=by_cost[0].label if by_cost else "",
        top_child_roas=round(by_cost[0].metrics.roas, 2) if by_cost else 0.0,
        top_3_children_pct_spend=round(top3, 1),
        tail_count=len(tail),
        tail_pct_spend=round(tail_cost / total_cost * 100, 1),
        tail_roas=round(tail_roas, 2),
        zero_purchase_children_count=len(zero_purch),
        zero_purchase_children_spend=round(zero_purch_spend, 2),
    )


def _attach_child_spend_shares(campaign_metrics: Metrics14d,
                               children: list[Child]) -> None:
    if campaign_metrics.cost > 0:
        for c in children:
            c.pct_of_campaign_spend = c.metrics.cost / campaign_metrics.cost * 100
    if campaign_metrics.sales14d > 0:
        for c in children:
            c.pct_of_campaign_sales = c.metrics.sales14d / campaign_metrics.sales14d * 100


# --- Public entry point -----------------------------------------------------

async def decompose_sp_campaign(
    *, integration_id: str, account_id: str, campaign_id: str, days: int = 14,
) -> CampaignHierarchy:
    """Fetch + decompose one SP campaign into a CampaignHierarchy.

    Makes 3 MAP calls:
      1. list_resources sp_campaigns  → campaign metadata (filter by id)
      2. list_resources sp_ad_groups   → ad-group metadata
      3. ask_report_analyst            → per-child 14-day metrics + campaign totals

    Returns a fully-populated CampaignHierarchy. Missing data → empty
    metrics rather than raising, so partial results are still useful.
    """
    # 1. Campaign metadata — we fetch all enabled + filter client-side
    # (MAP's campaign_id filter on list_resources is inconsistent).
    all_camps = await _list_resource(integration_id, account_id,
                                     "sp_campaigns", {"state_filter": "ENABLED"})
    camp_raw = next((c for c in all_camps if str(c.get("campaignId")) == campaign_id), None)
    if not camp_raw:
        # Try without state filter in case it's paused
        all_camps = await _list_resource(integration_id, account_id,
                                         "sp_campaigns", {})
        camp_raw = next((c for c in all_camps if str(c.get("campaignId")) == campaign_id), None)

    if not camp_raw:
        raise ValueError(f"campaign {campaign_id} not found in account {account_id}")

    budget_obj = camp_raw.get("budget") or {}
    bidding = (camp_raw.get("dynamicBidding") or {}).get("strategy", "?")
    placement_mods = (camp_raw.get("dynamicBidding") or {}).get("placementBidding", [])
    campaign = Campaign(
        id=str(camp_raw["campaignId"]),
        name=camp_raw.get("name", "?"),
        state=camp_raw.get("state", "?"),
        bidding_strategy=bidding,
        daily_budget=float(budget_obj.get("budget", 0) or 0),
        placement_modifiers=placement_mods,
    )

    # 2. Ad groups
    ag_raw = await _list_resource(integration_id, account_id, "sp_ad_groups",
                                  {"campaign_id": campaign_id})
    ad_groups = [
        AdGroup(
            id=str(ag.get("adGroupId", "")),
            name=ag.get("name", "?"),
            state=ag.get("state", "?"),
        )
        for ag in ag_raw
    ]
    ag_index = {ag.id: ag for ag in ad_groups}

    # 3. Per-child metrics via analyst
    rows = await _metrics_per_child(integration_id, account_id, campaign_id, days)

    # If analyst didn't give us rows, we still return a valid hierarchy
    # (structure without metrics) so the caller sees empty metrics rather
    # than a crash.
    if not rows:
        log.warning("campaign %s has no child metrics from analyst", campaign_id)

    children = _build_children_from_rows(rows, ag_index)

    # Derive campaign-level metrics by summing children
    cm = Metrics14d()
    for c in children:
        cm.cost         += c.metrics.cost
        cm.sales14d     += c.metrics.sales14d
        cm.purchases14d += c.metrics.purchases14d
        cm.clicks       += c.metrics.clicks
        cm.impressions  += c.metrics.impressions
    campaign.metrics = cm
    campaign.actual_avg_daily_spend = cm.cost / days if days > 0 else 0

    _compute_ad_group_metrics(ad_groups)
    _attach_child_spend_shares(campaign.metrics, children)
    conc = _compute_concentration(campaign.metrics, children)

    return CampaignHierarchy(
        campaign=campaign,
        ad_groups=ad_groups,
        flat_children=children,
        concentration=conc,
    )
