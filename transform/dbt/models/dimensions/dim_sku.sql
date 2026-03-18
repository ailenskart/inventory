/*
    dim_sku — SKU dimension with product attributes and fulfillment classification.

    Key business concepts:
    - sku_type: 'display_dummy' (try-on frame, order capture) vs 'physical_sell' (sold from stock)
    - fulfillment_type: 'order_capture' (prescription made after order) vs 'direct_sell' (walk out with product)
    - sales_channel: 'prescription' vs 'walk_in'
    - lifecycle_stage: new → active → aging → eol

    Assumptions:
    - Display dummy frames generate display_interest_signal via trials
    - Physical sell SKUs generate sell_through_signal via direct sales
    - Sunglasses are always physical_sell + walk_in
    - Contact lenses are always physical_sell + prescription
*/
{{ config(materialized='table') }}

select
    sku_id,
    product_name,
    brand,
    category,
    subcategory,
    sku_type,
    gender,
    frame_type,
    frame_shape,
    frame_material,
    frame_color,
    lens_type,
    size,
    cast(mrp as double)                  as mrp,
    cast(cost_price as double)           as cost_price,
    fulfillment_type,
    sales_channel,
    cast(is_display_only as boolean)     as is_display_only,
    lifecycle_stage,
    vendor_id,
    cast(lead_time_days as integer)      as lead_time_days,
    cast(launch_date as date)            as launch_date,

    -- Derived: margin
    round(cast(mrp as double) - cast(cost_price as double), 2) as unit_margin,
    round((cast(mrp as double) - cast(cost_price as double)) / nullif(cast(mrp as double), 0), 4) as margin_pct

from {{ source('raw', 'skus') }}
