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
    def test_compute_reorder_point(self):
        from services.replenishment.engine import compute_reorder_point, compute_safety_stock

        safety = compute_safety_stock(demand_std_daily=2.0, lead_time_days=7, z_score=1.645)
        rop = compute_reorder_point(avg_daily_demand=20.0 / 7, lead_time_days=7, safety_stock=safety)
        assert rop > 0
        assert rop >= 20.0  # At least lead-time demand

    def test_generate_recommendations(self):
        from services.replenishment.config import ReplenishmentConfig
        from services.replenishment.engine import generate_recommendations

        config = ReplenishmentConfig()
        positions = pd.DataFrame([
            {
                "store_id": "STR0001", "sku_id": "SKU00001",
                "on_hand_qty": 3, "in_transit_qty": 0, "available_qty": 3,
                "avg_weekly_demand": 14.0, "point_forecast": 14.0,
                "upper_bound": 18.0, "demand_std_weekly": 3.0,
                "lead_time_days": 7, "moq": 1, "case_pack": 1,
                "store_cluster": "METRO_HIGH", "sku_type": "physical_sell",
                "fulfillment_type": "direct_sell", "is_display_only": 0,
                "category": "eyeglasses", "vendor_id": "VND0001",
                "mrp": 2000, "store_capacity": 500, "current_store_units": 200,
            },
            {
                "store_id": "STR0001", "sku_id": "SKU00002",
                "on_hand_qty": 100, "in_transit_qty": 0, "available_qty": 100,
                "avg_weekly_demand": 5.0, "point_forecast": 5.0,
                "upper_bound": 7.0, "demand_std_weekly": 1.0,
                "lead_time_days": 7, "moq": 1, "case_pack": 1,
                "store_cluster": "METRO_HIGH", "sku_type": "physical_sell",
                "fulfillment_type": "direct_sell", "is_display_only": 0,
                "category": "eyeglasses", "vendor_id": "VND0001",
                "mrp": 1500, "store_capacity": 500, "current_store_units": 200,
            },
        ])
        result = generate_recommendations(positions, config)
        # SKU00001 needs replenishment (3 units, 14/wk demand)
        # SKU00002 doesn't (100 units, 5/wk demand — ~140 days cover)
        assert len(result) == 1
        assert result.iloc[0]["sku_id"] == "SKU00001"
