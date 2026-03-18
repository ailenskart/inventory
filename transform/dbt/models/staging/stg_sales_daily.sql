/*
    stg_sales_daily — Cleaned daily sales transactions.

    Semantic signal types:
    - sell_through_signal: physical product sold from store stock (direct_sell)
    - prescription_order_signal: order captured via display frame (order_capture)

    Grain: store_id × sku_id × sale_date (may have multiple rows if both channels)
*/
{{ config(materialized='view') }}

select
    store_id,
    sku_id,
    cast(sale_date as date)         as sale_date,
    cast(qty_sold as integer)       as qty_sold,
    cast(revenue as double)         as revenue,
    cast(discount as double)        as discount_amount,
    fulfillment_type,
    sales_channel,
    cast(is_return as boolean)      as is_return,

    -- Semantic demand signals
    case
        when fulfillment_type = 'direct_sell'
        then cast(qty_sold as integer)
        else 0
    end as sell_through_signal,

    case
        when fulfillment_type = 'order_capture'
        then cast(qty_sold as integer)
        else 0
    end as prescription_order_signal

from {{ source('raw', 'daily_sales') }}
where cast(qty_sold as integer) >= 0
