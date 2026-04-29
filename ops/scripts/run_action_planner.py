"""Cron entrypoint for the action planner.

Fires every 4 hours. For each configured store, scans Meta adsets against
R1/R2/R3 rules and posts surviving proposals to the store's Telegram group
as Approve/Reject prompts.

Usage:
    python ops/scripts/run_action_planner.py               # all enabled stores
    python ops/scripts/run_action_planner.py --store store-a
    python ops/scripts/run_action_planner.py --dry-run     # log only, no writes/posts
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

sys.path.insert(0, "src")

from dotenv import load_dotenv
load_dotenv()

import asyncpg

from ads_agent.actions.models import LIGHTHOUSE_CHAT_ID
from ads_agent.actions.planner import plan_amazon_for_store, plan_for_store

log = logging.getLogger("action_planner")

# Map store_slug → telegram chat_id for approval prompts.
# When a second client onboards, move this into STORES config.
STORE_APPROVAL_CHATS: dict[str, int] = {
    "store-a":    LIGHTHOUSE_CHAT_ID,
    "store-b": LIGHTHOUSE_CHAT_ID,  # same group serves both stores
}


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--store", help="single store slug (default: all configured)")
    p.add_argument("--dry-run", action="store_true", help="plan but don't post/persist")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    stores = [args.store] if args.store else sorted(STORE_APPROVAL_CHATS.keys())
    # Planner writes to ads_agent.agent_actions — must be the RW DSN (issue #3).
    dsn = os.environ.get("POSTGRES_RW_URL") or os.environ["POSTGRES_INSIGHTS_RO_URL"]
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=3, command_timeout=60.0)
    try:
        for slug in stores:
            chat = STORE_APPROVAL_CHATS.get(slug)
            if chat is None:
                log.warning("no Telegram chat configured for %s — skipping", slug)
                continue
            if args.dry_run:
                log.info("[DRY-RUN] would plan %s → chat %s", slug, chat)
                continue
            n_meta = await plan_for_store(pool, slug, chat)
            log.info("planned %s Meta: %d proposals posted", slug, n_meta)
            # Amazon planner is env-gated; returns 0 silently if AMAZON_PLANNER_ENABLED != '1'
            n_amz = await plan_amazon_for_store(pool, slug, chat)
            log.info("planned %s Amazon: %d proposals posted", slug, n_amz)
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
