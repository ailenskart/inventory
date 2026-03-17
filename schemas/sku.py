"""SKU and product attribute schemas."""

from pydantic import BaseModel

from schemas.base import FulfillmentType, ProductCategory, TimestampMixin


class SKU(TimestampMixin):
    sku_id: str
    product_name: str
    brand: str
    category: ProductCategory
    subcategory: str | None = None
    gender: str | None = None  # M, F, Unisex
    frame_type: str | None = None  # Full-rim, Half-rim, Rimless
    frame_shape: str | None = None  # Round, Rectangle, Aviator, etc.
    frame_material: str | None = None  # Metal, Acetate, TR90, etc.
    frame_color: str | None = None
    lens_type: str | None = None
    size: str | None = None  # S, M, L or bridge-lens-temple
    mrp: float = 0.0
    cost_price: float = 0.0
    fulfillment_type: FulfillmentType = FulfillmentType.ORDER_CAPTURE
    is_display_only: bool = False  # True for dummy frames
    lifecycle_stage: str = "active"  # new, active, aging, eol
    vendor_id: str | None = None
    lead_time_days: int = 7


class ProductAttributes(BaseModel):
    sku_id: str
    attribute_name: str
    attribute_value: str
