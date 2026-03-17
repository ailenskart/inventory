/*
    dim_store — Store dimension with cluster profiles.

    Assumptions:
    - store_cluster determines demand profile (traffic, conversion, category affinity)
    - display_capacity = max frames that can be shown on the display wall
    - storage_capacity = total back-storage units
    - Inactive stores are included but flagged
*/
{{ config(materialized='table') }}

select
    store_id,
    store_name,
    city,
    state,
    region,
    pincode,
    store_type,
    store_format,
    store_cluster,
    cast(latitude as double)             as latitude,
    cast(longitude as double)            as longitude,
    cast(opening_date as date)           as opening_date,
    cast(is_active as boolean)           as is_active,
    cast(display_capacity as integer)    as display_capacity,
    cast(storage_capacity as integer)    as storage_capacity

from {{ source('raw', 'stores') }}
