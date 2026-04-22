"""LangGraph state machine for the ads agent.

Graph entry -> recall_node -> conditional route -> command_node -> END

recall_node runs before every command, loads relevant prior turns from
ads_agent.agent_memory, and writes them to state.prior_context as an XML block.
LLM-using command nodes (tracking_audit, creative_critique, ideas) read the
block and prepend it to their LLM prompts.

Deterministic nodes (pull_insights, roas_compute, ads_leaderboard, alerts) ignore
prior_context — they're pure compute. Cheap to populate anyway; future delta-reports
will consume it without graph changes.
"""
from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, StateGraph

from ads_agent.agent.nodes.ads_leaderboard import ads_leaderboard_node
from ads_agent.agent.nodes.alerts import alerts_node
from ads_agent.agent.nodes.amazon_insights import amazon_insights_node
from ads_agent.agent.nodes.amazon_recs import amazon_recs_node
from ads_agent.agent.nodes.attribution import attribution_node
from ads_agent.agent.nodes.creative_critique import creative_critique_node
from ads_agent.agent.nodes.ideas import ideas_node
from ads_agent.agent.nodes.pull_insights import pull_insights_node
from ads_agent.agent.nodes.roas_compute import roas_compute_node
from ads_agent.agent.nodes.tracking_audit import tracking_audit_node
from ads_agent.memory.recall import recall_prior


class AgentState(TypedDict, total=False):
    command: str
    store_slug: str
    ad_id: str
    days: int
    orders_summary: dict
    reply_text: str
    prior_context: str  # XML <prior_context> block from recall_node, or ''


async def recall_node(state: AgentState) -> AgentState:
    """Load prior relevant turns into state.prior_context. Fail-open."""
    command = state.get("command", "")
    if not command:
        return {**state, "prior_context": ""}
    args = {k: v for k, v in state.items() if k in ("days", "ad_id")}
    prior = await recall_prior(
        store_slug=state.get("store_slug"),
        command=command,
        args=args,
    )
    return {**state, "prior_context": prior}


def _route(state: AgentState) -> str:
    cmd = state.get("command", "insights")
    return {
        "insights": "pull_insights",
        "roas": "roas_compute",
        "tracking_audit": "tracking_audit",
        "ads": "ads_leaderboard",
        "creative": "creative_critique",
        "ideas": "ideas",
        "alerts": "alerts",
        "amazon": "amazon_insights",
        "amazon_recs": "amazon_recs",
        "attribution": "attribution",
    }.get(cmd, "pull_insights")


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("recall", recall_node)
    g.add_node("pull_insights", pull_insights_node)
    g.add_node("roas_compute", roas_compute_node)
    g.add_node("tracking_audit", tracking_audit_node)
    g.add_node("ads_leaderboard", ads_leaderboard_node)
    g.add_node("creative_critique", creative_critique_node)
    g.add_node("ideas", ideas_node)
    g.add_node("alerts", alerts_node)
    g.add_node("amazon_insights", amazon_insights_node)
    g.add_node("amazon_recs", amazon_recs_node)
    g.add_node("attribution", attribution_node)

    g.set_entry_point("recall")
    g.add_conditional_edges("recall", _route)
    for node in ("pull_insights", "roas_compute", "tracking_audit",
                 "ads_leaderboard", "creative_critique", "ideas", "alerts",
                 "amazon_insights", "amazon_recs", "attribution"):
        g.add_edge(node, END)
    return g.compile()
