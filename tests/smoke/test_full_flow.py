"""Full-flow smoke test covering the entire pipeline.

Tests the integration across all modules using synthetic in-memory data:
1. Feature engineering
2. Lifecycle classification
3. Survival scoring
4. Assortment scoring with lifecycle freshness
5. Control tower endpoint
6. API router registration

This test does NOT require dbt or a DuckDB database —
it validates the code paths with synthetic data.
"""

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from apps.api.app.main import app


client = TestClient(app)


# ─── Synthetic data helpers ──────────────────────────────────────────────────


def _make_sales(n_skus: int = 5, n_weeks: int = 20) -> pd.DataFrame:
    """Generate synthetic daily sales."""
    np.random.seed(42)
    records = []
    for i in range(n_skus):
        sku = f"SKU_{i:03d}"
        for w in range(n_weeks):
            for d in range(7):
                day_offset = w * 7 + d
                sale_date = pd.Timestamp("2024-06-01") + pd.Timedelta(days=day_offset)
                # Sales decrease for later SKUs to simulate lifecycle
                qty = max(0, int(np.random.normal(5 - i * 0.5, 1.5)))
                records.append({"sku_id": sku, "sale_date": sale_date, "qty_sold": qty})
    return pd.DataFrame(records)


def _make_trials(n_skus: int = 5, n_weeks: int = 20) -> pd.DataFrame:
    """Generate synthetic trial data."""
    np.random.seed(42)
    records = []
    for i in range(n_skus):
        sku = f"SKU_{i:03d}"
        for w in range(n_weeks):
            trial_date = pd.Timestamp("2024-06-01") + pd.Timedelta(weeks=w)
            records.append({
                "sku_id": sku,
                "trial_date": trial_date,
                "resulted_in_order": int(np.random.random() < 0.3 - i * 0.03),
            })
    return pd.DataFrame(records)


def _make_sku_master(n_skus: int = 5) -> pd.DataFrame:
    """Generate SKU master with varying launch dates."""
    records = []
    for i in range(n_skus):
        launch = pd.Timestamp("2024-01-01") + pd.Timedelta(days=i * 60)
        records.append({"sku_id": f"SKU_{i:03d}", "launch_date": launch})
    return pd.DataFrame(records)


# ─── Test: Feature Engineering → Classification → Scoring ────────────────────


class TestFullLifecyclePipeline:
    """Tests the complete lifecycle pipeline in-memory."""

    @pytest.fixture
    def sales(self):
        return _make_sales()

    @pytest.fixture
    def trials(self):
        return _make_trials()

    @pytest.fixture
    def sku_master(self):
        return _make_sku_master()

    def test_feature_to_classification_flow(self, sales, trials, sku_master):
        """Features → classify → validate all stages covered."""
        from datetime import date

        from services.lifecycle.classifier import classify_skus
        from services.lifecycle.config import LifecycleConfig
        from services.lifecycle.features import compute_lifecycle_features

        config = LifecycleConfig()
        features = compute_lifecycle_features(
            sales, trials, pd.DataFrame(), sku_master,
            config, as_of_date=date(2024, 12, 1),
        )
        assert not features.empty
        assert len(features) == 5

        classifications = classify_skus(features, config)
        assert len(classifications) == 5

        # Each classification should have valid fields
        for c in classifications:
            assert c.lifecycle_stage is not None
            assert 0.0 <= c.confidence <= 1.0
            assert c.recommended_action is not None
            assert len(c.reason) > 0

    def test_feature_to_survival_scoring_flow(self, sales, trials, sku_master):
        """Features → survival scores → validate bounds."""
        from datetime import date

        from services.lifecycle.config import LifecycleConfig
        from services.lifecycle.features import compute_lifecycle_features
        from services.lifecycle.scoring import compute_survival_scores

        config = LifecycleConfig()
        features = compute_lifecycle_features(
            sales, trials, pd.DataFrame(), sku_master,
            config, as_of_date=date(2024, 12, 1),
        )

        scores = compute_survival_scores(features, config)
        assert not scores.empty
        assert (scores["survival_score"] >= 0).all()
        assert (scores["survival_score"] <= 1).all()
        assert (scores["expected_remaining_weeks"] >= 0).all()

    def test_lifecycle_summary_aggregation(self, sales, trials, sku_master):
        """Classifications → summary → validate counts."""
        from datetime import date

        from services.lifecycle.classifier import classify_skus
        from services.lifecycle.config import LifecycleConfig
        from services.lifecycle.features import compute_lifecycle_features
        from services.lifecycle.pipeline import build_summary

        config = LifecycleConfig()
        features = compute_lifecycle_features(
            sales, trials, pd.DataFrame(), sku_master,
            config, as_of_date=date(2024, 12, 1),
        )
        classifications = classify_skus(features, config)
        summary = build_summary(classifications)

        assert summary.total_skus == 5
        assert sum(summary.stage_counts.values()) == 5
        assert sum(summary.action_counts.values()) == 5
        assert 0 < summary.avg_confidence <= 1.0


# ─── Test: Assortment Scoring with Lifecycle Integration ─────────────────────


class TestAssortmentLifecycleIntegration:
    """Tests that lifecycle freshness scores flow into assortment scoring."""

    def test_freshness_scores_include_lifecycle_stages(self):
        """Assortment scoring should handle lifecycle stages from both old and new systems."""
        from services.assortment.config import AssortmentConfig, AssortmentScenario
        from services.assortment.scoring import compute_sku_scores

        config = AssortmentConfig()
        scenario = AssortmentScenario(name="test", description="test")

        # Create SKUs with new lifecycle stages
        df = pd.DataFrame({
            "sku_id": ["A", "B", "C", "D", "E", "F"],
            "store_id": ["S1"] * 6,
            "category": ["eyeglasses"] * 6,
            "subcategory": ["full_rim"] * 6,
            "brand": ["BrandA"] * 6,
            "sku_type": ["display_dummy"] * 6,
            "is_display_only": [1] * 6,
            "fulfillment_type": ["order_capture"] * 6,
            "lifecycle_stage": ["launch", "growth", "core", "maturity", "decline", "exit"],
            "mrp": [2000] * 6,
            "margin_pct": [0.4] * 6,
            "avg_weekly_demand": [5] * 6,
            "display_interest": [10] * 6,
            "trial_conversion_rate": [0.15] * 6,
        })

        scored = compute_sku_scores(df, scenario, config)

        # Freshness should be monotonically decreasing from launch to exit
        freshness = scored.set_index("sku_id")["freshness_score"]
        assert freshness["A"] >= freshness["B"]  # launch >= growth
        assert freshness["B"] >= freshness["C"]  # growth >= core
        assert freshness["E"] >= freshness["F"]  # decline >= exit

        # Exit should get stale penalty
        stale = scored.set_index("sku_id")["stale_penalty"]
        assert stale["F"] == 1.0  # exit
        assert stale["E"] > 0     # decline


# ─── Test: API Router Registration ──────────────────────────────────────────


class TestAPIIntegration:
    """Tests that all routers are registered and accessible."""

    def test_health_endpoint(self):
        response = client.get("/health")
        assert response.status_code == 200

    def test_control_tower_endpoint_exists(self):
        response = client.get("/api/v1/control-tower/summary")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "forecast" in data
        assert "stockout_risk" in data
        assert "replenishment" in data
        assert "transfers" in data
        assert "vendor_alerts" in data
        assert "purchase_orders" in data
        assert "lifecycle" in data

    def test_lifecycle_stages_endpoint(self):
        response = client.get("/api/v1/lifecycle/stages")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 6
        stages = {s["stage"] for s in data}
        assert stages == {"launch", "growth", "core", "maturity", "decline", "exit"}

    def test_assortment_scenarios_endpoint(self):
        response = client.get("/api/v1/assortment/scenarios")
        assert response.status_code == 200
        assert len(response.json()) == 5

    def test_all_routers_mounted(self):
        """Verify all expected API prefixes are mounted."""
        routes = [r.path for r in app.routes]
        expected_prefixes = [
            "/health",
            "/api/v1/control-tower",
            "/api/v1/forecasts",
            "/api/v1/lifecycle",
            "/api/v1/replenishment",
            "/api/v1/assortment",
            "/api/v1/transfers",
            "/api/v1/vendors",
            "/api/v1/purchase-orders",
        ]
        for prefix in expected_prefixes:
            matching = [r for r in routes if r.startswith(prefix)]
            assert len(matching) > 0, f"No routes found for prefix: {prefix}"
