// RSS feed of the weekly digest (issue #55): one item per price drop and
// new arrival from the latest scrape. Buttondown/feed readers can consume
// this directly, so the digest is subscribable before any newsletter
// infrastructure exists. Prerendered at build time like the rest of the
// static site.
import type { APIRoute } from 'astro';
import { buildDigest } from '../lib/digest';

function esc(text: string): string {
  return text
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

export const GET: APIRoute = ({ site }) => {
  const digest = buildDigest();
  const siteUrl = `${site ?? 'https://peterhadac.github.io'}`.replace(/\/$/, '');
  const pageUrl = `${siteUrl}/scm/this-week/`;
  const pubDate = digest.runDate ? new Date(digest.runDate).toUTCString() : new Date().toUTCString();

  const items: string[] = [];
  for (const d of digest.drops) {
    const weightText = `${d.row.weight_g} g${d.row.variant ? `, ${d.row.variant}` : ''}`;
    items.push(`    <item>
      <title>${esc(`↓ ${d.row.name} (${d.row.roaster}) — €${d.row.price.toFixed(2)}, was €${d.prevPrice.toFixed(2)}`)}</title>
      <link>${esc(d.row.url)}</link>
      <guid isPermaLink="false">${esc(`${d.row.url}|${d.row.weight_g}|${d.row.variant ?? ''}|${digest.runDate}`)}</guid>
      <pubDate>${pubDate}</pubDate>
      <description>${esc(`${d.row.name} (${d.row.roaster}, ${weightText}) dropped from €${d.prevPrice.toFixed(2)} to €${d.row.price.toFixed(2)}.`)}</description>
    </item>`);
  }
  if (!digest.isBaseline) {
    for (const c of digest.newCoffees) {
      const weightText = `${c.weight_g} g${c.variant ? `, ${c.variant}` : ''}`;
      items.push(`    <item>
      <title>${esc(`NEW: ${c.name} (${c.roaster}) — €${c.price.toFixed(2)} / ${c.weight_g} g`)}</title>
      <link>${esc(c.url)}</link>
      <guid isPermaLink="false">${esc(`${c.url}|new|${digest.runDate}`)}</guid>
      <pubDate>${pubDate}</pubDate>
      <description>${esc(`${c.name} by ${c.roaster} is newly listed at €${c.price.toFixed(2)} for ${weightText} (${c.origin}${c.process ? `, ${c.process}` : ''}, ${c.roast_type}).`)}</description>
    </item>`);
    }
  }

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Slovak Coffee Map — weekly changes</title>
    <link>${esc(pageUrl)}</link>
    <description>New coffees and price changes across Slovak specialty roasters, updated weekly.</description>
    <language>en</language>
    <lastBuildDate>${pubDate}</lastBuildDate>
${items.join('\n')}
  </channel>
</rss>
`;
  return new Response(xml, {
    headers: { 'Content-Type': 'application/rss+xml; charset=utf-8' },
  });
};
