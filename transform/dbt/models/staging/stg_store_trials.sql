-- Staging model for store try-on events
{{ config(materialized='view') }}

select
    trial_id,
    store_id,
    sku_id,
    trial_date,
    trial_time,
    customer_id,
    resulted_in_order,
    order_id
from {{ source('raw', 'store_trials') }}
