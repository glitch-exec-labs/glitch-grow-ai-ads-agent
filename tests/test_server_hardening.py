"""Tests for issues #7 (webhook error tracking), #8 (bearer parsing),
#9 (body-size cap). No live external services; FastAPI TestClient + a
monkey-patched Shopify webhook handler.
"""
from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    # Minimal env so server imports cleanly
    monkeypatch.setenv("AGENT_RUN_TOKEN", "testtoken123")
    monkeypatch.setenv("INTERNAL_API_SECRET", "internaltesttoken")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "tgsecret")
    monkeypatch.setenv("MAX_REQUEST_BODY_BYTES", str(4 * 1024))  # 4 KB cap for test

    # Avoid actually starting the telegram Application in tests
    with patch("ads_agent.server.build_telegram_app") as mock_build:
        fake_tg = AsyncMock()
        mock_build.return_value = fake_tg
        # Re-import server to pick up monkey-patched env for MAX_BODY_BYTES
        import importlib
        import ads_agent.server as srv
        importlib.reload(srv)
        with TestClient(srv.app) as c:
            yield c


def test_bearer_missing_header_returns_401(client):
    """Issue #8: no Authorization header → 401."""
    r = client.post("/agent/run", json={"command": "insights"})
    assert r.status_code == 401


def test_bearer_empty_token_returns_401(client):
    """Issue #8: 'Bearer ' with no token must not pass compare_digest."""
    r = client.post(
        "/agent/run",
        json={"command": "insights"},
        headers={"Authorization": "Bearer "},
    )
    assert r.status_code == 401


def test_bearer_whitespace_only_token_returns_401(client):
    """Issue #8: 'Bearer    ' (padding whitespace) → 401."""
    r = client.post(
        "/agent/run",
        json={"command": "insights"},
        headers={"Authorization": "Bearer    "},
    )
    assert r.status_code == 401


def test_bearer_wrong_token_returns_401(client):
    r = client.post(
        "/agent/run",
        json={"command": "insights"},
        headers={"Authorization": "Bearer wrongsecret"},
    )
    assert r.status_code == 401


def test_body_size_cap_rejects_oversize_with_413(client):
    """Issue #9: body over MAX_REQUEST_BODY_BYTES (4 KB in fixture) → 413."""
    # 10 KB payload — comfortably over the 4 KB test cap
    fat_payload = {"x": "A" * (10 * 1024)}
    r = client.post(
        "/agent/run",
        json=fat_payload,
        headers={"Authorization": "Bearer testtoken123"},
    )
    assert r.status_code == 413, r.text
    assert "too large" in r.text.lower()


def test_body_size_cap_lets_healthz_through(client):
    """Cap only applies to POST/PUT/PATCH — GET still works."""
    r = client.get("/healthz")
    assert r.status_code == 200


def test_bearer_helper_explicit_empty_expected(monkeypatch):
    """Issue #8: even if expected happens to be empty string (env misconfig
    that bypassed the earlier 503 check), _require_bearer must fail closed."""
    from fastapi import HTTPException
    from starlette.requests import Request
    from ads_agent.server import _require_bearer

    # Build a minimal Request stub with a Bearer header
    scope = {
        "type": "http", "method": "POST", "headers": [
            (b"authorization", b"Bearer anything"),
        ],
    }
    req = Request(scope)
    with pytest.raises(HTTPException) as ei:
        _require_bearer(req, "")
    assert ei.value.status_code == 503  # explicit 503 for unconfigured


def test_webhook_safely_logs_errors(monkeypatch, caplog):
    """Issue #7: _run_webhook_safely must log exceptions, never re-raise."""
    import asyncio
    from ads_agent.server import _run_webhook_safely

    async def broken(*a, **kw):
        raise RuntimeError("boom in handler")

    with patch("ads_agent.server.handle_webhook", side_effect=broken):
        with caplog.at_level("ERROR"):
            asyncio.get_event_loop().run_until_complete(
                _run_webhook_safely("orders/create", "x.myshopify.com", {"id": 1})
            )
    assert any("shopify webhook handler failed" in r.message for r in caplog.records)
