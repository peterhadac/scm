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
}

interface Roaster {
  name: string;
  slug: string;
  // Referral partnership (issue #57): when a roaster agrees to a discount
  // code, add `referral: {code: "..."}` to their roasters.yaml entry and
  // their rows grow a copyable code chip. Absent for everyone else.
  referral?: { code?: string };
}

export interface CoffeeRow {
  name: string;
  roaster: string;
  origin: string;
  process: string | null;
  roast_type: RoastType;
  price: number;
  weight_g: number;
  url: string;
  last_seen: string;
  referralCode: string | null;
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
    const roaster = roasterBySlug.get(slug);
    const roasterName = roaster?.name ?? slug;
    const referralCode = roaster?.referral?.code ?? null;
    for (const product of entries) {
      if (product.status !== 'ok') continue;
      for (const tier of product.packaging ?? []) {
        const key = `${product.url}|${tier.weight_g}|${product.roast_type}`;
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
          url: product.url,
          last_seen: product.last_seen,
          referralCode,
        });
      }
    }
  }
  return rows;
}
