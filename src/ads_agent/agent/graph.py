"""LangGraph state machine for the ads agent.

State routes by the `command` field (set by the Telegram handler) into one of:
  insights         -> pull_insights_node        (PostHog read, no LLM)
  roas             -> roas_compute_node         (PostHog + Meta Graph, no LLM)
  tracking_audit   -> tracking_audit_node       (PostHog + Meta Graph + Gemini 2.5 Pro)
"""
from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, StateGraph

from ads_agent.agent.nodes.ads_leaderboard import ads_leaderboard_node
from ads_agent.agent.nodes.creative_critique import creative_critique_node
from ads_agent.agent.nodes.pull_insights import pull_insights_node
from ads_agent.agent.nodes.roas_compute import roas_compute_node
from ads_agent.agent.nodes.tracking_audit import tracking_audit_node


class AgentState(TypedDict, total=False):
    command: str
    store_slug: str
    ad_id: str
    days: int
    orders_summary: dict
    reply_text: str


def _route(state: AgentState) -> str:
    cmd = state.get("command", "insights")
    return {
        "insights": "pull_insights",
        "roas": "roas_compute",
        "tracking_audit": "tracking_audit",
        "ads": "ads_leaderboard",
        "creative": "creative_critique",
    }.get(cmd, "pull_insights")


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("pull_insights", pull_insights_node)
    g.add_node("roas_compute", roas_compute_node)
    g.add_node("tracking_audit", tracking_audit_node)
    g.add_node("ads_leaderboard", ads_leaderboard_node)
    g.add_node("creative_critique", creative_critique_node)

    g.set_conditional_entry_point(_route)
    g.add_edge("pull_insights", END)
    g.add_edge("roas_compute", END)
    g.add_edge("tracking_audit", END)
    g.add_edge("ads_leaderboard", END)
    g.add_edge("creative_critique", END)
    return g.compile()
