"""Thin HTTP client for the amazon-ads-mcp MCP server (port 3105, streamable-http).

All Amazon data access goes through this — the agent does NOT talk to
Supermetrics or Amazon APIs directly any more. The MCP server owns both the
native Amazon Ads API (pending approval) and the Supermetrics fallback.

Why an MCP call rather than in-process function:
  - amazon-ads-mcp is a separable service maintained by its own repo
    (glitch-exec-labs/amazon-ads-mcp). Same pattern as glitch-ads-mcp for
    Meta Ads.
  - Swap from Supermetrics → native LWA is a server-side config change, no
    agent redeploy.

Transport: streamable-http with JSON-RPC 2.0 body. We call tools via
`tools/call` with a specific `name` and `arguments` blob.
"""
from __future__ import annotations

import logging
import os
import uuid
from typing import Any

import httpx

log = logging.getLogger(__name__)

DEFAULT_URL = os.environ.get("AMAZON_ADS_MCP_URL", "http://127.0.0.1:3105/mcp")


class AmazonMcpError(RuntimeError):
    pass


async def call_tool(tool_name: str, arguments: dict[str, Any] | None = None, *, timeout_s: float = 360.0) -> Any:
    """Invoke one tool on amazon-ads-mcp. Returns the tool's result dict.

    Slow path — some tools (supermetrics_ads_performance) hit Amazon's async
    Reports API and take 2–3 minutes. Caller should run these from background
    jobs, not inline in a user-facing handler.
    """
    payload = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments or {},
        },
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        r = await client.post(DEFAULT_URL, json=payload, headers=headers)
    if r.status_code >= 400:
        raise AmazonMcpError(f"MCP HTTP {r.status_code}: {r.text[:200]}")

    # Streamable-HTTP returns either JSON or SSE frames; MCP JSON-RPC
    # envelope shape is the same either way. Try JSON first, then parse SSE.
    try:
        body = r.json()
    except Exception:
        # SSE frames: `event: message\ndata: {...}\n\n`. Extract the last data line.
        text = r.text or ""
        body = None
        for line in text.splitlines():
            if line.startswith("data:"):
                try:
                    import json
                    body = json.loads(line[5:].strip())
                except Exception:
                    continue
        if body is None:
            raise AmazonMcpError(f"could not parse MCP response: {text[:200]}")

    if "error" in body:
        err = body["error"]
        raise AmazonMcpError(f"MCP error {err.get('code')}: {err.get('message')}")
    result = body.get("result") or {}
    # FastMCP wraps tool returns in {"content": [{"type":"text","text": "<json-string>"}]}
    # Unwrap to the original dict.
    content = result.get("content")
    if isinstance(content, list) and content:
        first = content[0]
        if isinstance(first, dict) and first.get("type") == "text":
            import json
            try:
                return json.loads(first["text"])
            except Exception:
                return {"text": first["text"]}
    return result
