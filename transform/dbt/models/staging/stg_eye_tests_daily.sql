/*
    stg_eye_tests_daily — Eye examinations and prescription captures.

    Eye tests are a strong prescription_order_signal: ~75% of tests result
    in an eyeglass purchase. Stores with high eye test volumes need deeper
    display assortment and faster prescription fulfillment.

    Grain: test_id
*/
{{ config(materialized='view') }}

select
    test_id,
    store_id,
    cast(test_date as date)                 as test_date,
    case when customer_id = '' then null else customer_id end as customer_id,
    cast(sph_right as double)               as sph_right,
    cast(cyl_right as double)               as cyl_right,
    cast(sph_left as double)                as sph_left,
    cast(cyl_left as double)                as cyl_left,
    cast(resulted_in_purchase as boolean)    as resulted_in_purchase,
    case when order_id = '' then null else order_id end as order_id,

    -- prescription_order_signal: each test = 1 signal unit
    1 as prescription_order_signal

from {{ source('raw', 'eye_tests') }}
