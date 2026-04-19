-- Meta → Amazon attribution view (v1, assume-zero-organic model).
--
-- Given Ayurpet's constraints (new brand, Amazon Attribution API unavailable
-- for India-only brand registry, only paid sources are Meta + Amazon SP Ads),
-- we attribute all non-SP Amazon orders to Meta by subtraction:
--
--   meta_attributed_orders = amz_total_orders − amz_sp_orders
--   meta_attributed_gross  = amz_total_gross  − amz_sp_sales1d
--   meta_attributed_roas   = meta_attributed_gross / meta_to_amazon_spend
--
-- Grain: one row per (date × store_slug × asin). A NULL asin row carries
-- store-level totals where ASIN couldn't be resolved (e.g. Meta ads that link
-- to amazon.in homepage or search results, not /dp/<ASIN>).
--
-- Currency normalization: Ayurpet's Meta ad account is INR, but Amazon AE
-- revenue is AED. To produce a meaningful ROAS, we convert AED → INR using a
-- hardcoded FX rate (22.7 ₹/AED as of 2026-04-19). Updating this is a quarterly
-- manual task — acceptable since the rate is stable and this is an internal
-- attribution tool, not an accounting system. A future improvement: replace
-- with a live FX API (openexchangerates / exchangerate-api). If/when Ayurpet
-- adds non-INR ad accounts, this becomes per-account instead of per-store.
--
-- Known limitations — must be communicated with every report consuming this view:
--   1. Organic Amazon traffic (branded search, "customers also bought", Amazon
--      Choice badge, Subscribe & Save) is assumed ~zero. Holds only while
--      Ayurpet is < ~20 orders/day. Revisit when volume crosses that threshold.
--   2. Repeat-buyer orders are credited to Meta even if the first purchase
--      happened months ago. Discount Meta-attributed numbers by the store's
--      repeat-buyer ratio for more accurate incrementality (see separate
--      one-time audit).
--   3. Branded search IS correctly included as Meta-attributed (prior ad
--      exposure → buyer remembers brand → searches → buys). This is a feature,
--      not a bug.
--   4. Sessions-refinement (multiplying by meta_share_of_sessions) will come
--      once GET_SALES_AND_TRAFFIC_REPORT lands from Airbyte. Drop-in upgrade.
--
-- Apply:
--   sudo -u postgres psql -d shopify_app -f ops/scripts/migrate_amazon_attribution_view.sql

DROP VIEW IF EXISTS ads_agent.amazon_attribution_daily_v;

CREATE VIEW ads_agent.amazon_attribution_daily_v AS
WITH
-- Dedup Airbyte's ~7× row-duplication at source (see project_airbyte_dedup_quirk).
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
items_in AS (
    SELECT DISTINCT ON ("OrderItemId") *
    FROM airbyte_amazon."OrderItems"
    ORDER BY "OrderItemId", _airbyte_extracted_at DESC
),
items_ae AS (
    SELECT DISTINCT ON ("OrderItemId") *
    FROM airbyte_amazon."fbsrf7_OrderItems"
    ORDER BY "OrderItemId", _airbyte_extracted_at DESC
),
productads_dedup AS (
    SELECT DISTINCT ON ("date","profileId","adId") *
    FROM airbyte_amazon."c0rakm_sponsored_products_productads_report_stream_daily"
    ORDER BY "date","profileId","adId", _airbyte_extracted_at DESC
),

-- ── Amazon total orders per (date, store, asin) ──────────────────────────
amz_orders_asin AS (
    SELECT
        ("PurchaseDate" AT TIME ZONE 'UTC')::date AS date,
        'ayurpet-ind'::text                        AS store_slug,
        oi."ASIN"                                  AS asin,
        COUNT(DISTINCT oi."AmazonOrderId")         AS amz_orders,
        SUM(oi."QuantityOrdered")                  AS amz_units,
        SUM(COALESCE((oi."ItemPrice"->>'Amount')::numeric, 0)) AS amz_gross,
        MAX(COALESCE(oi."ItemPrice"->>'CurrencyCode', 'INR')) AS currency
    FROM items_in oi
    JOIN orders_in o ON o."AmazonOrderId" = oi."AmazonOrderId"
    WHERE o."OrderStatus" IN ('Shipped','Unshipped','PartiallyShipped')
      AND oi."ASIN" IS NOT NULL
    GROUP BY 1, 2, 3

    UNION ALL

    SELECT
        ("PurchaseDate" AT TIME ZONE 'UTC')::date,
        'ayurpet-global'::text,
        oi."ASIN",
        COUNT(DISTINCT oi."AmazonOrderId"),
        SUM(oi."QuantityOrdered"),
        SUM(COALESCE((oi."ItemPrice"->>'Amount')::numeric, 0)),
        MAX(COALESCE(oi."ItemPrice"->>'CurrencyCode', 'AED'))
    FROM items_ae oi
    JOIN orders_ae o ON o."AmazonOrderId" = oi."AmazonOrderId"
    WHERE o."OrderStatus" IN ('Shipped','Unshipped','PartiallyShipped')
      AND oi."ASIN" IS NOT NULL
    GROUP BY 1, 2, 3
),

-- ── Amazon SP Ads per (date, store, asin) via advertisedAsin ─────────────
amz_sp_asin AS (
    SELECT
        pa."date"::date AS date,
        CASE pa."profileId"
            WHEN 2849798098183833 THEN 'ayurpet-ind'
            WHEN 75561079299164   THEN 'ayurpet-global'
        END AS store_slug,
        pa."advertisedAsin" AS asin,
        SUM(pa."cost")        AS sp_cost,
        SUM(pa."sales1d")     AS sp_sales1d,
        SUM(pa."purchases1d") AS sp_orders,
        SUM(pa."clicks")      AS sp_clicks,
        SUM(pa."impressions") AS sp_impressions
    FROM productads_dedup pa
    WHERE pa."profileId" IN (2849798098183833, 75561079299164)
      AND pa."advertisedAsin" IS NOT NULL
      AND pa."date" IS NOT NULL
    GROUP BY 1, 2, 3
),

-- ── Meta-to-Amazon spend per (date, store, asin) ─────────────────────────
-- Resolve ASIN from destination_url pattern /dp/<10-char-ASIN>.
-- Resolve store_slug by marketplace hostname (amazon.in = IN, amazon.ae = AE).
meta_to_amazon AS (
    SELECT
        date,
        CASE
            WHEN destination_url ~* 'amazon\.in' THEN 'ayurpet-ind'
            WHEN destination_url ~* 'amazon\.ae' THEN 'ayurpet-global'
        END AS store_slug,
        (regexp_match(destination_url, 'dp/([A-Z0-9]{10})'))[1] AS asin,
        SUM(spend)       AS meta_spend,
        SUM(clicks)      AS meta_clicks,
        SUM(impressions) AS meta_impressions,
        COUNT(DISTINCT ad_id) AS meta_ad_count
    FROM ads_agent.meta_ads_daily
    WHERE destination_url ~* 'amazon\.(in|ae)'
    GROUP BY 1, 2, 3
),

-- ── Spine: every (date × store × asin) that appears in any source ────────
spine AS (
    SELECT date, store_slug, asin FROM amz_orders_asin
    UNION
    SELECT date, store_slug, asin FROM amz_sp_asin
    UNION
    SELECT date, store_slug, asin FROM meta_to_amazon
)

SELECT
    s.date,
    s.store_slug,
    s.asin,

    -- Raw totals from each source
    COALESCE(o.amz_orders, 0)           AS amz_orders,
    COALESCE(o.amz_units, 0)            AS amz_units,
    COALESCE(o.amz_gross, 0)            AS amz_gross,

    COALESCE(sp.sp_orders, 0)           AS sp_orders,
    COALESCE(sp.sp_sales1d, 0)          AS sp_sales1d,
    COALESCE(sp.sp_cost, 0)             AS sp_cost,
    COALESCE(sp.sp_clicks, 0)           AS sp_clicks,
    COALESCE(sp.sp_impressions, 0)      AS sp_impressions,

    COALESCE(m.meta_spend, 0)           AS meta_spend,
    COALESCE(m.meta_clicks, 0)          AS meta_clicks,
    COALESCE(m.meta_impressions, 0)     AS meta_impressions,
    COALESCE(m.meta_ad_count, 0)        AS meta_ad_count,

    -- The attribution math: non-SP orders/gross credited to Meta, but ONLY
    -- for ASINs that actually received Meta-to-Amazon spend in the window.
    -- Orders on non-advertised ASINs are classified as organic/halo even
    -- under the zero-organic assumption — because if Meta didn't point
    -- traffic at ASIN X, Meta can't have driven ASIN X's orders.
    --
    -- This is conservative-honest: Meta gets credit only where we can
    -- causally trace a link click. Halo effects (brand search, cross-sell
    -- from a Meta-advertised ASIN to another ASIN) are intentionally under-
    -- attributed — they exist, but quantifying them needs the sessions data.
    CASE WHEN COALESCE(m.meta_spend, 0) > 0
         THEN GREATEST(COALESCE(o.amz_orders, 0) - COALESCE(sp.sp_orders, 0), 0)
         ELSE 0
    END AS meta_attributed_orders,

    CASE WHEN COALESCE(m.meta_spend, 0) > 0
         THEN GREATEST(COALESCE(o.amz_gross, 0) - COALESCE(sp.sp_sales1d, 0), 0)
         ELSE 0
    END AS meta_attributed_gross,

    -- Meta-attributed gross in INR (store-native × FX).
    -- Ayurpet's Meta ad account bills INR, so ROAS must be INR/INR to be meaningful.
    CASE WHEN COALESCE(m.meta_spend, 0) > 0
         THEN GREATEST(COALESCE(o.amz_gross, 0) - COALESCE(sp.sp_sales1d, 0), 0)
              * CASE s.store_slug
                    WHEN 'ayurpet-ind'    THEN 1.0
                    WHEN 'ayurpet-global' THEN 22.7   -- AED → INR, 2026-04-19 rate
                    ELSE 1.0
                END
         ELSE 0
    END AS meta_attributed_gross_inr,

    -- Derived ratios: only computed where denominators are non-zero.
    -- ROAS is INR/INR (currency-normalized); CPO returns in INR.
    CASE WHEN COALESCE(m.meta_spend, 0) > 0
         THEN (GREATEST(COALESCE(o.amz_gross, 0) - COALESCE(sp.sp_sales1d, 0), 0)
               * CASE s.store_slug
                     WHEN 'ayurpet-ind'    THEN 1.0
                     WHEN 'ayurpet-global' THEN 22.7
                     ELSE 1.0
                 END)
              / m.meta_spend
    END AS meta_attributed_roas,

    CASE WHEN COALESCE(m.meta_spend, 0) > 0
          AND GREATEST(COALESCE(o.amz_orders, 0) - COALESCE(sp.sp_orders, 0), 0) > 0
         THEN m.meta_spend
              / GREATEST(COALESCE(o.amz_orders, 0) - COALESCE(sp.sp_orders, 0), 0)
    END AS meta_attributed_cpo_inr,

    -- Currency resolved from orders; falls back to store-default.
    COALESCE(o.currency,
             CASE s.store_slug WHEN 'ayurpet-ind' THEN 'INR' ELSE 'AED' END) AS currency
FROM spine s
LEFT JOIN amz_orders_asin  o  USING (date, store_slug, asin)
LEFT JOIN amz_sp_asin      sp USING (date, store_slug, asin)
LEFT JOIN meta_to_amazon   m  USING (date, store_slug, asin)
;

GRANT SELECT ON ads_agent.amazon_attribution_daily_v TO shopify_app;
