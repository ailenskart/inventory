-- Weekly aggregated sales at SKU x Store granularity
{{ config(materialized='table') }}

select
    store_id,
    sku_id,
    date_trunc('week', sale_date) as week_start,
    sum(qty_sold) as total_qty_sold,
    sum(revenue) as total_revenue,
    sum(discount) as total_discount,
    count(*) as sale_days,
    sum(case when is_return then qty_sold else 0 end) as return_qty,
    sum(case when fulfillment_type = 'direct_sell' then qty_sold else 0 end) as direct_sell_qty,
    sum(case when fulfillment_type = 'order_capture' then qty_sold else 0 end) as order_capture_qty
from {{ ref('stg_daily_sales') }}
group by store_id, sku_id, date_trunc('week', sale_date)
