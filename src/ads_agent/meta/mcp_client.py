"""Thin client for the existing pipeboard-co/meta-ads-mcp service.

Runs locally on 127.0.0.1:3103 via systemd (/etc/systemd/system/meta-ads-mcp.service),
streamable-http transport. We call it over HTTP rather than hosting a parallel
SDK wrapper, to keep one source of truth for Meta creds and rate limiting.

Cloud Run service cannot reach this (localhost-only); the webhook receiver /
reconciler runs on the VM and is the only component that calls this client.
"""
from __future__ import annotations

import httpx

from ads_agent.config import settings


class MetaAdsMCPClient:
    def __init__(self, base_url: str | None = None, *, timeout: float = 60.0) -> None:
        self.base_url = (base_url or settings().meta_ads_mcp_url).rstrip("/")
        self._timeout = timeout

    async def call(self, tool: str, arguments: dict) -> dict:
        """Invoke an MCP tool by name. Exact streamable-http payload shape will be
        firmed up when we wire the first real call in v1 — left deliberately thin
        here so we can swap to the official MCP Python client if that matures.
        """
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self.base_url}/tools/{tool}",
                json={"arguments": arguments},
            )
        resp.raise_for_status()
        return resp.json()
