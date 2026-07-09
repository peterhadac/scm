# Product

## Register

product

## Users

Slovak coffee drinkers deciding where to buy beans right now — home brewers comparing
price-per-100g across roasters, and people who already know a roaster but want to check
current stock, origin, or process before ordering. They arrive with a specific
in-progress question ("what's in stock, and is it worth it") rather than to browse or be
inspired. Session is short: filter/sort, click through to the roaster's own shop to buy.

## Product Purpose

A weekly-refreshed, single-table catalogue of every coffee currently sold by tracked
Slovak roasters — scraped, normalized, and published automatically. Success is the table
being accurate and current enough that the "data updated" timestamp is trustworthy, and
that filtering by roaster/origin/process/roast gets someone to the right product page in
a few clicks. The site is a lookup tool wrapped in light docs chrome (Starlight), not a
retailer — it never sells directly; every row links out to the roaster's own site.

## Brand Personality

Precise, editorial, quietly confident. Reads like a well-made reference tool or
specialist publication, not a storefront — confidence comes from accurate data and
restrained typography, not from persuasive copy or promotional styling.

## Anti-references

Generic e-commerce/SaaS: no Shopify-storefront product cards, no SaaS-dashboard stock
icons or hero-metric templates, no promotional badges/urgency framing ("only 2 left!").
The existing brand system (`Design.md`, `brand-spec.md`) already constrains palette and
type to two families — do not introduce third-party visual conventions from either genre
to compensate.

## Design Principles

- **The table is the product.** Every other surface (hero, docs sidebar, recipe pages)
  exists to support or contextualize the filterable table, not to compete with it for
  attention.
- **Data honesty over polish.** Missing fields (`—`), stale timestamps, and
  `incomplete`/`not_a_product` states should read as trustworthy gaps, not be hidden or
  smoothed over — an editorial tool earns trust by showing its limits.
- **Restraint within the fixed system.** Work inside the existing palette, two type
  families, and 8px spacing grid (`Design.md`) rather than reaching for e-commerce or
  SaaS conventions to add visual interest.
- **Task-first interaction.** Filtering, sorting, and scanning price-per-100g should stay
  fast and low-friction; decorative motion or copy that slows down comparison is off-brand
  here even where it might suit a marketing page.
- **Link out, don't lock in.** The site's job ends at "here's the coffee and where to buy
  it" — never obscure or compete with the outbound link to the roaster's own product page.

## Accessibility & Inclusion

WCAG AA baseline: ≥4.5:1 body text contrast, ≥3:1 for large text/UI components, full
keyboard operability for the filter/sort controls, and a `prefers-reduced-motion`
alternative for any animation (the existing row-stagger-in animation and freshness-dot
pulse need reduced-motion fallbacks). No unusual user-population constraints beyond
standard AA.
