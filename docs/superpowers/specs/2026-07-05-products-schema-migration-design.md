# products.yaml schema tightening + coffees.json removal

## Motivation

`data/products.yaml` currently stores whatever the LLM extraction returns, mostly
unnormalized: `process` is raw free text ("Filter", "filter roast", Slovak
phrases), `origin` is often `null` even when it's spelled out in the product
name, and packaging tiers can end up with the same price across different
weights (e.g. a 200g/500g/1000g coffee all priced at €10.50 — an extraction
bug, not a real price). `_data/coffees.json` is a second generated, committed
artifact that duplicates `products.yaml`'s content in flattened form.

This change: (1) normalizes `process`/`roast_type`/`origin` into controlled,
English vocabularies at scrape time, (2) makes `weight_g`/`price`/`origin`/
`roast_type` required — a product missing any of them is flagged
`status: incomplete` rather than silently published with nulls, (3) validates
every entry against a committed JSON Schema before it's saved, and (4) retires
`_data/coffees.json` — the Astro site reads `data/products.yaml` directly.

## New data files

### `data/coffee_origins.yaml`

Canonical coffee-producing country → alias list, used for two things: translating
a stated origin (often Slovak — "Etiópia", "Kolumbia") to English, and — only
when the LLM's own `origin` field is null — scanning the product name for a
country mention (`"brazil • doce citrus"` → `Brazil`).

```yaml
Ethiopia: [ethiopia, etiópia, etiopia]
Brazil: [brazil, brazília, brazilia]
Colombia: [colombia, kolumbia]
Kenya: [kenya, keňa, kena]
Guatemala: [guatemala]
Rwanda: [rwanda]
Burundi: [burundi]
Honduras: [honduras]
Peru: [peru, peru]
Mexico: [mexico, mexiko]
Nicaragua: [nicaragua, nikaragua]
Costa Rica: [costa rica, kostarika]
Panama: [panama, panama]
El Salvador: [el salvador, salvador]
Bolivia: [bolivia, bolivia]
Ecuador: [ecuador, ekvador]
Vietnam: [vietnam]
Indonesia: [indonesia, indonézia, indonezia, sumatra]
India: [india]
Yemen: [yemen, jemen]
China: [china, čína, cina]
Tanzania: [tanzania, tanzánia, tanzania]
Uganda: [uganda]
Malawi: [malawi]
Zambia: [zambia, zambia]
Papua New Guinea: [papua new guinea, papua nova guinea]
Democratic Republic of the Congo: [congo, kongo]
Ivory Coast: [ivory coast, pobrežie slonoviny]
Dominican Republic: [dominican republic, dominikánska republika]
Jamaica: [jamaica, jamajka]
Cuba: [cuba, kuba]
Haiti: [haiti]
Philippines: [philippines, filipíny, filipiny]
Thailand: [thailand, thajsko]
Myanmar: [myanmar, mjanmarsko]
Laos: [laos]
Timor-Leste: [timor-leste, east timor]
```

Not in scope: region → country inference (e.g. "Yirgacheffe" → Ethiopia,
"Huila" → Colombia). Only literal country names/aliases are matched. Can be
added later if the name-fallback misses too often in practice.

### `data/products.schema.yaml`

JSON Schema (draft-07, YAML syntax), validated against every entry in
`process_roaster()` right before it's kept, via the `jsonschema` package
(added to `scraper/requirements.txt`).

```yaml
$schema: "http://json-schema.org/draft-07/schema#"
title: products.yaml entry
oneOf:
  - $ref: "#/definitions/ok_product"
  - $ref: "#/definitions/incomplete_product"
  - $ref: "#/definitions/not_a_product"

definitions:
  ok_packaging_tier:
    type: object
    required: [weight_g, price]
    properties:
      weight_g: {type: integer, exclusiveMinimum: 0}
      price: {type: number, exclusiveMinimum: 0}

  incomplete_packaging_tier:
    type: object
    required: [weight_g, price]
    properties:
      weight_g: {type: [integer, "null"], exclusiveMinimum: 0}
      price: {type: [number, "null"], exclusiveMinimum: 0}

  ok_product:
    type: object
    required: [name, url, origin, process, roast_type, status, last_seen, page_hash, packaging, schema_version]
    properties:
      status: {const: ok}
      name: {type: string, minLength: 1}
      url: {type: string}
      origin: {type: string, minLength: 1}
      process: {enum: [washed, natural, honey, wet-hulled, anaerobic, carbonic-maceration, other, null]}
      roast_type: {enum: [filter, espresso]}
      packaging:
        type: array
        minItems: 1
        items: {$ref: "#/definitions/ok_packaging_tier"}
      last_seen: {type: string, pattern: "^\\d{4}-\\d{2}-\\d{2}$"}
      page_hash: {type: string}
      schema_version: {type: integer}

  incomplete_product:
    type: object
    required: [name, url, status, last_seen, page_hash, missing_fields, schema_version]
    properties:
      status: {const: incomplete}
      missing_fields:
        type: array
        minItems: 1
        items: {enum: [origin, roast_type, weight_g, price]}
      name: {type: string}
      url: {type: string}
      origin: {type: [string, "null"]}
      process: {enum: [washed, natural, honey, wet-hulled, anaerobic, carbonic-maceration, other, null]}
      roast_type: {type: [string, "null"]}
      packaging:
        type: array
        items: {$ref: "#/definitions/incomplete_packaging_tier"}
      last_seen: {type: string}
      page_hash: {type: string}
      schema_version: {type: integer}

  not_a_product:
    type: object
    required: [url, status, last_seen, page_hash]
    properties:
      status: {const: not_a_product}
      url: {type: string}
      last_seen: {type: string}
      page_hash: {type: string}
```

## `scraper/scrape.py` changes

- **`normalize_process(raw) -> str | None`** — new function. Keyword-maps EN/SK
  text into the enum above (e.g. `"umytá"`/`"washed"` → `washed`,
  `"prírodná"`/`"natural"`/`"pulped natural"` → `natural`/`honey` per the
  processing method it actually describes — pulped natural leaves mucilage on
  during drying, closer to honey than full natural, so it maps to `honey`),
  `"anaerobic"` → `anaerobic`, `"carbonic maceration"` → `carbonic-maceration`,
  `"giling basah"`/`"wet-hull"` → `wet-hulled`. Text present but unmapped →
  `other`. `None` only when the site states nothing — `process` is the one
  field still allowed to be null, since many roasters simply don't publish it.
- **`normalize_roast_type`** gains a fallback chain: tries the LLM's own
  `roast_type` text first (existing behavior), then the raw `process` text,
  then the product name — reuses the same function on more inputs, since
  e.g. `process: "filter roast"` already implies `roast_type: filter` even if
  the model left `roast_type` blank.
- **`normalize_origin(raw, name) -> str | None`** — new function, backed by
  `data/coffee_origins.yaml`. Alias-matches `raw` first (translates + fixes
  casing); if `raw` is empty, alias-matches against `name`; if nothing matches
  anywhere, returns `None` (→ triggers `incomplete`).
- **`normalize_product()` rewrite**:
  - Per-tier `weight_g` no longer falls back to a name-parsed weight unless
    the product has exactly one packaging tier (a multi-tier product's weight
    must come from that tier's own text — falling back to the name for every
    tier was silently giving every tier the same weight).
  - If 2+ tiers have distinct `weight_g` but identical `price`, the whole
    product's packaging is untrustworthy → don't drop tiers piecemeal, mark
    the whole product incomplete instead.
  - Compute `missing_fields` from whichever of `origin`/`roast_type`/tier
    `weight_g`/tier `price` ended up null (or from the price-collision case
    above). Empty → `status: ok`. Non-empty → `status: incomplete`,
    `missing_fields` list attached, entry still saved (not dropped) with
    whatever was determined for the other fields.
  - `schema_version = SCHEMA_VERSION` stamped on every `ok`/`incomplete` entry.
- **`validate_entry(entry)`** — loads `data/products.schema.yaml` once at
  module scope, `jsonschema.validate(entry, SCHEMA)` on every entry right
  before `kept.append(...)`. A schema failure here means a bug in
  `normalize_product`, not bad website content — let it raise.
- **Hash-gate skip condition** (`process_roaster`) extends from
  `status in ("ok", "not_a_product")` to also include `"incomplete"` — an
  unchanged page produces the same incomplete result, no point re-calling the
  model. Additionally requires `entry.get("schema_version") == SCHEMA_VERSION`
  — this is what forces a one-time re-extraction of every pre-existing
  `ok`/`incomplete` entry after this change ships (there's no cached raw LLM
  output to replay against the new normalization rules, so the only way to
  reprocess them is a real re-fetch+re-extract, once, then hash-gating
  resumes as normal). `not_a_product` entries are untouched by the
  normalization change and don't need `schema_version` or reprocessing.
- **`flatten_to_coffees()` and the `_data/coffees.json` write are deleted**
  from `scrape.py` — see below.

## Website: `_data/coffees.json` retired

- `scrape.py` writes only `data/products.yaml` (`COFFEES_PATH`/`json` import
  removed).
- `src/components/CoffeeTable.astro` frontmatter: replace
  `import prodCoffees from '../../_data/coffees.json'` with a build-time
  read — `fs.readFileSync` + `js-yaml`'s `load()` on `data/products.yaml` and
  `roasters.yaml`, then the same flatten logic `flatten_to_coffees` used
  (explode `packaging`, join roaster display name by slug, dedupe on
  `(url, weight_g)`), restricted to `status === 'ok'` entries only
  (`incomplete` never reaches the site).
- `_data/coffees.sample.json` (the `import.meta.env.DEV` fixture) stays as a
  hand-maintained flat file, unchanged mechanism — just its *content* gets
  updated to match the new schema (English origin, canonical `process`
  values, no nulls in the now-required fields), so `npm run dev` reflects the
  real prod shape.
- `js-yaml` added as an explicit `package.json` dependency (currently only
  present transitively via Astro/Starlight).
- `CoffeeTable.astro`'s own `processType()` function — client-side guesswork
  that bucketed raw `process` text into washed/natural/honey for badge
  styling — is deleted. `process` now arrives pre-normalized, so the badge
  class becomes a one-line check: `washed`/`natural`/`honey` get their
  existing dedicated colors, everything else (`wet-hulled`, `anaerobic`,
  `carbonic-maceration`, `other`) falls back to the existing `ct-badge--other`
  style rather than adding four new color variants for a distinction the UI
  never asked to make.
- `.github/workflows/scrape.yml`: the commit step drops `_data/coffees.json`
  from `git diff`/`git add`, committing only `data/products.yaml`.
- `CLAUDE.md` and `Architecture.md` updated to describe the new schema
  (`incomplete` status, `missing_fields`, `schema_version`, controlled
  `process`/`roast_type`/`origin` vocabularies) and the retired flatten step
  / `coffees.json` file.

## Explicitly out of scope

- Region → country inference for origin (Yirgacheffe, Huila, etc.) — only
  literal country name/alias matches.
- Multi-origin blends recorded as more than one country — `origin` stays a
  single string.
- Any change to `roasters.yaml`'s roaster-identity model — it already keys
  `data/products.yaml` by `slug` at the top level; that already satisfies
  "refer to the roaster by slug," no change needed there.

## Testing

Extend `scraper/test_scrape.py` (existing suite, not a new file) with cases
for: `normalize_process` (EN/SK keyword mapping, unmapped-but-present →
`other`, absent → `None`), `normalize_origin` (alias match, name-fallback when
raw is null, no match found), the roast_type fallback chain (process text,
then name), the same-price-different-weight → `incomplete` rule, and
`validate_entry` accepting a well-formed `ok`/`incomplete`/`not_a_product`
entry and rejecting a malformed one (e.g. `roast_type` outside the enum).
