# REDIRECTS — darkins.in → darkins.com

Suggested 301 map for the DNS cutover. Product slugs were kept identical to
the old Shopify handles wherever possible, so most product redirects are
mechanical. (Two were tidied: see the exceptions table.)

## Pages

| Old (darkins.in) | New (darkins.com) |
|---|---|
| `/` | `/` |
| `/collections` | `/products` |
| `/collections/bar-collection` | `/products?category=bars` |
| `/collections/artisanal-dark-chocolate-bars` | `/products?badge=bestseller` |
| `/collections/combo-packs` | `/products?category=combos` |
| `/collections/tasting-packs` | `/products?category=tasting-packs` |
| `/collections/dragees` | `/products?category=dragees` |
| `/collections/spreads` | `/products?category=spreads` |
| `/collections/gifting` | `/products?category=gifting` |
| `/collections/chocolate-drinks` | `/products?category=drinks` |
| `/collections/covertures` | `/products?category=couvertures` |
| `/collections/collab-products` | `/products` |
| `/collections/experiences-tours` | `/experiences` |
| `/pages/bean-to-bar` | `/process` |
| `/pages/the-makers` | `/story` |
| `/pages/contact-us` | `/contact` |
| `/pages/faqs` | `/story#faq` |
| `/pages/home` | `/` |
| `/blogs/blog` | `/journal` |
| `/blogs/blog/:slug` | `/journal/:slug` |
| `/blogs/news` | `/journal` |
| `/products/:handle` | `/products/:handle` (see exceptions) |
| `/pages/return-refund-and-cancellation-policy` | `/contact` (no on-site sales anymore) |
| `/pages/terms-and-conditions` | `/contact` |
| `/pages/privacy-policy` | `/contact` |

## Product slug exceptions

| Old handle | New slug |
|---|---|
| `valentines-artisanal-chocolate-gift-box-copy` | `valentines-artisanal-chocolate-gift-box` |
| `the-curtain-raiser-best-selling-pack-of-3-darkins-bar` | `the-curtain-raiser-pack-of-3` |
| `chocolate-factory-tour-valentine-edition-7th-feb-2026` | `/experiences` |

## Vercel format (`vercel.json`)

```json
{
  "redirects": [
    { "source": "/collections", "destination": "/products", "permanent": true },
    { "source": "/collections/experiences-tours", "destination": "/experiences", "permanent": true },
    { "source": "/collections/:handle", "destination": "/products", "permanent": true },
    { "source": "/pages/bean-to-bar", "destination": "/process", "permanent": true },
    { "source": "/pages/the-makers", "destination": "/story", "permanent": true },
    { "source": "/pages/contact-us", "destination": "/contact", "permanent": true },
    { "source": "/pages/faqs", "destination": "/story", "permanent": true },
    { "source": "/blogs/blog/:slug", "destination": "/journal/:slug", "permanent": true },
    { "source": "/blogs/:blog", "destination": "/journal", "permanent": true },
    { "source": "/products/valentines-artisanal-chocolate-gift-box-copy", "destination": "/products/valentines-artisanal-chocolate-gift-box", "permanent": true },
    { "source": "/products/the-curtain-raiser-best-selling-pack-of-3-darkins-bar", "destination": "/products/the-curtain-raiser-pack-of-3", "permanent": true },
    { "source": "/products/chocolate-factory-tour-valentine-edition-7th-feb-2026", "destination": "/experiences", "permanent": true }
  ]
}
```

Netlify (`_redirects`) and Cloudflare equivalents are one-liners from the same
table. Query-string variants (`?category=`) work as-is because `/products`
reads filters from the URL.
