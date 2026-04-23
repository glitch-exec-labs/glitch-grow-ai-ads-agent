-- TikTok Marketing API OAuth — state (CSRF) table + token store.
--
-- Flow:
--   1. Agent generates `state`, inserts into tiktok_oauth_state with a
--      10-minute expiry, and returns the consent URL.
--   2. User approves access in TikTok Business.
--   3. TikTok redirects to grow.glitchexecutor.com/tiktok/oauth/callback
--      with auth_code + state.
--   4. Cloudflare Pages Function forwards that payload to
--      /api/tiktok/oauth/receive. Agent validates state, exchanges the
--      code for tokens, looks up accessible advertisers, and stores the
--      token row in tiktok_oauth_tokens.
--
-- Security:
--   - state is one-time-use (marked used_at after success)
--   - state expires after 10 minutes
--   - CF -> agent POST is gated by Bearer INTERNAL_API_SECRET
--   - tokens are stored at rest in Postgres and only readable via DB role

CREATE TABLE IF NOT EXISTS ads_agent.tiktok_oauth_state (
    state         text        PRIMARY KEY,
    created_at    timestamptz NOT NULL DEFAULT NOW(),
    expires_at    timestamptz NOT NULL DEFAULT NOW() + INTERVAL '10 minutes',
    used_at       timestamptz,
    account_ref   text,
    notes         text
);

CREATE INDEX IF NOT EXISTS tiktok_oauth_state_expires_idx
    ON ads_agent.tiktok_oauth_state (expires_at);


CREATE TABLE IF NOT EXISTS ads_agent.tiktok_oauth_tokens (
    id                       bigserial PRIMARY KEY,
    created_at               timestamptz NOT NULL DEFAULT NOW(),
    updated_at               timestamptz NOT NULL DEFAULT NOW(),
    account_ref              text        NOT NULL,
    access_token             text        NOT NULL,
    refresh_token            text,
    access_token_expires_at  timestamptz,
    advertiser_ids           jsonb,
    advertisers              jsonb,
    revoked_at               timestamptz,
    revoke_reason            text
);

CREATE UNIQUE INDEX IF NOT EXISTS tiktok_oauth_tokens_live_per_account
    ON ads_agent.tiktok_oauth_tokens (account_ref)
    WHERE revoked_at IS NULL;

GRANT SELECT, INSERT, UPDATE ON ads_agent.tiktok_oauth_state TO shopify_app;
GRANT SELECT, INSERT, UPDATE ON ads_agent.tiktok_oauth_tokens TO shopify_app;
GRANT USAGE, SELECT ON SEQUENCE ads_agent.tiktok_oauth_tokens_id_seq TO shopify_app;
