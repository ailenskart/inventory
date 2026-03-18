/*
    Custom test: for completed transfers, the 'out' qty must equal the 'in' qty.
    transfer_out must balance transfer_in by transfer_id.
*/
{% test transfer_out_balances_in(model) %}

with transfer_balance as (
    select
        transfer_id,
        sum(case when transfer_direction = 'out' then transfer_qty else 0 end) as out_qty,
        sum(case when transfer_direction = 'in' then transfer_qty else 0 end) as in_qty
    from {{ model }}
    where status = 'received'
    group by transfer_id
)

select
    transfer_id,
    out_qty,
    in_qty
from transfer_balance
where out_qty != in_qty

{% endtest %}
