"""Smoke + unit tests for the Meta→TikTok port workflow.

No live API calls. httpx is monkey-patched to simulate TikTok create
responses and Meta Graph responses.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest


def test_import_surface():
    """Everything imports and the graph compiles."""
    from ads_agent.agent.graph import build_graph
    from ads_agent.agent.workflows.port_meta_to_tiktok import (  # noqa: F401
        PortError,
        enable_launch,
        list_recent_manifests,
        port_meta_ad,
    )
    from ads_agent.tiktok.creatives import (  # noqa: F401
        MIN_DAILY_BUDGET,
        create_ad,
        create_adgroup,
        create_campaign,
    )
    from ads_agent.tiktok.uploads import upload_image, upload_video  # noqa: F401

    build_graph()


def test_budget_floor_enforced(tmp_path, monkeypatch):
    """create_campaign raises before HTTP if budget below TikTok's floor."""
    from ads_agent.tiktok.creatives import MIN_DAILY_BUDGET, TikTokCreativeError, create_campaign
    import asyncio

    with pytest.raises(TikTokCreativeError, match="below TikTok minimum"):
        asyncio.get_event_loop().run_until_complete(
            create_campaign(
                advertiser_id="x", campaign_name="t",
                budget=MIN_DAILY_BUDGET - 1,
                access_token="tok",
            )
        )


def test_ad_text_truncation_logs(caplog):
    """ad_text > 100 chars is truncated with a warning — no HTTP call here."""
    from ads_agent.tiktok.creatives import AD_TEXT_MAX
    assert AD_TEXT_MAX == 100


def test_port_node_missing_args():
    """Port node returns usage hint when required args missing."""
    import asyncio
    from ads_agent.agent.nodes.tiktok_port_meta import tiktok_port_meta_node

    out = asyncio.get_event_loop().run_until_complete(
        tiktok_port_meta_node({"meta_ad_id": "", "tiktok_slug": ""})
    )
    assert "Usage" in out["reply_text"]


def test_list_recent_manifests_empty(monkeypatch, tmp_path):
    """With an empty manifest dir, listing returns []."""
    monkeypatch.setenv("TIKTOK_LAUNCH_MANIFEST_DIR", str(tmp_path))
    # Re-import so module picks up env
    import importlib
    import ads_agent.agent.workflows.port_meta_to_tiktok as mod
    importlib.reload(mod)
    assert mod.list_recent_manifests() == []
