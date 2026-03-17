"""Base schema definitions."""

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict


class TimestampMixin(BaseModel):
    created_at: datetime | None = None
    updated_at: datetime | None = None


class StoreType(str, Enum):
    FRANCHISE = "franchise"
    COMPANY_OWNED = "company_owned"
    KIOSK = "kiosk"


class StoreFormat(str, Enum):
    LARGE = "large"
    MEDIUM = "medium"
    SMALL = "small"
    KIOSK = "kiosk"


class ProductCategory(str, Enum):
    EYEGLASSES = "eyeglasses"
    SUNGLASSES = "sunglasses"
    CONTACT_LENSES = "contact_lenses"
    ACCESSORIES = "accessories"


class FulfillmentType(str, Enum):
    """How the product reaches the customer."""
    DIRECT_SELL = "direct_sell"  # Sold from store stock (sunglasses, last-piece)
    ORDER_CAPTURE = "order_capture"  # Dummy display, prescription fulfillment


class OrderStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    IN_TRANSIT = "in_transit"
    RECEIVED = "received"
    CANCELLED = "cancelled"
