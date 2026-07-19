# Graph Report - .  (2026-07-19)

## Corpus Check
- 157 files · ~201,395 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 846 nodes · 1439 edges · 56 communities (46 shown, 10 thin omitted)
- Extraction: 96% EXTRACTED · 4% INFERRED · 0% AMBIGUOUS · INFERRED: 55 edges (avg confidence: 0.79)
- Token cost: 566,904 input · 12,000 output

## Community Hubs (Navigation)
- Scraper Test Suite
- Crawler Test Fakes
- Astro UI Components
- Architecture & Pipeline Docs
- Products Data & Roasters
- Shop Variation Tests
- Site Dependencies
- Scraper Core & Persistence
- Content Wrapper Pages
- Dev & Test Dependencies
- Products Schema & Plans
- Run Checkpoint Tests
- Roaster Map & Digest
- Origins Data Layer
- Coffee Table Pages
- EN/SK i18n Layer
- Page Parsing & Variations
- Origins Pages & Choropleth
- Brew Method Recipes
- LLM Extraction Core
- Product URL Discovery
- Scrape Status Tests
- Design Skill Library
- Product Normalization
- Espresso Cube Drinks
- Roaster Config Schema
- WooCommerce Attribute Parsing
- Public Dataset & About
- Origin Alias Matching
- Header Nav Data
- Logo Mark SVG
- Logo Mark 1024px
- Roaster Health Registry
- Lighthouse CI Gates
- Favicon Brand Identity
- Kamenicky Portrait Anomaly
- Logo Mark 512px
- TypeScript Config
- Canary Extraction Tests
- Price History Tests
- Hand-Made Dev Fixtures
- Page Hash Gating
- WooCommerce Pricing Plan
- Model Fallback Test
- Politeness Delay Tests
- Usage Tracking Tests
- Content Collections Config
- Bug Issue Template
- Scraper Package Meta

## God Nodes (most connected - your core abstractions)
1. `../layouts/Layout.astro` - 63 edges
2. `FakeCrawler` - 57 edges
3. `products.yaml Scraped Data Artifact` - 50 edges
4. `fake_result()` - 49 edges
5. `fake_completion()` - 42 edges
6. `_soup()` - 34 edges
7. `../../../components/CoffeeTable.astro` - 33 edges
8. `fake_tool_call()` - 30 edges
9. `fake_markdown()` - 29 edges
10. `listing_result()` - 28 edges

## Surprising Connections (you probably didn't know these)
- `WooCommerce Variation Pricing Implementation Plan` --references--> `extract_woocommerce_variations()`  [EXTRACTED]
  docs/superpowers/plans/2026-07-08-woocommerce-variation-pricing.md → scraper/scrape.py
- `Variations JSON Folded into Page Hash` --rationale_for--> `process_roaster()`  [EXTRACTED]
  docs/superpowers/plans/2026-07-08-woocommerce-variation-pricing.md → scraper/scrape.py
- `process_roaster()` --references--> `schema_version Stamp / Forced Re-extraction`  [EXTRACTED]
  scraper/scrape.py → data/products.schema.yaml
- `../../../components/CoffeeTable.astro` --shares_data_with--> `_data/coffees.sample.json Dev Fixture`  [EXTRACTED]
  src/components/CoffeeTable.astro → docs/superpowers/plans/2026-06-30-astro-starlight-site.md
- `normalize_origin()` --references--> `coffee_origins.yaml — Canonical Origin Country Alias Table`  [EXTRACTED]
  scraper/scrape.py → data/coffee_origins.yaml

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Anti-Generic-AI Frontend Design Skill Family** — claude_skills_design_taste_frontend_skill, claude_skills_gpt_taste_skill, claude_skills_high_end_visual_design_skill, claude_skills_minimalist_ui_skill, claude_skills_redesign_existing_projects_skill [INFERRED 0.85]
- **Weekly Scrape -> Commit -> Build -> Deploy Pipeline** — github_workflows_scrape, github_workflows_pages, architecture_discovery_pipeline, github_workflows_pages_workflow_run_trigger [EXTRACTED 1.00]
- **Stable-Titled Deduplicated gh-issue Escalation Pattern** — github_workflows_scrape_escalation_step, github_workflows_pages_alert_on_failure, claude_observability [EXTRACTED 1.00]
- **Product Entry Status Vocabulary** — data_products_schema_ok_product, data_products_schema_incomplete_product, data_products_schema_not_a_product, data_products_status_vocabulary [EXTRACTED 1.00]
- **Scrape-time Normalization and Validation Pipeline** — scraper_scrape_normalize_origin, scraper_scrape_normalize_process, scraper_scrape_normalize_roast_type, scraper_scrape_normalize_product, scraper_scrape_validate_entry, scraper_scrape_process_roaster [EXTRACTED 1.00]
- **Weekly Scrape-to-Pages Publishing Pipeline** — github_workflows_scrape, github_workflows_pages, data_products, src_components_coffeetable [EXTRACTED 1.00]
- **RecipeCard-driven brew ratio pages** — src_content_docs_brew_methods_cold_brew, src_content_docs_brew_methods_french_press, src_content_docs_brew_methods_v60, src_content_docs_sk_brew_methods_aeropress, src_content_docs_sk_brew_methods_cold_brew, src_content_docs_sk_brew_methods_french_press, src_content_docs_sk_brew_methods_v60, src_components_recipecard [EXTRACTED 1.00]
- **Coffee-with-milk drink recipes** — src_content_docs_drinks_filterccino, src_content_docs_drinks_filter_ice_cappuccino, src_content_docs_drinks_espresso_cube_cappuccino [INFERRED 0.75]

## Communities (56 total, 10 thin omitted)

### Community 0 - "Scraper Test Suite"
Cohesion: 0.01
Nodes (11): test_crawl_listing_links_page1_failure_is_not_failed_midway(), test_discover_product_urls_failed_when_first_page_unreachable(), test_discover_roast_type_hints_empty_when_not_configured(), test_extract_product_raises_on_empty_response(), test_extract_product_raises_on_malformed_tool_call_json(), test_extract_product_raises_on_truncated_response(), test_extract_product_returns_none_when_model_explicitly_declines(), test_extract_shopify_variations_endpoint_failure_returns_empty() (+3 more)

### Community 1 - "Crawler Test Fakes"
Cohesion: 0.09
Nodes (70): fake_completion(), fake_markdown(), fake_result(), fake_tool_call(), FakeCrawler, _incomplete_prior(), listing_result(), _mystery_crawler() (+62 more)

### Community 2 - "Astro UI Components"
Cohesion: 0.06
Nodes (43): RFC-4180, ../../components/Card.astro, ../../components/CardGrid.astro, ./FluidBackground.astro, ../../components/HeroVideoDark.astro, ../../components/MemeCard.astro, badgeVariants, ../components/ui/Button.astro (+35 more)

### Community 3 - "Architecture & Pipeline Docs"
Cohesion: 0.06
Nodes (41): Architecture.md — Discovery Pipeline Architecture, Two-Phase Discover-then-Detail Scraping Pipeline, SHA-256 Hash-Gated Extraction, Mass-Delisting Guard (suspect status), Unforced (Optional) extract_product Tool Call, Partial-Discovery Preservation (pagination_status), SCHEMA_VERSION Forced Re-Extraction, WooCommerce Variations Structural Extraction (+33 more)

### Community 4 - "Products Data & Roasters"
Cohesion: 0.06
Nodes (36): products.yaml Scraped Data Artifact, Packaging Tiers (weight_g / price / variant), Product Status Vocabulary (ok / incomplete / not_a_product), 9 Grams Coffee (Žilina), Alternativ Coffee (Nové Mesto nad Váhom), Black. (Bratislava), Blue Mondays Coffee (Bratislava), Caffe4u (Bratislava) (+28 more)

### Community 5 - "Shop Variation Tests"
Cohesion: 0.06
Nodes (36): Build a BeautifulSoup the same way process_roaster does (issue #27:     the extr, Build a minimal Shoptet product page: trackingScript data-products     JSON + th, _shoptet_html(), _soup(), test_extract_shoptet_variations_absent_returns_empty(), test_extract_shoptet_variations_excludes_related_product_records(), test_extract_shoptet_variations_hash_projection_is_deterministic(), test_extract_shoptet_variations_keeps_distinct_grind_tiers_per_weight() (+28 more)

### Community 6 - "Site Dependencies"
Cohesion: 0.06
Nodes (33): astro, @astrojs/mdx, @astrojs/sitemap, clsx, @fontsource/dm-sans, @fontsource/dm-serif-display, js-yaml, dependencies (+25 more)

### Community 7 - "Scraper Core & Persistence"
Cohesion: 0.09
Nodes (28): append_price_history(), build_price_history_rows(), build_scrape_status_records(), emit_warning_annotations(), escalate_repeated_failures(), load_last_known_prices(), load_products(), load_roasters() (+20 more)

### Community 8 - "Content Wrapper Pages"
Cohesion: 0.11
Nodes (9): ../components/LogoIcon.astro, ../components/Wordmark.astro, ../layouts/Layout.astro, base, Lang, ../lib/lang, ../lib/nav, ../styles/custom.css (+1 more)

### Community 9 - "Dev & Test Dependencies"
Cohesion: 0.07
Nodes (27): @axe-core/playwright, d3-geo, devDependencies, @axe-core/playwright, d3-geo, playwright, @playwright/test, tailwindcss (+19 more)

### Community 10 - "Products Schema & Plans"
Cohesion: 0.10
Nodes (21): _data/coffees.json (Retired Flattened Artifact), products.schema.yaml (JSON Schema for products.yaml entries), Blend Metadata (blend / blend_origins, issue #91), incomplete_packaging_tier Definition, incomplete_product Definition, not_a_product Definition, ok_packaging_tier Definition, ok_product Definition (+13 more)

### Community 11 - "Run Checkpoint Tests"
Cohesion: 0.18
Nodes (19): FakeWebCrawler, Duck-typed async-context-manager stand-in for crawl4ai's AsyncWebCrawler.      r, test_run_appends_price_history_for_ok_products(), test_run_checkpoint_lock_serializes_concurrent_saves(), test_run_checkpointing_survives_later_fatal_crash(), test_run_checkpoints_save_products_after_each_roaster(), test_run_emits_warning_and_writes_step_summary_for_non_ok_roaster(), test_run_escalates_after_three_consecutive_non_ok_runs() (+11 more)

### Community 12 - "Roaster Map & Digest"
Cohesion: 0.12
Nodes (15): leaflet/dist/leaflet.css, ./Comments.astro, enabled, ../../components/RoasterLogoSlider.astro, ../../components/RoasterMap.astro, { markers, unmapped }, payload, ../components/WeeklyDigest.astro (+7 more)

### Community 13 - "Origins Data Layer"
Cohesion: 0.18
Nodes (16): listOrigins(), originJsonLd(), originSlug(), OriginSummary, bucketFor(), buildChoropleth(), ChoroplethData, CountryShape (+8 more)

### Community 14 - "Coffee Table Pages"
Cohesion: 0.11
Nodes (6): Design Audit Follow-ups, MD3 Token / !important Retirement (deferred), Tailwind v4 Scoped to src/components/ui/*, Stable English Filter Keys, ../../../components/CoffeeTable.astro, ../lib/priceHistory

### Community 15 - "EN/SK i18n Layer"
Cohesion: 0.14
Nodes (14): EN/SK Site Translation Implementation Plan, EN/SK Site Translation Design Spec, ../components/FreshnessBadge.astro, lastUpdated, Lang, localizedProcess(), localizedRoastType(), ORIGIN_LABELS (+6 more)

### Community 16 - "Page Parsing & Variations"
Cohesion: 0.14
Nodes (18): compute_page_hash(), discover_roast_type_hints(), extract_shopify_variations(), extract_shoptet_variations(), extract_woocommerce_variations(), is_valid_tier(), parse_weight(), _politeness_wait() (+10 more)

### Community 17 - "Origins Pages & Choropleth"
Cohesion: 0.21
Nodes (11): ../../../components/OriginsChoropleth.astro, base, displayName(), { shapes, unmatched, width, height }, localizedOrigin(), base, origins, base (+3 more)

### Community 18 - "Brew Method Recipes"
Cohesion: 0.22
Nodes (12): dots, Aeropress Brew Method Page, Cold Brew (brew method page), French Press (brew method page), V60 (brew method page), French Press (drink recipe), Aeropress (Slovak brew method page), Studena kava / Cold Brew (Slovak brew method page) (+4 more)

### Community 19 - "LLM Extraction Core"
Cohesion: 0.17
Nodes (12): Exception, extract_product(), ExtractionFailed, Hints, normalize_products(), extract_product couldn't get a usable response from the model.      Distinct fro, Ask the model to extract one product, or decline for a non-product page.      ``, Deterministic per-page signals gathered outside the LLM call.      Bundles what (+4 more)

### Community 20 - "Product URL Discovery"
Cohesion: 0.17
Nodes (12): _crawl_listing_links(), discover_product_urls(), find_next_page_url(), is_coffee(), looks_like_product_link(), Follow pagination from `start_url`, collecting same-domain product-ish links., Crawl a roaster's listing (following pagination) and return (urls, status)., Heuristic: True unless the name clearly names non-coffee (gear/gift/subscription (+4 more)

### Community 21 - "Scrape Status Tests"
Cohesion: 0.17
Nodes (12): _statuses_by_slug(), test_build_scrape_status_records_first_ok_run_has_zero_streak(), test_build_scrape_status_records_increments_streak_across_two_failed_runs(), test_build_scrape_status_records_partial_and_needs_js_count_as_non_ok(), test_build_scrape_status_records_preserves_untouched_roasters(), test_build_scrape_status_records_resets_streak_on_recovery(), test_emit_warning_annotations_only_for_non_ok(), test_emit_warning_annotations_silent_when_all_ok() (+4 more)

### Community 22 - "Design Skill Library"
Cohesion: 0.20
Nodes (11): design-taste-frontend Skill (Anti-Slop Frontend), Brief Inference / Design Read, The Three Dials (VARIANCE / MOTION / DENSITY), gpt-taste Skill (Awwwards-Level Design Engineering), AIDA Page Structure (Attention/Interest/Desire/Action), Python-Driven True Randomization, high-end-visual-design Skill (Awwwards-Tier UI Architect), Double-Bezel (Doppelrand) Nested Card Architecture (+3 more)

### Community 23 - "Product Normalization"
Cohesion: 0.20
Nodes (11): Same-Price-Different-Weights Collision Rule, normalize_blend_origins(), normalize_origin(), normalize_price(), normalize_process(), normalize_product(), Parse the first EUR amount out of a raw price string into a float.      Handles:, Bucket free-text processing method into a controlled English vocabulary.      Re (+3 more)

### Community 24 - "Espresso Cube Drinks"
Cohesion: 0.22
Nodes (10): Espresso Cube Cappuccino (drink recipe), Espresso Cube Tonic (drink recipe), Espresso Ice Cubes (shared ingredient), Filter Ice Cappuccino (drink recipe), Filterccino (drink recipe), Filter Coffee Base (shared ingredient), Espresso Cube Cappuccino (Slovak drink recipe), Espresso Cube Tonic (Slovak drink recipe) (+2 more)

### Community 25 - "Roaster Config Schema"
Cohesion: 0.25
Nodes (8): Casa del Caffe (Bratislava), Coffeein (Šahy), Ready After (Bošany), roasters.schema.yaml (JSON Schema for roasters.yaml entries), Required metadata.city, scraper: playwright Opt-in, roast_type_urls Category Hints, Spojka Roastery (Prešov)

### Community 26 - "WooCommerce Attribute Parsing"
Cohesion: 0.25
Nodes (8): extract_woocommerce_roast_type(), extract_woocommerce_weight(), normalize_roast_type(), Bucket free-text roast info into 'filter' / 'espresso' / 'nespresso' / 'drip-bag, Parse a WooCommerce product's "recommended preparation method" attribute row., Parse a WooCommerce product's built-in core "Weight" shipping field.      Unlike, Visible text of a WooCommerce product-attribute row's value cell, or None., woocommerce_attribute_text()

### Community 27 - "Public Dataset & About"
Cohesion: 0.36
Nodes (8): slovak-coffee-map Agent Skill, Public coffees.json Dataset Endpoint, EUR-per-100g Value Comparison, One-Sentence Ko-fi Support Nudge (issue #116), About the Data Page, AI Coffee Picker Page, O datach (Slovak About the Data page), AI vyber kavy (Slovak AI coffee-picker page)

### Community 28 - "Origin Alias Matching"
Cohesion: 0.33
Nodes (6): extract_woocommerce_origin(), load_country_aliases(), Fold accented characters to their plain ASCII base ("Salvádor" -> "Salvador")., Flatten data/coffee_origins.yaml into a {diacritic-free lowercase alias: canonic, Parse a WooCommerce product's "Additional information" origin attribute row., strip_diacritics()

### Community 29 - "Header Nav Data"
Cohesion: 0.33
Nodes (5): isNavGroup(), NAV, NavEntry, NavGroup, NavLink

### Community 30 - "Logo Mark SVG"
Cohesion: 0.50
Nodes (5): Slovak Coffee Map Logo Mark (SVG), Site Brand Asset / Favicon Role, Brand Palette (Toxic Orange #FF6037 on Black Kite #351E1C), Coffee Bean Motif, Map Pin / Location Marker Motif

### Community 31 - "Logo Mark 1024px"
Cohesion: 0.50
Nodes (5): Slovak Coffee Map Logo Mark (1024px), App-Icon / Favicon Brand Asset Role, SCM Brand Palette (Toxic Orange on Black Kite), Coffee Bean Negative-Space Motif, Map Pin Iconography

### Community 32 - "Roaster Health Registry"
Cohesion: 0.50
Nodes (4): scrape_status.yaml Roaster Health Artifact, consecutive_non_ok Streak Counter, roasters.yaml Roaster Registry, Trinity Beans (Ružomberok)

### Community 34 - "Lighthouse CI Gates"
Cohesion: 0.67
Nodes (4): E2E Smoke Tests Workflow (Playwright + Lighthouse), Lighthouse Budget Job (a11y hard gate), Lighthouse Report for /scm/coffees/ (2026-07-12, Lighthouse 12.6.1), Lighthouse Scores: Perf 0.92 / A11y 0.96 / Best-Practices 1.0 / SEO 1.0

### Community 35 - "Favicon Brand Identity"
Cohesion: 0.67
Nodes (4): Brand Palette Usage (Black Kite #351E1C, Toxic Orange #FF6037), Coffee-Bean-in-Map-Pin Mark, Site Favicon (Coffee-Bean Map Pin), Slovak Coffee Map Visual Identity

### Community 36 - "Kamenicky Portrait Anomaly"
Cohesion: 0.67
Nodes (3): Kamenicky 2024 Portrait Photo (public asset), Portrait subject: middle-aged man in navy suit and tie (filename suggests a Slovak public figure, 2024), Slovak Coffee Map public/ static asset folder

### Community 37 - "Logo Mark 512px"
Cohesion: 0.67
Nodes (3): Brand Palette Usage (Toxic Orange on Black Kite), Slovak Coffee Map Logo Mark (512px), Map Pin with Coffee Bean Iconography

### Community 39 - "Canary Extraction Tests"
Cohesion: 0.67
Nodes (3): _canary_client(), test_run_canary_passes_on_expected_extraction(), test_run_canary_warns_on_field_drift()

### Community 40 - "Price History Tests"
Cohesion: 0.67
Nodes (3): _history_products(), test_build_price_history_rows_appends_only_changed_prices(), test_build_price_history_rows_records_every_ok_tier_on_first_run()

## Knowledge Gaps
- **151 isolated node(s):** `packageManager`, `dev`, `build`, `preview`, `scrape` (+146 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **10 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `products.yaml Scraped Data Artifact` connect `Products Data & Roasters` to `Roaster Health Registry`, `Architecture & Pipeline Docs`, `Scraper Core & Persistence`, `Page Hash Gating`, `Products Schema & Plans`, `WooCommerce Pricing Plan`, `Coffee Table Pages`, `Roaster Config Schema`, `Public Dataset & About`?**
  _High betweenness centrality (0.125) - this node is a cross-community bridge._
- **Why does `../../../components/CoffeeTable.astro` connect `Coffee Table Pages` to `Roaster Health Registry`, `Astro UI Components`, `Products Data & Roasters`, `Hand-Made Dev Fixtures`, `Products Schema & Plans`, `Roaster Map & Digest`, `Origins Data Layer`, `EN/SK i18n Layer`, `Origins Pages & Choropleth`?**
  _High betweenness centrality (0.112) - this node is a cross-community bridge._
- **Why does `../layouts/Layout.astro` connect `Content Wrapper Pages` to `Astro UI Components`, `Roaster Map & Digest`, `Origins Data Layer`, `Coffee Table Pages`, `EN/SK i18n Layer`, `Origins Pages & Choropleth`, `Header Nav Data`?**
  _High betweenness centrality (0.054) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `products.yaml Scraped Data Artifact` (e.g. with `scrape_status.yaml Roaster Health Artifact` and `Public coffees.json Dataset Endpoint`) actually correct?**
  _`products.yaml Scraped Data Artifact` has 3 INFERRED edges - model-reasoned connections that need verification._
- **What connects `packageManager`, `dev`, `build` to the rest of the system?**
  _151 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Scraper Test Suite` be split into smaller, more focused modules?**
  _Cohesion score 0.0136986301369863 - nodes in this community are weakly interconnected._
- **Should `Crawler Test Fakes` be split into smaller, more focused modules?**
  _Cohesion score 0.0903755868544601 - nodes in this community are weakly interconnected._