"""Generate synthetic datasets for Lenskart Retail Intelligence Platform.

Creates realistic data for local development and testing:
- 50 stores across Indian cities, assigned to 6 clusters
- 1000 SKUs: eyeglasses (dummy display + last-piece), sunglasses, contact lenses
- 5 vendors with varying lead times and reliability
- 365 days of transactional history (2024-01-01 to 2024-12-30)

Data includes:
- Seasonality (festive seasons, weekends, summer for sunglasses)
- Promotions (BOGO, clearance, seasonal)
- Store clusters with distinct demand profiles
- Dummy frames (display-only, order capture) vs physical-sell SKUs
- Trial events as display interest signals
- Eye test data as prescription order proxies
- Inter-store transfers and purchase orders
- Store traffic with footfall patterns
"""

import csv
import math
import os
import random
from datetime import date, timedelta

random.seed(42)

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

# ─── Constants ───────────────────────────────────────────────────────────────

NUM_STORES = 50
NUM_SKUS = 1000
NUM_VENDORS = 5
NUM_DAYS = 365
START_DATE = date(2024, 1, 1)

CITIES = [
    ("Mumbai", "Maharashtra", "West", 19.076, 72.877),
    ("Delhi", "Delhi", "North", 28.704, 77.102),
    ("Bangalore", "Karnataka", "South", 12.971, 77.594),
    ("Hyderabad", "Telangana", "South", 17.385, 78.486),
    ("Chennai", "Tamil Nadu", "South", 13.082, 80.270),
    ("Kolkata", "West Bengal", "East", 22.572, 88.363),
    ("Pune", "Maharashtra", "West", 18.520, 73.856),
    ("Ahmedabad", "Gujarat", "West", 23.022, 72.571),
    ("Jaipur", "Rajasthan", "North", 26.912, 75.787),
    ("Lucknow", "Uttar Pradesh", "North", 26.846, 80.946),
    ("Chandigarh", "Punjab", "North", 30.733, 76.779),
    ("Kochi", "Kerala", "South", 9.931, 76.267),
    ("Indore", "Madhya Pradesh", "Central", 22.719, 75.857),
    ("Nagpur", "Maharashtra", "Central", 21.145, 79.088),
    ("Coimbatore", "Tamil Nadu", "South", 11.016, 76.955),
]

BRANDS = ["Lenskart Air", "Lenskart Blu", "Vincent Chase", "John Jacobs", "Hooper", "Aqua", "Hustlr"]

FRAME_SHAPES = ["rectangle", "round", "aviator", "cat_eye", "wayfarer", "square", "clubmaster", "geometric"]
FRAME_MATERIALS = ["metal", "acetate", "TR90", "titanium", "mixed"]
FRAME_COLORS = ["black", "brown", "blue", "gold", "silver", "tortoise", "gunmetal", "transparent", "red", "green"]
LENS_TYPES = ["clear", "blue_cut", "photochromic", "polarized", "tinted", "progressive", "bifocal"]
SIZES = ["S", "M", "L"]
GENDERS = ["M", "F", "Unisex"]

# Store clusters define demand profiles
STORE_CLUSTERS = {
    "METRO_HIGH": {"base_traffic": 200, "conversion": 0.12, "sunglass_affinity": 0.35, "premium_affinity": 0.40},
    "METRO_MID": {"base_traffic": 120, "conversion": 0.10, "sunglass_affinity": 0.25, "premium_affinity": 0.25},
    "TIER1_HIGH": {"base_traffic": 100, "conversion": 0.11, "sunglass_affinity": 0.20, "premium_affinity": 0.20},
    "TIER1_MID": {"base_traffic": 70, "conversion": 0.09, "sunglass_affinity": 0.15, "premium_affinity": 0.15},
    "TIER2": {"base_traffic": 50, "conversion": 0.08, "sunglass_affinity": 0.10, "premium_affinity": 0.10},
    "KIOSK": {"base_traffic": 30, "conversion": 0.06, "sunglass_affinity": 0.20, "premium_affinity": 0.05},
}

# Festive / seasonal calendar for India
FESTIVE_PERIODS = [
    (date(2024, 1, 14), date(2024, 1, 16), 1.3, "makar_sankranti"),
    (date(2024, 3, 25), date(2024, 3, 28), 1.2, "holi"),
    (date(2024, 4, 10), date(2024, 4, 14), 1.4, "new_year_sales"),
    (date(2024, 8, 1), date(2024, 8, 15), 1.5, "independence_day_sale"),
    (date(2024, 10, 1), date(2024, 10, 15), 1.8, "navratri_dussehra"),
    (date(2024, 10, 25), date(2024, 11, 5), 2.0, "diwali"),
    (date(2024, 11, 20), date(2024, 11, 30), 1.6, "black_friday"),
    (date(2024, 12, 20), date(2024, 12, 31), 1.4, "year_end_sale"),
]


# ─── Helpers ─────────────────────────────────────────────────────────────────

def seasonal_multiplier(d: date) -> tuple[float, str | None]:
    """Return (multiplier, promo_name) for a given date."""
    for start, end, mult, name in FESTIVE_PERIODS:
        if start <= d <= end:
            return mult, name
    return 1.0, None


def sunglasses_seasonality(d: date) -> float:
    """Sunglasses peak in summer (March-June) in India."""
    month = d.month
    if month in (3, 4, 5, 6):
        return 1.5 + 0.3 * math.sin(math.pi * (month - 3) / 3)
    if month in (10, 11):  # festive gifting
        return 1.2
    return 0.7


def weekend_multiplier(d: date) -> float:
    """Weekends have higher traffic."""
    dow = d.weekday()
    if dow == 6:  # Sunday
        return 1.4
    if dow == 5:  # Saturday
        return 1.3
    return 1.0


# ─── Generators ──────────────────────────────────────────────────────────────

def generate_stores() -> list[dict]:
    stores = []
    cluster_names = list(STORE_CLUSTERS.keys())

    for i in range(1, NUM_STORES + 1):
        city, state, region, base_lat, base_lng = random.choice(CITIES)
        # Assign cluster based on city tier and store index
        if region in ("West", "South") and i % 5 < 2:
            cluster = "METRO_HIGH"
        elif region in ("North",) and i % 5 < 2:
            cluster = "METRO_MID"
        elif i % 7 == 0:
            cluster = "KIOSK"
        else:
            cluster = random.choice(["TIER1_HIGH", "TIER1_MID", "TIER2"])

        store_format = {"METRO_HIGH": "large", "METRO_MID": "large", "TIER1_HIGH": "medium",
                        "TIER1_MID": "medium", "TIER2": "small", "KIOSK": "kiosk"}[cluster]

        stores.append({
            "store_id": f"STR{i:04d}",
            "store_name": f"Lenskart {city} {i}",
            "city": city,
            "state": state,
            "region": region,
            "pincode": f"{random.randint(100000, 999999)}",
            "store_type": "company_owned" if i % 3 != 0 else "franchise",
            "store_format": store_format,
            "store_cluster": cluster,
            "latitude": round(base_lat + random.uniform(-0.05, 0.05), 6),
            "longitude": round(base_lng + random.uniform(-0.05, 0.05), 6),
            "opening_date": (START_DATE - timedelta(days=random.randint(90, 1800))).isoformat(),
            "is_active": True,
            "display_capacity": {"large": 200, "medium": 150, "small": 100, "kiosk": 50}[store_format],
            "storage_capacity": {"large": 600, "medium": 400, "small": 200, "kiosk": 80}[store_format],
        })
    return stores


def generate_vendors() -> list[dict]:
    vendor_specs = [
        ("VND001", "Luxottica India", "manufacturer", 10, 50000, 100, 0.92),
        ("VND002", "Titan Eyewear", "manufacturer", 7, 25000, 50, 0.95),
        ("VND003", "Safilo Distribution", "distributor", 5, 15000, 25, 0.88),
        ("VND004", "Shenzhen Optics Co", "manufacturer", 21, 100000, 500, 0.78),
        ("VND005", "Local Lens Crafters", "manufacturer", 3, 5000, 10, 0.96),
    ]
    vendors = []
    for vid, name, vtype, lt, mov, moq, reliability in vendor_specs:
        vendors.append({
            "vendor_id": vid,
            "vendor_name": name,
            "vendor_type": vtype,
            "contact_email": f"{vid.lower()}@example.com",
            "contact_phone": f"98{random.randint(10000000, 99999999)}",
            "city": random.choice(CITIES)[0],
            "state": random.choice(CITIES)[1],
            "avg_lead_time_days": lt,
            "min_order_value": mov,
            "min_order_qty": moq,
            "reliability_score": reliability,
            "is_active": True,
        })
    return vendors


def generate_skus(vendors: list[dict]) -> list[dict]:
    skus = []
    vendor_ids = [v["vendor_id"] for v in vendors]

    for i in range(1, NUM_SKUS + 1):
        # Distribution: 60% eyeglasses, 25% sunglasses, 15% contact lenses
        r = random.random()
        if r < 0.60:
            category = "eyeglasses"
            # 70% of eyeglasses are dummy display frames (order capture)
            # 30% are physical sell (last piece / ready stock)
            if random.random() < 0.70:
                sku_type = "display_dummy"
                fulfillment_type = "order_capture"
                is_display_only = True
            else:
                sku_type = "physical_sell"
                fulfillment_type = "direct_sell"
                is_display_only = False
            sales_channel = "prescription"
        elif r < 0.85:
            category = "sunglasses"
            sku_type = "physical_sell"
            fulfillment_type = "direct_sell"
            is_display_only = False
            sales_channel = "walk_in"
        else:
            category = "contact_lenses"
            sku_type = "physical_sell"
            fulfillment_type = "direct_sell"
            is_display_only = False
            sales_channel = "prescription"

        brand = random.choice(BRANDS)
        mrp = random.choice([499, 799, 999, 1299, 1599, 1999, 2499, 2999, 3999, 4999, 5999, 7999])
        lifecycle = random.choices(["new", "active", "aging", "eol"], weights=[0.10, 0.55, 0.25, 0.10])[0]

        skus.append({
            "sku_id": f"SKU{i:05d}",
            "product_name": f"{brand} {random.choice(FRAME_SHAPES).title()} {random.choice(FRAME_COLORS).title()} {i}",
            "brand": brand,
            "category": category,
            "subcategory": f"{category}_premium" if mrp >= 2999 else f"{category}_value",
            "sku_type": sku_type,
            "gender": random.choice(GENDERS),
            "frame_type": random.choice(["full_rim", "half_rim", "rimless"]) if category != "contact_lenses" else None,
            "frame_shape": random.choice(FRAME_SHAPES) if category != "contact_lenses" else None,
            "frame_material": random.choice(FRAME_MATERIALS) if category != "contact_lenses" else None,
            "frame_color": random.choice(FRAME_COLORS) if category != "contact_lenses" else None,
            "lens_type": random.choice(LENS_TYPES),
            "size": random.choice(SIZES),
            "mrp": mrp,
            "cost_price": round(mrp * random.uniform(0.25, 0.45), 2),
            "fulfillment_type": fulfillment_type,
            "sales_channel": sales_channel,
            "is_display_only": is_display_only,
            "lifecycle_stage": lifecycle,
            "vendor_id": random.choice(vendor_ids),
            "lead_time_days": random.choice([3, 5, 7, 10, 14, 21]),
            "launch_date": (START_DATE - timedelta(days=random.randint(0, 730))).isoformat(),
        })
    return skus


def generate_calendar() -> list[dict]:
    """Generate a calendar dimension for 365 days."""
    rows = []
    for d_offset in range(NUM_DAYS):
        d = START_DATE + timedelta(days=d_offset)
        season_mult, promo = seasonal_multiplier(d)
        rows.append({
            "date_key": d.isoformat(),
            "year": d.year,
            "quarter": (d.month - 1) // 3 + 1,
            "month": d.month,
            "month_name": d.strftime("%B"),
            "week_of_year": d.isocalendar()[1],
            "day_of_week": d.weekday(),
            "day_name": d.strftime("%A"),
            "is_weekend": d.weekday() >= 5,
            "is_festive": promo is not None,
            "festive_event": promo or "",
            "season": "summer" if d.month in (3, 4, 5, 6) else "monsoon" if d.month in (7, 8, 9) else "winter" if d.month in (11, 12, 1, 2) else "autumn",
        })
    return rows


def generate_daily_sales(stores: list[dict], skus: list[dict]) -> list[dict]:
    """Generate 365 days of daily sales with seasonality and promotions."""
    rows = []
    # Pre-compute sku lookup by category
    eyeglass_skus = [s for s in skus if s["category"] == "eyeglasses" and not s["is_display_only"]]
    sunglass_skus = [s for s in skus if s["category"] == "sunglasses"]
    cl_skus = [s for s in skus if s["category"] == "contact_lenses"]
    display_skus = [s for s in skus if s["is_display_only"]]

    for d_offset in range(NUM_DAYS):
        d = START_DATE + timedelta(days=d_offset)
        season_mult, promo = seasonal_multiplier(d)
        wknd_mult = weekend_multiplier(d)
        sun_mult = sunglasses_seasonality(d)

        for store in stores:
            cluster = STORE_CLUSTERS[store["store_cluster"]]
            store_base = cluster["conversion"] * cluster["base_traffic"]

            # Eyeglasses (prescription sell-through from physical stock)
            n_eye = max(1, int(store_base * 0.5 * season_mult * wknd_mult * random.uniform(0.5, 1.5)))
            for sku in random.sample(eyeglass_skus, min(n_eye, len(eyeglass_skus))):
                qty = random.choices([1, 2], weights=[0.85, 0.15])[0]
                discount_pct = 0.15 if promo else random.choice([0, 0, 0, 0.05, 0.10])
                rows.append({
                    "store_id": store["store_id"],
                    "sku_id": sku["sku_id"],
                    "sale_date": d.isoformat(),
                    "qty_sold": qty,
                    "revenue": round(sku["mrp"] * qty * (1 - discount_pct), 2),
                    "discount": round(sku["mrp"] * qty * discount_pct, 2),
                    "fulfillment_type": sku["fulfillment_type"],
                    "sales_channel": sku["sales_channel"],
                    "is_return": random.random() < 0.02,
                })

            # Sunglasses
            n_sun = max(0, int(store_base * cluster["sunglass_affinity"] * sun_mult * season_mult * wknd_mult * random.uniform(0.3, 1.5)))
            for sku in random.sample(sunglass_skus, min(n_sun, len(sunglass_skus))):
                qty = random.choices([1, 2], weights=[0.9, 0.1])[0]
                discount_pct = 0.20 if promo else random.choice([0, 0, 0.05, 0.10])
                rows.append({
                    "store_id": store["store_id"],
                    "sku_id": sku["sku_id"],
                    "sale_date": d.isoformat(),
                    "qty_sold": qty,
                    "revenue": round(sku["mrp"] * qty * (1 - discount_pct), 2),
                    "discount": round(sku["mrp"] * qty * discount_pct, 2),
                    "fulfillment_type": "direct_sell",
                    "sales_channel": "walk_in",
                    "is_return": random.random() < 0.04,
                })

            # Contact lenses (small but steady)
            n_cl = max(0, int(store_base * 0.1 * season_mult * random.uniform(0.5, 1.5)))
            for sku in random.sample(cl_skus, min(n_cl, len(cl_skus))):
                qty = random.choices([1, 2, 3], weights=[0.5, 0.35, 0.15])[0]
                rows.append({
                    "store_id": store["store_id"],
                    "sku_id": sku["sku_id"],
                    "sale_date": d.isoformat(),
                    "qty_sold": qty,
                    "revenue": round(sku["mrp"] * qty, 2),
                    "discount": 0.0,
                    "fulfillment_type": "direct_sell",
                    "sales_channel": "prescription",
                    "is_return": False,
                })

            # Display dummy frames generating orders (order_capture sales)
            n_display_orders = max(0, int(store_base * 0.3 * season_mult * wknd_mult * random.uniform(0.4, 1.2)))
            for sku in random.sample(display_skus, min(n_display_orders, len(display_skus))):
                rows.append({
                    "store_id": store["store_id"],
                    "sku_id": sku["sku_id"],
                    "sale_date": d.isoformat(),
                    "qty_sold": 1,
                    "revenue": round(sku["mrp"] * random.uniform(0.85, 1.0), 2),
                    "discount": round(sku["mrp"] * random.uniform(0, 0.15), 2),
                    "fulfillment_type": "order_capture",
                    "sales_channel": "prescription",
                    "is_return": False,
                })

    return rows


def generate_daily_inventory(stores: list[dict], skus: list[dict]) -> list[dict]:
    """Generate daily inventory snapshots for all 365 days.

    Inventory for physical-sell SKUs fluctuates based on sales and receipts.
    Display-only SKUs maintain constant on_display_qty.
    """
    rows = []
    physical_skus = [s for s in skus if not s["is_display_only"]]
    display_skus = [s for s in skus if s["is_display_only"]]

    for store in stores:
        cap = store["display_capacity"]
        # Each store carries a subset of SKUs
        store_physical = random.sample(physical_skus, min(random.randint(150, 350), len(physical_skus)))
        store_display = random.sample(display_skus, min(cap, len(display_skus)))

        # Initialize inventory levels
        inv_levels = {}
        for sku in store_physical:
            inv_levels[sku["sku_id"]] = random.randint(2, 25)
        for sku in store_display:
            inv_levels[sku["sku_id"]] = random.randint(1, 3)  # Display units

        for d_offset in range(NUM_DAYS):
            d = START_DATE + timedelta(days=d_offset)
            # Only emit every 7th day to keep data manageable, plus last 30 days daily
            if d_offset % 7 != 0 and d_offset < (NUM_DAYS - 30):
                # Still update levels
                for sid in inv_levels:
                    inv_levels[sid] = max(0, inv_levels[sid] + random.randint(-2, 1))
                    if inv_levels[sid] == 0 and random.random() < 0.3:
                        inv_levels[sid] = random.randint(5, 15)  # Replenishment
                continue

            for sku in store_physical:
                on_hand = max(0, inv_levels.get(sku["sku_id"], 0))
                on_display = min(on_hand, random.randint(0, 3))
                in_transit = random.randint(0, 5) if on_hand < 5 else 0
                rows.append({
                    "store_id": store["store_id"],
                    "sku_id": sku["sku_id"],
                    "snapshot_date": d.isoformat(),
                    "on_hand_qty": on_hand,
                    "on_display_qty": on_display,
                    "in_storage_qty": on_hand - on_display,
                    "in_transit_qty": in_transit,
                    "allocated_qty": random.randint(0, min(2, on_hand)),
                    "available_qty": max(0, on_hand - random.randint(0, 2)),
                })

            for sku in store_display:
                # Display dummies: always 1-2 on display
                on_display = random.randint(1, 2)
                rows.append({
                    "store_id": store["store_id"],
                    "sku_id": sku["sku_id"],
                    "snapshot_date": d.isoformat(),
                    "on_hand_qty": on_display,
                    "on_display_qty": on_display,
                    "in_storage_qty": 0,
                    "in_transit_qty": 0,
                    "allocated_qty": 0,
                    "available_qty": 0,  # Display-only, not for sale
                })

            # Drift inventory levels for next snapshot
            for sid in inv_levels:
                inv_levels[sid] = max(0, inv_levels[sid] + random.randint(-2, 1))
                if inv_levels[sid] == 0 and random.random() < 0.3:
                    inv_levels[sid] = random.randint(5, 15)

    return rows


def generate_receipts(stores: list[dict], skus: list[dict]) -> list[dict]:
    """Generate goods receipts from vendors and warehouses."""
    rows = []
    receipt_id = 0
    physical_skus = [s for s in skus if not s["is_display_only"]]

    for d_offset in range(0, NUM_DAYS, 3):  # Receipts every ~3 days
        d = START_DATE + timedelta(days=d_offset)
        for store in stores:
            # 3-8 receipts per store per cycle
            n_receipts = random.randint(3, 8)
            for _ in range(n_receipts):
                receipt_id += 1
                sku = random.choice(physical_skus)
                rows.append({
                    "receipt_id": f"RCP{receipt_id:08d}",
                    "store_id": store["store_id"],
                    "sku_id": sku["sku_id"],
                    "receipt_date": d.isoformat(),
                    "qty_received": random.randint(2, 20),
                    "source_type": random.choices(["warehouse", "vendor_direct", "transfer"], weights=[0.6, 0.25, 0.15])[0],
                    "source_id": random.choice(["WH_NORTH", "WH_SOUTH", "WH_WEST", "WH_EAST"]),
                    "po_id": f"PO{random.randint(1, 5000):06d}" if random.random() < 0.7 else "",
                })
    return rows


def generate_store_trials(stores: list[dict], skus: list[dict]) -> list[dict]:
    """Generate try-on events for display/eyeglasses SKUs.

    These are the primary 'display_interest_signal' — customers trying frames
    without necessarily buying. High trial counts indicate demand for that frame style.
    """
    display_skus = [s for s in skus if s["is_display_only"]]
    rows = []
    trial_id = 0

    for d_offset in range(NUM_DAYS):
        d = START_DATE + timedelta(days=d_offset)
        season_mult, _ = seasonal_multiplier(d)
        wknd_mult = weekend_multiplier(d)

        for store in stores:
            cluster = STORE_CLUSTERS[store["store_cluster"]]
            n_trials = max(1, int(cluster["base_traffic"] * 0.3 * season_mult * wknd_mult * random.uniform(0.5, 1.5)))

            for _ in range(n_trials):
                trial_id += 1
                sku = random.choice(display_skus)
                conversion = random.random() < cluster["conversion"]
                rows.append({
                    "trial_id": f"TRL{trial_id:08d}",
                    "store_id": store["store_id"],
                    "sku_id": sku["sku_id"],
                    "trial_date": d.isoformat(),
                    "trial_timestamp": f"{d.isoformat()} {random.randint(10, 20)}:{random.randint(0, 59):02d}:00",
                    "customer_id": f"CUST{random.randint(1, 100000):06d}" if random.random() < 0.5 else "",
                    "resulted_in_order": conversion,
                    "order_id": f"ORD{random.randint(1, 999999):07d}" if conversion else "",
                })
    return rows


def generate_eye_tests(stores: list[dict]) -> list[dict]:
    """Generate eye test / prescription data.

    Eye tests are a 'prescription_order_signal' — they almost always lead to
    an eyeglass order. Stores with more eye tests should get more display frames.
    """
    rows = []
    test_id = 0

    for d_offset in range(NUM_DAYS):
        d = START_DATE + timedelta(days=d_offset)
        season_mult, _ = seasonal_multiplier(d)
        wknd_mult = weekend_multiplier(d)

        for store in stores:
            cluster = STORE_CLUSTERS[store["store_cluster"]]
            # Eye tests: subset of footfall
            n_tests = max(0, int(cluster["base_traffic"] * 0.08 * season_mult * wknd_mult * random.uniform(0.5, 1.5)))

            for _ in range(n_tests):
                test_id += 1
                resulted_in_purchase = random.random() < 0.75  # 75% convert
                rows.append({
                    "test_id": f"EYE{test_id:08d}",
                    "store_id": store["store_id"],
                    "test_date": d.isoformat(),
                    "customer_id": f"CUST{random.randint(1, 100000):06d}",
                    "sph_right": round(random.uniform(-6.0, 4.0), 2),
                    "cyl_right": round(random.uniform(-3.0, 0.0), 2),
                    "sph_left": round(random.uniform(-6.0, 4.0), 2),
                    "cyl_left": round(random.uniform(-3.0, 0.0), 2),
                    "resulted_in_purchase": resulted_in_purchase,
                    "order_id": f"ORD{random.randint(1, 999999):07d}" if resulted_in_purchase else "",
                })
    return rows


def generate_transfers(stores: list[dict], skus: list[dict]) -> list[dict]:
    """Generate inter-store transfers.

    Transfers happen for: rebalancing, stockout prevention, EOL clearance.
    transfer_out at source must eventually balance transfer_in at destination.
    """
    rows = []
    transfer_id = 0
    physical_skus = [s for s in skus if not s["is_display_only"]]

    for d_offset in range(0, NUM_DAYS, 7):  # Weekly transfer batches
        d = START_DATE + timedelta(days=d_offset)
        # 5-15 transfers per week across the network
        n_transfers = random.randint(5, 15)
        for _ in range(n_transfers):
            transfer_id += 1
            from_store, to_store = random.sample(stores, 2)
            sku = random.choice(physical_skus)
            qty = random.randint(1, 10)
            reason = random.choices(["rebalance", "stockout_prevention", "eol_clearance"], weights=[0.5, 0.35, 0.15])[0]

            # Transfer has two rows: out from source, in to destination
            initiated = d
            completed = d + timedelta(days=random.randint(1, 5))
            status = "received" if completed <= START_DATE + timedelta(days=NUM_DAYS - 1) else "in_transit"

            tid = f"TRF{transfer_id:06d}"
            rows.append({
                "transfer_id": tid,
                "from_store_id": from_store["store_id"],
                "to_store_id": to_store["store_id"],
                "sku_id": sku["sku_id"],
                "transfer_qty": qty,
                "transfer_direction": "out",
                "status": status,
                "initiated_date": initiated.isoformat(),
                "completed_date": completed.isoformat() if status == "received" else "",
                "reason": reason,
            })
            rows.append({
                "transfer_id": tid,
                "from_store_id": from_store["store_id"],
                "to_store_id": to_store["store_id"],
                "sku_id": sku["sku_id"],
                "transfer_qty": qty,
                "transfer_direction": "in",
                "status": status,
                "initiated_date": initiated.isoformat(),
                "completed_date": completed.isoformat() if status == "received" else "",
                "reason": reason,
            })
    return rows


def generate_purchase_orders(vendors: list[dict], skus: list[dict]) -> list[dict]:
    """Generate purchase orders to vendors."""
    rows = []
    po_id = 0

    for d_offset in range(0, NUM_DAYS, 14):  # POs every 2 weeks
        d = START_DATE + timedelta(days=d_offset)
        for vendor in vendors:
            po_id += 1
            vendor_skus = [s for s in skus if s["vendor_id"] == vendor["vendor_id"] and not s["is_display_only"]]
            if not vendor_skus:
                continue

            n_lines = random.randint(5, 20)
            order_skus = random.sample(vendor_skus, min(n_lines, len(vendor_skus)))
            lead_time = vendor["avg_lead_time_days"]
            expected_delivery = d + timedelta(days=lead_time)
            # Sometimes delivered late
            actual_delivery = expected_delivery + timedelta(days=random.randint(-1, 5))
            if actual_delivery > START_DATE + timedelta(days=NUM_DAYS):
                status = "in_transit"
                actual_delivery_str = ""
            else:
                status = "received"
                actual_delivery_str = actual_delivery.isoformat()

            total_qty = 0
            total_value = 0.0
            for sku in order_skus:
                min_qty = vendor["min_order_qty"] // len(order_skus) + 1
                qty = random.randint(min(min_qty, 50), max(min_qty, 50))
                total_qty += qty
                total_value += qty * sku["cost_price"]

            rows.append({
                "po_id": f"PO{po_id:06d}",
                "vendor_id": vendor["vendor_id"],
                "status": status,
                "order_date": d.isoformat(),
                "expected_delivery_date": expected_delivery.isoformat(),
                "actual_delivery_date": actual_delivery_str,
                "total_qty": total_qty,
                "total_value": round(total_value, 2),
                "num_lines": len(order_skus),
            })
    return rows


def generate_store_traffic(stores: list[dict]) -> list[dict]:
    """Generate daily store traffic with realistic patterns."""
    rows = []
    for d_offset in range(NUM_DAYS):
        d = START_DATE + timedelta(days=d_offset)
        season_mult, _ = seasonal_multiplier(d)
        wknd_mult = weekend_multiplier(d)

        for store in stores:
            cluster = STORE_CLUSTERS[store["store_cluster"]]
            base = cluster["base_traffic"]
            footfall = max(1, int(base * season_mult * wknd_mult * random.uniform(0.6, 1.4)))
            walk_ins = int(footfall * random.uniform(0.65, 0.85))
            appointments = int(footfall * random.uniform(0.05, 0.15))
            rows.append({
                "store_id": store["store_id"],
                "traffic_date": d.isoformat(),
                "footfall_count": footfall,
                "walk_ins": walk_ins,
                "appointments": appointments,
            })
    return rows


def generate_promotions(skus: list[dict]) -> list[dict]:
    """Generate promotional events aligned with festive calendar."""
    rows = []
    promo_id = 0
    for start, end, mult, name in FESTIVE_PERIODS:
        # Store-wide promos
        promo_id += 1
        rows.append({
            "promo_id": f"PROMO{promo_id:04d}",
            "sku_id": "",
            "store_id": "",
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "promo_type": "seasonal_sale",
            "promo_name": name,
            "discount_pct": round((mult - 1) * 0.5, 2),  # e.g., 2.0 mult -> 50% of uplift as discount
            "discount_value": 0.0,
            "is_active": True,
        })

    # SKU-specific clearance promos for EOL items
    eol_skus = [s for s in skus if s["lifecycle_stage"] == "eol"]
    for sku in random.sample(eol_skus, min(30, len(eol_skus))):
        promo_id += 1
        start = START_DATE + timedelta(days=random.randint(180, 330))
        rows.append({
            "promo_id": f"PROMO{promo_id:04d}",
            "sku_id": sku["sku_id"],
            "store_id": "",
            "start_date": start.isoformat(),
            "end_date": (start + timedelta(days=random.randint(14, 45))).isoformat(),
            "promo_type": "clearance",
            "promo_name": f"clearance_{sku['sku_id']}",
            "discount_pct": random.choice([0.20, 0.30, 0.40, 0.50]),
            "discount_value": 0.0,
            "is_active": True,
        })
    return rows


# ─── Writer ──────────────────────────────────────────────────────────────────

def write_csv(filename: str, rows: list[dict], fieldnames: list[str] | None = None):
    if not rows:
        print(f"  SKIPPED {filename} (no rows)")
        return
    if fieldnames is None:
        fieldnames = list(rows[0].keys())
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  {len(rows):>12,} rows -> {filename}")


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Lenskart Retail Intelligence - Synthetic Data Generator")
    print("=" * 60)
    print(f"  Stores:  {NUM_STORES}")
    print(f"  SKUs:    {NUM_SKUS}")
    print(f"  Vendors: {NUM_VENDORS}")
    print(f"  Days:    {NUM_DAYS} ({START_DATE} to {START_DATE + timedelta(days=NUM_DAYS - 1)})")
    print()

    print("[1/11] Generating stores...")
    stores = generate_stores()
    write_csv("stores.csv", stores)

    print("[2/11] Generating vendors...")
    vendors = generate_vendors()
    write_csv("vendors.csv", vendors)

    print("[3/11] Generating SKUs...")
    skus = generate_skus(vendors)
    write_csv("skus.csv", skus)

    print("[4/11] Generating calendar...")
    calendar = generate_calendar()
    write_csv("calendar.csv", calendar)

    print("[5/11] Generating daily sales (this takes a moment)...")
    sales = generate_daily_sales(stores, skus)
    write_csv("daily_sales.csv", sales)

    print("[6/11] Generating inventory snapshots...")
    inventory = generate_daily_inventory(stores, skus)
    write_csv("daily_inventory.csv", inventory)

    print("[7/11] Generating receipts...")
    receipts = generate_receipts(stores, skus)
    write_csv("receipts.csv", receipts)

    print("[8/11] Generating store trials...")
    trials = generate_store_trials(stores, skus)
    write_csv("store_trials.csv", trials)

    print("[9/11] Generating eye tests...")
    eye_tests = generate_eye_tests(stores)
    write_csv("eye_tests.csv", eye_tests)

    print("[10/11] Generating transfers...")
    transfers = generate_transfers(stores, skus)
    write_csv("transfers.csv", transfers)

    print("[11/11] Generating purchase orders, traffic, promotions...")
    pos = generate_purchase_orders(vendors, skus)
    write_csv("purchase_orders.csv", pos)
    traffic = generate_store_traffic(stores)
    write_csv("store_traffic.csv", traffic)
    promos = generate_promotions(skus)
    write_csv("promotions.csv", promos)

    print()
    print("Done! Files written to:", OUTPUT_DIR)
    print()
    print("To load into DuckDB for dbt:")
    print("  make generate-data")
    print("  make dbt-seed   # or: make dbt-run")


if __name__ == "__main__":
    main()
