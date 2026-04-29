# Changelog — `glitch-grow-ads-agent`

Auto-regenerated from `git log` by `/home/support/bin/changelog-regen`,
called before every push by `/home/support/bin/git-sync-all` (cron `*/15 * * * *`).

**Purpose:** traceability. If a push broke something, scan dates + short SHAs
here; then `git show <sha>` to see the diff, `git revert <sha>` to undo.

**Format:** UTC dates, newest first. Each entry: `time — subject (sha) — N files`.
Body text (if present) shown as indented sub-bullets.

---

## 2026-04-29

- **23:19 UTC** — chore(redact): regen CHANGELOG after final commit-message scrub (`a950d45`) — 1 file
- **23:19 UTC** — feat(brand-registry): Phase 2 — env-driven brand registry, engine fully neutral (`011aed3`) — 3 files
    Add ads_agent/brand_registry.py as the single source of truth for slug →
    {brand_key, primary_market, shop_host, amazon_marketplace, currency}.
    Driven by STORE_BRAND_REGISTRY_JSON env var. The engine now has zero
    hardcoded brand-specific routing.
    Refactored callers:
      - playbook.py — default brand kwarg now 'default' (was a real brand name)
      - meta_audit.py — _brand_for() delegates to brand_registry.brand_for()
      - amazon_recs.py — same
      - attribution.py — slug→host, slug→amazon-marketplace, slug→currency all
        flow through the registry; FX_TO_INR table replaces hardcoded ternaries
- **23:15 UTC** — auto-sync: 2026-04-29 23:15 UTC (`261d355`) — 29 files
        M	ops/scripts/migrate_airbyte_amazon_financials_view.sql
        M	ops/scripts/migrate_airbyte_amazon_sku_view.sql
        M	ops/scripts/migrate_airbyte_amazon_traffic_view.sql
        M	ops/scripts/migrate_airbyte_amazon_view.sql
        M	ops/scripts/migrate_airbyte_amazon_view_v2.sql
        ... (+23 more)
- **23:00 UTC** — chore(redact): rename LIGHTHOUSE_CHAT_ID symbol + redact remaining comment refs (`14c324d`) — 8 files
    - Rename Python constant: LIGHTHOUSE_CHAT_ID → LIGHTHOUSE_CHAT_ID
      (used in actions/models.py + 5 importing modules)
    - Redact remaining <client> (uppercase) refs in comments
    - Smoke-tested: imports + graph compile clean
    Phase 2 still pending — 152 refs remain in source code:
      - playbook.py: default brand kwarg = '<client>'
      - meta_audit.py / amazon_recs.py: slug.startswith('<client>') router
      - attribution.py: hardcoded slug → host map (the<client>.com/.store)
                        + slug → currency (INR/AED) + slug → amazon.in/.ae
      - creative_critique.py: brand-specific prompt blocks
- **22:50 UTC** — chore(redact): regenerate CHANGELOG from rewritten commit history (`743c1bc`) — 1 file
- **22:49 UTC** — chore(redact): Phase 1 — strip client name from public-facing surfaces (`a348224`) — 18 files
    Sweep the public engine repo for hardcoded client name in:
    - README.md, pyproject.toml — narrative/docstring redaction
    - ops/scripts/*.py — example help text + docstrings
    - src/**/*.py — comments + docstrings only (behavioral code untouched)
    Phase 2 still needed: source code still has brand-specific routing
    hardcoded in playbook.py defaults, meta_audit.py / amazon_recs.py
    brand router, attribution.py slug→host map, creative_critique.py
    brand prompts, telegram/discord fallback slugs. Those need a proper
    refactor to env-driven brand registry — separate PR with tests so
    behavior is preserved.
- **22:45 UTC** — chore(docs): redact client account ids + MCC number from public surface (`1e81605`) — 2 files
    The README and changelog had leaked our Google Ads MCC number and a
    client's LinkedIn/Google ad account ids. This repo is public — those
    identifiers should never have been in commit messages or rendered docs.
    - README: replaced numeric MCC + account ids with descriptive text
    - CHANGELOG: regenerated from the rewritten commit history
    - Commit history rewritten via git filter-branch to redact the same
      patterns from older commit message bodies; force-pushed to origin
    If you have a local clone, fetch + reset:
      git fetch --tags --force
      git reset --hard origin/main
- **21:00 UTC** — Merge branch 'main' of github.com:glitch-exec-labs/glitch-grow-ai-ads-agent (`dad07ee`) — 1 file
- **21:00 UTC** — docs(readme): reflect new platform surface — Google Ads, LinkedIn Ads, native TikTok/Meta apps (`e2f3c92`) — 1 file
    What changed since the last README pass:
    - Native Google Ads (own MCC <redacted-mcc-id>) — read + write, multi-tenant
      by client linking under our manager account
    - Native LinkedIn Ads (Marketing API app with elevated access already
      approved) — read + write, multi-tenant via Manage Access
    - Native TikTok Business app, native Meta Marketing API app
    - Amazon: now via brand's own LWA (<client> personal); our Glitch Grow
      partner-tier app application is pending. Removed "Supermetrics
      fallback" wording — Supermetrics path is fully torn out
    - New public sibling: glitch-grow-linkedin-ad-mcp (MIT) — anyone can
- **20:45 UTC** — Merge branch 'main' of github.com:glitch-exec-labs/glitch-grow-ai-ads-agent (`416c1d6`) — 1 file
- **20:42 UTC** — Merge branch 'main' of github.com:glitch-exec-labs/glitch-grow-ai-ads-agent (`dbb6e39`)
- **20:42 UTC** — feat(linkedin): write API helpers — campaign group + campaign creation, status updates (`8e1ffbe`) — 2 files
    - mutations.py: create_campaign_group, create_campaign, update_*_status
      with all the LinkedIn-specific gotchas baked in (politicalIntent
      required as 202404, totalBudget min $100, runSchedule.start ≥ now,
      DRAFT campaigns inside DRAFT groups, %3A vs literal colons in URNs)
    - client.py: handle restli partial-update protocol (X-RestLi-Method
      PARTIAL_UPDATE header), surface created-entity ids from x-restli-id
      response header
    Live verified on <client> demo account <redacted-account-id>:
      group  <redacted-group-id> (DRAFT, $100)
      camp   <redacted-campaign-id> (DRAFT, TEXT_AD, $10/day)
- **20:30 UTC** — Merge branch 'main' of github.com:glitch-exec-labs/glitch-grow-ai-ads-agent (`4a82e32`) — 1 file
- **20:25 UTC** — Merge branch 'main' of github.com:glitch-exec-labs/glitch-grow-ai-ads-agent (`e28da9f`)
- **20:25 UTC** — Merge branch 'main' of github.com:glitch-exec-labs/glitch-grow-ai-ads-agent (`0ea4a6d`) — 9 files
- **19:29 UTC** — Merge branch 'main' of github.com:glitch-exec-labs/glitch-grow-ai-ads-agent (`63cae21`)
- **19:28 UTC** — feat(google_ads): native API client + agent node — multi-tenant via MCC (`6c7eab8`) — 8 files
    - google_ads/client.py: SA + quota_project override, MCC-aware client cache,
      customer_id resolver from STORE_GOOGLE_ADS_ACCOUNTS_JSON, list_mcc_clients
    - google_ads/queries.py: GAQL helpers — campaigns, keywords, search_terms,
      account_totals (returns plain dicts, cost in dollars)
    - agent/nodes/google_ads.py: /google_ads node with graceful "not yet linked"
      path that lists MCC roster as operator guidance
    - Wired into graph router + Telegram /google_ads + Discord SIMPLE_STORE_N
    Auth verified live: SA glitch-vertex-ai@capable-boulder-487806-j0 +
    quota project gen-lang-client-0187466920 (Default Gemini Project where
    dev token was approved) + Service Usage Consumer IAM grant. MCC <redacted-mcc-id>
- **19:15 UTC** — auto-sync: 2026-04-29 06:00 UTC (`871fa07`) — 2 files
        M	src/ads_agent/amazon/ads_api.py
- **05:45 UTC** — auto-sync: 2026-04-29 05:45 UTC (`96fa04e`) — 2 files
        M	src/ads_agent/amazon/ads_api.py
- **05:30 UTC** — Merge remote-tracking branch 'origin/main' (`b2fb96b`) — 1 file

## 2026-04-28

- **22:22 UTC** — Merge remote-tracking branch 'origin/main' (`6519742`)
- **22:22 UTC** — feat(amazon): migrate from MAP to native Amazon Ads API (LWA OAuth) (`33930bf`) — 8 files
    The MAP (Marketplace Ad Pros) Bearer-auth proxy is gone. All Amazon
    Ads reads + writes now go through native LWA OAuth tokens stored in
    ads_agent.amazon_oauth_tokens. Token cached on the row, profile_ids
    cached at OAuth time, access tokens refreshed on demand (1h TTL).
    ## New modules
    src/ads_agent/amazon/ads_api.py
      - profile_id_for(slug) — slug → Amazon Ads profileId resolver via
        AMAZON_ACCOUNTS_JSON marketplace mapping. Cached in-process.
      - list_sp_campaigns / list_sp_ad_groups / list_sp_keywords /
        list_sp_targets / list_sp_product_ads / list_sp_negative_keywords
- **22:15 UTC** — auto-sync: 2026-04-28 22:15 UTC (`462dfc0`) — 6 files
        M	src/ads_agent/agent/analysis/campaign_decomposer.py
        M	src/ads_agent/agent/nodes/amazon_insights.py
        M	src/ads_agent/agent/nodes/amazon_recs.py
        A	src/ads_agent/amazon/ads_api.py
        A	src/ads_agent/amazon/mutations.py
- **22:00 UTC** — Merge remote-tracking branch 'origin/main' (`8fcc2fd`) — 1 file
- **18:50 UTC** — Merge remote-tracking branch 'origin/main' (`df7e8a9`)
- **18:50 UTC** — feat(meta_audit): name-vs-URL cross-evidence — catch misnamed campaigns (`1290775`) — 4 files
    After fixing the sync-side destination_url bug, a fresh decompose surfaced
    a second class of error: campaigns named like Amazon work whose ads
    actually point at Shopify URLs. On <client>, ₹22.5k of 14d spend (13 ads
    in `final_retargeting|_amazon_uae` and `UAE - HOJ - 10thApril`) is
    operationally drift — campaigns duplicated from Amazon to Shopify but
    the names were never updated. Either signal alone misses this; together
    they catch it.
    ## What the engine now does (brand-neutral)
    src/ads_agent/meta/destinations.py — two new helpers:
      classify_name(*texts) → {amazon_intent: bool, market_hint: AE|IN|unknown}
- **18:45 UTC** — Merge remote-tracking branch 'origin/main' (`bdb00a5`) — 1 file
- **18:34 UTC** — Merge remote-tracking branch 'origin/main' (`9e1db4d`)
- **18:34 UTC** — fix(sync_meta_ads): destination_url silently nulled for ASC+ video creatives (`12a721f`) — 1 file
    The Meta sync was requesting `object_story_spec.video_data.call_to_action`
    without expanding `value{link}`. Meta returned the CTA wrapper but no
    link, so the extractor's video_data branch always got None — even when
    the destination URL existed in the API response.
    Net effect on <client> over 14 days:
      - 66 high-spend ads / ₹159k tagged as destination=NULL
      - amazon.ae spend showed as ₹7,198 in our pipeline vs ₹25k on Meta
        dashboard — 64% under-reported
      - amazon_attribution_daily_v missed half the Amazon-destined budget,
        making earlier audit halo numbers (4.00× IND, 2.94× AE) too low
- **18:30 UTC** — Merge remote-tracking branch 'origin/main' (`a9ba8fe`) — 1 file
- **02:40 UTC** — Merge remote-tracking branch 'origin/main' (`634f638`)
- **02:39 UTC** — fix(meta_audit): Phase A + B — campaign-level halo stamping + citation verifier (`3b837fc`) — 4 files
    After the per-ad halo stamp (ab99d05), the LLM still hallucinated
    campaign-level halo digits because ASC+ campaigns force campaign-level
    verdicts and the analyst was attempting weighted-mean math itself.
    Two audits of the same account quoted contradictory halos for the same
    campaigns (1.01× / 5.98× / 9.92× / 2.06× — none matching supplied data).
    ## Phase A — campaign-level halo stamping (engine)
    CampaignRow now carries:
      amazon_destined_spend
      amazon_destined_spend_pct
      amazon_halo_blended       — spend-weighted mean across the campaign's ASINs
- **02:30 UTC** — Merge remote-tracking branch 'origin/main' (`4c3c5f2`) — 1 file
- **02:25 UTC** — Merge remote-tracking branch 'origin/main' (`5dd4c18`)
- **02:24 UTC** — fix(meta_audit): stamp per-ASIN halo onto every Amazon-destined AdRow (`4cc441b`) — 2 files
    First live run of the destination-aware lens revealed the LLM sometimes
    mis-quotes per-ASIN halo numbers — picking the wrong row from
    amazon_halo.per_asin. Two audits of the same <client> account on the
    same day disagreed on which ASIN's halo applied to `UAE - AMAZON -
    GoodGut` (PAUSE quoting halo 1.01× vs SCALE quoting halo 9.92×, neither
    matching the live per_asin data which had B0FDKW4FD8 at 6.78× and
    B0G48Q6NZV at 0.0×).
    Fix: pre-resolve the per-ASIN halo at decompose time and attach to
    each AdRow:
      AdRow.target_asin_halo_roas
- **02:15 UTC** — Merge remote-tracking branch 'origin/main' (`d6a9e89`) — 1 file

## 2026-04-27

- **23:57 UTC** — Merge remote-tracking branch 'origin/main' (`4441997`)
- **23:57 UTC** — feat(meta_audit): destination tagging + Amazon halo data — engine-neutral (`1670186`) — 5 files
    Engine-level capability. Methodology (M40 / RECLAIM verb) lives in the
    <client> playbook brief only — other brands see the data but their
    briefs don't reference it, so behaviour is unchanged.
    ## What the engine now produces
      - AdRow.destination       — amazon | shopify-ind | shopify-global | other
      - AdRow.destination_url   — resolved final URL (follows amzn.eu/d/* short links)
      - AdRow.target_asin       — parsed B0XXXXXXXX ASIN when destination = amazon
      - hierarchy.destination_mix — spend/purchases/meta-ROAS per destination bucket
      - hierarchy.amazon_halo   — INR-normalised cross-channel halo from
                                  ads_agent.amazon_attribution_daily_v
- **23:45 UTC** — docs: README — dual transport, methodology audits, TikTok, 4-repo fleet (`81d1ec3`) — 2 files
    The README claimed "single Telegram surface" and "Telegram-first
    operator interface" — both stale. Updated to reflect:
      - Dual transport: same agent core serves Telegram and Discord,
        proposals dual-post and resolve atomically.
      - Methodology-driven audits: Health Score 0-100 + category bars +
        Quick Wins surfacing + stable check-IDs (M01-M35) + 2025
        platform-change awareness (Andromeda / iOS 14.5 / link-clicks
        Feb 2025 / OCAPI EOL / Threads GA).
      - TikTok integration: read commands + Meta→TikTok port workflow
        (extract winning Meta video, upload, build DISABLED launch with

## 2026-04-25

- **20:27 UTC** — docs: README — dual transport, methodology audits, TikTok, 4-repo fleet (`d7ab067`) — 1 file
    The README claimed "single Telegram surface" and "Telegram-first
    operator interface" — both stale. Updated to reflect:
      - Dual transport: same agent core serves Telegram and Discord,
        proposals dual-post and resolve atomically.
      - Methodology-driven audits: Health Score 0-100 + category bars +
        Quick Wins surfacing + stable check-IDs (M01-M35) + 2025
        platform-change awareness (Andromeda / iOS 14.5 / link-clicks
        Feb 2025 / OCAPI EOL / Threads GA).
      - TikTok integration: read commands + Meta→TikTok port workflow
        (extract winning Meta video, upload, build DISABLED launch with
- **20:18 UTC** — Merge remote-tracking branch 'origin/main' (`a597d7f`) — 1 file
    # Conflicts:
    #	CHANGELOG.md
- **20:18 UTC** — feat(meta_audit): Phase A+B engine — Health Score + Quick Wins + diversity + EMQ (`96b938e`) — 2 files
    Inspired by AgriciDaniel/claude-ads structure but adapted to our live-API
    agent. Their model is paste-export-into-Claude; we keep the live-data
    + HITL execution edge while borrowing the parts that make their reports
    client-grade: stable check-IDs, weighted health scores, severity/effort
    sorting, Andromeda awareness.
    ## Phase A — output structure
    src/ads_agent/playbook.py: load_ref(name) helper to read brand-agnostic
    reference docs from playbooks/refs/. Falls back to public repo, then
    to "" so the analyst's inline prompt remains the safety net.
    src/ads_agent/agent/analysis/meta_audit_analyst.py:
- **20:15 UTC** — auto-sync: 2026-04-25 20:15 UTC (`e26c343`) — 7 files
        A	src/ads_agent/actions/diversity.py
        M	src/ads_agent/agent/analysis/meta_audit_analyst.py
        M	src/ads_agent/agent/analysis/meta_decomposer.py
        M	src/ads_agent/agent/nodes/meta_audit.py
        A	src/ads_agent/meta/emq.py
        ... (+1 more)
- **20:00 UTC** — Merge remote-tracking branch 'origin/main' (`548ce19`) — 1 file
    # Conflicts:
    #	CHANGELOG.md
- **00:34 UTC** — Merge remote-tracking branch 'origin/main' (`f550a99`) — 1 file
    # Conflicts:
    #	CHANGELOG.md
- **00:34 UTC** — feat(actions): Discord cutover for proposal approvals — dual-post + shared resolver (`90e3214`) — 4 files
    The proposal flow used to be Telegram-only: post_proposal() took an int
    chat_id, sent to TG, persisted telegram_message_id, and the
    telegram/callbacks.py button handler resolved approve/reject. The client
    never saw any of it.
    This ships the Discord side:
      - Proposals dual-post to Telegram (legacy operator group) AND Discord
        (#glitch-x-<client> client channel) during a 48h cutover window.
      - Either platform's Approve/Reject click resolves the row atomically.
      - The shared resolver edits *both* platforms' messages so the buttons
        disappear on the side you didn't click.
- **00:30 UTC** — auto-sync: 2026-04-25 00:30 UTC (`4f8ac61`) — 6 files
        A	migrations/migrate_agent_actions_discord.sql
        A	src/ads_agent/actions/approval_targets.py
        A	src/ads_agent/actions/discord_notifier.py
        M	src/ads_agent/actions/notifier.py
        A	src/ads_agent/actions/resolver.py
- **00:15 UTC** — Merge remote-tracking branch 'origin/main' (`6296a05`) — 1 file
    # Conflicts:
    #	CHANGELOG.md

## 2026-04-24

- **21:24 UTC** — Merge remote-tracking branch 'origin/main' (`c0cb871`) — 1 file
    # Conflicts:
    #	CHANGELOG.md
- **21:23 UTC** — fix(server): address issues #7, #8, #9 (`d743638`) — 2 files
    Three Copilot-flagged issues on src/ads_agent/server.py:
    ## #7 — Shopify webhook fire-and-forget error tracking
    Previous: asyncio.ensure_future(handle_webhook(...)) — any exception in
    handler was swallowed; only surfaced as "Task exception was never
    retrieved" gc warnings. Risk: silent data loss on order events.
    Fix: new _run_webhook_safely() wraps the handler, logs structured
    errors with shop + topic, and forwards to Sentry if sentry_sdk is
    installed. Never re-raises (we've already 200'd Shopify). 200 is
    still returned fast — Shopify's 5-second window unaffected.
    ## #8 — Bearer token parsing hardening (lines 131, 182, 227, 320)
- **21:15 UTC** — auto-sync: 2026-04-24 17:30 UTC (`0a7a3f8`) — 3 files
        M	src/ads_agent/agent/nodes/ads_leaderboard.py
        M	src/ads_agent/meta/graph_client.py
- **17:30 UTC** — auto-sync: 2026-04-24 17:30 UTC (`e53fda0`) — 3 files
        M	src/ads_agent/agent/nodes/ads_leaderboard.py
        M	src/ads_agent/meta/graph_client.py
- **17:26 UTC** — fix(meta_audit): pre-flight hygiene + noise-campaign filter (`b74ddc1`) — 2 files
    Two bugs killed the first live run on <client>:
    1. Pre-flight falsely halted audit. The decomposer was emitting
       purchase_event_count_7d=-1 and purchase_event_value_sum_7d=-1.0
       whenever the audit window was not exactly 7 days (default 14d).
       The analyst correctly read -1 as "pixel broken" and refused to
       recommend. Fix: always side-pull account_spend(days=7) as an
       independent 5th parallel call and use those as the hygiene numbers,
       regardless of the audit's data window. Pixel is only flagged broken
       when 7d spend > 1000 AND (0 purchases OR 0 value) — a real
       misconfig signal, not a window-mismatch artefact.
- **17:26 UTC** — feat(meta_audit): D2C operator-grade Meta ads audit node (`6e00abb`) — 1 file
    Shape mirrors the Amazon campaign_analyst pattern we shipped last week:
    decomposer pulls the account → campaign → adset → ad hierarchy with 14d
    insights; analyst runs the brand-tuned methodology prompt from
    playbooks/<brand>.md Section X (meta_audit brief) and emits actions
    in the four-verb taxonomy: SCALE / REFRESH / PAUSE / WATCH.
    Fixes the amateur-output class:
      - Threshold is 3 × target_cpa (conversions-equivalent), not flat ₹4k
      - Breakeven ROAS is per-brand (1.6 <client>, 2.2 Urban, 2.0 Mokshya)
      - Creative fatigue (freq>2.5, 7d CTR drop>30%) → REFRESH not PAUSE
      - ASC+ campaigns judged at campaign level only; no ad-level drill
- **06:04 UTC** — feat(meta_audit): D2C operator-grade Meta ads audit node (`272b794`) — 5 files
    Shape mirrors the Amazon campaign_analyst pattern we shipped last week:
    decomposer pulls the account → campaign → adset → ad hierarchy with 14d
    insights; analyst runs the brand-tuned methodology prompt from
    playbooks/<brand>.md Section X (meta_audit brief) and emits actions
    in the four-verb taxonomy: SCALE / REFRESH / PAUSE / WATCH.
    Fixes the amateur-output class:
      - Threshold is 3 × target_cpa (conversions-equivalent), not flat ₹4k
      - Breakeven ROAS is per-brand (1.6 <client>, 2.2 Urban, 2.0 Mokshya)
      - Creative fatigue (freq>2.5, 7d CTR drop>30%) → REFRESH not PAUSE
      - ASC+ campaigns judged at campaign level only; no ad-level drill
- **06:00 UTC** — auto-sync: 2026-04-24 06:00 UTC (`e01d7bd`) — 8 files
        A	src/ads_agent/agent/analysis/meta_audit_analyst.py
        A	src/ads_agent/agent/analysis/meta_decomposer.py
        M	src/ads_agent/agent/graph.py
        A	src/ads_agent/agent/nodes/meta_audit.py
        M	src/ads_agent/meta/graph_client.py
        ... (+2 more)
- **04:30 UTC** — auto-sync: 2026-04-24 04:30 UTC (`7b5f2c7`) — 3 files
        A	.claude/worktrees/keen-lederberg-a44225
        M	ops/systemd/glitch-discord-consumer.service
- **04:15 UTC** — auto-sync: 2026-04-24 04:15 UTC (`e6da351`) — 3 files
        A	ops/systemd/glitch-discord-consumer.service
        A	tests/test_discord_dispatcher.py
- **04:00 UTC** — auto-sync: 2026-04-24 04:00 UTC (`eb98300`) — 5 files
        A	src/ads_agent/discord/__init__.py
        A	src/ads_agent/discord/dispatcher.py
        A	src/ads_agent/discord/inbox_consumer.py
        A	src/ads_agent/discord/poster.py
- **03:45 UTC** — auto-sync: 2026-04-24 03:45 UTC (`d4ec306`) — 14 files
        M	src/ads_agent/agent/graph.py
        M	src/ads_agent/agent/nodes/tiktok_common.py
        A	src/ads_agent/agent/nodes/tiktok_port_meta.py
        A	src/ads_agent/agent/workflows/__init__.py
        A	src/ads_agent/agent/workflows/port_meta_to_tiktok.py
        ... (+8 more)

## 2026-04-23

- **09:15 UTC** — auto-sync: 2026-04-23 09:15 UTC (`5824512`) — 12 files
        M	src/ads_agent/agent/graph.py
        A	src/ads_agent/agent/nodes/tiktok_campaign_budget.py
        A	src/ads_agent/agent/nodes/tiktok_campaign_status.py
        A	src/ads_agent/agent/nodes/tiktok_campaigns.py
        A	src/ads_agent/agent/nodes/tiktok_common.py
        ... (+6 more)
- **08:15 UTC** — auto-sync: 2026-04-23 08:15 UTC (`2e0f003`) — 2 files
        M	src/ads_agent/amazon/oauth.py
- **07:45 UTC** — auto-sync: 2026-04-23 07:45 UTC (`603def5`) — 2 files
        M	src/ads_agent/agent/nodes/tiktok_insights.py
- **07:30 UTC** — auto-sync: 2026-04-23 07:30 UTC (`8060c01`) — 9 files
        M	.env.example
        A	ops/scripts/migrate_tiktok_oauth.sql
        M	src/ads_agent/agent/nodes/tiktok_insights.py
        M	src/ads_agent/server.py
        M	src/ads_agent/tiktok/__init__.py
        ... (+3 more)
- **07:15 UTC** — auto-sync: 2026-04-23 07:15 UTC (`3fea934`) — 6 files
        M	.env.example
        M	src/ads_agent/agent/nodes/tiktok_insights.py
        M	src/ads_agent/config.py
        M	src/ads_agent/tiktok/client.py
        M	tests/test_smoke.py
- **07:00 UTC** — auto-sync: 2026-04-23 07:00 UTC (`55e8183`) — 11 files
        M	.env.example
        M	pyproject.toml
        M	src/ads_agent/agent/graph.py
        A	src/ads_agent/agent/nodes/tiktok_insights.py
        M	src/ads_agent/config.py
        ... (+5 more)
- **00:00 UTC** — auto-sync: 2026-04-23 00:00 UTC (`e8f0488`) — 2 files
        D	.claude/scheduled_tasks.lock

## 2026-04-22

- **22:45 UTC** — auto-sync: 2026-04-22 22:45 UTC (`368b112`) — 2 files
        A	.claude/scheduled_tasks.lock
- **20:25 UTC** — feat(amazon_recs): retrofit to methodology-driven decomposer pipeline (`e94d337`) — 3 files
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
- **20:06 UTC** — feat(analysis): methodology-driven campaign analyst with hierarchy drill-down (`b055c4f`) — 1 file
    Fix the "amateur analysis" class of mistake caught by the <client> founder:
    v2 recommendations said "pause Ap-TopKey-GWTH because ROAS 0.9×" while
    80% of that campaign's spend was on ONE winning keyword. The resolution
    can't be "pause the campaign"; it has to be surgical — kill the specific
    loser child, keep the hero untouched.
    New package: src/ads_agent/agent/analysis/
      - campaign_decomposer.py
        Pulls campaign → ad_group → keyword/target/product_ad tree from MAP
        with aggregated 14d metrics per child. Computes concentration ratios
        (top_child_pct_spend, top_3_pct_spend, tail_pct_spend + tail_roas,
- **20:00 UTC** — auto-sync: 2026-04-22 20:00 UTC (`1649e31`) — 3 files
        A	src/ads_agent/agent/analysis/campaign_analyst.py
        M	src/ads_agent/agent/analysis/campaign_decomposer.py
- **19:45 UTC** — auto-sync: 2026-04-22 19:45 UTC (`bbbdee3`) — 3 files
        A	src/ads_agent/agent/analysis/__init__.py
        A	src/ads_agent/agent/analysis/campaign_decomposer.py
- **18:31 UTC** — feat(actions): guardrails for pause-on-paused and raise-on-undersized (`4712d65`) — 2 files
    Fix two classes of mistake caught in QA of the 22-Apr-2026 <client> report:
    1. Pause-a-dead-target: the one-off report proposed pausing 7 Meta
       campaigns/adsets that were already paused (14d insights shows spend
       from BEFORE the target was paused; written up as if still active).
    2. Raise-budget-on-undersized-campaign: 4 Amazon campaigns recommended
       for cap increases were only burning 1–15% of their existing caps —
       budget was never the throttle, bids were.
    New src/ads_agent/actions/guardrails.py:
      - assert_pause_applicable(platform, target_id, fetch_effective_status)
        Rejects pause proposals when effective_status ∈
- **18:30 UTC** — auto-sync: 2026-04-22 18:30 UTC (`5013148`) — 3 files
        A	src/ads_agent/actions/guardrails.py
        M	src/ads_agent/actions/notifier.py
- **04:02 UTC** — refactor(playbook): move per-brand playbooks to private package (`f871e18`) — 3 files
    Per-brand playbooks (<client>, future clients) contain tuned thresholds,
    account IDs, SKU lists, and vendor benchmarks — the "step behind" asset
    we want to keep out of public forks. The public repo now ships only
    demo.md as a format reference; the real playbooks live in the
    glitch-grow-ads-playbook package and are loaded at runtime when
    installed. .gitignore ignores playbooks/*.md except demo.md so we
    can't accidentally re-commit a real one.
- **02:25 UTC** — feat(telegram): push command menu to BotFather + add /scan_amazon to /help (`d02f3a2`) — 2 files
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
- **01:45 UTC** — auto-sync: 2026-04-22 01:45 UTC (`44c2202`) — 7 files
        M	ops/scripts/run_action_planner.py
        M	src/ads_agent/actions/executor.py
        M	src/ads_agent/actions/models.py
        M	src/ads_agent/actions/planner.py
        M	src/ads_agent/telegram/bot.py
        ... (+1 more)
- **01:26 UTC** — feat(amazon-insights): flip /amazon Ads block to MAP, keep Seller Central on Airbyte (`812ec40`) — 2 files
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
- **00:56 UTC** — feat(amazon-recs): ask_report_analyst fallback for non-US markets (`e53391c`) — 2 files
    Amazon's native account_recs endpoint is US-only and MAP's response
    politely points at ask_report_analyst as the fallback for other
    marketplaces. Wire that into amazon_recs_node so IN + AE (and any
    future non-US <client> market) still get actionable recommendations
    instead of a dead "not available" line.
    Uses a templated prompt requesting 5 highest-impact optimization
    opportunities with specific entity names, justifying metrics, and
    one-verb action verbs — matches the SellerApp 4-bucket harvesting
    framework we codified in Section V of the playbook.
    Smoke test on store-a returned 5 real recommendations totaling
- **00:47 UTC** — feat(amazon-recs): wire MAP MCP into /amazon_recs Telegram command (`b597693`) — 4 files
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
- **00:45 UTC** — auto-sync: 2026-04-22 00:45 UTC (`9156cbd`) — 5 files
        A	src/ads_agent/agent/nodes/amazon_recs.py
        M	src/ads_agent/config.py
        A	src/ads_agent/map/__init__.py
        A	src/ads_agent/map/mcp_client.py
- **00:39 UTC** — feat(ga4): wire first-party GA4 attribution into roas_compute (`1f05eaa`) — 5 files
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
- **00:00 UTC** — auto-sync: 2026-04-22 00:00 UTC (`e509bc7`) — 2 files
        D	.claude/scheduled_tasks.lock

## 2026-04-21

- **23:30 UTC** — auto-sync: 2026-04-21 23:30 UTC (`8bf702f`) — 2 files
        A	.claude/scheduled_tasks.lock
- **21:09 UTC** — feat(playbook): inject brand brief into ideas + creative_critique nodes (`5e771c3`) — 2 files
    Mirrors the wiring already in tracking_audit_node: loads Section X brief
    from /playbooks/<brand>.md via ads_agent.playbook.node_brief() and appends
    it to the node's system prompt as authoritative brand context.
    Closes the Shiprocket/Flexipe-style hallucination class across the
    remaining two LLM nodes — for <client> the ideas + critique prompts now
    carry the codified India-D2C-supplement voice, ACOS targets, and 6-campaign
    spoke guidance instead of generic e-commerce heuristics.
    Falls back to vanilla system prompt for brands without a playbook (Urban
    family, Mokshya) so behavior there is unchanged.
    Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
- **19:56 UTC** — feat(playbook): codified <client> playbook + runtime loader (`e026ad3`) — 3 files
    The agent now has every <client> data feed wired (Meta API, Amazon Ads via
    Airbyte, Seller Central, Shopify, Sales & Traffic, PostHog). What it lacked
    was *codified expertise* — the decision rules that turn that data into
    actions. This commit adds that layer.
    ## playbooks/<client>.md (574 lines)
    Ten-section markdown playbook calibrated for <client>'s vertical + stage,
    sourced from Canopy Management, Feedvisor, BellaVix, SellerApp, Ad Badger,
    MyAmazonGuy, Helium10 (Destaney Wishon), Jon Loomer, PPC Ninja (Ritu Java),
    Pixamp, Titan Network, upGrowth India benchmarks, and <client>'s own
    observed data.
- **16:06 UTC** — fix(tracking-audit): compute UTM coverage only over UTM-capable orders (`a0235d5`) — 2 files
    The raw UTM-coverage metric was misleadingly low for in-app-heavy brands
    like <client> IN (3.8% raw). Most IN orders arrive via Meta Shop in-app
    checkout (source_name = numeric Meta app ID) where UTMs are physically
    impossible — the customer never hits the storefront URL, so there's no
    query string to tag.
    Counting those orders against the denominator made the metric appear
    catastrophically broken when tagging on the actually-taggable orders
    was already reasonable. New breakdown on <client> IN:
      Before: UTM coverage = 3.8%            (87 total orders)
      After : UTM coverage = 20.0% of web     (52 web, 35 in-app excluded)
- **02:20 UTC** — refactor(actions): split tuned rules into private playbook package (`2f9ef65`) — 2 files
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
- **00:06 UTC** — feat(amazon-oauth): allow scope override on /api/amazon/consent-url (`437cc4a`) — 1 file
    Adds ?scope= query param so operators can test the OAuth plumbing with
    scope=profile (always-available on any LWA Security Profile) before the
    advertising::* scopes are approved by Amazon Ads API.
    Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

## 2026-04-20

- **23:59 UTC** — chore(amazon-oauth): return 400 on missing CLIENT_ID instead of 500 (`ba33557`) — 1 file
    Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
- **23:58 UTC** — feat(amazon): LWA OAuth flow — state + tokens + callback receiver (`ef5267a`) — 3 files
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
- **22:53 UTC** — Update docs after public repo renames (`7cd415f`) — 3 files
- **20:49 UTC** — Polish branding for Glitch Executor Labs public positioning (`d0f5341`) — 1 file
- **19:57 UTC** — fix(security,data): close 6 P1/P2 audit issues (`77d561d`) — 12 files
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
- **16:50 UTC** — fix(actions): guard executor against no-op API calls (`d5047f8`) — 2 files
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
- **16:39 UTC** — fix(meta-sync): use omni_purchase only in daily Meta ads snapshot (`742a0c7`) — 1 file
    Third and final copy of the same bug fixed in af7f572 — sync_meta_ads.py
    had its own hardcoded PURCHASE_ACTION_TYPES set summing 5 aliases. This
    inflated meta_ads_daily.purchases and purchase_value by ~3×.
    Post-fix per-destination snapshot for <client>'s shared Meta account:
      Shopify Global:  spend ₹2,41,514  purchases 59  roas 1.18×
      Shopify IN:      spend ₹17,596    purchases 26  roas 1.37×
      Amazon AE:       spend ₹11,493    purchases 0   (blind)
      Amazon IN:       spend ₹6,971     purchases 0   (blind)
    These Meta-reported numbers now match Meta Ads Manager exactly, which
    matters for the founder report's per-destination attribution narrative.
- **16:26 UTC** — feat(v2): autonomous action layer — propose → approve → execute for Meta Ads (`d9298ed`) — 16 files
    First milestone of v2: the agent now closes the plan-analyze-execute-measure
    loop for Meta Ads. Every action requires explicit human approval in the
    <client> X Glitch Grow Telegram supergroup; no autonomy bypass in v1.
    ## Data model
    - ads_agent.agent_actions — queue with lifecycle
      pending_approval → approved → executing → executed / failed
      (or → rejected / expired / rolled_back)
      Persists rationale, evidence, expected_impact, prior_state for every action.
    ## Agent modules (src/ads_agent/actions/)
    - models.py — ActionProposal dataclass + kind-to-MCP tool routing
- **15:55 UTC** — fix(meta): use omni_purchase only for Meta ROAS (was 3× inflated) (`c51c49a`) — 2 files
    Meta Marketing API returns the same purchase event under 5 action_type aliases:
    purchase, omni_purchase, offsite_conversion.fb_pixel_purchase,
    onsite_web_purchase, onsite_web_app_purchase. Summing across them triple-counts
    the same conversions.
    Verified 2026-04-20 against act_654879327196107 last 30d:
      API purchase_roas.omni_purchase = 1.22×  (matches Ads Manager dashboard)
      Previous code (5-alias sum)     = 3.67×  (wrong)
    This was why /roas for <client> showed 3.67× Meta-reported ROAS while the
    client saw 1.22× in Meta's own dashboard. The client caught it.
    Two places fixed (the code had the same bug twice, independently):
- **01:32 UTC** — attribution: dual-method ROAS (subtraction + sessions-delta) (`579ab1a`) — 1 file
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
