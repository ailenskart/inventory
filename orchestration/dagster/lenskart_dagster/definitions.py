"""Dagster definitions entry point."""

from dagster import Definitions, load_assets_from_modules

from orchestration.dagster.lenskart_dagster import assets
from orchestration.dagster.lenskart_dagster.jobs import (
    daily_batch_job,
    daily_data_foundation_job,
    forecast_training_job,
    weekly_forecast_job,
)
from orchestration.dagster.lenskart_dagster.schedules import daily_schedule, weekly_schedule

all_assets = load_assets_from_modules([assets])

defs = Definitions(
    assets=all_assets,
    jobs=[daily_data_foundation_job, daily_batch_job, weekly_forecast_job, forecast_training_job],
    schedules=[daily_schedule, weekly_schedule],
)
