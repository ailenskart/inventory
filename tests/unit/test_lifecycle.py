"""Unit tests for Product Lifecycle Intelligence.

Covers: config, features, classifier, scoring, pipeline helpers, schemas.
"""

import math
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from schemas.lifecycle import (
    LifecycleClassification,
    LifecycleFeatures,
    LifecycleStage,
    LifecycleSummary,
    RecommendedAction,
)
from services.lifecycle.classifier import (
    _apply_rules,
    _determine_action,
    classify_single_sku,
    classify_skus,
)
from services.lifecycle.config import (
    LIFECYCLE_FRESHNESS_SCORES,
    STAGE_DEFAULT_ACTIONS,
    LifecycleConfig,
)
from services.lifecycle.features import (
    _compute_trend,
    _empty_features,
    compute_lifecycle_features,
)
from services.lifecycle.pipeline import build_summary
from services.lifecycle.scoring import (
    _estimate_remaining_weeks,
    _weibull_hazard,
    _weibull_survival,
    compute_survival_scores,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def config():
    return LifecycleConfig()


@pytest.fixture
def sample_features():
    """Sample lifecycle features DataFrame."""
    return pd.DataFrame([
        {
            "sku_id": "SKU_LAUNCH",
            "age_days": 30,
            "sales_velocity_trend": 0.15,
            "trial_trend": 0.10,
            "conversion_trend": 0.05,
            "aging_inventory_pct": 0.0,
            "markdown_count": 0,
            "avg_weekly_sales": 2.0,
            "weeks_of_history": 4,
            "peak_weekly_sales": 3.0,
            "current_vs_peak_ratio": 0.9,
        },
        {
            "sku_id": "SKU_GROWTH",
            "age_days": 120,
            "sales_velocity_trend": 0.12,
            "trial_trend": 0.08,
            "conversion_trend": 0.03,
            "aging_inventory_pct": 0.05,
            "markdown_count": 0,
            "avg_weekly_sales": 5.0,
            "weeks_of_history": 16,
            "peak_weekly_sales": 6.0,
            "current_vs_peak_ratio": 0.85,
        },
        {
            "sku_id": "SKU_CORE",
            "age_days": 300,
            "sales_velocity_trend": 0.01,
            "trial_trend": 0.0,
            "conversion_trend": 0.0,
            "aging_inventory_pct": 0.1,
            "markdown_count": 0,
            "avg_weekly_sales": 8.0,
            "weeks_of_history": 40,
            "peak_weekly_sales": 10.0,
            "current_vs_peak_ratio": 0.8,
        },
        {
            "sku_id": "SKU_MATURITY",
            "age_days": 400,
            "sales_velocity_trend": -0.02,
            "trial_trend": -0.01,
            "conversion_trend": -0.01,
            "aging_inventory_pct": 0.2,
            "markdown_count": 1,
            "avg_weekly_sales": 4.0,
            "weeks_of_history": 50,
            "peak_weekly_sales": 10.0,
            "current_vs_peak_ratio": 0.45,
        },
        {
            "sku_id": "SKU_DECLINE",
            "age_days": 350,
            "sales_velocity_trend": -0.15,
            "trial_trend": -0.08,
            "conversion_trend": -0.05,
            "aging_inventory_pct": 0.35,
            "markdown_count": 2,
            "avg_weekly_sales": 2.0,
            "weeks_of_history": 45,
            "peak_weekly_sales": 10.0,
            "current_vs_peak_ratio": 0.3,
        },
        {
            "sku_id": "SKU_EXIT",
            "age_days": 500,
            "sales_velocity_trend": -0.25,
            "trial_trend": -0.15,
            "conversion_trend": -0.10,
            "aging_inventory_pct": 0.7,
            "markdown_count": 3,
            "avg_weekly_sales": 0.5,
            "weeks_of_history": 60,
            "peak_weekly_sales": 8.0,
            "current_vs_peak_ratio": 0.1,
        },
    ])


@pytest.fixture
def sample_sales():
    """Sample daily sales data for feature computation."""
    np.random.seed(42)
    dates = pd.date_range("2025-01-01", periods=180, freq="D")
    records = []
    for d in dates:
        qty = max(0, int(np.random.normal(3, 1)))
        records.append({"sku_id": "SKU_001", "sale_date": d, "qty_sold": qty})
    return pd.DataFrame(records)


@pytest.fixture
def sample_trials():
    """Sample trial data."""
    np.random.seed(42)
    dates = pd.date_range("2025-01-01", periods=90, freq="D")
    records = []
    for d in dates:
        records.append({
            "sku_id": "SKU_001",
            "trial_date": d,
            "resulted_in_order": int(np.random.random() < 0.3),
        })
    return pd.DataFrame(records)


# ─── Schema Tests ────────────────────────────────────────────────────────────


class TestLifecycleSchemas:
    def test_lifecycle_stage_values(self):
        stages = [s.value for s in LifecycleStage]
        assert stages == ["launch", "growth", "core", "maturity", "decline", "exit"]

    def test_recommended_action_values(self):
        actions = [a.value for a in RecommendedAction]
        expected = [
            "expand_distribution", "protect_placement", "reduce_depth",
            "transfer", "markdown", "discontinue",
        ]
        assert actions == expected

    def test_lifecycle_features_validation(self):
        feat = LifecycleFeatures(
            sku_id="SKU_001",
            age_days=100,
            sales_velocity_trend=0.05,
            trial_trend=0.02,
            conversion_trend=0.01,
            aging_inventory_pct=0.1,
            markdown_count=0,
            avg_weekly_sales=5.0,
            weeks_of_history=12,
            peak_weekly_sales=8.0,
            current_vs_peak_ratio=0.6,
        )
        assert feat.sku_id == "SKU_001"
        assert feat.age_days == 100

    def test_lifecycle_features_age_nonnegative(self):
        with pytest.raises(Exception):
            LifecycleFeatures(
                sku_id="X", age_days=-1, sales_velocity_trend=0,
                trial_trend=0, conversion_trend=0, aging_inventory_pct=0,
                markdown_count=0, avg_weekly_sales=0, weeks_of_history=0,
                peak_weekly_sales=0, current_vs_peak_ratio=0,
            )

    def test_lifecycle_classification_model(self):
        feat = LifecycleFeatures(
            sku_id="SKU_001", age_days=50, sales_velocity_trend=0.1,
            trial_trend=0.05, conversion_trend=0.02, aging_inventory_pct=0.0,
            markdown_count=0, avg_weekly_sales=3.0, weeks_of_history=6,
            peak_weekly_sales=4.0, current_vs_peak_ratio=0.9,
        )
        cls = LifecycleClassification(
            sku_id="SKU_001",
            lifecycle_stage=LifecycleStage.LAUNCH,
            confidence=0.85,
            recommended_action=RecommendedAction.EXPAND_DISTRIBUTION,
            reason="New product",
            features=feat,
        )
        assert cls.lifecycle_stage == LifecycleStage.LAUNCH
        assert cls.confidence == 0.85

    def test_lifecycle_summary(self):
        summary = LifecycleSummary(
            total_skus=100,
            stage_counts={"launch": 10, "core": 50, "decline": 40},
            action_counts={"expand_distribution": 10, "protect_placement": 50},
            avg_confidence=0.75,
        )
        assert summary.total_skus == 100


# ─── Config Tests ────────────────────────────────────────────────────────────


class TestLifecycleConfig:
    def test_default_config(self, config):
        assert config.trend_window_weeks == 8
        assert config.min_history_weeks == 4
        assert config.aging_threshold_days == 90

    def test_launch_thresholds(self, config):
        assert config.launch_max_age_days == 60
        assert config.launch_max_history_weeks == 8

    def test_exit_thresholds(self, config):
        assert config.exit_min_age_days == 180
        assert config.exit_min_aging_pct == 0.5

    def test_survival_weights_sum_to_one(self, config):
        total = sum(config.survival_weights.values())
        assert abs(total - 1.0) < 0.01

    def test_stage_default_actions(self):
        assert STAGE_DEFAULT_ACTIONS["launch"] == "expand_distribution"
        assert STAGE_DEFAULT_ACTIONS["core"] == "protect_placement"
        assert STAGE_DEFAULT_ACTIONS["exit"] == "discontinue"
        assert len(STAGE_DEFAULT_ACTIONS) == 6

    def test_freshness_scores_all_stages(self):
        assert len(LIFECYCLE_FRESHNESS_SCORES) == 6
        assert LIFECYCLE_FRESHNESS_SCORES["launch"] == 1.0
        assert LIFECYCLE_FRESHNESS_SCORES["exit"] == 0.0

    def test_freshness_scores_monotonically_decreasing(self):
        stages = ["launch", "growth", "core", "maturity", "decline", "exit"]
        scores = [LIFECYCLE_FRESHNESS_SCORES[s] for s in stages]
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1], f"{stages[i]} < {stages[i+1]}"

    def test_custom_db_path(self):
        c = LifecycleConfig(db_path="/tmp/test.duckdb")
        assert c.db_path == "/tmp/test.duckdb"


# ─── Feature Engineering Tests ───────────────────────────────────────────────


class TestTrendComputation:
    def test_increasing_trend_positive(self):
        values = np.array([1, 2, 3, 4, 5], dtype=float)
        trend = _compute_trend(values, 5)
        assert trend > 0

    def test_decreasing_trend_negative(self):
        values = np.array([5, 4, 3, 2, 1], dtype=float)
        trend = _compute_trend(values, 5)
        assert trend < 0

    def test_flat_trend_zero(self):
        values = np.array([3, 3, 3, 3, 3], dtype=float)
        trend = _compute_trend(values, 5)
        assert trend == 0.0

    def test_single_value_returns_zero(self):
        values = np.array([5.0])
        trend = _compute_trend(values, 5)
        assert trend == 0.0

    def test_empty_array_returns_zero(self):
        values = np.array([], dtype=float)
        trend = _compute_trend(values, 5)
        assert trend == 0.0

    def test_window_larger_than_data(self):
        values = np.array([1, 2, 3], dtype=float)
        trend = _compute_trend(values, 10)
        assert trend > 0  # Still computes on available data

    def test_all_zeros_returns_zero(self):
        values = np.array([0, 0, 0, 0], dtype=float)
        trend = _compute_trend(values, 4)
        assert trend == 0.0


class TestEmptyFeatures:
    def test_empty_features_structure(self):
        feat = _empty_features("SKU_X", 100)
        assert feat["sku_id"] == "SKU_X"
        assert feat["age_days"] == 100
        assert feat["avg_weekly_sales"] == 0.0
        assert feat["weeks_of_history"] == 0


class TestComputeLifecycleFeatures:
    def test_basic_feature_computation(self, sample_sales, sample_trials):
        config = LifecycleConfig()
        sku_master = pd.DataFrame({"sku_id": ["SKU_001"], "launch_date": ["2025-01-01"]})
        features = compute_lifecycle_features(
            sample_sales, sample_trials, pd.DataFrame(), sku_master,
            config, as_of_date=date(2025, 7, 1),
        )
        assert len(features) == 1
        row = features.iloc[0]
        assert row["sku_id"] == "SKU_001"
        assert row["age_days"] == 181
        assert row["avg_weekly_sales"] > 0
        assert row["weeks_of_history"] > 0

    def test_empty_sales_returns_empty(self):
        config = LifecycleConfig()
        result = compute_lifecycle_features(
            pd.DataFrame(), pd.DataFrame(), pd.DataFrame(),
            pd.DataFrame({"sku_id": ["X"]}), config,
        )
        assert result.empty

    def test_features_have_all_columns(self, sample_sales, sample_trials):
        config = LifecycleConfig()
        sku_master = pd.DataFrame({"sku_id": ["SKU_001"], "launch_date": ["2025-01-01"]})
        features = compute_lifecycle_features(
            sample_sales, sample_trials, pd.DataFrame(), sku_master,
            config, as_of_date=date(2025, 7, 1),
        )
        expected_cols = [
            "sku_id", "age_days", "sales_velocity_trend", "trial_trend",
            "conversion_trend", "aging_inventory_pct", "markdown_count",
            "avg_weekly_sales", "weeks_of_history", "peak_weekly_sales",
            "current_vs_peak_ratio",
        ]
        for col in expected_cols:
            assert col in features.columns, f"Missing column: {col}"

    def test_current_vs_peak_bounded(self, sample_sales):
        config = LifecycleConfig()
        sku_master = pd.DataFrame({"sku_id": ["SKU_001"], "launch_date": ["2025-01-01"]})
        features = compute_lifecycle_features(
            sample_sales, pd.DataFrame(), pd.DataFrame(), sku_master,
            config, as_of_date=date(2025, 7, 1),
        )
        assert 0.0 <= features.iloc[0]["current_vs_peak_ratio"] <= 1.0


# ─── Classifier Tests ────────────────────────────────────────────────────────


class TestRuleBasedClassifier:
    def test_launch_classification(self, config):
        features = {
            "sku_id": "SKU_NEW", "age_days": 30,
            "sales_velocity_trend": 0.1, "trial_trend": 0.05,
            "conversion_trend": 0.02, "aging_inventory_pct": 0.0,
            "markdown_count": 0, "avg_weekly_sales": 2.0,
            "weeks_of_history": 4, "peak_weekly_sales": 3.0,
            "current_vs_peak_ratio": 0.9,
        }
        result = classify_single_sku(features, config)
        assert result.lifecycle_stage == LifecycleStage.LAUNCH
        assert result.recommended_action == RecommendedAction.EXPAND_DISTRIBUTION

    def test_growth_classification(self, config):
        features = {
            "sku_id": "SKU_GROW", "age_days": 120,
            "sales_velocity_trend": 0.12, "trial_trend": 0.08,
            "conversion_trend": 0.03, "aging_inventory_pct": 0.05,
            "markdown_count": 0, "avg_weekly_sales": 5.0,
            "weeks_of_history": 16, "peak_weekly_sales": 6.0,
            "current_vs_peak_ratio": 0.85,
        }
        result = classify_single_sku(features, config)
        assert result.lifecycle_stage == LifecycleStage.GROWTH
        assert result.recommended_action == RecommendedAction.EXPAND_DISTRIBUTION

    def test_core_classification(self, config):
        features = {
            "sku_id": "SKU_CORE", "age_days": 300,
            "sales_velocity_trend": 0.01, "trial_trend": 0.0,
            "conversion_trend": 0.0, "aging_inventory_pct": 0.1,
            "markdown_count": 0, "avg_weekly_sales": 8.0,
            "weeks_of_history": 40, "peak_weekly_sales": 10.0,
            "current_vs_peak_ratio": 0.8,
        }
        result = classify_single_sku(features, config)
        assert result.lifecycle_stage == LifecycleStage.CORE
        assert result.recommended_action == RecommendedAction.PROTECT_PLACEMENT

    def test_decline_classification(self, config):
        features = {
            "sku_id": "SKU_DEC", "age_days": 350,
            "sales_velocity_trend": -0.15, "trial_trend": -0.08,
            "conversion_trend": -0.05, "aging_inventory_pct": 0.35,
            "markdown_count": 2, "avg_weekly_sales": 2.0,
            "weeks_of_history": 45, "peak_weekly_sales": 10.0,
            "current_vs_peak_ratio": 0.3,
        }
        result = classify_single_sku(features, config)
        assert result.lifecycle_stage == LifecycleStage.DECLINE

    def test_exit_classification(self, config):
        features = {
            "sku_id": "SKU_EXIT", "age_days": 500,
            "sales_velocity_trend": -0.25, "trial_trend": -0.15,
            "conversion_trend": -0.10, "aging_inventory_pct": 0.7,
            "markdown_count": 3, "avg_weekly_sales": 0.5,
            "weeks_of_history": 60, "peak_weekly_sales": 8.0,
            "current_vs_peak_ratio": 0.1,
        }
        result = classify_single_sku(features, config)
        assert result.lifecycle_stage == LifecycleStage.EXIT
        assert result.recommended_action == RecommendedAction.DISCONTINUE

    def test_maturity_fallback(self, config):
        """SKU that doesn't match other rules falls to maturity."""
        features = {
            "sku_id": "SKU_MAT", "age_days": 400,
            "sales_velocity_trend": -0.02, "trial_trend": -0.01,
            "conversion_trend": -0.01, "aging_inventory_pct": 0.2,
            "markdown_count": 1, "avg_weekly_sales": 4.0,
            "weeks_of_history": 50, "peak_weekly_sales": 10.0,
            "current_vs_peak_ratio": 0.45,
        }
        result = classify_single_sku(features, config)
        assert result.lifecycle_stage == LifecycleStage.MATURITY

    def test_confidence_in_valid_range(self, sample_features, config):
        results = classify_skus(sample_features, config)
        for r in results:
            assert 0.0 <= r.confidence <= 1.0

    def test_all_skus_classified(self, sample_features, config):
        results = classify_skus(sample_features, config)
        assert len(results) == len(sample_features)

    def test_classify_skus_returns_valid_stages(self, sample_features, config):
        results = classify_skus(sample_features, config)
        valid_stages = {s for s in LifecycleStage}
        for r in results:
            assert r.lifecycle_stage in valid_stages

    def test_classify_skus_returns_valid_actions(self, sample_features, config):
        results = classify_skus(sample_features, config)
        valid_actions = {a for a in RecommendedAction}
        for r in results:
            assert r.recommended_action in valid_actions


class TestActionDetermination:
    def test_decline_with_high_aging_gets_markdown(self, config):
        feat = LifecycleFeatures(
            sku_id="X", age_days=300, sales_velocity_trend=-0.1,
            trial_trend=-0.05, conversion_trend=-0.03,
            aging_inventory_pct=0.65, markdown_count=1,
            avg_weekly_sales=1.0, weeks_of_history=30,
            peak_weekly_sales=5.0, current_vs_peak_ratio=0.3,
        )
        action = _determine_action(LifecycleStage.DECLINE, feat, config)
        assert action == RecommendedAction.MARKDOWN

    def test_decline_with_moderate_aging_gets_transfer(self, config):
        feat = LifecycleFeatures(
            sku_id="X", age_days=300, sales_velocity_trend=-0.1,
            trial_trend=-0.05, conversion_trend=-0.03,
            aging_inventory_pct=0.45, markdown_count=0,
            avg_weekly_sales=1.0, weeks_of_history=30,
            peak_weekly_sales=5.0, current_vs_peak_ratio=0.3,
        )
        action = _determine_action(LifecycleStage.DECLINE, feat, config)
        assert action == RecommendedAction.TRANSFER

    def test_maturity_with_aging_gets_reduce_depth(self, config):
        feat = LifecycleFeatures(
            sku_id="X", age_days=400, sales_velocity_trend=0.0,
            trial_trend=0.0, conversion_trend=0.0,
            aging_inventory_pct=0.5, markdown_count=0,
            avg_weekly_sales=3.0, weeks_of_history=40,
            peak_weekly_sales=5.0, current_vs_peak_ratio=0.6,
        )
        action = _determine_action(LifecycleStage.MATURITY, feat, config)
        assert action == RecommendedAction.REDUCE_DEPTH

    def test_exit_always_discontinue(self, config):
        feat = LifecycleFeatures(
            sku_id="X", age_days=600, sales_velocity_trend=-0.3,
            trial_trend=-0.2, conversion_trend=-0.1,
            aging_inventory_pct=0.8, markdown_count=5,
            avg_weekly_sales=0.1, weeks_of_history=70,
            peak_weekly_sales=10.0, current_vs_peak_ratio=0.05,
        )
        action = _determine_action(LifecycleStage.EXIT, feat, config)
        assert action == RecommendedAction.DISCONTINUE

    def test_launch_gets_expand_distribution(self, config):
        feat = LifecycleFeatures(
            sku_id="X", age_days=20, sales_velocity_trend=0.1,
            trial_trend=0.05, conversion_trend=0.02,
            aging_inventory_pct=0.0, markdown_count=0,
            avg_weekly_sales=2.0, weeks_of_history=3,
            peak_weekly_sales=3.0, current_vs_peak_ratio=0.9,
        )
        action = _determine_action(LifecycleStage.LAUNCH, feat, config)
        assert action == RecommendedAction.EXPAND_DISTRIBUTION


# ─── Survival Scoring Tests ──────────────────────────────────────────────────


class TestWeibullFunctions:
    def test_survival_at_zero(self):
        assert _weibull_survival(0, 1.5, 365) == 1.0

    def test_survival_decreases_with_age(self):
        s1 = _weibull_survival(100, 1.5, 365)
        s2 = _weibull_survival(200, 1.5, 365)
        assert s1 > s2

    def test_survival_always_positive(self):
        assert _weibull_survival(10000, 1.5, 365) > 0

    def test_hazard_at_zero(self):
        assert _weibull_hazard(0, 1.5, 365) == 0.0

    def test_hazard_increases_when_shape_gt_1(self):
        h1 = _weibull_hazard(100, 1.5, 365)
        h2 = _weibull_hazard(200, 1.5, 365)
        assert h2 > h1  # Increasing hazard for shape > 1

    def test_hazard_positive(self):
        assert _weibull_hazard(100, 1.5, 365) > 0


class TestEstimateRemainingWeeks:
    def test_zero_hazard(self):
        assert _estimate_remaining_weeks(0.8, 0.0) == 0.0

    def test_zero_survival(self):
        assert _estimate_remaining_weeks(0.0, 0.01) == 0.0

    def test_high_survival_more_weeks(self):
        w1 = _estimate_remaining_weeks(0.9, 0.01)
        w2 = _estimate_remaining_weeks(0.3, 0.01)
        assert w1 > w2

    def test_positive_result(self):
        weeks = _estimate_remaining_weeks(0.7, 0.005)
        assert weeks > 0


class TestSurvivalScoring:
    def test_scores_computed(self, sample_features, config):
        result = compute_survival_scores(sample_features, config)
        assert "survival_score" in result.columns
        assert "hazard_rate" in result.columns
        assert "expected_remaining_weeks" in result.columns

    def test_survival_scores_bounded(self, sample_features, config):
        result = compute_survival_scores(sample_features, config)
        assert (result["survival_score"] >= 0.0).all()
        assert (result["survival_score"] <= 1.0).all()

    def test_hazard_rates_nonnegative(self, sample_features, config):
        result = compute_survival_scores(sample_features, config)
        assert (result["hazard_rate"] >= 0.0).all()

    def test_remaining_weeks_nonnegative(self, sample_features, config):
        result = compute_survival_scores(sample_features, config)
        assert (result["expected_remaining_weeks"] >= 0.0).all()

    def test_young_sku_has_higher_survival(self, sample_features, config):
        result = compute_survival_scores(sample_features, config)
        launch_score = result[result["sku_id"] == "SKU_LAUNCH"]["survival_score"].iloc[0]
        exit_score = result[result["sku_id"] == "SKU_EXIT"]["survival_score"].iloc[0]
        assert launch_score > exit_score

    def test_empty_input(self, config):
        result = compute_survival_scores(pd.DataFrame(), config)
        assert result.empty

    def test_no_intermediate_columns_in_output(self, sample_features, config):
        result = compute_survival_scores(sample_features, config)
        intermediate = ["base_survival", "velocity_factor", "trial_factor",
                        "conversion_factor", "age_factor", "aging_factor",
                        "markdown_factor"]
        for col in intermediate:
            assert col not in result.columns


# ─── Pipeline Summary Tests ──────────────────────────────────────────────────


class TestBuildSummary:
    def test_summary_counts(self, sample_features, config):
        classifications = classify_skus(sample_features, config)
        summary = build_summary(classifications)
        assert summary.total_skus == len(sample_features)
        assert sum(summary.stage_counts.values()) == summary.total_skus
        assert sum(summary.action_counts.values()) == summary.total_skus

    def test_summary_avg_confidence(self, sample_features, config):
        classifications = classify_skus(sample_features, config)
        summary = build_summary(classifications)
        assert 0.0 < summary.avg_confidence <= 1.0

    def test_empty_classifications(self):
        summary = build_summary([])
        assert summary.total_skus == 0
        assert summary.stage_counts == {}
        assert summary.avg_confidence == 0.0


# ─── Integration: end-to-end classification ──────────────────────────────────


class TestEndToEnd:
    def test_features_to_classification(self, sample_features, config):
        """Feature DataFrame -> classify -> validate all outputs."""
        results = classify_skus(sample_features, config)
        assert len(results) == len(sample_features)

        for r in results:
            assert isinstance(r, LifecycleClassification)
            assert r.sku_id in sample_features["sku_id"].values
            assert r.lifecycle_stage in LifecycleStage
            assert r.recommended_action in RecommendedAction
            assert 0.0 <= r.confidence <= 1.0
            assert len(r.reason) > 0
            assert r.features is not None

    def test_features_to_scoring(self, sample_features, config):
        """Feature DataFrame -> survival scores -> validate outputs."""
        scores = compute_survival_scores(sample_features, config)
        assert len(scores) == len(sample_features)
        assert (scores["survival_score"] >= 0).all()
        assert (scores["survival_score"] <= 1).all()

    def test_classification_and_scoring_same_skus(self, sample_features, config):
        """Both v1 and v2 cover all SKUs."""
        classifications = classify_skus(sample_features, config)
        scores = compute_survival_scores(sample_features, config)

        cls_skus = {c.sku_id for c in classifications}
        score_skus = set(scores["sku_id"].values)
        assert cls_skus == score_skus

    def test_all_six_stages_representable(self, config):
        """Verify the classifier can produce all six stages."""
        test_cases = [
            {"sku_id": "L", "age_days": 20, "sales_velocity_trend": 0.1,
             "trial_trend": 0.05, "conversion_trend": 0.02,
             "aging_inventory_pct": 0.0, "markdown_count": 0,
             "avg_weekly_sales": 2.0, "weeks_of_history": 3,
             "peak_weekly_sales": 3.0, "current_vs_peak_ratio": 0.9},
            {"sku_id": "G", "age_days": 120, "sales_velocity_trend": 0.15,
             "trial_trend": 0.08, "conversion_trend": 0.03,
             "aging_inventory_pct": 0.05, "markdown_count": 0,
             "avg_weekly_sales": 5.0, "weeks_of_history": 16,
             "peak_weekly_sales": 6.0, "current_vs_peak_ratio": 0.85},
            {"sku_id": "C", "age_days": 300, "sales_velocity_trend": 0.01,
             "trial_trend": 0.0, "conversion_trend": 0.0,
             "aging_inventory_pct": 0.1, "markdown_count": 0,
             "avg_weekly_sales": 8.0, "weeks_of_history": 40,
             "peak_weekly_sales": 10.0, "current_vs_peak_ratio": 0.8},
            {"sku_id": "M", "age_days": 400, "sales_velocity_trend": -0.02,
             "trial_trend": -0.01, "conversion_trend": -0.01,
             "aging_inventory_pct": 0.2, "markdown_count": 1,
             "avg_weekly_sales": 4.0, "weeks_of_history": 50,
             "peak_weekly_sales": 10.0, "current_vs_peak_ratio": 0.45},
            {"sku_id": "D", "age_days": 350, "sales_velocity_trend": -0.15,
             "trial_trend": -0.08, "conversion_trend": -0.05,
             "aging_inventory_pct": 0.35, "markdown_count": 2,
             "avg_weekly_sales": 2.0, "weeks_of_history": 45,
             "peak_weekly_sales": 10.0, "current_vs_peak_ratio": 0.3},
            {"sku_id": "E", "age_days": 500, "sales_velocity_trend": -0.25,
             "trial_trend": -0.15, "conversion_trend": -0.1,
             "aging_inventory_pct": 0.7, "markdown_count": 3,
             "avg_weekly_sales": 0.5, "weeks_of_history": 60,
             "peak_weekly_sales": 8.0, "current_vs_peak_ratio": 0.1},
        ]
        features_df = pd.DataFrame(test_cases)
        results = classify_skus(features_df, config)
        stages_found = {r.lifecycle_stage for r in results}
        assert stages_found == set(LifecycleStage), (
            f"Missing stages: {set(LifecycleStage) - stages_found}"
        )
