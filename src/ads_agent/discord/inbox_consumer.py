"""Watch /home/support/.glitch-discord/inbox/<channel>/ and dispatch each
message through the agent, posting replies back to Discord.

Design:
  - Polling-based (1s sleep). Simpler than inotify for the current low
    message volume; switches to inotify are a one-line swap.
  - Each *.json file is parsed; if `.content` starts with `/`, it's routed
    through `dispatcher.parse_and_run`. Reply is posted to `channel_id`,
    referencing the source message id. The file is then moved to
    `<channel>/processed/<id>.json` so re-runs don't double-process.
  - Failures move the file to `<channel>/errors/<id>.json` with an
    appended `{"_error": "..."}` field so an operator can retriage.

Run as:
  python -m ads_agent.discord.inbox_consumer
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import time
from pathlib import Path

from dotenv import load_dotenv

# Load agent .env first (for LLM keys etc.), then Discord env
load_dotenv("/home/support/glitch-grow-ads-agent/.env")
load_dotenv("/home/support/.config/glitch-discord/env")

from ads_agent.discord.dispatcher import parse_and_run
from ads_agent.discord.poster import DiscordPostError, post_message

INBOX_ROOT = Path(os.environ.get("DISCORD_INBOX_ROOT", "/home/support/.glitch-discord/inbox"))
# Channels the consumer will serve. Extend via env for additional agents.
CHANNELS = tuple(
    c.strip() for c in os.environ.get("DISCORD_CONSUMER_CHANNELS", "grow-ads").split(",")
    if c.strip()
)
POLL_SECS = float(os.environ.get("DISCORD_CONSUMER_POLL_SECS", "1.0"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("discord_consumer")

_stop = asyncio.Event()


def _install_signal_handlers() -> None:
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _stop.set)
        except NotImplementedError:
            pass  # Windows


async def _handle_one(channel: str, path: Path) -> None:
    try:
        msg = json.loads(path.read_text())
    except Exception as e:  # noqa: BLE001
        log.warning("unreadable %s: %s", path, e)
        _archive(path, channel, kind="errors", extra={"_error": f"unreadable: {e}"})
        return

    content   = (msg.get("content") or "").strip()
    author    = (msg.get("author") or {}).get("name", "?")
    channel_id = str(msg.get("channel_id") or "")
    msg_id    = str(msg.get("id") or "")

    if not channel_id:
        log.warning("missing channel_id in %s", path)
        _archive(path, channel, kind="errors", extra={"_error": "missing channel_id"})
        return

    # Ignore the bot's own messages if the upstream bot echoes them
    if author == "glitch-bot":
        _archive(path, channel, kind="processed")
        return

    if not content.startswith("/"):
        log.info("skip non-command from %s: %s", author, content[:60])
        _archive(path, channel, kind="processed")
        return

    log.info("dispatch channel=%s author=%s cmd=%s", channel, author, content[:80])
    try:
        reply = await parse_and_run(content)
    except Exception as e:  # noqa: BLE001
        log.exception("dispatch error")
        reply = f"❌ internal error: {e}"

    if reply:
        try:
            await post_message(channel_id, reply, reply_to_message_id=msg_id)
        except DiscordPostError as e:
            log.error("post failed: %s", e)
            _archive(path, channel, kind="errors", extra={"_error": f"post failed: {e}"})
            return

    _archive(path, channel, kind="processed")


def _archive(path: Path, channel: str, *, kind: str, extra: dict | None = None) -> None:
    dest_dir = INBOX_ROOT / channel / kind
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / path.name
    try:
        if extra:
            try:
                data = json.loads(path.read_text())
            except Exception:
                data = {"_raw": path.read_text(errors="replace")}
            data.update(extra)
            dest.write_text(json.dumps(data, indent=2))
            path.unlink(missing_ok=True)
        else:
            path.rename(dest)
    except Exception as e:  # noqa: BLE001
        log.error("archive failed %s → %s: %s", path, dest, e)


async def _watch_channel(channel: str) -> None:
    inbox = INBOX_ROOT / channel
    inbox.mkdir(parents=True, exist_ok=True)
    log.info("watching %s", inbox)
    while not _stop.is_set():
        try:
            entries = sorted(inbox.glob("*.json"))
        except Exception as e:  # noqa: BLE001
            log.error("scan %s failed: %s", inbox, e)
            entries = []
        for path in entries:
            if _stop.is_set():
                break
            await _handle_one(channel, path)
        try:
            await asyncio.wait_for(_stop.wait(), timeout=POLL_SECS)
        except asyncio.TimeoutError:
            pass


async def main() -> None:
    _install_signal_handlers()
    log.info("discord inbox consumer up · channels=%s root=%s", CHANNELS, INBOX_ROOT)
    await asyncio.gather(*[_watch_channel(c) for c in CHANNELS])
    log.info("shutdown clean")


if __name__ == "__main__":
    asyncio.run(main())
