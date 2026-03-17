"""Unit tests for canonical schemas."""

import pytest
from datetime import date

from schemas.base import StoreType, StoreFormat, ProductCategory, FulfillmentType, OrderStatus
from schemas.store import Store
from schemas.sku import SKU
from schemas.vendor import Vendor
from schemas.transactions import DailySales, DailyInventory, Transfer, PurchaseOrder
from schemas.customer_signals import StoreTrial, EyeTest, StoreTraffic, PricingPromotion


class TestStoreSchema:
    def test_create_store(self):
        store = Store(
            store_id="STR0001",
            store_name="Lenskart Mumbai 1",
            city="Mumbai",
            state="Maharashtra",
            region="West",
            pincode="400001",
            store_type=StoreType.COMPANY_OWNED,
            store_format=StoreFormat.LARGE,
            display_capacity=200,
        )
        assert store.store_id == "STR0001"
        assert store.is_active is True
        assert store.store_type == StoreType.COMPANY_OWNED

    def test_store_defaults(self):
        store = Store(
            store_id="S1",
            store_name="Test",
            city="Test",
            state="Test",
            region="Test",
            pincode="000000",
            store_type=StoreType.FRANCHISE,
            store_format=StoreFormat.SMALL,
        )
        assert store.display_capacity == 0
        assert store.cluster_id is None


class TestSKUSchema:
    def test_create_sku(self):
        sku = SKU(
            sku_id="SKU00001",
            product_name="Vincent Chase Rectangle Black",
            brand="Vincent Chase",
            category=ProductCategory.EYEGLASSES,
            mrp=1999.0,
            cost_price=799.0,
            fulfillment_type=FulfillmentType.ORDER_CAPTURE,
            is_display_only=True,
        )
        assert sku.sku_id == "SKU00001"
        assert sku.fulfillment_type == FulfillmentType.ORDER_CAPTURE

    def test_sunglasses_direct_sell(self):
        sku = SKU(
            sku_id="SKU00002",
            product_name="John Jacobs Aviator",
            brand="John Jacobs",
            category=ProductCategory.SUNGLASSES,
            fulfillment_type=FulfillmentType.DIRECT_SELL,
        )
        assert sku.fulfillment_type == FulfillmentType.DIRECT_SELL
        assert sku.is_display_only is False


class TestTransactionSchemas:
    def test_daily_sales(self):
        sale = DailySales(
            store_id="STR0001",
            sku_id="SKU00001",
            sale_date=date(2024, 1, 15),
            qty_sold=2,
            revenue=3998.0,
            fulfillment_type=FulfillmentType.DIRECT_SELL,
        )
        assert sale.qty_sold == 2
        assert sale.is_return is False

    def test_daily_inventory(self):
        inv = DailyInventory(
            store_id="STR0001",
            sku_id="SKU00001",
            snapshot_date=date(2024, 1, 15),
            on_hand_qty=10,
            on_display_qty=2,
            in_storage_qty=8,
        )
        assert inv.on_hand_qty == 10

    def test_transfer(self):
        transfer = Transfer(
            transfer_id="TRF001",
            from_store_id="STR0001",
            to_store_id="STR0002",
            sku_id="SKU00001",
            qty=5,
            reason="rebalance",
        )
        assert transfer.status == OrderStatus.DRAFT

    def test_purchase_order(self):
        po = PurchaseOrder(
            po_id="PO001",
            vendor_id="VND0001",
            total_qty=100,
            total_value=50000.0,
        )
        assert po.status == OrderStatus.DRAFT


class TestCustomerSignalSchemas:
    def test_store_trial(self):
        trial = StoreTrial(
            trial_id="TRL00000001",
            store_id="STR0001",
            sku_id="SKU00001",
            trial_date=date(2024, 1, 15),
            resulted_in_order=True,
            order_id="ORD0000001",
        )
        assert trial.resulted_in_order is True

    def test_store_traffic(self):
        traffic = StoreTraffic(
            store_id="STR0001",
            traffic_date=date(2024, 1, 15),
            footfall_count=150,
            walk_ins=120,
            appointments=15,
        )
        assert traffic.footfall_count == 150
