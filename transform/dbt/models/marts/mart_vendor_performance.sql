-- Mart: Vendor performance summary
{{ config(materialized='table') }}

select
    sk.vendor_id,
    sk.brand,
    count(distinct sk.sku_id) as total_skus,
    count(distinct ws.store_id) as stores_selling,
    sum(ws.total_qty_sold) as total_units_sold,
    sum(ws.total_revenue) as total_revenue,
    avg(sk.lead_time_days) as avg_lead_time_days,
    sum(case when sk.lifecycle_stage = 'active' then 1 else 0 end) as active_skus,
    sum(case when sk.lifecycle_stage = 'eol' then 1 else 0 end) as eol_skus
from {{ ref('stg_skus') }} sk
left join {{ ref('int_weekly_sales') }} ws on sk.sku_id = ws.sku_id
group by sk.vendor_id, sk.brand
