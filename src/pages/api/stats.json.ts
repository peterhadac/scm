import type { APIRoute } from 'astro';
import yaml from 'js-yaml';
import { readFileSync, existsSync } from 'fs';
import { join } from 'path';

export const GET: APIRoute = async () => {
  const cwd = process.cwd();
  
  let products: Record<string, any[]> = {};
  try {
    const productsPath = join(cwd, 'data', 'products.yaml');
    if (existsSync(productsPath)) {
      products = yaml.load(readFileSync(productsPath, 'utf8')) || {};
    }
  } catch {
    products = {};
  }

  let roasters: Record<string, unknown> = {};
  try {
    const roastersPath = join(cwd, 'roasters.yaml');
    if (existsSync(roastersPath)) {
      roasters = (yaml.load(readFileSync(roastersPath, 'utf8')) || {}) as Record<string, unknown>;
    }
  } catch {
    roasters = {};
  }

  let roastTypeCounts: Record<string, number> = {};
  let originCounts: Record<string, number> = {};
  let processCounts: Record<string, number> = {};
  let priceMin = Infinity;
  let priceMax = 0;
  let totalOk = 0;
  let totalIncomplete = 0;

  for (const [, entries] of Object.entries(products)) {
    for (const entry of entries) {
      if (entry.status === 'ok') {
        totalOk++;
        const rtt = entry.roast_type;
        if (rtt) roastTypeCounts[rtt] = (roastTypeCounts[rtt] || 0) + 1;
        const origin = entry.origin;
        if (origin) originCounts[origin] = (originCounts[origin] || 0) + 1;
        const process = entry.process;
        if (process) processCounts[process] = (processCounts[process] || 0) + 1;
        for (const pkg of entry.packaging || []) {
          if (pkg.price != null) {
            if (pkg.price < priceMin) priceMin = pkg.price;
            if (pkg.price > priceMax) priceMax = pkg.price;
          }
        }
      } else if (entry.status === 'incomplete') {
        totalIncomplete++;
      }
    }
  }

  const statData = {
    totalOk,
    totalIncomplete,
    totalRoasters: (roasters.roasters || []).length,
    roastTypeCounts,
    originCounts: Object.entries(originCounts)
      .sort((a, b) => b[1] - a[1])
      .reduce((acc, [k, v]) => { acc[k] = v; return acc; }, {} as Record<string, number>),
    processCounts,
    priceRange: {
      min: priceMin === Infinity ? 0 : priceMin,
      max: priceMax || 0,
    },
    generatedAt: new Date().toISOString(),
  };

  return new Response(JSON.stringify(statData), {
    headers: { 'Content-Type': 'application/json' },
  });
};
