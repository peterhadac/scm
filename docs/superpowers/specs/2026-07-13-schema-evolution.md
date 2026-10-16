# Schema evolution proposals (issue #89)

Review of `roasters.yaml` and `data/products.yaml` schemas against the
feature wave (#54–#63, #81–#93) and what's plausibly next. Each proposal
carries its cost and a recommendation; accepted ones become their own
issues — this document changes no code.

## roasters.yaml

### R1. `metadata.latlng` alongside `city` — **recommend: yes**
The map (#59) keeps a hardcoded city→coordinates table in `mapData.ts`;
every new city means a code change. Move coordinates into the roaster
entry (`metadata: {city, lat, lng}`), keep the code table as fallback
during transition. Cost: config-only, no scraper impact.

### R2. `active: false` soft-delete — **recommend: yes**
Deleting a dead roaster from `roasters.yaml` orphans its `products.yaml`
block and its `price_history.csv` rows. An `active: false` flag stops
scraping + hides from the site while keeping history joinable. Cost: two
small guards (scraper skip, `flattenProducts` skip).

### R3. `social` links (instagram, facebook) — **recommend: later**
Only useful once roaster profile pages exist (revenue idea #4). No
consumer today; config noise until then.

### R4. `founded`, `description` — **recommend: later**
Same reasoning as R3 — profile-page material.

## data/products.yaml

### P1. Stable per-product `id` — **recommend: yes, soon**
Everything joins on `url` today (price history, hash gate, dedupe). A
roaster reshuffling permalinks silently orphans price history and
re-extracts everything as "new". A content-derived id
(`slug + normalized name + roast_type`) survives URL changes. Cost:
migration touch on price_history join + dedupe keys; no LLM change.
This is the one whose absence gets more expensive every week — history
keeps accumulating against unstable keys.

### P2. `decaf: true` flag — **recommend: yes**
Decafs are currently indistinguishable — a real purchase-decision field
(and a filter users will expect). Deterministic detection is nearly free
(`decaf`/`bezkofein` name keywords) plus an LLM tool param, mirroring the
blend pattern from #91. Cost: SCHEMA_VERSION bump (can ride along with
any other bump), one dropdown in the UI.

### P3. `tasting_notes: [string]` — **recommend: yes, capped**
Roasters publish them; shoppers search by them ("something with
blueberry"). Extraction is easy; the risk is vocabulary sprawl — so store
free-form but cap at 5 notes, lowercase, and treat as search/display data
(never a filter dropdown). Cost: tool param + SCHEMA_VERSION bump + table
search haystack extension.

### P4. `variety`, `altitude_m` — **recommend: later**
Specialty-nerd fields; often absent on shop pages, low decision impact,
and each one grows the extraction prompt (cost + drift surface). Revisit
if/when a product-detail view exists.

### P5. `ground_options` (whole bean / ground) — **recommend: no (for now)**
Almost every listed coffee is sold whole-bean with optional grinding at
checkout; encoding it adds a low-signal axis to packaging that the tier
model handles badly. Reconsider only if a roaster prices grinding
differently.

## Cross-cutting

### X1. coffees.json contract versioning — **recommend: yes, trivially**
The endpoint (#60) documents fields but nothing marks breaking changes.
Add `"schema": 1` to the payload and a line to About-the-data promising
additive-only changes within a version. Cost: two lines.

### X2. Schemas for scrape_status.yaml / price_history.csv — **recommend: no**
Both are machine-written, single-writer artifacts with tests over their
writers. A JSON-schema layer would validate the writer against itself.

## Suggested sequencing

1. **P1 (stable id)** — before more history accumulates on url keys.
2. **R1 + R2** — config-only, unblocks map growth and safe roaster removal.
3. **P2 + P3 together** — one shared SCHEMA_VERSION bump / re-extraction.
4. **X1** — ride along with any site PR.

Accepted items get their own issues per repo convention (one issue per
PR); this doc is the reference to link from each.
