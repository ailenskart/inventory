"""Baseline demand forecasting models using StatsForecast.

Model zoo:
- SeasonalNaive: Benchmark (last year same week)
- AutoETS: Exponential smoothing with automatic component selection
- AutoARIMA: ARIMA with automatic order selection
- CrostonOptimized: For intermittent demand (slow-moving SKUs)
- Ensemble: Simple average of top models

Forecasts at SKU × Store × Week granularity.
Supports both display demand (trials) and physical sell-through.
"""

import logging

import pandas as pd
from statsforecast import StatsForecast
from statsforecast.models import (
    AutoARIMA,
    AutoETS,
    CrostonOptimized,
    Naive,
    SeasonalNaive,
)

from ml.forecasting.config import ForecastConfig

logger = logging.getLogger(__name__)


def get_model_zoo(config: ForecastConfig) -> list:
    """Return the full set of baseline models."""
    return [
        Naive(),
        SeasonalNaive(season_length=config.season_length),
        AutoETS(season_length=config.season_length),
        AutoARIMA(season_length=config.season_length),
        CrostonOptimized(),
    ]


def get_production_models(config: ForecastConfig) -> list:
    """Return production models (excluding slow ones for speed)."""
    return [
        SeasonalNaive(season_length=config.season_length),
        AutoETS(season_length=config.season_length),
        CrostonOptimized(),
    ]


def fit_and_forecast(
    df: pd.DataFrame,
    config: ForecastConfig,
    models: list | None = None,
) -> pd.DataFrame:
    """Fit models and generate point forecasts.

    Args:
        df: StatsForecast-format DataFrame (unique_id, ds, y)
        config: Forecast configuration
        models: Optional model list override

    Returns:
        DataFrame with forecasts per model, indexed by unique_id and ds
    """
    if models is None:
        models = get_production_models(config)

    n_series = df["unique_id"].nunique()
    logger.info(f"Fitting {len(models)} models on {n_series} series, "
                f"horizon={config.horizon_weeks}w")

    sf = StatsForecast(
        models=models,
        freq=config.frequency,
        n_jobs=-1,
    )

    forecasts = sf.forecast(df=df, h=config.horizon_weeks)
    forecasts = forecasts.reset_index()

    logger.info(f"Generated {len(forecasts)} forecast rows")
    return forecasts


def fit_and_forecast_with_quantiles(
    df: pd.DataFrame,
    config: ForecastConfig,
    models: list | None = None,
) -> pd.DataFrame:
    """Fit models and generate quantile forecasts.

    Returns point forecast + prediction intervals at configured quantile levels.
    """
    if models is None:
        models = get_production_models(config)

    n_series = df["unique_id"].nunique()
    logger.info(f"Fitting {len(models)} models with quantiles {config.quantiles} "
                f"on {n_series} series")

    sf = StatsForecast(
        models=models,
        freq=config.frequency,
        n_jobs=-1,
    )

    forecasts = sf.forecast(
        df=df,
        h=config.horizon_weeks,
        level=[int(q * 100) for q in config.quantiles if q > 0.5],
    )
    forecasts = forecasts.reset_index()

    logger.info(f"Generated {len(forecasts)} quantile forecast rows")
    return forecasts


def cross_validate(
    df: pd.DataFrame,
    config: ForecastConfig,
    models: list | None = None,
) -> pd.DataFrame:
    """Run time-series cross-validation.

    Uses expanding window with config.cv_n_windows folds.
    """
    if models is None:
        models = get_production_models(config)

    sf = StatsForecast(
        models=models,
        freq=config.frequency,
        n_jobs=-1,
    )

    cv_results = sf.cross_validation(
        df=df,
        h=config.cv_h,
        step_size=config.cv_step_size,
        n_windows=config.cv_n_windows,
    )
    cv_results = cv_results.reset_index()

    logger.info(f"Cross-validation complete: {len(cv_results)} rows, "
                f"{config.cv_n_windows} windows")
    return cv_results


def select_best_model(
    cv_results: pd.DataFrame,
    model_columns: list[str] | None = None,
) -> pd.DataFrame:
    """Select best model per series based on cross-validation WMAPE.

    Returns DataFrame with unique_id → best_model mapping.
    """
    if model_columns is None:
        model_columns = [c for c in cv_results.columns
                         if c not in ("unique_id", "ds", "y", "cutoff", "lo-", "hi-")
                         and not c.startswith("lo-") and not c.startswith("hi-")]

    results = []
    for uid, group in cv_results.groupby("unique_id"):
        best_model = None
        best_wmape = float("inf")

        for model_col in model_columns:
            if model_col not in group.columns:
                continue
            abs_err = (group["y"] - group[model_col]).abs().sum()
            total = group["y"].abs().sum()
            wmape = abs_err / total if total > 0 else float("inf")

            if wmape < best_wmape:
                best_wmape = wmape
                best_model = model_col

        results.append({
            "unique_id": uid,
            "best_model": best_model or model_columns[0],
            "best_wmape": best_wmape,
        })

    selection = pd.DataFrame(results)
    logger.info(f"Model selection: {selection['best_model'].value_counts().to_dict()}")
    return selection


def create_ensemble_forecast(
    forecasts: pd.DataFrame,
    model_columns: list[str] | None = None,
) -> pd.DataFrame:
    """Create simple average ensemble of all model forecasts."""
    if model_columns is None:
        model_columns = [c for c in forecasts.columns
                         if c not in ("unique_id", "ds")
                         and not c.startswith("lo-") and not c.startswith("hi-")]

    forecasts = forecasts.copy()
    valid_cols = [c for c in model_columns if c in forecasts.columns]
    forecasts["Ensemble"] = forecasts[valid_cols].mean(axis=1)

    logger.info(f"Created ensemble from {len(valid_cols)} models")
    return forecasts
