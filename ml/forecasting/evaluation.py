"""Forecast evaluation metrics and reporting.

Metrics:
- WMAPE: Weighted Mean Absolute Percentage Error
- MASE: Mean Absolute Scaled Error (uses seasonal naive as baseline)
- Bias: Systematic over/under forecasting
- Coverage: Prediction interval calibration

Breakdowns by store cluster, category, SKU type, and lifecycle stage.
"""

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def wmape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Weighted Mean Absolute Percentage Error.

    WMAPE = sum(|actual - forecast|) / sum(|actual|)
    More robust than MAPE for series with zeros.
    """
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    total = np.abs(y_true).sum()
    if total == 0:
        return np.nan
    return float(np.abs(y_true - y_pred).sum() / total)


def mase(y_true: np.ndarray, y_pred: np.ndarray, y_train: np.ndarray, season_length: int = 52) -> float:
    """Mean Absolute Scaled Error.

    Scaled by in-sample seasonal naive error.
    MASE < 1 means better than seasonal naive.
    """
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    y_train = np.asarray(y_train, dtype=float)

    # In-sample seasonal naive MAE
    if len(y_train) <= season_length:
        naive_mae = np.abs(np.diff(y_train)).mean()
    else:
        naive_errors = np.abs(y_train[season_length:] - y_train[:-season_length])
        naive_mae = naive_errors.mean()

    if naive_mae == 0:
        return np.nan

    forecast_mae = np.abs(y_true - y_pred).mean()
    return float(forecast_mae / naive_mae)


def bias(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Forecast bias — positive means over-forecasting.

    Bias = sum(forecast - actual) / sum(|actual|)
    """
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    total = np.abs(y_true).sum()
    if total == 0:
        return np.nan
    return float((y_pred - y_true).sum() / total)


def mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Mean Absolute Error."""
    return float(np.abs(np.asarray(y_true) - np.asarray(y_pred)).mean())


def coverage(y_true: np.ndarray, lower: np.ndarray, upper: np.ndarray) -> float:
    """Prediction interval coverage — fraction of actuals within bounds."""
    y_true = np.asarray(y_true)
    lower = np.asarray(lower)
    upper = np.asarray(upper)
    within = ((y_true >= lower) & (y_true <= upper)).mean()
    return float(within)


def evaluate_forecasts(
    cv_results: pd.DataFrame,
    model_col: str,
    y_col: str = "y",
) -> dict[str, float]:
    """Compute aggregate metrics for a single model from CV results."""
    y_true = cv_results[y_col].values
    y_pred = cv_results[model_col].values

    # Filter out NaN
    mask = ~(np.isnan(y_true) | np.isnan(y_pred))
    y_true = y_true[mask]
    y_pred = y_pred[mask]

    return {
        "wmape": wmape(y_true, y_pred),
        "mae": mae(y_true, y_pred),
        "bias": bias(y_true, y_pred),
        "n_observations": int(len(y_true)),
    }


def evaluate_per_series(
    cv_results: pd.DataFrame,
    model_col: str,
    y_col: str = "y",
) -> pd.DataFrame:
    """Compute metrics per series (unique_id)."""
    records = []
    for uid, group in cv_results.groupby("unique_id"):
        y_true = group[y_col].values
        y_pred = group[model_col].values

        mask = ~(np.isnan(y_true) | np.isnan(y_pred))
        yt, yp = y_true[mask], y_pred[mask]

        records.append({
            "unique_id": uid,
            "wmape": wmape(yt, yp),
            "bias": bias(yt, yp),
            "mae": mae(yt, yp),
            "n_obs": len(yt),
            "mean_demand": float(yt.mean()) if len(yt) > 0 else 0,
        })

    return pd.DataFrame(records)


def evaluate_by_dimension(
    cv_results: pd.DataFrame,
    model_col: str,
    dimension_df: pd.DataFrame,
    dimension_col: str,
    y_col: str = "y",
) -> pd.DataFrame:
    """Compute metrics broken down by a dimensional attribute.

    Args:
        cv_results: Cross-validation results with unique_id, y, model predictions
        model_col: Name of the model column to evaluate
        dimension_df: DataFrame mapping unique_id to dimension values
        dimension_col: Column name for the dimension to group by
    """
    merged = cv_results.merge(
        dimension_df[["unique_id", dimension_col]].drop_duplicates(),
        on="unique_id",
        how="left",
    )

    records = []
    for dim_val, group in merged.groupby(dimension_col):
        y_true = group[y_col].values
        y_pred = group[model_col].values

        mask = ~(np.isnan(y_true) | np.isnan(y_pred))
        yt, yp = y_true[mask], y_pred[mask]

        records.append({
            dimension_col: dim_val,
            "wmape": wmape(yt, yp),
            "bias": bias(yt, yp),
            "mae": mae(yt, yp),
            "n_series": group["unique_id"].nunique(),
            "n_obs": len(yt),
        })

    result = pd.DataFrame(records).sort_values("wmape")
    logger.info(f"Evaluation by {dimension_col}:\n{result.to_string(index=False)}")
    return result


def generate_evaluation_report(
    cv_results: pd.DataFrame,
    model_columns: list[str],
    dimension_df: pd.DataFrame | None = None,
) -> dict:
    """Generate comprehensive evaluation report.

    Returns dict with:
    - aggregate: per-model aggregate metrics
    - per_series: per-model per-series metrics
    - by_cluster: metrics by store_cluster (if dimension_df provided)
    - by_category: metrics by category (if dimension_df provided)
    - model_ranking: models ranked by WMAPE
    """
    report = {"aggregate": {}, "model_ranking": []}

    for model_col in model_columns:
        if model_col not in cv_results.columns:
            continue
        metrics = evaluate_forecasts(cv_results, model_col)
        report["aggregate"][model_col] = metrics

    # Rank models by WMAPE
    ranking = sorted(
        report["aggregate"].items(),
        key=lambda x: x[1].get("wmape", float("inf")),
    )
    report["model_ranking"] = [{"model": m, **v} for m, v in ranking]

    # Dimensional breakdowns
    if dimension_df is not None:
        best_model = ranking[0][0] if ranking else model_columns[0]
        for dim_col in ["store_cluster", "category", "sku_type", "lifecycle_stage"]:
            if dim_col in dimension_df.columns:
                report[f"by_{dim_col}"] = evaluate_by_dimension(
                    cv_results, best_model, dimension_df, dim_col
                ).to_dict(orient="records")

    logger.info(f"Evaluation report: {len(report['model_ranking'])} models ranked")
    return report
