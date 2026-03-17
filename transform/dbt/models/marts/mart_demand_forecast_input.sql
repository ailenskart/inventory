-- Mart: Demand forecast input dataset at SKU x Store x Week
-- This feeds directly into the ML forecasting pipeline
{{ config(materialized='table') }}

select
    ws.store_id,
    ws.sku_id,
    ws.week_start,
    ws.total_qty_sold,
    ws.total_revenue,
    ws.direct_sell_qty,
    ws.order_capture_qty,
    coalesce(wt.total_trials, 0) as total_trials,
    coalesce(wt.trial_conversion_rate, 0) as trial_conversion_rate,
    s.city,
    s.state,
    s.region,
    s.store_type,
    s.store_format,
    s.cluster_id,
    sk.brand,
    sk.category,
    sk.subcategory,
    sk.frame_type,
    sk.frame_shape,
    sk.fulfillment_type,
    sk.mrp,
    sk.lifecycle_stage
from {{ ref('int_weekly_sales') }} ws
left join {{ ref('int_weekly_trials') }} wt
    on ws.store_id = wt.store_id
    and ws.sku_id = wt.sku_id
    and ws.week_start = wt.week_start
left join {{ ref('stg_stores') }} s on ws.store_id = s.store_id
left join {{ ref('stg_skus') }} sk on ws.sku_id = sk.sku_id
