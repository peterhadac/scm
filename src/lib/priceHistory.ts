// Build-time reader for data/price_history.csv (issue #54) — the
// append-only price time series the scraper maintains (issue #41, one row
// per (date, roaster, url, weight_g) observation, appended only on
// change). Returns one chronological series per (url, weight_g) so
// CoffeeTable can draw sparklines and price-drop badges. The file not
// existing yet (it appears with the first scrape after #50) — or any row
// being malformed — must degrade to "no history", never break the build.
import fs from 'node:fs';
import path from 'node:path';

export interface PricePoint {
  date: string;
  price: number;
}

// Minimal RFC-4180-ish line splitter: the `name` column (last) is quoted by
// Python's csv writer whenever it contains a comma/quote, and pulling in a
// CSV dependency for one 6-column file isn't worth it.
export function splitCsvLine(line: string): string[] {
  const fields: string[] = [];
  let current = '';
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (inQuotes) {
      if (ch === '"' && line[i + 1] === '"') {
        current += '"';
        i++;
      } else if (ch === '"') {
        inQuotes = false;
      } else {
        current += ch;
      }
    } else if (ch === '"') {
      inQuotes = true;
    } else if (ch === ',') {
      fields.push(current);
      current = '';
    } else {
      current += ch;
    }
  }
  fields.push(current);
  return fields;
}

export function historyKey(url: string, weightG: number): string {
  return `${url}|${weightG}`;
}

export function loadPriceHistory(
  relativePath = 'data/price_history.csv',
): Map<string, PricePoint[]> {
  const series = new Map<string, PricePoint[]>();
  const file = path.join(process.cwd(), relativePath);
  if (!fs.existsSync(file)) return series;

  const lines = fs.readFileSync(file, 'utf8').split('\n');
  // Header order is a contract with the scraper's PRICE_HISTORY_COLUMNS:
  // date,roaster,url,weight_g,price,name
  for (const line of lines.slice(1)) {
    if (!line.trim()) continue;
    const [date, , url, weightRaw, priceRaw] = splitCsvLine(line);
    const weightG = Number.parseInt(weightRaw, 10);
    const price = Number.parseFloat(priceRaw);
    if (!date || !url || Number.isNaN(weightG) || Number.isNaN(price)) continue;
    const key = historyKey(url, weightG);
    const points = series.get(key);
    if (points) points.push({ date, price });
    else series.set(key, [{ date, price }]);
  }
  // Rows are appended chronologically by the scraper, but sort defensively —
  // a hand-edit or merge shouldn't quietly flip a sparkline's direction.
  for (const points of series.values()) {
    points.sort((a, b) => a.date.localeCompare(b.date));
  }
  return series;
}

// Points string for an inline <polyline> sparkline, normalized into a
// width x height box (y inverted: SVG y grows downward, prices up).
export function sparklinePoints(
  points: PricePoint[],
  width = 56,
  height = 14,
  pad = 1.5,
): string {
  const prices = points.map((p) => p.price);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const span = max - min || 1;
  const innerW = width - 2 * pad;
  const innerH = height - 2 * pad;
  const step = points.length > 1 ? innerW / (points.length - 1) : 0;
  return points
    .map((p, i) => {
      const x = pad + i * step;
      const y = pad + innerH * (1 - (p.price - min) / span);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
}
