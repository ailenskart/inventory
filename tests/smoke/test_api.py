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
    def test_generate_forecasts(self):
        response = client.post(
            "/api/v1/forecasts/generate",
            json={"horizon_weeks": 4},
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_get_latest_forecasts(self):
        response = client.get("/api/v1/forecasts/latest")
        assert response.status_code == 200


class TestReplenishmentEndpoints:
    def test_get_plan(self):
        response = client.get("/api/v1/replenishment/plan")
        assert response.status_code == 200

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
