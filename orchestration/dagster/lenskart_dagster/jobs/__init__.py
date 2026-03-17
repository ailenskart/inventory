"""Dagster job definitions for the Lenskart Retail Intelligence Platform.

Jobs define which assets run together as a logical unit of work.
"""

from dagster import define_asset_job

# ─── Data Foundation ─────────────────────────────────────────────────────────

daily_data_foundation_job = define_asset_job(
    name="daily_data_foundation",
    description="Data foundation pipeline: ingest CSVs → dbt seed → staging → dims → intermediate → marts → tests",
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

# ─── Full Daily Pipeline ─────────────────────────────────────────────────────

daily_batch_job = define_asset_job(
    name="daily_batch_job",
    description=(
        "Full daily pipeline: data foundation → forecast → lifecycle → "
        "replenishment → transfers → PO suggestions"
    ),
    selection=[
        # Data foundation
        "synthetic_data",
        "load_seeds",
        "dbt_seed",
        "dbt_staging",
        "dbt_dimensions",
        "dbt_intermediate",
        "dbt_marts",
        "dbt_tests",
        "data_validation",
        # ML
        "demand_forecast_train",
        "demand_forecast",
        "feature_materialization",
        # Intelligence
        "lifecycle_classification",
        # Optimization
        "replenishment_plan",
        "transfer_plan",
        # Vendor
        "purchase_order_suggestions",
    ],
)

# ─── Weekly Full Pipeline ─────────────────────────────────────────────────────

weekly_forecast_job = define_asset_job(
    name="weekly_forecast_job",
    description=(
        "Weekly pipeline: full forecast → lifecycle → assortment → "
        "replenishment → transfers → PO suggestions"
    ),
    selection=[
        # Transform (refresh marts)
        "dbt_staging",
        "dbt_dimensions",
        "dbt_intermediate",
        "dbt_marts",
        # ML
        "demand_forecast_train",
        "demand_forecast",
        "feature_materialization",
        "store_clustering",
        # Intelligence
        "lifecycle_classification",
        # Optimization
        "assortment_plan",
        "replenishment_plan",
        "transfer_plan",
        # Vendor
        "purchase_order_suggestions",
    ],
)

# ─── Training-only Job ────────────────────────────────────────────────────────

forecast_training_job = define_asset_job(
    name="forecast_training_job",
    description="Train and evaluate demand forecast models",
    selection=[
        "demand_forecast_train",
        "demand_forecast",
        "feature_materialization",
    ],
)
