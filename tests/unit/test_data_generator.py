"""Unit tests for the synthetic data generator."""

import pytest
from collections import Counter, defaultdict
from datetime import date

from data.synthetic.generate import (
    BRAND_CONFIG,
    STORE_CLUSTERS,
    generate_calendar,
    generate_stores,
    generate_skus,
    generate_vendors,
    generate_transfers,
    generate_purchase_orders,
    seasonal_multiplier,
    sunglasses_seasonality,
)


# ─── Shared fixtures ────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def stores():
    return generate_stores()


@pytest.fixture(scope="module")
def vendors():
    return generate_vendors()


@pytest.fixture(scope="module")
def skus(vendors):
    return generate_skus(vendors)


# ─── Store tests ─────────────────────────────────────────────────────────────

class TestStoreGeneration:
    def test_generates_correct_count(self, stores):
        assert len(stores) == 50

    def test_all_stores_have_required_fields(self, stores):
        required = {"store_id", "store_name", "city", "state", "region", "store_cluster",
                     "store_format", "display_capacity", "storage_capacity", "store_type"}
        for store in stores:
            assert required.issubset(store.keys()), f"Missing fields in {store['store_id']}"

    def test_store_clusters_are_valid(self, stores):
        valid_clusters = set(STORE_CLUSTERS.keys())
        for store in stores:
            assert store["store_cluster"] in valid_clusters, f"Invalid cluster: {store['store_cluster']}"

    def test_store_ids_are_unique(self, stores):
        ids = [s["store_id"] for s in stores]
        assert len(ids) == len(set(ids))

    def test_store_ownership_types(self, stores):
        """All stores should be COCO or FOFO."""
        for store in stores:
            assert store["store_type"] in ("COCO", "FOFO"), f"Invalid store_type: {store['store_type']}"

    def test_metro_stores_are_coco(self, stores):
        """METRO_HIGH and METRO_MID clusters should always be COCO."""
        metro_stores = [s for s in stores if s["store_cluster"] in ("METRO_HIGH", "METRO_MID")]
        assert len(metro_stores) > 0
        for store in metro_stores:
            assert store["store_type"] == "COCO"

    def test_store_names_are_descriptive(self, stores):
        """Store names should include format keywords."""
        format_keywords = {"Mall", "High Street", "Hub", "Express", "Studio"}
        for store in stores:
            assert any(kw in store["store_name"] for kw in format_keywords), \
                f"Store name lacks format keyword: {store['store_name']}"


# ─── Vendor tests ────────────────────────────────────────────────────────────

class TestVendorGeneration:
    def test_generates_correct_count(self, vendors):
        assert len(vendors) == 5

    def test_vendor_ids_unique(self, vendors):
        ids = [v["vendor_id"] for v in vendors]
        assert len(ids) == len(set(ids))

    def test_vendor_names_are_realistic(self, vendors):
        """Vendor names should match real Lenskart supply chain partners."""
        names = {v["vendor_name"] for v in vendors}
        assert any("Lenskart" in n for n in names), "Should have in-house manufacturing"
        assert any("Essilor" in n or "Luxottica" in n for n in names), "Should have EssilorLuxottica"


# ─── SKU tests ───────────────────────────────────────────────────────────────

class TestSKUGeneration:
    def test_generates_correct_count(self, skus):
        assert len(skus) == 1000

    def test_sku_type_consistency(self, skus):
        """display_dummy => order_capture, physical_sell => direct_sell."""
        for sku in skus:
            if sku["sku_type"] == "display_dummy":
                assert sku["fulfillment_type"] == "order_capture"
                assert sku["is_display_only"] is True
            else:
                assert sku["fulfillment_type"] == "direct_sell"
                assert sku["is_display_only"] is False

    def test_sunglasses_are_always_physical_sell(self, skus):
        sunglass_skus = [s for s in skus if s["category"] == "sunglasses"]
        assert len(sunglass_skus) > 0
        for sku in sunglass_skus:
            assert sku["sku_type"] == "physical_sell"
            assert sku["sales_channel"] == "walk_in"

    def test_contact_lenses_are_always_physical_sell(self, skus):
        cl_skus = [s for s in skus if s["category"] == "contact_lenses"]
        assert len(cl_skus) > 0
        for sku in cl_skus:
            assert sku["sku_type"] == "physical_sell"
            assert sku["sales_channel"] == "prescription"

    def test_category_distribution(self, skus):
        """All expected categories should be present."""
        cats = {s["category"] for s in skus}
        assert "eyeglasses" in cats
        assert "sunglasses" in cats
        assert "contact_lenses" in cats
        assert "computer_glasses" in cats

    def test_all_skus_have_vendor(self, skus, vendors):
        vendor_ids = {v["vendor_id"] for v in vendors}
        for sku in skus:
            assert sku["vendor_id"] in vendor_ids

    def test_brand_distribution_is_weighted(self, skus):
        """Vincent Chase should be the most common brand (highest weight)."""
        brand_counts = Counter(s["brand"] for s in skus)
        assert brand_counts["Vincent Chase"] > brand_counts.get("Oakley", 0)
        assert brand_counts["Vincent Chase"] > brand_counts.get("Owndays", 0)

    def test_inhouse_brands_use_inhouse_vendor(self, skus):
        """In-house brands should be manufactured by VND001."""
        inhouse = {"Vincent Chase", "Lenskart Air", "Lenskart Blu", "Hooper", "Hustlr"}
        for sku in skus:
            if sku["brand"] in inhouse:
                assert sku["vendor_id"] == "VND001", \
                    f"{sku['brand']} SKU {sku['sku_id']} has vendor {sku['vendor_id']}, expected VND001"

    def test_premium_brands_use_luxottica_vendor(self, skus):
        """Premium third-party brands should use VND002 (EssilorLuxottica)."""
        premium = {"Ray-Ban", "Oakley", "Carrera", "Tommy Hilfiger", "Owndays"}
        for sku in skus:
            if sku["brand"] in premium:
                assert sku["vendor_id"] == "VND002", \
                    f"{sku['brand']} SKU {sku['sku_id']} has vendor {sku['vendor_id']}, expected VND002"

    def test_subcategory_price_tiers(self, skus):
        """Subcategory should reflect price tier."""
        for sku in skus:
            if sku["mrp"] >= 5000:
                assert "premium" in sku["subcategory"]
            elif sku["mrp"] >= 2000:
                assert "mid" in sku["subcategory"]
            else:
                assert "value" in sku["subcategory"]

    def test_contact_lenses_have_no_frame_attrs(self, skus):
        """Contact lenses should not have frame attributes."""
        for sku in skus:
            if sku["category"] == "contact_lenses":
                assert sku["frame_type"] is None
                assert sku["frame_shape"] is None
                assert sku["frame_material"] is None
                assert sku["frame_color"] is None

    def test_brand_category_consistency(self, skus):
        """Each brand should only produce categories defined in BRAND_CONFIG."""
        for sku in skus:
            if sku["brand"] in BRAND_CONFIG:
                allowed_cats = BRAND_CONFIG[sku["brand"]]["cats"]
                assert sku["category"] in allowed_cats, \
                    f"{sku['brand']} produced {sku['category']}, expected one of {allowed_cats}"


# ─── Calendar tests ──────────────────────────────────────────────────────────

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


# ─── Seasonality tests ───────────────────────────────────────────────────────

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


# ─── Transfer tests ──────────────────────────────────────────────────────────

class TestTransferGeneration:
    def test_transfers_have_paired_directions(self, stores, skus):
        transfers = generate_transfers(stores, skus)
        ids = Counter(t["transfer_id"] for t in transfers)
        for tid, count in ids.items():
            assert count == 2, f"Transfer {tid} should have exactly 2 rows (out+in)"

    def test_transfers_balance(self, stores, skus):
        transfers = generate_transfers(stores, skus)
        balance = defaultdict(lambda: {"out": 0, "in": 0})
        for t in transfers:
            if t["status"] == "received":
                balance[t["transfer_id"]][t["transfer_direction"]] += t["transfer_qty"]

        for tid, b in balance.items():
            assert b["out"] == b["in"], f"Transfer {tid} imbalanced: out={b['out']} in={b['in']}"


# ─── Purchase order tests ────────────────────────────────────────────────────

class TestPurchaseOrderGeneration:
    def test_po_dates_are_valid(self, vendors, skus):
        pos = generate_purchase_orders(vendors, skus)
        for po in pos:
            assert po["order_date"] <= po["expected_delivery_date"], \
                f"PO {po['po_id']}: order_date > expected_delivery_date"
