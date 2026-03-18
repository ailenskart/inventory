"""MLflow experiment tracking for demand forecasting.

Logs:
- Model parameters and hyperparameters
- Evaluation metrics (WMAPE, MASE, bias) per model
- Dimensional breakdowns (by cluster, category)
- Forecast artifacts (CSV, plots)
- Model registry for production deployment
"""

import json
import logging
import os
import tempfile

import pandas as pd

from ml.forecasting.config import ForecastConfig

logger = logging.getLogger(__name__)


def _get_mlflow():
    """Lazy import mlflow to avoid hard dependency."""
    import mlflow
    return mlflow


def init_tracking(config: ForecastConfig) -> str:
    """Initialize MLflow tracking and return experiment ID."""
    mlflow = _get_mlflow()
    mlflow.set_tracking_uri(config.mlflow_tracking_uri)
    experiment = mlflow.set_experiment(config.mlflow_experiment_name)
    logger.info(f"MLflow experiment: {experiment.name} (ID: {experiment.experiment_id})")
    return experiment.experiment_id


def start_run(config: ForecastConfig, run_name: str | None = None):
    """Start an MLflow run and log config parameters."""
    mlflow = _get_mlflow()
    run = mlflow.start_run(run_name=run_name)

    # Log config as parameters
    mlflow.log_params({
        "horizon_weeks": config.horizon_weeks,
        "min_history_weeks": config.min_history_weeks,
        "season_length": config.season_length,
        "target_column": config.target_column,
        "reconciliation_method": config.reconciliation_method,
        "censor_stockout_demand": config.censor_stockout_demand,
        "stockout_imputation_method": config.stockout_imputation_method,
        "cv_n_windows": config.cv_n_windows,
        "cv_step_size": config.cv_step_size,
    })

    return run


def log_metrics(metrics: dict[str, float], prefix: str = ""):
    """Log metrics to active MLflow run."""
    mlflow = _get_mlflow()
    for key, value in metrics.items():
        if value is not None and not (isinstance(value, float) and pd.isna(value)):
            metric_name = f"{prefix}_{key}" if prefix else key
            mlflow.log_metric(metric_name, value)


def log_evaluation_report(report: dict):
    """Log full evaluation report to MLflow."""
    mlflow = _get_mlflow()

    # Log aggregate metrics per model
    for model_name, metrics in report.get("aggregate", {}).items():
        log_metrics(metrics, prefix=model_name)

    # Log best model info
    ranking = report.get("model_ranking", [])
    if ranking:
        mlflow.log_param("best_model", ranking[0]["model"])
        mlflow.log_metric("best_wmape", ranking[0].get("wmape", -1))

    # Log report as artifact
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(report, f, indent=2, default=str)
        f.flush()
        mlflow.log_artifact(f.name, "evaluation")
        os.unlink(f.name)


def log_forecasts_artifact(forecasts: pd.DataFrame, name: str = "forecasts"):
    """Log forecast DataFrame as CSV artifact."""
    mlflow = _get_mlflow()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        forecasts.to_csv(f.name, index=False)
        mlflow.log_artifact(f.name, name)
        os.unlink(f.name)


def log_model_selection(selection: pd.DataFrame):
    """Log per-series model selection results."""
    mlflow = _get_mlflow()

    # Log selection distribution
    dist = selection["best_model"].value_counts().to_dict()
    for model, count in dist.items():
        mlflow.log_metric(f"selection_{model}_count", count)

    log_forecasts_artifact(selection, "model_selection")


def end_run():
    """End current MLflow run."""
    mlflow = _get_mlflow()
    mlflow.end_run()


def register_model(model_name: str = "demand_forecast_v1"):
    """Register the current run's model in MLflow registry."""
    mlflow = _get_mlflow()
    run = mlflow.active_run()
    if run:
        model_uri = f"runs:/{run.info.run_id}/model"
        mlflow.register_model(model_uri, model_name)
        logger.info(f"Registered model: {model_name}")
