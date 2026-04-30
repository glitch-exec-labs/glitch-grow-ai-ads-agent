#!/usr/bin/env bash
# Urban-family underperformer watch — runs every 30 min via cron.
# Posts alerts to #urban-family-alert (Discord) when an active ad has
# lifetime spend ≥ $20 and < 4 purchases. Alert-only, no auto-pause.
set -euo pipefail

cd /home/support/glitch-grow-ads-agent
exec .venv/bin/python -m ads_agent.actions.underperformer_watch "$@"
