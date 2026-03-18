/*
    dim_vendor — Vendor dimension with supply chain attributes.

    reliability_score: 0–1, based on historical on-time delivery rate.
    MOQ/MOV: minimum order constraints for PO generation.
*/
{{ config(materialized='table') }}

select
    vendor_id,
    vendor_name,
    vendor_type,
    contact_email,
    contact_phone,
    city,
    state,
    cast(avg_lead_time_days as integer)      as avg_lead_time_days,
    cast(min_order_value as double)          as min_order_value,
    cast(min_order_qty as integer)           as min_order_qty,
    cast(reliability_score as double)        as reliability_score,
    cast(is_active as boolean)               as is_active

from {{ source('raw', 'vendors') }}
