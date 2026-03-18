/*
    Custom test: receipt_date must be >= po order_date.
    Validates that goods are not received before the PO was placed.
*/
{% test receipt_date_after_po_date(model) %}

select
    r.receipt_id,
    r.receipt_date,
    r.po_id,
    po.order_date as po_order_date
from {{ model }} r
inner join {{ ref('stg_purchase_orders') }} po
    on r.po_id = po.po_id
where r.receipt_date < po.order_date

{% endtest %}
