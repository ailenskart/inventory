"""Survival-analysis-inspired lifecycle scoring (v2).

Provides a continuous lifecycle score as an alternative to the discrete
rule-based classifier. Uses Weibull-inspired hazard modelling to compute
a "lifecycle health" score that decays over time and is modulated by
observed signals (sales velocity, trials, conversions, aging).
"""

import logging
import math

import pandas as pd

from services.lifecycle.config import LifecycleConfig

logger = logging.getLogger(__name__)


def compute_survival_scores(
    features_df: pd.DataFrame,
    config: LifecycleConfig,
) -> pd.DataFrame:
    """Compute survival-analysis-inspired lifecycle scores.

    For each SKU, produces:
    - survival_score: 0-1 continuous score (1 = healthy, 0 = end of life)
    - hazard_rate: instantaneous risk of lifecycle decline
    - expected_remaining_weeks: estimated weeks of productive life

    Args:
        features_df: DataFrame from compute_lifecycle_features().
        config: Lifecycle configuration.

    Returns:
        Input DataFrame with additional scoring columns.
    """
    if features_df.empty:
        return features_df

    df = features_df.copy()
    shape = config.survival_shape
    scale = config.survival_scale
    weights = config.survival_weights

    # ── Base Weibull survival function ──────────────────────────────────
    # S(t) = exp(-(t/scale)^shape)
    df["base_survival"] = df["age_days"].apply(
        lambda t: _weibull_survival(t, shape, scale)
    )

    # ── Signal modifiers ────────────────────────────────────────────────
    # Each factor adjusts the base survival up or down

    # Velocity factor: positive trend extends life, negative shortens
    df["velocity_factor"] = df["sales_velocity_trend"].clip(-1, 1).apply(
        lambda v: 0.5 + 0.5 * v  # Maps [-1, 1] -> [0, 1]
    )

    # Trial factor
    df["trial_factor"] = df["trial_trend"].clip(-1, 1).apply(
        lambda v: 0.5 + 0.5 * v
    )

    # Conversion factor
    df["conversion_factor"] = df["conversion_trend"].clip(-1, 1).apply(
        lambda v: 0.5 + 0.5 * v
    )

    # Age factor: inverse of normalized age
    df["age_factor"] = 1.0 - df["base_survival"].apply(lambda s: 1.0 - s)

    # Aging inventory factor: high aging = lower score
    df["aging_factor"] = 1.0 - df["aging_inventory_pct"]

    # Markdown factor: more markdowns = lower score
    max_md = df["markdown_count"].max() if df["markdown_count"].max() > 0 else 1
    df["markdown_factor"] = 1.0 - (df["markdown_count"] / max_md)

    # ── Composite survival score ────────────────────────────────────────
    df["survival_score"] = (
        weights["age_factor"] * df["age_factor"]
        + weights["velocity_factor"] * df["velocity_factor"]
        + weights["trial_factor"] * df["trial_factor"]
        + weights["conversion_factor"] * df["conversion_factor"]
        + weights["aging_factor"] * df["aging_factor"]
        + weights["markdown_factor"] * df["markdown_factor"]
    ).clip(0.0, 1.0).round(4)

    # ── Hazard rate ─────────────────────────────────────────────────────
    # h(t) = (shape/scale) * (t/scale)^(shape-1)
    df["hazard_rate"] = df["age_days"].apply(
        lambda t: _weibull_hazard(t, shape, scale)
    ).round(6)

    # ── Expected remaining weeks ────────────────────────────────────────
    # Estimate based on current survival score and hazard rate
    df["expected_remaining_weeks"] = df.apply(
        lambda row: _estimate_remaining_weeks(
            row["survival_score"], row["hazard_rate"]
        ),
        axis=1,
    ).round(1)

    # Clean up intermediate columns
    intermediate = ["base_survival", "velocity_factor", "trial_factor",
                    "conversion_factor", "age_factor", "aging_factor",
                    "markdown_factor"]
    df = df.drop(columns=intermediate)

    logger.info(
        f"Computed survival scores for {len(df)} SKUs. "
        f"Mean score: {df['survival_score'].mean():.3f}, "
        f"Mean remaining weeks: {df['expected_remaining_weeks'].mean():.1f}"
    )

    return df


def _weibull_survival(t: float, shape: float, scale: float) -> float:
    """Weibull survival function: S(t) = exp(-(t/scale)^shape)."""
    if t <= 0:
        return 1.0
    return math.exp(-((t / scale) ** shape))


def _weibull_hazard(t: float, shape: float, scale: float) -> float:
    """Weibull hazard function: h(t) = (shape/scale) * (t/scale)^(shape-1)."""
    if t <= 0:
        return 0.0
    return (shape / scale) * ((t / scale) ** (shape - 1))


def _estimate_remaining_weeks(
    survival_score: float,
    hazard_rate: float,
) -> float:
    """Estimate remaining productive weeks.

    Uses a simple inverse-hazard approach modulated by current health.
    """
    if hazard_rate <= 0 or survival_score <= 0:
        return 0.0
    # Remaining life proportional to (survival / hazard), converted to weeks
    remaining_days = survival_score / max(hazard_rate, 0.001)
    return remaining_days / 7.0
