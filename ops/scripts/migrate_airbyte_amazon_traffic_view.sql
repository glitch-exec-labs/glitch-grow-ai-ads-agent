-- Amazon daily traffic + sales roll-up per store — the ground-truth session layer.
--
-- Source: GET_SALES_AND_TRAFFIC_REPORT_BY_DATE (and UAE fbsrf7_ counterpart)
-- which Amazon SP-API delivers as one row per date per marketplace with jsonb
-- payloads salesByDate + trafficByDate. This view extracts the numeric fields
-- we care about for Meta→Amazon attribution sessions-delta analysis.
--
-- Grain: (date × store_slug) — one row per marketplace per day. No ASIN grain
-- here because the BY_DATE variant aggregates across all ASINs; for ASIN-level
-- session data, the BY_ASIN variant (GET_SALES_AND_TRAFFIC_REPORT) exists but
-- is currently thin — Amazon only reports ASINs that had non-zero activity on
-- top-N days, so most SKUs have no rows. We use BY_DATE as the authoritative
-- daily signal and keep the BY_ASIN view for future per-SKU analysis if the
-- data densifies.
--
-- Apply:
--   sudo -u postgres psql -d shopify_app -f ops/scripts/migrate_airbyte_amazon_traffic_view.sql

DROP VIEW IF EXISTS ads_agent.amazon_traffic_daily_v;

CREATE VIEW ads_agent.amazon_traffic_daily_v AS
SELECT
    date,
    'store-a'::text                                            AS store_slug,
    'A21TJRUUN4KGV'::text                                          AS account_id,
    'Amazon.in'::text                                              AS marketplace,
    ("trafficByDate"->>'sessions')::int                            AS sessions,
    ("trafficByDate"->>'sessionsB2B')::int                         AS sessions_b2b,
    ("trafficByDate"->>'pageViews')::int                           AS pageviews,
    ("trafficByDate"->>'browserSessions')::int                     AS browser_sessions,
    ("trafficByDate"->>'mobileAppSessions')::int                   AS mobile_sessions,
    ("trafficByDate"->>'buyBoxPercentage')::numeric                AS buy_box_pct,
    ("trafficByDate"->>'unitSessionPercentage')::numeric           AS unit_session_pct, -- Amazon's CVR
    ("trafficByDate"->>'orderItemSessionPercentage')::numeric      AS orderitem_session_pct,
    ("salesByDate"->>'unitsOrdered')::int                          AS units_ordered,
    ("salesByDate"->>'totalOrderItems')::int                       AS order_items,
    ("salesByDate"->>'ordersShipped')::int                         AS orders_shipped,
    ("salesByDate"->>'unitsRefunded')::int                         AS units_refunded,
    ("salesByDate"->>'refundRate')::numeric                        AS refund_rate,
    ("salesByDate"->'orderedProductSales'->>'amount')::numeric     AS gross,
    ("salesByDate"->'orderedProductSales'->>'currencyCode')::text  AS currency,
    ("salesByDate"->'averageSellingPrice'->>'amount')::numeric     AS avg_selling_price,
    _airbyte_extracted_at                                          AS synced_at
FROM airbyte_amazon."GET_SALES_AND_TRAFFIC_REPORT_BY_DATE"

UNION ALL

SELECT
    date,
    'store-b'::text,
    'A2VIGQ35RCS4UG'::text,
    'Amazon.ae'::text,
    ("trafficByDate"->>'sessions')::int,
    ("trafficByDate"->>'sessionsB2B')::int,
    ("trafficByDate"->>'pageViews')::int,
    ("trafficByDate"->>'browserSessions')::int,
    ("trafficByDate"->>'mobileAppSessions')::int,
    ("trafficByDate"->>'buyBoxPercentage')::numeric,
    ("trafficByDate"->>'unitSessionPercentage')::numeric,
    ("trafficByDate"->>'orderItemSessionPercentage')::numeric,
    ("salesByDate"->>'unitsOrdered')::int,
    ("salesByDate"->>'totalOrderItems')::int,
    ("salesByDate"->>'ordersShipped')::int,
    ("salesByDate"->>'unitsRefunded')::int,
    ("salesByDate"->>'refundRate')::numeric,
    ("salesByDate"->'orderedProductSales'->>'amount')::numeric,
    ("salesByDate"->'orderedProductSales'->>'currencyCode')::text,
    ("salesByDate"->'averageSellingPrice'->>'amount')::numeric,
    _airbyte_extracted_at
FROM airbyte_amazon."fbsrf7_GET_SALES_AND_TRAFFIC_REPORT_BY_DATE"
;

GRANT SELECT ON ads_agent.amazon_traffic_daily_v TO shopify_app;
