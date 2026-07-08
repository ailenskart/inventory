#!/usr/bin/env python3
"""One-time importer: merges scraped darkins.in Shopify data with hand-curated
editorial copy and emits src/data/products.json. Image width lists are read
from the files actually present in public/images/products."""
import json, os, re, sys

SCRATCH = sys.argv[1] if len(sys.argv) > 1 else '.'
RAW = json.load(open(os.path.join(SCRATCH, 'products-raw.json')))['products']
IMGDIR = 'public/images/products'

AMAZON = "https://www.amazon.in/stores/DarkinsChocolates/page/6D8DF4F9-BAC5-4D5F-890A-33F755D6420E"
BLINKIT = "https://blinkit.com/s/?q=darkins"
WHATSAPP = "https://wa.me/918800335220"

def amazon_link():  return {"retailer": "amazon",  "label": "Buy on Amazon",    "url": AMAZON}
def blinkit_link(): return {"retailer": "blinkit", "label": "Order on Blinkit", "url": BLINKIT}
def whatsapp_link(label="Order on WhatsApp"): return {"retailer": "whatsapp", "label": label, "url": WHATSAPP}

RETAIL = [amazon_link(), blinkit_link()]
DIRECT = [whatsapp_link()]

# ---- hand-curated editorial layer -------------------------------------------
C = {
  "55-single-origin-dark-chocolate-tamil-nadu": dict(
    name="55% Single Origin Dark — Tamil Nadu", category="bars", cacaoPercent=55,
    tastingNotes=["citrus", "lemongrass", "pine", "nutmeg"],
    description="Our gateway dark. Single-estate cacao from Pollachi, Tamil Nadu, taken through a medium roast and stone-ground slow. It opens bright — citrus and lemongrass — then settles into pine and warm nutmeg.",
    origin="Pollachi, Tamil Nadu", roast="Medium",
    badges=["Single Origin"], buyLinks=RETAIL),
  "70-single-origin-dark-chocolate-andhra-pradesh": dict(
    name="70% Single Origin Dark — Andhra Pradesh", category="bars", cacaoPercent=70,
    tastingNotes=["grape", "plum", "wood", "licorice"],
    description="Cacao from Eluru, on the Andhra coast that grows some of India's most expressive beans. Deep grape and plum sweetness gives way to wood and a whisper of licorice. Three ingredients, nothing to hide behind.",
    origin="Eluru, Andhra Pradesh", roast="Mild to medium",
    badges=["Single Origin"], buyLinks=RETAIL),
  "80-single-origin-dark-chocolate-karnataka": dict(
    name="80% Single Origin Dark — Karnataka", category="bars", cacaoPercent=80,
    tastingNotes=["banana", "vanilla", "bread", "sage"],
    description="Intense, never bitter. Puttur cacao from Karnataka opens with an improbable sweetness of banana and vanilla, then lands on warm bread and sage. Proof that a big number can still be gentle.",
    origin="Puttur, Karnataka", roast="Mild to medium",
    badges=["Single Origin"], buyLinks=RETAIL),
  "95-single-origin-dark-chocolate-andhra": dict(
    name="95% Single Origin Dark — Andhra Pradesh", category="bars", cacaoPercent=95,
    tastingNotes=["almond", "smoke", "wood", "grape"],
    description="Nearly naked cacao. Grown in Eluru on a farm run by a matriarch who holds the region's best practices to account — and it shows in the bean. Almond and smoke up front, wood and grape underneath. For people who mean it.",
    origin="Eluru, Andhra Pradesh", roast="Medium",
    badges=["Single Origin"], buyLinks=RETAIL),
  "70-dark-chocolate-with-blueberries": dict(
    name="70% Dark Chocolate with Blueberries", category="bars", cacaoPercent=70,
    tastingNotes=["dark berries", "jammy tang", "long cocoa finish"],
    description="The blues buster. Deep 70% cacao brightened with whole dehydrated blueberries — jammy, tart, and gone far too soon. Our most-loved bar, and the one we run out of first.",
    roast="Medium", badges=["Bestseller"], featured=True, buyLinks=RETAIL),
  "70-dark-chocolate-with-almonds": dict(
    name="70% Dark Chocolate with Almonds", category="bars", cacaoPercent=70,
    tastingNotes=["toasted almond", "deep cocoa", "clean snap"],
    description="The old-school pairing that never misses: crunchy roasted almonds folded through smooth 70% dark. The friend for all seasons.",
    roast="Medium", badges=["Bestseller"], buyLinks=RETAIL),
  "70-dark-chocolate-with-cranberry-and-chilli": dict(
    name="70% Dark Chocolate with Cranberry & Chilli", category="bars", cacaoPercent=70,
    tastingNotes=["tart cranberry", "slow heat", "pink salt"],
    description="Tangy cranberries, a pinch of Himalayan pink salt, and just enough bhut jolokia to make itself known on the way out. If you like your dark chocolate with a little heat, this one's yours.",
    roast="Medium", badges=["Bestseller"], featured=True, buyLinks=RETAIL),
  "65-dark-chocolate-with-coffee": dict(
    name="65% Dark Chocolate with Coffee", category="bars", cacaoPercent=65,
    tastingNotes=["Coorg coffee", "roasted nib", "molasses"],
    description="Mild-roast coffee from the hills of Coorg, blended into intense coastal Andhra cacao. For late-night work routines — or simply because you like coffee.",
    roast="Medium", badges=[], featured=True, buyLinks=RETAIL),
  "63-artisanal-dark-chocolate-with-paan": dict(
    name="63% Dark Chocolate with Paan", category="bars", cacaoPercent=63,
    tastingNotes=["betel leaf", "fennel", "rose", "cardamom"],
    description="A nouveau twist on Banarasi paan: cherry, paan leaf, fennel, cardamom and a breath of rose, set in 63% dark. A mignardise to end any feast — India in one square.",
    roast="Medium", badges=[], featured=True, buyLinks=RETAIL),
  "63-artisanal-dark-chocolate-with-peppermint": dict(
    name="63% Dark Chocolate with Peppermint", category="bars", cacaoPercent=63,
    tastingNotes=["peppermint", "petrichor", "cool cocoa"],
    description="Earthy peppermint over smooth 63% dark — like refreshing poetry with petrichor. Cooling, clean, quietly addictive.",
    roast="Medium", badges=[], buyLinks=RETAIL),
  "63-artisanal-dark-chocolate-with-orange": dict(
    name="63% Dark Chocolate with Orange", category="bars", cacaoPercent=63,
    tastingNotes=["orange zest", "candied peel", "bittersweet cocoa"],
    description="Everyone's favourite pair. Tangy orange with a zesty bite, drowned in smooth 63% dark. Winter sunshine, all year.",
    roast="Medium", badges=[], buyLinks=RETAIL),
  "56-artisanal-dark-chocolate-with-sanikatta-salt": dict(
    name="56% Dark Chocolate with Sanikatta Salt", category="bars", cacaoPercent=56,
    tastingNotes=["sea salt", "caramel", "mellow cocoa"],
    description="Hand-sieved freshwater salt crystals from the Aghanashini river beds — a three-century-old salt-making tradition — scattered through mild 56% dark. The ideal blend of sweet and savoury.",
    roast="Medium", badges=[], featured=True, buyLinks=RETAIL),
  "70-dark-chocolate-noir-sugarfree": dict(
    name="70% Dark Chocolate Noir (Sugarfree)", category="bars", cacaoPercent=70, sugarfree=True,
    tastingNotes=["pure cacao", "espresso", "clean finish"],
    description="Dark chocolate in its most honest form: no added sugar, no flavour distractions. Deep, intense cocoa sweetened gently with maltitol. Uncompromising, and proud of it.",
    roast="Medium", badges=["Sugarfree"], buyLinks=RETAIL),
  "70-dark-chocolate-almond-crunch-sugarfree": dict(
    name="70% Dark Chocolate Almond Crunch (Sugarfree)", category="bars", cacaoPercent=70, sugarfree=True,
    tastingNotes=["roasted almond", "toast", "dark cocoa"],
    description="Texture with intensity. Rich 70% cacao generously studded with roasted almonds, with no added sugar — a satisfying crunch in every bite.",
    roast="Medium", badges=["Sugarfree"], buyLinks=RETAIL),
  "70-dark-chocolate-oranje": dict(
    name="70% Dark Chocolate Oranjé (Sugarfree)", category="bars", cacaoPercent=70, sugarfree=True,
    tastingNotes=["orange", "citrus oil", "bright cocoa"],
    description="Deep, intense cacao lifted with real orange peel and a hint of lemon — sugarfree, and all the brighter for it. Bold, refreshing, clean.",
    roast="Medium", badges=["Sugarfree"], buyLinks=RETAIL),
  "mylk-chocolate-classic": dict(
    name="Mylk Chocolate Classic", category="bars", cacaoPercent=45,
    tastingNotes=["coconut cream", "cashew", "soft cocoa"],
    description="Our dairy-free answer to milk chocolate: cacao rounded out with coconut milk and cashew for a melt-in-the-mouth creaminess. All the comfort, none of the dairy.",
    badges=["Mylk"], buyLinks=RETAIL),
  "mylk-chocolate-with-rice-crispies": dict(
    name="Mylk Chocolate with Rice Crispies", category="bars", cacaoPercent=45,
    tastingNotes=["toasted rice", "coconut", "caramel"],
    description="Velvety plant-based mylk chocolate threaded with golden rice crispies — smoothness and delicate crunch in the same bite.",
    badges=["Mylk"], buyLinks=RETAIL),
  "mylk-chocolate-with-pineapple-paprika": dict(
    name="Mylk Chocolate with Pineapple & Paprika", category="bars", cacaoPercent=45,
    tastingNotes=["ripe pineapple", "smoked paprika", "sea salt"],
    description="Tropical pineapple and a flicker of paprika heat over creamy coconut-cashew mylk. A sensory field trip disguised as a chocolate bar.",
    badges=["Mylk"], featured=True, buyLinks=RETAIL),
  "mylk-chocolate-with-fruit-nuts": dict(
    name="Mylk Chocolate with Fruit & Nuts", category="bars", cacaoPercent=45,
    tastingNotes=["raisin", "almond", "cashew cream"],
    description="A medley of almonds, cashews and vibrant raisins folded through dairy-free mylk chocolate. The timeless indulgence, done the Darkins way.",
    badges=["Mylk"], buyLinks=RETAIL),
  "forever-favourites-artisanal-chocolate-tasting-pack": dict(
    name="Forever Favourites Tasting Pack", category="tasting-packs",
    tastingNotes=["five bars", "35g each", "the crowd-pleasers"],
    description="Five 35g mini bars of the ones everyone asks for: 70% Blueberries, 70% Roasted Almond, 70% Cranberry & Chilli, 63% Orange Zest and 65% Coffee. The safest gift in craft chocolate.",
    contents=["70% Dark with Blueberries · 35g", "70% Dark with Roasted Almond · 35g", "70% Dark with Cranberry & Chilli · 35g", "63% Dark with Orange Zest · 35g", "65% Dark with Coffee · 35g"],
    badges=["Bestseller"], featured=True, buyLinks=RETAIL),
  "a-sweet-life-artisanal-chocolate-tasting-pack": dict(
    name="A Sweet Life Tasting Pack", category="tasting-packs",
    tastingNotes=["five bars", "35g each", "the adventurous side"],
    description="Five 35g mini bars for the curious: 63% Banarasi Paan, 63% Orange Zest, 56% Sanikatta Salt, Mylk Pineapple & Paprika and Mylk Fruit & Nuts. India's pantry, in chocolate form.",
    contents=["63% Dark with Banarasi Paan · 35g", "63% Dark with Orange Zest · 35g", "56% Dark with Sanikatta Salt · 35g", "Mylk with Pineapple & Paprika · 35g", "Mylk with Fruit & Nuts · 35g"],
    badges=[], buyLinks=RETAIL),
  "explore-your-dark-side-artisanal-chocolate-tasting-pack": dict(
    name="Explore Your Dark Side Tasting Pack", category="tasting-packs",
    tastingNotes=["five bars", "35g each", "for dark devotees"],
    description="Five 35g mini bars that go deep: 80% Karnataka, 70% Andhra, 70% Blueberries, 70% Roasted Almond and 70% Cranberry & Chilli. Work your way up — or dive straight in.",
    contents=["80% Single Origin Karnataka · 35g", "70% Single Origin Andhra · 35g", "70% Dark with Blueberries · 35g", "70% Dark with Roasted Almond · 35g", "70% Dark with Cranberry & Chilli · 35g"],
    badges=[], buyLinks=RETAIL),
  "strawberry-chocolate-pebbles": dict(
    name="Strawberry Chocolate Pebbles", category="dragees",
    tastingNotes=["strawberry jelly", "crisp shell", "dark cocoa"],
    description="Chocolate shots with a velvety strawberry-jelly centre, crafted on Indian cacao. No preservatives, no shortcuts — just joy in every pebble.",
    vegan=False, badges=["Collab"], buyLinks=RETAIL),
  "citrus-blast-dragees": dict(
    name="Citrus Blast Chocolate Pebbles", category="dragees",
    tastingNotes=["orange jelly", "crisp shell", "dark cocoa"],
    description="A tangy blast in each bite you'll keep going back for — chocolate shots wrapped around an orange jelly centre.",
    vegan=False, badges=[], buyLinks=RETAIL),
  "almond-dragees": dict(
    name="Roasted Almond Chocolate Pebbles", category="dragees",
    tastingNotes=["roasted almond", "fine chocolate", "crisp shell"],
    description="Flavourful roasted almonds in fine chocolate with a sweet, crispy finish. Conversation-starters at any gathering — they work with coffee and bubbly alike.",
    vegan=False, badges=[], buyLinks=RETAIL),
  "choco-hazelnut-elixir": dict(
    name="Choco Hazelnut Elixir", category="spreads",
    tastingNotes=["30% hazelnut", "dark cocoa", "no palm oil"],
    description="The perfect hazelnut spread in town: 30% real hazelnuts, no palm oil, no preservatives. Totally delish on toast — dangerously good off the spoon.",
    vegan=False, badges=["Collab"], buyLinks=RETAIL),
  "choco-peanut-elixir": dict(
    name="Choco Peanut Elixir", category="spreads",
    tastingNotes=["crunchy peanut", "dark cocoa", "unrefined sugar"],
    description="Crunchy peanut chocolate spread for your toast, your chapati, or straight-up as is. Natural, vegan and gluten-free — like everything we make.",
    badges=[], buyLinks=RETAIL),
  "hot-chocolate-dark": dict(
    name="Hot Chocolate — Dark", category="drinks",
    tastingNotes=["intense cocoa", "velvet body", "gentle sweetness"],
    description="Real chocolate, made drinkable. Naturally farmed cacao and unrefined cane sugar whisked into a smooth, velvety cup — hot or cold. Six 30g servings per pack.",
    badges=[], buyLinks=RETAIL),
  "hot-chocolate-classic": dict(
    name="Hot Chocolate — Classic", category="drinks",
    tastingNotes=["rounded cocoa", "velvet body", "cosy sweetness"],
    description="The gentler cup: classic hot chocolate crafted from naturally farmed cacao, balanced for everyday comfort. Six 30g servings per pack — works cold, too.",
    badges=[], buyLinks=RETAIL),
  "70-dark-chocolate-couvertures": dict(
    name="70% Dark Chocolate Couverture — 1kg", category="couvertures", cacaoPercent=70,
    tastingNotes=["bakers' grade", "high cocoa butter", "clean snap"],
    description="Our 70% dark in professional form: a 1kg couverture block with high cocoa-butter content for tempering, enrobing, ganache and bakes that deserve real chocolate.",
    badges=["Pro"], buyLinks=DIRECT),
  "55-dark-chocolate-couvertures": dict(
    name="55% Dark Chocolate Couverture — 1kg", category="couvertures", cacaoPercent=55,
    tastingNotes=["bakers' grade", "mellow profile", "easy tempering"],
    description="A mellower 55% couverture in a 1kg block — the workhorse for pastry, desserts and anything that needs smooth, reliable Indian dark chocolate at scale.",
    badges=["Pro"], buyLinks=DIRECT),
  "premium-artisanal-chocolate-gift-box": dict(
    name="Premium Artisanal Chocolate Gift Box", category="gifting",
    tastingNotes=["five bars", "curated", "customisable"],
    description="A curated box of five 35g bars — Blueberries, Roasted Almond, Orange, Sanikatta Salt and Mylk Pineapple & Paprika. Contents can be customised; price follows the picks.",
    contents=["70% Dark with Blueberries · 35g", "70% Dark with Roasted Almond · 35g", "63% Dark with Orange · 35g", "56% Dark with Sanikatta Salt · 35g", "Mylk with Pineapple & Paprika · 35g"],
    badges=[], buyLinks=[whatsapp_link("Order on WhatsApp"), amazon_link()]),
  "valentines-artisanal-chocolate-gift-box-copy": dict(
    id="valentines-artisanal-chocolate-gift-box",
    name="Valentine's Artisanal Chocolate Gift Box", category="gifting",
    tastingNotes=["rose dark bar", "strawberry dragees", "a love letter"],
    description="When words fail, post choco-mail. A written love letter opens the box; the Crimson Rose Chocobar and Strawberry Chocopop dragees do the rest. Seasonal, and worth the wait.",
    contents=["Crimson Rose Chocobar · 50g", "Strawberry Chocopop · 50g", "A love letter"],
    badges=["Seasonal"], buyLinks=[whatsapp_link("Order on WhatsApp"), amazon_link()]),
  "the-curtain-raiser-best-selling-pack-of-3-darkins-bar": dict(
    id="the-curtain-raiser-pack-of-3",
    name="The Curtain Raiser — Pack of 3", category="combos",
    tastingNotes=["three bestsellers", "50g each"],
    description="Our three best-selling bars in one pack: 70% Blueberries, 70% Roasted Almond and 70% Cranberry & Chilli. The right way to meet Darkins.",
    contents=["70% Dark with Blueberries · 50g", "70% Dark with Roasted Almond · 50g", "70% Dark with Cranberry & Chilli · 50g"],
    badges=["Bestseller"], featured=True, buyLinks=RETAIL),
  "nuts-beans": dict(
    name="Nuts & Beans — Pack of 2", category="combos",
    tastingNotes=["almond", "coffee"],
    description="Two 50g bars for the after-dinner crowd: 70% Dark with Almonds and 65% Dark with Coorg Coffee.",
    contents=["70% Dark with Almonds · 50g", "65% Dark with Coffee · 50g"],
    badges=[], buyLinks=RETAIL),
  "berrylicious": dict(
    name="Berrylicious — Pack of 2", category="combos",
    tastingNotes=["blueberry", "cranberry & chilli"],
    description="Two 50g bars, berries first: 70% Dark with Blueberries and 70% Dark with Cranberry & Chilli.",
    contents=["70% Dark with Blueberries · 50g", "70% Dark with Cranberry & Chilli · 50g"],
    badges=[], buyLinks=RETAIL),
  "nuts-meets-berries": dict(
    name="Nuts Meets Berries — Pack of 2", category="combos",
    tastingNotes=["almond", "blueberry"],
    description="Two 50g bars in perfect balance: 70% Dark with Almonds and 70% Dark with Blueberries.",
    contents=["70% Dark with Almonds · 50g", "70% Dark with Blueberries · 50g"],
    badges=[], buyLinks=RETAIL),
  "met-a-four-box-of-4": dict(
    name="Met-A-Four — Box of 4", category="combos",
    tastingNotes=["berries", "beans", "nuts"],
    description="A metaphor for flavours: four Darkins bars spanning berries, beans and nuts — Coffee, Cranberry & Chilli, Blueberry and Almonds.",
    contents=["65% Dark with Coffee", "70% Dark with Cranberry & Chilli", "70% Dark with Blueberries", "70% Dark with Almonds"],
    badges=[], buyLinks=RETAIL),
  "f-r-i-e-n-d-s-box-of-6": dict(
    name="F.R.I.E.N.D.S — Box of 6", category="combos",
    tastingNotes=["six bars", "the full range"],
    description="Six of our best in one box: 70% Blueberry, 70% Cranberry & Chilli, 70% Almonds, 65% Coffee, 70% Andhra and 80% Karnataka. The one where everyone's happy.",
    contents=["70% Dark with Blueberries", "70% Dark with Cranberry & Chilli", "70% Dark with Almonds", "65% Dark with Coffee", "70% Single Origin Andhra", "80% Single Origin Karnataka"],
    badges=[], buyLinks=RETAIL),
}

SKIP = {"chocolate-factory-tour-valentine-edition-7th-feb-2026"}  # lives in experiences.json

def ingredients_from(body):
    m = re.search(r'Ingredients\s*:\s*(.*?)(?:Net Weight|Medium Roast|Natural \||$)', re.sub(r'<[^>]+>', ' ', body or ''), re.S | re.I)
    if not m: return []
    raw = m.group(1).replace('\xa0', ' ')
    parts = re.split(r'[|,]', raw)
    return [re.sub(r'\s+', ' ', p).strip() for p in parts if p.strip() and len(p.strip()) > 1]

def weight_of(v, handle):
    g = v.get('grams') or 0
    if g >= 1000: return f"{g//1000}kg"
    if g > 0: return f"{g}g"
    return {"premium-artisanal-chocolate-gift-box": "5 × 35g",
            "valentines-artisanal-chocolate-gift-box-copy": "2 × 50g + letter"}.get(handle, "")

def images_for(handle, raw_images):
    files = os.listdir(IMGDIR)
    out = []
    for idx, im in enumerate(raw_images[:6], 1):
        base = f"{handle}-{idx}"
        widths = sorted(int(m.group(1)) for f in files
                        if (m := re.fullmatch(re.escape(base) + r'-(\d+)w\.webp', f)))
        if not widths: continue
        src_name = (im['src'].split('?')[0].rsplit('/', 1)[1]).lower()
        if 'nutritional' in src_name or 'ingredient' in src_name: role, alt = 'nutrition', 'Nutrition and ingredients label'
        elif 'brandvalue' in src_name: role, alt = 'values', 'Darkins brand values'
        elif 'lifestyle' in src_name: role, alt = 'lifestyle', 'Lifestyle shot'
        else: role, alt = 'packshot', 'Product photo'
        out.append({"base": f"/images/products/{base}", "widths": widths, "role": role,
                    "width": im.get('width'), "height": im.get('height'), "alt": alt})
    # gallery order: packshots/lifestyle first, labels last
    out.sort(key=lambda i: {'packshot': 0, 'lifestyle': 1, 'values': 2, 'nutrition': 3}[i['role']])
    return out

products = []
for q in RAW:
    h = q['handle']
    if h in SKIP: continue
    cur = C[h]
    v = q['variants'][0]
    imgs = images_for(h, q['images'])
    for im in imgs:
        if im['role'] == 'packshot': im['alt'] = cur['name']
        elif im['role'] == 'lifestyle': im['alt'] = f"{cur['name']} — lifestyle"
    p = {
        "id": cur.get('id', h),
        "name": cur['name'],
        "category": cur['category'],
        "cacaoPercent": cur.get('cacaoPercent'),
        "sugarfree": cur.get('sugarfree', False),
        "vegan": cur.get('vegan', True),
        "glutenFree": True,
        "weight": weight_of(v, h),
        "mrp": int(float(v['price'])),
        "tastingNotes": cur['tastingNotes'],
        "description": cur['description'],
        "ingredients": ingredients_from(q['body_html']),
        "images": imgs,
        "buyLinks": cur['buyLinks'],
        "featured": cur.get('featured', False),
        "badges": cur['badges'],
    }
    if cur.get('origin'): p['origin'] = cur['origin']
    if cur.get('roast'): p['roast'] = cur['roast']
    if cur.get('contents'): p['contents'] = cur['contents']
    products.append(p)

order = {"bars": 0, "tasting-packs": 1, "combos": 2, "dragees": 3, "spreads": 4,
         "drinks": 5, "gifting": 6, "couvertures": 7}
products.sort(key=lambda p: (order[p['category']], -(p['cacaoPercent'] or 0) if p['category'] == 'bars' else 0, p['name']))

os.makedirs('src/data', exist_ok=True)
with open('src/data/products.json', 'w') as f:
    json.dump(products, f, indent=2, ensure_ascii=False)
print(f"wrote {len(products)} products")
missing = [q['handle'] for q in RAW if q['handle'] not in C and q['handle'] not in SKIP]
if missing: print("MISSING CURATION:", missing)
