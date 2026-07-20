// Build-time data layer for the coffee table: reads data/products.yaml +
// roasters.yaml and flattens ok-status products into one row per packaging
// tier. Lives outside the component so another view (per-roaster page, map)
// can reuse it, and so it's unit-testable without rendering.
import fs from 'node:fs';
import path from 'node:path';
import yaml from 'js-yaml';

// `url` traces back to a scraped/discovered link — attacker-influenced
// data. Astro escapes text but does NOT neutralize dangerous URL schemes in
// href attributes, so a poisoned page yielding a `javascript:`/`data:` URL
// would run on click (DOM XSS). Allow only http(s) absolute URLs and
// root-relative paths; everything else renders as "#".
export function safeUrl(raw: string | null | undefined): string {
  if (typeof raw !== 'string') return '#';
  const s = raw.trim();
  if (s.startsWith('/') && !s.startsWith('//')) return s; // root-relative, no scheme
  try {
    const u = new URL(s);
    return u.protocol === 'http:' || u.protocol === 'https:' ? s : '#';
  } catch {
    return '#';
  }
}

// Mirrors data/products.schema.yaml's roast_type enum — the canonical
// English keys stored in data/products.yaml.
export type RoastType = 'filter' | 'espresso' | 'nespresso' | 'drip-bag';

interface ProductTier {
  weight_g: number;
  price: number;
  // Present only when this product sells the same weight in more than one
  // form (e.g. whole bean vs ground) — disambiguates such tiers from one
  // another. Absent on every other tier.
  variant?: string;
}

interface ProductEntry {
  name: string;
  url: string;
  origin: string;
  process: string | null;
  roast_type: RoastType;
  status: string;
  last_seen: string;
  packaging: ProductTier[];
  // Present only on multi-origin blends (origin === "Blend", issue #91);
  // blend_origins lists the component countries when the page stated them.
  blend?: true;
  blend_origins?: string[];
  // New optional fields (schema v22: issues #89, #139, #141, #138, #140, #142)
  is_decaffeinated?: boolean;
  stock_status?: string;
  tasting_notes?: string;
  brewing_recommendations?: string;
  sweetness?: number;
  acidity?: number;
  body?: number;
  bitterness?: number;
}

interface Roaster {
  name: string;
  slug: string;
  url: string;
  discount_code?: string;
  referral_url?: string;
}

export interface CoffeeRow {
  name: string;
  roaster: string;
  origin: string;
  process: string | null;
  roast_type: RoastType;
  price: number;
  weight_g: number;
  // Present only when this row's weight collides with a sibling tier of
  // the same product (e.g. whole bean vs ground) — undefined for every
  // other row, dropped by JSON.stringify same as blend/blend_origins below.
  variant?: string;
  url: string;
  last_seen: string;
  // Only set on blends (issue #93) — undefined keys are dropped by
  // JSON.stringify, so coffees.json stays clean for single-origin rows.
  blend?: true;
  blend_origins?: string[];
  // New optional fields (schema v22: issues #89, #139, #141, #138, #140, #142)
  is_decaffeinated?: boolean;
  stock_status?: string;
  tasting_notes?: string;
  brewing_recommendations?: string;
  sweetness?: number;
  acidity?: number;
  body?: number;
  bitterness?: number;
}

function loadYaml<T>(relativePath: string): T {
  const file = path.join(process.cwd(), relativePath);
  return yaml.load(fs.readFileSync(file, 'utf8')) as T;
}

// Explodes each ok-status product's packaging tiers into flat rows, joined
// with the roaster's display name from roasters.yaml by slug — mirrors
// scraper/scrape.py's old flatten_to_coffees(), now run at site-build time
// instead of by the Python scraper.
export function flattenProducts(): CoffeeRow[] {
  const roasterList = loadYaml<{ roasters: Roaster[] }>('roasters.yaml').roasters;
  const roasterBySlug = new Map(roasterList.map((r) => [r.slug, r]));
  const products = loadYaml<Record<string, ProductEntry[]>>('data/products.yaml');

  const seen = new Set<string>();
  const rows: CoffeeRow[] = [];
  for (const [slug, entries] of Object.entries(products)) {
    const roasterName = roasterBySlug.get(slug)?.name ?? slug;
    for (const product of entries) {
      if (product.status !== 'ok') continue;
      for (const tier of product.packaging ?? []) {
        const key = `${product.url}|${tier.weight_g}|${product.roast_type}|${tier.variant ?? ''}`;
        if (seen.has(key)) continue;
        seen.add(key);
        rows.push({
          name: product.name,
          roaster: roasterName,
          origin: product.origin,
          process: product.process,
          roast_type: product.roast_type,
          price: tier.price,
          weight_g: tier.weight_g,
          ...(tier.variant && { variant: tier.variant }),
          url: product.url,
          last_seen: product.last_seen,
          ...(product.blend === true && {
            blend: true as const,
            ...(product.blend_origins?.length && { blend_origins: product.blend_origins }),
          }),
          discount_code: roasterBySlug.get(slug)?.discount_code,
          referral_url: roasterBySlug.get(slug)?.referral_url,
        });
      }
    }
  }
  return rows;
}

export interface RoasterCoffeeCount {
  name: string;
  slug: string;
  url: string;
  count: number;
}

// Counts ok-status products (not packaging tiers, so a coffee sold in
// several weights only counts once) per roaster — used by the homepage
// logo slider to feature the roasters with the deepest current catalogue.
export function topRoastersByCoffeeCount(limit = 12): RoasterCoffeeCount[] {
  const roasterList = loadYaml<{ roasters: Roaster[] }>('roasters.yaml').roasters;
  const products = loadYaml<Record<string, ProductEntry[]>>('data/products.yaml');

  return roasterList
    .map((r) => ({
      name: r.name,
      slug: r.slug,
      url: r.url,
      count: (products[r.slug] ?? []).filter((p) => p.status === 'ok').length,
    }))
    .filter((r) => r.count > 0)
    .sort((a, b) => b.count - a.count)
    .slice(0, limit);
}
