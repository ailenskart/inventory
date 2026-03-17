/*
    stg_receipts_daily — Goods received at stores.

    Sources: warehouse replenishment, vendor direct, inter-store transfer.

    Grain: receipt_id (one row per receipt event)
*/
{{ config(materialized='view') }}

select
    receipt_id,
    store_id,
    sku_id,
    cast(receipt_date as date)      as receipt_date,
    cast(qty_received as integer)   as qty_received,
    source_type,
    source_id,
    case when po_id = '' then null else po_id end as po_id

from {{ source('raw', 'receipts') }}
where cast(qty_received as integer) > 0
