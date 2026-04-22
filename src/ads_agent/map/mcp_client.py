"""Marketplace Ad Pros MCP client — remote streamable-HTTP, Bearer auth.

MAP is a paid third-party that exposes 41 Amazon-Ads + Selling-Partner
tools at https://app.marketplaceadpros.com/mcp. We use it to bypass the
LWA Partner Network approval bottleneck and pull:

  • campaign/ad-group/keyword structure (list_resources resource_type=...)
  • Amazon's own bid/budget/keyword recommendations
  • cross-SKU attribution via `ask_report_analyst` (needs active plan)

Auth model:
  Single static Bearer token (`MAP_API_KEY` env) — MAP's OAuth discovery
  endpoints advertise RFC 7591 but in practice an API key works for all
  tool calls and is simpler to rotate.

Plan-gate behavior:
  Read tools (list_brands, list_selling_partner_integrations, whoami,
  list_resources) return real data even on the free tier.
  Paid tools (ask_report_analyst, get_amazon_ads_*_recs) return
  `isError=True` with "You do not have an active plan" text until you
  upgrade to AI Connect ($10/wk). Callers should treat that as a
  soft-fail and degrade to the free-tier tools.

Uses the same `streamablehttp_client + ClientSession` pattern as the
local amazon + meta MCP clients, so call sites remain symmetric.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from ads_agent.config import settings

log = logging.getLogger(__name__)

DEFAULT_URL = "https://app.marketplaceadpros.com/mcp"


class MapMcpError(RuntimeError):
    pass


def _unwrap(result: Any) -> Any:
    """MAP's server returns FastMCP-style content arrays for most tools, but
    the text payload is itself often a JSON string we want to parse — e.g.
    `{"content":[{"type":"text","text":"{\\"brands\\": [...]}"}]}`. Walk
    through that nesting so callers get a native object.
    """
    content = getattr(result, "content", None)
    if content is None and isinstance(result, dict):
        content = result.get("content")
    if isinstance(content, list) and content:
        first = content[0]
        text = getattr(first, "text", None)
        if text is None and isinstance(first, dict):
            text = first.get("text")
        if text is not None:
            try:
                return json.loads(text)
            except Exception:
                return {"text": text}
    sc = getattr(result, "structuredContent", None)
    if sc:
        return sc
    if isinstance(result, dict):
        return result
    return {}


def _is_plan_gated(result: Any) -> bool:
    """Did MAP refuse this call because we're on the free tier?

    The server returns a content-text payload whose text contains
    "You do not have an active plan" and isError=True. We surface that
    as a structured signal callers can branch on.
    """
    is_err = getattr(result, "isError", None)
    if is_err is None and isinstance(result, dict):
        is_err = result.get("isError")
    if not is_err:
        return False
    content = getattr(result, "content", None) or (result.get("content") if isinstance(result, dict) else None)
    if isinstance(content, list) and content:
        first = content[0]
        text = getattr(first, "text", None) or (first.get("text") if isinstance(first, dict) else "")
        return "active plan" in (text or "").lower()
    return False


async def call_tool(
    tool_name: str,
    arguments: dict[str, Any] | None = None,
    *,
    timeout_s: float = 60.0,
) -> Any:
    """Invoke a tool on MAP. Returns unwrapped Python object.

    Raises MapMcpError if the MAP_API_KEY is unset, the MCP handshake
    fails, or the tool raises at the SDK layer. Plan-gate errors do NOT
    raise — inspect the returned payload (`isError` + "active plan" text)
    or use `call_tool_checked` below if you want a clean boolean.
    """
    token = settings().map_api_key.strip()
    if not token:
        raise MapMcpError("MAP_API_KEY not configured")

    headers = {"Authorization": f"Bearer {token}"}
    async with streamablehttp_client(DEFAULT_URL, headers=headers, timeout=timeout_s) as (
        read_stream, write_stream, _meta,
    ):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            try:
                result = await session.call_tool(tool_name, arguments or {})
            except Exception as e:
                raise MapMcpError(f"{tool_name}: {e}") from e
    return _unwrap(result), _is_plan_gated(result)


async def list_brands() -> list[dict[str, Any]]:
    """Read-only tier — works without a plan. Returns the brand list with
    nested Amazon Ads profiles. Useful as a healthcheck and for mapping
    store slugs → MAP account_id + integration_id."""
    data, gated = await call_tool("list_brands", {})
    if gated:
        raise MapMcpError("list_brands shouldn't be plan-gated — unexpected")
    if isinstance(data, dict) and "brands" in data:
        return data["brands"]
    return []


async def whoami() -> dict[str, Any]:
    """Identity + plan status probe. Used by /map healthcheck."""
    data, _gated = await call_tool("whoami", {})
    if isinstance(data, dict) and "text" in data:
        # whoami returns plain text, not JSON
        return {"text": data["text"]}
    return data if isinstance(data, dict) else {"text": str(data)}


async def list_sp_campaigns(integration_id: str, account_id: str, state_filter: str = "ENABLED") -> list[dict]:
    """Enabled Sponsored Products campaigns for an account. Free-tier tool."""
    data, gated = await call_tool("list_resources", {
        "integration_id": integration_id,
        "account_id": account_id,
        "resource_type": "sp_campaigns",
        "state_filter": state_filter,
    })
    if gated:
        return []
    if isinstance(data, dict) and "items" in data:
        return data["items"]
    return []


async def account_recs(integration_id: str, account_id: str) -> dict[str, Any]:
    """Amazon's top consolidated recommendations for an account (bid, budget,
    targeting). Paid tool — AI Connect plan required."""
    data, gated = await call_tool("get_amazon_ads_account_recs", {
        "integration_id": integration_id,
        "account_id": account_id,
    })
    if gated:
        return {"_plan_gated": True}
    return data if isinstance(data, dict) else {"raw": data}


async def budget_recs(integration_id: str, account_id: str) -> dict[str, Any]:
    """Campaigns running out of budget + estimated missed opportunity.
    Paid tool — AI Connect plan required."""
    data, gated = await call_tool("get_amazon_ads_campaigns_budget_recs", {
        "integration_id": integration_id,
        "account_id": account_id,
    })
    if gated:
        return {"_plan_gated": True}
    return data if isinstance(data, dict) else {"raw": data}
