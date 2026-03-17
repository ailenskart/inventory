/*
    mart_inventory_position — Current inventory health at SKU × Store.

    Combines latest inventory snapshot with sales velocity to compute
    weeks-of-supply, stockout risk, and excess detection.

    Key metrics:
    - weeks_of_supply: on_hand / avg_weekly_demand
    - inventory_status: stockout | critical | low | healthy | excess | dead
    - days_since_last_sale: freshness indicator

    Grain: store_id × sku_id (latest position)
*/
{{ config(materialized='table') }}

with latest_inventory as (
    select
        store_id,
        sku_id,
        snapshot_date,
        on_hand_qty,
        on_display_qty,
        in_storage_qty,
        in_transit_qty,
        available_qty,
        is_stockout,
        row_number() over (partition by store_id, sku_id order by snapshot_date desc) as rn
    from {{ ref('stg_inventory_daily') }}
),

-- Average weekly demand over last 8 weeks
max_week as (
    select max(week_start) as mw from {{ ref('mart_demand_base') }}
),

recent_demand as (
    select
        db.store_id,
        db.sku_id,
        avg(db.total_qty_sold)     as avg_weekly_demand,
        sum(db.total_qty_sold)     as total_8wk_demand,
        max(db.week_start)         as last_sale_week
    from {{ ref('mart_demand_base') }} db
    cross join max_week mw
    where db.week_start >= mw.mw - interval 56 day
    group by db.store_id, db.sku_id
),

-- Last receipt
last_receipt as (
    select
        store_id,
        sku_id,
        max(receipt_date) as last_receipt_date
    from {{ ref('stg_receipts_daily') }}
    group by store_id, sku_id
)

select
    li.store_id,
    li.sku_id,
    li.snapshot_date                                    as latest_snapshot_date,
    li.on_hand_qty,
    li.on_display_qty,
    li.in_storage_qty,
    li.in_transit_qty,
    li.available_qty,
    li.is_stockout,

    coalesce(rd.avg_weekly_demand, 0)                   as avg_weekly_demand,
    coalesce(rd.total_8wk_demand, 0)                    as total_8wk_demand,

    -- Weeks of supply
    case
        when coalesce(rd.avg_weekly_demand, 0) > 0
        then round(cast(li.on_hand_qty as double) / rd.avg_weekly_demand, 1)
        else null
    end as weeks_of_supply,

    -- Inventory health classification
    case
        when li.on_hand_qty = 0 and li.in_transit_qty = 0
            then 'stockout'
        when li.on_hand_qty = 0 and li.in_transit_qty > 0
            then 'stockout_pending_receipt'
        when coalesce(rd.avg_weekly_demand, 0) > 0 and
             cast(li.on_hand_qty as double) / rd.avg_weekly_demand < 1.0
            then 'critical'
        when coalesce(rd.avg_weekly_demand, 0) > 0 and
             cast(li.on_hand_qty as double) / rd.avg_weekly_demand < 2.0
            then 'low'
        when coalesce(rd.avg_weekly_demand, 0) > 0 and
             cast(li.on_hand_qty as double) / rd.avg_weekly_demand > 12.0
            then 'excess'
        when coalesce(rd.avg_weekly_demand, 0) = 0 and li.on_hand_qty > 0
            then 'dead_stock'
        else 'healthy'
    end as inventory_status,

    lr.last_receipt_date,

    -- Store + SKU enrichment
    st.store_cluster,
    st.store_format,
    st.region,
    sk.category,
    sk.sku_type,
    sk.fulfillment_type,
    sk.lifecycle_stage,
    sk.is_display_only,
    sk.vendor_id

from latest_inventory li
left join recent_demand rd on li.store_id = rd.store_id and li.sku_id = rd.sku_id
left join last_receipt lr on li.store_id = lr.store_id and li.sku_id = lr.sku_id
left join {{ ref('dim_store') }} st on li.store_id = st.store_id
left join {{ ref('dim_sku') }} sk on li.sku_id = sk.sku_id
where li.rn = 1
