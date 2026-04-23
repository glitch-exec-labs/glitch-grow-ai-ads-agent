# Changelog — `glitch-grow-ads-agent`

Auto-regenerated from `git log` by `/home/support/bin/changelog-regen`,
called before every push by `/home/support/bin/git-sync-all` (cron `*/15 * * * *`).

**Purpose:** traceability. If a push broke something, scan dates + short SHAs
here; then `git show <sha>` to see the diff, `git revert <sha>` to undo.

**Format:** UTC dates, newest first. Each entry: `time — subject (sha) — N files`.
Body text (if present) shown as indented sub-bullets.

---

## 2026-04-23

- **00:00 UTC** — auto-sync: 2026-04-23 00:00 UTC (`075a846`) — 1 file
        D	.claude/scheduled_tasks.lock

## 2026-04-22

- **22:45 UTC** — auto-sync: 2026-04-22 22:45 UTC (`1d14fc6`) — 2 files
        A	.claude/scheduled_tasks.lock
- **20:25 UTC** — feat(amazon_recs): retrofit to methodology-driven decomposer pipeline (`383b326`) — 3 files
    Replaces the single thin ask_report_analyst wrapper with the full
    decomposer + campaign_analyst pipeline. Every /amazon_recs <slug> call
    now drills into the top-spend campaign and produces surgical,
    entity-level recommendations instead of campaign-level blunt advice.
    Flow per invocation:
      1. list_sp_campaigns for roster + budget cap overview
      2. For the top-N (default 1) highest-budget campaigns:
           a. decompose_sp_campaign — campaign + ad-group + keyword/target/ad
              hierarchy with aggregated 14d metrics + concentration ratios
           b. analyze_campaign(brand=<slug-derived>) — methodology prompt
- **20:06 UTC** — feat(analysis): methodology-driven campaign analyst with hierarchy drill-down (`2cdc7d4`) — 1 file
    Fix the "amateur analysis" class of mistake caught by the Ayurpet founder:
    v2 recommendations said "pause Ap-TopKey-GWTH because ROAS 0.9×" while
    80% of that campaign's spend was on ONE winning keyword. The resolution
    can't be "pause the campaign"; it has to be surgical — kill the specific
    loser child, keep the hero untouched.
    New package: src/ads_agent/agent/analysis/
      - campaign_decomposer.py
        Pulls campaign → ad_group → keyword/target/product_ad tree from MAP
        with aggregated 14d metrics per child. Computes concentration ratios
        (top_child_pct_spend, top_3_pct_spend, tail_pct_spend + tail_roas,
- **20:00 UTC** — auto-sync: 2026-04-22 20:00 UTC (`0961dd0`) — 3 files
        A	src/ads_agent/agent/analysis/campaign_analyst.py
        M	src/ads_agent/agent/analysis/campaign_decomposer.py
- **19:45 UTC** — auto-sync: 2026-04-22 19:45 UTC (`991ada7`) — 3 files
        A	src/ads_agent/agent/analysis/__init__.py
        A	src/ads_agent/agent/analysis/campaign_decomposer.py
- **18:31 UTC** — feat(actions): guardrails for pause-on-paused and raise-on-undersized (`56cc49a`) — 2 files
    Fix two classes of mistake caught in QA of the 22-Apr-2026 Ayurpet report:
    1. Pause-a-dead-target: the one-off report proposed pausing 7 Meta
       campaigns/adsets that were already paused (14d insights shows spend
       from BEFORE the target was paused; written up as if still active).
    2. Raise-budget-on-undersized-campaign: 4 Amazon campaigns recommended
       for cap increases were only burning 1–15% of their existing caps —
       budget was never the throttle, bids were.
    New src/ads_agent/actions/guardrails.py:
      - assert_pause_applicable(platform, target_id, fetch_effective_status)
        Rejects pause proposals when effective_status ∈
- **18:30 UTC** — auto-sync: 2026-04-22 18:30 UTC (`513b284`) — 3 files
        A	src/ads_agent/actions/guardrails.py
        M	src/ads_agent/actions/notifier.py
- **04:02 UTC** — refactor(playbook): move per-brand playbooks to private package (`0cc1ce7`) — 3 files
    Per-brand playbooks (Ayurpet, future clients) contain tuned thresholds,
    account IDs, SKU lists, and vendor benchmarks — the "step behind" asset
    we want to keep out of public forks. The public repo now ships only
    demo.md as a format reference; the real playbooks live in the
    glitch-grow-ads-playbook package and are loaded at runtime when
    installed. .gitignore ignores playbooks/*.md except demo.md so we
    can't accidentally re-commit a real one.
- **02:25 UTC** — feat(telegram): push command menu to BotFather + add /scan_amazon to /help (`25d0f57`) — 2 files
    Telegram's '/' command-autocomplete menu is a separate per-bot setting
    from the app's CommandHandler registrations — CommandHandlers make the
    command work, but the menu needs setMyCommands called once. Previously
    only old commands were in the menu; /amazon_recs and /scan_amazon were
    invisible in the UI despite being handled by the bot.
    Adds:
      - ops/scripts/set_bot_commands.py — re-runnable helper that pushes
        the full 16-command list to BotFather via setMyCommands. Source of
        truth for the UI menu; keep in sync with bot.py registrations.
        Supports --show (read back current menu) and --clear.
- **01:45 UTC** — auto-sync: 2026-04-22 01:45 UTC (`ce10e0a`) — 7 files
        M	ops/scripts/run_action_planner.py
        M	src/ads_agent/actions/executor.py
        M	src/ads_agent/actions/models.py
        M	src/ads_agent/actions/planner.py
        M	src/ads_agent/telegram/bot.py
        ... (+1 more)
- **01:26 UTC** — feat(amazon-insights): flip /amazon Ads block to MAP, keep Seller Central on Airbyte (`eef86da`) — 2 files
    Our Airbyte Amazon Ads connection (EU region, covers IN + AE) has a
    ~56% data-loss bug (job history shows 3 failed + 2 cancelled syncs in
    the Apr 18-19 window). MAP proxies Amazon's Partner Network API
    directly and returns authoritative, hour-fresh totals.
    This commit:
      - Adds map.mcp_client.ads_totals(integration_id, account_id, days)
        — single ask_report_analyst call, structured totals, ~1s latency.
      - Switches amazon_insights_node's Amazon Ads block to MAP as primary
        data source with a transparent Airbyte fallback on MAP failure
        (plan lapse, server down).
- **00:56 UTC** — feat(amazon-recs): ask_report_analyst fallback for non-US markets (`2527cbb`) — 2 files
    Amazon's native account_recs endpoint is US-only and MAP's response
    politely points at ask_report_analyst as the fallback for other
    marketplaces. Wire that into amazon_recs_node so IN + AE (and any
    future non-US Ayurpet market) still get actionable recommendations
    instead of a dead "not available" line.
    Uses a templated prompt requesting 5 highest-impact optimization
    opportunities with specific entity names, justifying metrics, and
    one-verb action verbs — matches the SellerApp 4-bucket harvesting
    framework we codified in Section V of the playbook.
    Smoke test on ayurpet-ind returned 5 real recommendations totaling
- **00:47 UTC** — feat(amazon-recs): wire MAP MCP into /amazon_recs Telegram command (`ff6bb6b`) — 4 files
    Completes the MAP integration started in 443c842 (auto-synced). Registers
    the `amazon_recs` node in the LangGraph router, exposes `/amazon_recs
    <store>` in Telegram, and polishes the node's output so non-US market
    errors render cleanly instead of as raw JSON.
    Output is complementary to /amazon (which reads our Airbyte warehouse):
      • Enabled SP campaign roster with daily budgets, bid strategy, and
        targeting type — top 5 by budget, count of the rest.
      • Amazon's account-level recommendations (US-only; IN + AE get a
        clean "not available for this market" message pointing at the
        report_analyst fallback).
- **00:45 UTC** — auto-sync: 2026-04-22 00:45 UTC (`443c842`) — 5 files
        A	src/ads_agent/agent/nodes/amazon_recs.py
        M	src/ads_agent/config.py
        A	src/ads_agent/map/__init__.py
        A	src/ads_agent/map/mcp_client.py
- **00:39 UTC** — feat(ga4): wire first-party GA4 attribution into roas_compute (`b95cbc2`) — 5 files
    New ads_agent.ga4.client exposes a thin async wrapper over the GA4 Data
    API (run_report in a thread-pool) returning headline purchase metrics for
    a store over the last N days: revenue, currency, purchases, sessions,
    converted_sessions.
    roas_compute_node now surfaces a third GA4 ROAS line alongside Shopify
    pipeline / paid-only / Meta-reported. For stores not in
    STORE_GA4_STREAMS_JSON the GA4 block is silently skipped, so Urban
    family + Mokshya see no behavior change.
    Config additions:
      - ga4_service_account_json_path — points at the shared Vertex SA JSON
- **00:00 UTC** — auto-sync: 2026-04-22 00:00 UTC (`c7b4d70`) — 2 files
        D	.claude/scheduled_tasks.lock

## 2026-04-21

- **23:30 UTC** — auto-sync: 2026-04-21 23:30 UTC (`70557bb`) — 2 files
        A	.claude/scheduled_tasks.lock
- **21:09 UTC** — feat(playbook): inject brand brief into ideas + creative_critique nodes (`4fe3f54`) — 2 files
    Mirrors the wiring already in tracking_audit_node: loads Section X brief
    from /playbooks/<brand>.md via ads_agent.playbook.node_brief() and appends
    it to the node's system prompt as authoritative brand context.
    Closes the Shiprocket/Flexipe-style hallucination class across the
    remaining two LLM nodes — for Ayurpet the ideas + critique prompts now
    carry the codified India-D2C-supplement voice, ACOS targets, and 6-campaign
    spoke guidance instead of generic e-commerce heuristics.
    Falls back to vanilla system prompt for brands without a playbook (Urban
    family, Mokshya) so behavior there is unchanged.
    Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
- **19:56 UTC** — feat(playbook): codified Ayurpet playbook + runtime loader (`a641b06`) — 3 files
    The agent now has every Ayurpet data feed wired (Meta API, Amazon Ads via
    Airbyte, Seller Central, Shopify, Sales & Traffic, PostHog). What it lacked
    was *codified expertise* — the decision rules that turn that data into
    actions. This commit adds that layer.
    ## playbooks/ayurpet.md (574 lines)
    Ten-section markdown playbook calibrated for Ayurpet's vertical + stage,
    sourced from Canopy Management, Feedvisor, BellaVix, SellerApp, Ad Badger,
    MyAmazonGuy, Helium10 (Destaney Wishon), Jon Loomer, PPC Ninja (Ritu Java),
    Pixamp, Titan Network, upGrowth India benchmarks, and Ayurpet's own
    observed data.
- **16:06 UTC** — fix(tracking-audit): compute UTM coverage only over UTM-capable orders (`605b122`) — 2 files
    The raw UTM-coverage metric was misleadingly low for in-app-heavy brands
    like Ayurpet IN (3.8% raw). Most IN orders arrive via Meta Shop in-app
    checkout (source_name = numeric Meta app ID) where UTMs are physically
    impossible — the customer never hits the storefront URL, so there's no
    query string to tag.
    Counting those orders against the denominator made the metric appear
    catastrophically broken when tagging on the actually-taggable orders
    was already reasonable. New breakdown on Ayurpet IN:
      Before: UTM coverage = 3.8%            (87 total orders)
      After : UTM coverage = 20.0% of web     (52 web, 35 in-app excluded)
- **02:20 UTC** — refactor(actions): split tuned rules into private playbook package (`9ae49fa`) — 2 files
    Public-engine / private-playbook split for the planner. The calibrated
    thresholds and rationale copy now live in glitch-grow-ads-agent-private
    (new private sibling repo) and are loaded at import time. A generic
    stub (rules_stub.py) with deliberately-loose placeholder values keeps
    the public repo runnable end-to-end for anyone cloning it.
    Rationale: the framework is the signal, the calibration is the moat.
    README + architecture stay public (they help hiring, clients, and
    credibility); the tuned ₹ thresholds, ROAS cutoffs, and operator-facing
    rationale copy were the real proprietary edge and should never have
    been in a public file.
- **00:06 UTC** — feat(amazon-oauth): allow scope override on /api/amazon/consent-url (`878a913`) — 1 file
    Adds ?scope= query param so operators can test the OAuth plumbing with
    scope=profile (always-available on any LWA Security Profile) before the
    advertising::* scopes are approved by Amazon Ads API.
    Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

## 2026-04-20

- **23:59 UTC** — chore(amazon-oauth): return 400 on missing CLIENT_ID instead of 500 (`1654a1b`) — 1 file
    Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
- **23:58 UTC** — feat(amazon): LWA OAuth flow — state + tokens + callback receiver (`f15bcd3`) — 3 files
    First half of Amazon Ads API authorization pipeline. The receiver endpoint
    is gated by INTERNAL_API_SECRET (shared with the Cloudflare Pages Function
    at grow.glitchexecutor.com that catches Amazon's redirect).
    Data model:
    - ads_agent.amazon_oauth_state — CSRF-guarded, 10-min TTL, one-time-use
      state tokens. Agent creates; CF Function forwards + agent consumes.
    - ads_agent.amazon_oauth_tokens — long-lived refresh_tokens per account_ref,
      with scope/region/profile_ids cache. Partial unique index enforces one
      live token per account (old ones get revoked on re-auth).
    New module src/ads_agent/amazon/oauth.py:
- **22:53 UTC** — Update docs after public repo renames (`b09ca6e`) — 3 files
- **20:49 UTC** — Polish branding for Glitch Executor Labs public positioning (`44688a8`) — 1 file
- **19:57 UTC** — fix(security,data): close 6 P1/P2 audit issues (`acd09eb`) — 12 files
    Six issues filed on GitHub against v1 were all real. This fixes them.
    P1 (security + data integrity):
    - #1 Verify Telegram webhook secret. /telegram/webhook now requires
      X-Telegram-Bot-Api-Secret-Token to match TELEGRAM_WEBHOOK_SECRET via
      constant-time compare. Fail closed if unset. Without this anyone
      reaching the public endpoint could forge Updates with spoofed user
      ids, bypassing the admin gate entirely.
    - #2 Admin-only + first-click-wins approval callbacks. Callback path
      now calls is_admin() before any DB work and does the status flip
      via atomic UPDATE ... WHERE status='pending_approval' RETURNING. If
- **16:50 UTC** — fix(actions): guard executor against no-op API calls (`d1beaf3`) — 2 files
    Found during action #2 smoke-test: the target adset's parent campaign was
    already PAUSED (effective_status=CAMPAIGN_PAUSED), so pausing the adset
    would have been a pointless Meta API call that "succeeded" without doing
    anything visible.
    Two fixes:
    - Executor now pre-checks prior_state before firing any Meta API call.
      If target is already in the desired end state (already paused / already
      active / budget already at target value), we mark the action 'executed'
      with skipped_no_op=true and post a skip-notification to Telegram instead
      of "✅ executed". No Meta call made, no confusion.
- **16:39 UTC** — fix(meta-sync): use omni_purchase only in daily Meta ads snapshot (`363a93f`) — 1 file
    Third and final copy of the same bug fixed in af7f572 — sync_meta_ads.py
    had its own hardcoded PURCHASE_ACTION_TYPES set summing 5 aliases. This
    inflated meta_ads_daily.purchases and purchase_value by ~3×.
    Post-fix per-destination snapshot for Ayurpet's shared Meta account:
      Shopify Global:  spend ₹2,41,514  purchases 59  roas 1.18×
      Shopify IN:      spend ₹17,596    purchases 26  roas 1.37×
      Amazon AE:       spend ₹11,493    purchases 0   (blind)
      Amazon IN:       spend ₹6,971     purchases 0   (blind)
    These Meta-reported numbers now match Meta Ads Manager exactly, which
    matters for the founder report's per-destination attribution narrative.
- **16:26 UTC** — feat(v2): autonomous action layer — propose → approve → execute for Meta Ads (`50c11ab`) — 16 files
    First milestone of v2: the agent now closes the plan-analyze-execute-measure
    loop for Meta Ads. Every action requires explicit human approval in the
    Ayurpet X Glitch Grow Telegram supergroup; no autonomy bypass in v1.
    ## Data model
    - ads_agent.agent_actions — queue with lifecycle
      pending_approval → approved → executing → executed / failed
      (or → rejected / expired / rolled_back)
      Persists rationale, evidence, expected_impact, prior_state for every action.
    ## Agent modules (src/ads_agent/actions/)
    - models.py — ActionProposal dataclass + kind-to-MCP tool routing
- **15:55 UTC** — fix(meta): use omni_purchase only for Meta ROAS (was 3× inflated) (`af7f572`) — 2 files
    Meta Marketing API returns the same purchase event under 5 action_type aliases:
    purchase, omni_purchase, offsite_conversion.fb_pixel_purchase,
    onsite_web_purchase, onsite_web_app_purchase. Summing across them triple-counts
    the same conversions.
    Verified 2026-04-20 against act_654879327196107 last 30d:
      API purchase_roas.omni_purchase = 1.22×  (matches Ads Manager dashboard)
      Previous code (5-alias sum)     = 3.67×  (wrong)
    This was why /roas for Ayurpet showed 3.67× Meta-reported ROAS while the
    client saw 1.22× in Meta's own dashboard. The client caught it.
    Two places fixed (the code had the same bug twice, independently):
- **01:32 UTC** — attribution: dual-method ROAS (subtraction + sessions-delta) (`3d5a32e`) — 1 file
    /attribution now returns both numbers side-by-side:
      Method 1 (subtraction): meta_attributed = amz_total - amz_sp_orders,
      credited only to advertised ASINs. Upper bound.
      Method 2 (sessions-delta): zero-Meta-spend days provide a median baseline
      for orders/gross/sessions per day. Spend-day totals minus (n_spend_days ×
      baseline_per_day) = true incremental attributable to Meta.
    Divergence flag fires when the two methods disagree by > 2×:
      - Subtraction > sessions-delta  → Meta is being over-credited for organic
      - Sessions-delta > subtraction  → Meta is driving halo on non-advertised
        ASINs that subtraction misses
- **01:30 UTC** — auto-sync: 2026-04-20 01:30 UTC (`40a033e`) — 3 files
        A	ops/scripts/migrate_airbyte_amazon_traffic_view.sql
        M	src/ads_agent/agent/nodes/attribution.py

## 2026-04-19

- **04:46 UTC** — docs: reframe README around autonomous ads agent vision (`824d00f`) — 1 file
    Positioning was insights-dashboard-with-HITL-bolt-on; actual product is a
    closed-loop agent that plans, analyzes, executes, and delivers ROAS end-to-end
    across Shopify + Meta + Amazon. Human is supervisor, not the driver.
    Changes:
    - Tagline + What-this-is: lead with autonomous loop, not read-only insights
    - Features: split into v2 autonomous action layer (roadmap) and v1
      measurement substrate (shipped); call out pluggable data sources,
      pgvector memory + hybrid recall, learning-loop architecture
    - Architecture diagram: include agent core (planner / measurement / action /
      HITL / memory), add Airbyte → Postgres path for Amazon
- **04:45 UTC** — auto-sync: 2026-04-19 04:45 UTC (`a918e6b`) — 2 files
        M	README.md
- **03:45 UTC** — auto-sync: 2026-04-19 03:45 UTC (`b7895b7`) — 6 files
        A	ops/scripts/migrate_amazon_attribution_view.sql
        M	src/ads_agent/agent/graph.py
        A	src/ads_agent/agent/nodes/attribution.py
        M	src/ads_agent/telegram/bot.py
        M	src/ads_agent/telegram/handlers.py
- **02:30 UTC** — auto-sync: 2026-04-19 02:30 UTC (`5d57824`) — 5 files
        A	ops/scripts/migrate_meta_ads_daily.sql
        A	ops/scripts/sync_meta_ads.py
        A	ops/systemd/glitch-meta-ads-sync.service
        A	ops/systemd/glitch-meta-ads-sync.timer
- **02:00 UTC** — auto-sync: 2026-04-19 02:00 UTC (`473d651`) — 3 files
        M	ops/scripts/migrate_airbyte_amazon_sku_view.sql
        M	src/ads_agent/agent/nodes/amazon_insights.py
- **01:45 UTC** — auto-sync: 2026-04-19 01:45 UTC (`9e10147`) — 5 files
        A	ops/scripts/migrate_airbyte_amazon_sku_view.sql
        A	ops/scripts/migrate_airbyte_amazon_view_v4.sql
        A	ops/scripts/migrate_airbyte_amazon_view_v5.sql
        M	src/ads_agent/agent/nodes/amazon_insights.py

## 2026-04-18

- **22:30 UTC** — auto-sync: 2026-04-18 22:30 UTC (`89d51da`) — 2 files
        A	ops/scripts/cleanup_airbyte_amazon_stale_tables.sql
- **21:15 UTC** — auto-sync: 2026-04-18 21:15 UTC (`e73a9a4`) — 2 files
        A	ops/scripts/migrate_airbyte_amazon_financials_view.sql
- **00:27 UTC** — chore: update license contact to support@glitchexecutor.com (`e182404`) — 2 files
    Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
- **00:25 UTC** — chore: relicense from MIT to BSL 1.1 (`22e0e11`) — 2 files
    License converts to Apache 2.0 on 2030-04-18. Production use permitted
    except for offering as a competing hosted/embedded product.
    Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

## 2026-04-17

- **23:00 UTC** — auto-sync: 2026-04-17 23:00 UTC (`e434a16`) — 2 files
        A	ops/scripts/migrate_airbyte_amazon_view_v3.sql
- **22:00 UTC** — auto-sync: 2026-04-17 22:00 UTC (`ffe323d`) — 3 files
        A	ops/scripts/migrate_airbyte_amazon_view_v2.sql
        M	src/ads_agent/agent/nodes/amazon_insights.py
- **19:15 UTC** — auto-sync: 2026-04-17 19:15 UTC (`797bc7d`) — 2 files
        A	ops/scripts/migrate_airbyte_amazon_view.sql
- **02:26 UTC** — chore: add gitleaks pre-commit hook (`bb4bbe8`) — 1 file
    Blocks commits containing API keys, tokens, or other secrets.
    Install locally: pre-commit install
    Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
- **01:00 UTC** — auto-sync: 2026-04-17 01:00 UTC (`3aa5f0b`) — 6 files
        A	ops/scripts/migrate_amazon_daily.sql
        A	ops/scripts/sync_amazon.py
        A	ops/systemd/glitch-amazon-sync.service
        A	ops/systemd/glitch-amazon-sync.timer
        M	src/ads_agent/amazon/mcp_client.py
- **00:45 UTC** — auto-sync: 2026-04-17 00:45 UTC (`bfaa33e`) — 5 files
        M	README.md
        M	src/ads_agent/agent/nodes/amazon_insights.py
        A	src/ads_agent/amazon/mcp_client.py
        D	src/ads_agent/amazon/supermetrics_client.py
- **00:15 UTC** — auto-sync: 2026-04-17 00:15 UTC (`e9ae704`) — 2 files
        M	src/ads_agent/amazon/supermetrics_client.py
- **00:00 UTC** — auto-sync: 2026-04-17 00:00 UTC (`9281cff`) — 3 files
        M	src/ads_agent/agent/nodes/amazon_insights.py
        M	src/ads_agent/amazon/supermetrics_client.py

## 2026-04-16

- **23:30 UTC** — auto-sync: 2026-04-16 23:30 UTC (`14f8565`) — 2 files
        M	src/ads_agent/amazon/supermetrics_client.py
- **23:15 UTC** — auto-sync: 2026-04-16 23:15 UTC (`72198b1`) — 3 files
        M	src/ads_agent/agent/nodes/amazon_insights.py
        M	src/ads_agent/amazon/supermetrics_client.py
- **23:00 UTC** — auto-sync: 2026-04-16 23:00 UTC (`e146cfe`) — 7 files
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
