/*
    stg_store_traffic_daily — Daily footfall per store.

    Traffic data contextualizes sales: conversion_rate = sales / footfall.

    Grain: store_id × traffic_date
*/
{{ config(materialized='view') }}

select
    store_id,
    cast(traffic_date as date)          as traffic_date,
    cast(footfall_count as integer)     as footfall_count,
    cast(walk_ins as integer)           as walk_ins,
    cast(appointments as integer)       as appointments

from {{ source('raw', 'store_traffic') }}
where cast(footfall_count as integer) > 0
