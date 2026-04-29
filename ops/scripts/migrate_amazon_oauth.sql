-- Amazon Ads LWA OAuth — state (CSRF) table + long-lived token store.
--
-- Flow:
--   1. Agent generates `state` (random uuid), inserts a row into amazon_oauth_state
--      with expires_at = now + 10min, returns the consent URL.
--   2. User clicks consent URL at amazon.com/ap/oa → Amazon redirects to
--      grow.glitchexecutor.com/amazon/oauth/callback?code=X&state=Y.
--   3. Cloudflare Pages Function forwards {code, state} to agent's
--      /api/amazon/oauth/receive. Agent looks up state, validates, exchanges
--      code for refresh_token, stores in amazon_oauth_tokens, marks state used.
--
--   Security:
--     - state is one-time-use (marked used_at after success)
--     - state expires after 10min
--     - CF→agent POST is gated by Bearer INTERNAL_API_SECRET
--     - refresh_tokens are store at rest in Postgres; access via DB role only

CREATE TABLE IF NOT EXISTS ads_agent.amazon_oauth_state (
    state         text        PRIMARY KEY,          -- random uuid v4
    created_at    timestamptz NOT NULL DEFAULT NOW(),
    expires_at    timestamptz NOT NULL DEFAULT NOW() + INTERVAL '10 minutes',
    used_at       timestamptz,                      -- NULL until consumed
    account_ref   text,                             -- optional hint: who this authorization is for (e.g. "<client>")
    scope         text,                             -- e.g. "advertising::campaign_management advertising::account_management"
    notes         text
);

CREATE INDEX IF NOT EXISTS amazon_oauth_state_expires_idx
    ON ads_agent.amazon_oauth_state (expires_at);


CREATE TABLE IF NOT EXISTS ads_agent.amazon_oauth_tokens (
    id                bigserial PRIMARY KEY,
    created_at        timestamptz NOT NULL DEFAULT NOW(),
    updated_at        timestamptz NOT NULL DEFAULT NOW(),

    -- Who/what this token belongs to
    account_ref       text        NOT NULL,         -- same hint as state.account_ref
    amazon_customer_id text,                        -- Amazon's own customer id (if returned in profile lookup)
    region            text        NOT NULL,         -- NA | EU | FE

    -- The credentials themselves
    refresh_token     text        NOT NULL,
    scope             text        NOT NULL,         -- granted scope from the access_token response
    last_access_token text,                         -- last minted short-lived access token (diagnostic; expires in 1h)
    last_access_token_expires_at timestamptz,

    -- Optional: which Amazon Ads profiles (advertisers) this refresh_token sees
    -- Populated on first successful /v2/profiles call.
    profile_ids       jsonb,                        -- e.g. [2849798098183833, 75561079299164]
    profiles_cached_at timestamptz,

    -- Lifecycle
    revoked_at        timestamptz,
    revoke_reason     text
);

CREATE UNIQUE INDEX IF NOT EXISTS amazon_oauth_tokens_live_per_account
    ON ads_agent.amazon_oauth_tokens (account_ref)
    WHERE revoked_at IS NULL;

GRANT SELECT, INSERT, UPDATE ON ads_agent.amazon_oauth_state  TO shopify_app;
GRANT SELECT, INSERT, UPDATE ON ads_agent.amazon_oauth_tokens TO shopify_app;
GRANT USAGE, SELECT ON SEQUENCE ads_agent.amazon_oauth_tokens_id_seq TO shopify_app;
