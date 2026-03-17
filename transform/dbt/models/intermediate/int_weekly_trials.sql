-- Weekly aggregated try-on events (display demand signal)
{{ config(materialized='table') }}

select
    store_id,
    sku_id,
    date_trunc('week', trial_date) as week_start,
    count(*) as total_trials,
    sum(case when resulted_in_order then 1 else 0 end) as trials_with_order,
    round(
        sum(case when resulted_in_order then 1 else 0 end)::numeric / nullif(count(*), 0),
        4
    ) as trial_conversion_rate
from {{ ref('stg_store_trials') }}
group by store_id, sku_id, date_trunc('week', trial_date)
