# English/Slovak Site Translation — Design

## Context

The site exclusively catalogues coffee from the Slovak market but has only
ever existed in English — `CoffeeTable.astro`'s legend already hand-hardcoded
one bilingual hint (`"Washed · Umytá"`), the tell that this gap had been
noticed but never properly closed. This spec covers translating the whole
site (coffee table + static content pages) to Slovak as a second language,
with a switcher to move between them.

## Decisions

- **Starlight's built-in i18n**, not a custom JS toggle. Starlight already
  ships everything a bespoke toggle would have to reinvent: URL-based
  routing (`/scm/sk/...`), a translated sidebar, a language picker, and —
  critically — a **complete Slovak translation of its own chrome**
  (`@astrojs/starlight/translations/sk.json`: search, pagination, 404,
  "skip to content", etc.), confirmed present and equal in size to `en.json`
  in the installed `@astrojs/starlight@0.41.1`. That's the majority of
  "whole page" translation with zero custom code.
- **Whole-site scope**: the coffee table page(s), the index hero, and the
  Drinks/Brew Methods content pages all get a Slovak version — not just the
  table.
- **Controlled-vocabulary data fields only**: `origin`, `process`, and
  `roast_type` (the enums documented in `CLAUDE.md`'s Data Schema) get a
  small static EN→SK display-label map. `name` and `roaster` — scraped
  proper nouns that link out to the roaster's own untranslated page — are
  never translated. Filtering/sorting must keep comparing the stable English
  value from `data/products.yaml`; only the *rendered* label changes with
  language, so switching language can never change which rows a filter
  matches.
- **Persisted language choice.** Starlight's `LanguageSelect.astro` (read
  from the installed package) is confirmed to be purely URL-based with no
  memory of its own — selecting a language just navigates to the localized
  equivalent of the current path, nothing more. Since every page is static
  (no server to set a cookie), persistence is a small `localStorage`-backed
  script.

## Architecture

```
astro.config.mjs
  starlight({
    locales: {
      root: { label: 'English', lang: 'en' },
      sk:   { label: 'Slovensky', lang: 'sk' },
    },
    sidebar: [...],  // existing manual sidebar; each item gains an optional
                      // `translations: { sk: '...' }` — `link` stays
                      // unprefixed, Starlight injects the active locale
                      // automatically (confirmed in
                      // utils/navigation.ts:linkFromSidebarLinkItem)
    head: [...existing Ko-fi scripts..., languagePersistenceScript],
  })

src/
  lib/
    i18n.ts            ← Lang type; UI EN/SK string table; ORIGIN_LABELS /
                          PROCESS_LABELS / ROAST_TYPE_LABELS display maps
                          keyed by the canonical English value from
                          data/products.yaml. Pure data — no Node built-ins
                          — so it's safe to import both server-side
                          (CoffeeTable.astro's frontmatter) and client-side
                          (its <script>, which Astro/Vite bundles for the
                          browser).
  components/
    CoffeeTable.astro   ← reads Astro.locals.starlightRoute.lang server-side
                          and document.documentElement.lang client-side
                          (both set by Starlight) to select strings/labels.
  content/docs/
    index.mdx, coffees.mdx, coffees/*.mdx, drinks/*.mdx,
    brew-methods/*.mdx        ← existing English pages, unchanged
    sk/                        ← 1:1 mirror of every page above, Slovak
                                 prose, internal links rewritten to /scm/sk/...
```

### Data-field translation, keeping filters stable

`CoffeeTable.astro` computes `originLabel`/`processLabel` per row via
`localizedOrigin()`/`localizedProcess()` for **display only**. The
`data-origin`/`data-process`/`data-roast` attributes each `<tr>` carries —
and the filter `<select>` option **values** — stay the raw English key from
`products.yaml`; `populateSelect()`'s client script derives each option's
*label* from `ORIGIN_LABELS`/`PROCESS_LABELS` but keeps `value` as the
English key, so `applyFilters()`'s equality checks are entirely unaffected
by which language is active.

### Persistence script

Since Starlight's picker has no memory, a small inline script (added to
`head`, alongside the existing Ko-fi widget scripts) does two things:

1. On every page load, if a stored `localStorage['scm-lang']` preference
   disagrees with the current page's locale, redirect to that language's
   mirror of the current path (a plain `/sk` path-segment swap after the
   `/scm` base — safe because every page has a 1:1 counterpart in both
   languages). No-op once the redirect lands, so there's no loop.
2. A `document`-level delegated `change` listener on
   `starlight-lang-select select` stores the newly chosen language.

## Testing / Verification

No unit-test suite for this (matches the existing site's testing strategy —
static markup + vanilla JS, manual/browser verification covers the real
risk). Verified via `npm run build` (both locale trees built cleanly, 0
errors) plus a scripted Playwright pass against `astro preview`:

1. English coffees page renders with English headers.
2. Switching the language picker to Slovensky navigates to `/scm/sk/...`
   and the table headers/filter labels/legend/summary line are all Slovak.
3. The origin filter dropdown shows translated labels (e.g. "Brazília")
   while filtering by it still correctly narrows the row set.
4. Visiting the site root after choosing Slovak redirects to `/scm/sk/`;
   switching back to English and revisiting root stays on `/scm/` — i.e.
   persistence works in both directions without looping.
