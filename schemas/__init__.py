"""Canonical Pydantic schemas for Lenskart Retail Intelligence Platform.

Re-exports all domain models for convenient imports:
    from schemas import SKU, Store, Vendor, LifecycleStage
"""

from schemas.base import (
    FulfillmentType,
    OrderStatus,
    ProductCategory,
    StoreFormat,
    StoreType,
    TimestampMixin,
)
from schemas.customer_signals import EyeTest, PricingPromotion, StoreTrial, StoreTraffic
from schemas.lifecycle import (
    LifecycleClassification,
    LifecycleFeatures,
    LifecycleStage,
    LifecycleSummary,
    RecommendedAction,
)
from schemas.sku import ProductAttributes, SKU
from schemas.store import Store
from schemas.transactions import (
    DailyInventory,
    DailySales,
    PurchaseOrder,
    PurchaseOrderLine,
    Receipt,
    Transfer,
)
from schemas.vendor import Vendor

__all__ = [
    # Base
    "TimestampMixin",
    "StoreType",
    "StoreFormat",
    "ProductCategory",
    "FulfillmentType",
    "OrderStatus",
    # Domain models
    "SKU",
    "ProductAttributes",
    "Store",
    "Vendor",
    # Transactions
    "DailySales",
    "DailyInventory",
    "Receipt",
    "Transfer",
    "PurchaseOrder",
    "PurchaseOrderLine",
    # Customer signals
    "StoreTrial",
    "EyeTest",
    "StoreTraffic",
    "PricingPromotion",
    # Lifecycle
    "LifecycleStage",
    "RecommendedAction",
    "LifecycleFeatures",
    "LifecycleClassification",
    "LifecycleSummary",
]
