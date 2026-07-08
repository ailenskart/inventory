# darkins.com

Ground-up redesign of [darkins.in](https://darkins.in) for **Darkins Chocolates** —
an Indian bean-to-bar craft chocolate brand. Concept: **Dark, Indian, Honest.**

This is **not an e-commerce site**: no cart, no checkout, no login. It's a brand
portfolio + product menu — every product's CTA is an outbound "Buy on Amazon" /
"Order on Blinkit" link (with WhatsApp for custom orders and tour bookings).

## Stack

- [Astro 5](https://astro.build) — fully static output, near-zero JS
- Tailwind CSS 4 (via `@tailwindcss/vite`)
- Self-hosted variable fonts: Fraunces (display) × Inter (body), with
  metric-matched fallbacks (zero CLS)
- No client framework. The only JavaScript: reveal-on-scroll, mobile menu,
  retailer dialog, filter URL-sync, outbound-click analytics stub.

## Commands

```bash
npm install
npm run dev        # dev server on :4321
npm run build      # static build to dist/
npm run preview    # serve dist/
```

## Editing content (no code required)

| What | Where |
|---|---|
| Products (copy, prices, badges, buy links) | `src/data/products.json` |
| Factory tours (dates, price, booking) | `src/data/experiences.json` |
| Retail partners (logos, URLs) | `src/data/retailers.json` |
| Journal posts | `src/content/journal/*.md` (HTML bodies, frontmatter for title/date/cover) |
| Brand copy on pages | `src/pages/*.astro` |

Per-product retailer deep links are currently brand-store/search fallbacks —
see **LINKS_TODO.md** for the checklist. Photography gaps are in
**IMAGE_TODO.md**. The darkins.in → darkins.com 301 map is **REDIRECTS.md**
(already wired for Vercel in `vercel.json`).

## Structure

```
src/
  data/            products.json · experiences.json · retailers.json
  content/journal/ 12 posts ported from the old Shopify blog
  layouts/Base.astro     head/SEO/JSON-LD, header, footer, retailer dialog
  components/      Pic, ProductCard, BuyButtons, Badges, OriginMap, …
  pages/           index, products (+[slug]), process, story, experiences,
                   journal (+[slug]), contact, 404, styleguide
  styles/global.css      design tokens + component classes
public/
  images/          all imagery, downloaded from the old CDN → WebP (no hotlinks)
  fonts/           Fraunces + Inter variable, latin subset
scripts/
  optimize-images.mjs    originals → 480/960/1600w WebP
  build-data.py          scraped Shopify JSON + curated copy → products.json
```

## Quality bars (verified)

- Lighthouse (mobile, simulated slow-4G): home **96/100/100/100**,
  products **97/98→100/100/100**, product detail **98/100/100/100**; CLS 0.
  On real 4G (~10 Mbps) LCP lands well under 2s (~230 KB critical path).
- axe-core WCAG 2.1 AA: 0 violations on all page templates.
- Product filtering is pure CSS (`:has()`) — works with JavaScript disabled;
  JS only syncs filter state to the URL. Reveal animations are also no-JS safe.
- `prefers-reduced-motion` respected everywhere.
- JSON-LD: Organization, Product+Offer, BreadcrumbList, HowTo (process),
  FAQPage (story), Event (tours), BlogPosting (journal).
- Sitemap (`@astrojs/sitemap`), robots.txt, canonicals to darkins.com,
  unique titles/descriptions/OG images per page.
- All outbound retailer links: `target="_blank" rel="noopener"` +
  `data-retailer` attribute; GA4/Plausible stub in `Base.astro` tracks them
  once a provider is added.

## Deploy

Static output — Vercel (config included), Netlify or Cloudflare Pages.
Set the domain to `darkins.com`; redirects in `vercel.json` handle old
darkins.in URLs after the DNS switch.
