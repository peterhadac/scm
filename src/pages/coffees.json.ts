// Public data endpoint (issue #60): the same flattened rows the coffee
// table renders, as a stable JSON artifact at /scm/coffees.json. Statically
// prerendered at build time, so it refreshes with every weekly deploy —
// same freshness as the site itself. Documented on the "About the data"
// page; treat field names as a public contract.
import type { APIRoute } from 'astro';
import { flattenProducts } from '../lib/coffees';

export const GET: APIRoute = () => {
  const coffees = flattenProducts();
  const body = JSON.stringify(
    {
      // Build date, not scrape date — individual rows carry their own
      // last_seen from the scrape that actually observed them.
      generated: new Date().toISOString().slice(0, 10),
      source: 'https://github.com/peterhadac/scm',
      license: 'Prices/availability scraped from public roaster pages; verify before commercial use.',
      count: coffees.length,
      coffees,
    },
    null,
    1,
  );
  return new Response(body, {
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
  });
};
