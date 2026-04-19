-- Meta (Facebook/Instagram) Ads daily snapshot.
--
-- Populated by ops/scripts/sync_meta_ads.py (daily cron, per STORE_AD_ACCOUNTS_JSON).
-- One row per (date, ad_id). `destination_url` is the key field for
-- Meta → Amazon attribution analysis: filter by pattern '%amazon.in%' / '%amazon.ae%'
-- to isolate Meta spend that drove Amazon traffic.
--
-- Idempotent. UPSERT on (date, ad_id). Re-runs safely backfill + update.
--
-- Apply:
--   sudo -u postgres psql -d shopify_app -f ops/scripts/migrate_meta_ads_daily.sql

CREATE TABLE IF NOT EXISTS ads_agent.meta_ads_daily (
    date              date         NOT NULL,
    ad_account_id     text         NOT NULL,          -- act_<id>
    campaign_id       text,
    campaign_name     text,
    adset_id          text,
    adset_name        text,
    ad_id             text         NOT NULL,
    ad_name           text,
    effective_status  text,

    -- Destination / creative info (resolved at sync time from ad's creative).
    destination_url   text,                            -- landing URL — KEY for Amazon attribution
    call_to_action    text,                            -- SHOP_NOW, LEARN_MORE, etc.
    creative_id       text,
    creative_body     text,
    creative_title    text,
    object_type       text,                            -- VIDEO / PHOTO / CAROUSEL ...

    -- Insights (ad-level, time_increment=1 → one row per day per ad).
    spend             numeric      DEFAULT 0,
    impressions       bigint       DEFAULT 0,
    clicks            bigint       DEFAULT 0,
    reach             bigint       DEFAULT 0,
    frequency         numeric      DEFAULT 0,
    ctr               numeric      DEFAULT 0,
    cpc               numeric      DEFAULT 0,
    cpm               numeric      DEFAULT 0,

    -- Conversions (Meta pixel events — reported on Meta's attribution, subject
    -- to the 2,390% over-report gap we see on Ayurpet. Useful only as a cross-check).
    purchases         integer      DEFAULT 0,
    purchase_value    numeric      DEFAULT 0,
    add_to_cart       integer      DEFAULT 0,
    content_view      integer      DEFAULT 0,

    currency          text,
    raw_json          jsonb,                           -- full insights row, for late-stage slicing
    synced_at         timestamptz  DEFAULT NOW(),

    PRIMARY KEY (date, ad_id)
);

CREATE INDEX IF NOT EXISTS meta_ads_daily_account_date_idx
    ON ads_agent.meta_ads_daily (ad_account_id, date DESC);

CREATE INDEX IF NOT EXISTS meta_ads_daily_destination_idx
    ON ads_agent.meta_ads_daily (destination_url)
    WHERE destination_url IS NOT NULL;

CREATE INDEX IF NOT EXISTS meta_ads_daily_amazon_links_idx
    ON ads_agent.meta_ads_daily (date, ad_account_id)
    WHERE destination_url ~* 'amazon\.(in|ae|com|co\.uk)';

GRANT SELECT, INSERT, UPDATE ON ads_agent.meta_ads_daily TO shopify_app;
