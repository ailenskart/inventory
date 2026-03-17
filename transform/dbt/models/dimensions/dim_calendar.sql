/*
    dim_calendar — Date dimension with seasonality and festive flags.

    Used for time-series joins and seasonal pattern analysis.
    Covers the full 365-day synthetic data range.
*/
{{ config(materialized='table') }}

select
    cast(date_key as date)               as date_key,
    cast(year as integer)                as year,
    cast(quarter as integer)             as quarter,
    cast(month as integer)               as month,
    month_name,
    cast(week_of_year as integer)        as week_of_year,
    cast(day_of_week as integer)         as day_of_week,
    day_name,
    cast(is_weekend as boolean)          as is_weekend,
    cast(is_festive as boolean)          as is_festive,
    festive_event,
    season

from {{ source('raw', 'calendar') }}
