-- Airbyte Amazon SKU-level daily P&L view (v1).
--
-- Purpose: `/amazon ayurpet-ind 30 --by-sku` — top SKU contribution by units,
-- gross, and ad-spend/ad-sales. Complements amazon_daily_v (store-grain) with
-- one row per (date × store × seller_sku).
--
-- Joins per store:
--   Orders o × OrderItems oi ON AmazonOrderId → per-SKU units and gross
--   GET_MERCHANT_LISTINGS_ALL_DATA l ON oi.SellerSKU = l.seller_sku → title + listing ASIN
--   c0rakm_sponsored_products_productads_report_stream_daily pa
--     × c0rakm_sponsored_product_ads a ON adId → SKU (a."sku")
--     → per-SKU ad spend/clicks/impressions (FULL OUTER so ad-only and sales-only
--       SKUs both surface; e.g. a SKU burning spend but zero orders must appear).
--
-- Limitations (v1, deliberate):
--   - No SKU-grain fees/refunds. ListFinancialEvents has them in
--     ShipmentEventList → ShipmentItemList → ItemFeeList[]/SellerSKU, a 3-level
--     jsonb expansion. Skipped until there's a consumer — the store-grain
--     amazon_financials_daily_v already covers net-profit questions.
--   - gross is from OrderItems.ItemPrice.Amount (principal only; no tax lines).
--     Consistent with amazon_daily_v — see known Seller-vs-Finances discrepancy.
--   - Ads sales1d is click-date attributed (1d window), matches ads_sp_campaigns
--     branch of amazon_daily_v.
--
-- Apply:
--   sudo -u postgres psql -d shopify_app -f ops/scripts/migrate_airbyte_amazon_sku_view.sql

DROP VIEW IF EXISTS ads_agent.amazon_sku_daily_v;

-- NOTE: Airbyte's "Incremental Append + Deduped" mode is NOT deduping in
-- practice — Orders/OrderItems/Listings all carry ~7× duplicate rows. We
-- dedup at the view layer with DISTINCT ON (natural_key, latest extract).
-- See ops/scripts/migrate_airbyte_amazon_view_v5.sql for context.

CREATE VIEW ads_agent.amazon_sku_daily_v AS
WITH
orders_in_dedup AS (
    SELECT DISTINCT ON ("AmazonOrderId") *
    FROM airbyte_amazon."Orders"
    ORDER BY "AmazonOrderId", _airbyte_extracted_at DESC
),
orders_ae_dedup AS (
    SELECT DISTINCT ON ("AmazonOrderId") *
    FROM airbyte_amazon."fbsrf7_Orders"
    ORDER BY "AmazonOrderId", _airbyte_extracted_at DESC
),
items_in_dedup AS (
    SELECT DISTINCT ON ("OrderItemId") *
    FROM airbyte_amazon."OrderItems"
    ORDER BY "OrderItemId", _airbyte_extracted_at DESC
),
items_ae_dedup AS (
    SELECT DISTINCT ON ("OrderItemId") *
    FROM airbyte_amazon."fbsrf7_OrderItems"
    ORDER BY "OrderItemId", _airbyte_extracted_at DESC
),
listings_in_dedup AS (
    SELECT DISTINCT ON (seller_sku) *
    FROM airbyte_amazon."GET_MERCHANT_LISTINGS_ALL_DATA"
    ORDER BY seller_sku, _airbyte_extracted_at DESC
),
listings_ae_dedup AS (
    SELECT DISTINCT ON (seller_sku) *
    FROM airbyte_amazon."fbsrf7_GET_MERCHANT_LISTINGS_ALL_DATA"
    ORDER BY seller_sku, _airbyte_extracted_at DESC
),
productads_dedup AS (
    SELECT DISTINCT ON ("date","profileId","adId") *
    FROM airbyte_amazon."c0rakm_sponsored_products_productads_report_stream_daily"
    ORDER BY "date","profileId","adId", _airbyte_extracted_at DESC
),
ads_meta_dedup AS (
    SELECT DISTINCT ON ("adId") *
    FROM airbyte_amazon."c0rakm_sponsored_product_ads"
    ORDER BY "adId", _airbyte_extracted_at DESC
),
-- ── Seller orders & items, both regions, flattened to per-SKU rows ─────────
seller_items AS (
    SELECT
        ("PurchaseDate" AT TIME ZONE 'UTC')::date    AS date,
        'ayurpet-ind'::text                          AS store_slug,
        'A21TJRUUN4KGV'::text                        AS account_id,
        oi."SellerSKU"                               AS seller_sku,
        oi."ASIN"                                    AS asin_ordered,
        oi."QuantityOrdered"                         AS units,
        COALESCE((oi."ItemPrice"->>'Amount')::numeric, 0)           AS gross,
        COALESCE(oi."ItemPrice"->>'CurrencyCode', 'INR')            AS currency,
        oi."AmazonOrderId"                           AS order_id
    FROM items_in_dedup oi
    JOIN orders_in_dedup o ON o."AmazonOrderId" = oi."AmazonOrderId"
    WHERE o."OrderStatus" IN ('Shipped','Unshipped','PartiallyShipped')
      AND oi."SellerSKU" IS NOT NULL

    UNION ALL

    SELECT
        ("PurchaseDate" AT TIME ZONE 'UTC')::date,
        'ayurpet-global'::text,
        'A2VIGQ35RCS4UG'::text,
        oi."SellerSKU",
        oi."ASIN",
        oi."QuantityOrdered",
        COALESCE((oi."ItemPrice"->>'Amount')::numeric, 0),
        COALESCE(oi."ItemPrice"->>'CurrencyCode', 'AED'),
        oi."AmazonOrderId"
    FROM items_ae_dedup oi
    JOIN orders_ae_dedup o ON o."AmazonOrderId" = oi."AmazonOrderId"
    WHERE o."OrderStatus" IN ('Shipped','Unshipped','PartiallyShipped')
      AND oi."SellerSKU" IS NOT NULL
),
seller_agg AS (
    SELECT
        date, store_slug, account_id, seller_sku, currency,
        max(asin_ordered)               AS asin_ordered,
        sum(units)                      AS units,
        sum(gross)                      AS gross,
        count(DISTINCT order_id)        AS order_lines
    FROM seller_items
    GROUP BY 1, 2, 3, 4, 5
),
-- ── Listings metadata (title + canonical asin1) per region ─────────────────
listings AS (
    SELECT 'ayurpet-ind'::text AS store_slug,
           seller_sku, asin1, item_name
    FROM listings_in_dedup
    UNION ALL
    SELECT 'ayurpet-global'::text,
           seller_sku, asin1, item_name
    FROM listings_ae_dedup
),
-- ── Ads productads_daily, joined to ads-meta for SKU mapping ───────────────
ads_agg AS (
    SELECT
        pa."date"::date                              AS date,
        CASE pa."profileId"
            WHEN 2849798098183833 THEN 'ayurpet-ind'
            WHEN 75561079299164   THEN 'ayurpet-global'
            ELSE 'unknown'
        END                                          AS store_slug,
        a."sku"                                      AS seller_sku,
        max(a."asin")                                AS asin_ad,
        sum(pa."cost")                               AS ads_cost,
        sum(pa."sales1d")                            AS ads_sales1d,
        sum(pa."impressions")::bigint                AS ads_impressions,
        sum(pa."clicks")::bigint                     AS ads_clicks,
        sum(pa."unitsSoldClicks1d")::bigint          AS ads_units_1d
    FROM productads_dedup pa
    JOIN ads_meta_dedup a
      ON a."adId"::text = pa."adId"::text
    WHERE pa."profileId" IN (2849798098183833, 75561079299164)
      AND a."sku" IS NOT NULL
      AND pa."date" IS NOT NULL
    GROUP BY 1, 2, 3
)
SELECT
    COALESCE(s.date,       ad.date)            AS date,
    COALESCE(s.store_slug, ad.store_slug)      AS store_slug,
    s.account_id,
    COALESCE(s.seller_sku, ad.seller_sku)      AS seller_sku,
    COALESCE(l.asin1, s.asin_ordered, ad.asin_ad) AS asin,
    l.item_name,
    COALESCE(s.units, 0)                       AS units,
    COALESCE(s.gross, 0)                       AS gross,
    COALESCE(s.order_lines, 0)                 AS order_lines,
    COALESCE(ad.ads_cost, 0)                   AS ads_cost,
    COALESCE(ad.ads_sales1d, 0)                AS ads_sales1d,
    COALESCE(ad.ads_impressions, 0)            AS ads_impressions,
    COALESCE(ad.ads_clicks, 0)                 AS ads_clicks,
    COALESCE(ad.ads_units_1d, 0)               AS ads_units_1d,
    CASE WHEN COALESCE(ad.ads_cost, 0) > 0 AND COALESCE(s.gross, 0) > 0
         THEN ad.ads_cost / s.gross END        AS tacos,  -- ad cost as % of seller gross (total-ACOS)
    s.currency
FROM seller_agg s
FULL OUTER JOIN ads_agg ad
  ON ad.date = s.date
 AND ad.store_slug = s.store_slug
 AND ad.seller_sku = s.seller_sku
LEFT JOIN listings l
  ON l.store_slug = COALESCE(s.store_slug, ad.store_slug)
 AND l.seller_sku = COALESCE(s.seller_sku, ad.seller_sku)
;

GRANT SELECT ON ads_agent.amazon_sku_daily_v TO shopify_app;
