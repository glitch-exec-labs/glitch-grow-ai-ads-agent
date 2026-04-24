"""Decompose a Meta ad account into campaign → adset → ad with 14d metrics.

Mirror of `campaign_decomposer.py` (Amazon SP) for Meta. The analyst LLM
consumes a single structured dict that contains:

  account_summary           — totals + blended ROAS
  campaigns[]               — each with:
    metrics, config (ASC+/buying_type/budget), concentration (by ad_set
    spend share), ad_sets[] (each with metrics + ads[])
  pre_flight[]              — hygiene signals: Purchase event counts,
                              attribution window used, window length

Every number here is traceable to a Meta Graph API pull, timestamped.
The analyst is forbidden from inventing figures; if a claim doesn't tie
back to this payload, it's hallucination.
"""
from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from ads_agent.meta.graph_client import (
    account_info,
    ads_for_account_lean,
    adsets_for_account,
    campaigns_for_account,
)

log = logging.getLogger(__name__)


@dataclass
class AdRow:
    ad_id: str
    ad_name: str
    status: str
    effective_status: str
    spend: float
    impressions: int
    clicks: int
    ctr: float
    cpc: float
    cpm: float
    frequency: float
    reach: int
    purchases: int
    purchase_value: float
    roas: float
    days_live: float
    creative_object_type: str = ""
    creative_video_id: str = ""
    creative_thumbnail: str = ""


@dataclass
class AdSetRow:
    adset_id: str
    name: str
    status: str
    effective_status: str
    optimization_goal: str
    billing_event: str
    bid_strategy: str
    daily_budget: float
    spend: float
    impressions: int
    clicks: int
    ctr: float
    cpc: float
    cpm: float
    frequency: float
    reach: int
    purchases: int
    purchase_value: float
    roas: float
    ads: list[AdRow] = field(default_factory=list)


@dataclass
class Concentration:
    n_adsets: int
    n_ads: int
    top_ad_label: str
    top_ad_pct_spend: float
    top_ad_pct_revenue: float
    top_ad_roas: float
    top_3_ads_pct_spend: float
    zero_purchase_ads_count: int
    zero_purchase_ads_spend: float
    carried_by_one_ad: bool  # True if top-1 ad holds ≥70% of campaign revenue


@dataclass
class CampaignRow:
    campaign_id: str
    name: str
    status: str
    effective_status: str
    objective: str
    buying_type: str
    is_asc_plus: bool
    daily_budget: float
    lifetime_budget: float
    currency: str
    spend: float
    impressions: int
    clicks: int
    ctr: float
    cpc: float
    cpm: float
    frequency: float
    reach: int
    purchases: int
    purchase_value: float
    roas: float
    concentration: Concentration | None = None
    ad_sets: list[AdSetRow] = field(default_factory=list)


@dataclass
class AccountSummary:
    ad_account_id: str
    account_name: str
    currency: str
    days: int
    generated_at: str
    n_campaigns: int
    n_adsets: int
    n_ads: int
    spend: float
    impressions: int
    clicks: int
    purchases: int
    purchase_value: float
    blended_roas: float
    blended_ctr: float
    blended_cpc: float


@dataclass
class PreFlight:
    attribution_window: str
    days_window: int
    day_of_week_skew_risk: bool
    purchase_event_count_7d: int
    purchase_event_value_sum_7d: float
    purchase_event_currency_sane: bool
    pixel_hygiene_ok: bool
    asc_plus_campaign_count: int
    manual_campaign_count: int


@dataclass
class MetaAccountHierarchy:
    summary: AccountSummary
    pre_flight: PreFlight
    campaigns: list[CampaignRow] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _mk_concentration(ads: list[AdRow], campaign_revenue: float) -> Concentration:
    live = [a for a in ads if a.spend > 0 or a.impressions > 0]
    n_ads = len(live)
    if not live:
        return Concentration(
            n_adsets=0, n_ads=0, top_ad_label="",
            top_ad_pct_spend=0, top_ad_pct_revenue=0, top_ad_roas=0,
            top_3_ads_pct_spend=0, zero_purchase_ads_count=0,
            zero_purchase_ads_spend=0, carried_by_one_ad=False,
        )
    live_sorted = sorted(live, key=lambda a: a.spend, reverse=True)
    total_spend = sum(a.spend for a in live_sorted) or 1.0
    total_rev = sum(a.purchase_value for a in live_sorted) or 0.0
    top = live_sorted[0]
    top3 = live_sorted[:3]
    zeros = [a for a in live_sorted if a.purchases == 0 and a.spend > 100]
    top_rev_pct = (top.purchase_value / total_rev) if total_rev > 0 else 0.0
    return Concentration(
        n_adsets=0,
        n_ads=n_ads,
        top_ad_label=top.ad_name[:80],
        top_ad_pct_spend=round(100 * top.spend / total_spend, 1),
        top_ad_pct_revenue=round(100 * top_rev_pct, 1),
        top_ad_roas=round(top.roas, 2),
        top_3_ads_pct_spend=round(100 * sum(a.spend for a in top3) / total_spend, 1),
        zero_purchase_ads_count=len(zeros),
        zero_purchase_ads_spend=round(sum(a.spend for a in zeros), 2),
        carried_by_one_ad=(top_rev_pct >= 0.70 and top.purchases >= 1),
    )


async def decompose_meta_account(
    ad_account_id: str, *, days: int = 14,
) -> MetaAccountHierarchy:
    """Three Graph API calls (campaigns + adsets + ads) + one account_info,
    joined in Python. Total runtime typically 2–6s for an account with
    <50 campaigns and <500 ads.
    """
    t0 = time.time()
    info, camp_rows, adset_rows, ad_rows = await _parallel(
        account_info(ad_account_id),
        campaigns_for_account(ad_account_id, days=days),
        adsets_for_account(ad_account_id, days=days),
        ads_for_account_lean(ad_account_id, days=days, limit=1000),
    )

    currency = info.get("currency", "?")

    ads_by_adset: dict[str, list[AdRow]] = {}
    for r in ad_rows:
        ad = AdRow(
            ad_id=r["ad_id"], ad_name=r["ad_name"],
            status="", effective_status="",  # lean pull skips these; fine — audit works off numbers
            spend=r["spend"], impressions=r["impressions"],
            clicks=r["clicks"], ctr=r["ctr"], cpc=r["cpc"], cpm=r["cpm"],
            frequency=r["frequency"], reach=r["reach"],
            purchases=r["purchases"], purchase_value=r["purchase_value"],
            roas=r.get("reported_roas", 0.0),
            days_live=0.0,
        )
        ads_by_adset.setdefault(r.get("adset_id", ""), []).append(ad)

    # Build adset rows
    adsets_by_campaign: dict[str, list[AdSetRow]] = {}
    for r in adset_rows:
        as_row = AdSetRow(
            adset_id=r["adset_id"], name=r["name"],
            status=r["status"], effective_status=r["effective_status"],
            optimization_goal=r["optimization_goal"],
            billing_event=r["billing_event"],
            bid_strategy=r["bid_strategy"],
            daily_budget=r["daily_budget"],
            spend=r["spend"], impressions=r["impressions"],
            clicks=r["clicks"], ctr=r["ctr"], cpc=r["cpc"], cpm=r["cpm"],
            frequency=r["frequency"], reach=r["reach"],
            purchases=r["purchases"], purchase_value=r["purchase_value"],
            roas=r["roas"],
            ads=sorted(
                ads_by_adset.get(r["adset_id"], []),
                key=lambda a: a.spend, reverse=True,
            ),
        )
        adsets_by_campaign.setdefault(r["campaign_id"], []).append(as_row)

    # Build campaign rows with concentration
    campaigns: list[CampaignRow] = []
    for r in camp_rows:
        ad_sets = adsets_by_campaign.get(r["campaign_id"], [])
        # Roll all ads across all ad sets for concentration
        all_ads: list[AdRow] = []
        for s in ad_sets:
            all_ads.extend(s.ads)
        conc = _mk_concentration(all_ads, r["purchase_value"])
        conc.n_adsets = len([s for s in ad_sets if s.spend > 0 or s.impressions > 0])
        campaigns.append(CampaignRow(
            campaign_id=r["campaign_id"], name=r["name"],
            status=r["status"], effective_status=r["effective_status"],
            objective=r["objective"], buying_type=r["buying_type"],
            is_asc_plus=r["is_asc_plus"],
            daily_budget=r["daily_budget"],
            lifetime_budget=r["lifetime_budget"],
            currency=r["currency"] if r["currency"] != "?" else currency,
            spend=r["spend"], impressions=r["impressions"],
            clicks=r["clicks"], ctr=r["ctr"], cpc=r["cpc"], cpm=r["cpm"],
            frequency=r["frequency"], reach=r["reach"],
            purchases=r["purchases"], purchase_value=r["purchase_value"],
            roas=r["roas"],
            concentration=conc,
            ad_sets=sorted(ad_sets, key=lambda s: s.spend, reverse=True),
        ))
    campaigns.sort(key=lambda c: c.spend, reverse=True)

    # Account summary
    total_spend = sum(c.spend for c in campaigns)
    total_rev   = sum(c.purchase_value for c in campaigns)
    total_imp   = sum(c.impressions for c in campaigns)
    total_clicks= sum(c.clicks for c in campaigns)
    total_purch = sum(c.purchases for c in campaigns)
    summary = AccountSummary(
        ad_account_id=ad_account_id,
        account_name=info.get("name", ""),
        currency=currency,
        days=days,
        generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        n_campaigns=len(campaigns),
        n_adsets=sum(len(c.ad_sets) for c in campaigns),
        n_ads=sum(len(s.ads) for c in campaigns for s in c.ad_sets),
        spend=round(total_spend, 2),
        impressions=total_imp,
        clicks=total_clicks,
        purchases=total_purch,
        purchase_value=round(total_rev, 2),
        blended_roas=round(total_rev / total_spend, 2) if total_spend > 0 else 0.0,
        blended_ctr=round(100 * total_clicks / total_imp, 2) if total_imp > 0 else 0.0,
        blended_cpc=round(total_spend / total_clicks, 2) if total_clicks > 0 else 0.0,
    )

    # Pre-flight hygiene
    asc = sum(1 for c in campaigns if c.is_asc_plus)
    pre = PreFlight(
        attribution_window="7d_click (default)",
        days_window=days,
        day_of_week_skew_risk=(days < 7),
        purchase_event_count_7d=total_purch if days <= 7 else -1,  # meaningful only on 7d pulls
        purchase_event_value_sum_7d=round(total_rev, 2) if days <= 7 else -1.0,
        purchase_event_currency_sane=(currency not in ("", "?")),
        pixel_hygiene_ok=(total_purch > 0 and total_rev > 0),
        asc_plus_campaign_count=asc,
        manual_campaign_count=len(campaigns) - asc,
    )

    log.info(
        "meta_decompose: account=%s days=%d → %d campaigns, %d adsets, %d ads in %.1fs",
        ad_account_id, days, summary.n_campaigns, summary.n_adsets, summary.n_ads,
        time.time() - t0,
    )
    return MetaAccountHierarchy(summary=summary, pre_flight=pre, campaigns=campaigns)


async def _parallel(*coros):
    import asyncio
    return await asyncio.gather(*coros)
