/*
    mart_vendor_performance — Vendor scorecard for procurement decisions.

    Aggregates PO delivery performance, SKU portfolio health, and revenue
    contribution per vendor. Feeds into automated PO generation logic.

    Grain: vendor_id
*/
{{ config(materialized='table') }}

with po_stats as (
    select
        vendor_id,
        count(*)                                                as total_pos,
        sum(case when status = 'received' then 1 else 0 end)    as received_pos,
        sum(case when status = 'in_transit' then 1 else 0 end)  as in_transit_pos,
        sum(total_qty)                                           as total_units_ordered,
        sum(total_value)                                         as total_po_value,
        avg(case when delivery_delay_days is not null then delivery_delay_days else null end) as avg_delivery_delay_days,
        sum(case when delivery_delay_days is not null and delivery_delay_days > 0 then 1 else 0 end) as late_deliveries,
        sum(case when delivery_delay_days is not null and delivery_delay_days <= 0 then 1 else 0 end) as on_time_deliveries
    from {{ ref('stg_purchase_orders') }}
    group by vendor_id
),

sku_portfolio as (
    select
        vendor_id,
        count(distinct sku_id)                                       as total_skus,
        sum(case when lifecycle_stage = 'active' then 1 else 0 end)  as active_skus,
        sum(case when lifecycle_stage = 'new' then 1 else 0 end)     as new_skus,
        sum(case when lifecycle_stage = 'aging' then 1 else 0 end)   as aging_skus,
        sum(case when lifecycle_stage = 'eol' then 1 else 0 end)     as eol_skus,
        sum(case when sku_type = 'display_dummy' then 1 else 0 end)  as display_dummy_skus,
        sum(case when sku_type = 'physical_sell' then 1 else 0 end)  as physical_sell_skus,
        avg(mrp)                                                      as avg_mrp,
        avg(lead_time_days)                                           as avg_sku_lead_time
    from {{ ref('dim_sku') }}
    group by vendor_id
),

sales_contribution as (
    select
        sk.vendor_id,
        sum(db.total_qty_sold)                  as total_units_sold,
        sum(db.total_revenue)                   as total_revenue,
        count(distinct db.store_id)             as stores_selling,
        count(distinct db.sku_id)               as skus_with_sales
    from {{ ref('mart_demand_base') }} db
    left join {{ ref('dim_sku') }} sk on db.sku_id = sk.sku_id
    group by sk.vendor_id
)

select
    v.vendor_id,
    v.vendor_name,
    v.vendor_type,
    v.avg_lead_time_days,
    v.min_order_value,
    v.min_order_qty,
    v.reliability_score,
    v.is_active,

    -- PO performance
    coalesce(po.total_pos, 0)                   as total_pos,
    coalesce(po.received_pos, 0)                as received_pos,
    coalesce(po.total_units_ordered, 0)         as total_units_ordered,
    coalesce(po.total_po_value, 0)              as total_po_value,
    round(coalesce(po.avg_delivery_delay_days, 0), 1) as avg_delivery_delay_days,
    coalesce(po.late_deliveries, 0)             as late_deliveries,
    coalesce(po.on_time_deliveries, 0)          as on_time_deliveries,
    case
        when coalesce(po.received_pos, 0) > 0
        then round(cast(coalesce(po.on_time_deliveries, 0) as double) / po.received_pos, 3)
        else null
    end as on_time_rate,

    -- SKU portfolio
    coalesce(sp.total_skus, 0)                  as total_skus,
    coalesce(sp.active_skus, 0)                 as active_skus,
    coalesce(sp.eol_skus, 0)                    as eol_skus,
    coalesce(sp.display_dummy_skus, 0)          as display_dummy_skus,
    coalesce(sp.physical_sell_skus, 0)          as physical_sell_skus,
    round(coalesce(sp.avg_mrp, 0), 2)           as avg_mrp,

    -- Sales contribution
    coalesce(sc.total_units_sold, 0)            as total_units_sold,
    coalesce(sc.total_revenue, 0)               as total_revenue,
    coalesce(sc.stores_selling, 0)              as stores_selling

from {{ ref('dim_vendor') }} v
left join po_stats po on v.vendor_id = po.vendor_id
left join sku_portfolio sp on v.vendor_id = sp.vendor_id
left join sales_contribution sc on v.vendor_id = sc.vendor_id
