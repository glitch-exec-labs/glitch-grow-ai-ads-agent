-- Airbyte Amazon normalization view v5 — dedup layer on top of v4.
--
-- WHY v5: Airbyte's "Incremental Append + Deduped" mode is NOT actually
-- deduping in practice — all five metadata tables carry ~7× duplicate rows
-- (e.g. Orders: 5986 rows / 861 distinct AmazonOrderIds). This silently
-- inflated v4's order counts and sales by ~7×. Rather than re-plumb the
-- Airbyte stream config, we dedup at the view layer with DISTINCT ON picking
-- the most recently extracted copy of each natural-key row.
--
-- Natural keys:
--   Orders / fbsrf7_Orders                 → AmazonOrderId
--   OrderItems                             → OrderItemId (not used in this view)
--   c0rakm_sponsored_products_* reports    → presumed already deduped per
--                                            (date, profileId, campaignId)
--                                            because Airbyte re-fetches the
--                                            same report daily (so this view
--                                            also dedupes that branch).
--   c0rakm_profiles                        → profileId
--
-- If Airbyte's dedup behavior is later fixed, the DISTINCT ON layers become
-- no-ops (correct but redundant) — safe to keep.
--
-- Apply:
--   sudo -u postgres psql -d shopify_app -f ops/scripts/migrate_airbyte_amazon_view_v5.sql

DROP VIEW IF EXISTS ads_agent.amazon_daily_v;

CREATE VIEW ads_agent.amazon_daily_v AS
WITH
orders_in AS (
    SELECT DISTINCT ON ("AmazonOrderId") *
    FROM airbyte_amazon."Orders"
    ORDER BY "AmazonOrderId", _airbyte_extracted_at DESC
),
orders_ae AS (
    SELECT DISTINCT ON ("AmazonOrderId") *
    FROM airbyte_amazon."fbsrf7_Orders"
    ORDER BY "AmazonOrderId", _airbyte_extracted_at DESC
),
ads_camp AS (
    SELECT DISTINCT ON ("date","profileId","campaignId") *
    FROM airbyte_amazon."c0rakm_sponsored_products_campaigns_report_stream_daily"
    ORDER BY "date","profileId","campaignId", _airbyte_extracted_at DESC
),
profiles AS (
    SELECT DISTINCT ON ("profileId") *
    FROM airbyte_amazon."c0rakm_profiles"
    ORDER BY "profileId", _airbyte_extracted_at DESC
)

-- ─── India Seller Central ─────────────────────────────────────────────────
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
FROM orders_in
WHERE "OrderTotal" IS NOT NULL
GROUP BY 1, 2, 3, 4, 5, 6

UNION ALL

-- ─── UAE Seller Central ───────────────────────────────────────────────────
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
FROM orders_ae
WHERE "OrderTotal" IS NOT NULL
GROUP BY 1, 2, 3, 4, 5, 6

UNION ALL

-- ─── Amazon Ads Sponsored Products ────────────────────────────────────────
SELECT
    cd."date"::date                                                      AS date,
    CASE (p."accountInfo"->>'marketplaceStringId')
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
    (p."accountInfo"->>'marketplaceStringId')                            AS account_id,
    p."countryCode"                                                      AS marketplace,
    'ads_sp_campaigns'                                                   AS report_type,
    'ads'                                                                AS source,
    sum(cd."impressions")::bigint                                        AS impressions,
    sum(cd."clicks")::bigint                                             AS clicks,
    sum(cd."cost")                                                       AS cost,
    sum(cd."sales1d")                                                    AS sales,
    sum(cd."purchases1d")::bigint                                        AS orders,
    CASE WHEN sum(cd."sales1d") > 0
         THEN sum(cd."cost")    / sum(cd."sales1d") END                  AS acos,
    CASE WHEN sum(cd."cost")    > 0
         THEN sum(cd."sales1d") / sum(cd."cost") END                     AS roas,
    max(p."currencyCode")                                                AS currency,
    max(cd._airbyte_extracted_at)                                        AS synced_at
FROM ads_camp cd
JOIN profiles p ON p."profileId" = cd."profileId"
WHERE cd."profileId" IN (2849798098183833, 75561079299164)
  AND cd."date" IS NOT NULL
GROUP BY 1, 2, 3, 4, 5, 6
;

GRANT SELECT ON ads_agent.amazon_daily_v TO shopify_app;
