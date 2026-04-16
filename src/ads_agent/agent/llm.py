"""LLM routing via LiteLLM.

Tiers:
  cheap   -> Gemini 2.5 Flash         (bulk classification, short summaries)
  smart   -> Gemini 2.5 Pro           (deep reasoning, tracking audits)
  openai  -> gpt-4o-mini              (fallback / comparison)

Falls back gracefully if a provider key is missing.
"""
from __future__ import annotations

import logging
import os

from ads_agent.config import settings

log = logging.getLogger(__name__)


def _ensure_env() -> None:
    """LiteLLM reads keys from env vars. Mirror our Settings values into os.environ."""
    s = settings()
    if s.google_api_key and not os.environ.get("GEMINI_API_KEY"):
        os.environ["GEMINI_API_KEY"] = s.google_api_key
        os.environ["GOOGLE_API_KEY"] = s.google_api_key
    if s.openai_api_key and not os.environ.get("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = s.openai_api_key
    if s.anthropic_api_key and not os.environ.get("ANTHROPIC_API_KEY"):
        os.environ["ANTHROPIC_API_KEY"] = s.anthropic_api_key


def pick(tier: str = "cheap") -> str:
    """Return a LiteLLM model string."""
    s = settings()
    if tier == "smart":
        if s.google_api_key:
            return "gemini/gemini-2.5-pro"
        if s.openai_api_key:
            return "openai/gpt-4o"
        return "openai/gpt-4o-mini"
    if tier == "openai":
        return "openai/gpt-4o-mini"
    # cheap default
    if s.google_api_key:
        return "gemini/gemini-2.5-flash"
    return "openai/gpt-4o-mini"


def _fallback_chain(tier: str) -> list[str]:
    """Ordered list of models to try for a tier, from preferred to last-resort."""
    s = settings()
    chain: list[str] = []
    if tier == "smart":
        if s.google_api_key:
            chain.extend(["gemini/gemini-2.5-pro", "gemini/gemini-2.5-flash"])
        if s.openai_api_key:
            chain.append("openai/gpt-4o")
        if s.anthropic_api_key:
            chain.append("claude-sonnet-4-5")
    else:
        if s.google_api_key:
            chain.append("gemini/gemini-2.5-flash")
        if s.openai_api_key:
            chain.append("openai/gpt-4o-mini")
    return chain or ["openai/gpt-4o-mini"]


async def complete(prompt: str, *, tier: str = "cheap", system: str | None = None, max_tokens: int = 800) -> str:
    """One-shot text completion with automatic fallback across providers."""
    _ensure_env()
    import litellm

    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    last_err: Exception | None = None
    for model in _fallback_chain(tier):
        try:
            resp = await litellm.acompletion(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.3,
            )
            text = resp.choices[0].message.content or ""
            if text.strip():
                return text
        except Exception as e:
            last_err = e
            log.warning("LLM %s failed: %s", model, str(e)[:200])
            continue

    log.error("all LLM providers failed for tier=%s", tier)
    return f"(LLM error across all providers: {last_err})"
