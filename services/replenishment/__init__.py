"""Replenishment Engine v1.

Generates daily store replenishment recommendations that maximize
availability while minimizing overstock.

Supports:
- Display dummy inventory (maintain display wall coverage)
- Direct store sell-through inventory (forecast-driven reorder)
- Prescription fulfillment components (order-capture pipeline)

Pull-based, forecast-driven replenishment using:
- Reorder point / safety stock / order-up-to level
- Service-level targets per store cluster
- Lead time, MOQ, and case pack constraints
- Store capacity limits
- Emergency replenishment flags
"""
