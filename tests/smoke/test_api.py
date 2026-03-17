"""Smoke tests for FastAPI application."""

import pytest
from fastapi.testclient import TestClient

from apps.api.app.main import app

client = TestClient(app)


class TestHealthEndpoints:
    def test_health(self):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_readiness(self):
        response = client.get("/ready")
        assert response.status_code == 200


class TestForecastEndpoints:
    def test_get_latest_forecasts(self):
        response = client.get("/api/v1/forecasts/latest")
        assert response.status_code == 200
        data = response.json()
        assert "forecasts" in data
        assert "count" in data

    def test_run_endpoint_exists(self):
        """POST /run endpoint should exist (may fail if DB not ready)."""
        response = client.post(
            "/api/v1/forecasts/run",
            json={"horizon_weeks": 4},
        )
        # 200 if DB exists, 503 if not — either is acceptable for smoke test
        assert response.status_code in (200, 500, 503)

    def test_store_forecast_404_without_data(self):
        """GET /store/{id} returns 404 when no forecasts exist."""
        response = client.get("/api/v1/forecasts/store/NONEXISTENT")
        assert response.status_code in (404, 503)

    def test_sku_forecast_404_without_data(self):
        """GET /sku/{id} returns 404 when no forecasts exist."""
        response = client.get("/api/v1/forecasts/sku/NONEXISTENT")
        assert response.status_code in (404, 503)


class TestReplenishmentEndpoints:
    def test_get_plan(self):
        response = client.get("/api/v1/replenishment/plan")
        assert response.status_code == 200
        data = response.json()
        assert "plans" in data
        assert "total_skus" in data
        assert "total_stores" in data

    def test_run_endpoint_exists(self):
        """POST /run should exist (may fail if DB not ready)."""
        response = client.post(
            "/api/v1/replenishment/run",
            json={"target_days_of_cover": 28},
        )
        assert response.status_code in (200, 500, 503)

    def test_store_replenishment_404(self):
        """GET /store/{id} returns 404 when no recommendations exist."""
        response = client.get("/api/v1/replenishment/store/NONEXISTENT")
        assert response.status_code in (404, 503)

    def test_execute(self):
        response = client.post(
            "/api/v1/replenishment/execute",
            json=["plan_1", "plan_2"],
        )
        assert response.status_code == 200


class TestAssortmentEndpoints:
    def test_get_recommendations(self):
        response = client.get("/api/v1/assortment/recommendations")
        assert response.status_code == 200

    def test_get_clusters(self):
        response = client.get("/api/v1/assortment/clusters")
        assert response.status_code == 200


class TestTransferEndpoints:
    def test_get_recommendations(self):
        response = client.get("/api/v1/transfers/recommendations")
        assert response.status_code == 200


class TestPurchaseOrderEndpoints:
    def test_list_pos(self):
        response = client.get("/api/v1/purchase-orders/")
        assert response.status_code == 200

    def test_create_po(self):
        response = client.post(
            "/api/v1/purchase-orders/create",
            json={
                "vendor_id": "VND0001",
                "lines": [{"sku_id": "SKU00001", "qty": 50, "unit_cost": 500.0, "destination": "warehouse"}],
            },
        )
        assert response.status_code == 200

    def test_get_suggestions(self):
        response = client.get("/api/v1/purchase-orders/suggestions")
        assert response.status_code == 200
