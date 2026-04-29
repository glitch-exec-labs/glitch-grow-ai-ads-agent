-- Airbyte Amazon normalization view v3 — adds UAE Seller Central.
--
-- India and UAE Seller Central come from SEPARATE Airbyte Source connections
-- (because Amazon Seller Partner needs one OAuth per Seller-Central account).
-- Airbyte writes each source's streams to differently-prefixed tables:
--
--   India  → airbyte_amazon.Orders          (unprefixed; first source)
--   UAE    → airbyte_amazon.fbsrf7_Orders   (hash-prefixed; second source)
--
-- If a third Seller region gets connected (US/UK/etc.), it will come in as
-- another hashed-prefix table (e.g. airbyte_amazon.abc123_Orders) and we'll
-- add another UNION branch here.
--
-- Apply:
--   sudo -u postgres psql -d shopify_app -f ops/scripts/migrate_airbyte_amazon_view_v3.sql

DROP VIEW IF EXISTS ads_agent.amazon_daily_v;

CREATE VIEW ads_agent.amazon_daily_v AS

-- ─── India Seller Central (airbyte_amazon.Orders) ───────────────────────────
SELECT
    ("PurchaseDate" AT TIME ZONE 'UTC')::date                            AS date,
    CASE "MarketplaceId"
        WHEN 'A21TJRUUN4KGV' THEN 'store-a'
        WHEN 'A2VIGQ35RCS4UG' THEN 'store-b'
        WHEN 'ATVPDKIKX0DER'  THEN 'store-b'
        WHEN 'A2EUQ1WTGCTBG2' THEN 'store-b'
        WHEN 'A1AM78C64UM0Y8' THEN 'store-b'
        WHEN 'A1F83G8C2ARO7P' THEN 'store-b'
        WHEN 'A28R8C7NBKEWEA' THEN 'store-b'
        WHEN 'A1RKKUPIHCS9HS' THEN 'store-b'
        WHEN 'A1C3SOZRARQ6R3' THEN 'store-b'
        ELSE 'unknown'
    END                                                                  AS store_slug,
    "MarketplaceId"                                                      AS account_id,
    "SalesChannel"                                                       AS marketplace,
    'orders'                                                             AS report_type,
    'seller'                                                             AS source,
    NULL::bigint                                                         AS impressions,
    NULL::bigint                                                         AS clicks,
    NULL::numeric                                                        AS cost,
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

UNION ALL

-- ─── UAE Seller Central (airbyte_amazon.fbsrf7_Orders) ──────────────────────
SELECT
    ("PurchaseDate" AT TIME ZONE 'UTC')::date                            AS date,
    CASE "MarketplaceId"
        WHEN 'A21TJRUUN4KGV' THEN 'store-a'
        WHEN 'A2VIGQ35RCS4UG' THEN 'store-b'
        WHEN 'ATVPDKIKX0DER'  THEN 'store-b'
        WHEN 'A2EUQ1WTGCTBG2' THEN 'store-b'
        WHEN 'A1AM78C64UM0Y8' THEN 'store-b'
        WHEN 'A1F83G8C2ARO7P' THEN 'store-b'
        WHEN 'A28R8C7NBKEWEA' THEN 'store-b'
        WHEN 'A1RKKUPIHCS9HS' THEN 'store-b'
        WHEN 'A1C3SOZRARQ6R3' THEN 'store-b'
        ELSE 'unknown'
    END                                                                  AS store_slug,
    "MarketplaceId"                                                      AS account_id,
    "SalesChannel"                                                       AS marketplace,
    'orders'                                                             AS report_type,
    'seller'                                                             AS source,
    NULL::bigint                                                         AS impressions,
    NULL::bigint                                                         AS clicks,
    NULL::numeric                                                        AS cost,
    sum(CASE WHEN "OrderStatus" IN ('Shipped','Unshipped','PartiallyShipped')
             THEN ("OrderTotal"->>'Amount')::numeric ELSE 0 END)         AS sales,
    count(*) FILTER (WHERE "OrderStatus" IN ('Shipped','Unshipped','PartiallyShipped')) AS orders,
    NULL::numeric                                                        AS acos,
    NULL::numeric                                                        AS roas,
    max("OrderTotal"->>'CurrencyCode')                                   AS currency,
    max(_airbyte_extracted_at)                                           AS synced_at
FROM airbyte_amazon."fbsrf7_Orders"
WHERE "OrderTotal" IS NOT NULL
GROUP BY 1, 2, 3, 4, 5, 6
;

GRANT SELECT ON ads_agent.amazon_daily_v TO shopify_app;
