# Slovak Coffee Map

Daily-updated catalogue of coffees available on the Slovak market, scraped from roaster websites, stored as JSON, and published via GitHub Pages (Astro + [Starlight](https://starlight.astro.build/)).

> ponytail: Starlight is a docs framework; for one filterable table, plain Astro (no Starlight) is lighter. Keeping Starlight as requested for theme/chrome — drop it for `@astrojs` base if the docs sidebar/search become noise.

## Architecture

```
roasters.yaml          ← seed list of roasters + per-site scraper overrides
scraper/
  scrape.py            ← main entrypoint: fetch → AI extract → write JSON
  requirements.txt
_data/
  coffees.json         ← scraper output; imported by the Astro page (plain import, no magic)
src/
  content/docs/index.mdx   ← Starlight page embedding the table component
  components/CoffeeTable.astro  ← filterable/sortable table (imports ../../_data/coffees.json)
astro.config.mjs       ← Astro + Starlight config (site + base for project Pages)
package.json           ← astro, @astrojs/starlight, starlight-theme-md3 (npm)
.github/workflows/
  scrape.yml           ← daily cron, commits coffees.json (push triggers pages.yml)
  pages.yml            ← build Astro + deploy to Pages on push to main / manual
.gitignore             ← dist/, node_modules/, .astro/, __pycache__/, .venv/
```

## Data Schema

Each entry in `_data/coffees.json`:

```json
{
  "name": "Ethiopia Yirgacheffe",
  "roaster": "Kaffa Roastery",
  "origin": "Ethiopia",
  "process": "Washed",
  "price": 12.90,
  "weight_g": 250,
  "url": "https://kaffaroastery.sk/...",
  "last_seen": "2026-06-30"
}
```

- **Required**: `name`, `roaster`, `price`, `url`. Drop any extracted entry missing these.
- **Optional / nullable**: `origin`, `process`, `weight_g` — set `null` when the page doesn't state them. Don't guess.
- `price` is **EUR**, stored as a JSON number with a `.` decimal. Slovak sites display `12,90 €` — normalize comma→dot and strip the currency symbol during extraction.
- `last_seen` = date of the last **successful** scrape that included this item (`YYYY-MM-DD`). It stops advancing while the roaster is `failed`/`needs_js`, so a stale `last_seen` flags a roaster that's been unreachable.

Out-of-stock items are **deleted** on the next successful run for that roaster (see Scraper step 4). Git history is the changelog.

## Roaster Config (`roasters.yaml`)

```yaml
roasters:
  - name: Kavoholik
    url: https://kavoholik.sk/
  - name: Ready After
    url: https://www.readyafter.sk/
  - name: Kaffa Roastery
    url: https://kaffaroastery.sk/
  - name: Suca Roastery
    url: https://www.sucaroastery.sk/
  - name: Coffeein
    url: https://www.coffeein.sk/
    scraper: playwright   # opt-in for JS-heavy sites
```

Add `scraper: playwright` to any roaster that requires JavaScript rendering.

## Scraper (`scraper/scrape.py`)

1. Load `roasters.yaml`
2. For each roaster: fetch product listing page(s) with `httpx` (or `playwright` if flagged). Send a real browser `User-Agent` (default httpx UA gets blocked/served bot pages), and follow pagination until no new products appear.
3. Pass raw HTML to Claude API with a JSON schema prompt to extract fields
4. Merge results into `coffees.json`:
   - Status `ok` → **replace** that roaster's entries with the fresh set (out-of-stock items vanish).
   - Status `failed` / `needs_js` → **keep** that roaster's existing entries untouched. A transient outage must never wipe a roaster's data; their `last_seen` simply stops advancing until the next successful run.
5. Write a `scrape_status` summary (logged to stdout; not stored in `coffees.json`)

### Scrape status values
- `ok` — extracted ≥1 product
- `failed` — HTTP error or no products extracted
- `needs_js` — page returned empty/suspicious HTML (likely JS-rendered; add `scraper: playwright`)

### Claude API extraction prompt pattern
Send the raw product page HTML and ask for a JSON array matching the schema above. Use `claude-haiku-4-5-20251001` for cost efficiency. Schema-validate the response before writing.

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

Steps: checkout → install deps → (`playwright install --with-deps chromium` if any roaster uses playwright) → run scraper → commit `_data/coffees.json` → push.

- Guard the commit so a no-change run doesn't fail the job:
  `git diff --quiet -- _data/coffees.json || (git commit -am "data: $(date -u +%F)" && git push)`
- The push to `main` triggers `pages.yml` — that's the only thing that publishes.

### `pages.yml` — build & deploy (Astro is **not** auto-built by Pages)

Unlike Jekyll, GitHub Pages does not build Astro for you. A workflow must run `astro build` and deploy `dist/`.

```yaml
on:
  push:
    branches: [main]        # fires after scrape.yml commits fresh data
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write
```

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
- **Data source**: plain `import coffees from '../../_data/coffees.json'` inside `CoffeeTable.astro`. No `site.data` magic — JSON is bundled at build time, so a new scrape requires a rebuild (handled by `pages.yml`).
- **`astro.config.mjs`**: set `site: 'https://<user>.github.io'` and `base: '/scm'` for a project Pages site, or links 404.
- **UI**: filterable/sortable table
  - Dropdowns: roaster, origin, process
  - Sort: price (asc/desc)
  - Implementation: vanilla JS in a `<script>` inside the `.astro` component, no framework island.

## Environment Variables / Secrets

- `ANTHROPIC_API_KEY` — required by scraper, stored as GitHub Actions secret

## Development

```bash
# Install scraper deps
pip install -r scraper/requirements.txt

# Run scraper locally
ANTHROPIC_API_KEY=... python scraper/scrape.py

# Serve site locally
npm install
npm run dev          # astro dev server with live reload
```

## Adding a New Roaster

1. Add entry to `roasters.yaml`
2. Run scraper locally to verify extraction works
3. If output is empty, add `scraper: playwright` and re-test
4. Commit `roasters.yaml` — next cron run picks it up
