# Schema evolution proposal — `roasters.yaml` + `products.yaml`

**Status:** proposal (no code in this change) · **Issue:** #89 · **Date:** 2026-07-13

This doc reviews both schemas against the feature wave now in flight (#54–#63,
#81–#93) and recommends which fields to add, defer, or decline. Each candidate
carries its cost — a `SCHEMA_VERSION` bump forces a one-time full re-extraction
(~600 LLM calls), LLM prompt growth risks extraction accuracy, and a UI-visible
field needs EN/SK display work — and a **yes / later / no** call. Accepted items
become their own follow-up issues; nothing here ships as code.

Reference points: the `SCHEMA_VERSION` gate and `EXTRACT_PRODUCT_TOOL` live in
`scraper/scrape.py`; the validated shape is `data/products.schema.yaml`; the
roaster seed is `roasters.yaml`; the documented public contract is `coffees.json`
(#60).

---

## 1. `roasters.yaml`

Today each roaster has `name`, `slug`, `url`, `scrape_url`, optional
`scraper: playwright`, optional `roast_type_urls`, optional `referral` (#57),
and an optional `metadata: {city}`. No `SCHEMA_VERSION` gate applies — this file
is hand-maintained, so additions are free of re-extraction cost; the only cost
is the build-time reader (`src/lib/coffees.ts`) and any UI that surfaces the
field.

| Candidate | What / why | Cost | Call |
|---|---|---|---|
| **`metadata.lat` / `metadata.lng`** | Structured coordinates so the map (#59) reads them straight from `roasters.yaml` instead of a hardcoded city→lat/lng table. City stays for display. | Reader + one-time fill for ~30 roasters. No extraction cost. | **yes** |
| **`active: false` soft-delete** | Mark a roaster closed/dropped instead of deleting the entry, preserving its `products.yaml` history and `price_history.csv` rows. Scraper skips `active: false`; site hides it. | Small scraper + reader guard. | **yes** |
| **`social` / `instagram`** | Link a roaster's Instagram/socials from the map popup and (eventually) a roaster detail view. | Reader + UI; data-gathering is manual. | **later** — wait until a roaster page (beyond the map popup) exists to consume it. |
| **`founded`** | "Roasting since 20xx" flavor text. | Trivial, but no consumer today. | **later** |

**Note on `referral`:** already specced in #57 as
`referral: {code, note}`; not re-proposed here.

---

## 2. `products.yaml`

Every addition here that comes from extraction touches `EXTRACT_PRODUCT_TOOL`
and bumps `SCHEMA_VERSION` (full re-extraction). Group the accepted ones into a
**single** version bump so the re-extraction happens once, not once per field.

| Candidate | What / why | Cost | Call |
|---|---|---|---|
| **`decaf: true`** | Decaf is currently invisible — a decaf coffee is indistinguishable from caffeinated in the table, and buyers actively filter on it. Boolean, deterministic keyword fallback (`bezkofeínová`/`decaf`/`swiss water`) mirrors the `blend` flag pattern (#91). | Tool param + `SCHEMA_VERSION` bump + a filter/badge in the UI. | **yes** |
| **`tasting_notes`** | The single most-requested-shaped data: chocolate/citrus/floral notes drive both browsing and the coffee-buying skill (#90). Extractable free text, but must be normalized/capped to avoid dropdown pollution (issue #14's lesson). | Tool param + `SCHEMA_VERSION` bump + prompt growth + a normalization pass + UI column/search. | **yes**, but scoped: store as a short free-text list, display-only, **not** a filter dropdown initially. |
| **`id` (stable per-product)** | `price_history.csv` joins history on `url`; when a roaster changes a product's URL the history orphans. A stable id (hash of roaster-slug + normalized name) would survive URL changes. | Migration of the history join key; id derivation must be stable across re-extraction. | **later** — real problem, but needs its own design (how to re-key existing history) — track as a dedicated issue. |
| **`variety`** (Caturra, Gesha…) | Specialty buyers care; extractable when stated. | Tool param + bump + prompt growth; often absent on SK sites. | **later** — pair it with `tasting_notes` in the *same* bump if we do it, else skip. |
| **`altitude_m`** | Masl figure, when stated. | Tool param + bump + parse ("1800 masl" → 1800). | **no** — low consumer value for a price-comparison table; noise-to-signal poor. |
| **`ground_options`** (whole bean vs ground) | Some sites sell the same coffee whole or pre-ground. | Tool/variation-extractor change + bump. | **no** for now — orthogonal to the price/weight axis the table is built on; revisit only if a roaster's pricing actually differs by grind. |

---

## 3. Cross-cutting

- **`coffees.json` as a versioned contract (#60).** The endpoint now has
  documented fields and at least one external consumer coming (the #90 skill).
  Recommendation: add a top-level `schema` integer to `coffees.json` and a
  documented additive-only policy (new fields never break consumers; removals
  require a version bump). **yes** — cheap insurance before #90/#93 add fields.
- **Schemas for `scrape_status.yaml` and `price_history.csv`.** Both are
  machine-written and already stable. `price_history.csv` is a flat CSV with a
  fixed header; a schema buys little. `scrape_status.yaml` is small and internal.
  **no** — document their shape in `Architecture.md` instead of adding JSON
  Schemas.
- **Single combined re-extraction.** If `decaf` + `tasting_notes` (+ maybe
  `variety`) are accepted, land them in **one** `SCHEMA_VERSION` bump so the
  ~600-call re-extraction runs once. `blend` (#91) already bumped to 20; the
  next combined bump would be 21.

---

## Recommendation summary

**Do now (own issues):** `metadata.lat/lng`, `active: false`, `decaf`,
`tasting_notes` (scoped), `coffees.json` `schema` field.
**Later (needs its own design):** stable product `id`, `social`/`instagram`,
`founded`, `variety`.
**Decline:** `altitude_m`, `ground_options`, standalone schemas for
`scrape_status`/`price_history`.
