[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/slovakcoffeemap)

# Slovak Coffee Map

Weekly-updated catalogue of coffees available on the Slovak market, scraped from roaster websites, stored as JSON, and published via GitHub Pages (Astro + Starlight).

**Live site:** https://peterhadac.github.io/scm/

## How it works

```mermaid
flowchart TD
    W["Roaster websites"] --> D
    W --> L

    subgraph scrape["scrape.yml — weekly cron (Mon 6:00 UTC)"]
        R[("roasters.yaml<br/>seed list + per-site overrides")] --> D["Discover product URLs<br/>(crawl4ai, no LLM)"]
        D --> H{"Page hash changed<br/>since last run?"}
        H -- "no" --> S["Skip — keep existing entry"]
        H -- "yes" --> L["LLM extraction<br/>(OpenRouter · gemini-2.5-flash-lite)"]
        L --> N["Normalize + validate<br/>origin, process, roast_type, packaging"]
        N --> P[("data/products.yaml<br/>ok / incomplete / not_a_product")]
        S --> P
        P --> C["Commit + push to main"]
    end

    C -. "workflow_run: completed" .-> B
    U["Human push to main"] --> B

    subgraph pages["pages.yml — build & deploy"]
        B["astro build<br/>(coffees.ts reads products.yaml + roasters.yaml)"] --> T["CoffeeTable.astro<br/>filterable/sortable table"]
        T --> G["Deploy dist/ to GitHub Pages"]
    end
```

See [`Architecture.md`](./Architecture.md) for the full scraping pipeline and [`CLAUDE.md`](./CLAUDE.md) for the project layout.

## Adding a roaster

1. Add an entry (`name`, `slug`, `url`, `scrape_url`) to `roasters.yaml`.
2. Run the scraper locally to verify extraction works (see below).
3. If extraction comes back empty, the site likely needs JS rendering —
   add `scraper: playwright` to the roaster entry and re-test.
4. Commit `roasters.yaml`; the next weekly cron run picks it up.

Full details, including `roast_type_urls` for sites that only reveal roast
type via category pages, are in [`CLAUDE.md`](./CLAUDE.md#adding-a-new-roaster).

## Development

```bash
# Scraper
pip install -r scraper/requirements.txt
OPENROUTER_API_KEY=... python scraper/scrape.py

# Site
npm install
npm run dev   # astro dev server with live reload
```

## License

Code is licensed under the [MIT License](./LICENSE). `data/products.yaml`
contains facts (prices, weights, origins) scraped from third-party roaster
shops — the license covers the code, not any claim of ownership over that
data.
