# LINKS_TODO — retailer links that need per-product URLs

The old darkins.in never exposed per-product retailer URLs, so every product
currently falls back to the **Amazon brand store** and a **Blinkit search**:

- Amazon: `https://www.amazon.in/stores/DarkinsChocolates/page/6D8DF4F9-BAC5-4D5F-890A-33F755D6420E`
- Blinkit: `https://blinkit.com/s/?q=darkins`

To make "Buy on Amazon" land on the exact product, collect the ASIN link for
each of the following and replace `buyLinks[].url` in `src/data/products.json`
(the file is plain JSON — no code changes needed):

## Bars (19)
- [ ] 95% Single Origin Dark — Andhra Pradesh
- [ ] 80% Single Origin Dark — Karnataka
- [ ] 70% Single Origin Dark — Andhra Pradesh
- [ ] 55% Single Origin Dark — Tamil Nadu
- [ ] 70% Dark with Blueberries
- [ ] 70% Dark with Almonds
- [ ] 70% Dark with Cranberry & Chilli
- [ ] 65% Dark with Coffee
- [ ] 63% Dark with Paan
- [ ] 63% Dark with Peppermint
- [ ] 63% Dark with Orange
- [ ] 56% Dark with Sanikatta Salt
- [ ] 70% Noir / Almond Crunch / Oranjé (Sugarfree ×3)
- [ ] Mylk Classic / Rice Crispies / Pineapple & Paprika / Fruit & Nuts (×4)

## Everything else
- [ ] Tasting packs ×3, combos ×6, dragees ×3, spreads ×2, hot chocolate ×2

## Known deep links (found during scrape)
- Zepto has at least one live product page:
  `https://www.zeptonow.com/pn/darkins-63-dark-chocolate-orange/pvid/cfa5f23d-e926-41cd-a0be-9f52bdc02767`
  — currently the site uses the Zepto search fallback; swap in per-product
  Zepto links as they're catalogued.

## No URL at all (need answers from Darkins)
- **Adrish** and **Provenance** appear as partners in the old footer but have
  no online links — listed as in-store-only in `src/data/retailers.json`.
- **Flipkart** logo was in the old footer but no brand-store link existed;
  currently a search-results fallback.
- **Couvertures (1kg)** and **gift boxes** point to WhatsApp
  (`wa.me/918800335220`) since the old site handled these as custom orders.
  Confirm this is the desired channel.

## Content gaps inherited from the old site
- Ingredients were never published for: dragees (×3), Choco Hazelnut Elixir,
  couvertures (×2), tasting packs / combos / gift boxes (composition is shown
  instead). Add to `products.json → ingredients` when available.
- Mylk bars' cacao % is not stated anywhere; set to 45 as an editorial
  placeholder — **confirm the real number**.
- Vegan flag is set to `false` (badge hidden) for the dragees and the hazelnut
  spread because the old site made no vegan claim for them — confirm.
- FSSAI licence number is not on the old site; the footer ships with a
  placeholder (`FSSAI Lic. No. — TODO`).
