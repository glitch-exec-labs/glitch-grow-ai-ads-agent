# glitch-grow-ads-agent

Systematic AI agent for Glitch Grow Shopify ads ops — cross-store insights, Shopify ↔ Meta tracking reconciliation, and HITL-gated write-actions.

Stack: **LangGraph** (orchestrator) + **Pydantic AI** (typed tools) + **PostHog Cloud** (events, identity, CAPI dedup) + **meta-ads-mcp** (Meta read/CRUD) + **Shopify Admin GraphQL** (revenue truth) + **python-telegram-bot** (operator surface) + **LiteLLM** (Claude Sonnet ↔ Gemini Flash).

Surfaces: Telegram first. PostHog-native dashboards for raw analytics. Custom Next.js dashboard deferred to v2.

Hosting: agent HTTP on **Cloud Run** (GenAI App Builder credit). Telegram webhook receiver + reconciler on this VM (localhost access to `meta-ads-mcp:3103`).

Plan: `/home/support/.claude/plans/groovy-strolling-sloth.md`
OSS research: `/home/support/.claude/plans/groovy-strolling-sloth-agent-aa26e1e224be4a066.md`

## Phasing

- **v0** — scaffolding, single-store read (`urban`), LangGraph pull_insights node, Telegram `/insights urban 7d`.
- **v1** — multi-store, webhooks, tracking audit with Gemini 2.5 Pro, HITL gate, `/roas`, `/tracking_audit`.
- **v2** — scheduled digests, proactive alerts, HITL-gated write-actions on Meta, custom Next.js dashboard.

## Local dev

```bash
cp .env.example .env   # fill secrets
uv sync                # or: python -m venv .venv && pip install -e .
uvicorn ads_agent.server:app --reload --port 3110
```

## Layout

```
src/ads_agent/
  config.py           # store registry + scope matrix
  server.py           # FastAPI: /healthz /shopify/webhook/{shop} /telegram/webhook /agent/run
  shopify/            # sessions (asyncpg), admin_gql, webhooks (HMAC)
  meta/               # mcp_client (streamable-http), capi_sender
  posthog/            # PostHog Cloud SDK wrapper
  agent/              # LangGraph graph + nodes + Pydantic AI tools + LiteLLM router
  reconcile/          # order <-> conversion matcher, metrics, remediation recipes
  telegram/           # python-telegram-bot handlers + admin auth
  scheduler/          # daily digest / nightly reconciliation entrypoints
ops/
  systemd/            # glitch-ads-bot.service
  nginx/              # example nginx vhost (swap in your own domain)
  scripts/            # bootstrap_posthog.py, register_webhooks.py
```
