-- Mart: Store inventory health dashboard
{{ config(materialized='table') }}

select
    ih.store_id,
    s.store_name,
    s.city,
    s.region,
    s.store_format,
    s.cluster_id,
    count(distinct ih.sku_id) as total_skus,
    sum(case when ih.inventory_status = 'stockout' then 1 else 0 end) as stockout_skus,
    sum(case when ih.inventory_status = 'low' then 1 else 0 end) as low_stock_skus,
    sum(case when ih.inventory_status = 'excess' then 1 else 0 end) as excess_stock_skus,
    sum(case when ih.inventory_status = 'healthy' then 1 else 0 end) as healthy_skus,
    round(avg(ih.weeks_of_supply), 1) as avg_weeks_of_supply,
    sum(ih.on_hand_qty) as total_on_hand
from {{ ref('int_inventory_health') }} ih
left join {{ ref('stg_stores') }} s on ih.store_id = s.store_id
group by ih.store_id, s.store_name, s.city, s.region, s.store_format, s.cluster_id
