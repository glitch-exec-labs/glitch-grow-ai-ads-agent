# Changelog — `glitch-grow-ads-agent`

Auto-regenerated from `git log` by `/home/support/bin/changelog-regen`,
called before every push by `/home/support/bin/git-sync-all` (cron `*/15 * * * *`).

**Purpose:** traceability. If a push broke something, scan dates + short SHAs
here; then `git show <sha>` to see the diff, `git revert <sha>` to undo.

**Format:** UTC dates, newest first. Each entry: `time — subject (sha) — N files`.
Body text (if present) shown as indented sub-bullets.

---

## 2026-04-16

- **07:45 UTC** — auto-sync: 2026-04-16 07:45 UTC (`2bb2aad`) — 1 file
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
