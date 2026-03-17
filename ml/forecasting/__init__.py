"""Demand Intelligence Engine v1.

Forecasting at SKU × Store × Week granularity using StatsForecast and
HierarchicalForecast. Supports three demand signals:
- sell_through_signal (physical sales)
- prescription_order_signal (eye-test driven orders)
- display_interest_signal (try-on / display engagement)

Hierarchy: Total → Region → Store Cluster → Store → SKU Category → SKU
"""
