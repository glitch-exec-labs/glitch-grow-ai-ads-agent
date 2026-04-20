"""Cron entrypoint for the action executor.

Fires every 5 minutes. Atomically claims approved actions from the queue and
runs each via glitch-ads-mcp. Also moves past-TTL pending_approval rows to
'expired' status so the queue stays clean.

Usage:
    python ops/scripts/run_action_executor.py
    python ops/scripts/run_action_executor.py --max-batch 5
    python ops/scripts/run_action_executor.py --dry-run   # claim but don't call MCP
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

from ads_agent.actions.executor import expire_old_pending, run_once

log = logging.getLogger("action_executor")


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--max-batch", type=int, default=10,
                   help="max approved actions per run (default 10)")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    # Executor flips status approved→executing and writes result/prior_state —
    # must be the RW DSN (issue #3).
    dsn = os.environ.get("POSTGRES_RW_URL") or os.environ["POSTGRES_INSIGHTS_RO_URL"]
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=3, command_timeout=90.0)
    try:
        expired = await expire_old_pending(pool)
        if expired:
            log.info("expired %d past-TTL proposals", expired)
        n = await run_once(pool, max_batch=args.max_batch)
        log.info("executor tick: %d actions processed", n)
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
