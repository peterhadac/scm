// Weekly digest data (issue #55): what changed on the Slovak coffee market
// in the most recent scrape, derived entirely at build time from
// data/price_history.csv (issue #41) + the current products.yaml rows.
// No scraper changes: "new" means a tier's first observation carries the
// history's latest date, "price drop/rise" means the latest observation
// differs from the one before it and is dated to the latest run.
import { flattenProducts, type CoffeeRow } from './coffees';
import { loadPriceHistory, historyKey, type PricePoint } from './priceHistory';

export interface PriceChange {
  row: CoffeeRow;
  prevPrice: number;
  prevDate: string;
}

export interface Digest {
  // Date of the newest observation in the history file — null when the
  // file doesn't exist yet (before the first scrape after #50) or is
  // empty; the page shows a "come back after Monday" note instead.
  runDate: string | null;
  // True on the seeding run: the first history append records EVERY tier
  // at once, which would make the digest shout "596 new coffees!" —
  // meaningless as news, so the page explains instead of listing.
  isBaseline: boolean;
  newCoffees: CoffeeRow[];
  drops: PriceChange[];
  rises: PriceChange[];
}

// Above this share of all listed tiers being "new on the same date", the
// data is a baseline seed, not a week's arrivals.
const BASELINE_NEW_FRACTION = 0.3;

export function buildDigest(): Digest {
  const rows = flattenProducts();
  const history = loadPriceHistory();

  let runDate: string | null = null;
  for (const series of history.values()) {
    const last = series[series.length - 1];
    if (last && (runDate === null || last.date > runDate)) runDate = last.date;
  }
  if (runDate === null) {
    return { runDate: null, isBaseline: false, newCoffees: [], drops: [], rises: [] };
  }

  const newCoffees: CoffeeRow[] = [];
  const seenNewUrls = new Set<string>();
  const drops: PriceChange[] = [];
  const rises: PriceChange[] = [];

  for (const row of rows) {
    const series = history.get(historyKey(row.url, row.weight_g));
    if (!series || series.length === 0) continue;
    const last: PricePoint = series[series.length - 1];

    if (series.length === 1 && last.date === runDate) {
      // One tier is enough to call the coffee new — don't list a
      // three-tier product three times.
      if (!seenNewUrls.has(row.url)) {
        seenNewUrls.add(row.url);
        newCoffees.push(row);
      }
      continue;
    }

    if (series.length >= 2 && last.date === runDate) {
      const prev = series[series.length - 2];
      const change = { row, prevPrice: prev.price, prevDate: prev.date };
      if (last.price < prev.price) drops.push(change);
      else if (last.price > prev.price) rises.push(change);
    }
  }

  const isBaseline = rows.length > 0 && newCoffees.length / rows.length > BASELINE_NEW_FRACTION;
  // Biggest saving first reads as news; new arrivals alphabetical.
  drops.sort((a, b) => (b.prevPrice - b.row.price) - (a.prevPrice - a.row.price));
  rises.sort((a, b) => (b.row.price - b.prevPrice) - (a.row.price - a.prevPrice));
  newCoffees.sort((a, b) => a.name.localeCompare(b.name));

  return { runDate, isBaseline, newCoffees: isBaseline ? [] : newCoffees, drops, rises };
}
