-- Amazon data cache — one row per (date, account, report_type, source).
--
-- Populated nightly by ops/scripts/sync_amazon.py which pulls from
-- amazon-ads-mcp (port 3105). Live Supermetrics queries take 2-3 minutes
-- per account; caching is the only way /amazon can reply in sub-second.
--
-- Schema stays stable across data-source changes: when native LWA ships
-- and replaces Supermetrics inside amazon-ads-mcp, this table is unchanged.
--
-- Apply:
--   sudo -u postgres psql -d shopify_app -f ops/scripts/migrate_amazon_daily.sql

CREATE SCHEMA IF NOT EXISTS ads_agent AUTHORIZATION shopify_app;

CREATE TABLE IF NOT EXISTS ads_agent.amazon_daily (
    id             BIGSERIAL PRIMARY KEY,
    date           DATE NOT NULL,
    store_slug     TEXT NOT NULL,
    account_id     TEXT NOT NULL,
    marketplace    TEXT,
    report_type    TEXT,              -- SponsoredProduct / SponsoredBrands / SponsoredDisplay / 'seller'
    source         TEXT NOT NULL,     -- 'ads' | 'seller'
    impressions    BIGINT,
    clicks         BIGINT,
    cost           NUMERIC(14,2),
    sales          NUMERIC(14,2),
    orders         BIGINT,
    acos           NUMERIC(10,4),
    roas           NUMERIC(10,4),
    raw_json       JSONB,             -- full row as returned by the MCP; future-proofs field additions
    synced_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT amazon_daily_unique UNIQUE (date, account_id, report_type, source)
);

CREATE INDEX IF NOT EXISTS amazon_daily_store_date_idx      ON ads_agent.amazon_daily (store_slug, date DESC);
CREATE INDEX IF NOT EXISTS amazon_daily_account_date_idx    ON ads_agent.amazon_daily (account_id, date DESC);
CREATE INDEX IF NOT EXISTS amazon_daily_synced_idx          ON ads_agent.amazon_daily (synced_at DESC);

-- Sync errors table — track OAuth expiries, 502s, per-account issues without
-- letting them bubble up as cron failures.
CREATE TABLE IF NOT EXISTS ads_agent.amazon_sync_errors (
    id         BIGSERIAL PRIMARY KEY,
    ts         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    store_slug TEXT,
    account_id TEXT,
    report_type TEXT,
    error_kind TEXT,   -- 'auth_expired' | 'timeout' | '502' | 'schema' | 'other'
    error_msg  TEXT
);
CREATE INDEX IF NOT EXISTS amazon_sync_errors_ts_idx ON ads_agent.amazon_sync_errors (ts DESC);

GRANT SELECT, INSERT, UPDATE, DELETE ON ads_agent.amazon_daily       TO shopify_app;
GRANT SELECT, INSERT                 ON ads_agent.amazon_sync_errors TO shopify_app;
GRANT USAGE, SELECT                  ON SEQUENCE ads_agent.amazon_daily_id_seq       TO shopify_app;
GRANT USAGE, SELECT                  ON SEQUENCE ads_agent.amazon_sync_errors_id_seq TO shopify_app;
