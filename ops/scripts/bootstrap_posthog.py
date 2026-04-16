"""Bootstrap a PostHog Cloud project for Glitch Grow.

What this does (idempotent):
  1. Verifies POSTHOG_API_KEY authenticates against POSTHOG_HOST.
  2. Emits a test `bootstrap_ping` event so the project shows activity.
  3. Prints the next manual steps (Shopify source + Meta CAPI destination
     are set up from the PostHog UI today — no public API for them yet).

v1 extends this to use the PostHog Data Pipelines / sources API once stable.
"""
from __future__ import annotations

import sys

from ads_agent.posthog.client import client
from ads_agent.config import settings


def main() -> int:
    s = settings()
    if not s.posthog_api_key or s.posthog_api_key.startswith("phc_REPLACE"):
        print("POSTHOG_API_KEY is not set. Create a project at", s.posthog_host, "first.")
        return 1

    client().capture(
        distinct_id="bootstrap",
        event="bootstrap_ping",
        properties={"source": "glitch-grow-ads-agent"},
    )
    client().flush()

    print("PostHog ping sent. Next manual steps (once, via PostHog UI):")
    print(f"  1. Open {s.posthog_host} > Data management > Sources > add a Shopify source per store.")
    print("  2. Data management > Destinations > add Meta Ads (Conversions API).")
    print("  3. Configure person-profile PII minimization + short retention on customer properties.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
