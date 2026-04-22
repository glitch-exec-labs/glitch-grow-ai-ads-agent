"""Push the bot's command menu to Telegram via setMyCommands.

Telegram's `/` command-autocomplete menu is NOT derived from registered
CommandHandlers — it's a separate per-bot setting you push once via the
Bot API. This script is the single source of truth for that menu; re-run
after adding or renaming commands in bot.py.

Usage:
    python ops/scripts/set_bot_commands.py            # push current list
    python ops/scripts/set_bot_commands.py --show     # show current server-side list
    python ops/scripts/set_bot_commands.py --clear    # wipe the menu (not usually useful)
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, "src")

from dotenv import load_dotenv
load_dotenv()

import httpx

# Source of truth for the user-visible command menu. Keep in sync with
# src/ads_agent/telegram/bot.py handler registrations. Descriptions must
# stay under 256 chars per Telegram's API.
BOT_COMMANDS: list[dict] = [
    # --- diagnostics / reporting ---
    {"command": "insights",       "description": "Shopify orders + revenue rollup (last 7d default)"},
    {"command": "roas",           "description": "ROAS: pipeline vs paid vs Meta-reported vs GA4 ground truth"},
    {"command": "tracking_audit", "description": "Diagnose UTM coverage + pixel/CAPI gaps (last 30d)"},
    {"command": "ads",            "description": "Top-spending ads this week (per store)"},
    {"command": "creative",       "description": "LLM critique of a specific ad creative — usage: /creative <ad_id>"},
    {"command": "ideas",          "description": "Generate 5 creative briefs based on top-3 winners"},
    {"command": "alerts",         "description": "Daily-digest style alerts (spend anomalies, paused-campaign signals)"},
    {"command": "amazon",         "description": "Amazon Seller + Ads rollup (MAP for ads, Airbyte for Seller)"},
    {"command": "amazon_recs",    "description": "Amazon's own bid/budget/keyword recommendations via MAP"},
    {"command": "attribution",    "description": "Cross-channel Meta → Amazon attribution (sessions-delta model)"},
    # --- v2 action layer ---
    {"command": "plan",           "description": "Show pending action proposals (Meta + Amazon HITL queue)"},
    {"command": "actions",        "description": "Show recent executed/rejected actions"},
    {"command": "scan_amazon",    "description": "Manually trigger Amazon HITL scan — proposes pauses / negatives"},
    # --- housekeeping ---
    {"command": "stores",         "description": "List all stores configured in the agent"},
    {"command": "help",           "description": "Show available commands"},
    {"command": "start",          "description": "Handshake / welcome"},
]


async def _api(method: str, token: str, **body) -> dict:
    async with httpx.AsyncClient(timeout=15.0) as c:
        r = await c.post(
            f"https://api.telegram.org/bot{token}/{method}",
            json=body,
        )
    return r.json()


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--show",  action="store_true", help="GET current menu from Telegram")
    p.add_argument("--clear", action="store_true", help="POST empty commands list (wipe menu)")
    args = p.parse_args()

    token = os.environ.get("TELEGRAM_BOT_TOKEN_ADS", "").strip()
    if not token:
        print("TELEGRAM_BOT_TOKEN_ADS not set", file=sys.stderr)
        sys.exit(2)

    if args.show:
        body = await _api("getMyCommands", token)
        if not body.get("ok"):
            print(f"getMyCommands failed: {body}", file=sys.stderr)
            sys.exit(1)
        print(f"Current menu has {len(body['result'])} commands:")
        for c in body["result"]:
            print(f"  /{c['command']:20} {c['description']}")
        return

    if args.clear:
        body = await _api("setMyCommands", token, commands=[])
        print(f"clear: {body.get('ok')} · {body.get('description','')}")
        return

    # Validate lengths (Telegram: description ≤ 256 chars, command ≤ 32 chars,
    # and lowercase-letters / digits / underscore only for command).
    for c in BOT_COMMANDS:
        assert len(c["description"]) <= 256, c
        assert len(c["command"]) <= 32, c
        assert all(ch.islower() or ch.isdigit() or ch == "_" for ch in c["command"]), c

    body = await _api("setMyCommands", token, commands=BOT_COMMANDS)
    if body.get("ok"):
        print(f"✓ pushed {len(BOT_COMMANDS)} commands to BotFather")
        # Read back to confirm
        body2 = await _api("getMyCommands", token)
        print(f"  server now holds {len(body2.get('result', []))} commands:")
        for c in body2.get("result", []):
            print(f"    /{c['command']:20} {c['description']}")
    else:
        print(f"✗ setMyCommands failed: {body}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
