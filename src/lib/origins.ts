// Per-origin landing-page data (issue #58): which origins exist, their URL
// slugs, and schema.org JSON-LD for the coffees of one origin. Origin keys
// are the canonical English country names from data/products.yaml (plus
// the "Blend" sentinel), so slugs are stable across languages.
import { flattenProducts, type CoffeeRow } from './coffees';

export function originSlug(origin: string): string {
  return origin.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
}

export interface OriginSummary {
  origin: string;
  slug: string;
  coffeeCount: number; // distinct products, not tiers
  roasterCount: number;
}

export function listOrigins(): OriginSummary[] {
  const byOrigin = new Map<string, { urls: Set<string>; roasters: Set<string> }>();
  for (const row of flattenProducts()) {
    if (!row.origin) continue;
    let entry = byOrigin.get(row.origin);
    if (!entry) {
      entry = { urls: new Set(), roasters: new Set() };
      byOrigin.set(row.origin, entry);
    }
    entry.urls.add(row.url);
    entry.roasters.add(row.roaster);
  }
  return [...byOrigin.entries()]
    .map(([origin, e]) => ({
      origin,
      slug: originSlug(origin),
      coffeeCount: e.urls.size,
      roasterCount: e.roasters.size,
    }))
    .sort((a, b) => b.coffeeCount - a.coffeeCount || a.origin.localeCompare(b.origin));
}

// schema.org ItemList of Product entries (one per product URL, tiers
// folded into an AggregateOffer) for one origin's coffees. Kept to origin
// pages rather than the main table: 30-ish products of JSON-LD is a
// reasonable page-weight cost, ~600 is not.
export function originJsonLd(origin: string, pageUrl: string): string {
  const byUrl = new Map<string, CoffeeRow[]>();
  for (const row of flattenProducts()) {
    if (row.origin !== origin) continue;
    const group = byUrl.get(row.url);
    if (group) group.push(row);
    else byUrl.set(row.url, [row]);
  }

  const items = [...byUrl.values()].map((tiers, i) => {
    const first = tiers[0];
    const prices = tiers.map((t) => t.price);
    const low = Math.min(...prices);
    const high = Math.max(...prices);
    const offers =
      tiers.length === 1
        ? {
            '@type': 'Offer',
            price: low.toFixed(2),
            priceCurrency: 'EUR',
            url: first.url,
          }
        : {
            '@type': 'AggregateOffer',
            lowPrice: low.toFixed(2),
            highPrice: high.toFixed(2),
            priceCurrency: 'EUR',
            offerCount: tiers.length,
            url: first.url,
          };
    return {
      '@type': 'ListItem',
      position: i + 1,
      item: {
        '@type': 'Product',
        name: first.name,
        url: first.url,
        brand: { '@type': 'Brand', name: first.roaster },
        offers,
      },
    };
  });

  return JSON.stringify({
    '@context': 'https://schema.org',
    '@type': 'ItemList',
    url: pageUrl,
    numberOfItems: items.length,
    itemListElement: items,
  });
}
