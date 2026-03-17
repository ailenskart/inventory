-- Staging model for stores
{{ config(materialized='view') }}

select
    store_id,
    store_name,
    city,
    state,
    region,
    pincode,
    store_type,
    store_format,
    cluster_id,
    latitude,
    longitude,
    opening_date,
    is_active,
    display_capacity,
    storage_capacity,
    created_at,
    updated_at
from {{ source('raw', 'stores') }}
