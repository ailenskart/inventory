"""Generate synthetic datasets for Lenskart Retail Intelligence Platform.

Creates realistic data for local development and testing:
- 50 stores across Indian cities, assigned to 6 clusters
- 1000 SKUs: eyeglasses (dummy display + last-piece), sunglasses, contact lenses
- 5 vendors with varying lead times and reliability
- 365 days of transactional history (2024-01-01 to 2024-12-30)

Set LENSKART_DATA_LITE=1 to generate a smaller dataset (10 stores, 100 SKUs, 90 days)
suitable for memory-constrained environments like Railway free tier.
"""

import csv
import math
import os
import random
from datetime import date, timedelta

random.seed(42)

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

# ─── Lite mode for constrained environments ─────────────────────────────────

LITE_MODE = os.environ.get("LENSKART_DATA_LITE", "0") == "1"

NUM_STORES = 10 if LITE_MODE else 50
NUM_SKUS = 100 if LITE_MODE else 1000
NUM_VENDORS = 5
NUM_DAYS = 90 if LITE_MODE else 365
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

# ─── Real Lenskart product data ──────────────────────────────────────────────

# In-house brands (primary revenue, ~85% of catalog)
INHOUSE_BRANDS = ["Vincent Chase", "John Jacobs", "Lenskart Air", "Lenskart Blu", "Hooper", "Hustlr", "Aqua", "Aquacolor"]
# Third-party / licensed brands
THIRDPARTY_BRANDS = ["Ray-Ban", "Oakley", "Carrera", "Tommy Hilfiger", "Lee Cooper", "New Balance", "Owndays"]
# Contact lens third-party brands
CL_BRANDS = ["Bausch & Lomb", "Acuvue", "Alcon", "CooperVision", "Aqua", "Aquacolor"]

# Brand → typical categories and price positioning
BRAND_CONFIG = {
    "Vincent Chase":   {"cats": ["eyeglasses", "sunglasses"], "prices": [499, 799, 999, 1299, 1599, 1999, 2499, 2999], "weight": 25},
    "John Jacobs":     {"cats": ["eyeglasses", "sunglasses"], "prices": [1299, 1599, 1999, 2499, 2999, 3999, 4999], "weight": 18},
    "Lenskart Air":    {"cats": ["eyeglasses"], "prices": [999, 1299, 1599, 1999, 2499, 3999], "weight": 15},
    "Lenskart Blu":    {"cats": ["computer_glasses"], "prices": [799, 999, 1299, 1599, 2499], "weight": 8},
    "Hooper":          {"cats": ["eyeglasses", "computer_glasses"], "prices": [499, 799, 999, 1299, 1999], "weight": 7},
    "Hustlr":          {"cats": ["eyeglasses", "sunglasses"], "prices": [799, 999, 1299, 1999, 2499], "weight": 5},
    "Aqua":            {"cats": ["contact_lenses"], "prices": [300, 499, 699, 899, 1199, 1499], "weight": 5},
    "Aquacolor":       {"cats": ["contact_lenses"], "prices": [500, 699, 899, 1199], "weight": 3},
    "Ray-Ban":         {"cats": ["eyeglasses", "sunglasses"], "prices": [4999, 5999, 7999, 9999, 12999], "weight": 4},
    "Oakley":          {"cats": ["sunglasses"], "prices": [5999, 7999, 9999, 14999], "weight": 2},
    "Carrera":         {"cats": ["sunglasses"], "prices": [3999, 4999, 5999, 7999], "weight": 2},
    "Tommy Hilfiger":  {"cats": ["eyeglasses"], "prices": [3999, 4999, 5999, 7999], "weight": 1},
    "Lee Cooper":      {"cats": ["eyeglasses"], "prices": [1999, 2499, 2999, 3999], "weight": 1},
    "New Balance":     {"cats": ["eyeglasses"], "prices": [2499, 2999, 3999], "weight": 1},
    "Owndays":         {"cats": ["eyeglasses", "sunglasses"], "prices": [4999, 5999, 7999, 9999], "weight": 1},
    "Bausch & Lomb":   {"cats": ["contact_lenses"], "prices": [399, 599, 899, 1299, 1599], "weight": 1},
    "Acuvue":          {"cats": ["contact_lenses"], "prices": [699, 999, 1499, 1999], "weight": 1},
    "Alcon":           {"cats": ["contact_lenses"], "prices": [599, 899, 1299, 1799], "weight": 0},
    "CooperVision":    {"cats": ["contact_lenses"], "prices": [499, 799, 1099], "weight": 0},
}

# Collections (for product naming)
COLLECTIONS = {
    "Vincent Chase": ["Air Wrap", "Poppin 2.0", "Float Pop", "Hip Hop", "Boost", "Crystal Clear"],
    "John Jacobs": ["Coastline", "Rhapsody", "Roman Holiday", "Surrealist", "Art Deco"],
    "Lenskart Air": ["Air Flex", "Air Prism", "Switch", "Ultra Light"],
    "Lenskart Blu": ["Zero Power", "Screen Guard", "Blu Cut Pro"],
    "Hooper": ["Daily Comfort", "Classic"],
    "Hustlr": ["Street", "Sport Fit"],
}

FRAME_SHAPES = ["rectangle", "round", "aviator", "cat_eye", "wayfarer", "square", "clubmaster", "geometric", "hexagonal", "oval"]
FRAME_TYPES = ["full_rim", "half_rim", "rimless"]
FRAME_MATERIALS = ["metal", "acetate", "TR90", "titanium", "stainless_steel", "ultem", "mixed"]
FRAME_COLORS = [
    "black", "brown", "blue", "gold", "silver", "tortoise", "gunmetal", "transparent",
    "red", "green", "rose_gold", "purple", "maroon", "white", "grey", "pink",
]
LENS_TYPES_EYEGLASSES = ["single_vision", "blue_cut", "photochromic", "progressive", "bifocal", "zero_power"]
LENS_TYPES_SUNGLASSES = ["polarized", "mirrored", "gradient", "tinted", "photochromic"]
LENS_TYPES_CL = ["spherical", "toric", "multifocal", "colored"]
CL_DISPOSAL = ["daily", "monthly", "yearly"]
SIZES = ["S", "M", "L", "XL"]
GENDERS = ["M", "F", "Unisex", "Kids"]

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


# ─── Streaming CSV Writer ───────────────────────────────────────────────────

class StreamingCSV:
    """Write CSV rows incrementally to avoid holding everything in memory."""

    def __init__(self, filename: str, fieldnames: list[str]):
        self.filepath = os.path.join(OUTPUT_DIR, filename)
        self.filename = filename
        self.fieldnames = fieldnames
        self.count = 0
        self._file = open(self.filepath, "w", newline="")
        self._writer = csv.DictWriter(self._file, fieldnames=fieldnames)
        self._writer.writeheader()

    def write(self, row: dict):
        self._writer.writerow(row)
        self.count += 1

    def close(self):
        self._file.close()
        print(f"  {self.count:>12,} rows -> {self.filename}")


# ─── Generators ──────────────────────────────────────────────────────────────

def generate_stores() -> list[dict]:
    stores = []
    cluster_names = list(STORE_CLUSTERS.keys())

    for i in range(1, NUM_STORES + 1):
        city, state, region, base_lat, base_lng = random.choice(CITIES)
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
        # Real Lenskart ownership: COCO (flagship) vs FOFO (franchise expansion)
        ownership = "COCO" if cluster in ("METRO_HIGH", "METRO_MID") else (
            "FOFO" if random.random() < 0.6 else "COCO"
        )

        stores.append({
            "store_id": f"STR{i:04d}",
            "store_name": f"Lenskart {city} {random.choice(['Mall', 'High Street', 'Hub', 'Express', 'Studio'])} {i}",
            "city": city,
            "state": state,
            "region": region,
            "pincode": f"{random.randint(100000, 999999)}",
            "store_type": ownership,
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
        ("VND001", "Lenskart Manufacturing (In-house)", "manufacturer", 5, 25000, 50, 0.96),
        ("VND002", "EssilorLuxottica India", "manufacturer", 10, 50000, 100, 0.92),
        ("VND003", "Titan Eyeplus", "manufacturer", 7, 25000, 50, 0.94),
        ("VND004", "Shenzhen Hongyi Optics", "manufacturer", 21, 100000, 500, 0.78),
        ("VND005", "Bausch & Lomb India", "manufacturer", 8, 15000, 200, 0.91),
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

    # Build weighted brand list for realistic distribution
    brand_weights = []
    brand_names = []
    for b, cfg in BRAND_CONFIG.items():
        brand_names.append(b)
        brand_weights.append(cfg["weight"])

    for i in range(1, NUM_SKUS + 1):
        # Pick brand first (weighted by market share), then derive category
        brand = random.choices(brand_names, weights=brand_weights)[0]
        cfg = BRAND_CONFIG[brand]
        category = random.choice(cfg["cats"])
        mrp = random.choice(cfg["prices"])

        # Map category → subcategory, sku_type, fulfillment
        if category in ("eyeglasses", "computer_glasses"):
            if random.random() < 0.65:
                sku_type = "display_dummy"
                fulfillment_type = "order_capture"
                is_display_only = True
            else:
                sku_type = "physical_sell"
                fulfillment_type = "direct_sell"
                is_display_only = False
            sales_channel = "prescription" if category == "eyeglasses" else "walk_in"
        elif category == "sunglasses":
            sku_type = "physical_sell"
            fulfillment_type = "direct_sell"
            is_display_only = False
            sales_channel = "walk_in"
        else:  # contact_lenses
            sku_type = "physical_sell"
            fulfillment_type = "direct_sell"
            is_display_only = False
            sales_channel = "prescription"

        lifecycle = random.choices(["new", "active", "aging", "eol"], weights=[0.12, 0.55, 0.23, 0.10])[0]

        # Realistic product naming with collections
        collection = ""
        if brand in COLLECTIONS:
            collection = random.choice(COLLECTIONS[brand]) + " "

        if category == "contact_lenses":
            disposal = random.choice(CL_DISPOSAL)
            lens_type = random.choice(LENS_TYPES_CL)
            product_name = f"{brand} {collection}{disposal.title()} {lens_type.title()} {random.choice(FRAME_COLORS).title()}"
            frame_type = None
            frame_shape = None
            frame_material = None
            frame_color = None
        elif category == "sunglasses":
            lens_type = random.choice(LENS_TYPES_SUNGLASSES)
            shape = random.choice(FRAME_SHAPES)
            color = random.choice(FRAME_COLORS)
            frame_type = random.choice(FRAME_TYPES)
            frame_shape = shape
            frame_material = random.choice(FRAME_MATERIALS)
            frame_color = color
            product_name = f"{brand} {collection}{shape.replace('_', ' ').title()} {color.replace('_', ' ').title()}"
        else:  # eyeglasses, computer_glasses
            lens_type = random.choice(LENS_TYPES_EYEGLASSES)
            shape = random.choice(FRAME_SHAPES)
            color = random.choice(FRAME_COLORS)
            frame_type = random.choice(FRAME_TYPES)
            frame_shape = shape
            frame_material = random.choice(FRAME_MATERIALS)
            frame_color = color
            product_name = f"{brand} {collection}{shape.replace('_', ' ').title()} {color.replace('_', ' ').title()}"

        # Vendor assignment: in-house brands → VND001, premium → VND002, CL → VND005
        if brand in ("Vincent Chase", "Lenskart Air", "Lenskart Blu", "Hooper", "Hustlr"):
            vendor_id = "VND001"  # In-house manufacturing
        elif brand in ("Ray-Ban", "Oakley", "Carrera", "Tommy Hilfiger", "Owndays"):
            vendor_id = "VND002"  # EssilorLuxottica
        elif brand in ("Bausch & Lomb", "Acuvue", "Alcon", "CooperVision"):
            vendor_id = "VND005"  # B&L India
        elif category == "contact_lenses":
            vendor_id = random.choice(["VND005", "VND003"])
        else:
            vendor_id = random.choice(vendor_ids)

        # Subcategory with price tier
        if mrp >= 5000:
            subcategory = f"{category}_premium"
        elif mrp >= 2000:
            subcategory = f"{category}_mid"
        else:
            subcategory = f"{category}_value"

        gender = random.choice(GENDERS)
        if brand == "Aquacolor":
            gender = random.choice(["F", "Unisex"])  # Colored lenses skew female

        skus.append({
            "sku_id": f"SKU{i:05d}",
            "product_name": product_name,
            "brand": brand,
            "category": category,
            "subcategory": subcategory,
            "sku_type": sku_type,
            "gender": gender,
            "frame_type": frame_type,
            "frame_shape": frame_shape,
            "frame_material": frame_material,
            "frame_color": frame_color,
            "lens_type": lens_type,
            "size": random.choice(SIZES),
            "mrp": mrp,
            "cost_price": round(mrp * random.uniform(0.25, 0.45), 2),
            "fulfillment_type": fulfillment_type,
            "sales_channel": sales_channel,
            "is_display_only": is_display_only,
            "lifecycle_stage": lifecycle,
            "vendor_id": vendor_id,
            "lead_time_days": random.choice([3, 5, 7, 10, 14, 21]),
            "launch_date": (START_DATE - timedelta(days=random.randint(0, 730))).isoformat(),
        })
    return skus


def generate_calendar() -> list[dict]:
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


SALES_FIELDS = ["store_id", "sku_id", "sale_date", "qty_sold", "revenue", "discount",
                "fulfillment_type", "sales_channel", "is_return"]

def generate_daily_sales_streaming(stores: list[dict], skus: list[dict]):
    """Stream daily sales directly to CSV to avoid OOM."""
    eyeglass_skus = [s for s in skus if s["category"] in ("eyeglasses", "computer_glasses") and not s["is_display_only"]]
    sunglass_skus = [s for s in skus if s["category"] == "sunglasses"]
    cl_skus = [s for s in skus if s["category"] == "contact_lenses"]
    display_skus = [s for s in skus if s["is_display_only"]]

    csv_out = StreamingCSV("daily_sales.csv", SALES_FIELDS)

    for d_offset in range(NUM_DAYS):
        d = START_DATE + timedelta(days=d_offset)
        season_mult, promo = seasonal_multiplier(d)
        wknd_mult = weekend_multiplier(d)
        sun_mult = sunglasses_seasonality(d)

        for store in stores:
            cluster = STORE_CLUSTERS[store["store_cluster"]]
            store_base = cluster["conversion"] * cluster["base_traffic"]

            # Eyeglasses
            n_eye = max(1, int(store_base * 0.5 * season_mult * wknd_mult * random.uniform(0.5, 1.5)))
            for sku in random.sample(eyeglass_skus, min(n_eye, len(eyeglass_skus))):
                qty = random.choices([1, 2], weights=[0.85, 0.15])[0]
                discount_pct = 0.15 if promo else random.choice([0, 0, 0, 0.05, 0.10])
                csv_out.write({
                    "store_id": store["store_id"], "sku_id": sku["sku_id"],
                    "sale_date": d.isoformat(), "qty_sold": qty,
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
                csv_out.write({
                    "store_id": store["store_id"], "sku_id": sku["sku_id"],
                    "sale_date": d.isoformat(), "qty_sold": qty,
                    "revenue": round(sku["mrp"] * qty * (1 - discount_pct), 2),
                    "discount": round(sku["mrp"] * qty * discount_pct, 2),
                    "fulfillment_type": "direct_sell", "sales_channel": "walk_in",
                    "is_return": random.random() < 0.04,
                })

            # Contact lenses
            n_cl = max(0, int(store_base * 0.1 * season_mult * random.uniform(0.5, 1.5)))
            for sku in random.sample(cl_skus, min(n_cl, len(cl_skus))):
                qty = random.choices([1, 2, 3], weights=[0.5, 0.35, 0.15])[0]
                csv_out.write({
                    "store_id": store["store_id"], "sku_id": sku["sku_id"],
                    "sale_date": d.isoformat(), "qty_sold": qty,
                    "revenue": round(sku["mrp"] * qty, 2), "discount": 0.0,
                    "fulfillment_type": "direct_sell", "sales_channel": "prescription",
                    "is_return": False,
                })

            # Display dummy frames
            n_display = max(0, int(store_base * 0.3 * season_mult * wknd_mult * random.uniform(0.4, 1.2)))
            for sku in random.sample(display_skus, min(n_display, len(display_skus))):
                csv_out.write({
                    "store_id": store["store_id"], "sku_id": sku["sku_id"],
                    "sale_date": d.isoformat(), "qty_sold": 1,
                    "revenue": round(sku["mrp"] * random.uniform(0.85, 1.0), 2),
                    "discount": round(sku["mrp"] * random.uniform(0, 0.15), 2),
                    "fulfillment_type": "order_capture", "sales_channel": "prescription",
                    "is_return": False,
                })

    csv_out.close()


INVENTORY_FIELDS = ["store_id", "sku_id", "snapshot_date", "on_hand_qty", "on_display_qty",
                    "in_storage_qty", "in_transit_qty", "allocated_qty", "available_qty"]

def generate_daily_inventory_streaming(stores: list[dict], skus: list[dict]):
    """Stream daily inventory snapshots to CSV."""
    physical_skus = [s for s in skus if not s["is_display_only"]]
    display_skus = [s for s in skus if s["is_display_only"]]

    csv_out = StreamingCSV("daily_inventory.csv", INVENTORY_FIELDS)

    for store in stores:
        cap = store["display_capacity"]
        store_physical = random.sample(physical_skus, min(random.randint(30 if LITE_MODE else 150, 60 if LITE_MODE else 350), len(physical_skus)))
        store_display = random.sample(display_skus, min(cap, len(display_skus)))

        inv_levels = {}
        for sku in store_physical:
            inv_levels[sku["sku_id"]] = random.randint(2, 25)
        for sku in store_display:
            inv_levels[sku["sku_id"]] = random.randint(1, 3)

        for d_offset in range(NUM_DAYS):
            d = START_DATE + timedelta(days=d_offset)
            if d_offset % 7 != 0 and d_offset < (NUM_DAYS - 30):
                for sid in inv_levels:
                    inv_levels[sid] = max(0, inv_levels[sid] + random.randint(-2, 1))
                    if inv_levels[sid] == 0 and random.random() < 0.3:
                        inv_levels[sid] = random.randint(5, 15)
                continue

            for sku in store_physical:
                on_hand = max(0, inv_levels.get(sku["sku_id"], 0))
                on_display = min(on_hand, random.randint(0, 3))
                in_transit = random.randint(0, 5) if on_hand < 5 else 0
                csv_out.write({
                    "store_id": store["store_id"], "sku_id": sku["sku_id"],
                    "snapshot_date": d.isoformat(), "on_hand_qty": on_hand,
                    "on_display_qty": on_display, "in_storage_qty": on_hand - on_display,
                    "in_transit_qty": in_transit,
                    "allocated_qty": random.randint(0, min(2, on_hand)),
                    "available_qty": max(0, on_hand - random.randint(0, 2)),
                })

            for sku in store_display:
                on_display = random.randint(1, 2)
                csv_out.write({
                    "store_id": store["store_id"], "sku_id": sku["sku_id"],
                    "snapshot_date": d.isoformat(), "on_hand_qty": on_display,
                    "on_display_qty": on_display, "in_storage_qty": 0,
                    "in_transit_qty": 0, "allocated_qty": 0, "available_qty": 0,
                })

            for sid in inv_levels:
                inv_levels[sid] = max(0, inv_levels[sid] + random.randint(-2, 1))
                if inv_levels[sid] == 0 and random.random() < 0.3:
                    inv_levels[sid] = random.randint(5, 15)

    csv_out.close()


TRIAL_FIELDS = ["trial_id", "store_id", "sku_id", "trial_date", "trial_timestamp",
                "customer_id", "resulted_in_order", "order_id"]

def generate_store_trials_streaming(stores: list[dict], skus: list[dict]):
    """Stream store trial events to CSV."""
    display_skus = [s for s in skus if s["is_display_only"]]
    csv_out = StreamingCSV("store_trials.csv", TRIAL_FIELDS)
    trial_id = 0

    for d_offset in range(NUM_DAYS):
        d = START_DATE + timedelta(days=d_offset)
        season_mult, _ = seasonal_multiplier(d)
        wknd_mult = weekend_multiplier(d)

        for store in stores:
            cluster = STORE_CLUSTERS[store["store_cluster"]]
            n_trials = max(1, int(cluster["base_traffic"] * 0.3 * season_mult * wknd_mult * random.uniform(0.5, 1.5)))
            # In lite mode, cap trials per store-day
            if LITE_MODE:
                n_trials = min(n_trials, 10)

            for _ in range(n_trials):
                trial_id += 1
                sku = random.choice(display_skus)
                conversion = random.random() < cluster["conversion"]
                csv_out.write({
                    "trial_id": f"TRL{trial_id:08d}",
                    "store_id": store["store_id"], "sku_id": sku["sku_id"],
                    "trial_date": d.isoformat(),
                    "trial_timestamp": f"{d.isoformat()} {random.randint(10, 20)}:{random.randint(0, 59):02d}:00",
                    "customer_id": f"CUST{random.randint(1, 100000):06d}" if random.random() < 0.5 else "",
                    "resulted_in_order": conversion,
                    "order_id": f"ORD{random.randint(1, 999999):07d}" if conversion else "",
                })

    csv_out.close()


EYE_TEST_FIELDS = ["test_id", "store_id", "test_date", "customer_id",
                   "sph_right", "cyl_right", "sph_left", "cyl_left",
                   "resulted_in_purchase", "order_id"]

def generate_eye_tests_streaming(stores: list[dict]):
    """Stream eye test data to CSV."""
    csv_out = StreamingCSV("eye_tests.csv", EYE_TEST_FIELDS)
    test_id = 0

    for d_offset in range(NUM_DAYS):
        d = START_DATE + timedelta(days=d_offset)
        season_mult, _ = seasonal_multiplier(d)
        wknd_mult = weekend_multiplier(d)

        for store in stores:
            cluster = STORE_CLUSTERS[store["store_cluster"]]
            n_tests = max(0, int(cluster["base_traffic"] * 0.08 * season_mult * wknd_mult * random.uniform(0.5, 1.5)))

            for _ in range(n_tests):
                test_id += 1
                resulted_in_purchase = random.random() < 0.75
                csv_out.write({
                    "test_id": f"EYE{test_id:08d}",
                    "store_id": store["store_id"], "test_date": d.isoformat(),
                    "customer_id": f"CUST{random.randint(1, 100000):06d}",
                    "sph_right": round(random.uniform(-6.0, 4.0), 2),
                    "cyl_right": round(random.uniform(-3.0, 0.0), 2),
                    "sph_left": round(random.uniform(-6.0, 4.0), 2),
                    "cyl_left": round(random.uniform(-3.0, 0.0), 2),
                    "resulted_in_purchase": resulted_in_purchase,
                    "order_id": f"ORD{random.randint(1, 999999):07d}" if resulted_in_purchase else "",
                })

    csv_out.close()


def generate_receipts(stores: list[dict], skus: list[dict]) -> list[dict]:
    rows = []
    receipt_id = 0
    physical_skus = [s for s in skus if not s["is_display_only"]]

    for d_offset in range(0, NUM_DAYS, 3):
        d = START_DATE + timedelta(days=d_offset)
        for store in stores:
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


def generate_transfers(stores: list[dict], skus: list[dict]) -> list[dict]:
    rows = []
    transfer_id = 0
    physical_skus = [s for s in skus if not s["is_display_only"]]

    for d_offset in range(0, NUM_DAYS, 7):
        d = START_DATE + timedelta(days=d_offset)
        n_transfers = random.randint(5, 15)
        for _ in range(n_transfers):
            transfer_id += 1
            from_store, to_store = random.sample(stores, 2)
            sku = random.choice(physical_skus)
            qty = random.randint(1, 10)
            reason = random.choices(["rebalance", "stockout_prevention", "eol_clearance"], weights=[0.5, 0.35, 0.15])[0]

            initiated = d
            completed = d + timedelta(days=random.randint(1, 5))
            status = "received" if completed <= START_DATE + timedelta(days=NUM_DAYS - 1) else "in_transit"

            tid = f"TRF{transfer_id:06d}"
            base = {
                "transfer_id": tid,
                "from_store_id": from_store["store_id"],
                "to_store_id": to_store["store_id"],
                "sku_id": sku["sku_id"],
                "transfer_qty": qty,
                "status": status,
                "initiated_date": initiated.isoformat(),
                "completed_date": completed.isoformat() if status == "received" else "",
                "reason": reason,
            }
            rows.append({**base, "transfer_direction": "out"})
            rows.append({**base, "transfer_direction": "in"})
    return rows


def generate_purchase_orders(vendors: list[dict], skus: list[dict]) -> list[dict]:
    rows = []
    po_id = 0

    for d_offset in range(0, NUM_DAYS, 14):
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
    rows = []
    promo_id = 0
    for start, end, mult, name in FESTIVE_PERIODS:
        promo_id += 1
        rows.append({
            "promo_id": f"PROMO{promo_id:04d}",
            "sku_id": "",
            "store_id": "",
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "promo_type": "seasonal_sale",
            "promo_name": name,
            "discount_pct": round((mult - 1) * 0.5, 2),
            "discount_value": 0.0,
            "is_active": True,
        })

    eol_skus = [s for s in skus if s["lifecycle_stage"] == "eol"]
    for sku in random.sample(eol_skus, min(30, len(eol_skus))):
        promo_id += 1
        start = START_DATE + timedelta(days=random.randint(30 if LITE_MODE else 180, min(NUM_DAYS - 15, 330)))
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


# ─── Writer (for small datasets that fit in memory) ─────────────────────────

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
    if LITE_MODE:
        print("  *** LITE MODE (reduced dataset for constrained envs) ***")
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

    print("[5/11] Generating daily sales (streaming to disk)...")
    generate_daily_sales_streaming(stores, skus)

    print("[6/11] Generating inventory snapshots (streaming to disk)...")
    generate_daily_inventory_streaming(stores, skus)

    print("[7/11] Generating receipts...")
    receipts = generate_receipts(stores, skus)
    write_csv("receipts.csv", receipts)

    print("[8/11] Generating store trials (streaming to disk)...")
    generate_store_trials_streaming(stores, skus)

    print("[9/11] Generating eye tests (streaming to disk)...")
    generate_eye_tests_streaming(stores)

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


if __name__ == "__main__":
    main()
