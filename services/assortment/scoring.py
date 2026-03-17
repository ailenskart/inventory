"""SKU scoring for assortment optimization.

Computes composite scores per SKU × Store using:
- Expected demand / conversion
- Trial propensity (display interest signal)
- Gross margin contribution
- Freshness value (lifecycle stage)
- Strategic new-launch exposure
- Category balance bonus

Scores are used as objective coefficients in the CP-SAT model.
"""

import logging

import numpy as np
import pandas as pd

from services.assortment.config import AssortmentConfig, AssortmentScenario

logger = logging.getLogger(__name__)


def compute_sku_scores(
    sku_data: pd.DataFrame,
    scenario: AssortmentScenario,
    config: AssortmentConfig,
) -> pd.DataFrame:
    """Compute composite optimization scores for each SKU.

    Args:
        sku_data: DataFrame with columns:
            sku_id, store_id, avg_weekly_demand, display_interest,
            trial_conversion_rate, margin_pct, mrp, lifecycle_stage,
            category, subcategory, brand, sku_type, fulfillment_type,
            is_display_only, weeks_on_display
        scenario: Scenario profile with objective weights
        config: Global config

    Returns:
        DataFrame with sku_id, store_id, and all component + composite scores
    """
    df = sku_data.copy()

    # ─── Component scores (all normalized to 0-1) ───────────────────────

    # 1. Demand score: normalized expected weekly demand
    df["demand_score"] = _normalize_column(df, "avg_weekly_demand")

    # 2. Trial propensity: display interest signal
    df["trial_score"] = _normalize_column(df, "display_interest")

    # 3. Margin score: margin percentage
    df["margin_score"] = _normalize_column(df, "margin_pct")

    # 4. Freshness score: from lifecycle stage
    #    Uses lifecycle intelligence freshness mapping when available,
    #    falls back to config.freshness_scores for backward compatibility
    from services.lifecycle.config import LIFECYCLE_FRESHNESS_SCORES
    merged_freshness = {**config.freshness_scores, **LIFECYCLE_FRESHNESS_SCORES}
    df["freshness_score"] = df["lifecycle_stage"].map(
        merged_freshness
    ).fillna(0.3)

    # 5. New-launch score: binary (1 if new, 0 otherwise)
    df["new_launch_score"] = (
        df["lifecycle_stage"] == scenario.new_launch_lifecycle
    ).astype(float)

    # 6. Category balance score: inverse of category share
    # Rewards rare categories to promote diversity
    cat_counts = df["category"].value_counts(normalize=True)
    df["category_balance_score"] = df["category"].map(
        lambda c: 1.0 - cat_counts.get(c, 0.5)
    )

    # ─── Penalty scores (negative contributions) ────────────────────────

    # Stale penalty: aging / eol / decline / exit products
    df["stale_penalty"] = df["lifecycle_stage"].map({
        "aging": 0.5, "eol": 1.0,
        "decline": 0.4, "exit": 1.0,
    }).fillna(0.0)

    # Poor fit penalty: sell-through SKU with zero demand → doesn't belong
    df["poor_fit_penalty"] = np.where(
        (df["avg_weekly_demand"] <= 0) & (df["is_display_only"] == 0),
        1.0, 0.0,
    )

    # Duplication penalty placeholder (would need subcategory similarity)
    df["duplication_penalty"] = 0.0

    # ─── Composite score ────────────────────────────────────────────────

    df["composite_score"] = (
        scenario.w_demand * df["demand_score"]
        + scenario.w_trial * df["trial_score"]
        + scenario.w_margin * df["margin_score"]
        + scenario.w_freshness * df["freshness_score"]
        + scenario.w_new_launch * df["new_launch_score"]
        + scenario.w_category_balance * df["category_balance_score"]
        - scenario.p_stale * df["stale_penalty"]
        - scenario.p_poor_fit * df["poor_fit_penalty"]
        - scenario.p_duplication * df["duplication_penalty"]
    ).clip(lower=0.0)

    # Scale to integer for CP-SAT (which needs int coefficients)
    df["score_int"] = (df["composite_score"] * config.score_scale).astype(int)

    logger.info(
        f"Scored {len(df)} SKUs: "
        f"mean={df['composite_score'].mean():.3f}, "
        f"max={df['composite_score'].max():.3f}"
    )

    return df


def _normalize_column(df: pd.DataFrame, col: str) -> pd.Series:
    """Min-max normalize a column to 0-1."""
    if col not in df.columns:
        return pd.Series(0.0, index=df.index)
    series = df[col].fillna(0).astype(float)
    vmin, vmax = series.min(), series.max()
    if vmax - vmin == 0:
        return pd.Series(0.5, index=df.index)
    return (series - vmin) / (vmax - vmin)


def get_price_tier(mrp: float, config: AssortmentConfig) -> str:
    """Map MRP to price tier."""
    for tier, (lo, hi) in config.price_tiers.items():
        if lo <= mrp < hi:
            return tier
    return "mid"
