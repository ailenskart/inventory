"""Generate synthetic datasets for local development.

Creates realistic-looking data for ~50 stores, ~500 SKUs, 10 vendors,
and 90 days of transaction history.
"""

import csv
import os
import random
from datetime import date, timedelta

random.seed(42)

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

# --- Constants ---
NUM_STORES = 50
NUM_SKUS = 500
NUM_VENDORS = 10
DAYS = 90
START_DATE = date(2024, 1, 1)

CITIES = [
    ("Mumbai", "Maharashtra", "West"),
    ("Delhi", "Delhi", "North"),
    ("Bangalore", "Karnataka", "South"),
    ("Hyderabad", "Telangana", "South"),
    ("Chennai", "Tamil Nadu", "South"),
    ("Kolkata", "West Bengal", "East"),
    ("Pune", "Maharashtra", "West"),
    ("Ahmedabad", "Gujarat", "West"),
    ("Jaipur", "Rajasthan", "North"),
    ("Lucknow", "Uttar Pradesh", "North"),
]

BRANDS = ["Lenskart Air", "Lenskart Blu", "Vincent Chase", "John Jacobs", "Hooper", "Aqua", "Hustlr"]
CATEGORIES = ["eyeglasses", "sunglasses", "contact_lenses"]
FRAME_TYPES = ["full_rim", "half_rim", "rimless"]
FRAME_SHAPES = ["rectangle", "round", "aviator", "cat_eye", "wayfarer", "square"]
FRAME_MATERIALS = ["metal", "acetate", "TR90", "titanium"]
GENDERS = ["M", "F", "Unisex"]
STORE_TYPES = ["company_owned", "franchise"]
STORE_FORMATS = ["large", "medium", "small"]


def generate_stores():
    stores = []
    for i in range(1, NUM_STORES + 1):
        city, state, region = random.choice(CITIES)
        stores.append({
            "store_id": f"STR{i:04d}",
            "store_name": f"Lenskart {city} {i}",
            "city": city,
            "state": state,
            "region": region,
            "pincode": f"{random.randint(100000, 999999)}",
            "store_type": random.choice(STORE_TYPES),
            "store_format": random.choice(STORE_FORMATS),
            "cluster_id": f"CLU{random.randint(1, 8):02d}",
            "latitude": round(random.uniform(8.0, 35.0), 6),
            "longitude": round(random.uniform(68.0, 97.0), 6),
            "opening_date": (START_DATE - timedelta(days=random.randint(30, 1800))).isoformat(),
            "is_active": True,
            "display_capacity": random.choice([80, 120, 160, 200]),
            "storage_capacity": random.choice([200, 400, 600]),
        })
    return stores


def generate_vendors():
    vendors = []
    for i in range(1, NUM_VENDORS + 1):
        city, state, _ = random.choice(CITIES)
        vendors.append({
            "vendor_id": f"VND{i:04d}",
            "vendor_name": f"Vendor {chr(64 + i)}",
            "vendor_type": random.choice(["manufacturer", "distributor"]),
            "contact_email": f"vendor{i}@example.com",
            "contact_phone": f"98{random.randint(10000000, 99999999)}",
            "city": city,
            "state": state,
            "avg_lead_time_days": random.choice([5, 7, 10, 14]),
            "min_order_value": random.choice([10000, 25000, 50000]),
            "min_order_qty": random.choice([10, 25, 50, 100]),
            "reliability_score": round(random.uniform(0.7, 1.0), 2),
            "is_active": True,
        })
    return vendors


def generate_skus(vendors):
    skus = []
    for i in range(1, NUM_SKUS + 1):
        category = random.choices(CATEGORIES, weights=[0.6, 0.3, 0.1])[0]
        is_display = category == "eyeglasses" and random.random() < 0.7
        fulfillment = "order_capture" if is_display else "direct_sell"
        mrp = random.choice([799, 999, 1299, 1599, 1999, 2499, 2999, 3999, 4999])

        skus.append({
            "sku_id": f"SKU{i:05d}",
            "product_name": f"{random.choice(BRANDS)} {random.choice(FRAME_SHAPES).title()} {i}",
            "brand": random.choice(BRANDS),
            "category": category,
            "subcategory": f"{category}_sub",
            "gender": random.choice(GENDERS),
            "frame_type": random.choice(FRAME_TYPES) if category != "contact_lenses" else None,
            "frame_shape": random.choice(FRAME_SHAPES) if category != "contact_lenses" else None,
            "frame_material": random.choice(FRAME_MATERIALS) if category != "contact_lenses" else None,
            "frame_color": random.choice(["black", "brown", "blue", "gold", "silver", "tortoise"]),
            "lens_type": random.choice(["clear", "blue_cut", "photochromic", "polarized", "tinted"]),
            "size": random.choice(["S", "M", "L"]),
            "mrp": mrp,
            "cost_price": round(mrp * random.uniform(0.3, 0.5), 2),
            "fulfillment_type": fulfillment,
            "is_display_only": is_display,
            "lifecycle_stage": random.choices(["new", "active", "aging", "eol"], weights=[0.15, 0.55, 0.2, 0.1])[0],
            "vendor_id": random.choice(vendors)["vendor_id"],
            "lead_time_days": random.choice([5, 7, 10, 14]),
        })
    return skus


def generate_daily_sales(stores, skus):
    """Generate 90 days of daily sales."""
    rows = []
    for d in range(DAYS):
        sale_date = (START_DATE + timedelta(days=d)).isoformat()
        for store in stores:
            # Each store sells 5-30 SKUs per day
            num_sold = random.randint(5, 30)
            sold_skus = random.sample(skus, min(num_sold, len(skus)))
            for sku in sold_skus:
                qty = random.choices([1, 2, 3], weights=[0.7, 0.2, 0.1])[0]
                rows.append({
                    "store_id": store["store_id"],
                    "sku_id": sku["sku_id"],
                    "sale_date": sale_date,
                    "qty_sold": qty,
                    "revenue": round(sku["mrp"] * qty * random.uniform(0.8, 1.0), 2),
                    "discount": round(sku["mrp"] * qty * random.uniform(0, 0.2), 2),
                    "fulfillment_type": sku["fulfillment_type"],
                    "is_return": random.random() < 0.03,
                })
    return rows


def generate_daily_inventory(stores, skus):
    """Generate daily inventory snapshots (last 7 days only to keep size manageable)."""
    rows = []
    for d in range(max(0, DAYS - 7), DAYS):
        snap_date = (START_DATE + timedelta(days=d)).isoformat()
        for store in stores:
            # Each store has 100-300 SKUs in inventory
            inv_skus = random.sample(skus, min(random.randint(100, 300), len(skus)))
            for sku in inv_skus:
                on_hand = random.randint(0, 20)
                on_display = min(on_hand, random.randint(0, 3))
                rows.append({
                    "store_id": store["store_id"],
                    "sku_id": sku["sku_id"],
                    "snapshot_date": snap_date,
                    "on_hand_qty": on_hand,
                    "on_display_qty": on_display,
                    "in_storage_qty": on_hand - on_display,
                    "in_transit_qty": random.randint(0, 5),
                    "allocated_qty": random.randint(0, 3),
                    "available_qty": max(0, on_hand - random.randint(0, 3)),
                })
    return rows


def generate_store_trials(stores, skus):
    """Generate try-on events (for display/eyeglasses SKUs)."""
    display_skus = [s for s in skus if s["is_display_only"]]
    rows = []
    trial_id = 0
    for d in range(DAYS):
        trial_date = (START_DATE + timedelta(days=d)).isoformat()
        for store in stores:
            num_trials = random.randint(10, 50)
            for _ in range(num_trials):
                trial_id += 1
                sku = random.choice(display_skus)
                resulted = random.random() < 0.15
                rows.append({
                    "trial_id": f"TRL{trial_id:08d}",
                    "store_id": store["store_id"],
                    "sku_id": sku["sku_id"],
                    "trial_date": trial_date,
                    "customer_id": f"CUST{random.randint(1, 50000):06d}" if random.random() < 0.6 else "",
                    "resulted_in_order": resulted,
                    "order_id": f"ORD{random.randint(1, 999999):07d}" if resulted else "",
                })
    return rows


def generate_store_traffic(stores):
    """Generate daily store traffic."""
    rows = []
    for d in range(DAYS):
        traffic_date = (START_DATE + timedelta(days=d)).isoformat()
        for store in stores:
            base = {"large": 150, "medium": 80, "small": 40}.get(store["store_format"], 60)
            # Weekend boost
            day_of_week = (START_DATE + timedelta(days=d)).weekday()
            multiplier = 1.4 if day_of_week >= 5 else 1.0
            footfall = int(base * multiplier * random.uniform(0.6, 1.4))
            rows.append({
                "store_id": store["store_id"],
                "traffic_date": traffic_date,
                "footfall_count": footfall,
                "walk_ins": int(footfall * random.uniform(0.7, 0.9)),
                "appointments": int(footfall * random.uniform(0.05, 0.15)),
            })
    return rows


def write_csv(filename, rows, fieldnames=None):
    if not rows:
        return
    if fieldnames is None:
        fieldnames = list(rows[0].keys())
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  Written {len(rows):>10,} rows -> {filename}")


def main():
    print("Generating synthetic data for Lenskart Retail Intelligence...")
    stores = generate_stores()
    vendors = generate_vendors()
    skus = generate_skus(vendors)

    write_csv("stores.csv", stores)
    write_csv("vendors.csv", vendors)
    write_csv("skus.csv", skus)

    print("  Generating daily sales (this may take a moment)...")
    sales = generate_daily_sales(stores, skus)
    write_csv("daily_sales.csv", sales)

    print("  Generating inventory snapshots...")
    inventory = generate_daily_inventory(stores, skus)
    write_csv("daily_inventory.csv", inventory)

    print("  Generating store trials...")
    trials = generate_store_trials(stores, skus)
    write_csv("store_trials.csv", trials)

    print("  Generating store traffic...")
    traffic = generate_store_traffic(stores)
    write_csv("store_traffic.csv", traffic)

    print("\nDone! Synthetic data generated in:", OUTPUT_DIR)


if __name__ == "__main__":
    main()
