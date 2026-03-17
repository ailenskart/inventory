"""Unit tests for service modules."""

import pytest
import pandas as pd
from datetime import date

from services.purchase_orders.manager import PurchaseOrderManager


class TestPurchaseOrderManager:
    def setup_method(self):
        self.manager = PurchaseOrderManager()

    def test_create_draft(self):
        po = self.manager.create_draft(
            vendor_id="VND0001",
            lines=[
                {"sku_id": "SKU00001", "qty_ordered": 50, "unit_cost": 500.0},
                {"sku_id": "SKU00002", "qty_ordered": 30, "unit_cost": 700.0},
            ],
        )
        assert po["status"] == "draft"
        assert po["total_qty"] == 80

    def test_submit_po(self):
        po = self.manager.create_draft("VND0001", [{"sku_id": "SKU00001", "qty_ordered": 10, "unit_cost": 100}])
        submitted = self.manager.submit(po["po_id"])
        assert submitted["status"] == "submitted"

    def test_approve_po(self):
        po = self.manager.create_draft("VND0001", [{"sku_id": "SKU00001", "qty_ordered": 10, "unit_cost": 100}])
        self.manager.submit(po["po_id"])
        approved = self.manager.approve(po["po_id"])
        assert approved["status"] == "approved"

    def test_cannot_approve_draft(self):
        po = self.manager.create_draft("VND0001", [{"sku_id": "SKU00001", "qty_ordered": 10, "unit_cost": 100}])
        with pytest.raises(ValueError, match="not in submitted status"):
            self.manager.approve(po["po_id"])

    def test_record_receipt(self):
        po = self.manager.create_draft("VND0001", [{"sku_id": "SKU00001", "qty_ordered": 10, "unit_cost": 100}])
        self.manager.submit(po["po_id"])
        self.manager.approve(po["po_id"])
        result = self.manager.record_receipt(po["po_id"], [{"sku_id": "SKU00001", "qty_received": 10}])
        assert result["status"] == "received"
        assert result["total_received"] == 10


class TestReplenishmentEngine:
    def test_compute_reorder_points(self):
        from services.replenishment.engine import compute_reorder_points

        forecasts = pd.DataFrame({
            "store_id": ["STR0001", "STR0001"],
            "sku_id": ["SKU00001", "SKU00002"],
            "forecast_qty": [20.0, 5.0],
        })
        lead_times = pd.DataFrame({
            "sku_id": ["SKU00001", "SKU00002"],
            "lead_time_days": [7, 14],
        })
        result = compute_reorder_points(forecasts, lead_times)
        assert len(result) == 2
        assert "reorder_point" in result.columns
        assert all(result["reorder_point"] >= 0)

    def test_identify_replenishment_needs(self):
        from services.replenishment.engine import identify_replenishment_needs

        reorder_points = pd.DataFrame({
            "store_id": ["STR0001", "STR0001"],
            "sku_id": ["SKU00001", "SKU00002"],
            "reorder_point": [10.0, 5.0],
            "reorder_qty": [20, 10],
        })
        inventory = pd.DataFrame({
            "store_id": ["STR0001", "STR0001"],
            "sku_id": ["SKU00001", "SKU00002"],
            "on_hand_qty": [3, 20],
        })
        result = identify_replenishment_needs(reorder_points, inventory)
        # SKU00001 needs replenishment (3 < 10), SKU00002 doesn't (20 > 5)
        assert len(result) == 1
        assert result.iloc[0]["sku_id"] == "SKU00001"
