"""Transaction schemas: sales, inventory, receipts, transfers, POs."""

from datetime import date, datetime

from pydantic import BaseModel

from schemas.base import FulfillmentType, OrderStatus, TimestampMixin


class DailySales(BaseModel):
    store_id: str
    sku_id: str
    sale_date: date
    qty_sold: int = 0
    revenue: float = 0.0
    discount: float = 0.0
    fulfillment_type: FulfillmentType = FulfillmentType.DIRECT_SELL
    is_return: bool = False


class DailyInventory(BaseModel):
    store_id: str
    sku_id: str
    snapshot_date: date
    on_hand_qty: int = 0
    on_display_qty: int = 0  # Items currently on display wall
    in_storage_qty: int = 0  # Items in back storage
    in_transit_qty: int = 0
    allocated_qty: int = 0  # Reserved for orders
    available_qty: int = 0


class Receipt(TimestampMixin):
    receipt_id: str
    store_id: str
    sku_id: str
    receipt_date: date
    qty_received: int = 0
    source_type: str = "warehouse"  # warehouse, vendor_direct, transfer
    source_id: str | None = None  # warehouse_id or store_id
    po_id: str | None = None


class Transfer(TimestampMixin):
    transfer_id: str
    from_store_id: str
    to_store_id: str
    sku_id: str
    qty: int = 0
    status: OrderStatus = OrderStatus.DRAFT
    initiated_date: date | None = None
    completed_date: date | None = None
    reason: str | None = None  # rebalance, stockout_prevention, eol_clearance


class PurchaseOrder(TimestampMixin):
    po_id: str
    vendor_id: str
    status: OrderStatus = OrderStatus.DRAFT
    order_date: date | None = None
    expected_delivery_date: date | None = None
    actual_delivery_date: date | None = None
    total_qty: int = 0
    total_value: float = 0.0


class PurchaseOrderLine(BaseModel):
    po_id: str
    line_number: int
    sku_id: str
    qty_ordered: int = 0
    qty_received: int = 0
    unit_cost: float = 0.0
    destination_type: str = "warehouse"  # warehouse, store
    destination_id: str | None = None
