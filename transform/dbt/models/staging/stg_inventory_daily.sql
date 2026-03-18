/*
    stg_inventory_daily — Daily inventory position snapshots.

    For display-only SKUs, available_qty = 0 (not sellable from stock).
    Physical-sell SKUs have real inventory that fluctuates.

    Grain: store_id × sku_id × snapshot_date
*/
{{ config(materialized='view') }}

select
    store_id,
    sku_id,
    cast(snapshot_date as date)     as snapshot_date,
    cast(on_hand_qty as integer)    as on_hand_qty,
    cast(on_display_qty as integer) as on_display_qty,
    cast(in_storage_qty as integer) as in_storage_qty,
    cast(in_transit_qty as integer) as in_transit_qty,
    cast(allocated_qty as integer)  as allocated_qty,
    cast(available_qty as integer)  as available_qty,

    -- Derived: is this a stockout?
    cast(case when cast(on_hand_qty as integer) = 0 then 1 else 0 end as integer) as is_stockout

from {{ source('raw', 'daily_inventory') }}
