export const SITE = {
  name: 'Darkins Chocolates',
  domain: 'https://darkins.com',
  tagline: 'Bean-to-bar chocolate from single-origin Indian cacao',
  description:
    'Darkins is an Indian bean-to-bar craft chocolate brand. Single-origin cacao from Karnataka, Tamil Nadu and Andhra Pradesh, roasted and stone-ground in our Delhi studio. Natural, vegan, gluten-free.',
  email: 'hello@darkins.in',
  phone: '+91 88003 35220',
  whatsapp: 'https://wa.me/918800335220',
  address: '2nd Floor, B-108, Pocket B, Okhla Phase I, New Delhi 110020',
  social: {
    instagram: 'https://www.instagram.com/darkinschocolate/',
    facebook: 'https://www.facebook.com/darkinschocolate/',
    x: 'https://twitter.com/darkinschocolat',
    youtube: 'https://www.youtube.com/@darkinschocolate',
  },
} as const;

export const CATEGORIES: Record<string, string> = {
  bars: 'Bars',
  'tasting-packs': 'Tasting Packs',
  combos: 'Combo Packs',
  dragees: 'Dragées',
  spreads: 'Spreads',
  drinks: 'Chocolate Drinks',
  gifting: 'Gifting',
  couvertures: 'Couvertures',
};

export interface ProductImage {
  base: string;
  widths: number[];
  role: 'packshot' | 'lifestyle' | 'values' | 'nutrition';
  width: number | null;
  height: number | null;
  alt: string;
}

export interface BuyLink {
  retailer: string;
  label: string;
  url: string;
}

export interface Product {
  id: string;
  name: string;
  category: keyof typeof CATEGORIES;
  cacaoPercent: number | null;
  sugarfree: boolean;
  vegan: boolean;
  glutenFree: boolean;
  weight: string;
  mrp: number;
  tastingNotes: string[];
  description: string;
  ingredients: string[];
  images: ProductImage[];
  buyLinks: BuyLink[];
  featured: boolean;
  badges: string[];
  origin?: string;
  roast?: string;
  contents?: string[];
}

/** Build a srcset string from an image record. */
export function srcset(img: { base: string; widths: number[] }): string {
  return img.widths.map((w) => `${img.base}-${w}w.webp ${w}w`).join(', ');
}

/** Largest available file — used for og:image and JSON-LD. */
export function largestSrc(img: { base: string; widths: number[] }): string {
  return `${img.base}-${Math.max(...img.widths)}w.webp`;
}

/** Default rendered src (mid size). */
export function src(img: { base: string; widths: number[] }, target = 960): string {
  const w = img.widths.includes(target) ? target : Math.max(...img.widths);
  return `${img.base}-${w}w.webp`;
}

export function pctBucket(p: Product): 'mid' | 'high' | 'max' | null {
  if (p.cacaoPercent == null) return null;
  if (p.cacaoPercent >= 80) return 'max';
  if (p.cacaoPercent >= 65) return 'high';
  return 'mid';
}
