# IMAGE_TODO — what needs a reshoot or a better source

Everything below is live on the site today using the best asset that could be
recovered from darkins.in / the Shopify CDN. Nothing is hotlinked — all images
are local WebP under `public/images/`. This list is what a photographer /
designer should replace, in priority order.

## Priority 1 — the process page has almost no photography

`/process` is the showpiece page, currently illustrated typographically because
the old site had **one** 480px image for the whole bean-to-bar story
(`public/images/site/bean-to-bar-page-480w.webp`). Shoot one strong image per step:

| # | Step | Suggested shot |
|---|------|----------------|
| 1 | Harvesting | Cacao pods on the tree / machete-opened pod with pulp |
| 2 | Fermenting | Beans in wooden fermentation boxes, mid-turn |
| 3 | Drying | Beans on bamboo drying tables in the sun |
| 4 | Transportation | Jute sacks, tagged, at the Delhi studio |
| 5 | Sorting | Hands sorting beans, rejects in a separate tray |
| 6 | Roasting | Beans going into / coming out of the oven |
| 7 | Cracking & winnowing | Nibs vs. husk separation, fans running |
| 8 | Grinding & conching | The melanger running, chocolate flowing |
| 9 | Tempering | Tempering machine, glossy chocolate curtain |
| 10 | Moulding | Pouring into polycarbonate moulds, tapping bubbles |
| 11 | Wrapping | Hand-wrapping bars in foil |

## Priority 2 — brand / hero photography

- **Hero texture**: full-bleed macro of tempered dark chocolate (snap, gloss,
  melt). Nothing suitable exists; the home hero currently leans on packshots.
- **Founder portrait**: only a 480px square of the chef exists
  (`public/images/site/makers-chef-360w.webp`). Shoot Richa Chaudhary in the
  studio, landscape and portrait crops.
- **Origin/farm imagery**: no photography of the Puttur / Pollachi / Eluru
  farms exists. The origin block on the home page uses a typographic map
  instead. Farm + farmer photos would materially upgrade `/story`.
- **Studio/factory**: tour images 2 and 5 are only 600px
  (`chocolate-factory-tour-...-2`, `-5`). Reshoot wide shots of the Okhla studio.

## Priority 3 — retail partner logos (currently 320px raster)

All nine logos in `public/images/partners/` were recovered at 320×320 from the
old footer. Replace with vector (SVG) or ≥800px versions, ideally monochrome
variants for the dark theme: amazon, blinkit, zepto, bigbasket, flipkart,
urban-platter, the-organic-world, adrish, provenance.

## Priority 4 — journal covers

Blog images were only published at 480px on the old site; they're upscale-free
at `public/images/journal/*-960w.webp` (real width varies). These four posts
had no usable image at all and currently fall back to a brand texture:

- `why-dark-chocolate-is-the-new-superfood`
- `is-chocolate-a-secret-weapon-for-weight-loss-...`
- `cacao-vs-cocoa-what-s-the-real-difference`
- `from-eluru-to-the-cacao-pod-delhi`

## Fine as-is

Product packshots came off the CDN at 1080–2048px and are shipped at
480/960/(≤1600)px WebP — good enough for launch. The nutrition-label and
brand-values graphics per product were also recovered and appear on product
detail pages.
