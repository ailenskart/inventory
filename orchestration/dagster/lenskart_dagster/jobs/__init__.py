"""Dagster job definitions."""

from dagster import define_asset_job

daily_batch_job = define_asset_job(
    name="daily_batch_job",
    description="Daily pipeline: ingest -> transform -> forecast -> optimize",
    selection=[
        "raw_daily_sales",
        "raw_daily_inventory",
        "raw_store_trials",
        "dbt_transform",
        "demand_forecast",
        "replenishment_plan",
        "transfer_plan",
    ],
)

weekly_forecast_job = define_asset_job(
    name="weekly_forecast_job",
    description="Weekly pipeline: full forecast + assortment + PO suggestions",
    selection=[
        "dbt_transform",
        "demand_forecast",
        "store_clustering",
        "assortment_plan",
        "replenishment_plan",
        "transfer_plan",
        "purchase_order_suggestions",
    ],
)
