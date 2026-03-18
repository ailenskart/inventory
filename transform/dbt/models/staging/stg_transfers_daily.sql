/*
    stg_transfers_daily — Inter-store inventory transfers.

    Each transfer_id has two rows: direction='out' at source, direction='in' at destination.
    Eventually, transfer_out qty must balance transfer_in qty.

    Grain: transfer_id × transfer_direction
*/
{{ config(materialized='view') }}

select
    transfer_id,
    from_store_id,
    to_store_id,
    sku_id,
    cast(transfer_qty as integer)   as transfer_qty,
    transfer_direction,
    status,
    cast(initiated_date as date)    as initiated_date,
    case when completed_date = '' then null else cast(completed_date as date) end as completed_date,
    reason

from {{ source('raw', 'transfers') }}
