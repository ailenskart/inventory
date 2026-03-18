"""Assortment Optimization Engine v1.

Selects the best SKU assortment per store to maximize expected
sales/conversion under display capacity and assortment policy constraints.

Lenskart-specific:
- Dummy display frames for try-on (order-capture)
- Sunglasses / last-piece eyeglasses as direct sell-through
- Display slots are scarce → optimize allocation
- Freshness and new-launch exposure matter
- Store clusters have differentiated strategies
- Width vs depth tradeoff by cluster and category

Solver: OR-Tools CP-SAT (constraint programming)
"""
