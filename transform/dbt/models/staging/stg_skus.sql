-- Staging model for SKUs
{{ config(materialized='view') }}

select
    sku_id,
    product_name,
    brand,
    category,
    subcategory,
    gender,
    frame_type,
    frame_shape,
    frame_material,
    frame_color,
    lens_type,
    size,
    mrp,
    cost_price,
    fulfillment_type,
    is_display_only,
    lifecycle_stage,
    vendor_id,
    lead_time_days,
    created_at,
    updated_at
from {{ source('raw', 'skus') }}
