# Codebase Map

Generated: 2026-07-20T22:15:59Z | Files: 169 | Described: 0/169
<!-- gsd:codebase-meta {"generatedAt":"2026-07-20T22:15:59Z","fingerprint":"48f4e7283a101fe942fdf497b9046bd83dc70808","fileCount":169,"truncated":false} -->

### (root)/
- `.env.example`
- `.gitignore`
- `.lighthouserc.json`
- `.node-version`
- `Architecture.md`
- `astro.config.mjs`
- `CLAUDE.md`
- `Design.md`
- `LICENSE`
- `package-lock.json`
- `package.json`
- `playwright.config.ts`
- `pnpm-lock.yaml`
- `PRODUCT.md`
- `README.md`
- `roasters.schema.yaml`
- `roasters.yaml`
- `skills-lock.json`
- `tsconfig.json`

### .github/
- `.github/dependabot.yml`

### .github/ISSUE_TEMPLATE/
- `.github/ISSUE_TEMPLATE/bug-report.yml`
- `.github/ISSUE_TEMPLATE/config.yml`
- `.github/ISSUE_TEMPLATE/wrong-data.yml`

### .github/workflows/
- `.github/workflows/ci.yml`
- `.github/workflows/e2e.yml`
- `.github/workflows/pages.yml`
- `.github/workflows/scrape.yml`

### .lighthouseci/
- `.lighthouseci/assertion-results.json`
- `.lighthouseci/lhr-1783882915218.html`
- `.lighthouseci/lhr-1783882915218.json`
- `.lighthouseci/links.json`

### .opencode/goals/
- `.opencode/goals/state.json`

### .opencode/goals/state.json.lock/
- `.opencode/goals/state.json.lock/owner.json`

### data/
- `data/coffee_origins.yaml`
- `data/price_history.csv`
- `data/products.schema.yaml`
- `data/products.yaml`
- `data/scrape_status.yaml`

### docs/
- `docs/design-audit-followups.md`

### docs/superpowers/plans/
- `docs/superpowers/plans/2026-06-30-astro-starlight-site.md`
- `docs/superpowers/plans/2026-06-30-ci-workflows.md`
- `docs/superpowers/plans/2026-07-05-products-schema-migration.md`
- `docs/superpowers/plans/2026-07-08-woocommerce-variation-pricing.md`
- `docs/superpowers/plans/2026-07-11-i18n-en-sk.md`

### docs/superpowers/specs/
- `docs/superpowers/specs/2026-06-30-astro-starlight-site-design.md`
- `docs/superpowers/specs/2026-06-30-ci-workflows-design.md`
- `docs/superpowers/specs/2026-07-05-products-schema-migration-design.md`
- `docs/superpowers/specs/2026-07-11-i18n-en-sk-design.md`

### e2e/
- `e2e/a11y.spec.ts`
- `e2e/blends.spec.ts`
- `e2e/coffee-table.spec.ts`
- `e2e/map.spec.ts`

### graphify-out/
- `graphify-out/.graphify_labels.json`
- `graphify-out/cost.json`
- `graphify-out/GRAPH_REPORT.md`
- `graphify-out/graph.html`
- `graphify-out/graph.json`
- `graphify-out/manifest.json`

### scraper/
- `scraper/canary_page.md`
- `scraper/pyproject.toml`
- `scraper/scrape.py`
- `scraper/test_scrape.py`

### skills/slovak-coffee-map/
- `skills/slovak-coffee-map/SKILL.md`

### src/
- `src/content.config.ts`

### src/components/
- `src/components/Card.astro`
- `src/components/CardGrid.astro`
- `src/components/CoffeeTable.astro`
- `src/components/Comments.astro`
- `src/components/FluidBackground.astro`
- `src/components/FreshnessBadge.astro`
- `src/components/HeroVideoDark.astro`
- `src/components/LogoIcon.astro`
- `src/components/MemeCard.astro`
- `src/components/OriginsChoropleth.astro`
- `src/components/RecipeCard.astro`
- `src/components/RoasterLogoSlider.astro`
- `src/components/RoasterMap.astro`
- `src/components/WeeklyDigest.astro`
- `src/components/Wordmark.astro`

### src/components/ui/
- `src/components/ui/Badge.astro`
- `src/components/ui/Button.astro`

### src/content/docs/
- `src/content/docs/about-data.mdx`
- `src/content/docs/ai-coffee.mdx`

### src/content/docs/brew-methods/
- `src/content/docs/brew-methods/aeropress.mdx`
- `src/content/docs/brew-methods/cold-brew.mdx`
- `src/content/docs/brew-methods/french-press.mdx`
- `src/content/docs/brew-methods/v60.mdx`

### src/content/docs/drinks/
- `src/content/docs/drinks/espresso-cube-cappuccino.mdx`
- `src/content/docs/drinks/espresso-cube-tonic.mdx`
- `src/content/docs/drinks/filter-ice-cappuccino.mdx`
- `src/content/docs/drinks/filterccino.mdx`
- `src/content/docs/drinks/french-press.mdx`

### src/content/docs/sk/
- `src/content/docs/sk/about-data.mdx`
- `src/content/docs/sk/ai-coffee.mdx`

### src/content/docs/sk/brew-methods/
- `src/content/docs/sk/brew-methods/aeropress.mdx`
- `src/content/docs/sk/brew-methods/cold-brew.mdx`
- `src/content/docs/sk/brew-methods/french-press.mdx`
- `src/content/docs/sk/brew-methods/v60.mdx`

### src/content/docs/sk/drinks/
- `src/content/docs/sk/drinks/espresso-cube-cappuccino.mdx`
- `src/content/docs/sk/drinks/espresso-cube-tonic.mdx`
- `src/content/docs/sk/drinks/filter-ice-cappuccino.mdx`
- `src/content/docs/sk/drinks/filterccino.mdx`
- `src/content/docs/sk/drinks/french-press.mdx`

### src/layouts/
- `src/layouts/Layout.astro`

### src/lib/
- `src/lib/coffees.ts`
- `src/lib/digest.ts`
- `src/lib/i18n.ts`
- `src/lib/lang.ts`
- `src/lib/mapData.ts`
- `src/lib/nav.ts`
- `src/lib/origins.ts`
- `src/lib/originsMap.ts`
- `src/lib/priceHistory.ts`
- `src/lib/recipes.ts`
- `src/lib/utils.ts`

### src/pages/
- `src/pages/404.astro`
- `src/pages/about-data.astro`
- `src/pages/ai-coffee.astro`
- `src/pages/coffees.json.ts`
- `src/pages/digest.xml.ts`
- `src/pages/index.astro`
- `src/pages/map.astro`
- `src/pages/stats.astro`
- `src/pages/this-week.astro`

### src/pages/api/
- `src/pages/api/stats.json.ts`

### src/pages/brew-methods/
- `src/pages/brew-methods/aeropress.astro`
- `src/pages/brew-methods/cold-brew.astro`
- `src/pages/brew-methods/french-press.astro`
- `src/pages/brew-methods/v60.astro`

### src/pages/coffees/
- `src/pages/coffees/blends.astro`
- `src/pages/coffees/decaf.astro`
- `src/pages/coffees/drip-bags.astro`
- `src/pages/coffees/espresso.astro`
- `src/pages/coffees/filter.astro`
- `src/pages/coffees/index.astro`
- `src/pages/coffees/nespresso.astro`

### src/pages/drinks/
- `src/pages/drinks/espresso-cube-cappuccino.astro`
- `src/pages/drinks/espresso-cube-tonic.astro`
- `src/pages/drinks/filter-ice-cappuccino.astro`
- `src/pages/drinks/filterccino.astro`
- `src/pages/drinks/french-press.astro`

### src/pages/origins/
- `src/pages/origins/[slug].astro`
- `src/pages/origins/index.astro`

### src/pages/sk/
- `src/pages/sk/about-data.astro`
- `src/pages/sk/ai-coffee.astro`
- `src/pages/sk/index.astro`
- `src/pages/sk/map.astro`
- `src/pages/sk/stats.astro`
- `src/pages/sk/this-week.astro`

### src/pages/sk/brew-methods/
- `src/pages/sk/brew-methods/aeropress.astro`
- `src/pages/sk/brew-methods/cold-brew.astro`
- `src/pages/sk/brew-methods/french-press.astro`
- `src/pages/sk/brew-methods/v60.astro`

### src/pages/sk/coffees/
- `src/pages/sk/coffees/blends.astro`
- `src/pages/sk/coffees/decaf.astro`
- `src/pages/sk/coffees/drip-bags.astro`
- `src/pages/sk/coffees/espresso.astro`
- `src/pages/sk/coffees/filter.astro`
- `src/pages/sk/coffees/index.astro`
- `src/pages/sk/coffees/nespresso.astro`

### src/pages/sk/drinks/
- `src/pages/sk/drinks/espresso-cube-cappuccino.astro`
- `src/pages/sk/drinks/espresso-cube-tonic.astro`
- `src/pages/sk/drinks/filter-ice-cappuccino.astro`
- `src/pages/sk/drinks/filterccino.astro`
- `src/pages/sk/drinks/french-press.astro`

### src/pages/sk/origins/
- `src/pages/sk/origins/[slug].astro`
- `src/pages/sk/origins/index.astro`

### src/styles/
- `src/styles/custom.css`
- `src/styles/tailwind.css`
