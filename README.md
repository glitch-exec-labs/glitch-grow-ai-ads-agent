# Glitch Grow Ads Agent

> **An autonomous AI ads-ops agent that plans, analyzes, executes, and delivers ROAS end-to-end** — across Shopify, Meta, and Amazon, from a single Telegram surface.

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![LangGraph](https://img.shields.io/badge/orchestrator-LangGraph-orange)](https://github.com/langchain-ai/langgraph)
[![License: BSL 1.1](https://img.shields.io/badge/License-BSL%201.1-blue.svg)](LICENSE)
[![Cloud Run ready](https://img.shields.io/badge/deploy-Cloud%20Run-4285F4?logo=google-cloud)](https://cloud.google.com/run)

---

## What this is

An **autonomous AI agent** that runs paid-media ops for a portfolio of e-commerce brands. The agent closes the full loop — it plans what to do, measures what happened, executes the next action, and learns from the outcome — with the operator supervising from Telegram rather than driving every click.

```
            ┌─────────────────────────────────────────────────┐
            │                                                 │
            │    PLAN         ANALYZE        EXECUTE          │
            │   (what to     (did it         (pause / scale   │
            │    test next)   work?)          budgets /       │
            │                                  swap creative)  │
            │       ▲                               │         │
            │       │                               ▼         │
            │     LEARN ◄────────────── MEASURE (ROAS) ────────┘
            │  (agent memory: lessons, prior decisions,
            │   per-brand behavior rules)
            └─────────────────────────────────────────────────┘
```

The human is the **supervisor**: sets constraints (budget caps, brand tone, approval thresholds), reviews the agent's proposed actions when they cross HITL gates, and gets delivered outcomes — not dashboards.

Every decision the agent makes is grounded in real revenue math across three surfaces it ties together natively:

- **Shopify** — per-store GMV, AOV, repeat-buyer cohorts, UTM coverage
- **Meta Ads** — campaign/ad-set/ad-level spend + creative + destination URLs
- **Amazon** — Seller Central orders, SP Ads performance, per-ASIN P&L, and Meta → Amazon cross-channel attribution (subtraction model where Amazon Attribution API is unavailable)

It answers the questions an ad ops manager would otherwise pay ₹50K-2L/month to a human for:

- *"What's our true blended ROAS across Meta-to-Shopify and Meta-to-Amazon for this brand?"*
- *"Which ASIN is getting disproportionate Meta clicks but no Amazon conversions — pause or iterate?"*
- *"Shopify pixel says 8× ROAS, PostHog ground truth says 0.9× — reconcile and propose the fix."*
- *"Scale Hip-O-Joint by ₹10K — but flag me first if CPC jumps > 30%."*

---

## Features

### Shopify Insights
- Pull **orders, revenue, AOV, and top SKUs** per store via Shopify Admin GraphQL
- Multi-store support — one command covers all connected storefronts
- UTM attribution coverage analysis (how many orders have a known traffic source)
- Repeat customer rate and cohort roll-up

### Meta Ads Integration
- **True ROAS** calculation: Shopify revenue ÷ Meta spend (not Meta's own reported ROAS, which over-counts)
- Campaign, ad set, and ad-level spend breakdown via [glitch-ads-mcp](https://github.com/glitch-exec-labs/glitch-ads-mcp) (our fork of meta-ads-mcp, port 3103)
- Cross-account support — single agent, multiple Meta ad accounts

### Amazon (via sibling MCP)
- Amazon Seller Central + Amazon Ads data flows through [amazon-ads-mcp](https://github.com/glitch-exec-labs/amazon-ads-mcp) (port 3105)
- Runs in **Supermetrics-fallback mode** until our native Amazon Ads LWA app is approved; switches to native SP-API without agent changes once approved
- Agent reads from a nightly Postgres cache (`ads_agent.amazon_daily`) because live Amazon Reports API queries take 2–3 minutes — unfit for inline Telegram replies

### Tracking Reconciliation & Audit
- **Order match rate**: joins Shopify orders to Meta conversion events by `order_id`
- Detects pixel-only vs. CAPI-only vs. fully-deduped events
- Surfaces dark conversions (orders Shopify recorded but Meta never saw)
- Generates remediation recipes — specific, actionable fixes (no vague advice)

### Telegram-First Operator Surface
- Dedicated bot (separate from any trading or ops bots) — right audience, right commands
- HITL (human-in-the-loop) approval gates: the agent proposes, you confirm before any write-action hits Meta
- Daily digest at 07:00 IST: GMV, spend, ROAS delta, tracking health per store
- Proactive alerts: match-rate drop >20% d/d, spend anomaly, top-SKU out-of-stock

### Human-In-The-Loop Ad Management (v2)
- `/ads <store> pause <campaign_id>` — agent drafts the action, Telegram button confirms it
- Budget adjustments, creative swaps — all logged in the agent run history
- Never touches Meta without an explicit human approval in the approval chain

---

## Three-repo fleet

This agent doesn't hold every integration itself — it delegates per-platform
work to sibling MCP servers maintained in their own repos. Clean separation
makes it easy to swap a data source (e.g. Amazon Supermetrics → native LWA)
without redeploying the agent.

| Repo | Role | Port | Status |
|---|---|---|---|
| **glitch-grow-ads-agent** (this repo) | LangGraph agent, Telegram bot, PostHog attribution, memory | `3110` | v1 live |
| [glitch-ads-mcp](https://github.com/glitch-exec-labs/glitch-ads-mcp) | Meta Ads (fork of pipeboard's meta-ads-mcp) | `3103` | live |
| [amazon-ads-mcp](https://github.com/glitch-exec-labs/amazon-ads-mcp) | Amazon Seller Central + Amazon Ads + attribution bridge. Runs in Supermetrics-fallback mode until LWA approval | `3105` | live (fallback mode) |

## Architecture

```
                  Telegram (@YourAdsBot)
                        │
          /insights  /roas  /tracking_audit  /ads
                        │
              ┌─────────▼──────────┐
              │  LangGraph Agent   │  ← Pydantic AI typed tools
              │  (state + retries  │    LiteLLM model router
              │   + HITL gates)    │    Claude Sonnet / Gemini Flash
              └──────┬─────────────┘
                     │
       ┌─────────────┼─────────────────┐
       ▼             ▼                 ▼
  PostHog Cloud  meta-ads-mcp    Shopify Admin
  (events,       (campaign        GraphQL client
   identity,      read + CRUD,    (orders, refunds,
   CAPI dedup)    spend data)     inventory)
```

**Deployment split:**
- **Cloud Run** — LangGraph agent HTTP endpoint (`/agent/run`), Cloud Scheduler jobs
- **VM / systemd** — Telegram bot + Shopify webhook receiver + reconciler (needs localhost access to `meta-ads-mcp`)
- **PostHog Cloud** — events, identity stitching, Conversions API deduplication (free tier covers most brands)

---

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| Agent orchestration | [LangGraph](https://github.com/langchain-ai/langgraph) | Durable state machine, retries, HITL — right model for ad ops workflows |
| Typed tool schemas | [Pydantic AI](https://github.com/pydantic/pydantic-ai) | Validated I/O for ad objects; swap Claude ↔ Gemini without rewriting tools |
| LLM routing | [LiteLLM](https://github.com/BerriAI/litellm) | Claude Sonnet for reasoning, Gemini 2.5 Flash for bulk, Pro for deep audits |
| CDP / attribution | [PostHog](https://github.com/PostHog/posthog) (Cloud) | Shopify source + Meta CAPI destination + identity stitching built-in |
| Meta Ads read/CRUD | [meta-ads-mcp](https://github.com/pipeboard-co/meta-ads-mcp) | MCP server for campaign data, insights, audience tools |
| Meta CAPI sends | [facebook-python-business-sdk](https://github.com/facebook/facebook-python-business-sdk) | Official SDK; sends `order_id` + `event_id` for dedup |
| Shopify data | Own GraphQL client (`~300 LoC`) | Community Shopify MCPs are all toy-tier; our auth hub holds tokens |
| Telegram interface | [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) | Webhook mode, built-in rate limiter, command routing |
| Web server | FastAPI + uvicorn | Shopify webhook receiver, Telegram webhook, Cloud Run healthz |
| Hosting | Google Cloud Run + Cloud Scheduler | Scale-to-zero, native Vertex AI / Gemini integration |

---

## Quickstart

### Prerequisites

- Python 3.11+
- A Shopify Custom App installed on each store (with `read_orders`, `read_customers`, `read_products` scopes)
- A Meta App with Marketing API access
- [meta-ads-mcp](https://github.com/pipeboard-co/meta-ads-mcp) running locally or via Cloud Run
- A PostHog Cloud account (free tier, 1M events/month)
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- Google Cloud project with Vertex AI enabled (for Gemini) or Anthropic API key (for Claude)

### Install

```bash
git clone https://github.com/glitch-exec-labs/glitch-grow-ads-agent.git
cd glitch-grow-ads-agent

# Install deps (uv recommended)
uv sync
# or: python -m venv .venv && pip install -e .
```

### Configure

```bash
cp .env.example .env
# Edit .env — all required keys documented inside
```

Key variables in `.env`:

| Variable | What it is |
|---|---|
| `POSTGRES_INSIGHTS_RO_URL` | Read-only Postgres role on the Shopify session DB |
| `SHOPIFY_WEBHOOK_SECRETS` | JSON map `{app_slug: webhook_secret}` per Custom App |
| `META_ADS_MCP_URL` | URL of your running `meta-ads-mcp` instance |
| `META_ACCESS_TOKEN` | Meta Marketing API token for CAPI sends |
| `POSTHOG_API_KEY` | PostHog Cloud project key |
| `TELEGRAM_BOT_TOKEN_ADS` | Token from BotFather for your ads bot |
| `TELEGRAM_ADMIN_IDS` | Comma-separated Telegram user IDs who can issue commands |
| `ANTHROPIC_API_KEY` | For Claude Sonnet (reasoning nodes) |
| `GOOGLE_API_KEY` | For Gemini Flash/Pro (bulk + audit nodes) |

### Configure your stores

Edit `src/ads_agent/config.py` and populate `STORES` with your real Shopify domains and Meta ad account IDs. This file stays on your server — it is not committed to the public repo.

```python
STORES = (
    Store(
        slug="brand-a",
        brand="Brand A",
        shop_domain="your-brand-a.myshopify.com",
        custom_app="brand-a",          # matches *_CLIENT_ID in your Shopify auth hub
        meta_ad_account="act_YOUR_ID",
        currency="USD",
    ),
    # add more stores ...
)
```

### Set up the read-only Postgres role

The agent reads Shopify session tokens from the auth-hub database without being able to modify them:

```sql
CREATE USER insights_ro WITH PASSWORD 'choose_strong_password';
GRANT CONNECT ON DATABASE your_shopify_db TO insights_ro;
GRANT USAGE ON SCHEMA public TO insights_ro;
GRANT SELECT ON "Session" TO insights_ro;
```

### Run locally

```bash
# Start the FastAPI server
uvicorn ads_agent.server:app --reload --port 3110

# Check it works
curl http://localhost:3110/healthz

# Start the Telegram bot in long-poll mode (dev only)
python -m ads_agent.telegram.bot
```

### Deploy to Cloud Run

```bash
docker build -t glitch-grow-ads-agent .
docker tag glitch-grow-ads-agent gcr.io/YOUR_PROJECT/glitch-grow-ads-agent
docker push gcr.io/YOUR_PROJECT/glitch-grow-ads-agent

gcloud run deploy glitch-grow-ads-agent \
  --image gcr.io/YOUR_PROJECT/glitch-grow-ads-agent \
  --region us-central1 \
  --allow-unauthenticated \
  --set-secrets="ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest,..."
```

### Set up Shopify webhooks

```bash
python ops/scripts/register_webhooks.py
# Registers ORDERS_CREATE, ORDERS_PAID, ORDERS_FULFILLED, REFUNDS_CREATE per store
```

---

## Telegram Commands

| Command | What it does |
|---|---|
| `/insights <store> [days]` | GMV, order count, AOV, top SKUs for the last N days |
| `/roas <store> <days>` | True ROAS (Shopify revenue ÷ Meta spend) vs. Meta-reported ROAS |
| `/tracking_audit <store>` | Order match rate, UTM coverage, pixel/CAPI gap, remediation recipes |
| `/scopes_check` | Shows Shopify API scopes granted per store — flags missing read_orders etc. |
| `/stores` | List all configured storefronts |
| `/daily_digest_toggle on\|off` | Subscribe/unsubscribe this chat from 07:00 IST digest |
| `/ads <store> <action>` | *(v2)* Propose a Meta write-action; requires inline HITL approval |

All commands require your Telegram user ID to be in `TELEGRAM_ADMIN_IDS`.

---

## Shopify Scope Requirements

The agent needs read scopes above Shopify's default `write_orders`:

```
read_orders, read_customers, read_products, read_analytics, read_reports
```

If any are missing, `/scopes_check` flags them and the agent degrades gracefully (funnel computed from orders + customers only, no session-level analytics on non-Plus stores).

---

## PostHog Setup

1. Create a free [PostHog Cloud](https://posthog.com) account.
2. Run the bootstrap script: `python ops/scripts/bootstrap_posthog.py`
3. In PostHog UI: **Data pipelines → Sources → Add Shopify source** per store.
4. **Data pipelines → Destinations → Add Meta Ads (Conversions API)** destination.
5. Configure PII minimization and retention TTL on customer properties (especially important for EU/India stores).

PostHog handles pixel-vs-CAPI event deduplication and person-level identity stitching out of the box. This replaces several hundred lines of custom reconciliation logic.

---

## Project Layout

```
src/ads_agent/
  config.py              # Store registry + scope matrix + Settings
  server.py              # FastAPI: /healthz, /shopify/webhook/{shop}, /telegram/webhook, /agent/run
  shopify/
    sessions.py          # asyncpg read-only access to Shopify auth-hub Session table
    admin_gql.py         # Typed Shopify Admin GraphQL client
    webhooks.py          # HMAC verification for Shopify webhook payloads
  meta/
    mcp_client.py        # HTTP client for meta-ads-mcp (streamable-http transport)
    capi_sender.py       # facebook-business-sdk CAPI sends with order_id + event_id
  posthog/
    client.py            # PostHog Cloud SDK wrapper
  agent/
    graph.py             # LangGraph state machine (pull_insights → reconcile → diagnose → HITL)
    llm.py               # LiteLLM model router (Claude Sonnet / Gemini Flash / Pro per node)
    tools.py             # Pydantic AI typed tool schemas
    nodes/               # One file per graph node
  reconcile/
    matcher.py           # Shopify order ↔ Meta conversion join (exact + fuzzy)
    metrics.py           # match_rate, CAPI gap, UTM coverage, true vs. reported ROAS
    recipes.py           # Canned remediation strings surfaced by /tracking_audit
  telegram/
    bot.py               # python-telegram-bot Application bootstrap
    handlers.py          # Command handlers
    auth.py              # Admin-only guard (TELEGRAM_ADMIN_IDS)
  scheduler/
    digest.py            # Daily digest + nightly reconciliation entrypoints
ops/
  systemd/               # systemd unit for on-VM Telegram bot + webhook receiver
  nginx/                 # Example nginx reverse-proxy vhost
  scripts/               # bootstrap_posthog.py, register_webhooks.py
```

---

## Roadmap

- [x] **v0** — Repo scaffold, store registry, LangGraph skeleton, `/insights` Telegram command, FastAPI `/healthz`
- [ ] **v1** — Multi-store webhooks live, HMAC verification, Meta ROAS cross-ref, `/tracking_audit` with Gemini 2.5 Pro, HITL gate wired
- [ ] **v2** — Cloud Scheduler daily digest + proactive alerts, HITL-gated Meta write-actions (`/ads pause|budget`), Next.js dashboard (ROAS roll-up, agent run log, HITL approval inbox)

---

## Why LangGraph over CrewAI / AutoGen?

Ad operations is a **state machine**, not a conversation:

```
pull_insights → reconcile → diagnose → propose_action → [HITL gate] → ads_write
```

LangGraph gives you durable checkpoints (surviving restarts between HITL steps), per-node model selection, and retries with exponential backoff — exactly what you want before the agent touches a live Meta campaign. CrewAI's role-framing and AutoGen's conversation model are the wrong abstraction here.

---

## Contributing

Issues and PRs welcome. For major changes, open an issue first to discuss the approach.

```bash
# Lint
ruff check src/ tests/

# Type-check
mypy src/

# Tests
pytest
```

---

## License

Business Source License 1.1 — see [LICENSE](LICENSE). Converts to Apache 2.0 on 2030-04-18. Production use is permitted except for offering the software as a competing hosted/embedded product. For commercial licensing, contact support@glitchexecutor.com.

---

*Built by [Glitch Executor Labs](https://glitchexecutor.com) — AI-powered e-commerce operations.*
