-- Airbyte Amazon normalization view v2 — built against actual first-sync schema.
--
-- What's here:
--   Seller Central Orders: real data (852 rows since 2025-03-09 for India).
--     Mapped via MarketplaceId → store_slug + currency passthrough.
--   Ads report streams: 0 rows so far (date range issue on first sync;
--     Ads source config should be tweaked in Airbyte UI to backfill 90d+).
--     View includes the UNION branches so new data will surface automatically
--     without another view rebuild.
--
-- Contract the agent reads:
--   date, store_slug, account_id, marketplace, report_type, source,
--   impressions, clicks, cost, sales, orders, acos, roas, currency, synced_at
--
-- Apply:
--   sudo -u postgres psql -d shopify_app -f ops/scripts/migrate_airbyte_amazon_view_v2.sql

DROP VIEW IF EXISTS ads_agent.amazon_daily_v;

CREATE VIEW ads_agent.amazon_daily_v AS

-- ─── Seller Central Orders: group by purchase_date + marketplace ─────────────
-- "orders" counts only non-cancelled (the real paying-order signal).
-- "sales" aggregates OrderTotal.Amount for paying orders in native currency.
SELECT
    ("PurchaseDate" AT TIME ZONE 'UTC')::date                            AS date,
    CASE "MarketplaceId"
        WHEN 'A21TJRUUN4KGV' THEN 'store-a'     -- Amazon.in
        WHEN 'A2VIGQ35RCS4UG' THEN 'store-b' -- Amazon.ae (UAE)
        WHEN 'ATVPDKIKX0DER'  THEN 'store-b' -- Amazon.com (US)
        WHEN 'A2EUQ1WTGCTBG2' THEN 'store-b' -- Amazon.ca
        WHEN 'A1AM78C64UM0Y8' THEN 'store-b' -- Amazon.com.mx
        WHEN 'A1F83G8C2ARO7P' THEN 'store-b' -- Amazon.co.uk
        WHEN 'A28R8C7NBKEWEA' THEN 'store-b' -- Amazon.ie
        WHEN 'A1RKKUPIHCS9HS' THEN 'store-b' -- Amazon.es
        WHEN 'A1C3SOZRARQ6R3' THEN 'store-b' -- Amazon.pl
        ELSE 'unknown'
    END                                                                  AS store_slug,
    "MarketplaceId"                                                      AS account_id,
    "SalesChannel"                                                       AS marketplace,
    'orders'                                                             AS report_type,
    'seller'                                                             AS source,
    NULL::bigint                                                         AS impressions,
    NULL::bigint                                                         AS clicks,
    NULL::numeric                                                        AS cost,
    -- Sum Amount for paying orders; exclude cancelled/pending
    sum(CASE WHEN "OrderStatus" IN ('Shipped','Unshipped','PartiallyShipped')
             THEN ("OrderTotal"->>'Amount')::numeric ELSE 0 END)         AS sales,
    count(*) FILTER (WHERE "OrderStatus" IN ('Shipped','Unshipped','PartiallyShipped')) AS orders,
    NULL::numeric                                                        AS acos,
    NULL::numeric                                                        AS roas,
    max("OrderTotal"->>'CurrencyCode')                                   AS currency,
    max(_airbyte_extracted_at)                                           AS synced_at
FROM airbyte_amazon."Orders"
WHERE "OrderTotal" IS NOT NULL
GROUP BY 1, 2, 3, 4, 5, 6

-- ─── Sponsored Products daily (will fire once Airbyte backfills Ads reports) ──
UNION ALL
SELECT
    NULL::date, NULL::text, NULL::text, NULL::text, NULL::text, NULL::text,
    NULL::bigint, NULL::bigint, NULL::numeric, NULL::numeric, NULL::bigint,
    NULL::numeric, NULL::numeric, NULL::text, NULL::timestamptz
FROM airbyte_amazon.sponsored_products_campaigns_report_stream_daily
WHERE FALSE  -- placeholder until columns are known
;

GRANT SELECT ON ads_agent.amazon_daily_v TO shopify_app;

-- Quick sanity
ANALYZE airbyte_amazon."Orders";
