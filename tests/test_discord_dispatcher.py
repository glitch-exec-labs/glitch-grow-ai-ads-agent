"""Dispatcher parsing + routing tests — no live Discord or LLM calls."""
from __future__ import annotations

import asyncio

import pytest


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_import_clean():
    from ads_agent.discord import dispatcher, inbox_consumer, poster  # noqa: F401


def test_non_command_returns_none():
    from ads_agent.discord.dispatcher import parse_and_run
    assert _run(parse_and_run("hello")) is None
    assert _run(parse_and_run("")) is None
    assert _run(parse_and_run("just chat")) is None


def test_help_works():
    from ads_agent.discord.dispatcher import parse_and_run
    r = _run(parse_and_run("/help"))
    assert r and "ads-agent" in r and "/insights" in r


def test_stores_works():
    from ads_agent.discord.dispatcher import parse_and_run
    r = _run(parse_and_run("/stores"))
    assert r and "Configured stores" in r


def test_unknown_command():
    from ads_agent.discord.dispatcher import parse_and_run
    r = _run(parse_and_run("/wutang"))
    assert r and "Unknown command" in r


def test_kv_arg_parsing():
    """port_meta_to_tiktok with missing landing should complain about landing+text."""
    from ads_agent.discord.dispatcher import parse_and_run
    r = _run(parse_and_run("/port_meta_to_tiktok 123 ayurpet-global"))
    assert r and "landing=" in r


def test_poster_chunking():
    from ads_agent.discord.poster import _chunks
    long = ("abc\n" * 600)  # ~2400 chars
    c = _chunks(long, limit=2000)
    assert len(c) >= 2
    assert all(len(x) <= 2000 for x in c)
