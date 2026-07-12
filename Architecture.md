# Discovery Pipeline Architecture

A per-product scraping pipeline: crawl4ai **discovers** product URLs on each roaster's listing page, then **fetches detail** for each one individually, skipping unchanged pages via a content hash. Implemented in `scraper/scrape.py`; verified end-to-end against a real roaster site (Jungle Roastery) — see [Open follow-up work](#open-follow-up-work) for what's still outstanding.

## Overview

The scraper used to be single-phase: one LLM call per roaster, fed the whole listing page's HTML. That couldn't tell "a product disappeared" from "the whole roaster failed to load," couldn't skip LLM calls for unchanged pages, and couldn't represent a coffee sold in more than one package size.

The current design discovers product URLs cheaply (no LLM call), then fetches and extracts each product individually, gated by a SHA-256 hash of the page's markdown so a re-run only pays for a Gemini call when a page actually changed. Fetching is done via [crawl4ai](https://github.com/unclecode/crawl4ai) rather than raw `httpx`/`playwright`.

## Data Flow

```
roasters.yaml (human-edited seed: name, slug, url, scraper override, metadata)
      │
      ▼
discover_product_urls()  — crawl4ai prefetch=True fetch of the listing page(s),
      │                    following pagination; no LLM call, nothing persisted
      ▼
data/products.yaml (per-product fields, page_hash, status, missing_fields,
      │              schema_version, packaging — validated against
      │              data/products.schema.yaml before being saved; the ONLY
      │              generated artifact, and also the record of "what did we
      │              know about last time" for removal detection)
      ▼
src/components/CoffeeTable.astro (site UI — reads data/products.yaml +
      │                            roasters.yaml directly at build time,
      │                            flattens ok-status packaging into rows)
```

There is deliberately **no separate `data/index.yaml`**. An earlier design persisted discovered URLs there so a later run could diff against them — but crawl4ai's `prefetch=True` mode makes discovery cheap enough (one plain HTTP fetch per listing page, no markdown generation, no LLM call) to redo fully fresh every run. Removed-product detection instead diffs *this run's* freshly discovered URLs against the URLs already present in `data/products.yaml` (in-memory, no prior index needed).

## Files & Ownership

| File | Owner | Committed |
|---|---|---|
| `roasters.yaml` | Human-edited | yes |
| `data/coffee_origins.yaml` | Human-edited (country list for origin normalization) | yes |
| `data/products.schema.yaml` | Human-edited (JSON Schema, validated on every scrape) | yes |
| `data/products.yaml` | Generated, sole scraped artifact | yes — must be committed so the *next* run can diff/hash-gate against it, and so the Astro build can read it directly |

`roasters.yaml` is the sole authority for roaster identity: `name` (display), `slug` (stable key `data/products.yaml` is keyed on), `url` (crawl entry point), optional `scraper: playwright` override, optional `metadata` (e.g. `city`). `data/products.yaml` never defines roaster identity itself.

## Discovery (`discover_product_urls`)

For each roaster, fetch the listing page(s) with `CrawlerRunConfig(prefetch=True, cache_mode=CacheMode.BYPASS)` — crawl4ai skips markdown generation/extraction entirely in this mode, so it's one plain HTTP(S) fetch per page, no LLM call. Pagination is still followed by hand (`find_next_page_url()` — crawl4ai has no built-in Slovak-aware "next page" primitive). Candidate product links come from `result.links["internal"]`, filtered by:
- same-domain (post-redirect) check,
- `looks_like_product_link()` — rejects obvious site plumbing (cart, login, legal, nav) by URL path segment,
- `is_coffee()` — rejects link text naming equipment/gift-cards/subscriptions.

This filter is a cheap first pass, not a guarantee — a nav link that slips through still costs one wasted fetch, but the model will decline to extract it (see below), and that decision gets cached so it isn't repeated every run.

A crawl that fails outright, or whose listing page looks JS-rendered (visible text under 200 chars), stops for that roaster this run — existing `data/products.yaml` entries are left untouched. A crawl that *succeeds* but discovers zero URLs while the roaster previously had entries is treated the same way (`needs_js`) rather than as "everything was removed" — a broken link filter or page restructure is far more likely than a real wipeout.

Pagination itself can also fail *partway through* rather than outright: `_crawl_listing_links()` (shared by `discover_product_urls()` and `discover_roast_type_hints()`) tracks a `pagination_status` alongside the URLs it collects — `"complete"` when it ran out of next-page links naturally (or the very first page failed, which is the total-failure case above, not this one), `"failed_midway"` when a fetch on page 2+ raised or came back non-success, or `"capped"` when `MAX_PAGES` (30 — discovery pages are cheap: `prefetch=True`, no LLM call) was reached while a further page was still linked. `discover_product_urls()` surfaces the latter two as roaster status `"partial"` (logging a warning in each case) rather than folding them into `"ok"`: a partial discovery pass only knows about *some* of the roaster's listing pages, so `process_roaster()` must not read "not in this run's discovered set" as "delisted" for it (issue #22 — previously a single flaky pagination fetch, or any catalog with more than `MAX_PAGES` listing pages, would silently wipe every product only reachable from the unvisited pages, resetting their hash-gate too). On a `"partial"` run, products that a run *did* rediscover are still processed/hash-gated normally; only the drop-if-not-rediscovered step is skipped for the roaster's remaining prior entries — they're carried over untouched (`last_seen`/`page_hash` unchanged).

`discover_product_urls()` shares its pagination-following crawl loop (`_crawl_listing_links()`) with `discover_roast_type_hints()`, which crawls a roaster's optional `roasters.yaml` `roast_type_urls` category pages (e.g. a Shopify "espresso" collection or a Shoptet "kava-filter" category) and tags each discovered product URL with the category it came from. Some sites never state a roast type on the product page itself — only via which listing links to it — so `process_roaster` passes this per-URL hint into `normalize_product()` as a last-resort `roast_type` fallback, used only when the page's own content states nothing at all.

## Detail Extraction (`process_roaster`, `extract_product`, `normalize_product`)

For each discovered URL: fetch with `CrawlerRunConfig(cache_mode=CacheMode.BYPASS, markdown_generator=DefaultMarkdownGenerator())` — **no `PruningContentFilter`**. That content filter's density-based pruning was verified (against a real product page) to discard the weight/price selector widget — exactly the data extraction needs — so plain markdown conversion is used instead (still a ~13x size cut vs. raw HTML, just without the filter's data loss).

If the page is a WooCommerce variable product, `extract_woocommerce_variations()` parses its `data-product_variations` JSON attribute (BeautifulSoup, on the raw HTML — WooCommerce embeds every variation's price at initial page load, no browser rendering needed) into `{weight_g, price}` tiers directly, bypassing the LLM for pricing on those pages: markdown only ever shows the currently-selected variant's price, so asking the LLM to read prices off markdown silently loses every other weight tier. `normalize_product()` trusts these tiers over anything the LLM guesses when present.

`compute_page_hash()` hashes (SHA-256) the same `MAX_MARKDOWN_CHARS`-truncated markdown window that gets sent to Gemini, **plus the raw variations JSON string**, and compares to the product's stored `page_hash` — not the full raw markdown (issue #13: dynamic page chrome below that window — recommendation carousels, "N people viewing this", stock countdowns, rotating testimonials — would otherwise flip the hash on an otherwise-unchanged product every run, forcing a fresh paid/nondeterministic extraction each time). Folding in the variations JSON matters because a price change on a non-default variant never touches the visible markdown text, so hashing markdown alone would hash-gate that change away forever:
- **Unchanged**, and previous `status` was `ok` or `not_a_product` → skip the Gemini call entirely, just bump `last_seen`.
- **Changed** (or no prior hash) → call Gemini (`extract_product`) with the `extract_product` tool **not forced** (`tool_choice` left at the default `"auto"`). Forcing it was tried first and verified broken: the model fabricated a plausible-looking product from category pages, the homepage, and non-coffee pages that slipped past the discovery filter, because a forced tool call cannot decline. Leaving it optional lets the model reply in plain text (no `tool_use` block) for anything that isn't a single coffee product's page.

`normalize_product()` turns a raw extraction into a `products.yaml` entry: drops it if the name fails `is_coffee()`, parses each `packaging` tier's price/weight (reusing `normalize_price`/`parse_weight`), and drops tiers with no parseable price. A product with zero valid tiers is treated as "not extractable" — same as an explicit decline.

Some pages (confirmed live: Suca Roastery, on the Upgates platform — no structured extractor exists for it, unlike WooCommerce/Shopify) sell the same coffee across **two independent selector axes** — roast type (Espresso/Filter) crossed with weight — rather than weight alone. Since `roast_type` is one field per entry, a single entry can't represent both roast types' pricing. `normalize_products()` (plural) wraps `normalize_product()`: the LLM tags each `packaging` tier with its own `roast_type` when a page has this shape (see `EXTRACT_PRODUCT_TOOL`), and if 2+ distinct tagged roast types appear across tiers, it groups them and calls `normalize_product()` once per group — producing multiple entries that share a `url`/`name` but each carry only their own roast type's tiers, never assuming the two roast types share a price. When tiers carry 0 or 1 distinct tag, this is exactly one `normalize_product()` call, identical to before. `variation_tiers` (WooCommerce/Shopify) is out of scope for this splitting — neither extractor produces a per-tier roast_type today.

## Status & Freshness Semantics

A `url` normally maps to exactly one entry — except after a `normalize_products()` roast-type split (see above), where one `url` maps to two. `process_roaster()` gates re-extraction all-or-nothing per `url`: one page fetch backs however many entries currently exist for it, so a single stale `schema_version` among them is enough to force reprocessing of all of them together.

Per product:
- **`ok`** — extracted a name and ≥1 valid packaging tier. Fields, `page_hash`, `last_seen` all update.
- **`not_a_product`** — the model declined, or extraction yielded no usable packaging, for a URL with no prior good data. Cached (with `page_hash`, no `packaging`) so an unchanged nav/category link isn't re-fetched and re-sent to the model every run — it only costs one wasted call the first time, then nothing until the page's content actually changes.
- **A previously-`ok` product that declines** (page hash changed, but the model no longer sees a product there) keeps its last known-good entry untouched rather than being downgraded — more likely a transient hiccup than genuine in-place delisting.
- **Fetch failure / JS-shell page** (text under 200 chars) → keep the existing entry untouched, don't advance `last_seen`. A transient blip must never wipe a product.
- **Removed products** are detected by diffing: any URL present in the *previous* `data/products.yaml` for a roaster but absent from *this run's* successful discovery is genuinely delisted and dropped. (Guarded against a failed/suspicious-empty discovery — see above — **and** against a `"partial"` discovery pass, where "absent from this run" may just mean "on a listing page this run never reached.")
- **Mass-delisting guard** (issue #39): even a clean-looking discovery is treated as suspect when it would drop more than `MASS_DELIST_GUARD_FRACTION` (50%) of the roaster's `ok`/`incomplete` entries at once (with a `MASS_DELIST_GUARD_MIN_DROPPED` floor of 3, so tiny catalogues' ordinary churn passes). Roasters delist coffees a handful at a time — a site redesign that still parses as a listing but exposes only a few product links is the likelier explanation, so prior entries are preserved exactly like a `"partial"` run and the roaster reports status `"suspect"` (which warns, streaks in `data/scrape_status.yaml`, and escalates like any other non-ok status). Only `ok`/`incomplete` priors count: `not_a_product` noise vanishing en masse after a discovery-filter tightening (issue #37) must not trip this.

## Normalization & Validation

`normalize_product()` translates `origin`/`process`/`roast_type` into the
controlled English vocabularies documented in `CLAUDE.md`, backed by
`data/coffee_origins.yaml` for origin. A product missing `origin`,
`roast_type`, or any tier's `weight_g`/`price` becomes `status: incomplete`
with a `missing_fields` list, rather than being published with nulls or
dropped outright — two tiers sharing a price across different weights (a
sign the extraction didn't actually see distinct per-tier prices) marks the
whole product incomplete rather than trusting any of its tiers. Every entry
is validated against `data/products.schema.yaml` (via `validate_entry()`)
before being kept — a validation failure means a bug in this module, not bad
website content.

A `SCHEMA_VERSION` constant is stamped on every `ok`/`incomplete` entry.
`process_roaster`'s hash-gate only skips re-extraction when the prior
entry's `schema_version` matches the current one — this forces exactly one
re-extraction of every pre-existing entry after a normalization-rule change
ships (there's no cached raw LLM output to replay against new rules), after
which hash-gating resumes as normal.

An `incomplete` entry additionally bypasses the gate on up to
`MAX_INCOMPLETE_REEXTRACTIONS` (3) later runs even when its page hash is
unchanged (issue #36): a flaky extraction — the model missing a field the
page does state — self-heals on a retry, while a page that genuinely omits
the field stops burning a weekly LLM call once its per-entry
`reextract_attempts` counter (carried across runs only while the hash stays
identical, so any page change resets the budget) reaches the limit.

## Flatten / Build Step

Exploding each `ok`-status product's `packaging` array into one flat row per
`(product url, weight_g)`, deduped on that pair, and joining in the
roaster's display `name` from `roasters.yaml` by `slug`, now happens in
`src/components/CoffeeTable.astro`'s frontmatter at site-build time — there
is no Python-side flatten step or generated `_data/coffees.json` file
anymore. `incomplete`/`not_a_product` entries never reach the site.

## Cost & Politeness

Model: `google/gemini-2.5-flash-lite` via [OpenRouter](https://openrouter.ai/) ($0.10/$0.40 per 1M input/output tokens; originally `claude-haiku-4-5-20251001` direct via Anthropic at $1/$5 — switched for lower per-call cost, same tool-call-optional extraction behavior). The old pipeline made ~1 LLM call per roaster (~23/day, whole-listing extraction). Per-product detail fetching means one call per *product*, but the hash gate keeps steady-state cost low — verified live: a second run over unchanged pages made **zero** LLM calls. The one-time cost is the first run over all products per roaster (dozens), plus one wasted call per nav/category link that slips past discovery's filter (also a one-time cost — subsequently cached as `not_a_product`).

No per-domain rate limiting/delay exists yet — roasters are still processed sequentially (one at a time, no concurrency), which limits worst-case request rate against any single domain, but there's no explicit inter-request delay within a roaster's product loop.

## CI / Publishing

`.github/workflows/scrape.yml` installs deps via `crawl4ai-setup` (replaces the old `playwright install --with-deps chromium` — verified to be a strict superset) and commits `data/products.yaml` — this is what makes cross-run removal-detection and hash-gating possible, and it's also what the Astro build reads directly. `pages.yml` needs no changes; its `npm run build` step reads `data/products.yaml` at build time regardless of how that file was produced.

## Adding a Roaster

1. Add an entry to `roasters.yaml`: `name`, `slug` (lowercase-kebab of the name), `url`, optional `scraper: playwright`, optional `metadata`.
2. Run the scraper locally — it discovers product URLs and fetches detail into `data/products.yaml`; the Astro build reads that directly, no separate regeneration step needed.
3. If discovery finds nothing, add `scraper: playwright` and re-test.
4. Commit `roasters.yaml` — the next cron run picks it up.

## Open follow-up work

- **No per-domain rate limiting/jitter** for the product-detail loop within a roaster.
- **Only Jungle Roastery has been run against the new pipeline** so far (verified: discovery, hash-gate skip, removal-via-diff, listing-failure preservation, and the mixed HTTP/Playwright crawler path all confirmed live). The other 22 roasters' `data/products.yaml` entries still come from the old single-phase pipeline until a full production run happens — `git diff` per-roaster counts before/after that run to confirm no unexpected drops.
- `looks_like_product_link()`'s path-segment blocklist is necessarily incomplete per-site (verified: Jungle's own `/kava/` category page slipped through and had to be caught by the extraction-decline mechanism instead) — this is fine (the decline gets cached), but a roaster with an unusually link-heavy homepage will eat a few extra one-time model calls the first run.
