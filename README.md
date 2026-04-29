# Glitch Grow AI Ads Agent

> **An AI ads agent for Shopify and e-commerce brands that plans, analyses, executes, and improves ROAS end-to-end** — across Shopify, Meta, Amazon, TikTok, Google Ads, and LinkedIn Ads, controllable from Telegram **or** Discord.

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![LangGraph](https://img.shields.io/badge/orchestrator-LangGraph-orange)](https://github.com/langchain-ai/langgraph)
[![License: BSL 1.1](https://img.shields.io/badge/License-BSL%201.1-blue.svg)](LICENSE)
[![Cloud Run ready](https://img.shields.io/badge/deploy-Cloud%20Run-4285F4?logo=google-cloud)](https://cloud.google.com/run)

---

> Part of **Glitch Grow**, the digital marketing domain inside **Glitch Executor Labs** — one builder shipping products across **Trade**, **Edge**, and **Grow**.

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

Every decision the agent makes is grounded in real revenue math across the surfaces it ties together natively:

- **Shopify** — per-store GMV, AOV, repeat-buyer cohorts, UTM coverage
- **Meta Ads** — campaign/ad-set/ad-level spend + creative + destination URLs (native Marketing API app)
- **Amazon** — Seller Central orders, SP Ads performance, per-ASIN P&L, and Meta → Amazon cross-channel attribution (native Ads API on the brand's own LWA approval; our Glitch Grow partner-tier app is pending)
- **TikTok Ads** — native Business API app: campaigns, ad-sets, ads, pixels, creative upload, Meta→TikTok port flow
- **Google Ads** — native Google Ads API on our own Manager (MCC) account. Clients link their account once; we read + write across the whole portfolio without per-tenant OAuth
- **LinkedIn Ads** — native Marketing API app with elevated access already approved. Read + write campaigns, groups, analytics. Same pattern as Google: client adds our user via Manage Access, no fresh app approval needed on their end

### Use it for your brand (managed-service offer)

The agent currently runs production paid-media ops for **Ayurpet**
across Shopify, Meta, Amazon, TikTok, Google Ads, and LinkedIn Ads.
We're now opening it up: if you want the same agent operating your ad
accounts under your supervision, reach out at
<https://grow.glitchexecutor.com> · `support@glitchexecutor.com`.

Onboarding is the same pattern across every platform — you grant our
already-approved apps access to your accounts (Meta Business Manager
partner add, Google MCC link, LinkedIn Manage Access, TikTok BC partner,
Amazon LWA install) and we wire your store slug into the agent's
`STORE_*_JSON` config files. **No fresh app approvals on your side, no
waiting on platform review queues.** Your access can be revoked
instantly from each platform's UI if you ever want to stop.

---

It answers the questions an ad ops manager would otherwise pay ₹50K-2L/month to a human for:

- *"What's our true blended ROAS across Meta-to-Shopify and Meta-to-Amazon for this brand?"*
- *"Which ASIN is getting disproportionate Meta clicks but no Amazon conversions — pause or iterate?"*
- *"Shopify pixel says 8× ROAS, PostHog ground truth says 0.9× — reconcile and propose the fix."*
- *"Scale Hip-O-Joint by ₹10K — but flag me first if CPC jumps > 30%."*

---

## Features

### Autonomous decision loop (v2, in progress)
- Agent runs hourly evaluation cycles per brand — ingests fresh spend/revenue/session data, diagnoses drift vs. expectation, proposes the minimum-risk next action
- Executes write-actions (pause, scale budget ±X%, swap primary creative) via platform APIs once a brand-specific **autonomy threshold** is cleared
- Below-threshold actions are queued for Telegram HITL approval with a one-click accept
- Every action writes a durable decision record in `ads_agent.agent_memory` with rationale, alternatives considered, and predicted outcome — feeds the learning loop

### Measurement substrate (v1, shipped)
- **True ROAS** per channel: Shopify revenue ÷ Meta spend via PostHog ground truth (not Meta's own over-reported number)
- **Meta → Amazon attribution** via subtraction model (`total_amazon_orders − amazon_sp_ads_orders`) for brands without Amazon Attribution API access
- **Per-SKU P&L** joining Amazon OrderItems × Listings × productads with currency-normalized ROAS across IN/AE/UK/EU marketplaces
- **Tracking reconciliation**: Shopify orders joined to Meta conversion events by `order_id`; surfaces pixel-only vs CAPI-only events and generates specific remediation recipes

### Pluggable data-source architecture
- Meta Ads via [glitch-ads-mcp](https://github.com/glitch-exec-labs/glitch-ads-mcp) (fork of pipeboard/meta-ads-mcp, port 3103)
- Amazon Seller + Ads via Airbyte Cloud → Postgres (24 streams, dedup'd + typed views in `ads_agent.*`); sibling [amazon-ads-mcp](https://github.com/glitch-exec-labs/amazon-ads-mcp) kept for ad-hoc Claude Code exploration and for eventual Amazon Attribution API activation
- Shopify via owned asyncpg reader against the auth-hub `Session` table + typed GraphQL client
- Swapping a data source (e.g. Amazon Airbyte → native LWA once approved) is a server-side change with zero agent redeploy

### Memory + learning
- `ads_agent.agent_memory` with pgvector (HNSW cosine) and tsvector FTS — every agent turn indexed for hybrid recall
- Every command injects `<prior_context>` from relevant past turns before prompting the LLM — agent starts each decision with "last time we faced X, we did Y, outcome was Z"
- Nightly consolidation cron scores memories on relevance/frequency/diversity/recency/consolidation and promotes durable lessons to per-brand `MEMORY.md` files loaded as system prompt context

### Dual transport: Telegram + Discord
- Same agent core, two control planes. Diagnostic commands and write-action approvals work from either Telegram (`@GlitchGrowAdsBot`) or Discord (`#grow-ads`, plus per-client channels like `#glitch-x-ayurpet`).
- Action proposals **dual-post** with Approve/Reject buttons; either side resolves the row atomically and strips buttons on the other (first-click-wins via DB-level constraint).
- Discord lets clients self-serve audits (`/insights`, `/amazon_recs`, `/meta_audit`) without giving them ops-team access. Per-channel approver allowlists keep write authority scoped.

### Methodology-driven audits, not vibes
- `/meta_audit` and `/amazon_recs` run a **decomposer** (account → campaign → adset → ad with 14d rollup + concentration analysis) followed by a brand-tuned methodology analyst.
- Output leads with a **Health Score 0-100** and category bars (Pixel/CAPI 30% · Creative 30% · Structure 20% · Audience 20%), then **Quick Wins** (high-severity × low-effort), then full per-campaign drill.
- Every recommendation cites a stable check-ID (M01-M35) so week-over-week deltas are tractable.
- 2025 platform-change awareness baked in: Andromeda creative-diversity (Oct 2025), iOS 14.5 dedup, link-clicks redefinition (Feb 2025), Offline Conversions API EOL, Threads GA, AEM v2.

### TikTok integration (native Business API app)
- Read: `/tiktok`, `/tiktok_campaigns`, `/tiktok_pixels`, `/tiktok_campaign_status`, `/tiktok_campaign_budget`.
- Write: `/port_meta_to_tiktok <meta_ad_id> <slug>` — extracts a winning Meta video, uploads to TikTok, creates campaign + adset + ad in DISABLED state with the right pixel optimization event auto-picked. `/enable_tiktok_launch <manifest_id>` flips it live after HITL review.

### Google Ads integration (native API on our MCC)
- Read: `/google_ads <store> [days]` — account totals, top campaigns by spend, zero-conversion search terms (negative-keyword candidates), per-keyword performance.
- Write helpers: campaign budget + Search/Performance Max campaign creation, ad-group + keyword mutations (BROAD/PHRASE/EXACT). All EU-political-ad declaration handled.
- Multi-tenant via our Glitch Grow MCC: client requests link from their Google Ads account → we approve → their `customer_id` goes into `STORE_GOOGLE_ADS_ACCOUNTS_JSON` → `/google_ads <slug>` works the next second.

### LinkedIn Ads integration (native Marketing API app)
- Read: `/linkedin_ads <store> [days]` — account totals, campaign roster, per-creative metrics via `/rest/adAnalytics`.
- Write helpers: campaign-group + campaign creation with all the LinkedIn-specific gotchas codified (`politicalIntent`, $100 minimum totalBudget, runSchedule.start ≥ now, DRAFT-in-DRAFT cascade, restli URL encoding).
- Multi-tenant via Campaign Manager → **Manage Access**: client adds our LinkedIn user as `CAMPAIGN_MANAGER` → their account_id goes into `STORE_LINKEDIN_ADS_ACCOUNTS_JSON` → live.
- The same surface is published as a public MCP server at [glitch-grow-linkedin-ad-mcp](https://github.com/glitch-exec-labs/glitch-grow-linkedin-ad-mcp) so any MCP client (Claude Desktop, Cursor, your own agent) can use the LinkedIn Marketing API without going through their own approval queue.

### Per-brand playbook system
- Tuned thresholds (`breakeven_roas`, `target_roas`, `target_cpa`) live in private playbooks per brand, not hardcoded in the engine. Ayurpet pet-supplements (1.6/2.8 breakeven/target) ≠ Urban apparel (2.2/3.5) ≠ Mokshya (2.0/3.2). Engine is brand-agnostic; calibration ships separately.

### Proactive alerts
- CPC drift, match-rate drop > 20% d/d, ROAS drop > 30% w/w, zero-purchase burners, premature-kill bias warnings, daily 07:00 IST digest per store.

---

## Multi-repo fleet

This agent doesn't hold every integration itself — it delegates per-platform
work to sibling repos. Clean separation makes it easy to swap a data source
without redeploying the agent.

| Repo | Role | Port | Status |
|---|---|---|---|
| **glitch-grow-ai-ads-agent** (this repo) | LangGraph agent, Telegram + Discord transports, PostHog attribution, memory, native Google Ads + LinkedIn Ads + TikTok clients | `3110` | v2 live |
| [glitch-ads-mcp](https://github.com/glitch-exec-labs/glitch-ads-mcp) | Meta Ads MCP (fork of pipeboard's meta-ads-mcp) | `3103` | live |
| [amazon-ads-mcp](https://github.com/glitch-exec-labs/amazon-ads-mcp) | Amazon Seller Central + Amazon Ads + attribution bridge | `3105` | live (native LWA on Ayurpet's personal API access; our Glitch Grow partner-tier application pending) |
| [glitch-grow-linkedin-ad-mcp](https://github.com/glitch-exec-labs/glitch-grow-linkedin-ad-mcp) | Public MCP server for LinkedIn Marketing API. Anyone can pip-install it and connect our hosted (already-approved) app to skip LinkedIn's Marketing API approval queue | n/a | public, MIT |
| [glitch-discord-bot](https://github.com/glitch-exec-labs/glitch-discord-bot) | Guild slash commands + channel→JSON inbox fanout that the agent's Discord consumer reads | n/a | live |

TikTok and Google Ads + LinkedIn Ads are **in-process native clients** in
this repo (`ads_agent/tiktok/`, `ads_agent/google_ads/`,
`ads_agent/linkedin/`) — no separate sibling needed. ClickUp + Metabase
are post-processing surfaces driven by ad-hoc scripts under `/tmp/`.

## Architecture

```
       Telegram (operator)            Discord (#grow-ads · #glitch-x-<brand>)
            ▲                                       ▲
            │ commands + HITL                       │ commands + HITL
            ▼                                       ▼
  python-telegram-bot              glitch-discord-bot (sibling)
  (webhook mode + secret)        ↓ writes JSON to inbox/
                                   ads_agent.discord.inbox_consumer
            ▼                                       ▼
        ┌──────────────────────────────────────────────────┐
        │           LangGraph Agent Core                   │   recall → route → execute
        │   ─────────────────────────────────              │   every turn injects <prior_context>
        │   • planner / router                             │   LiteLLM: Gemini 2.5 Pro / Sonnet / Flash
        │   • methodology nodes (meta_audit, amazon_recs)  │
        │   • measurement nodes                            │
        │   • action nodes + HITL gate                     │
        │   • cross-platform approval resolver             │
        │   • memory (pgvector + FTS)                      │
        └──────┬───────────────────────────────────────────┘
               │
   ┌───────────┼─────────────┬──────────────┬──────────────┬───────────────┐
   ▼           ▼             ▼              ▼              ▼               ▼
 PostHog   Meta Graph   Airbyte→Postgres   MAP API     TikTok Business   Shopify Admin
 (events,   (read +     (Amazon Seller     (Amazon     (campaign /        GraphQL
  CAPI,      CAPI write   + Ads, dedup'd    Ads CRUD,   adset / ad CRUD,  + Session DB
  identity)  via MCP)     views)            authoritative) creative upload)
                                  │
                                  ▼
                          ads_agent.*_daily_v
                       (deduped, typed views;
                        attribution math, SKU P&L)
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
git clone https://github.com/glitch-exec-labs/glitch-grow-ai-ads-agent.git
cd glitch-grow-ai-ads-agent

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
| `POSTGRES_INSIGHTS_RO_URL` | **Read-only** Postgres role on the Shopify auth-hub DB — used ONLY to read the `Session` table |
| `POSTGRES_RW_URL` | **Writable** Postgres role that owns `ads_agent.*` (agent_memory, agent_actions). All agent writes go here. In dev you may leave this blank and both roles collapse to `POSTGRES_INSIGHTS_RO_URL`, but in prod the two MUST be separate |
| `SHOPIFY_WEBHOOK_SECRETS` | JSON map `{app_slug: webhook_secret}` per Custom App |
| `META_ADS_MCP_URL` | URL of your running `meta-ads-mcp` instance |
| `META_ACCESS_TOKEN` | Meta Marketing API token for CAPI sends |
| `POSTHOG_API_KEY` | PostHog Cloud project key |
| `TELEGRAM_BOT_TOKEN_ADS` | Token from BotFather for your ads bot |
| `TELEGRAM_ADMIN_IDS` | Comma-separated Telegram user IDs who can issue commands **and approve/reject action proposals** |
| `TELEGRAM_WEBHOOK_SECRET` | Random string you pass to Telegram's `setWebhook?secret_token=...`. The server rejects any webhook update without this header — without it anyone can forge Telegram updates |
| `AGENT_RUN_TOKEN` | Bearer token required to call `POST /agent/run`. If unset the endpoint is disabled. In Cloud Run, also gate with IAM — never deploy `/agent/run` as `--allow-unauthenticated` |
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

### Set up the two Postgres roles

The agent needs **two** database roles with distinct privileges. Do not merge them.

**1. `insights_ro` — read-only on the Shopify auth-hub DB.** Used only to read the `Session` table (Shopify access tokens per shop):

```sql
CREATE USER insights_ro WITH PASSWORD 'choose_strong_password';
GRANT CONNECT ON DATABASE your_shopify_db TO insights_ro;
GRANT USAGE ON SCHEMA public TO insights_ro;
GRANT SELECT ON "Session" TO insights_ro;
```

Point `POSTGRES_INSIGHTS_RO_URL` at this role.

**2. `ads_agent_rw` — writable on `ads_agent.*`.** Used for agent memory, action proposals, approval state transitions, and executor result writes. This can live in the same Postgres instance or a separate one:

```sql
CREATE USER ads_agent_rw WITH PASSWORD 'choose_strong_password';
GRANT CONNECT ON DATABASE your_db TO ads_agent_rw;
GRANT USAGE, CREATE ON SCHEMA ads_agent TO ads_agent_rw;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA ads_agent TO ads_agent_rw;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA ads_agent TO ads_agent_rw;
ALTER DEFAULT PRIVILEGES IN SCHEMA ads_agent
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ads_agent_rw;
```

Point `POSTGRES_RW_URL` at this role. If you leave `POSTGRES_RW_URL` blank the agent falls back to `POSTGRES_INSIGHTS_RO_URL` for writes — this is intentional so local dev works with a single superuser DSN, but against a correctly-locked `insights_ro` role every write path will fail.

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
docker build -t glitch-grow-ai-ads-agent .
docker tag glitch-grow-ai-ads-agent gcr.io/YOUR_PROJECT/glitch-grow-ai-ads-agent
docker push gcr.io/YOUR_PROJECT/glitch-grow-ai-ads-agent

gcloud run deploy glitch-grow-ai-ads-agent \
  --image gcr.io/YOUR_PROJECT/glitch-grow-ai-ads-agent \
  --region us-central1 \
  --no-allow-unauthenticated \
  --set-secrets="ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest,TELEGRAM_WEBHOOK_SECRET=TELEGRAM_WEBHOOK_SECRET:latest,AGENT_RUN_TOKEN=AGENT_RUN_TOKEN:latest,..."
```

**Do not use `--allow-unauthenticated`.** The service exposes:

- `POST /telegram/webhook` — must be reachable by Telegram. Protect it by configuring Telegram with `setWebhook?secret_token=<TELEGRAM_WEBHOOK_SECRET>`; the server rejects updates without that header.
- `POST /shopify/webhook/{shop}` — must be reachable by Shopify. Protected by per-app HMAC via `SHOPIFY_WEBHOOK_SECRETS`.
- `POST /agent/run` — internal only. Requires `Authorization: Bearer <AGENT_RUN_TOKEN>`. Prefer Cloud Run IAM + a signed internal gateway as a second layer.
- `GET  /healthz` — safe to expose.

If you need Telegram/Shopify to reach the webhook endpoints on an IAM-gated service, put Cloud Run behind an HTTPS load balancer with per-path policies, or terminate webhooks on a VM and keep the LangGraph service fully IAM-private.

### Register the Telegram webhook with a secret token

```bash
curl "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN_ADS}/setWebhook" \
  -d "url=${PUBLIC_BASE_URL}/telegram/webhook" \
  -d "secret_token=${TELEGRAM_WEBHOOK_SECRET}"
```

Telegram will now include `X-Telegram-Bot-Api-Secret-Token: ${TELEGRAM_WEBHOOK_SECRET}` on every delivery. The server rejects any update that lacks it.

### Set up Shopify webhooks

```bash
python ops/scripts/register_webhooks.py
# Registers ORDERS_CREATE, ORDERS_PAID, ORDERS_FULFILLED, REFUNDS_CREATE per store
```

---

## Commands

All commands work from both Telegram and Discord (in any agent or
client channel that's wired into `DISCORD_CONSUMER_CHANNELS`). Telegram
admins are gated by `TELEGRAM_ADMIN_IDS`; Discord approvers by
`DISCORD_APPROVER_USER_IDS_JSON`.

### Diagnostic / read

| Command | What it does |
|---|---|
| `/insights <store> [days]` | GMV, orders, AOV, UTM coverage, repeat rate (Shopify + PostHog) |
| `/roas <store> [days]` | Pipeline / paid-only / Meta-reported / GA4 ground-truth ROAS — four numbers, four perspectives |
| `/tracking_audit <store> [days]` | LLM-picked remediation recipes for pixel/CAPI gaps |
| `/ads <store> [days]` | Top-10 ad leaderboard by spend with deep-link to `/creative <ad_id>` |
| `/creative <ad_id> [store]` | Gemini vision critique of thumbnail + body + metrics |
| `/ideas <store> [days]` | 5 numbered creative briefs based on winning patterns |
| `/alerts <store>` | CPC drift, spend-up/rev-flat, zero-purchase burners, premature-kill reminders |
| `/amazon <store> [days]` | Amazon Seller + Ads rollup per marketplace |
| `/attribution <store> [days]` | Meta → Amazon attribution (subtraction model + sessions-delta when data allows) |
| `/stores` | List all configured storefronts |

### Methodology-driven audits

| Command | What it does |
|---|---|
| `/meta_audit <store> [days]` | Operator-grade D2C Meta audit — Health Score 0-100 + category bars + Quick Wins + per-campaign drill. Cites check-IDs (M01-M35); aware of Andromeda + iOS 14.5 + Feb 2025 link-click redefinition |
| `/amazon_recs <store>` | Surgical Amazon SP recommendations via the campaign decomposer + analyst. Returns concrete actions at the right entity level (keyword / product_ad / product_target / campaign) |

### TikTok

| Command | What it does |
|---|---|
| `/tiktok <store> [days]` | Advertiser snapshot + paid media totals |
| `/tiktok_campaigns <store> [limit]` | List campaigns with status / objective / budget |
| `/tiktok_pixels <store> [limit]` | List pixels and the events each fires |
| `/tiktok_campaign_status <store> <campaign_id> <enable\|disable>` | Flip campaign status |
| `/tiktok_campaign_budget <store> <campaign_id> <amount>` | Change campaign budget |
| `/port_meta_to_tiktok <meta_ad_id> <slug> landing=<url> text="..." name=<display>` | Extract a winning Meta video and create a DISABLED TikTok Conversions launch with auto-picked optimization event |
| `/enable_tiktok_launch <manifest_id>` | HITL gate: flip a built TikTok launch live |

### Autonomous action layer (HITL)

| Command | What it does |
|---|---|
| `/plan [store]` | Show pending action proposals awaiting Approve/Reject |
| `/actions [store]` | Recent executed / rejected / failed actions |
| `/scan_amazon <store>` | Trigger Amazon waste-reduction scan → proposals |

The planner runs every 4 hours; proposals dual-post to Telegram and to
the brand's Discord client channel. Either side's button click resolves
the row atomically; the executor runs within 5 minutes after approval.

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

- [x] **v0** — Repo scaffold, store registry, LangGraph skeleton, Shopify webhook receivers, FastAPI `/healthz`
- [x] **v1** — All 9 diagnostic commands live: `/insights`, `/roas`, `/tracking_audit`, `/ads`, `/creative`, `/ideas`, `/alerts`, `/amazon`, `/attribution`. Amazon Seller + Ads + cross-channel (Meta → Amazon) attribution wired via Airbyte direct. pgvector memory substrate with hybrid recall. Daily cron for Meta ads destination-URL snapshot.
- [ ] **v2 (in progress)** — Autonomous action layer: per-brand autonomy thresholds, agent-proposed write-actions (pause / scale budget / swap creative), HITL approval inbox in Telegram, structured decision log in `agent_memory.kind='action_*'`. Weekly alert rules, Amazon session-refined attribution once `GET_SALES_AND_TRAFFIC_REPORT` lands.
- [ ] **v3** — Creative generation loop: agent writes + renders new Meta ad creatives (Gemini + Imagen/Flux) based on observed winning patterns, ships them for HITL review, tracks lift. Cross-channel brand ROAS dashboard (Shopify + Amazon combined sales vs Meta + Amazon Ads combined spend).

---

## Why LangGraph over CrewAI / AutoGen?

Autonomous ad ops is a **state machine**, not a conversation:

```
recall → measure → diagnose → plan_action → [HITL gate if > threshold] → execute → observe → memorize
```

LangGraph gives:
- **Durable checkpoints** — state survives restarts between HITL approvals (critical when an action sits in the approval queue for hours)
- **Per-node model selection** — route reasoning nodes to Gemini 2.5 Pro, bulk-summary nodes to Flash, parse-only nodes to GPT-4o-mini; cost scales with cognitive demand
- **Deterministic retries with exponential backoff** — non-negotiable before the agent touches a live Meta budget
- **Conditional entry points** — one graph serves 12+ command types without rebuilding

CrewAI's role-framing pattern and AutoGen's conversation model are the wrong abstractions for a system that must make the same call reproducibly and audit-ably whether a human or a scheduler triggered it.

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
