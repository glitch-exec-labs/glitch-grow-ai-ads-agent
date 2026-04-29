-- Airbyte Amazon financials view — net-profit per day per marketplace.
--
-- Source: airbyte_amazon."ListFinancialEvents" (Finances API stream).
-- Aggregates four event lists that together make up Amazon's settlement math:
--
--   ShipmentEventList         → gross revenue (Principal/Tax/Shipping) and
--                               referral/closing/shipping fees (negative).
--   RefundEventList           → customer refunds (negative principal) and
--                               fee reimbursements (positive).
--   ProductAdsPaymentEventList → Sponsored Ads deducted from settlement (negative).
--   ServiceFeeEventList       → misc service fees (negative).
--
-- Every event has a PostedDate (when it hit the settlement ledger) and a
-- MarketplaceName we map to the same store_slug taxonomy as amazon_daily_v.
--
-- Signs: fees/refunds/ads are already negative in the JSON, so net_amount is
-- simply the sum of every CurrencyAmount we pull out.
--
-- Caveat: this keys on PostedDate (cash basis), not PurchaseDate (accrual).
-- So `net_amount for 2026-04-10` is money that *settled* on that date, which
-- may belong to orders placed days earlier. That's what you actually want for
-- profit tracking — it matches the money landing in your bank account.
--
-- Apply:
--   sudo -u postgres psql -d shopify_app -f ops/scripts/migrate_airbyte_amazon_financials_view.sql

DROP VIEW IF EXISTS ads_agent.amazon_financials_daily_v;

CREATE VIEW ads_agent.amazon_financials_daily_v AS
WITH

-- ─── Shipment events: revenue + per-item fees ───────────────────────────────
shipment_rows AS (
    SELECT
        (evt->>'PostedDate')::timestamptz                      AS posted_at,
        evt->>'MarketplaceName'                                AS marketplace_name,
        item->>'SellerSKU'                                     AS sku,
        COALESCE((charge->'ChargeAmount'->>'CurrencyAmount')::numeric, 0) AS charge_amt,
        charge->>'ChargeType'                                  AS charge_type,
        COALESCE((fee->'FeeAmount'->>'CurrencyAmount')::numeric, 0)       AS fee_amt,
        fee->>'FeeType'                                        AS fee_type
    FROM airbyte_amazon."ListFinancialEvents" lfe
    LEFT JOIN LATERAL jsonb_array_elements(COALESCE(lfe."ShipmentEventList", '[]'::jsonb)) AS evt ON true
    LEFT JOIN LATERAL jsonb_array_elements(COALESCE(evt->'ShipmentItemList',  '[]'::jsonb)) AS item ON true
    LEFT JOIN LATERAL jsonb_array_elements(COALESCE(item->'ItemChargeList',   '[]'::jsonb)) AS charge ON true
    LEFT JOIN LATERAL jsonb_array_elements(COALESCE(item->'ItemFeeList',      '[]'::jsonb)) AS fee ON true
),

-- ─── Refund events: negative charges + fee reversals ────────────────────────
refund_rows AS (
    SELECT
        (evt->>'PostedDate')::timestamptz                      AS posted_at,
        evt->>'MarketplaceName'                                AS marketplace_name,
        COALESCE((charge->'ChargeAmount'->>'CurrencyAmount')::numeric, 0) AS charge_amt,
        COALESCE((fee->'FeeAmount'->>'CurrencyAmount')::numeric, 0)       AS fee_amt
    FROM airbyte_amazon."ListFinancialEvents" lfe
    LEFT JOIN LATERAL jsonb_array_elements(COALESCE(lfe."RefundEventList", '[]'::jsonb)) AS evt ON true
    LEFT JOIN LATERAL jsonb_array_elements(COALESCE(evt->'ShipmentItemAdjustmentList', '[]'::jsonb)) AS item ON true
    LEFT JOIN LATERAL jsonb_array_elements(COALESCE(item->'ItemChargeAdjustmentList',  '[]'::jsonb)) AS charge ON true
    LEFT JOIN LATERAL jsonb_array_elements(COALESCE(item->'ItemFeeAdjustmentList',     '[]'::jsonb)) AS fee ON true
),

-- ─── Sponsored Ads deductions ───────────────────────────────────────────────
ads_rows AS (
    SELECT
        (evt->>'postedDate')::timestamptz                      AS posted_at,
        NULL::text                                             AS marketplace_name,
        COALESCE((evt->'transactionValue'->>'CurrencyAmount')::numeric, 0) AS amount
    FROM airbyte_amazon."ListFinancialEvents" lfe
    LEFT JOIN LATERAL jsonb_array_elements(COALESCE(lfe."ProductAdsPaymentEventList", '[]'::jsonb)) AS evt ON true
),

-- ─── Service fees (monthly subscription, storage, misc) ─────────────────────
service_fee_rows AS (
    SELECT
        (evt->>'FeeReason')::text                              AS _unused,
        (evt->>'PostedDate')::timestamptz                      AS posted_at,
        COALESCE((fee->'FeeAmount'->>'CurrencyAmount')::numeric, 0) AS fee_amt
    FROM airbyte_amazon."ListFinancialEvents" lfe
    LEFT JOIN LATERAL jsonb_array_elements(COALESCE(lfe."ServiceFeeEventList", '[]'::jsonb)) AS evt ON true
    LEFT JOIN LATERAL jsonb_array_elements(COALESCE(evt->'FeeList', '[]'::jsonb)) AS fee ON true
),

-- ─── Per-day aggregates, keyed by date + marketplace ────────────────────────
shipment_daily AS (
    SELECT
        (posted_at AT TIME ZONE 'UTC')::date                   AS date,
        marketplace_name,
        sum(CASE WHEN charge_amt > 0 THEN charge_amt ELSE 0 END) AS gross_revenue,
        sum(CASE WHEN charge_amt < 0 THEN charge_amt ELSE 0 END) AS shipment_adjustments,
        sum(fee_amt)                                             AS fees
    FROM shipment_rows
    WHERE posted_at IS NOT NULL
    GROUP BY 1, 2
),
refund_daily AS (
    SELECT
        (posted_at AT TIME ZONE 'UTC')::date                   AS date,
        marketplace_name,
        sum(charge_amt)                                        AS refund_principal,
        sum(fee_amt)                                           AS refund_fee_reversal
    FROM refund_rows
    WHERE posted_at IS NOT NULL
    GROUP BY 1, 2
),
ads_daily AS (
    SELECT
        (posted_at AT TIME ZONE 'UTC')::date                   AS date,
        sum(amount)                                            AS ads_deducted
    FROM ads_rows
    WHERE posted_at IS NOT NULL
    GROUP BY 1
),
service_fee_daily AS (
    SELECT
        (posted_at AT TIME ZONE 'UTC')::date                   AS date,
        sum(fee_amt)                                           AS service_fees
    FROM service_fee_rows
    WHERE posted_at IS NOT NULL
    GROUP BY 1
),

-- ─── Spine: every (date, marketplace) that appears anywhere ─────────────────
spine AS (
    SELECT date, marketplace_name FROM shipment_daily
    UNION
    SELECT date, marketplace_name FROM refund_daily
)

SELECT
    s.date,
    CASE s.marketplace_name
        WHEN 'Amazon.in' THEN 'store-a'
        WHEN 'Amazon.ae' THEN 'store-b'
        WHEN 'Amazon.com' THEN 'store-b'
        WHEN 'Amazon.co.uk' THEN 'store-b'
        WHEN 'Amazon.ca' THEN 'store-b'
        WHEN 'Amazon.de' THEN 'store-b'
        WHEN 'Amazon.fr' THEN 'store-b'
        WHEN 'Amazon.it' THEN 'store-b'
        WHEN 'Amazon.es' THEN 'store-b'
        ELSE 'unknown'
    END                                                        AS store_slug,
    s.marketplace_name                                         AS marketplace,
    COALESCE(sh.gross_revenue, 0)                              AS gross_revenue,
    COALESCE(sh.fees, 0)                                       AS fees,
    COALESCE(sh.shipment_adjustments, 0)                       AS shipment_adjustments,
    COALESCE(rf.refund_principal, 0)                           AS refunds,
    COALESCE(rf.refund_fee_reversal, 0)                        AS refund_fee_reversal,
    -- Ads + service fees are not marketplace-scoped in the JSON, so we
    -- attribute them to Amazon.in (India) where 100% of current ads/service
    -- events originate. When UAE ads data starts flowing, we'll revisit.
    CASE WHEN s.marketplace_name = 'Amazon.in'
         THEN COALESCE(ad.ads_deducted, 0) ELSE 0 END          AS ads_deducted,
    CASE WHEN s.marketplace_name = 'Amazon.in'
         THEN COALESCE(sf.service_fees, 0) ELSE 0 END          AS service_fees,
    -- Net = everything summed. Signs in the JSON already encode direction.
    COALESCE(sh.gross_revenue, 0)
      + COALESCE(sh.shipment_adjustments, 0)
      + COALESCE(sh.fees, 0)
      + COALESCE(rf.refund_principal, 0)
      + COALESCE(rf.refund_fee_reversal, 0)
      + CASE WHEN s.marketplace_name = 'Amazon.in' THEN COALESCE(ad.ads_deducted, 0) ELSE 0 END
      + CASE WHEN s.marketplace_name = 'Amazon.in' THEN COALESCE(sf.service_fees, 0) ELSE 0 END
                                                               AS net_amount,
    'INR'                                                      AS currency  -- TODO: per-marketplace FX when UAE settles
FROM spine s
LEFT JOIN shipment_daily    sh ON sh.date = s.date AND sh.marketplace_name = s.marketplace_name
LEFT JOIN refund_daily      rf ON rf.date = s.date AND rf.marketplace_name = s.marketplace_name
LEFT JOIN ads_daily         ad ON ad.date = s.date
LEFT JOIN service_fee_daily sf ON sf.date = s.date
;

GRANT SELECT ON ads_agent.amazon_financials_daily_v TO shopify_app;
