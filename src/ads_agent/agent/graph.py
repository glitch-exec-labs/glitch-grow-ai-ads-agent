"""LangGraph state machine for the ads agent.

Skeleton in v0: a single `pull_insights` node that returns a deterministic
summary from Shopify Admin GraphQL — no LLM reasoning yet.

v1 adds: reconcile -> diagnose -> propose_action -> hitl_gate.
v2 adds: ads_write node behind the HITL gate.
"""
from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, StateGraph

from ads_agent.agent.nodes.pull_insights import pull_insights_node


class AgentState(TypedDict, total=False):
    command: str  # e.g. "insights"
    store_slug: str
    days: int
    # Node outputs accrete here:
    orders_summary: dict
    reply_text: str  # final Telegram-ready string


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("pull_insights", pull_insights_node)
    graph.set_entry_point("pull_insights")
    graph.add_edge("pull_insights", END)
    return graph.compile()
