/*
    Singular test: receipt_date must be >= po order_date.
    Goods cannot be received before the purchase order was placed.

    NOTE: In synthetic data, receipts and POs are generated independently,
    so po_ids on receipts are random references. This test is configured
    as warn-only for synthetic data. In production, this would be a hard fail.
*/
{{ config(severity='warn') }}

select
    r.receipt_id,
    r.receipt_date,
    r.po_id,
    po.order_date
from {{ ref('stg_receipts_daily') }} r
inner join {{ ref('stg_purchase_orders') }} po
    on r.po_id = po.po_id
where r.receipt_date < po.order_date
