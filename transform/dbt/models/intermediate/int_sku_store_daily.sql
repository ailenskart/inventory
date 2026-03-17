/*
    int_sku_store_daily — Central daily fact at SKU × Store granularity.

    Joins all daily signals into a single spine:
    - sell_through_signal (physical sales)
    - prescription_order_signal (order capture from display frames)
    - display_interest_signal (trial/try-on count)
    - prescription_order_signal_eye_tests (eye test proxy)
    - inventory position
    - traffic context

    This is the foundational table for weekly rollups, forecasting, and optimization.

    Grain: store_id × sku_id × day_date
*/
{{ config(materialized='table') }}

with daily_sales_agg as (
    select
        store_id,
        sku_id,
        sale_date as day_date,
        sum(qty_sold)                       as total_qty_sold,
        sum(revenue)                        as total_revenue,
        sum(discount_amount)                as total_discount,
        sum(sell_through_signal)            as sell_through_signal,
        sum(prescription_order_signal)      as prescription_order_signal,
        sum(case when is_return then qty_sold else 0 end) as return_qty,
        max(fulfillment_type)               as primary_fulfillment_type,
        max(sales_channel)                  as primary_sales_channel
    from {{ ref('stg_sales_daily') }}
    group by store_id, sku_id, sale_date
),

daily_trials_agg as (
    select
        store_id,
        sku_id,
        trial_date as day_date,
        count(*)                            as trial_count,
        sum(display_interest_signal)        as display_interest_signal,
        sum(case when resulted_in_order then 1 else 0 end) as trials_with_order
    from {{ ref('stg_trials_daily') }}
    group by store_id, sku_id, trial_date
),

daily_eye_tests_agg as (
    select
        store_id,
        test_date as day_date,
        count(*)                                            as eye_test_count,
        sum(prescription_order_signal)                      as prescription_signal_eye_tests,
        sum(case when resulted_in_purchase then 1 else 0 end) as eye_tests_with_purchase
    from {{ ref('stg_eye_tests_daily') }}
    group by store_id, test_date
),

daily_traffic as (
    select
        store_id,
        traffic_date as day_date,
        footfall_count,
        walk_ins,
        appointments
    from {{ ref('stg_store_traffic_daily') }}
),

-- Build a spine of all store × sku × date combos that have any activity
spine as (
    select store_id, sku_id, day_date from daily_sales_agg
    union
    select store_id, sku_id, day_date from daily_trials_agg
)

select
    sp.store_id,
    sp.sku_id,
    sp.day_date,

    -- Sales signals
    coalesce(s.total_qty_sold, 0)               as qty_sold,
    coalesce(s.total_revenue, 0)                as revenue,
    coalesce(s.total_discount, 0)               as discount_amount,
    coalesce(s.sell_through_signal, 0)          as sell_through_signal,
    coalesce(s.prescription_order_signal, 0)    as prescription_order_signal,
    coalesce(s.return_qty, 0)                   as return_qty,
    s.primary_fulfillment_type,
    s.primary_sales_channel,

    -- Display interest signal (try-ons)
    coalesce(t.trial_count, 0)                  as trial_count,
    coalesce(t.display_interest_signal, 0)      as display_interest_signal,
    coalesce(t.trials_with_order, 0)            as trials_with_order,

    -- Eye test signal (store-level, not sku-level)
    coalesce(e.eye_test_count, 0)               as eye_test_count,
    coalesce(e.prescription_signal_eye_tests, 0) as prescription_signal_eye_tests,

    -- Inventory position (if snapshot exists for this date)
    inv.on_hand_qty,
    inv.on_display_qty,
    inv.in_storage_qty,
    inv.in_transit_qty,
    inv.available_qty,
    inv.is_stockout,

    -- Traffic context (store-level)
    coalesce(tr.footfall_count, 0)              as footfall_count,
    coalesce(tr.walk_ins, 0)                    as walk_ins

from spine sp

left join daily_sales_agg s
    on sp.store_id = s.store_id and sp.sku_id = s.sku_id and sp.day_date = s.day_date

left join daily_trials_agg t
    on sp.store_id = t.store_id and sp.sku_id = t.sku_id and sp.day_date = t.day_date

left join daily_eye_tests_agg e
    on sp.store_id = e.store_id and sp.day_date = e.day_date

left join {{ ref('stg_inventory_daily') }} inv
    on sp.store_id = inv.store_id and sp.sku_id = inv.sku_id and sp.day_date = inv.snapshot_date

left join daily_traffic tr
    on sp.store_id = tr.store_id and sp.day_date = tr.day_date
