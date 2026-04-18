-- Drop Airbyte-created tables belonging to disabled Amazon sources.
--
-- Context (2026-04-18): User disabled all Airbyte sources except:
--   1. India Seller Central  → writes unprefixed:  Orders, OrderItems,
--      ListFinancialEvents, ListFinancialEventGroups
--   2. UAE Seller Central    → writes prefix `fbsrf7_`:  same 4 streams
--   3. Amazon Ads (EU/FE)    → writes prefix `c0rakm_`:  metadata streams
--      (report streams will land later, also prefixed c0rakm_)
--
-- Everything else in airbyte_amazon is stale from disabled sources:
--   • bmok90_*           → NA Amazon Ads source (dead)
--   • gjrf6w_*           → Duplicate Amazon Ads source (dead)
--   • ib0s9r_*           → Duplicate Amazon Ads source (dead)
--   • Unprefixed GET_*   → Disabled Seller Partner report streams
--   • Unprefixed Vendor* → Disabled (we're a Seller, not Vendor)
--   • Unprefixed sponsored_*, profiles, portfolios → Legacy Ads source (dead)
--   • fbsrf7_GET_*, fbsrf7_Vendor* → UAE disabled report streams
--   • airbyte_amazon_1esmkh_* → Internal raw-staging for dead source
--   • airbyte_amazonattribut* → Attribution source (no API approval)
--   • airbyte_amazongjrf6w_* → Internal raw-staging for dead source
--
-- KEEP: airbyte_amazonc0rakm_* (internal raw-staging for active source).
--
-- Dropping stale tables is safe — views ads_agent.amazon_daily_v and
-- ads_agent.amazon_financials_daily_v only reference the KEEP list.
--
-- Apply:
--   sudo -u postgres psql -d shopify_app -f ops/scripts/cleanup_airbyte_amazon_stale_tables.sql

BEGIN;

\echo '=== Before: airbyte_amazon table count ==='
SELECT COUNT(*) AS tables_before FROM pg_tables WHERE schemaname = 'airbyte_amazon';

-- Sanity: fail loudly if the keep tables are missing
DO $$
DECLARE
    missing text;
BEGIN
    FOR missing IN
        SELECT unnest(ARRAY[
            'Orders','OrderItems','ListFinancialEvents','ListFinancialEventGroups',
            'fbsrf7_Orders','fbsrf7_OrderItems','fbsrf7_ListFinancialEvents','fbsrf7_ListFinancialEventGroups',
            'c0rakm_profiles'
        ])
    LOOP
        IF NOT EXISTS (
            SELECT 1 FROM pg_tables
            WHERE schemaname = 'airbyte_amazon' AND tablename = missing
        ) THEN
            RAISE EXCEPTION 'KEEP table missing, aborting: airbyte_amazon.%', missing;
        END IF;
    END LOOP;
END $$;

-- Drop everything NOT in the keep list
DO $$
DECLARE
    r          record;
    keep_list  text[] := ARRAY[
        -- India Seller Central
        'Orders','OrderItems','ListFinancialEvents','ListFinancialEventGroups',
        -- UAE Seller Central
        'fbsrf7_Orders','fbsrf7_OrderItems','fbsrf7_ListFinancialEvents','fbsrf7_ListFinancialEventGroups',
        -- Amazon Ads (c0rakm) metadata
        'c0rakm_profiles',
        'c0rakm_sponsored_product_ad_group_bid_recommendations',
        'c0rakm_sponsored_product_ad_group_suggested_keywords',
        'c0rakm_sponsored_product_ad_groups',
        'c0rakm_sponsored_product_ads',
        'c0rakm_sponsored_product_campaign_negative_keywords',
        'c0rakm_sponsored_product_campaigns',
        'c0rakm_sponsored_product_keywords',
        'c0rakm_sponsored_product_negative_keywords',
        'c0rakm_sponsored_product_targetings'
    ];
    dropped_count int := 0;
BEGIN
    FOR r IN
        SELECT schemaname, tablename
        FROM pg_tables
        WHERE schemaname = 'airbyte_amazon'
          AND NOT (tablename = ANY(keep_list))
          -- Keep c0rakm future report streams (e.g. c0rakm_sponsored_products_*_report_stream_daily)
          AND tablename NOT LIKE 'c0rakm\_%\_report\_stream%' ESCAPE '\'
          -- Keep Airbyte internal raw-staging for the active c0rakm source
          AND tablename NOT LIKE 'airbyte\_amazonc0rakm\_%' ESCAPE '\'
    LOOP
        EXECUTE format('DROP TABLE IF EXISTS %I.%I CASCADE', r.schemaname, r.tablename);
        dropped_count := dropped_count + 1;
    END LOOP;
    RAISE NOTICE 'Dropped % stale tables', dropped_count;
END $$;

\echo '=== After: airbyte_amazon table count ==='
SELECT COUNT(*) AS tables_after FROM pg_tables WHERE schemaname = 'airbyte_amazon';

\echo '=== Remaining tables ==='
SELECT tablename FROM pg_tables
WHERE schemaname = 'airbyte_amazon'
ORDER BY tablename;

-- Sanity: views still work
\echo '=== View sanity: ads_agent.amazon_daily_v ==='
SELECT store_slug, COUNT(*) AS rows, SUM(sales)::numeric(12,0) AS total_sales
FROM ads_agent.amazon_daily_v
GROUP BY 1 ORDER BY 1;

\echo '=== View sanity: ads_agent.amazon_financials_daily_v ==='
SELECT store_slug, COUNT(*) AS rows, SUM(net_amount)::numeric(12,0) AS total_net
FROM ads_agent.amazon_financials_daily_v
GROUP BY 1 ORDER BY 1;

COMMIT;
