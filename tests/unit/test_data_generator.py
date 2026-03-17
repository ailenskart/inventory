"""Unit tests for the synthetic data generator."""

import pytest

from data.synthetic.generate import (
    generate_calendar,
    generate_stores,
    generate_skus,
    generate_vendors,
    generate_eye_tests,
    generate_transfers,
    generate_purchase_orders,
    seasonal_multiplier,
    sunglasses_seasonality,
    STORE_CLUSTERS,
)
from datetime import date


class TestStoreGeneration:
    def test_generates_correct_count(self):
        stores = generate_stores()
        assert len(stores) == 50

    def test_all_stores_have_required_fields(self):
        stores = generate_stores()
        required = {"store_id", "store_name", "city", "state", "region", "store_cluster",
                     "store_format", "display_capacity", "storage_capacity"}
        for store in stores:
            assert required.issubset(store.keys()), f"Missing fields in {store['store_id']}"

    def test_store_clusters_are_valid(self):
        stores = generate_stores()
        valid_clusters = set(STORE_CLUSTERS.keys())
        for store in stores:
            assert store["store_cluster"] in valid_clusters, f"Invalid cluster: {store['store_cluster']}"

    def test_store_ids_are_unique(self):
        stores = generate_stores()
        ids = [s["store_id"] for s in stores]
        assert len(ids) == len(set(ids))


class TestVendorGeneration:
    def test_generates_correct_count(self):
        vendors = generate_vendors()
        assert len(vendors) == 5

    def test_vendor_ids_unique(self):
        vendors = generate_vendors()
        ids = [v["vendor_id"] for v in vendors]
        assert len(ids) == len(set(ids))


class TestSKUGeneration:
    def test_generates_correct_count(self):
        vendors = generate_vendors()
        skus = generate_skus(vendors)
        assert len(skus) == 1000

    def test_sku_type_consistency(self):
        """display_dummy => order_capture, physical_sell => direct_sell."""
        vendors = generate_vendors()
        skus = generate_skus(vendors)
        for sku in skus:
            if sku["sku_type"] == "display_dummy":
                assert sku["fulfillment_type"] == "order_capture"
                assert sku["is_display_only"] is True
            else:
                assert sku["fulfillment_type"] == "direct_sell"
                assert sku["is_display_only"] is False

    def test_sunglasses_are_always_physical_sell(self):
        vendors = generate_vendors()
        skus = generate_skus(vendors)
        sunglass_skus = [s for s in skus if s["category"] == "sunglasses"]
        assert len(sunglass_skus) > 0
        for sku in sunglass_skus:
            assert sku["sku_type"] == "physical_sell"
            assert sku["sales_channel"] == "walk_in"

    def test_category_distribution(self):
        """Roughly 60% eyeglasses, 25% sunglasses, 15% contact lenses."""
        vendors = generate_vendors()
        skus = generate_skus(vendors)
        cats = {s["category"] for s in skus}
        assert "eyeglasses" in cats
        assert "sunglasses" in cats
        assert "contact_lenses" in cats

    def test_all_skus_have_vendor(self):
        vendors = generate_vendors()
        skus = generate_skus(vendors)
        vendor_ids = {v["vendor_id"] for v in vendors}
        for sku in skus:
            assert sku["vendor_id"] in vendor_ids


class TestCalendarGeneration:
    def test_generates_365_days(self):
        cal = generate_calendar()
        assert len(cal) == 365

    def test_has_festive_days(self):
        cal = generate_calendar()
        festive = [c for c in cal if c["is_festive"]]
        assert len(festive) > 0

    def test_has_all_seasons(self):
        cal = generate_calendar()
        seasons = {c["season"] for c in cal}
        assert seasons == {"summer", "monsoon", "winter", "autumn"}


class TestSeasonality:
    def test_diwali_has_high_multiplier(self):
        mult, name = seasonal_multiplier(date(2024, 11, 1))
        assert mult == 2.0
        assert name == "diwali"

    def test_normal_day_has_base_multiplier(self):
        mult, name = seasonal_multiplier(date(2024, 6, 15))
        assert mult == 1.0
        assert name is None

    def test_sunglasses_peak_in_summer(self):
        summer = sunglasses_seasonality(date(2024, 5, 1))
        winter = sunglasses_seasonality(date(2024, 12, 15))
        assert summer > winter


class TestTransferGeneration:
    def test_transfers_have_paired_directions(self):
        stores = generate_stores()
        vendors = generate_vendors()
        skus = generate_skus(vendors)
        transfers = generate_transfers(stores, skus)

        # Group by transfer_id
        from collections import Counter
        ids = Counter(t["transfer_id"] for t in transfers)
        for tid, count in ids.items():
            assert count == 2, f"Transfer {tid} should have exactly 2 rows (out+in)"

    def test_transfers_balance(self):
        stores = generate_stores()
        vendors = generate_vendors()
        skus = generate_skus(vendors)
        transfers = generate_transfers(stores, skus)

        from collections import defaultdict
        balance = defaultdict(lambda: {"out": 0, "in": 0})
        for t in transfers:
            if t["status"] == "received":
                balance[t["transfer_id"]][t["transfer_direction"]] += t["transfer_qty"]

        for tid, b in balance.items():
            assert b["out"] == b["in"], f"Transfer {tid} imbalanced: out={b['out']} in={b['in']}"


class TestPurchaseOrderGeneration:
    def test_po_dates_are_valid(self):
        vendors = generate_vendors()
        skus = generate_skus(vendors)
        pos = generate_purchase_orders(vendors, skus)

        for po in pos:
            assert po["order_date"] <= po["expected_delivery_date"], \
                f"PO {po['po_id']}: order_date > expected_delivery_date"
