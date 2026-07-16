# Slovak Coffee Map

Weekly-updated catalogue of coffees available on the Slovak market, scraped from roaster websites, stored as JSON, and published via GitHub Pages (Astro + [Starlight](https://starlight.astro.build/)).

> ponytail: Starlight is a docs framework; for one filterable table, plain Astro (no Starlight) is lighter. Keeping Starlight as requested for theme/chrome — drop it for `@astrojs` base if the docs sidebar/search become noise.

> See [`Architecture.md`](./Architecture.md) for the full scraping pipeline: crawl4ai-based per-product discovery, hash-gated extraction, and normalization into the `data/products.yaml` artifact below.

## Architecture

```
roasters.yaml          ← seed list of roasters + per-site scraper overrides + slug/metadata
scraper/
  scrape.py            ← main entrypoint: crawl4ai discover → hash-gate → AI extract → normalize/validate → products.yaml
  pyproject.toml       ← uv project: runtime deps + pytest dev dep
  uv.lock              ← pinned lockfile
data/
  products.yaml        ← per-product intermediate: fields, page_hash, status, packaging (see Architecture.md)
  scrape_status.yaml    ← per-roaster health: status + consecutive_non_ok streak, committed alongside products.yaml (see "Observability" below)
  price_history.csv     ← append-only price time series (issue #41): one row per (date, roaster, url, weight_g), appended only when that tier's price is new or changed; a no-change week appends nothing
src/
  content/docs/index.mdx   ← Starlight page embedding the table component (+ sk/ mirror for Slovak)
  components/CoffeeTable.astro  ← filterable/sortable table UI
  lib/coffees.ts       ← build-time data layer: reads data/products.yaml + roasters.yaml, flattens to table rows
  lib/i18n.ts           ← EN/SK UI string table + origin/process/roast_type display-label maps
astro.config.mjs       ← Astro + Starlight config (site + base for project Pages, locales for EN/SK)
package.json           ← astro, @astrojs/starlight, starlight-theme-md3 (pnpm)
.github/workflows/
  scrape.yml           ← weekly cron, commits products.yaml (its push does NOT trigger pages.yml — see below)
  pages.yml            ← build Astro + deploy to Pages on push to main / scrape.yml completion / manual
.gitignore             ← dist/, node_modules/, .astro/, __pycache__/, .venv/
```

## Data Schema

`data/products.yaml` (mapping of roaster `slug` → array of product entries)
is the sole scraped artifact — see [`Architecture.md`](./Architecture.md) for
the full pipeline and [`data/products.schema.yaml`](./data/products.schema.yaml)
for the validated shape. Each entry is one of:

- **`status: ok`** — `name`, `url`, `origin`, `roast_type`, and every
  `packaging` tier's `weight_g`/`price` are all non-null. `process` may
  still be `null` (many roasters don't publish it).
- **`status: incomplete`** — a genuine coffee product, but missing one of
  `origin`/`roast_type`/`weight_g`/`price` (listed in `missing_fields`).
  Excluded from the site until fixed; kept in `products.yaml` so hash-gating
  still applies — though an unchanged page is still re-extracted on up to
  `MAX_INCOMPLETE_REEXTRACTIONS` (3) later runs (tracked per entry as
  `reextract_attempts`, issue #36) so a flaky extraction self-heals; after
  that it hash-gates normally until the page changes.
- **`status: not_a_product`** — the discovered URL wasn't a single coffee
  product page.

Controlled vocabularies (translated to English at scrape time regardless of
source language):
- `process`: `washed` | `natural` | `honey` | `wet-hulled` | `anaerobic` |
  `carbonic-maceration` | `other` | `null`
- `roast_type`: `filter` | `espresso` | `nespresso` (Nespresso-compatible
  capsules) | `drip-bag` (single-serve drip bags) — never `null` on an `ok`
  entry
- `origin`: an English country name, matched against
  [`data/coffee_origins.yaml`](./data/coffee_origins.yaml) — falls back to
  scanning the product name for a country mention when the site doesn't
  state one (e.g. `"brazil • doce citrus"` → `Brazil`). A product whose name
  marks it as a multi-origin blend (`"blend"` / `"zmes"` / `"mix"`) and that
  matches no single country gets the sentinel `"Blend"` instead of staying
  `null` — it genuinely has no one source country to report. The model can
  also mark a blend explicitly (`blend: true` tool param, issue #91), which
  fills a missing origin with the sentinel — but never overrides a stated
  country.
- Blend entries (`origin: "Blend"`) additionally carry `blend: true` and,
  when the page lists component countries, `blend_origins` (canonical
  English names via the same alias table; unmatchable entries dropped, issue
  #91). Absent on single-origin coffees.

`price` is **EUR** as a JSON number with a `.` decimal. `last_seen` is the
date of the last successful scrape that included this item; it stops
advancing while the roaster is `failed`/`needs_js`.

The Astro build reads `data/products.yaml` + `roasters.yaml` directly at
build time (see `src/lib/coffees.ts`, used by
`src/components/CoffeeTable.astro`) and flattens each `ok`-status product's
packaging tiers into one row per weight — there is no separate generated
JSON file for the site to import.

## Roaster Config (`roasters.yaml`)

```yaml
roasters:
  - name: Kavoholik
    slug: kavoholik
    url: https://kavoholik.sk/
    scrape_url: https://kavoholik.sk/
  - name: Coffeein
    slug: coffeein
    url: https://www.coffeein.sk/
    scrape_url: https://www.coffeein.sk/
    scraper: playwright   # opt-in for JS-heavy sites
  - name: Ready After
    slug: ready-after
    url: https://www.readyafter.sk/
    scrape_url: https://www.readyafter.sk/
    roast_type_urls:   # site never states roast_type on the product page itself
      espresso: https://www.readyafter.sk/espresso-zmesi/
      filter: https://www.readyafter.sk/kava-filter/
```

(See the real [`roasters.yaml`](./roasters.yaml) ~30 lines below this file for the full, current list — this snippet only illustrates the optional keys.)

`slug` is the stable key `data/products.yaml` is keyed on (lowercase-kebab of the name). `url` is the roaster's canonical site link; `scrape_url` is the discovery entry point the scraper crawls for product links — usually the same page, but point it at the actual shop/listing page when the homepage doesn't link to every product. `metadata` is optional, added as roaster details are gathered — not required for the scraper to run; currently just `{city: <string>}` (the roaster's Slovak town/city), not read by the scraper itself. Add `scraper: playwright` to any roaster that requires JavaScript rendering (selects crawl4ai's browser-backed crawler instead of the HTTP one). `roast_type_urls` (optional, mapping of `roast_type` value → category URL, e.g. `{espresso: <url>, filter: <url>}` — `nespresso`/`drip-bag` keys work too) is for sites (Shopify collections, Shoptet category pages) that only reveal a product's roast type through which category page links to it, never on the product page itself — the scraper crawls each configured category and uses it as a last-resort `roast_type` fallback (see `discover_roast_type_hints()` in `scraper/scrape.py`). `referral` (optional, `{code: <string>}`, issue #57) marks a roaster with an agreed discount-code partnership — not read by the scraper; the site renders a copyable code chip on that roaster's rows (see `docs/referral-outreach-sk.md` for the outreach template).

## Scraper (`scraper/scrape.py`)

Full design in [`Architecture.md`](./Architecture.md). Summary:

1. Load `roasters.yaml`.
2. Per roaster, **discover** product URLs from the listing page(s) via crawl4ai's `prefetch=True` mode (cheap — no LLM call), following pagination by hand.
3. Per discovered URL, fetch via crawl4ai (markdown output), hash it, and **skip the LLM call** if the hash matches what's already stored for that URL in `data/products.yaml`. Otherwise call the model (tool call left optional, not forced, so it can decline non-product pages) to extract `name`/`origin`/`process`/`roast_type`/`packaging` (multi-weight).
4. Diff this run's discovered URLs against `data/products.yaml`'s existing entries for that roaster — anything missing is genuinely delisted and gets dropped; anything new gets fetched. This diff only runs when discovery for that roaster completed cleanly (see `partial` below) — an incomplete discovery pass must never be read as "everything not rediscovered is gone".
5. Write a `scrape_status` summary (logged to stdout; not stored in either file).

### Scrape status values (per product, in `data/products.yaml`)
- `ok` — extracted a name and ≥1 valid price/weight tier
- `not_a_product` — discovered link wasn't actually a single coffee product page (cached so it isn't re-sent to the model every run)
- A fetch failure or JS-rendered-looking page leaves the existing entry untouched (no status overwrite, `last_seen` doesn't advance)

### Roaster-level scrape statuses (`scrape_status` summary)
Distinct from the per-product statuses above — one of these is reported per roaster in the stdout summary, and returned by `process_roaster()`/`discover_product_urls()`:
- `ok` — listing discovery completed cleanly (no fetch failure, no `MAX_PAGES` cap hit) and every entry not rediscovered this run is genuinely delisted and dropped.
- `failed` — the listing page itself couldn't be fetched; existing entries untouched.
- `needs_js` — the listing page looks JS-rendered (or a successful crawl found zero product links despite prior data existing); existing entries untouched.
- `partial` — listing discovery started but didn't finish: either a fetch on page 2+ of pagination failed (`failed_midway`), or pagination hit the `MAX_PAGES` cap (currently 30) while a further page was still linked (`capped`) — both logged as a warning by `discover_product_urls()`. Products freshly (re)discovered this run are still processed normally; any prior entry whose URL wasn't rediscovered is **preserved as-is** (no `last_seen`/`page_hash` change) rather than dropped, since it may simply live on a listing page this run never reached (issue #22).
- `suspect` — discovery looked clean but would have dropped most of the roaster's known-good products in one run (more than `MASS_DELIST_GUARD_FRACTION` (50%) of `ok`/`incomplete` priors, and at least `MASS_DELIST_GUARD_MIN_DROPPED` (3) of them) — far more likely a site redesign that still parses as a listing than a real catalogue wipeout (issue #39). Prior entries are preserved exactly like a `partial` run; only `ok`/`incomplete` priors count, so a mass drop of `not_a_product` noise (e.g. after a discovery-filter tightening) doesn't trip it.

### Observability (`data/scrape_status.yaml`)

The roaster-level statuses above are deliberately silent, by-design
degradations (stale data kept, `last_seen` frozen, exit code still 0) — but
nothing escalated them, so a roaster that quietly broke months ago just
faded from the table with no one told (issue #28). `run()` closes that gap
in three ways, all driven by `data/scrape_status.yaml` — a mapping of
roaster `slug` → `{name, status, last_run, consecutive_non_ok}` written at
the end of every run (via `load_scrape_status`/`build_scrape_status_records`/
`save_scrape_status`, same `yaml.safe_dump(..., sort_keys=True)` style as
`products.yaml`). `consecutive_non_ok` increments on any non-`"ok"`
roaster-level status and resets to `0` the moment a roaster comes back
`"ok"`; a roaster not processed this run (e.g. `--only`) keeps its prior
record untouched — the streak only means something for runs that actually
happened.

1. **`::warning::` annotations** (`emit_warning_annotations()`) — one GitHub
   Actions workflow-command line per non-`"ok"` roaster, printed to stdout.
   Picked up by the Actions runner and surfaced in the run's checks UI; a
   harmless stdout line everywhere else.
2. **`$GITHUB_STEP_SUMMARY` table** (`write_github_step_summary()`) — a
   Markdown roaster/status/note table appended to the step summary file, so
   non-ok roasters show up on the run's summary page at a glance. No-op
   (doesn't error) when `GITHUB_STEP_SUMMARY` isn't set, e.g. running
   locally.
3. **Escalation** (`escalate_repeated_failures()`) — prints a distinct
   `::error::` annotation for any roaster whose `consecutive_non_ok` has
   reached `CONSECUTIVE_NON_OK_ALERT_THRESHOLD` (3). The scraper itself only
   annotates — it has no `GITHUB_TOKEN`; `scrape.yml`'s "Escalate roasters
   non-ok for 3+ consecutive runs" step reads the freshly-written
   `data/scrape_status.yaml` after the scraper runs and opens (or comments
   on, to avoid duplicate spam) a `gh issue` titled `Roaster health: <name>`
   for each one.

### LLM extraction (OpenRouter)
One call per product page's markdown via [OpenRouter](https://openrouter.ai/)'s OpenAI-compatible `/chat/completions` endpoint (`openai` SDK pointed at `base_url="https://openrouter.ai/api/v1"`), model `google/gemini-2.5-flash-lite` with fallback to `google/gemini-2.5-flash` (ordered `MODELS` list, issue #42 — a model-level 404/400 moves to the next model immediately, transient errors retry first; override via the `OPENROUTER_MODELS` env var, comma-separated). The `extract_product` tool (OpenAI function-calling shape: `{"type": "function", "function": {...}}`) is available but not forced — this lets the model decline (plain text reply, no tool call) when a discovered URL turns out to be a category page, the homepage, or something that isn't coffee, rather than fabricating a product from whatever's on the page.

## GitHub Actions

### `scrape.yml` — weekly data refresh

```yaml
on:
  schedule:
    - cron: '0 6 * * 1'   # 6am UTC, every Monday
  workflow_dispatch:        # manual trigger for testing

permissions:
  contents: write           # default GITHUB_TOKEN is read-only; needed to push
  issues: write              # for the escalation step below (issue #28)
```

Steps: checkout → `setup-uv` → `uv sync --directory scraper` → `crawl4ai-setup` (installs Playwright/Patchright browsers) → run scraper → **escalate roasters non-ok for 3+ consecutive runs** → commit `data/products.yaml` + `data/scrape_status.yaml` + `data/price_history.csv` → push.

- The escalation step (issue #28) reads `data/scrape_status.yaml` (just
  written by the scraper) with a small inline Python snippet, and for every
  roaster whose `consecutive_non_ok >= 3` uses the `gh` CLI (preinstalled on
  `ubuntu-latest`, authenticated via `${{ github.token }}`) to search for an
  open issue titled `Roaster health: <name>` — commenting on it if found,
  creating it otherwise, so a persistently-broken roaster doesn't spam a new
  issue every week.
- Guard the commit so a no-change run doesn't fail the job — all scraped
  artifacts are staged **first** and then diffed staged (a plain `git diff`
  never sees a brand-new untracked artifact, e.g. the first-ever
  `scrape_status.yaml`/`price_history.csv`), so any one of them changing
  triggers a commit; `price_history.csv` is `git add`ed behind an existence
  guard since it only appears once the first run with an `ok` product has
  happened.
- **The push to `main` does NOT trigger `pages.yml`** — a push made with the default `GITHUB_TOKEN` (which `actions/checkout` uses here) doesn't fire other workflows' `on: push`, to prevent recursive runs. `pages.yml` instead listens for `scrape.yml`'s completion via `workflow_run` (see below). Ordinary human pushes to `main` are unaffected and still trigger `pages.yml` normally.

### `pages.yml` — build & deploy (Astro is **not** auto-built by Pages)

Unlike Jekyll, GitHub Pages does not build Astro for you. A workflow must run `astro build` and deploy `dist/`.

```yaml
on:
  push:
    branches: [main]
  # GITHUB_TOKEN-authenticated pushes (like scrape.yml's data commits) don't
  # trigger on:push workflows — this workflow_run trigger closes that gap.
  workflow_run:
    workflows: ["Scrape coffee data"]   # must match scrape.yml's `name:`
    types: [completed]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write
```

The `build` job additionally guards `if: github.event_name != 'workflow_run' || github.event.workflow_run.conclusion == 'success'`, so a failed/cancelled scrape run doesn't trigger a pointless (or stale) rebuild.

Steps: checkout → setup-node → `npm ci` → `npm run build` → `actions/upload-pages-artifact` (path `dist/`) → `actions/deploy-pages`. Set Pages source to "GitHub Actions" in repo settings.

## Astro + Starlight Site

- **Framework**: [Astro](https://astro.build/) with the [Starlight](https://starlight.astro.build/) integration for theme/chrome.
- **Theme**: [`starlight-theme-md3`](https://axiaobo7788.github.io/starlight-material-design-theme/) (Material Design 3 / Material You), added as a Starlight **plugin** in `astro.config.mjs`:
  ```js
  import starlight from '@astrojs/starlight';
  import md3Theme from 'starlight-theme-md3';
  // ...
  starlight({
    title: 'Slovak Coffee Map',
    plugins: [md3Theme({ seed: '#FF6037', variant: 'tonalSpot' })],  // seed = Toxic Orange, brand accent
  })
  ```
  Brand palette (also applied as MD3 token overrides in `src/styles/custom.css`, light + dark): Morning Snow `#F5F4ED`, Amazon Mist `#ECECDC`, Black Kite `#351E1C`, Aqua Mist `#A0C9CB`, Toxic Orange `#FF6037`, Garnet `#733635`.
- **Data source**: `src/lib/coffees.ts` reads `data/products.yaml` + `roasters.yaml` directly at build time (via `js-yaml`) and flattens them into table rows consumed by `CoffeeTable.astro` — no separate generated JSON file, and local dev uses the same real data. A new scrape requires a rebuild (handled by `pages.yml`).
- **`astro.config.mjs`**: set `site: 'https://<user>.github.io'` and `base: '/scm'` for a project Pages site, or links 404.
- **UI**: filterable/sortable table
  - Dropdowns: roaster, origin, process
  - Sort: price (asc/desc)
  - Implementation: vanilla JS in a `<script>` inside the `.astro` component, no framework island.
  - **Stale indicator** (issue #28): each row's `last_seen` is compared at
    build time (`new Date()` in the frontmatter) against a 21-day
    (~3 weekly scrape cycles) threshold; a row older than that gets a small
    muted warning icon next to its price (`.ct-stale`, reusing the tertiary
    / Garnet role already used for the "natural" process badge — no new
    color) with a title/aria-label explaining the price may be outdated.
- **Internationalization (English + Slovak)**: uses Starlight's built-in
  i18n rather than a bespoke toggle — `locales: { root: { lang: 'en' }, sk:
  { lang: 'sk' } }` in `astro.config.mjs` gives URL-based routing
  (`/scm/sk/...`), a translated sidebar, and a language picker for free.
  Starlight's own chrome (search, pagination, 404, "skip to content"...)
  already ships a complete Slovak translation
  (`@astrojs/starlight/translations/sk.json`) and needs no extra work.
  - **Content pages**: every page under `src/content/docs/` has a 1:1
    mirror under `src/content/docs/sk/` with hand-written Slovak prose
    (internal links inside those pages point at the `/scm/sk/...` path).
    Sidebar item labels are translated via each item's `translations: {
    sk: '...' }` key in `astro.config.mjs`; the `link` itself stays
    unprefixed — Starlight injects the current locale automatically.
  - **`CoffeeTable.astro` UI strings and data-field display translation**:
    `src/lib/i18n.ts` holds the EN/SK string table (`UI`) plus display-label
    maps for the controlled-vocabulary fields (`ORIGIN_LABELS`,
    `PROCESS_LABELS`, `ROAST_TYPE_LABELS`, keyed by the canonical English
    value from `data/products.yaml`). The component reads the active locale
    from `Astro.locals.starlightRoute.lang` server-side and from
    `document.documentElement.lang` in its client `<script>` (both set by
    Starlight). Only the *rendered* text changes with language — every
    `data-origin`/`data-process`/`data-roast` attribute (and the filter
    `<select>` option **values**) stays the stable English key from
    `products.yaml`, so switching language never changes which rows match a
    filter. Coffee `name` and `roaster` are never translated — they're
    scraped proper nouns linking out to the roaster's own untranslated page.
  - **Persistence**: Starlight's language picker is purely URL-based with no
    memory of its own, so a small inline script (in `astro.config.mjs`'s
    `head` array) stores the chosen language in `localStorage` and, on any
    page load, redirects to that language's mirror of the current path if
    it doesn't already match — safe because every page has a 1:1 `/sk`
    counterpart, so the redirect is just a path-segment swap.

## Brand & Design System

See [`Design.md`](./Design.md) — logo, colour palette, typography, and spacing rules. All rules there are binding when writing UI code.

## Testing

`scraper/test_scrape.py` is a pytest suite covering the pure-function/parsing logic
(`normalize_product`, `extract_product`'s decline/failure contract, weight/price
parsing, WooCommerce/Shopify variation extraction, pagination, etc.) — no network
access or `OPENROUTER_API_KEY` needed. Run it with:

```bash
uv run --directory scraper pytest test_scrape.py -v
```

Site-side, `e2e/coffee-table.spec.ts` is a Playwright smoke suite (issue #43)
covering CoffeeTable.astro's client logic against the real built site: rows
render, the origin filter narrows to matching `data-origin` rows, the price
header flips the default cheapest-first sort, and the `/sk` locale filters on
the stable English keys. Run it with `pnpm build && pnpm test:e2e` (the
config's `webServer` starts `astro preview` on `dist/` itself); CI runs it in
`.github/workflows/e2e.yml`. Playwright artifacts (`test-results/`,
`playwright-report/`) are gitignored.

Any change to `scraper/scrape.py`'s extraction/normalization logic should come with
a matching test in `test_scrape.py`, and `pytest` should pass before opening a PR;
a behavior change in `CoffeeTable.astro`'s filtering/sorting/i18n should keep
`pnpm test:e2e` passing the same way.

## Larger-feature planning (`docs/superpowers/`)

Multi-task features get a paired design spec + implementation plan under
`docs/superpowers/specs/` and `docs/superpowers/plans/` (e.g.
`2026-07-05-products-schema-migration-design.md` /
`-products-schema-migration.md`), written before implementation and referenced from
the eventual PR body. Not required for a small, single-file bug fix — reserve it for
changes that touch several files/behaviors together (a schema migration, a new CI
workflow, a new site section).

## Issue/PR conventions

- When a single PR or commit fixes **multiple** GitHub issues, repeat the closing
  keyword before every issue number on its own (`Fixes #10, Fixes #11, Fixes #12`),
  not a keyword followed by a comma-separated list (`Fixes #10, #11, #12`) — GitHub
  only auto-closes the issue immediately following the keyword, so the
  comma-separated form silently leaves the rest open even though the fix is merged.
  This has already caused stale "fixed but still open" issues once in this repo.
- Prefer one issue per PR where practical; when using worktrees to fix several
  issues in parallel, open one PR per worktree/issue rather than squashing them
  into a single branch — it keeps the "Fixes #N" auto-close working per-PR and
  keeps review scoped to one change.

## Environment Variables / Secrets

- `OPENROUTER_API_KEY` — required by scraper (OpenRouter, models `google/gemini-2.5-flash-lite` → `google/gemini-2.5-flash` fallback), stored as GitHub Actions secret
- `OPENROUTER_MODELS` — optional comma-separated ordered override of the extraction model list (issue #42)
- `GOATCOUNTER_CODE` — optional GoatCounter site code (issue #56), stored as a GitHub Actions **repository variable** (not a secret) and passed to `pnpm build` by `pages.yml`. When unset (local dev, forks) the analytics scripts are simply not emitted. Enables pageviews + `out:<host><path>` outbound-click events on roaster links — the numbers behind referral conversations.

## Development

```bash
# Install scraper deps and set up Playwright/Patchright browsers
uv sync --directory scraper
uv run --directory scraper crawl4ai-setup
# (required even for the plain-HTTP crawler; definitely
# required to test any roaster with `scraper: playwright`)

# Run scraper locally
OPENROUTER_API_KEY=... uv run --directory scraper python scrape.py

# Serve site locally
pnpm install
pnpm dev             # astro dev server with live reload
```

## Adding a New Roaster

1. Add entry to `roasters.yaml` (`name`, `slug`, `url`)
2. Run scraper locally to verify extraction works
3. If output is empty, add `scraper: playwright` and re-test
4. Commit `roasters.yaml` — next cron run picks it up
