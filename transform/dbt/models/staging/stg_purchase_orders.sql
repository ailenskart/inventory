/*
    stg_purchase_orders — Purchase orders to vendors.

    Grain: po_id
*/
{{ config(materialized='view') }}

select
    po_id,
    vendor_id,
    status,
    cast(order_date as date)                as order_date,
    cast(expected_delivery_date as date)    as expected_delivery_date,
    try_cast(actual_delivery_date as date)  as actual_delivery_date,
    cast(total_qty as integer)              as total_qty,
    cast(total_value as double)             as total_value,
    cast(num_lines as integer)              as num_lines,

    -- Derived: delivery delay in days (positive = late)
    case
        when try_cast(actual_delivery_date as date) is not null
        then datediff('day', cast(expected_delivery_date as date), try_cast(actual_delivery_date as date))
        else null
    end as delivery_delay_days

from {{ source('raw', 'purchase_orders') }}
