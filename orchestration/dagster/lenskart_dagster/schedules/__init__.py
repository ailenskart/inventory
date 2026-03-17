"""Dagster schedule definitions."""

from dagster import ScheduleDefinition

from orchestration.dagster.lenskart_dagster.jobs import daily_batch_job, weekly_forecast_job

daily_schedule = ScheduleDefinition(
    job=daily_batch_job,
    cron_schedule="0 6 * * *",  # 6 AM daily
    name="daily_6am",
)

weekly_schedule = ScheduleDefinition(
    job=weekly_forecast_job,
    cron_schedule="0 4 * * 1",  # 4 AM every Monday
    name="weekly_monday_4am",
)
