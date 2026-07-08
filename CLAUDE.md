# Slovak Coffee Map

Daily-updated catalogue of coffees available on the Slovak market, scraped from roaster websites, stored as JSON, and published via GitHub Pages (Astro + [Starlight](https://starlight.astro.build/)).

> ponytail: Starlight is a docs framework; for one filterable table, plain Astro (no Starlight) is lighter. Keeping Starlight as requested for theme/chrome — drop it for `@astrojs` base if the docs sidebar/search become noise.

> See [`Architecture.md`](./Architecture.md) for the full scraping pipeline: crawl4ai-based per-product discovery, hash-gated extraction, and normalization into the `data/products.yaml` artifact below.

## Architecture

```
roasters.yaml          ← seed list of roasters + per-site scraper overrides + slug/metadata
scraper/
  scrape.py            ← main entrypoint: crawl4ai discover → hash-gate → AI extract → normalize/validate → products.yaml
  requirements.txt
data/
  products.yaml        ← per-product intermediate: fields, page_hash, status, packaging (see Architecture.md)
_data/
  coffees.sample.json  ← hand-maintained dev fixture (import.meta.env.DEV only)
src/
  content/docs/index.mdx   ← Starlight page embedding the table component
  components/CoffeeTable.astro  ← filterable/sortable table (reads ../../data/products.yaml + roasters.yaml directly at build time)
astro.config.mjs       ← Astro + Starlight config (site + base for project Pages)
package.json           ← astro, @astrojs/starlight, starlight-theme-md3 (npm)
.github/workflows/
  scrape.yml           ← daily cron, commits products.yaml (its push does NOT trigger pages.yml — see below)
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
  still applies.
- **`status: not_a_product`** — the discovered URL wasn't a single coffee
  product page.

Controlled vocabularies (translated to English at scrape time regardless of
source language):
- `process`: `washed` | `natural` | `honey` | `wet-hulled` | `anaerobic` |
  `carbonic-maceration` | `other` | `null`
- `roast_type`: `filter` | `espresso` (never `null` on an `ok` entry)
- `origin`: an English country name, matched against
  [`data/coffee_origins.yaml`](./data/coffee_origins.yaml) — falls back to
  scanning the product name for a country mention when the site doesn't
  state one (e.g. `"brazil • doce citrus"` → `Brazil`). A product whose name
  marks it as a multi-origin blend (`"blend"` / `"zmes"` / `"mix"`) and that
  matches no single country gets the sentinel `"Blend"` instead of staying
  `null` — it genuinely has no one source country to report.

`price` is **EUR** as a JSON number with a `.` decimal. `last_seen` is the
date of the last successful scrape that included this item; it stops
advancing while the roaster is `failed`/`needs_js`.

The Astro build reads `data/products.yaml` + `roasters.yaml` directly at
build time (see `src/components/CoffeeTable.astro`) and flattens each
`ok`-status product's packaging tiers into one row per weight — there is no
separate generated JSON file for the site to import.

## Roaster Config (`roasters.yaml`)

```yaml
roasters:
  - name: Kavoholik
    slug: kavoholik
    url: https://kavoholik.sk/
    scrape_url: https://kavoholik.sk/
  - name: Ready After
    slug: ready-after
    url: https://www.readyafter.sk/
    scrape_url: https://www.readyafter.sk/
  - name: Jungle Roastery
    slug: jungle-roastery
    url: https://thisisjungle.sk/
    scrape_url: https://thisisjungle.sk/
    metadata:
      city: Bratislava
  - name: Coffeein
    slug: coffeein
    url: https://www.coffeein.sk/
    scrape_url: https://www.coffeein.sk/
    scraper: playwright   # opt-in for JS-heavy sites
  - name: Trip Coffee Roasters
    slug: trip-roasters
    url: https://triproasters.sk/
    scrape_url: https://triproasters.sk/vyberova-kava/   # homepage doesn't link every product; the shop listing does
```

`slug` is the stable key `data/products.yaml` is keyed on (lowercase-kebab of the name). `url` is the roaster's canonical site link; `scrape_url` is the discovery entry point the scraper crawls for product links — usually the same page, but point it at the actual shop/listing page when the homepage doesn't link to every product. `metadata` is optional, added as roaster details are gathered — not required for the scraper to run. Add `scraper: playwright` to any roaster that requires JavaScript rendering (selects crawl4ai's browser-backed crawler instead of the HTTP one).

## Scraper (`scraper/scrape.py`)

Full design in [`Architecture.md`](./Architecture.md). Summary:

1. Load `roasters.yaml`.
2. Per roaster, **discover** product URLs from the listing page(s) via crawl4ai's `prefetch=True` mode (cheap — no LLM call), following pagination by hand.
3. Per discovered URL, fetch via crawl4ai (markdown output), hash it, and **skip the LLM call** if the hash matches what's already stored for that URL in `data/products.yaml`. Otherwise call the model (tool call left optional, not forced, so it can decline non-product pages) to extract `name`/`origin`/`process`/`roast_type`/`packaging` (multi-weight).
4. Diff this run's discovered URLs against `data/products.yaml`'s existing entries for that roaster — anything missing is genuinely delisted and gets dropped; anything new gets fetched.
5. Write a `scrape_status` summary (logged to stdout; not stored in either file).

### Scrape status values (per product, in `data/products.yaml`)
- `ok` — extracted a name and ≥1 valid price/weight tier
- `not_a_product` — discovered link wasn't actually a single coffee product page (cached so it isn't re-sent to the model every run)
- A fetch failure or JS-rendered-looking page leaves the existing entry untouched (no status overwrite, `last_seen` doesn't advance)

### LLM extraction (OpenRouter)
One call per product page's markdown via [OpenRouter](https://openrouter.ai/)'s OpenAI-compatible `/chat/completions` endpoint (`openai` SDK pointed at `base_url="https://openrouter.ai/api/v1"`), model `google/gemini-2.5-flash-lite`. The `extract_product` tool (OpenAI function-calling shape: `{"type": "function", "function": {...}}`) is available but not forced — this lets the model decline (plain text reply, no tool call) when a discovered URL turns out to be a category page, the homepage, or something that isn't coffee, rather than fabricating a product from whatever's on the page.

## GitHub Actions

### `scrape.yml` — daily data refresh

```yaml
on:
  schedule:
    - cron: '0 6 * * *'   # 6am UTC daily
  workflow_dispatch:        # manual trigger for testing

permissions:
  contents: write           # default GITHUB_TOKEN is read-only; needed to push
```

Steps: checkout → install deps → `crawl4ai-setup` (installs Playwright/Patchright browsers crawl4ai needs) → run scraper → commit `data/products.yaml` → push.

- Guard the commit so a no-change run doesn't fail the job:
  `git diff --quiet -- data/products.yaml || (git add data/products.yaml && git commit -m "data: $(date -u +%F)" && git push)`
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
- **Data source**: `CoffeeTable.astro`'s frontmatter reads `data/products.yaml` + `roasters.yaml` directly at build time (via `js-yaml`) and flattens them into table rows — no separate generated JSON file. `import.meta.env.DEV` still uses the hand-maintained `_data/coffees.sample.json` fixture for local dev. A new scrape requires a rebuild (handled by `pages.yml`).
- **`astro.config.mjs`**: set `site: 'https://<user>.github.io'` and `base: '/scm'` for a project Pages site, or links 404.
- **UI**: filterable/sortable table
  - Dropdowns: roaster, origin, process
  - Sort: price (asc/desc)
  - Implementation: vanilla JS in a `<script>` inside the `.astro` component, no framework island.

## Brand & Design System

See [`Design.md`](./Design.md) — logo, colour palette, typography, and spacing rules. All rules there are binding when writing UI code.

## Environment Variables / Secrets

- `OPENROUTER_API_KEY` — required by scraper (OpenRouter, model `google/gemini-2.5-flash-lite`), stored as GitHub Actions secret

## Development

```bash
# Install scraper deps
pip install -r scraper/requirements.txt

# Run scraper locally
OPENROUTER_API_KEY=... python scraper/scrape.py

# Serve site locally
npm install
npm run dev          # astro dev server with live reload
```

## Adding a New Roaster

1. Add entry to `roasters.yaml` (`name`, `slug`, `url`)
2. Run scraper locally to verify extraction works
3. If output is empty, add `scraper: playwright` and re-test
4. Commit `roasters.yaml` — next cron run picks it up
