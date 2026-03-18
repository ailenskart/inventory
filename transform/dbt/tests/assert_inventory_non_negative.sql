/*
    Singular test: assert no negative on_hand_qty in inventory snapshots.
    Business rule: on_hand_qty should never be negative unless there's
    an explicit adjustment_reason (not modeled in synthetic data).
*/
select
    store_id,
    sku_id,
    snapshot_date,
    on_hand_qty
from {{ ref('stg_inventory_daily') }}
where on_hand_qty < 0
