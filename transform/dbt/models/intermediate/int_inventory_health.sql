-- Inventory health metrics by store x sku
{{ config(materialized='table') }}

with latest_inventory as (
    select
        store_id,
        sku_id,
        snapshot_date,
        on_hand_qty,
        on_display_qty,
        in_storage_qty,
        available_qty,
        row_number() over (partition by store_id, sku_id order by snapshot_date desc) as rn
    from {{ ref('stg_daily_inventory') }}
),

avg_sales as (
    select
        store_id,
        sku_id,
        avg(total_qty_sold) as avg_weekly_sales
    from {{ ref('int_weekly_sales') }}
    group by store_id, sku_id
)

select
    li.store_id,
    li.sku_id,
    li.snapshot_date as latest_date,
    li.on_hand_qty,
    li.on_display_qty,
    li.available_qty,
    coalesce(s.avg_weekly_sales, 0) as avg_weekly_sales,
    case
        when coalesce(s.avg_weekly_sales, 0) > 0
        then round(li.on_hand_qty / s.avg_weekly_sales, 1)
        else null
    end as weeks_of_supply,
    case
        when li.on_hand_qty = 0 then 'stockout'
        when coalesce(s.avg_weekly_sales, 0) > 0
            and li.on_hand_qty / s.avg_weekly_sales < 2 then 'low'
        when coalesce(s.avg_weekly_sales, 0) > 0
            and li.on_hand_qty / s.avg_weekly_sales > 12 then 'excess'
        else 'healthy'
    end as inventory_status
from latest_inventory li
left join avg_sales s on li.store_id = s.store_id and li.sku_id = s.sku_id
where li.rn = 1
