# Astro + Starlight Site — Design

## Context

Slovak Coffee Map decomposes into three independent sub-projects: scraper (done — see `scraper/`), this site, and GitHub Actions CI to glue them together and deploy. This spec covers the site: an Astro project using the Starlight documentation theme (with the `starlight-theme-md3` Material Design 3 plugin, already installed) that renders `_data/coffees.json` as a filterable, sortable table.

Nothing of the site exists yet beyond the installed `starlight-theme-md3` npm package — no `astro.config.mjs`, no `src/`, no `package.json` entries for Astro itself.

## Decisions

- **Full Starlight docs template** (sidebar nav + search), not a stripped single-page app — leaves room for future pages (roaster profiles, an About page) without restructuring.
- **Splash homepage + separate `/coffees` page** — `index.mdx` is Starlight's hero/splash template (title, tagline, button to `/coffees`); the table itself lives at `/coffees`, not at the root.
- **Separate dev-only sample data** (`_data/coffees.sample.json`) — `_data/coffees.json` stays the untouched real scraper-output path (currently `[]`). The component picks the source via Vite's built-in `import.meta.env.DEV` flag — no new env var or config file.
- **No client framework** — vanilla JS in a `<script>` tag inside the `.astro` component, matching the existing CLAUDE.md spec.
- **`last_seen` is not a visible column** — it's freshness metadata, not buyer-facing. Easy to add later if wanted.

> **Post-implementation update (2026-06-30):** the theme seed shipped as `#FF6037` ("Toxic Orange"), not the `#6f4e37` coffee-brown this spec originally called for — a deliberate rebrand by the project owner during implementation, applied alongside a full named palette (Morning Snow, Amazon Mist, Black Kite, Aqua Mist, Toxic Orange, Garnet) as MD3 token overrides in `src/styles/custom.css`. The code sample below and `CLAUDE.md` have been updated to match; the implementation plan (`docs/superpowers/plans/2026-06-30-astro-starlight-site.md`) still shows `#6f4e37` as a historical record of what was originally planned.

## Architecture

```
astro.config.mjs       ← Starlight integration + starlight-theme-md3 plugin, site/base for GitHub Pages, sidebar
package.json            ← + astro, @astrojs/starlight (starlight-theme-md3 already present)
src/
  content/
    docs/
      index.mdx          ← Starlight splash template: title, tagline, button → /coffees
      coffees.mdx         ← embeds <CoffeeTable />
  components/
    CoffeeTable.astro    ← table markup + filter/sort <script>
_data/
  coffees.json            ← real scraper output (untouched, stays [])
  coffees.sample.json     ← ~8-10 hand-written rows for local dev, all 5 roasters represented
```

Starlight's default scaffolded example pages (`guides/example`, `reference/example`) are deleted — unused boilerplate not relevant to this site.

### `astro.config.mjs`

```js
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import md3Theme from 'starlight-theme-md3';

export default defineConfig({
  site: 'https://<user>.github.io',
  base: '/scm',
  integrations: [
    starlight({
      title: 'Slovak Coffee Map',
      plugins: [md3Theme({ seed: '#FF6037', variant: 'tonalSpot' })],
      sidebar: [{ label: 'Coffees', link: '/coffees' }],
    }),
  ],
});
```

`base: '/scm'` must match whatever the GitHub Pages project slug actually is — confirm this when the repo is created on Pages, or links 404.

### `CoffeeTable.astro` — data source

```js
import prodCoffees from '../../_data/coffees.json';
import sampleCoffees from '../../_data/coffees.sample.json';
const coffees = import.meta.env.DEV ? sampleCoffees : prodCoffees;
```

### Table columns

Coffee name (linked to product `url`), roaster, origin, process, price (`€X.XX`), weight (`Xg`).

### Filtering and sorting

- Dropdowns for roaster / origin / process, **populated dynamically from the loaded data** (not hardcoded — must reflect whatever roasters/origins/processes are actually present).
- Price sort toggle (ascending/descending).
- Plain vanilla JS in a `<script>` tag: recomputes the visible row set client-side on any filter or sort change. Filters and sort compose (e.g. filter to one roaster *and* sort by price).
- Empty-result state (a filter combination matching zero rows) must render cleanly, not break.

## Testing / Verification

Run `npm run dev`, open in a browser, and verify manually:
1. Table renders all sample rows on load.
2. Each dropdown (roaster, origin, process) filters correctly in isolation.
3. Price sort toggle reorders rows ascending/descending.
4. A filter + sort combined together both apply correctly.
5. A filter combination with zero matches shows an empty state without erroring.
6. Each coffee name links to its product `url`.

No automated test suite for this sub-project — it's static markup + vanilla JS reacting to a small, fully-enumerable in-memory array; manual browser verification covers the real risk (visual/interaction correctness), which a unit test wouldn't catch any faster than looking at it.
