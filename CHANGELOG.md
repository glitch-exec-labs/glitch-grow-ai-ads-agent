# Changelog — `glitch-grow-ads-agent`

Auto-regenerated from `git log` by `/home/support/bin/changelog-regen`,
called before every push by `/home/support/bin/git-sync-all` (cron `*/15 * * * *`).

**Purpose:** traceability. If a push broke something, scan dates + short SHAs
here; then `git show <sha>` to see the diff, `git revert <sha>` to undo.

**Format:** UTC dates, newest first. Each entry: `time — subject (sha) — N files`.
Body text (if present) shown as indented sub-bullets.

---

## 2026-04-16

- **23:00 UTC** — auto-sync: 2026-04-16 23:00 UTC (`225dc23`) — 6 files
        M	src/ads_agent/agent/graph.py
        A	src/ads_agent/agent/nodes/amazon_insights.py
        A	src/ads_agent/amazon/__init__.py
        A	src/ads_agent/amazon/supermetrics_client.py
        M	src/ads_agent/telegram/bot.py
        ... (+1 more)
- **22:30 UTC** — auto-sync: 2026-04-16 22:30 UTC (`b1cacee`) — 2 files
        M	src/ads_agent/memory/recall.py
- **22:15 UTC** — auto-sync: 2026-04-16 22:15 UTC (`0c414b3`) — 3 files
        M	src/ads_agent/agent/nodes/tracking_audit.py
        M	src/ads_agent/reconcile/recipes.py
- **21:15 UTC** — auto-sync: 2026-04-16 21:15 UTC (`a7d63af`) — 2 files
        M	src/ads_agent/meta/graph_client.py
- **21:00 UTC** — auto-sync: 2026-04-16 21:00 UTC (`0df865e`) — 3 files
        M	src/ads_agent/agent/nodes/roas_compute.py
        M	src/ads_agent/posthog/queries.py
- **20:45 UTC** — auto-sync: 2026-04-16 20:45 UTC (`31c4007`) — 4 files
        M	src/ads_agent/agent/nodes/alerts.py
        M	src/ads_agent/agent/nodes/roas_compute.py
        A	src/ads_agent/fx.py
- **20:30 UTC** — auto-sync: 2026-04-16 20:30 UTC (`b646daa`) — 6 files
        M	ops/scripts/backfill_embeddings.py
        M	src/ads_agent/agent/llm.py
        M	src/ads_agent/agent/nodes/tracking_audit.py
        M	src/ads_agent/memory/embed.py
        M	src/ads_agent/memory/recall.py
- **20:15 UTC** — auto-sync: 2026-04-16 20:15 UTC (`d36d36d`) — 9 files
        A	ops/scripts/backfill_embeddings.py
        M	src/ads_agent/agent/graph.py
        M	src/ads_agent/agent/nodes/creative_critique.py
        M	src/ads_agent/agent/nodes/ideas.py
        M	src/ads_agent/agent/nodes/tracking_audit.py
        ... (+3 more)
- **19:45 UTC** — auto-sync: 2026-04-16 19:45 UTC (`1572d2f`) — 6 files
        A	ops/scripts/migrate_agent_memory.sql
        A	src/ads_agent/memory/__init__.py
        A	src/ads_agent/memory/store.py
        M	src/ads_agent/server.py
        M	src/ads_agent/telegram/handlers.py
- **19:15 UTC** — auto-sync: 2026-04-16 19:15 UTC (`0d96d8a`) — 6 files
        M	src/ads_agent/agent/graph.py
        A	src/ads_agent/agent/nodes/alerts.py
        A	src/ads_agent/agent/nodes/ideas.py
        M	src/ads_agent/telegram/bot.py
        M	src/ads_agent/telegram/handlers.py
- **18:30 UTC** — auto-sync: 2026-04-16 18:30 UTC (`1ff45fb`) — 3 files
        M	src/ads_agent/agent/llm.py
        M	src/ads_agent/agent/nodes/creative_critique.py
- **10:45 UTC** — auto-sync: 2026-04-16 10:45 UTC (`489cb7c`) — 3 files
        M	src/ads_agent/telegram/bot.py
        M	src/ads_agent/telegram/handlers.py
- **10:30 UTC** — auto-sync: 2026-04-16 10:30 UTC (`e8acac6`) — 7 files
        M	src/ads_agent/agent/graph.py
        M	src/ads_agent/agent/llm.py
        A	src/ads_agent/agent/nodes/ads_leaderboard.py
        A	src/ads_agent/agent/nodes/creative_critique.py
        M	src/ads_agent/meta/graph_client.py
        ... (+1 more)
- **09:37 UTC** — Move store registry + ad-account map to env-loaded JSON config (`da63237`) — 5 files
    Committed code now carries only placeholder stores; real client data lives
    in .env via STORES_JSON and STORE_AD_ACCOUNTS_JSON (gitignored). Anyone can
    clone this repo, drop their own JSON into .env, and run against their own
    Shopify fleet without code edits.
    Also:
    - Add LLM fallback chain (Gemini Pro → Flash → OpenAI) so tracking_audit
      survives Gemini 503s
    - Add OPENAI_API_KEY + POSTHOG_PERSONAL_API_KEY to Settings
    - Expand .env.example to document the full runtime-config surface
    Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
- **09:30 UTC** — auto-sync: 2026-04-16 09:30 UTC (`09afc87`) — 12 files
        M	src/ads_agent/agent/graph.py
        M	src/ads_agent/agent/llm.py
        M	src/ads_agent/agent/nodes/pull_insights.py
        A	src/ads_agent/agent/nodes/roas_compute.py
        A	src/ads_agent/agent/nodes/tracking_audit.py
        ... (+6 more)
- **08:30 UTC** — auto-sync: 2026-04-16 08:30 UTC (`eb53c26`) — 3 files
        M	ops/scripts/backfill_posthog.py
        M	src/ads_agent/posthog/client.py
- **07:45 UTC** — auto-sync: 2026-04-16 07:45 UTC (`7ed7770`) — 2 files
        M	src/ads_agent/config.py
- **07:30 UTC** — auto-sync: 2026-04-16 07:30 UTC (`8ad445a`) — 3 files
        M	src/ads_agent/config.py
        M	src/ads_agent/shopify/sessions.py
- **07:00 UTC** — auto-sync: 2026-04-16 07:00 UTC (`8bf9c3b`) — 3 files
        M	ops/scripts/backfill_posthog.py
        M	ops/scripts/register_webhooks.py
- **06:45 UTC** — auto-sync: 2026-04-16 06:45 UTC (`cadb8da`) — 7 files
        A	ops/scripts/backfill_posthog.py
        M	ops/scripts/register_webhooks.py
        M	src/ads_agent/config.py
        M	src/ads_agent/posthog/client.py
        M	src/ads_agent/server.py
        ... (+1 more)
- **06:00 UTC** — auto-sync: 2026-04-16 06:00 UTC (`65bd9b9`) — 3 files
        A	LICENSE
        M	README.md
- **05:54 UTC** — Sanitize for public release: remove all client-specific data (`ba18b63`) — 8 files
    Replace real myshopify domains, Meta act_... account IDs, internal
    hostnames, and filesystem paths with generic placeholder values so
    the repo can serve as a public showcase template.
    All actual store/account mappings live in .env on the server (gitignored).
    Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
- **05:45 UTC** — auto-sync: 2026-04-16 05:45 UTC (`7559843`) — 40 files
        A	.env.example
        A	.gitignore
        A	Dockerfile
        A	README.md
        A	ops/nginx/insights.glitchexecutor.com.conf
        ... (+34 more)
