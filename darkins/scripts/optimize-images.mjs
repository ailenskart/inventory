// One-time importer: converts scraped originals into the sizes the site ships.
// Usage: node scripts/optimize-images.mjs <originals-dir>
import sharp from 'sharp';
import { readdirSync, mkdirSync, existsSync } from 'node:fs';
import { join, parse } from 'node:path';

const src = process.argv[2];
if (!src) { console.error('usage: node scripts/optimize-images.mjs <originals-dir>'); process.exit(1); }

const SIZES = [480, 960, 1600];
const outFor = (name) =>
  name.startsWith('partner-') ? 'public/images/partners' :
  /^(logo|makers|bean-to-bar|blog)/.test(name) ? 'public/images/site' :
  'public/images/products';

for (const dir of ['public/images/products', 'public/images/site', 'public/images/partners']) mkdirSync(dir, { recursive: true });

let done = 0;
for (const file of readdirSync(src)) {
  const { name } = parse(file);
  const outDir = outFor(file);
  const img = sharp(join(src, file));
  const meta = await img.metadata();
  const widths = SIZES.filter(w => w < meta.width);
  if (!widths.length || widths[widths.length - 1] !== Math.min(meta.width, 1600)) widths.push(Math.min(meta.width, 1600));
  for (const w of widths) {
    const out = join(outDir, `${name}-${w}w.webp`);
    if (existsSync(out)) continue;
    await sharp(join(src, file)).resize({ width: w, withoutEnlargement: true }).webp({ quality: 78 }).toFile(out);
  }
  done++;
}
console.log(`optimized ${done} images`);
