"""creative_critique: structured per-ad creative analysis using Gemini vision.

Input:  ad_id
Output: a structured Telegram-markdown message with these sections:
  - Hook           — first-frame / opening framing critique
  - Body           — copy analysis (readability, offer clarity, audience fit)
  - Offer          — what's being promised, how trust is built, CTA quality
  - Audience-fit   — does this creative match the family's target persona
  - Test-next      — 2-3 concrete variants to try

Per-family context (from project memory) is injected into the critique prompt
so the agent judges Mokshya by authentic-brand standards, Urban-family by
dropship standards, etc.
"""
from __future__ import annotations

from ads_agent.agent.llm import complete_vision
from ads_agent.config import get_store
from ads_agent.meta.graph_client import MetaGraphError, creative_details


FAMILY_CONTEXT = {
    "urban": (
        "URBAN FAMILY context: dropshipping store selling high-quality clone replicas "
        "(Prada/Cartier/etc. style) to the Indian market. Legal. COD-heavy; trust signals "
        "(Cash on Delivery, All India Delivery, authentic-looking product) matter more than brand story. "
        "Content is vendor-provided UGC. Average CPC benchmark: $3.50 CAD. Creative churn cadence is fast. "
        "Judge: does the hook grab in <1.5s, is the offer clear, does it trigger impulse buy with trust cues."
    ),
    "storico": "URBAN FAMILY (see urban).",
    "classicoo": "URBAN FAMILY (see urban).",
    "trendsetters": "URBAN FAMILY (see urban).",
    "ayurpet-ind": (
        "AYURPET context: legitimate pet-health/supplement brand. India market. Longer consideration "
        "cycle than dropship; trust + authenticity + product ingredient clarity matter. "
        "Judge: does it build brand equity, is the health claim credible, would a pet owner trust this."
    ),
    "ayurpet-global": (
        "AYURPET (Global storefront): same brand, international pet owners. English copy. "
        "Same criteria but test for clarity across non-Indian audiences."
    ),
    "mokshya": (
        "MOKSHYA context: authentic rudraksha bead mala brand targeting WESTERN SEEKERS "
        "(non-Indian audiences into Hinduism/yoga/meditation/spiritual practice, NOT Indian diaspora). "
        "Copy + visuals should feel authentic, consecrated, sourced-from-Himalaya — never tacky, "
        "never generic spiritual. Judge: is it premium, does it speak to a Western seeker (not Indian-cultural "
        "in-group), does it show proof of authenticity."
    ),
}


CRITIQUE_SYSTEM = """You are a Meta Ads creative director for e-commerce brands.
Given an ad's thumbnail (hook frame), body copy, metrics, and brand context, produce a STRUCTURED critique in this EXACT format:

*Hook*
<2–3 sentences on what the opening frame / first impression does right and wrong. Reference visual composition, text overlays, product framing. Be specific, not generic.>

*Body*
<2–3 sentences on the copy — does it lead with the right thing for this audience, is the offer clear, is the reading order correct, any friction words.>

*Offer*
<2–3 sentences on what's promised, how trust is built (social proof, COD, ingredients, etc.), CTA clarity.>

*Audience-fit*
<2–3 sentences on whether this creative matches the target persona for the given brand family. Be blunt if it's mismatched.>

*Test-next*
<3 bulleted concrete variants to try next. Each one sentence. Name the change (e.g. "Swap thumbnail to clean single-product framing against white backdrop") and why (e.g. "reduce cognitive load from current cluttered multi-product grid").>

Rules:
- Cite the metrics explicitly when they support your critique (CTR below 1%, CPC above benchmark, etc.).
- Don't hedge. If the creative is dying, say so.
- Match tone to the brand family context — don't critique a dropship ad by brand-purist standards and vice-versa.
- No preamble, no summary at the end. Start with *Hook* and end with *Test-next*.
"""


async def creative_critique_node(state: dict) -> dict:
    ad_id = state.get("ad_id") or ""
    if not ad_id:
        return {**state, "reply_text": "usage: /creative <ad_id>"}

    # The store this ad belongs to — we don't know directly, so we pass slug through state if available
    slug = state.get("store_slug", "")
    store = get_store(slug) if slug else None

    try:
        d = await creative_details(ad_id, days=7)
    except MetaGraphError as e:
        return {**state, "reply_text": f"Couldn't fetch ad `{ad_id}`: {e}"}

    creative = d.get("creative", {})
    thumbnail = creative.get("thumbnail_url") or creative.get("image_url") or ""
    body = (creative.get("body") or "").strip() or "(no body copy)"
    title = (creative.get("title") or "").strip()
    object_type = creative.get("object_type", "UNKNOWN")

    # Metrics for the prompt
    metrics_block = (
        f"Ad: {d['ad_name']}\n"
        f"Status: {d.get('effective_status') or d.get('status')}\n"
        f"Media type: {object_type}  (note: full video content not accessible; thumbnail only)\n"
        f"Last 7d: spend {d['spend']:,.2f} {d['currency']}  ·  "
        f"impressions {d['impressions']:,}  ·  clicks {d['clicks']:,}  ·  "
        f"CTR {d['ctr']:.2f}%  ·  CPC {d['cpc']:.2f}  ·  CPM {d['cpm']:.2f}  ·  "
        f"frequency {d['frequency']:.2f}  ·  reach {d['reach']:,}\n"
        f"Meta-reported: purchases {d['purchases']}  ·  purchase value {d['purchase_value']:,.2f}  ·  "
        f"ROAS {d['reported_roas']:.2f}x\n"
    )

    family_ctx = FAMILY_CONTEXT.get(slug, "No specific brand family context available — judge by general e-commerce standards.")

    prompt = (
        f"{family_ctx}\n\n"
        f"{metrics_block}\n"
        f"Title: {title}\n"
        f"Body copy (verbatim):\n\"\"\"\n{body}\n\"\"\"\n\n"
        "Produce the structured critique now."
    )

    images = [thumbnail] if thumbnail else []
    if not images:
        # Fallback to text-only if no thumbnail
        from ads_agent.agent.llm import complete
        out = await complete(prompt, tier="smart", system=CRITIQUE_SYSTEM, max_tokens=3000)
    else:
        # max_tokens=3000 covers Gemini 2.5's "thinking" token budget plus ~1500 output chars.
        out = await complete_vision(prompt, images, tier="smart", system=CRITIQUE_SYSTEM, max_tokens=3000)

    header = (
        f"*Creative critique · ad `{ad_id}`*\n"
        f"{d['ad_name']}\n\n"
    )
    return {**state, "reply_text": header + out}
