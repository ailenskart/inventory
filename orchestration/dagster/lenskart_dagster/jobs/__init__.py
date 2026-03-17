"""Dagster job definitions."""

from dagster import define_asset_job

# Daily data foundation pipeline: generate → seed → transform → test
daily_data_foundation_job = define_asset_job(
    name="daily_data_foundation",
    description="Daily pipeline: ingest CSVs → dbt seed → staging → dims → intermediate → marts → tests",
    selection=[
        "synthetic_data",
        "load_seeds",
        "dbt_seed",
        "dbt_staging",
        "dbt_dimensions",
        "dbt_intermediate",
        "dbt_marts",
        "dbt_tests",
        "data_validation",
    ],
)

# Full pipeline including ML and optimization
daily_batch_job = define_asset_job(
    name="daily_batch_job",
    description="Full daily pipeline: data foundation + forecast + replenishment + transfers",
    selection=[
        "synthetic_data",
        "load_seeds",
        "dbt_seed",
        "dbt_staging",
        "dbt_dimensions",
        "dbt_intermediate",
        "dbt_marts",
        "dbt_tests",
        "data_validation",
        "demand_forecast_train",
        "demand_forecast",
        "feature_materialization",
        "replenishment_plan",
        "transfer_plan",
    ],
)

weekly_forecast_job = define_asset_job(
    name="weekly_forecast_job",
    description="Weekly pipeline: full forecast + assortment + PO suggestions",
    selection=[
        "dbt_staging",
        "dbt_dimensions",
        "dbt_intermediate",
        "dbt_marts",
        "demand_forecast_train",
        "demand_forecast",
        "feature_materialization",
        "store_clustering",
        "assortment_plan",
        "replenishment_plan",
        "transfer_plan",
        "purchase_order_suggestions",
    ],
)

# Training-only job (for model development / retraining)
forecast_training_job = define_asset_job(
    name="forecast_training_job",
    description="Train and evaluate demand forecast models",
    selection=[
        "demand_forecast_train",
        "demand_forecast",
        "feature_materialization",
    ],
)
