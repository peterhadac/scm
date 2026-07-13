// Build-time choropleth data for the origins index (issue #87): world
// country outlines from world-atlas (110m resolution), projected with
// d3-geo in the frontmatter — the browser receives plain colored SVG
// paths, no client-side map library.
import { geoNaturalEarth1, geoPath } from 'd3-geo';
import { feature } from 'topojson-client';
import type { FeatureCollection, Geometry } from 'geojson';
import type { Topology } from 'topojson-specification';
import worldData from 'world-atlas/countries-110m.json';
import { listOrigins, originSlug, type OriginSummary } from './origins';

// Origin keys that aren't a single geographic country — shown as a text
// note under the map, never as a filled shape.
const NON_GEOGRAPHIC = new Set(['Blend', 'Svet']);

// Origin key → world-atlas country name, for the cases where they differ:
// world-atlas abbreviates some names, and a few origins in current data
// are regions or spelling variants that still have one honest home
// country ("Blue Mountain" is definitionally Jamaica; Huila/Tolima are
// Colombian departments — their counts aggregate into Colombia's shade).
const ORIGIN_TO_COUNTRY: Record<string, string> = {
  'Democratic Republic of the Congo': 'Dem. Rep. Congo',
  'Dominican Republic': 'Dominican Rep.',
  'Blue Mountain': 'Jamaica',
  Huila: 'Colombia',
  Tolima: 'Colombia',
  Indonézie: 'Indonesia',
};

// Shade buckets by coffee count — class names map to CSS fills in the
// component. Fixed thresholds (not quantiles) so the same count always
// reads as the same shade week over week.
export function bucketFor(count: number): string {
  if (count >= 25) return 'oc-b4';
  if (count >= 10) return 'oc-b3';
  if (count >= 3) return 'oc-b2';
  if (count >= 1) return 'oc-b1';
  return 'oc-none';
}

export interface CountryShape {
  d: string;
  name: string; // world-atlas display name (map's own label, not localized)
  count: number;
  // Origin key to link/label with (the origin page slug source); null for
  // countries with no coffees.
  originKey: string | null;
  slug: string | null;
  bucket: string;
}

export interface ChoroplethData {
  shapes: CountryShape[];
  // Geographic origins that matched no atlas country — surfaced as a note
  // rather than silently dropped.
  unmatched: OriginSummary[];
  nonGeographic: OriginSummary[];
  width: number;
  height: number;
}

export function buildChoropleth(width = 960, height = 480): ChoroplethData {
  const world = worldData as unknown as Topology;
  const countries = feature(
    world,
    world.objects.countries,
  ) as unknown as FeatureCollection<Geometry, { name: string }>;

  const projection = geoNaturalEarth1().fitSize([width, height], countries);
  const path = geoPath(projection);

  // Aggregate origin counts by atlas country name; the origin with the
  // highest count "owns" the link target (Colombia over Huila/Tolima).
  const byCountry = new Map<string, { count: number; origin: OriginSummary }>();
  const unmatched: OriginSummary[] = [];
  const nonGeographic: OriginSummary[] = [];
  const atlasNames = new Set(countries.features.map((f) => f.properties.name));

  for (const summary of listOrigins()) {
    if (NON_GEOGRAPHIC.has(summary.origin)) {
      nonGeographic.push(summary);
      continue;
    }
    const countryName = ORIGIN_TO_COUNTRY[summary.origin] ?? summary.origin;
    if (!atlasNames.has(countryName)) {
      unmatched.push(summary);
      continue;
    }
    const existing = byCountry.get(countryName);
    if (existing) {
      existing.count += summary.coffeeCount;
      if (summary.coffeeCount > existing.origin.coffeeCount) existing.origin = summary;
    } else {
      byCountry.set(countryName, { count: summary.coffeeCount, origin: summary });
    }
  }

  const shapes: CountryShape[] = [];
  for (const f of countries.features) {
    const d = path(f);
    if (!d) continue;
    const entry = byCountry.get(f.properties.name);
    shapes.push({
      d,
      name: f.properties.name,
      count: entry?.count ?? 0,
      originKey: entry?.origin.origin ?? null,
      slug: entry ? originSlug(entry.origin.origin) : null,
      bucket: bucketFor(entry?.count ?? 0),
    });
  }
  // Colored countries last → painted on top, so their strokes aren't
  // overdrawn by empty neighbours.
  shapes.sort((a, b) => a.count - b.count);

  return { shapes, unmatched, nonGeographic, width, height };
}
