"""Rule-based lifecycle classifier (v1).

Classifies each SKU into one of six lifecycle stages based on feature
thresholds, then maps the stage to a recommended action.
"""

import logging

import pandas as pd

from schemas.lifecycle import (
    LifecycleClassification,
    LifecycleFeatures,
    LifecycleStage,
    RecommendedAction,
)
from services.lifecycle.config import (
    STAGE_DEFAULT_ACTIONS,
    LifecycleConfig,
)

logger = logging.getLogger(__name__)


def classify_skus(
    features_df: pd.DataFrame,
    config: LifecycleConfig,
) -> list[LifecycleClassification]:
    """Classify all SKUs using rule-based v1 classifier.

    Args:
        features_df: DataFrame from compute_lifecycle_features().
        config: Lifecycle configuration with thresholds.

    Returns:
        List of LifecycleClassification objects.
    """
    results = []
    for _, row in features_df.iterrows():
        classification = classify_single_sku(row.to_dict(), config)
        results.append(classification)

    stage_counts = {}
    for r in results:
        stage_counts[r.lifecycle_stage.value] = stage_counts.get(r.lifecycle_stage.value, 0) + 1
    logger.info(f"Classified {len(results)} SKUs: {stage_counts}")

    return results


def classify_single_sku(
    features: dict,
    config: LifecycleConfig,
) -> LifecycleClassification:
    """Classify a single SKU into a lifecycle stage.

    The rules are applied in priority order:
    1. EXIT - very low performance, high aging
    2. LAUNCH - young SKU with limited data
    3. GROWTH - positive trends, expanding
    4. DECLINE - negative trends, contracting
    5. CORE - stable high performer
    6. MATURITY - stable but not peak (fallback)
    """
    feat = LifecycleFeatures(**features)

    stage, confidence, reason = _apply_rules(feat, config)
    action = _determine_action(stage, feat, config)

    return LifecycleClassification(
        sku_id=feat.sku_id,
        lifecycle_stage=stage,
        confidence=confidence,
        recommended_action=action,
        reason=reason,
        features=feat,
        classifier_version="v1_rules",
    )


def _apply_rules(
    feat: LifecycleFeatures,
    config: LifecycleConfig,
) -> tuple[LifecycleStage, float, str]:
    """Apply classification rules in priority order.

    Returns:
        (stage, confidence, reason)
    """
    confidence = config.base_confidence

    # Adjust confidence based on data availability
    if feat.weeks_of_history < config.full_confidence_weeks:
        data_factor = feat.weeks_of_history / config.full_confidence_weeks
        confidence -= config.low_data_penalty * (1 - data_factor)

    # ── EXIT: very low performance, high aging ──────────────────────────
    if (
        feat.age_days >= config.exit_min_age_days
        and feat.current_vs_peak_ratio <= config.exit_max_current_vs_peak
        and feat.aging_inventory_pct >= config.exit_min_aging_pct
    ):
        signals = sum([
            feat.sales_velocity_trend < 0,
            feat.trial_trend < 0,
            feat.current_vs_peak_ratio < 0.1,
        ])
        conf = min(1.0, confidence + config.agreement_bonus * (signals / 3))
        return (
            LifecycleStage.EXIT,
            round(conf, 2),
            f"Low performance ({feat.current_vs_peak_ratio:.0%} of peak), "
            f"high aging inventory ({feat.aging_inventory_pct:.0%}), "
            f"age {feat.age_days}d",
        )

    # ── LAUNCH: young SKU ───────────────────────────────────────────────
    if (
        feat.age_days <= config.launch_max_age_days
        and feat.weeks_of_history <= config.launch_max_history_weeks
    ):
        conf = min(1.0, confidence + config.agreement_bonus)
        return (
            LifecycleStage.LAUNCH,
            round(conf, 2),
            f"Recently launched ({feat.age_days}d ago), "
            f"{feat.weeks_of_history} weeks of data",
        )

    # ── GROWTH: positive trends ─────────────────────────────────────────
    if (
        feat.sales_velocity_trend >= config.growth_min_velocity_trend
        and feat.trial_trend >= config.growth_min_trial_trend
        and feat.age_days <= config.growth_max_age_days
    ):
        signals = sum([
            feat.sales_velocity_trend > 0.1,
            feat.trial_trend > 0.05,
            feat.conversion_trend > 0,
            feat.current_vs_peak_ratio > 0.8,
        ])
        conf = min(1.0, confidence + config.agreement_bonus * (signals / 4))
        return (
            LifecycleStage.GROWTH,
            round(conf, 2),
            f"Growing velocity trend ({feat.sales_velocity_trend:+.2f}), "
            f"trial trend ({feat.trial_trend:+.2f}), "
            f"age {feat.age_days}d",
        )

    # ── DECLINE: negative trends ────────────────────────────────────────
    if (
        feat.sales_velocity_trend <= config.decline_max_velocity_trend
        and feat.current_vs_peak_ratio <= config.decline_max_current_vs_peak
        and feat.age_days >= config.decline_min_age_days
    ):
        signals = sum([
            feat.sales_velocity_trend < -0.1,
            feat.trial_trend < 0,
            feat.conversion_trend < 0,
            feat.aging_inventory_pct > 0.3,
        ])
        conf = min(1.0, confidence + config.agreement_bonus * (signals / 4))
        return (
            LifecycleStage.DECLINE,
            round(conf, 2),
            f"Declining velocity ({feat.sales_velocity_trend:+.2f}), "
            f"at {feat.current_vs_peak_ratio:.0%} of peak, "
            f"age {feat.age_days}d",
        )

    # ── CORE: stable high performer ─────────────────────────────────────
    if (
        feat.current_vs_peak_ratio >= config.core_min_current_vs_peak
        and feat.avg_weekly_sales >= config.core_min_avg_weekly_sales
        and feat.aging_inventory_pct <= config.core_max_aging_pct
    ):
        signals = sum([
            abs(feat.sales_velocity_trend) < 0.05,
            feat.conversion_trend >= 0,
            feat.aging_inventory_pct < 0.1,
        ])
        conf = min(1.0, confidence + config.agreement_bonus * (signals / 3))
        return (
            LifecycleStage.CORE,
            round(conf, 2),
            f"Stable performer at {feat.current_vs_peak_ratio:.0%} of peak, "
            f"avg {feat.avg_weekly_sales:.1f} units/wk",
        )

    # ── MATURITY: fallback for stable but not peak ──────────────────────
    return (
        LifecycleStage.MATURITY,
        round(confidence, 2),
        f"Mature product at {feat.current_vs_peak_ratio:.0%} of peak, "
        f"velocity trend {feat.sales_velocity_trend:+.2f}, "
        f"age {feat.age_days}d",
    )


def _determine_action(
    stage: LifecycleStage,
    feat: LifecycleFeatures,
    config: LifecycleConfig,
) -> RecommendedAction:
    """Determine recommended action based on stage and features.

    Overrides the default stage-to-action mapping when specific
    conditions warrant a different action.
    """
    # Start with default action for this stage
    default_action = STAGE_DEFAULT_ACTIONS[stage.value]

    # Override: high aging inventory in decline -> markdown
    if (
        stage == LifecycleStage.DECLINE
        and feat.aging_inventory_pct >= config.markdown_aging_threshold
    ):
        return RecommendedAction.MARKDOWN

    # Override: moderate aging in decline -> transfer
    if (
        stage == LifecycleStage.DECLINE
        and feat.aging_inventory_pct >= config.transfer_aging_threshold
    ):
        return RecommendedAction.TRANSFER

    # Override: maturity with high aging -> reduce depth
    if (
        stage == LifecycleStage.MATURITY
        and feat.aging_inventory_pct >= config.transfer_aging_threshold
    ):
        return RecommendedAction.REDUCE_DEPTH

    # Override: exit with very low sales -> discontinue
    if stage == LifecycleStage.EXIT:
        return RecommendedAction.DISCONTINUE

    return RecommendedAction(default_action)
