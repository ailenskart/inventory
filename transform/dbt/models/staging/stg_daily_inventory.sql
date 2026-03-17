-- Staging model for daily inventory snapshots
{{ config(materialized='view') }}

select
    store_id,
    sku_id,
    snapshot_date,
    on_hand_qty,
    on_display_qty,
    in_storage_qty,
    in_transit_qty,
    allocated_qty,
    available_qty
from {{ source('raw', 'daily_inventory') }}
