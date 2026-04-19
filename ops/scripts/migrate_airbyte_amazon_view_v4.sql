-- Airbyte Amazon normalization view v4 — adds Amazon Ads (Sponsored Products) branch.
--
-- v3 UNIONed India and UAE Seller-Central Orders. v4 adds a third branch:
-- Amazon Ads daily campaign-level spend/clicks/impressions/sales from
-- airbyte_amazon."c0rakm_sponsored_products_campaigns_report_stream_daily".
--
-- Ad-account → marketplace mapping is resolved through c0rakm_profiles.
-- We filter to the two profiles Ayurpet actively manages:
--   2849798098183833 → marketplace A21TJRUUN4KGV → store_slug ayurpet-ind (INR)
--   75561079299164   → marketplace A2VIGQ35RCS4UG → store_slug ayurpet-global (AED)
-- Other Indofolk Wellness profiles (IE/PL/UK/ES) also exist in c0rakm_profiles
-- but carry ~zero managed spend; excluded to keep view's currency mix honest.
--
-- sales1d column is picked (vs 7d/14d/30d) to match click-date reporting:
-- it's the conversion attributed within 1 day of the click, keeps the date axis
-- clean for daily ACOS/ROAS. Cost is spend on the report date regardless.
--
-- Apply:
--   sudo -u postgres psql -d shopify_app -f ops/scripts/migrate_airbyte_amazon_view_v4.sql

DROP VIEW IF EXISTS ads_agent.amazon_daily_v;

CREATE VIEW ads_agent.amazon_daily_v AS

-- ─── India Seller Central (airbyte_amazon.Orders) ───────────────────────────
SELECT
    ("PurchaseDate" AT TIME ZONE 'UTC')::date                            AS date,
    CASE "MarketplaceId"
        WHEN 'A21TJRUUN4KGV' THEN 'ayurpet-ind'
        WHEN 'A2VIGQ35RCS4UG' THEN 'ayurpet-global'
        WHEN 'ATVPDKIKX0DER'  THEN 'ayurpet-global'
        WHEN 'A2EUQ1WTGCTBG2' THEN 'ayurpet-global'
        WHEN 'A1AM78C64UM0Y8' THEN 'ayurpet-global'
        WHEN 'A1F83G8C2ARO7P' THEN 'ayurpet-global'
        WHEN 'A28R8C7NBKEWEA' THEN 'ayurpet-global'
        WHEN 'A1RKKUPIHCS9HS' THEN 'ayurpet-global'
        WHEN 'A1C3SOZRARQ6R3' THEN 'ayurpet-global'
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
        WHEN 'A21TJRUUN4KGV' THEN 'ayurpet-ind'
        WHEN 'A2VIGQ35RCS4UG' THEN 'ayurpet-global'
        WHEN 'ATVPDKIKX0DER'  THEN 'ayurpet-global'
        WHEN 'A2EUQ1WTGCTBG2' THEN 'ayurpet-global'
        WHEN 'A1AM78C64UM0Y8' THEN 'ayurpet-global'
        WHEN 'A1F83G8C2ARO7P' THEN 'ayurpet-global'
        WHEN 'A28R8C7NBKEWEA' THEN 'ayurpet-global'
        WHEN 'A1RKKUPIHCS9HS' THEN 'ayurpet-global'
        WHEN 'A1C3SOZRARQ6R3' THEN 'ayurpet-global'
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

UNION ALL

-- ─── Amazon Ads Sponsored Products (c0rakm_*) ───────────────────────────────
SELECT
    cd."date"::date                                                      AS date,
    CASE (p."accountInfo"->>'marketplaceStringId')
        WHEN 'A21TJRUUN4KGV' THEN 'ayurpet-ind'
        WHEN 'A2VIGQ35RCS4UG' THEN 'ayurpet-global'
        WHEN 'ATVPDKIKX0DER'  THEN 'ayurpet-global'
        WHEN 'A2EUQ1WTGCTBG2' THEN 'ayurpet-global'
        WHEN 'A1AM78C64UM0Y8' THEN 'ayurpet-global'
        WHEN 'A1F83G8C2ARO7P' THEN 'ayurpet-global'
        WHEN 'A28R8C7NBKEWEA' THEN 'ayurpet-global'
        WHEN 'A1RKKUPIHCS9HS' THEN 'ayurpet-global'
        WHEN 'A1C3SOZRARQ6R3' THEN 'ayurpet-global'
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
FROM airbyte_amazon."c0rakm_sponsored_products_campaigns_report_stream_daily" cd
JOIN airbyte_amazon."c0rakm_profiles" p
  ON p."profileId" = cd."profileId"
WHERE cd."profileId" IN (2849798098183833, 75561079299164)
  AND cd."date" IS NOT NULL
GROUP BY 1, 2, 3, 4, 5, 6
;

GRANT SELECT ON ads_agent.amazon_daily_v TO shopify_app;
