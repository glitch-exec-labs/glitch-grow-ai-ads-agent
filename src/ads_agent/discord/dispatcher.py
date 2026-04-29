"""Parse a Discord message into an agent state dict, invoke the graph, return reply.

Recognised commands mirror the Telegram handler surface, minus a few that
need interactive callbacks (plan approval buttons) — those are Telegram-only
for now.

Argument syntax:
  /cmd arg1 arg2 key=value "quoted string arg" key2="quoted value"

Free-form (non-command) messages are acknowledged but not dispatched, to
avoid the agent spamming on every chat reaction.
"""
from __future__ import annotations

import logging
import shlex
from typing import Any

from ads_agent.agent.graph import build_graph
from ads_agent.config import STORES, get_store

log = logging.getLogger(__name__)

# Lazy-built to keep import cheap (graph pulls LLM clients etc.)
_graph = None


def _g():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


def _split_args(body: str) -> tuple[list[str], dict[str, str]]:
    """Split 'a b c k1=v1 k2="v with space"' into (positional, kv)."""
    try:
        parts = shlex.split(body)
    except ValueError:
        parts = body.split()
    pos: list[str] = []
    kv: dict[str, str] = {}
    for p in parts:
        if "=" in p and not p.startswith("="):
            k, _, v = p.partition("=")
            kv[k.strip().lower()] = v.strip()
        else:
            pos.append(p)
    return pos, kv


def _help_text() -> str:
    return (
        "**ads-agent · Discord commands**\n"
        "• `/help` — this message\n"
        "• `/stores` — list configured stores\n"
        "• `/insights <store> [days]`\n"
        "• `/roas <store> [days]`\n"
        "• `/ads <store> [days]`\n"
        "• `/alerts <store>`\n"
        "• `/amazon <store> [days]`\n"
        "• `/amazon_recs <store>`\n"
        "• `/meta_audit <store> [days]` — D2C Meta audit (SCALE/REFRESH/PAUSE/WATCH)\n"
        "• `/google_ads <store> [days]` — Google Ads roster + zero-conv search terms\n"
        "• `/linkedin_ads <store> [days]` — LinkedIn Ads roster + creative metrics\n"
        "• `/tiktok <store> [days]`\n"
        "• `/tiktok_campaigns <store> [limit]`\n"
        "• `/tiktok_pixels <store> [limit]`\n"
        "• `/port_meta_to_tiktok <meta_ad_id> <tiktok_slug> landing=<url> "
        "text=\"...\" name=<display> [budget=50] [bid=10] [cta=LEARN_MORE]`\n"
        "• `/enable_tiktok_launch <manifest_id>`\n"
        "\n"
        "_The interactive `/plan` approval flow is Telegram-only — Discord "
        "can still view proposals but not click Approve/Reject._"
    )


def _stores_text() -> str:
    lines = ["**Configured stores:**"]
    for s in STORES:
        lines.append(f"• `{s.slug}` — {s.brand} ({s.currency})")
    return "\n".join(lines)


async def parse_and_run(content: str) -> str | None:
    """Given raw Discord message content, return reply text or None to stay silent."""
    text = (content or "").strip()
    if not text.startswith("/"):
        return None

    # strip leading slash, split command vs args
    head, _, rest = text[1:].partition(" ")
    cmd = head.strip().lower()
    pos, kv = _split_args(rest)

    if cmd in {"help", "h"}:
        return _help_text()
    if cmd in {"stores", "store"}:
        return _stores_text()

    # Commands that take <store> [days|limit]
    SIMPLE_STORE_N = {
        "insights":          ("insights",         "days",  7),
        "roas":              ("roas",             "days",  7),
        "ads":               ("ads",              "days",  7),
        "alerts":            ("alerts",           "days",  7),
        "amazon":            ("amazon",           "days",  7),
        "amazon_recs":       ("amazon_recs",      "days",  30),
        "meta_audit":        ("meta_audit",       "days",  14),
        "google_ads":        ("google_ads",       "days",  14),
        "linkedin_ads":      ("linkedin_ads",     "days",  14),
        "tiktok":            ("tiktok",           "days",  7),
        "tiktok_campaigns":  ("tiktok_campaigns", "limit", 10),
        "tiktok_pixels":     ("tiktok_pixels",    "limit", 10),
        "tracking_audit":    ("tracking_audit",   "days",  14),
    }
    if cmd in SIMPLE_STORE_N:
        route, second_key, default = SIMPLE_STORE_N[cmd]
        if not pos:
            return f"usage: `/{cmd} <store> [{second_key}]`"
        slug = pos[0]
        if get_store(slug) is None:
            return f"Unknown store `{slug}`. Try `/stores`."
        try:
            val = int(pos[1]) if len(pos) > 1 else default
        except ValueError:
            val = default
        state: dict[str, Any] = {
            "command": route, "store_slug": slug, second_key: val,
        }
        out = await _g().ainvoke(state)
        return (out or {}).get("reply_text") or "(no output)"

    if cmd == "port_meta_to_tiktok":
        if len(pos) < 2:
            return ("usage: `/port_meta_to_tiktok <meta_ad_id> <tiktok_slug> "
                    "landing=<url> text=\"...\" name=<display>`")
        meta_ad_id, tiktok_slug = pos[0], pos[1]
        landing = kv.get("landing") or ""
        ad_text = kv.get("text") or ""
        if not (landing and ad_text):
            return "`landing=` and `text=` are required."
        state = {
            "command": "port_meta_to_tiktok",
            "meta_ad_id": meta_ad_id,
            "tiktok_slug": tiktok_slug,
            "store_slug": tiktok_slug,
            "landing_url": landing,
            "ad_text": ad_text,
            "display_name": kv.get("name") or "Brand",
            "daily_budget": float(kv.get("budget") or 50),
            "bid_price": float(kv.get("bid") or 10),
            "call_to_action": (kv.get("cta") or "LEARN_MORE").upper(),
        }
        out = await _g().ainvoke(state)
        return (out or {}).get("reply_text") or "(no output)"

    if cmd == "enable_tiktok_launch":
        mid = pos[0] if pos else ""
        slug = mid.split("__")[0] if "__" in mid else "ayurpet-global"
        state = {
            "command": "enable_tiktok_launch",
            "manifest_id": mid,
            "store_slug": slug,
        }
        out = await _g().ainvoke(state)
        return (out or {}).get("reply_text") or "(no output)"

    return f"Unknown command: `/{cmd}`. Try `/help`."
