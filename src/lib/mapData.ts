// Build-time data for the roaster map (issue #59). Coordinates are
// city-level (town centre, ~4 decimal places) from a hand-maintained table
// — deliberately no geocoding API: the city list is tiny, changes rarely,
// and a build must not depend on a third-party service. A roaster appears
// on the map when roasters.yaml gives it metadata.city AND that city is in
// CITY_COORDS; everything else lands in `unmapped` so the page can say so
// instead of silently omitting them.
import fs from 'node:fs';
import path from 'node:path';
import yaml from 'js-yaml';
import { flattenProducts } from './coffees';

export const CITY_COORDS: Record<string, { lat: number; lng: number }> = {
  Bratislava: { lat: 48.1486, lng: 17.1077 },
  'Dubnica nad Váhom': { lat: 48.96, lng: 18.1708 },
  Golianovo: { lat: 48.2436, lng: 18.1874 },
  Komárno: { lat: 47.7633, lng: 18.1283 },
  'Liptovský Mikuláš': { lat: 49.0842, lng: 19.6122 },
  'Nové Mesto nad Váhom': { lat: 48.757, lng: 17.831 },
  Piešťany: { lat: 48.5905, lng: 17.8271 },
  Prešov: { lat: 48.9986, lng: 21.2339 },
  Topoľčany: { lat: 48.5613, lng: 18.1704 },
  'Veľké Zálužie': { lat: 48.2986, lng: 17.9767 },
  Žilina: { lat: 49.2231, lng: 18.7394 },
};

interface RoasterEntry {
  name: string;
  slug: string;
  url: string;
  metadata?: { city?: string };
}

export interface MapRoaster {
  name: string;
  url: string;
  coffeeCount: number;
}

export interface CityMarker {
  city: string;
  lat: number;
  lng: number;
  roasters: MapRoaster[];
}

export interface MapData {
  markers: CityMarker[];
  unmapped: MapRoaster[];
}

export function buildMapData(): MapData {
  const roasters = (
    yaml.load(fs.readFileSync(path.join(process.cwd(), 'roasters.yaml'), 'utf8')) as {
      roasters: RoasterEntry[];
    }
  ).roasters;

  // Distinct products (not tiers) per roaster display name.
  const countByRoaster = new Map<string, Set<string>>();
  for (const row of flattenProducts()) {
    let urls = countByRoaster.get(row.roaster);
    if (!urls) {
      urls = new Set();
      countByRoaster.set(row.roaster, urls);
    }
    urls.add(row.url);
  }

  const byCity = new Map<string, MapRoaster[]>();
  const unmapped: MapRoaster[] = [];
  for (const r of roasters) {
    const entry: MapRoaster = {
      name: r.name,
      url: r.url,
      coffeeCount: countByRoaster.get(r.name)?.size ?? 0,
    };
    const city = r.metadata?.city;
    if (city && CITY_COORDS[city]) {
      const group = byCity.get(city);
      if (group) group.push(entry);
      else byCity.set(city, [entry]);
    } else {
      unmapped.push(entry);
    }
  }

  const markers = [...byCity.entries()]
    .map(([city, group]) => ({
      city,
      ...CITY_COORDS[city],
      roasters: group.sort((a, b) => a.name.localeCompare(b.name)),
    }))
    .sort((a, b) => a.city.localeCompare(b.city));
  unmapped.sort((a, b) => a.name.localeCompare(b.name));
  return { markers, unmapped };
}
