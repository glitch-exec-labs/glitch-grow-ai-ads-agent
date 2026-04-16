"""LiteLLM-routed model selection.

Default policy:
  - `cheap`    -> Gemini 2.5 Flash (Vertex or AI Studio, whichever creds exist)
  - `smart`    -> Claude Sonnet 4.5 (Anthropic)
  - `heavy`    -> Gemini 2.5 Pro for long-reasoning audits (HITL gated)

Per-node overrides live in agent/graph.py. Keeping the router tiny so swapping
providers doesn't cascade through tool code.
"""
from __future__ import annotations

from dataclasses import dataclass

from ads_agent.config import settings


@dataclass(frozen=True)
class ModelChoice:
    """litellm `model` string + extra kwargs."""

    model: str
    kwargs: dict


def pick(tier: str = "cheap") -> ModelChoice:
    s = settings()
    if tier == "smart":
        return ModelChoice(model="claude-sonnet-4-5", kwargs={"api_key": s.anthropic_api_key})
    if tier == "heavy":
        if s.vertex_project:
            return ModelChoice(
                model="vertex_ai/gemini-2.5-pro",
                kwargs={"vertex_project": s.vertex_project, "vertex_location": s.vertex_location},
            )
        return ModelChoice(model="gemini/gemini-2.5-pro", kwargs={"api_key": s.google_api_key})
    # default cheap
    if s.vertex_project:
        return ModelChoice(
            model="vertex_ai/gemini-2.5-flash",
            kwargs={"vertex_project": s.vertex_project, "vertex_location": s.vertex_location},
        )
    return ModelChoice(model="gemini/gemini-2.5-flash", kwargs={"api_key": s.google_api_key})
