"""One-time backfill: embed ads_agent.agent_memory rows where embedding IS NULL.

Idempotent — skips rows that already have embeddings. Safe to re-run anytime.
Typically run once after first introducing the embed pipeline, plus manually
after any change to the embedding model (in which case clear embeddings first).

Usage:
    cd /home/support/glitch-grow-ads-agent
    .venv/bin/python ops/scripts/backfill_embeddings.py
"""
from __future__ import annotations

import asyncio
import logging
import sys

sys.path.insert(0, "src")

from dotenv import load_dotenv

load_dotenv()

import asyncpg

from ads_agent.config import settings
from ads_agent.memory.embed import composed_for_log, embed_text

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


async def main() -> None:
    conn = await asyncpg.connect(settings().postgres_insights_ro_url)
    try:
        rows = await conn.fetch(
            """SELECT id, command, store_slug, args, reply_text
               FROM ads_agent.agent_memory
               WHERE embedding IS NULL
               ORDER BY id ASC"""
        )
        log.info("found %d rows needing embeddings", len(rows))
        if not rows:
            return

        done = 0
        for r in rows:
            args = dict(r["args"]) if r["args"] else {}
            text = composed_for_log(
                command=r["command"],
                store_slug=r["store_slug"],
                args=args,
                reply_text=r["reply_text"] or "",
            )
            vec = await embed_text(text)
            if vec is None:
                log.warning("embed failed for row %d, skipping", r["id"])
                continue
            vec_str = "[" + ",".join(f"{v:.7f}" for v in vec) + "]"
            await conn.execute(
                "UPDATE ads_agent.agent_memory SET embedding = $1::vector WHERE id = $2",
                vec_str,
                r["id"],
            )
            done += 1
            if done % 20 == 0:
                log.info("  ...%d embeddings written", done)
        log.info("done: %d rows embedded", done)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
