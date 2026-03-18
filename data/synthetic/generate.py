"""Generate synthetic datasets for Lenskart Retail Intelligence Platform.

Creates realistic data for local development and testing:
- 2000 stores across 60+ Indian cities with real Lenskart naming
- 2000 SKUs: eyeglasses, sunglasses, contact lenses, computer glasses, reading glasses
- 12 vendors with varying lead times and reliability
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

NUM_STORES = 10 if LITE_MODE else 2000
NUM_SKUS = 100 if LITE_MODE else 2000
NUM_VENDORS = 12
NUM_DAYS = 90 if LITE_MODE else 365
START_DATE = date(2024, 1, 1)

# ─── 60+ Indian cities with real coordinates ────────────────────────────────

CITIES = [
    # Metros
    ("Mumbai", "Maharashtra", "West", 19.076, 72.877),
    ("Delhi", "Delhi", "North", 28.704, 77.102),
    ("Bangalore", "Karnataka", "South", 12.971, 77.594),
    ("Hyderabad", "Telangana", "South", 17.385, 78.486),
    ("Chennai", "Tamil Nadu", "South", 13.082, 80.270),
    ("Kolkata", "West Bengal", "East", 22.572, 88.363),
    # Tier-1
    ("Pune", "Maharashtra", "West", 18.520, 73.856),
    ("Ahmedabad", "Gujarat", "West", 23.022, 72.571),
    ("Jaipur", "Rajasthan", "North", 26.912, 75.787),
    ("Lucknow", "Uttar Pradesh", "North", 26.846, 80.946),
    ("Chandigarh", "Punjab", "North", 30.733, 76.779),
    ("Kochi", "Kerala", "South", 9.931, 76.267),
    ("Indore", "Madhya Pradesh", "Central", 22.719, 75.857),
    ("Nagpur", "Maharashtra", "Central", 21.145, 79.088),
    ("Coimbatore", "Tamil Nadu", "South", 11.016, 76.955),
    ("Surat", "Gujarat", "West", 21.170, 72.831),
    ("Vadodara", "Gujarat", "West", 22.310, 73.192),
    ("Visakhapatnam", "Andhra Pradesh", "South", 17.686, 83.218),
    ("Bhopal", "Madhya Pradesh", "Central", 23.259, 77.412),
    ("Patna", "Bihar", "East", 25.612, 85.144),
    ("Thiruvananthapuram", "Kerala", "South", 8.524, 76.936),
    ("Guwahati", "Assam", "East", 26.144, 91.736),
    ("Bhubaneswar", "Odisha", "East", 20.296, 85.824),
    ("Dehradun", "Uttarakhand", "North", 30.316, 78.032),
    ("Ranchi", "Jharkhand", "East", 23.344, 85.309),
    # Tier-2
    ("Noida", "Uttar Pradesh", "North", 28.535, 77.391),
    ("Gurgaon", "Haryana", "North", 28.459, 77.026),
    ("Faridabad", "Haryana", "North", 28.408, 77.317),
    ("Ghaziabad", "Uttar Pradesh", "North", 28.669, 77.438),
    ("Thane", "Maharashtra", "West", 19.218, 72.978),
    ("Navi Mumbai", "Maharashtra", "West", 19.033, 73.029),
    ("Mysore", "Karnataka", "South", 12.295, 76.639),
    ("Mangalore", "Karnataka", "South", 12.914, 74.856),
    ("Hubli", "Karnataka", "South", 15.361, 75.124),
    ("Amritsar", "Punjab", "North", 31.633, 74.872),
    ("Ludhiana", "Punjab", "North", 30.900, 75.857),
    ("Jalandhar", "Punjab", "North", 31.326, 75.576),
    ("Agra", "Uttar Pradesh", "North", 27.176, 78.008),
    ("Varanasi", "Uttar Pradesh", "North", 25.317, 82.987),
    ("Allahabad", "Uttar Pradesh", "North", 25.431, 81.846),
    ("Kanpur", "Uttar Pradesh", "North", 26.449, 80.331),
    ("Meerut", "Uttar Pradesh", "North", 28.984, 77.706),
    ("Jodhpur", "Rajasthan", "North", 26.238, 73.024),
    ("Udaipur", "Rajasthan", "North", 24.585, 73.712),
    ("Kota", "Rajasthan", "North", 25.180, 75.864),
    ("Raipur", "Chhattisgarh", "Central", 21.250, 81.629),
    ("Nashik", "Maharashtra", "West", 19.997, 73.790),
    ("Aurangabad", "Maharashtra", "West", 19.876, 75.343),
    ("Kolhapur", "Maharashtra", "West", 16.705, 74.243),
    ("Rajkot", "Gujarat", "West", 22.303, 70.802),
    ("Gandhinagar", "Gujarat", "West", 23.215, 72.636),
    ("Vijayawada", "Andhra Pradesh", "South", 16.506, 80.648),
    ("Tirupati", "Andhra Pradesh", "South", 13.628, 79.419),
    ("Madurai", "Tamil Nadu", "South", 9.925, 78.119),
    ("Trichy", "Tamil Nadu", "South", 10.790, 78.704),
    ("Salem", "Tamil Nadu", "South", 11.664, 78.146),
    ("Thrissur", "Kerala", "South", 10.527, 76.214),
    ("Kozhikode", "Kerala", "South", 11.258, 75.780),
    ("Siliguri", "West Bengal", "East", 26.727, 88.395),
    ("Durgapur", "West Bengal", "East", 23.520, 87.311),
    ("Jabalpur", "Madhya Pradesh", "Central", 23.181, 79.986),
    ("Gwalior", "Madhya Pradesh", "Central", 26.218, 78.182),
    ("Bareilly", "Uttar Pradesh", "North", 28.367, 79.432),
    ("Gorakhpur", "Uttar Pradesh", "North", 26.760, 83.373),
]

# Cities classified by tier for store cluster assignment
METRO_CITIES = {"Mumbai", "Delhi", "Bangalore", "Hyderabad", "Chennai", "Kolkata"}
TIER1_CITIES = {
    "Pune", "Ahmedabad", "Jaipur", "Lucknow", "Chandigarh", "Kochi", "Indore",
    "Nagpur", "Coimbatore", "Surat", "Vadodara", "Visakhapatnam", "Bhopal",
    "Patna", "Thiruvananthapuram", "Guwahati", "Bhubaneswar", "Dehradun", "Ranchi",
    "Noida", "Gurgaon", "Thane", "Navi Mumbai",
}

# ─── Real Lenskart product data ──────────────────────────────────────────────

# In-house brands (primary revenue, ~80% of catalog)
INHOUSE_BRANDS = [
    "Vincent Chase", "John Jacobs", "Lenskart Air", "Lenskart Blu",
    "Hooper", "Hustlr", "Aqua", "Aquacolor", "Lenskart Junior",
]
# Third-party / licensed brands
THIRDPARTY_BRANDS = [
    "Ray-Ban", "Oakley", "Carrera", "Tommy Hilfiger", "Lee Cooper",
    "New Balance", "Owndays", "Fossil", "Hugo Boss", "GUESS",
    "Polaroid", "Vogue Eyewear",
]
# Contact lens third-party brands
CL_BRANDS = ["Bausch & Lomb", "Acuvue", "Alcon", "CooperVision", "Aqua", "Aquacolor", "Aqualens"]

# Brand → typical categories and price positioning
BRAND_CONFIG = {
    # In-house brands
    "Vincent Chase":   {"cats": ["eyeglasses", "sunglasses"], "prices": [499, 599, 799, 999, 1199, 1299, 1499, 1599, 1999, 2499, 2999], "weight": 22},
    "John Jacobs":     {"cats": ["eyeglasses", "sunglasses"], "prices": [1299, 1499, 1599, 1999, 2499, 2999, 3499, 3999, 4499, 4999], "weight": 16},
    "Lenskart Air":    {"cats": ["eyeglasses"], "prices": [799, 999, 1199, 1299, 1499, 1599, 1999, 2499, 2999, 3999], "weight": 14},
    "Lenskart Blu":    {"cats": ["computer_glasses"], "prices": [499, 699, 799, 999, 1199, 1299, 1499, 1599, 2499], "weight": 8},
    "Hooper":          {"cats": ["eyeglasses", "computer_glasses"], "prices": [399, 499, 599, 799, 999, 1199, 1299, 1999], "weight": 7},
    "Hustlr":          {"cats": ["eyeglasses", "sunglasses"], "prices": [599, 799, 999, 1199, 1299, 1499, 1999, 2499], "weight": 5},
    "Lenskart Junior": {"cats": ["eyeglasses"], "prices": [399, 499, 599, 799, 999], "weight": 3},
    "Aqua":            {"cats": ["contact_lenses"], "prices": [250, 300, 399, 499, 599, 699, 899, 1199, 1499], "weight": 4},
    "Aquacolor":       {"cats": ["contact_lenses"], "prices": [399, 500, 599, 699, 799, 899, 1199], "weight": 2},
    "Aqualens":        {"cats": ["contact_lenses"], "prices": [199, 299, 399, 499, 699], "weight": 2},
    # Third-party premium
    "Ray-Ban":         {"cats": ["eyeglasses", "sunglasses"], "prices": [4999, 5499, 5999, 6999, 7999, 8999, 9999, 11999, 12999, 14999], "weight": 4},
    "Oakley":          {"cats": ["sunglasses"], "prices": [5999, 7999, 8999, 9999, 11999, 14999, 17999], "weight": 2},
    "Carrera":         {"cats": ["sunglasses", "eyeglasses"], "prices": [3999, 4999, 5999, 6999, 7999, 9999], "weight": 1},
    "Tommy Hilfiger":  {"cats": ["eyeglasses", "sunglasses"], "prices": [3999, 4999, 5499, 5999, 6999, 7999], "weight": 1},
    "Lee Cooper":      {"cats": ["eyeglasses", "sunglasses"], "prices": [1499, 1999, 2499, 2999, 3499, 3999], "weight": 1},
    "New Balance":     {"cats": ["eyeglasses"], "prices": [2499, 2999, 3499, 3999, 4999], "weight": 1},
    "Owndays":         {"cats": ["eyeglasses", "sunglasses"], "prices": [4999, 5999, 6999, 7999, 9999], "weight": 1},
    "Fossil":          {"cats": ["eyeglasses", "sunglasses"], "prices": [3999, 4999, 5999, 7999], "weight": 1},
    "Hugo Boss":       {"cats": ["eyeglasses", "sunglasses"], "prices": [7999, 9999, 11999, 14999, 17999], "weight": 0},
    "GUESS":           {"cats": ["eyeglasses", "sunglasses"], "prices": [4999, 5999, 6999, 7999, 9999], "weight": 1},
    "Polaroid":        {"cats": ["sunglasses"], "prices": [2999, 3499, 3999, 4999, 5999], "weight": 1},
    "Vogue Eyewear":   {"cats": ["eyeglasses", "sunglasses"], "prices": [3999, 4999, 5999, 6999], "weight": 1},
    # CL third-party
    "Bausch & Lomb":   {"cats": ["contact_lenses"], "prices": [299, 399, 499, 599, 799, 899, 1099, 1299, 1599], "weight": 1},
    "Acuvue":          {"cats": ["contact_lenses"], "prices": [599, 699, 899, 999, 1299, 1499, 1799, 1999], "weight": 1},
    "Alcon":           {"cats": ["contact_lenses"], "prices": [499, 599, 799, 899, 1099, 1299, 1599, 1799], "weight": 0},
    "CooperVision":    {"cats": ["contact_lenses"], "prices": [399, 499, 599, 799, 999, 1099], "weight": 0},
}

# Collections (for product naming — real Lenskart collection names)
COLLECTIONS = {
    "Vincent Chase": [
        "Air Wrap", "Poppin 2.0", "Float Pop", "Hip Hop", "Boost", "Crystal Clear",
        "Sleek Steel", "Flex Fit", "Trendsetter", "Bold", "Classic", "Vintage",
        "Urban", "Retro Pop", "Maverick", "Essentials", "Street Style",
    ],
    "John Jacobs": [
        "Coastline", "Rhapsody", "Roman Holiday", "Surrealist", "Art Deco",
        "Encore", "Ashbury", "Boulevard", "Heritage", "Voyager", "Icon",
        "Metropolitan", "Sterling", "Prestige", "Signature",
    ],
    "Lenskart Air": [
        "Air Flex", "Air Prism", "Switch", "Ultra Light", "Air Clip-On",
        "Air Progressive", "Air Titan", "Air Sport", "Feather Light",
        "Breeze", "Cloud", "Zero G",
    ],
    "Lenskart Blu": [
        "Zero Power", "Screen Guard", "Blu Cut Pro", "Digital Shield",
        "Blu Comfort", "Blu Block Plus", "Eye Protect", "Office Pro",
    ],
    "Hooper": [
        "Daily Comfort", "Classic", "Budget Flex", "Easy Wear", "Campus",
        "Value Plus", "Smooth", "Everyday",
    ],
    "Hustlr": [
        "Street", "Sport Fit", "Active", "Rush", "Grind", "Hustle Pro",
        "Edge", "Vibe",
    ],
    "Lenskart Junior": [
        "Junior Flex", "Kids Cool", "Tiny Tot", "Junior Blu", "Playtime",
        "Scholar", "Little Star",
    ],
}

FRAME_SHAPES = [
    "rectangle", "round", "aviator", "cat_eye", "wayfarer", "square",
    "clubmaster", "geometric", "hexagonal", "oval", "butterfly", "navigator",
    "browline", "oversized", "wrap", "shield",
]
FRAME_TYPES = ["full_rim", "half_rim", "rimless"]
FRAME_MATERIALS = [
    "metal", "acetate", "TR90", "titanium", "stainless_steel", "ultem",
    "mixed", "carbon_fiber", "wood_acetate", "memory_metal", "beta_titanium",
]
FRAME_COLORS = [
    "black", "matte_black", "brown", "tortoise", "dark_tortoise", "blue",
    "navy", "teal", "gold", "silver", "gunmetal", "transparent", "crystal",
    "red", "wine", "maroon", "green", "olive", "rose_gold", "purple",
    "lavender", "white", "grey", "charcoal", "pink", "peach", "orange",
    "copper", "bronze", "two_tone_black_gold", "two_tone_silver_blue",
]
LENS_TYPES_EYEGLASSES = ["single_vision", "blue_cut", "photochromic", "progressive", "bifocal", "zero_power"]
LENS_TYPES_SUNGLASSES = ["polarized", "mirrored", "gradient", "tinted", "photochromic", "TAC_polarized"]
LENS_TYPES_CL = ["spherical", "toric", "multifocal", "colored"]
CL_DISPOSAL = ["daily", "biweekly", "monthly", "quarterly", "yearly"]
CL_PACK_SIZES = [1, 3, 6, 10, 30, 90]
SIZES = ["XS", "S", "M", "L", "XL"]
GENDERS = ["M", "F", "Unisex", "Kids"]

# Power ranges for contact lenses
CL_POWERS = [f"{p:.2f}" for p in [x * -0.25 for x in range(1, 33)] + [x * 0.25 for x in range(1, 17)]]

# Reading glasses powers
READING_POWERS = ["+1.00", "+1.25", "+1.50", "+1.75", "+2.00", "+2.25", "+2.50", "+3.00"]

# Store clusters define demand profiles
STORE_CLUSTERS = {
    "METRO_FLAGSHIP": {"base_traffic": 280, "conversion": 0.14, "sunglass_affinity": 0.40, "premium_affinity": 0.50},
    "METRO_HIGH":     {"base_traffic": 200, "conversion": 0.12, "sunglass_affinity": 0.35, "premium_affinity": 0.40},
    "METRO_MID":      {"base_traffic": 120, "conversion": 0.10, "sunglass_affinity": 0.25, "premium_affinity": 0.25},
    "TIER1_HIGH":     {"base_traffic": 100, "conversion": 0.11, "sunglass_affinity": 0.20, "premium_affinity": 0.20},
    "TIER1_MID":      {"base_traffic": 70,  "conversion": 0.09, "sunglass_affinity": 0.15, "premium_affinity": 0.15},
    "TIER2":          {"base_traffic": 50,  "conversion": 0.08, "sunglass_affinity": 0.10, "premium_affinity": 0.10},
    "TIER3":          {"base_traffic": 35,  "conversion": 0.07, "sunglass_affinity": 0.08, "premium_affinity": 0.05},
    "KIOSK":          {"base_traffic": 30,  "conversion": 0.06, "sunglass_affinity": 0.20, "premium_affinity": 0.05},
    "AIRPORT":        {"base_traffic": 150, "conversion": 0.05, "sunglass_affinity": 0.50, "premium_affinity": 0.60},
}

# Store naming patterns (real Lenskart store names)
STORE_LOCATIONS = [
    "Mall", "High Street", "Hub", "Express", "Studio", "Lite",
    "Phoenix Mall", "Ambience Mall", "Select Citywalk", "Inorbit Mall",
    "VR Mall", "Forum Mall", "Nexus Mall", "DLF Mall", "Elante Mall",
    "Lulu Mall", "DB Mall", "Pavilion Mall", "Centre Square",
    "MG Road", "Brigade Road", "Park Street", "Connaught Place",
    "Linking Road", "Commercial Street", "Residency Road",
    "Sector 17", "Sector 35", "Sector 44",
    "Koramangala", "Indiranagar", "Whitefield", "HSR Layout",
    "Bandra", "Andheri", "Malad", "Powai", "Juhu",
    "Gachibowli", "Hitech City", "Jubilee Hills", "Banjara Hills",
    "T Nagar", "Anna Nagar", "Velachery", "Adyar",
    "Salt Lake", "New Town", "Park Circus",
    "Aundh", "Koregaon Park", "Viman Nagar", "Hinjewadi",
    "SG Highway", "CG Road", "Vastrapur",
]

# Festive / seasonal calendar for India
FESTIVE_PERIODS = [
    (date(2024, 1, 14), date(2024, 1, 16), 1.3, "makar_sankranti"),
    (date(2024, 1, 26), date(2024, 1, 28), 1.25, "republic_day_sale"),
    (date(2024, 3, 8), date(2024, 3, 10), 1.2, "womens_day_sale"),
    (date(2024, 3, 25), date(2024, 3, 28), 1.2, "holi"),
    (date(2024, 4, 10), date(2024, 4, 14), 1.4, "new_year_sales"),
    (date(2024, 5, 1), date(2024, 5, 5), 1.3, "summer_sale"),
    (date(2024, 6, 15), date(2024, 6, 30), 1.35, "monsoon_sale"),
    (date(2024, 8, 1), date(2024, 8, 15), 1.5, "independence_day_sale"),
    (date(2024, 8, 26), date(2024, 8, 28), 1.3, "raksha_bandhan"),
    (date(2024, 9, 15), date(2024, 9, 20), 1.3, "onam"),
    (date(2024, 10, 1), date(2024, 10, 15), 1.8, "navratri_dussehra"),
    (date(2024, 10, 25), date(2024, 11, 5), 2.0, "diwali"),
    (date(2024, 11, 15), date(2024, 11, 17), 1.4, "childrens_day_sale"),
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
    used_names = set()

    for i in range(1, NUM_STORES + 1):
        city, state, region, base_lat, base_lng = random.choice(CITIES)

        # Assign cluster based on city tier and random distribution
        if city in METRO_CITIES:
            if i <= 20:
                cluster = "METRO_FLAGSHIP"
            elif random.random() < 0.4:
                cluster = "METRO_HIGH"
            elif random.random() < 0.5:
                cluster = "METRO_MID"
            else:
                cluster = random.choice(["TIER1_HIGH", "TIER1_MID"])
        elif city in TIER1_CITIES:
            if random.random() < 0.3:
                cluster = "TIER1_HIGH"
            elif random.random() < 0.5:
                cluster = "TIER1_MID"
            else:
                cluster = "TIER2"
        else:
            cluster = random.choices(
                ["TIER2", "TIER3", "KIOSK"],
                weights=[0.5, 0.35, 0.15]
            )[0]

        # Some airport stores
        if i % 200 == 0 and city in METRO_CITIES:
            cluster = "AIRPORT"

        store_format = {
            "METRO_FLAGSHIP": "flagship", "METRO_HIGH": "large", "METRO_MID": "large",
            "TIER1_HIGH": "medium", "TIER1_MID": "medium", "TIER2": "small",
            "TIER3": "small", "KIOSK": "kiosk", "AIRPORT": "medium",
        }[cluster]

        # Real Lenskart ownership: COCO (flagship) vs FOFO (franchise expansion)
        if cluster in ("METRO_FLAGSHIP", "AIRPORT"):
            ownership = "COCO"
        elif cluster in ("METRO_HIGH", "METRO_MID"):
            ownership = "COCO" if random.random() < 0.7 else "FOFO"
        else:
            ownership = "FOFO" if random.random() < 0.65 else "COCO"

        # Generate unique store name
        location = random.choice(STORE_LOCATIONS)
        name = f"Lenskart {city} {location} {i}"
        while name in used_names:
            location = random.choice(STORE_LOCATIONS)
            name = f"Lenskart {city} {location} {i}"
        used_names.add(name)

        stores.append({
            "store_id": f"STR{i:04d}",
            "store_name": name,
            "city": city,
            "state": state,
            "region": region,
            "pincode": f"{random.randint(100000, 999999)}",
            "store_type": ownership,
            "store_format": store_format,
            "store_cluster": cluster,
            "latitude": round(base_lat + random.uniform(-0.08, 0.08), 6),
            "longitude": round(base_lng + random.uniform(-0.08, 0.08), 6),
            "opening_date": (START_DATE - timedelta(days=random.randint(30, 2500))).isoformat(),
            "is_active": random.random() < 0.96,
            "display_capacity": {"flagship": 300, "large": 200, "medium": 150, "small": 100, "kiosk": 50}[store_format],
            "storage_capacity": {"flagship": 1000, "large": 600, "medium": 400, "small": 200, "kiosk": 80}[store_format],
        })
    return stores


def generate_vendors() -> list[dict]:
    vendor_specs = [
        ("VND001", "Lenskart Manufacturing (In-house)", "manufacturer", 5, 25000, 50, 0.96, "Gurugram"),
        ("VND002", "EssilorLuxottica India", "manufacturer", 10, 50000, 100, 0.92, "Mumbai"),
        ("VND003", "Titan Eyeplus", "manufacturer", 7, 25000, 50, 0.94, "Bangalore"),
        ("VND004", "Shenzhen Hongyi Optics", "manufacturer", 21, 100000, 500, 0.78, "Shenzhen"),
        ("VND005", "Bausch & Lomb India", "manufacturer", 8, 15000, 200, 0.91, "Mumbai"),
        ("VND006", "CooperVision India", "manufacturer", 9, 12000, 150, 0.89, "Mumbai"),
        ("VND007", "Alcon India", "manufacturer", 8, 20000, 200, 0.90, "Bangalore"),
        ("VND008", "Safilo Group India", "manufacturer", 12, 30000, 100, 0.87, "Delhi"),
        ("VND009", "De Rigo India", "manufacturer", 14, 25000, 80, 0.85, "Mumbai"),
        ("VND010", "Marchon Eyewear India", "manufacturer", 11, 20000, 100, 0.88, "Delhi"),
        ("VND011", "Wenzhou Optics Co.", "manufacturer", 25, 150000, 1000, 0.75, "Wenzhou"),
        ("VND012", "Lenskart Lens Lab (In-house)", "lens_manufacturer", 3, 10000, 100, 0.97, "Gurugram"),
    ]
    vendors = []
    for vid, name, vtype, lt, mov, moq, reliability, city in vendor_specs:
        vendors.append({
            "vendor_id": vid,
            "vendor_name": name,
            "vendor_type": vtype,
            "contact_email": f"{vid.lower()}@example.com",
            "contact_phone": f"98{random.randint(10000000, 99999999)}",
            "city": city,
            "state": "",
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

    # Model number counter per brand
    model_counters = {}

    for i in range(1, NUM_SKUS + 1):
        # Pick brand first (weighted by market share), then derive category
        brand = random.choices(brand_names, weights=brand_weights)[0]
        cfg = BRAND_CONFIG[brand]
        category = random.choice(cfg["cats"])
        mrp = random.choice(cfg["prices"])

        # Generate model number
        brand_key = brand.replace(" ", "").replace("&", "").upper()[:4]
        model_counters[brand_key] = model_counters.get(brand_key, 0) + 1
        model_num = f"{brand_key}{model_counters[brand_key]:04d}"

        # Map category -> subcategory, sku_type, fulfillment
        if category in ("eyeglasses", "computer_glasses"):
            if random.random() < 0.60:
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

        lifecycle = random.choices(["new", "active", "aging", "eol"], weights=[0.15, 0.50, 0.25, 0.10])[0]

        # Realistic product naming with collections
        collection = ""
        if brand in COLLECTIONS:
            collection = random.choice(COLLECTIONS[brand]) + " "

        if category == "contact_lenses":
            disposal = random.choice(CL_DISPOSAL)
            lens_type = random.choice(LENS_TYPES_CL)
            pack_size = random.choice(CL_PACK_SIZES)
            color_name = random.choice(["Hazel", "Green", "Blue", "Grey", "Turquoise", "Brown", "Honey", "Amethyst"]) if lens_type == "colored" else ""
            product_name = f"{brand} {collection}{disposal.title()} {lens_type.title()}"
            if color_name:
                product_name += f" {color_name}"
            product_name += f" ({pack_size}pk)"
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
            product_name = f"{brand} {collection}{shape.replace('_', ' ').title()} {color.replace('_', ' ').title()} {model_num}"
        else:  # eyeglasses, computer_glasses
            lens_type = random.choice(LENS_TYPES_EYEGLASSES)
            shape = random.choice(FRAME_SHAPES)
            color = random.choice(FRAME_COLORS)
            frame_type = random.choice(FRAME_TYPES)
            frame_shape = shape
            frame_material = random.choice(FRAME_MATERIALS)
            frame_color = color
            product_name = f"{brand} {collection}{shape.replace('_', ' ').title()} {color.replace('_', ' ').title()} {model_num}"

        # Vendor assignment
        if brand in ("Vincent Chase", "Lenskart Air", "Lenskart Blu", "Hooper", "Hustlr", "Lenskart Junior"):
            vendor_id = "VND001"
        elif brand == "John Jacobs":
            vendor_id = random.choice(["VND001", "VND004"])
        elif brand in ("Ray-Ban", "Oakley", "Vogue Eyewear"):
            vendor_id = "VND002"
        elif brand in ("Carrera", "Tommy Hilfiger", "Hugo Boss", "Polaroid"):
            vendor_id = "VND008"
        elif brand in ("Fossil", "GUESS"):
            vendor_id = "VND009"
        elif brand == "New Balance":
            vendor_id = "VND010"
        elif brand == "Owndays":
            vendor_id = "VND004"
        elif brand == "Lee Cooper":
            vendor_id = random.choice(["VND004", "VND011"])
        elif brand == "Bausch & Lomb":
            vendor_id = "VND005"
        elif brand == "Acuvue":
            vendor_id = random.choice(["VND005", "VND006"])
        elif brand == "Alcon":
            vendor_id = "VND007"
        elif brand == "CooperVision":
            vendor_id = "VND006"
        elif brand in ("Aqua", "Aquacolor", "Aqualens"):
            vendor_id = "VND012"
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
            gender = random.choice(["F", "Unisex"])
        elif brand == "Lenskart Junior":
            gender = "Kids"
        elif brand in ("Hugo Boss", "Oakley"):
            gender = random.choice(["M", "Unisex"])

        # Cost price varies by brand type
        if brand in INHOUSE_BRANDS:
            cost_ratio = random.uniform(0.20, 0.35)
        elif brand in CL_BRANDS:
            cost_ratio = random.uniform(0.35, 0.50)
        else:
            cost_ratio = random.uniform(0.40, 0.55)

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
            "cost_price": round(mrp * cost_ratio, 2),
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
    """Stream daily sales directly to CSV to avoid OOM.

    With 2000 stores we sample a subset of stores each day to keep file size
    manageable while still producing millions of rows.
    """
    eyeglass_skus = [s for s in skus if s["category"] in ("eyeglasses", "computer_glasses") and not s["is_display_only"]]
    sunglass_skus = [s for s in skus if s["category"] == "sunglasses"]
    cl_skus = [s for s in skus if s["category"] == "contact_lenses"]
    display_skus = [s for s in skus if s["is_display_only"]]

    csv_out = StreamingCSV("daily_sales.csv", SALES_FIELDS)

    # With 2000 stores, sample a fraction each day to keep output ~5-8M rows
    daily_store_fraction = 0.15 if not LITE_MODE else 1.0

    for d_offset in range(NUM_DAYS):
        d = START_DATE + timedelta(days=d_offset)
        season_mult, promo = seasonal_multiplier(d)
        wknd_mult = weekend_multiplier(d)
        sun_mult = sunglasses_seasonality(d)

        day_stores = stores if LITE_MODE else random.sample(stores, max(1, int(len(stores) * daily_store_fraction)))

        for store in day_stores:
            if not store["is_active"]:
                continue
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
    """Stream daily inventory snapshots to CSV.

    With 2000 stores we snapshot weekly and sample stores to keep output manageable.
    """
    physical_skus = [s for s in skus if not s["is_display_only"]]
    display_skus = [s for s in skus if s["is_display_only"]]

    csv_out = StreamingCSV("daily_inventory.csv", INVENTORY_FIELDS)

    # Sample stores for inventory (all in lite, fraction in full)
    inv_stores = stores if LITE_MODE else random.sample(stores, min(500, len(stores)))

    for store in inv_stores:
        if not store["is_active"]:
            continue
        cap = store["display_capacity"]
        store_physical = random.sample(physical_skus, min(random.randint(30 if LITE_MODE else 100, 60 if LITE_MODE else 250), len(physical_skus)))
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

    # Sample stores for trials
    trial_stores = stores if LITE_MODE else random.sample(stores, min(400, len(stores)))

    for d_offset in range(NUM_DAYS):
        d = START_DATE + timedelta(days=d_offset)
        season_mult, _ = seasonal_multiplier(d)
        wknd_mult = weekend_multiplier(d)

        for store in trial_stores:
            if not store["is_active"]:
                continue
            cluster = STORE_CLUSTERS[store["store_cluster"]]
            n_trials = max(1, int(cluster["base_traffic"] * 0.3 * season_mult * wknd_mult * random.uniform(0.5, 1.5)))
            if LITE_MODE:
                n_trials = min(n_trials, 10)
            else:
                n_trials = min(n_trials, 40)

            for _ in range(n_trials):
                trial_id += 1
                sku = random.choice(display_skus)
                conversion = random.random() < cluster["conversion"]
                csv_out.write({
                    "trial_id": f"TRL{trial_id:08d}",
                    "store_id": store["store_id"], "sku_id": sku["sku_id"],
                    "trial_date": d.isoformat(),
                    "trial_timestamp": f"{d.isoformat()} {random.randint(10, 20)}:{random.randint(0, 59):02d}:00",
                    "customer_id": f"CUST{random.randint(1, 500000):06d}" if random.random() < 0.5 else "",
                    "resulted_in_order": conversion,
                    "order_id": f"ORD{random.randint(1, 9999999):07d}" if conversion else "",
                })

    csv_out.close()


EYE_TEST_FIELDS = ["test_id", "store_id", "test_date", "customer_id",
                   "sph_right", "cyl_right", "sph_left", "cyl_left",
                   "resulted_in_purchase", "order_id"]

def generate_eye_tests_streaming(stores: list[dict]):
    """Stream eye test data to CSV."""
    csv_out = StreamingCSV("eye_tests.csv", EYE_TEST_FIELDS)
    test_id = 0

    # Sample stores
    test_stores = stores if LITE_MODE else random.sample(stores, min(500, len(stores)))

    for d_offset in range(NUM_DAYS):
        d = START_DATE + timedelta(days=d_offset)
        season_mult, _ = seasonal_multiplier(d)
        wknd_mult = weekend_multiplier(d)

        for store in test_stores:
            if not store["is_active"]:
                continue
            cluster = STORE_CLUSTERS[store["store_cluster"]]
            n_tests = max(0, int(cluster["base_traffic"] * 0.08 * season_mult * wknd_mult * random.uniform(0.5, 1.5)))

            for _ in range(n_tests):
                test_id += 1
                resulted_in_purchase = random.random() < 0.75
                csv_out.write({
                    "test_id": f"EYE{test_id:08d}",
                    "store_id": store["store_id"], "test_date": d.isoformat(),
                    "customer_id": f"CUST{random.randint(1, 500000):06d}",
                    "sph_right": round(random.uniform(-6.0, 4.0), 2),
                    "cyl_right": round(random.uniform(-3.0, 0.0), 2),
                    "sph_left": round(random.uniform(-6.0, 4.0), 2),
                    "cyl_left": round(random.uniform(-3.0, 0.0), 2),
                    "resulted_in_purchase": resulted_in_purchase,
                    "order_id": f"ORD{random.randint(1, 9999999):07d}" if resulted_in_purchase else "",
                })

    csv_out.close()


def generate_receipts(stores: list[dict], skus: list[dict]) -> list[dict]:
    rows = []
    receipt_id = 0
    physical_skus = [s for s in skus if not s["is_display_only"]]

    # Sample stores for receipts
    receipt_stores = stores if LITE_MODE else random.sample(stores, min(500, len(stores)))

    for d_offset in range(0, NUM_DAYS, 3):
        d = START_DATE + timedelta(days=d_offset)
        for store in receipt_stores:
            if not store["is_active"]:
                continue
            n_receipts = random.randint(3, 10)
            for _ in range(n_receipts):
                receipt_id += 1
                sku = random.choice(physical_skus)
                rows.append({
                    "receipt_id": f"RCP{receipt_id:08d}",
                    "store_id": store["store_id"],
                    "sku_id": sku["sku_id"],
                    "receipt_date": d.isoformat(),
                    "qty_received": random.randint(2, 30),
                    "source_type": random.choices(["warehouse", "vendor_direct", "transfer"], weights=[0.6, 0.25, 0.15])[0],
                    "source_id": random.choice(["WH_NORTH", "WH_SOUTH", "WH_WEST", "WH_EAST", "WH_CENTRAL"]),
                    "po_id": f"PO{random.randint(1, 10000):06d}" if random.random() < 0.7 else "",
                })
    return rows


def generate_transfers(stores: list[dict], skus: list[dict]) -> list[dict]:
    rows = []
    transfer_id = 0
    physical_skus = [s for s in skus if not s["is_display_only"]]

    for d_offset in range(0, NUM_DAYS, 7):
        d = START_DATE + timedelta(days=d_offset)
        n_transfers = random.randint(10, 40)
        for _ in range(n_transfers):
            transfer_id += 1
            from_store, to_store = random.sample(stores, 2)
            sku = random.choice(physical_skus)
            qty = random.randint(1, 15)
            reason = random.choices(["rebalance", "stockout_prevention", "eol_clearance", "new_store_fill"], weights=[0.45, 0.30, 0.15, 0.10])[0]

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

            n_lines = random.randint(5, 25)
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
    # Sample stores for traffic
    traffic_stores = stores if LITE_MODE else random.sample(stores, min(500, len(stores)))

    for d_offset in range(NUM_DAYS):
        d = START_DATE + timedelta(days=d_offset)
        season_mult, _ = seasonal_multiplier(d)
        wknd_mult = weekend_multiplier(d)

        for store in traffic_stores:
            if not store["is_active"]:
                continue
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


# ─── Granular store traffic (hourly x demographics) ─────────────────────────

STORE_HOURS = list(range(10, 22))  # 10 AM to 9 PM

HOURLY_WEIGHTS = {
    10: 0.04, 11: 0.06, 12: 0.10, 13: 0.09, 14: 0.07,
    15: 0.06, 16: 0.07, 17: 0.09, 18: 0.12, 19: 0.13,
    20: 0.10, 21: 0.07,
}

AGE_GROUPS = ["18-24", "25-34", "35-44", "45-54", "55+"]
AGE_WEIGHTS = [0.18, 0.35, 0.25, 0.14, 0.08]

AFFLUENCE_SEGMENTS = ["budget", "mid", "premium", "luxury"]
AFFLUENCE_BY_CLUSTER = {
    "METRO_FLAGSHIP": [0.05, 0.20, 0.40, 0.35],
    "METRO_HIGH":  [0.10, 0.25, 0.40, 0.25],
    "METRO_MID":   [0.15, 0.35, 0.35, 0.15],
    "TIER1_HIGH":  [0.20, 0.40, 0.30, 0.10],
    "TIER1_MID":   [0.25, 0.40, 0.25, 0.10],
    "TIER2":       [0.35, 0.40, 0.20, 0.05],
    "TIER3":       [0.40, 0.40, 0.15, 0.05],
    "KIOSK":       [0.20, 0.35, 0.30, 0.15],
    "AIRPORT":     [0.05, 0.20, 0.40, 0.35],
}

TRAFFIC_DETAIL_FIELDS = [
    "store_id", "traffic_date", "hour", "gender", "age_group",
    "affluence_segment", "visitor_count", "tried_product", "made_purchase",
]


def generate_store_traffic_detail_streaming(stores: list[dict]):
    """Stream hourly demographic traffic data to CSV."""
    csv_out = StreamingCSV("store_traffic_detail.csv", TRAFFIC_DETAIL_FIELDS)

    step = 14 if not LITE_MODE else 14
    detail_stores = stores if LITE_MODE else random.sample(stores, min(200, len(stores)))

    for d_offset in range(0, NUM_DAYS, step):
        d = START_DATE + timedelta(days=d_offset)
        season_mult, _ = seasonal_multiplier(d)
        wknd_mult = weekend_multiplier(d)

        for store in detail_stores:
            if not store["is_active"]:
                continue
            cluster = STORE_CLUSTERS[store["store_cluster"]]
            daily_base = cluster["base_traffic"]
            daily_total = max(1, int(daily_base * season_mult * wknd_mult * random.uniform(0.6, 1.4)))
            affluence_weights = AFFLUENCE_BY_CLUSTER[store["store_cluster"]]

            for hour in STORE_HOURS:
                hour_traffic = max(1, int(daily_total * HOURLY_WEIGHTS[hour] * random.uniform(0.7, 1.3)))

                for gender in ["M", "F"]:
                    gender_share = random.uniform(0.45, 0.55) if gender == "M" else None
                    if gender_share is None:
                        gender_share = 1.0 - random.uniform(0.45, 0.55)
                    gender_traffic = max(0, int(hour_traffic * gender_share))

                    if gender_traffic == 0:
                        continue

                    age_group = random.choices(AGE_GROUPS, weights=AGE_WEIGHTS)[0]
                    affluence = random.choices(AFFLUENCE_SEGMENTS, weights=affluence_weights)[0]

                    tried = int(gender_traffic * random.uniform(0.2, 0.5))
                    purchased = int(tried * cluster["conversion"] * random.uniform(0.5, 1.5))

                    csv_out.write({
                        "store_id": store["store_id"],
                        "traffic_date": d.isoformat(),
                        "hour": hour,
                        "gender": gender,
                        "age_group": age_group,
                        "affluence_segment": affluence,
                        "visitor_count": gender_traffic,
                        "tried_product": tried,
                        "made_purchase": purchased,
                    })

    csv_out.close()


# ─── Staff / sales associate data ───────────────────────────────────────────

STAFF_ROLES = ["optometrist", "sales_associate", "store_manager", "senior_associate"]
STAFF_ROLE_WEIGHTS = [0.15, 0.55, 0.10, 0.20]

STAFF_COUNT_BY_FORMAT = {
    "flagship": (12, 20),
    "large": (8, 15),
    "medium": (5, 10),
    "small": (3, 6),
    "kiosk": (2, 4),
}

FIRST_NAMES = [
    "Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh", "Ayaan", "Krishna", "Ishaan",
    "Ananya", "Saanvi", "Aanya", "Isha", "Pari", "Diya", "Priya", "Meera", "Kavya", "Riya",
    "Rohan", "Amit", "Rahul", "Suresh", "Deepak", "Neha", "Pooja", "Sneha", "Anjali", "Swati",
    "Vikram", "Nikhil", "Manish", "Gaurav", "Akash", "Shruti", "Pallavi", "Tanvi", "Nisha", "Divya",
    "Harsh", "Karan", "Pranav", "Dhruv", "Siddharth", "Aditi", "Simran", "Ritika", "Nikita", "Sakshi",
    "Yash", "Dev", "Raj", "Om", "Abhi", "Bhavna", "Komal", "Megha", "Shweta", "Tanya",
]
LAST_NAMES = [
    "Sharma", "Verma", "Patel", "Gupta", "Singh", "Kumar", "Reddy", "Nair", "Iyer", "Joshi",
    "Mehta", "Shah", "Chopra", "Malhotra", "Bhat", "Rao", "Das", "Mukherjee", "Banerjee", "Pillai",
    "Agarwal", "Khanna", "Kapoor", "Sinha", "Mishra", "Pandey", "Tiwari", "Yadav", "Chauhan", "Saxena",
    "Bhatt", "Desai", "Kulkarni", "Jain", "Thakur", "Bose", "Sen", "Ghosh", "Dutta", "Roy",
]


def generate_staff(stores: list[dict]) -> list[dict]:
    """Generate staff roster for each store."""
    staff = []
    staff_id = 0

    for store in stores:
        if not store["is_active"]:
            continue
        min_staff, max_staff = STAFF_COUNT_BY_FORMAT[store["store_format"]]
        n_staff = random.randint(min_staff, max_staff)

        for _ in range(n_staff):
            staff_id += 1
            role = random.choices(STAFF_ROLES, weights=STAFF_ROLE_WEIGHTS)[0]
            join_date = START_DATE - timedelta(days=random.randint(30, 1500))
            is_active = random.random() < 0.92

            staff.append({
                "staff_id": f"EMP{staff_id:05d}",
                "store_id": store["store_id"],
                "staff_name": f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}",
                "role": role,
                "join_date": join_date.isoformat(),
                "is_active": is_active,
                "monthly_target_units": {"optometrist": 0, "sales_associate": 80,
                                         "store_manager": 40, "senior_associate": 100}[role],
                "monthly_target_revenue": {"optometrist": 0, "sales_associate": 150000,
                                           "store_manager": 100000, "senior_associate": 250000}[role],
            })
    return staff


STAFF_SALES_FIELDS = [
    "staff_id", "store_id", "sale_date", "sku_id", "category", "brand",
    "qty_sold", "revenue", "was_upsell", "customer_rating",
]


def generate_staff_sales_streaming(stores: list[dict], skus: list[dict], staff: list[dict]):
    """Stream staff-level sales performance data to CSV."""
    csv_out = StreamingCSV("staff_sales.csv", STAFF_SALES_FIELDS)

    staff_by_store = {}
    for emp in staff:
        if emp["is_active"] and emp["role"] in ("sales_associate", "senior_associate", "store_manager"):
            staff_by_store.setdefault(emp["store_id"], []).append(emp)

    sellable_skus = [s for s in skus if not s["is_display_only"]]

    step = 7 if not LITE_MODE else 7
    staff_stores = stores if LITE_MODE else random.sample(stores, min(300, len(stores)))

    for d_offset in range(0, NUM_DAYS, step):
        d = START_DATE + timedelta(days=d_offset)
        season_mult, _ = seasonal_multiplier(d)
        wknd_mult = weekend_multiplier(d)

        for store in staff_stores:
            if not store["is_active"]:
                continue
            store_staff = staff_by_store.get(store["store_id"], [])
            if not store_staff:
                continue

            cluster = STORE_CLUSTERS[store["store_cluster"]]
            daily_sales = max(1, int(cluster["base_traffic"] * cluster["conversion"]
                                     * season_mult * wknd_mult * random.uniform(0.4, 1.2)))

            for _ in range(daily_sales):
                emp = random.choice(store_staff)
                sku = random.choice(sellable_skus)
                qty = random.choices([1, 2], weights=[0.85, 0.15])[0]
                was_upsell = random.random() < 0.15
                rating = random.choices([0, 3, 4, 5], weights=[0.5, 0.10, 0.20, 0.20])[0]

                csv_out.write({
                    "staff_id": emp["staff_id"],
                    "store_id": store["store_id"],
                    "sale_date": d.isoformat(),
                    "sku_id": sku["sku_id"],
                    "category": sku["category"],
                    "brand": sku["brand"],
                    "qty_sold": qty,
                    "revenue": round(sku["mrp"] * qty * random.uniform(0.85, 1.0), 2),
                    "was_upsell": was_upsell,
                    "customer_rating": rating,
                })

    csv_out.close()


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
    for sku in random.sample(eol_skus, min(50, len(eol_skus))):
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

    print("[1/14] Generating stores...")
    stores = generate_stores()
    write_csv("stores.csv", stores)

    print("[2/14] Generating vendors...")
    vendors = generate_vendors()
    write_csv("vendors.csv", vendors)

    print("[3/14] Generating SKUs...")
    skus = generate_skus(vendors)
    write_csv("skus.csv", skus)

    print("[4/14] Generating calendar...")
    calendar = generate_calendar()
    write_csv("calendar.csv", calendar)

    print("[5/14] Generating daily sales (streaming to disk)...")
    generate_daily_sales_streaming(stores, skus)

    print("[6/14] Generating inventory snapshots (streaming to disk)...")
    generate_daily_inventory_streaming(stores, skus)

    print("[7/14] Generating receipts...")
    receipts = generate_receipts(stores, skus)
    write_csv("receipts.csv", receipts)

    print("[8/14] Generating store trials (streaming to disk)...")
    generate_store_trials_streaming(stores, skus)

    print("[9/14] Generating eye tests (streaming to disk)...")
    generate_eye_tests_streaming(stores)

    print("[10/14] Generating transfers...")
    transfers = generate_transfers(stores, skus)
    write_csv("transfers.csv", transfers)

    print("[11/14] Generating purchase orders, traffic, promotions...")
    pos = generate_purchase_orders(vendors, skus)
    write_csv("purchase_orders.csv", pos)
    traffic = generate_store_traffic(stores)
    write_csv("store_traffic.csv", traffic)
    promos = generate_promotions(skus)
    write_csv("promotions.csv", promos)

    print("[12/14] Generating granular store traffic (hourly x demographics)...")
    generate_store_traffic_detail_streaming(stores)

    print("[13/14] Generating staff roster...")
    staff = generate_staff(stores)
    write_csv("staff.csv", staff)

    print("[14/14] Generating staff sales performance (streaming to disk)...")
    generate_staff_sales_streaming(stores, skus, staff)

    print()
    print("Done! Files written to:", OUTPUT_DIR)


if __name__ == "__main__":
    main()
