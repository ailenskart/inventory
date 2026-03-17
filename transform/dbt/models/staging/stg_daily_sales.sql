-- Staging model for daily sales
{{ config(materialized='view') }}

select
    store_id,
    sku_id,
    sale_date,
    qty_sold,
    revenue,
    discount,
    fulfillment_type,
    is_return
from {{ source('raw', 'daily_sales') }}
where qty_sold >= 0
