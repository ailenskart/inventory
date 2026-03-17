/*
    mart_demand_base — Weekly demand dataset at SKU × Store × Week granularity.

    This is THE input to the ML forecasting pipeline. Rolls up daily signals
    into weekly aggregates and enriches with store/SKU/calendar dimensions.

    Three distinct demand signals:
    1. sell_through_signal — physical units sold from stock (sunglasses, last-piece)
    2. prescription_order_signal — orders captured via display frames
    3. display_interest_signal — try-on events (leading indicator)

    Grain: store_id × sku_id × week_start
*/
{{ config(materialized='table') }}

with weekly as (
    select
        f.store_id,
        f.sku_id,
        date_trunc('week', f.day_date)              as week_start,

        -- Core demand signals (weekly totals)
        sum(f.qty_sold)                              as total_qty_sold,
        sum(f.revenue)                               as total_revenue,
        sum(f.discount_amount)                       as total_discount,
        sum(f.sell_through_signal)                   as sell_through_signal,
        sum(f.prescription_order_signal)             as prescription_order_signal,
        sum(f.display_interest_signal)               as display_interest_signal,
        sum(f.return_qty)                            as return_qty,

        -- Eye test context (store-level, deduplicated)
        max(f.prescription_signal_eye_tests)         as weekly_eye_tests_max,

        -- Inventory context (latest snapshot in the week)
        max(f.on_hand_qty)                           as max_on_hand_qty,
        min(f.on_hand_qty)                           as min_on_hand_qty,
        max(case when f.is_stockout then 1 else 0 end) as had_stockout,

        -- Traffic context
        avg(f.footfall_count)                        as avg_daily_footfall,

        -- Activity counts
        count(distinct f.day_date)                   as active_days

    from {{ ref('int_sku_store_daily') }} f
    group by f.store_id, f.sku_id, date_trunc('week', f.day_date)
)

select
    w.store_id,
    w.sku_id,
    w.week_start,

    -- Demand signals
    w.total_qty_sold,
    w.total_revenue,
    w.total_discount,
    w.sell_through_signal,
    w.prescription_order_signal,
    w.display_interest_signal,
    w.return_qty,
    w.weekly_eye_tests_max,

    -- Derived: trial conversion rate
    case
        when w.display_interest_signal > 0
        then round(cast(w.prescription_order_signal as double) / w.display_interest_signal, 4)
        else null
    end as trial_conversion_rate,

    -- Inventory context
    w.max_on_hand_qty,
    w.min_on_hand_qty,
    w.had_stockout,
    w.avg_daily_footfall,
    w.active_days,

    -- Store dimensions
    st.city,
    st.state,
    st.region,
    st.store_type,
    st.store_format,
    st.store_cluster,

    -- SKU dimensions
    sk.brand,
    sk.category,
    sk.subcategory,
    sk.sku_type,
    sk.fulfillment_type,
    sk.sales_channel,
    sk.frame_type,
    sk.frame_shape,
    sk.mrp,
    sk.lifecycle_stage,
    sk.is_display_only,

    -- Calendar dimensions
    cal.month,
    cal.quarter,
    cal.is_festive,
    cal.season

from weekly w
left join {{ ref('dim_store') }} st on w.store_id = st.store_id
left join {{ ref('dim_sku') }} sk on w.sku_id = sk.sku_id
left join {{ ref('dim_calendar') }} cal on w.week_start = cal.date_key
