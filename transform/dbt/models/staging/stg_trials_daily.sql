/*
    stg_trials_daily — Store try-on events (display_interest_signal).

    A trial is when a customer tries on a display frame. This is the primary
    demand signal for dummy/display-only eyeglasses. High trial counts for a
    frame indicate strong interest even if no immediate purchase.

    Grain: trial_id
*/
{{ config(materialized='view') }}

select
    trial_id,
    store_id,
    sku_id,
    cast(trial_date as date)                    as trial_date,
    cast(trial_timestamp as timestamp)          as trial_timestamp,
    case when customer_id = '' then null else customer_id end as customer_id,
    cast(resulted_in_order as boolean)           as resulted_in_order,
    case when order_id = '' then null else order_id end as order_id,

    -- This is the display_interest_signal: each trial = 1 signal unit
    1 as display_interest_signal

from {{ source('raw', 'store_trials') }}
