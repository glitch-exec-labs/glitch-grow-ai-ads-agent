-- Normalization view: airbyte_amazon.* (written by Airbyte) → ads_agent.amazon_daily_v
--
-- Airbyte's Amazon connectors create tables like:
--   airbyte_amazon.sponsored_products_report_stream
--   airbyte_amazon.sponsored_brands_report_stream
--   airbyte_amazon.sponsored_display_report_stream
--   airbyte_amazon.seller_feedback
--   airbyte_amazon.orders
--   (etc. — exact names depend on streams enabled in the Airbyte connection)
--
-- We DON'T know the exact column names until Airbyte's first sync lands. Rather
-- than guess, this view starts empty and we incrementally UNION in real Airbyte
-- tables as we see them, keeping the agent's read path stable.
--
-- Contract the agent consumes (same shape as ads_agent.amazon_daily):
--   date, store_slug, account_id, marketplace, report_type, source,
--   impressions, clicks, cost, sales, orders, acos, roas
--
-- Rebuild this view whenever new Airbyte streams are enabled.
--
-- Apply:
--   sudo -u postgres psql -d shopify_app -f ops/scripts/migrate_airbyte_amazon_view.sql

-- Empty skeleton. Once Airbyte's first sync creates concrete tables, REPLACE
-- this with a UNION ALL across them. See comment at bottom for the canonical
-- template.
CREATE OR REPLACE VIEW ads_agent.amazon_daily_v AS
SELECT
    NULL::date        AS date,
    NULL::text        AS store_slug,
    NULL::text        AS account_id,
    NULL::text        AS marketplace,
    NULL::text        AS report_type,
    NULL::text        AS source,
    NULL::bigint      AS impressions,
    NULL::bigint      AS clicks,
    NULL::numeric     AS cost,
    NULL::numeric     AS sales,
    NULL::bigint      AS orders,
    NULL::numeric     AS acos,
    NULL::numeric     AS roas,
    NULL::timestamptz AS synced_at
WHERE FALSE;  -- always empty until streams land

GRANT SELECT ON ads_agent.amazon_daily_v TO shopify_app;

-- Template for the real view once Airbyte tables exist (adjust column names
-- to match Airbyte's actual schema after first sync):
--
-- CREATE OR REPLACE VIEW ads_agent.amazon_daily_v AS
-- SELECT
--     report_date::date                                       AS date,
--     CASE profile_id
--         WHEN 'A21TJRUUN4KGV' THEN 'ayurpet-ind'
--         WHEN 'A2VIGQ35RCS4UG' THEN 'ayurpet-global'
--         ELSE 'unknown'
--     END                                                     AS store_slug,
--     profile_id                                              AS account_id,
--     marketplace_id                                          AS marketplace,
--     'SponsoredProduct'                                      AS report_type,
--     'ads'                                                   AS source,
--     impressions::bigint                                     AS impressions,
--     clicks::bigint                                          AS clicks,
--     cost::numeric                                           AS cost,
--     sales::numeric                                          AS sales,
--     purchases::bigint                                       AS orders,
--     acos_clicks14d::numeric                                 AS acos,
--     roas_clicks14d::numeric                                 AS roas,
--     _airbyte_extracted_at                                   AS synced_at
-- FROM airbyte_amazon.sponsored_products_report_stream
-- UNION ALL
-- SELECT ... FROM airbyte_amazon.sponsored_brands_report_stream
-- UNION ALL
-- SELECT ... FROM airbyte_amazon.sponsored_display_report_stream;
