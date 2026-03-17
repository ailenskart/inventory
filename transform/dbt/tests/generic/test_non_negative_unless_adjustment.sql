/*
    Custom test: on_hand_qty must be non-negative.
    In a production system, negative on-hand would require an adjustment_reason.
    For synthetic data, we simply assert >= 0.
*/
{% test non_negative_inventory(model, column_name) %}

select
    {{ column_name }}
from {{ model }}
where {{ column_name }} < 0

{% endtest %}
