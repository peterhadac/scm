# products.yaml Schema Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Normalize `origin`/`process`/`roast_type` into controlled English vocabularies at scrape time, make `weight_g`/`price`/`origin`/`roast_type` required (flagging incomplete data instead of publishing nulls), validate every `products.yaml` entry against a committed JSON Schema, and retire `_data/coffees.json` so the Astro site reads `data/products.yaml` directly.

**Architecture:** All normalization/validation logic lives in `scraper/scrape.py`; the flatten step that used to write `_data/coffees.json` moves into `src/components/CoffeeTable.astro`'s build-time frontmatter (reads `data/products.yaml` + `roasters.yaml` directly via `js-yaml`). A `schema_version` stamp forces a one-time re-extraction of every pre-existing entry so old raw/unnormalized data gets reprocessed under the new rules.

**Tech Stack:** Python (`scrape.py`, `pytest`), `jsonschema` (new Python dep), Astro frontmatter (TypeScript), `js-yaml` (new JS dep, already present transitively).

## Global Constraints

- `process` may be `null` (many roasters don't publish it) — but if stated, must normalize to one of: `washed`, `natural`, `honey`, `wet-hulled`, `anaerobic`, `carbonic-maceration`, `other`.
- `origin`, `roast_type`, and per-tier `weight_g`/`price` may **never** be `null` on a `status: ok` entry — missing any of them makes the whole entry `status: incomplete` with a `missing_fields` list, never silently dropped.
- `roaster` identity in `products.yaml` is already keyed by `slug` at the top level (`roasters.yaml`'s `slug` field) — no change needed there.
- Region names (e.g. "Yirgacheffe", "Huila") are **not** mapped to countries — only literal country name/alias matches. Multi-origin blends are **not** split — `origin` stays a single string.
- `_data/coffees.json` is retired entirely — `scrape.py` stops writing it, the Astro build reads `data/products.yaml` directly instead.

---

### Task 1: Coffee-origin country data + `normalize_origin()`

**Files:**
- Create: `data/coffee_origins.yaml`
- Modify: `scraper/scrape.py` (add `COUNTRIES_PATH` constant, `load_country_aliases()`, `COUNTRY_ALIASES`, `normalize_origin()`)
- Test: `scraper/test_scrape.py`

**Interfaces:**
- Produces: `scrape.normalize_origin(raw: str | None, name: str | None, aliases: dict[str, str] | None = None) -> str | None` — later tasks (Task 5) call this as `normalize_origin(raw.get("origin"), name)`.
- Produces: `scrape.load_country_aliases(path=COUNTRIES_PATH) -> dict[str, str]` (lowercase alias → canonical English country name).

- [ ] **Step 1: Create the country data file**

```yaml
# data/coffee_origins.yaml
# Canonical coffee-producing country -> alias list (casings + Slovak spellings)
# used to translate a stated origin to English and, when origin is null, to
# scan the product name for a country mention. Region names (Yirgacheffe,
# Huila, etc.) are deliberately NOT included — literal country matches only.
Ethiopia: [ethiopia, etiópia, etiopia]
Brazil: [brazil, brazília, brazilia]
Colombia: [colombia, kolumbia]
Kenya: [kenya, keňa, kena]
Guatemala: [guatemala]
Rwanda: [rwanda]
Burundi: [burundi]
Honduras: [honduras]
Peru: [peru]
Mexico: [mexico, mexiko]
Nicaragua: [nicaragua, nikaragua]
Costa Rica: [costa rica, kostarika]
Panama: [panama, panamá]
El Salvador: [el salvador, salvador]
Bolivia: [bolivia]
Ecuador: [ecuador, ekvador]
Vietnam: [vietnam]
Indonesia: [indonesia, indonézia, indonezia, sumatra]
India: [india]
Yemen: [yemen, jemen]
China: [china, čína, cina]
Tanzania: [tanzania, tanzánia]
Uganda: [uganda]
Malawi: [malawi]
Zambia: [zambia]
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
Timor-Leste: [timor-leste, "east timor"]
```

- [ ] **Step 2: Write the failing tests**

Append to `scraper/test_scrape.py` (near the `normalize_roast_type` tests):

```python
# --- normalize_origin ---------------------------------------------------------


def test_normalize_origin_translates_slovak_text():
    assert scrape.normalize_origin("Etiópia", "some name") == "Ethiopia"


def test_normalize_origin_falls_back_to_name_when_raw_missing():
    assert scrape.normalize_origin(None, "brazil • doce citrus") == "Brazil"


def test_normalize_origin_trusts_raw_over_name_when_both_present():
    # LLM origin wins as-is — no cross-check against a differing name mention.
    assert scrape.normalize_origin("Colombia", "brazil • doce citrus") == "Colombia"


def test_normalize_origin_keeps_unmatched_raw_text_as_is():
    assert scrape.normalize_origin("Fantasyland", None) == "Fantasyland"


def test_normalize_origin_none_when_nothing_matches():
    assert scrape.normalize_origin(None, "House Blend") is None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd scraper && python -m pytest test_scrape.py -k normalize_origin -v`
Expected: FAIL with `AttributeError: module 'scrape' has no attribute 'normalize_origin'`

- [ ] **Step 4: Implement `normalize_origin` in `scrape.py`**

Add near the top, alongside the other path constants (after `PRODUCTS_PATH`):

```python
COUNTRIES_PATH = ROOT / "data" / "coffee_origins.yaml"
```

Add after `load_products`/`save_products` (before `find_next_page_url`):

```python
def load_country_aliases(path=COUNTRIES_PATH):
    """Flatten data/coffee_origins.yaml into a {lowercase alias: canonical name} map."""
    data = yaml.safe_load(path.read_text()) or {}
    aliases = {}
    for canonical, alias_list in data.items():
        for alias in alias_list:
            aliases[alias.lower()] = canonical
    return aliases


COUNTRY_ALIASES = load_country_aliases()


def normalize_origin(raw, name, aliases=None):
    """Translate a stated origin to its canonical English country name.

    Only falls back to scanning the product name when `raw` is empty —
    trusts an LLM-stated origin as-is (translating known aliases), it never
    cross-checks it against the name. Text that matches no known country is
    kept verbatim rather than discarded (better than losing real data for a
    producing country not yet in the list).
    """
    aliases = COUNTRY_ALIASES if aliases is None else aliases
    if raw:
        lowered = raw.lower()
        for alias, canonical in aliases.items():
            if alias in lowered:
                return canonical
        return raw.strip()
    if name:
        lowered = name.lower()
        for alias, canonical in aliases.items():
            if alias in lowered:
                return canonical
    return None
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd scraper && python -m pytest test_scrape.py -k normalize_origin -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
git add data/coffee_origins.yaml scraper/scrape.py scraper/test_scrape.py
git commit -m "feat(scraper): add coffee-origin country list and normalize_origin()"
```

---

### Task 2: `products.schema.yaml` + `validate_entry()`

**Files:**
- Create: `data/products.schema.yaml`
- Modify: `scraper/scrape.py` (add `import jsonschema`, `SCHEMA_PATH`, `SCHEMA_VERSION`, `load_schema()`, `PRODUCT_SCHEMA`, `validate_entry()`)
- Modify: `scraper/requirements.txt` (add `jsonschema`)
- Test: `scraper/test_scrape.py`

**Interfaces:**
- Produces: `scrape.SCHEMA_VERSION: int` (used by Task 5's `normalize_product` and Task 6's hash-gate condition).
- Produces: `scrape.validate_entry(entry: dict) -> None` — raises `jsonschema.ValidationError` on a malformed entry. Called by Task 6 in `process_roaster`.

- [ ] **Step 1: Create the schema file**

```yaml
# data/products.schema.yaml
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

- [ ] **Step 2: Write the failing tests**

Append to `scraper/test_scrape.py`:

```python
# --- validate_entry -------------------------------------------------------------


def test_validate_entry_accepts_ok_product():
    entry = {
        "name": "Rwanda Kigali",
        "url": "https://x.sk/rwanda/",
        "origin": "Rwanda",
        "process": "washed",
        "roast_type": "filter",
        "status": "ok",
        "last_seen": "2026-07-04",
        "page_hash": "abc123",
        "packaging": [{"weight_g": 250, "price": 12.5}],
        "schema_version": scrape.SCHEMA_VERSION,
    }
    scrape.validate_entry(entry)  # must not raise


def test_validate_entry_accepts_incomplete_product():
    entry = {
        "name": "House Blend",
        "url": "https://x.sk/house-blend/",
        "origin": None,
        "process": None,
        "roast_type": None,
        "status": "incomplete",
        "missing_fields": ["origin", "roast_type"],
        "last_seen": "2026-07-04",
        "page_hash": "abc123",
        "packaging": [{"weight_g": 250, "price": 12.5}],
        "schema_version": scrape.SCHEMA_VERSION,
    }
    scrape.validate_entry(entry)  # must not raise


def test_validate_entry_accepts_not_a_product():
    entry = {
        "url": "https://x.sk/kosik/",
        "status": "not_a_product",
        "last_seen": "2026-07-04",
        "page_hash": "abc123",
    }
    scrape.validate_entry(entry)  # must not raise


def test_validate_entry_rejects_bad_roast_type():
    entry = {
        "name": "Rwanda Kigali",
        "url": "https://x.sk/rwanda/",
        "origin": "Rwanda",
        "process": "washed",
        "roast_type": "cappuccino",  # not a valid enum value
        "status": "ok",
        "last_seen": "2026-07-04",
        "page_hash": "abc123",
        "packaging": [{"weight_g": 250, "price": 12.5}],
        "schema_version": scrape.SCHEMA_VERSION,
    }
    with pytest.raises(Exception):
        scrape.validate_entry(entry)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd scraper && python -m pytest test_scrape.py -k validate_entry -v`
Expected: FAIL with `AttributeError: module 'scrape' has no attribute 'validate_entry'` (and `SCHEMA_VERSION` undefined)

- [ ] **Step 4: Implement `validate_entry` in `scrape.py`**

Add `import jsonschema` to the import block at the top (alongside `import yaml`).

Add near `COUNTRIES_PATH`:

```python
SCHEMA_PATH = ROOT / "data" / "products.schema.yaml"

# Bump whenever normalize_product's rules change in a way that would alter
# the output for already-scraped pages — this forces process_roaster's
# hash-gate to re-extract every existing entry once, even if the page's
# content hasn't changed, since there's no cached raw LLM output to replay
# against the new rules.
SCHEMA_VERSION = 2
```

Add after `load_country_aliases`/`COUNTRY_ALIASES`:

```python
def load_schema(path=SCHEMA_PATH):
    return yaml.safe_load(path.read_text())


PRODUCT_SCHEMA = load_schema()


def validate_entry(entry):
    """Validate one products.yaml entry against data/products.schema.yaml.

    A failure here means normalize_product produced a shape the schema
    doesn't allow — a bug in this module, not bad website content — so it
    raises rather than being caught and swallowed.
    """
    jsonschema.validate(entry, PRODUCT_SCHEMA)
```

Add `jsonschema` to `scraper/requirements.txt`:

```
crawl4ai==0.9.0
beautifulsoup4
openai
pyyaml
jsonschema
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd scraper && python -m pytest test_scrape.py -k validate_entry -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add data/products.schema.yaml scraper/scrape.py scraper/test_scrape.py scraper/requirements.txt
git commit -m "feat(scraper): add products.yaml JSON Schema and validate_entry()"
```

---

### Task 3: `normalize_process()`

**Files:**
- Modify: `scraper/scrape.py`
- Test: `scraper/test_scrape.py`

**Interfaces:**
- Produces: `scrape.normalize_process(raw: str | None) -> str | None` — used by Task 5's `normalize_product`.

- [ ] **Step 1: Write the failing tests**

Append to `scraper/test_scrape.py`:

```python
# --- normalize_process ---------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Washed", "washed"),
        ("Umytá", "washed"),
        ("Natural", "natural"),
        ("Prírodná", "natural"),
        ("Honey", "honey"),
        ("Pulped natural, 900-1050 masl", "honey"),
        ("Semi-washed", "honey"),
        ("Anaerobic fermentation", "anaerobic"),
        ("Carbonic maceration", "carbonic-maceration"),
        ("Giling Basah", "wet-hulled"),
        ("Some experimental co-ferment", "other"),
        (None, None),
        ("", None),
    ],
)
def test_normalize_process(raw, expected):
    assert scrape.normalize_process(raw) == expected
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd scraper && python -m pytest test_scrape.py -k normalize_process -v`
Expected: FAIL with `AttributeError: module 'scrape' has no attribute 'normalize_process'`

- [ ] **Step 3: Implement `normalize_process` in `scrape.py`**

Add after `normalize_price` (before `normalize_roast_type`):

```python
# Checked in this order — most specific first. "pulped natural" must hit the
# honey bucket (mucilage left on during drying) before the plain "natural"
# keyword would otherwise match it; "semi-washed" must hit honey before the
# "washed" keyword matches it.
PROCESS_KEYWORDS = (
    ("anaerobic", ("anaerobic", "anaeróbn", "anaerobn")),
    ("carbonic-maceration", ("carbonic maceration", "karbonick")),
    ("wet-hulled", ("wet-hull", "wet hull", "giling basah")),
    ("honey", ("honey", "medov", "pulped natural", "semi-washed", "semi washed")),
    ("washed", ("washed", "umyt", "mokr")),
    ("natural", ("natural", "prírodn", "prirodn", "suchá", "sucha", "dry process")),
)


def normalize_process(raw):
    """Bucket free-text processing method into a controlled English vocabulary.

    Returns 'other' for a stated-but-unrecognized method, and None only when
    the site states nothing at all — process is the one field still allowed
    to be null, since many roasters simply don't publish it.
    """
    if not raw:
        return None
    lowered = raw.strip().lower()
    for canonical, keywords in PROCESS_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            return canonical
    return "other"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd scraper && python -m pytest test_scrape.py -k normalize_process -v`
Expected: PASS (13 cases)

- [ ] **Step 5: Commit**

```bash
git add scraper/scrape.py scraper/test_scrape.py
git commit -m "feat(scraper): add normalize_process() controlled vocabulary"
```

---

### Task 4: `normalize_roast_type()` fallback chain

**Files:**
- Modify: `scraper/scrape.py:379-393` (replace `normalize_roast_type`)
- Test: `scraper/test_scrape.py`

**Interfaces:**
- Produces: `scrape.normalize_roast_type(raw: str | None, process_raw: str | None = None, name: str | None = None) -> str | None` — backward compatible with the existing single-argument call sites; used by Task 5's `normalize_product`.

- [ ] **Step 1: Write the failing tests**

Append to `scraper/test_scrape.py`:

```python
# --- normalize_roast_type fallback chain --------------------------------------


def test_normalize_roast_type_falls_back_to_process_text():
    assert scrape.normalize_roast_type(None, "filter roast", "Some Blend") == "filter"


def test_normalize_roast_type_falls_back_to_name():
    assert scrape.normalize_roast_type(None, None, "Espresso Blend") == "espresso"


def test_normalize_roast_type_raw_wins_over_process_and_name():
    assert scrape.normalize_roast_type("Espresso", "filter roast", "Filter Blend") == "espresso"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd scraper && python -m pytest test_scrape.py -k "normalize_roast_type and (falls_back or raw_wins)" -v`
Expected: FAIL — `normalize_roast_type()` doesn't yet accept `process_raw`/`name` args (`TypeError: takes 1 positional argument but 3 were given`)

- [ ] **Step 3: Replace `normalize_roast_type` in `scrape.py`** (lines 379-393)

```python
def normalize_roast_type(raw, process_raw=None, name=None):
    """Bucket free-text roast info into 'filter' / 'espresso' / None.

    Tries `raw` (the model's own roast_type field) first, then falls back to
    the raw `process` text, then the product name — e.g. `process: "filter
    roast"` already implies roast_type even when the model left roast_type
    itself blank.
    """
    for text in (raw, process_raw, name):
        if not text:
            continue
        lowered = text.strip().lower()
        if "espresso" in lowered:
            return "espresso"
        if "filter" in lowered or "prekvapk" in lowered or "filtrovan" in lowered:
            return "filter"
    return None
```

- [ ] **Step 4: Run the full existing + new roast_type test set**

Run: `cd scraper && python -m pytest test_scrape.py -k normalize_roast_type -v`
Expected: PASS (all, including the 3 pre-existing single-argument tests)

- [ ] **Step 5: Commit**

```bash
git add scraper/scrape.py scraper/test_scrape.py
git commit -m "feat(scraper): normalize_roast_type falls back to process text and name"
```

---

### Task 5: `normalize_product()` rewrite — required fields, incomplete status

**Files:**
- Modify: `scraper/scrape.py:461-486` (replace `normalize_product`)
- Test: `scraper/test_scrape.py`

**Interfaces:**
- Consumes: `normalize_origin` (Task 1), `normalize_process` (Task 3), `normalize_roast_type` (Task 4), `SCHEMA_VERSION` (Task 2).
- Produces: `scrape.normalize_product(raw: dict | None, url: str, today: str) -> dict | None` — same signature as before. Returns `None` only when there's no coffee at all (unchanged). Otherwise always returns a dict with `status` = `"ok"` or `"incomplete"` (+ `missing_fields` when incomplete) and `schema_version`. Consumed by Task 6's `process_roaster`.

- [ ] **Step 1: Write the failing tests**

Append to `scraper/test_scrape.py`:

```python
# --- normalize_product: incomplete status -------------------------------------


def test_normalize_product_incomplete_when_roast_type_unknown():
    raw = {
        "name": "House Blend",
        "origin": "Brazil",
        "packaging": [{"weight": "250 g", "price": "12,00 €"}],
    }
    result = scrape.normalize_product(raw, "https://x.sk/house-blend/", "2026-07-04")
    assert result["status"] == "incomplete"
    assert result["missing_fields"] == ["roast_type"]
    assert result["schema_version"] == scrape.SCHEMA_VERSION


def test_normalize_product_incomplete_on_same_price_different_weights():
    raw = {
        "name": "brazil • doce citrus",
        "origin": "Brazil",
        "roast_type": "espresso",
        "packaging": [
            {"weight": "200 g", "price": "10,50 €"},
            {"weight": "500 g", "price": "10,50 €"},
            {"weight": "1000 g", "price": "10,50 €"},
        ],
    }
    result = scrape.normalize_product(raw, "https://x.sk/brazil/", "2026-07-04")
    assert result["status"] == "incomplete"
    assert "price" in result["missing_fields"]
    # tiers are kept (not silently dropped) so the bad data is visible for debugging
    assert len(result["packaging"]) == 3


def test_normalize_product_incomplete_when_multi_tier_weight_not_per_tier():
    # Multi-tier product where the second tier states no weight of its own —
    # must NOT fall back to a name-parsed weight for it (that would silently
    # give every tier the same weight).
    raw = {
        "name": "Kenya AA",
        "origin": "Kenya",
        "roast_type": "filter",
        "packaging": [
            {"weight": "250 g", "price": "12,00 €"},
            {"weight": None, "price": "20,00 €"},
        ],
    }
    result = scrape.normalize_product(raw, "https://x.sk/kenya/", "2026-07-04")
    assert result["status"] == "incomplete"
    assert "weight_g" in result["missing_fields"]
    assert result["packaging"][1]["weight_g"] is None


def test_normalize_product_ok_when_all_required_fields_present():
    raw = {
        "name": "Rwanda Kigali",
        "origin": "Rwanda",
        "roast_type": "Filter",
        "packaging": [{"weight": "250 g", "price": "12,50 €"}],
    }
    result = scrape.normalize_product(raw, "https://x.sk/rwanda/", "2026-07-04")
    assert result["status"] == "ok"
    assert "missing_fields" not in result
    assert result["schema_version"] == scrape.SCHEMA_VERSION
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd scraper && python -m pytest test_scrape.py -k "normalize_product and (incomplete or ok_when_all)" -v`
Expected: FAIL — current `normalize_product` always sets `status: "ok"` unconditionally and never sets `schema_version`/`missing_fields`.

- [ ] **Step 3: Replace `normalize_product` in `scrape.py`** (lines 461-486)

```python
def normalize_product(raw, url, today):
    """Turn a raw Claude extraction into a products.yaml entry, or None if unusable.

    Returns None only when there's no coffee here at all (Claude declined, or
    the name reads as non-coffee/equipment) — same as before. Anything that
    IS a coffee but is missing a required field (origin, roast_type, or a
    tier's weight/price) is still returned, just as `status: incomplete` with
    `missing_fields` listing what's missing, rather than being dropped.
    """
    if not raw or not isinstance(raw, dict) or not raw.get("name") or not is_coffee(raw["name"]):
        return None

    name = raw["name"]
    packaging = []
    for tier in raw.get("packaging") or []:
        if not isinstance(tier, dict):
            continue
        price = normalize_price(tier.get("price", ""))
        if price is None:
            continue
        weight_g = parse_weight(tier.get("weight") or "")
        packaging.append({"weight_g": weight_g, "price": price})

    # A single-tier product often states its weight in the name rather than
    # next to that one price ("Colombia Huila 200 g") — safe to fall back to
    # the name there. A multi-tier product's weight must come from its own
    # tier text; falling back to the name for every tier would silently give
    # every tier the same weight.
    if len(packaging) == 1 and packaging[0]["weight_g"] is None:
        packaging[0]["weight_g"] = parse_weight(name)

    if not packaging:
        return None

    process = normalize_process(raw.get("process"))
    roast_type = normalize_roast_type(raw.get("roast_type"), raw.get("process"), name)
    origin = normalize_origin(raw.get("origin"), name)

    weighted_tiers = [t for t in packaging if t["weight_g"] is not None]
    distinct_weights = {t["weight_g"] for t in weighted_tiers}
    distinct_prices = {t["price"] for t in weighted_tiers}
    price_collision = len(distinct_weights) >= 2 and len(distinct_prices) == 1

    missing_fields = []
    if origin is None:
        missing_fields.append("origin")
    if roast_type is None:
        missing_fields.append("roast_type")
    if any(t["weight_g"] is None for t in packaging):
        missing_fields.append("weight_g")
    if price_collision:
        missing_fields.append("price")

    entry = {
        "name": name,
        "url": url,
        "origin": origin,
        "process": process,
        "roast_type": roast_type,
        "last_seen": today,
        "page_hash": None,  # filled in by the caller once the page hash is known
        "packaging": packaging,
        "schema_version": SCHEMA_VERSION,
    }
    if missing_fields:
        entry["status"] = "incomplete"
        entry["missing_fields"] = missing_fields
    else:
        entry["status"] = "ok"
    return entry
```

- [ ] **Step 4: Run the full normalize_product test set**

Run: `cd scraper && python -m pytest test_scrape.py -k normalize_product -v`
Expected: PASS (all, including the 6 pre-existing tests — they don't assert on `status`/`origin`/`process` in ways this rewrite changes, only on `packaging`/`name`/`roast_type` shape, which are preserved)

- [ ] **Step 5: Run the entire test suite to check for regressions**

Run: `cd scraper && python -m pytest test_scrape.py -v`
Expected: All PASS except `process_roaster`-related tests, which Task 6 will fix next (they currently call the old, unmodified `process_roaster`, which doesn't yet call `validate_entry` — so no schema errors should appear yet; any failure here is a real regression to investigate before moving on).

- [ ] **Step 6: Commit**

```bash
git add scraper/scrape.py scraper/test_scrape.py
git commit -m "feat(scraper): normalize_product flags incomplete data instead of publishing nulls"
```

---

### Task 6: `process_roaster()` — schema-version hash-gate + `validate_entry` wiring

**Files:**
- Modify: `scraper/scrape.py:489-557` (replace `process_roaster`)
- Test: `scraper/test_scrape.py`

**Interfaces:**
- Consumes: `validate_entry` (Task 2), `SCHEMA_VERSION` (Task 2), `normalize_product` (Task 5).
- Produces: unchanged signature `scrape.process_roaster(crawler, client, roaster, existing_entries, today) -> (list[dict], str)`.

- [ ] **Step 1: Write the failing test**

Append to `scraper/test_scrape.py` (near the other `process_roaster` tests):

```python
@pytest.mark.asyncio
async def test_process_roaster_forces_reextraction_when_schema_version_stale():
    markdown_text = LONG_TEXT + " 12,50 €"
    import hashlib

    page_hash = hashlib.sha256(markdown_text.encode("utf-8")).hexdigest()
    crawler = FakeCrawler(
        {
            "https://x.sk/": listing_result(["https://x.sk/rwanda/"]),
            "https://x.sk/rwanda/": fake_result(markdown=fake_markdown(markdown_text)),
        }
    )
    client = MagicMock()
    client.chat.completions.create.return_value = fake_completion(
        [
            fake_tool_call(
                "extract_product",
                {
                    "name": "Rwanda",
                    "origin": "Rwanda",
                    "roast_type": "Filter",
                    "packaging": [{"price": "12,50 €", "weight": "250 g"}],
                },
            )
        ]
    )
    existing = [
        {
            "name": "Rwanda",
            "url": "https://x.sk/rwanda/",
            "status": "ok",
            "last_seen": "2026-07-01",
            "page_hash": page_hash,  # page content unchanged
            "packaging": [{"weight_g": 250, "price": 12.5}],
            # no schema_version key — a legacy entry predating this migration
        }
    ]
    entries, status = await scrape.process_roaster(crawler, client, ROASTER, existing, "2026-07-04")
    assert status == "ok"
    client.chat.completions.create.assert_called_once()  # re-extracted despite unchanged hash
    assert entries[0]["schema_version"] == scrape.SCHEMA_VERSION
```

Also update the existing `test_process_roaster_skips_claude_when_hash_unchanged` fixture so it represents an *already-migrated* entry (this proves hash-gating still works once an entry is current) — add one line to its `existing` dict:

```python
    existing = [
        {
            "name": "Rwanda",
            "url": "https://x.sk/rwanda/",
            "status": "ok",
            "last_seen": "2026-07-01",
            "page_hash": page_hash,
            "packaging": [{"weight_g": 250, "price": 12.5}],
            "schema_version": scrape.SCHEMA_VERSION,
        }
    ]
```

- [ ] **Step 2: Run tests to verify the new one fails**

Run: `cd scraper && python -m pytest test_scrape.py -k "reextraction_when_schema_version_stale or skips_claude_when_hash_unchanged" -v`
Expected: `test_process_roaster_forces_reextraction_when_schema_version_stale` FAILS (`assert_called_once()` fails — old code skips the call regardless of `schema_version`). `test_process_roaster_skips_claude_when_hash_unchanged` still PASSES (fixture edit is forward-compatible with old code too).

- [ ] **Step 3: Replace `process_roaster` in `scrape.py`** (lines 489-557)

```python
async def process_roaster(crawler, client, roaster, existing_entries, today):
    """Discover + hash-gate-extract one roaster's products.

    Returns the roaster's fresh `products.yaml` entry list (unchanged from
    `existing_entries` if discovery failed) and a status string for reporting.
    """
    existing_by_url = {e["url"]: e for e in existing_entries}

    discovered, status = await discover_product_urls(crawler, roaster)
    if status != "ok":
        return existing_entries, status
    if not discovered and existing_entries:
        # A successful-looking crawl that suddenly finds zero products is more
        # likely a broken link filter / page restructure than a real wipeout —
        # treat it like needs_js (keep old data) rather than removing everything.
        return existing_entries, "needs_js"

    kept = []
    for url in discovered:
        prior = existing_by_url.get(url)
        try:
            result = await crawler.arun(url, config=DETAIL_CONFIG)
        except Exception:
            result = None
        if not result or not result.success:
            if prior:
                kept.append(prior)
            continue

        markdown = ""
        if result.markdown:
            markdown = result.markdown.fit_markdown or result.markdown.raw_markdown or ""
        if len(markdown.strip()) < MIN_TEXT_LENGTH:
            if prior:
                kept.append(prior)
            continue

        page_hash = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
        prior_status = prior.get("status") if prior else None
        # An unchanged page skips re-extraction — unless the prior entry
        # predates the current normalization rules (schema_version stale),
        # in which case it's reprocessed once even though nothing on the
        # page itself changed. not_a_product entries carry no schema_version
        # and are unaffected by normalization changes, so they always gate.
        hash_gate_ok = (
            prior
            and prior.get("page_hash") == page_hash
            and prior_status in ("ok", "incomplete", "not_a_product")
            and (prior_status == "not_a_product" or prior.get("schema_version") == SCHEMA_VERSION)
        )
        if hash_gate_ok:
            prior["last_seen"] = today
            kept.append(prior)
            continue

        raw = extract_product(client, url, markdown)
        normalized = normalize_product(raw, url, today)
        if normalized is None:
            if prior and prior.get("status") in ("ok", "incomplete"):
                # A previously-good(-ish) product declining extraction is more
                # likely a transient hiccup than a real delisting-in-place —
                # keep the known data rather than downgrading it.
                kept.append(prior)
            else:
                # Genuinely not a product (nav/category link that slipped past
                # discovery's filter, or a first-time unparseable page). Cache
                # the hash so this URL isn't re-fetched and re-sent to Claude
                # every single run until the page actually changes.
                not_a_product_entry = {
                    "url": url,
                    "status": "not_a_product",
                    "last_seen": today,
                    "page_hash": page_hash,
                }
                validate_entry(not_a_product_entry)
                kept.append(not_a_product_entry)
            continue
        normalized["page_hash"] = page_hash
        validate_entry(normalized)
        kept.append(normalized)

    return kept, "ok"
```

- [ ] **Step 4: Run the full test suite**

Run: `cd scraper && python -m pytest test_scrape.py -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add scraper/scrape.py scraper/test_scrape.py
git commit -m "feat(scraper): validate entries and force one-time re-extraction on schema bump"
```

---

### Task 7: Stop generating `_data/coffees.json` from `scrape.py`

**Files:**
- Modify: `scraper/scrape.py` (remove `COFFEES_PATH`, `flatten_to_coffees`, and the coffees-writing code in `run()`)
- Modify: `scraper/test_scrape.py` (remove the two `flatten_to_coffees` tests)

**Interfaces:**
- Removes: `scrape.flatten_to_coffees` and `scrape.COFFEES_PATH` (no longer used anywhere — Task 8 re-implements the same logic in TypeScript inside `CoffeeTable.astro`).
- Produces: `scrape.run(only=None, roasters_path=ROASTERS_PATH, products_path=PRODUCTS_PATH)` — same as before minus the `coffees_path` parameter.

- [ ] **Step 1: Delete the `flatten_to_coffees` tests from `scraper/test_scrape.py`**

Remove these two test functions entirely (they test code being deleted in Step 3):
- `test_flatten_to_coffees_explodes_packaging_and_joins_roaster_name`
- `test_flatten_to_coffees_dedupes_same_url_and_weight`

- [ ] **Step 2: Run the full test suite to confirm it's still green before the code deletion**

Run: `cd scraper && python -m pytest test_scrape.py -v`
Expected: All PASS (the two deleted tests are gone; `flatten_to_coffees` itself still exists and unused tests removed cleanly).

- [ ] **Step 3: Remove `COFFEES_PATH`, `flatten_to_coffees`, and the coffees-write from `run()`**

Remove this line near the top (with the other path constants):

```python
COFFEES_PATH = ROOT / "_data" / "coffees.json"
```

Delete the entire `flatten_to_coffees` function.

Replace the `run()` function's signature and tail:

```python
async def run(only=None, roasters_path=ROASTERS_PATH, products_path=PRODUCTS_PATH):
    client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=os.environ["OPENROUTER_API_KEY"])
    all_roasters = load_roasters(roasters_path)
    roasters = all_roasters
    if only:
        roasters = [r for r in roasters if only.lower() in r["name"].lower()]

    products = load_products(products_path)
    today = date.today().isoformat()
    statuses = {}

    http_strategy = AsyncHTTPCrawlerStrategy(
        browser_config=HTTPCrawlerConfig(headers={"User-Agent": USER_AGENT})
    )
    need_browser = any(r.get("scraper") == "playwright" for r in roasters)

    async with AsyncExitStack() as stack:
        crawler_http = await stack.enter_async_context(
            AsyncWebCrawler(crawler_strategy=http_strategy)
        )
        crawler_browser = None
        if need_browser:
            browser_cfg = BrowserConfig(headless=True, user_agent=USER_AGENT)
            crawler_browser = await stack.enter_async_context(AsyncWebCrawler(config=browser_cfg))

        for roaster in roasters:
            slug = roaster["slug"]
            crawler = crawler_browser if roaster.get("scraper") == "playwright" else crawler_http
            entries, status = await process_roaster(
                crawler, client, roaster, products.get(slug, []), today
            )
            products[slug] = entries
            statuses[roaster["name"]] = status

    save_products(products, products_path)

    print("scrape_status:")
    for name, status in statuses.items():
        print(f"  {name}: {status}")
```

(`json` is still imported/used elsewhere in the module — `extract_product`'s `json.loads(call.function.arguments)` — so the import stays.)

- [ ] **Step 4: Run the full test suite**

Run: `cd scraper && python -m pytest test_scrape.py -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add scraper/scrape.py scraper/test_scrape.py
git commit -m "refactor(scraper): stop generating _data/coffees.json, products.yaml is the only output"
```

---

### Task 8: Astro build reads `data/products.yaml` directly

**Files:**
- Modify: `package.json` (add `js-yaml` dependency, `@types/js-yaml` devDependency)
- Modify: `src/components/CoffeeTable.astro:1-44` (frontmatter) and `:166-203` (row rendering)

**Interfaces:**
- Consumes: `data/products.yaml` (mapping of roaster `slug` → array of product entries, `status: "ok"` only), `roasters.yaml` (`{ roasters: [{name, slug, ...}] }`).
- Produces: same `coffees` array shape the component already used (`{name, roaster, origin, process, roast_type, price, weight_g, url, last_seen}[]`), so everything below line 44 (stats, table rendering, filter script) needs no changes beyond the badge-class simplification in Step 3.

- [ ] **Step 1: Add `js-yaml` as an explicit dependency**

Both packages are already present transitively (confirmed in `package-lock.json` at the versions below), so this just formalizes a direct dependency — no new versions to resolve.

Edit `package.json`:

```json
{
  "scripts": {
    "dev": "astro dev",
    "build": "astro build",
    "preview": "astro preview"
  },
  "dependencies": {
    "@astrojs/starlight": "^0.41.1",
    "astro": "^7.0.4",
    "js-yaml": "^4.1.1",
    "starlight-theme-md3": "^0.2.0"
  },
  "devDependencies": {
    "@types/js-yaml": "^4.0.9",
    "playwright": "^1.61.1"
  }
}
```

Run: `npm install`
Expected: lockfile updates in place (no new packages to download — both already resolved).

- [ ] **Step 2: Replace the data-loading frontmatter** (`src/components/CoffeeTable.astro:1-26`)

Replace:

```astro
---
import sampleCoffees from '../../_data/coffees.sample.json';
import prodCoffees from '../../_data/coffees.json';

interface Props {
  // When set, page is locked to one roast profile: the Roast dropdown is
  // hidden and only matching coffees are shown (used by the filter/espresso
  // submenu pages). Omit to show every coffee with a Roast filter.
  roastType?: 'filter' | 'espresso';
}

const { roastType } = Astro.props;

const allCoffees = import.meta.env.DEV ? sampleCoffees : prodCoffees;
const coffees = roastType
  ? allCoffees.filter((c) => c.roast_type === roastType)
  : allCoffees;

function processType(p: string | null): 'washed' | 'natural' | 'honey' | null {
  if (!p) return null;
  const l = p.toLowerCase();
  if (l.includes('umyt') || l.includes('washed')) return 'washed';
  if (l.includes('prírodn') || l.includes('natural')) return 'natural';
  if (l.includes('med') || l.includes('honey')) return 'honey';
  return null;
}
```

With:

```astro
---
import fs from 'node:fs';
import path from 'node:path';
import yaml from 'js-yaml';
import sampleCoffees from '../../_data/coffees.sample.json';

interface Props {
  // When set, page is locked to one roast profile: the Roast dropdown is
  // hidden and only matching coffees are shown (used by the filter/espresso
  // submenu pages). Omit to show every coffee with a Roast filter.
  roastType?: 'filter' | 'espresso';
}

interface ProductTier {
  weight_g: number;
  price: number;
}

interface ProductEntry {
  name: string;
  url: string;
  origin: string;
  process: string | null;
  roast_type: 'filter' | 'espresso';
  status: string;
  last_seen: string;
  packaging: ProductTier[];
}

interface Roaster {
  name: string;
  slug: string;
}

function loadYaml<T>(relativePath: string): T {
  const file = path.join(process.cwd(), relativePath);
  return yaml.load(fs.readFileSync(file, 'utf8')) as T;
}

// Explodes each ok-status product's packaging tiers into flat rows, joined
// with the roaster's display name from roasters.yaml by slug — mirrors
// scraper/scrape.py's old flatten_to_coffees(), now run at site-build time
// instead of by the Python scraper.
function flattenProducts() {
  const roasterList = loadYaml<{ roasters: Roaster[] }>('roasters.yaml').roasters;
  const roasterBySlug = new Map(roasterList.map((r) => [r.slug, r]));
  const products = loadYaml<Record<string, ProductEntry[]>>('data/products.yaml');

  const seen = new Set<string>();
  const rows = [];
  for (const [slug, entries] of Object.entries(products)) {
    const roasterName = roasterBySlug.get(slug)?.name ?? slug;
    for (const product of entries) {
      if (product.status !== 'ok') continue;
      for (const tier of product.packaging ?? []) {
        const key = `${product.url}|${tier.weight_g}`;
        if (seen.has(key)) continue;
        seen.add(key);
        rows.push({
          name: product.name,
          roaster: roasterName,
          origin: product.origin,
          process: product.process,
          roast_type: product.roast_type,
          price: tier.price,
          weight_g: tier.weight_g,
          url: product.url,
          last_seen: product.last_seen,
        });
      }
    }
  }
  return rows;
}

const { roastType } = Astro.props;

const allCoffees = import.meta.env.DEV ? sampleCoffees : flattenProducts();
const coffees = roastType
  ? allCoffees.filter((c) => c.roast_type === roastType)
  : allCoffees;

const PROCESS_BADGE_CLASSES = new Set(['washed', 'natural', 'honey']);
```

- [ ] **Step 3: Simplify the badge rendering** (`src/components/CoffeeTable.astro`, inside the `coffees.map` block)

Replace:

```astro
        {coffees.map((c, i) => {
          const pType = processType(c.process ?? null);
          const per100gNum = c.weight_g ? (c.price / c.weight_g) * 100 : null;
```

With:

```astro
        {coffees.map((c, i) => {
          const per100gNum = c.weight_g ? (c.price / c.weight_g) * 100 : null;
```

Replace:

```astro
              <td>
                {c.process && pType
                  ? <span class={`ct-badge ct-badge--${pType}`}>{c.process}</span>
                  : c.process
                  ? <span class="ct-badge ct-badge--other">{c.process}</span>
                  : <span class="ct-muted">—</span>
                }
              </td>
```

With:

```astro
              <td>
                {c.process
                  ? <span class={`ct-badge ct-badge--${PROCESS_BADGE_CLASSES.has(c.process) ? c.process : 'other'}`}>{c.process}</span>
                  : <span class="ct-muted">—</span>
                }
              </td>
```

- [ ] **Step 4: Build and manually verify**

Run: `npm run build`
Expected: build succeeds, no TypeScript errors.

Run: `npm run dev`, open the site, confirm the table still renders with the (unchanged) `_data/coffees.sample.json` fixture in dev mode, filters and sorting still work, process badges still show correct colors for washed/natural/honey and the neutral style for anything else.

- [ ] **Step 5: Commit**

```bash
git add package.json package-lock.json src/components/CoffeeTable.astro
git commit -m "feat(site): read data/products.yaml directly at build time instead of _data/coffees.json"
```

---

### Task 9: Update `_data/coffees.sample.json` to the new schema

**Files:**
- Modify: `_data/coffees.sample.json`

**Interfaces:**
- None — this is a static dev-only fixture consumed by `CoffeeTable.astro`'s `import.meta.env.DEV` branch (unchanged mechanism from Task 8).

- [ ] **Step 1: Replace the file content**

```json
[
  {
    "name": "Ethiopia Yirgacheffe",
    "roaster": "Kavoholik",
    "origin": "Ethiopia",
    "process": "washed",
    "roast_type": "filter",
    "price": 12.90,
    "weight_g": 250,
    "url": "https://kavoholik.sk/coffee/etiopia-yirgacheffe",
    "last_seen": "2026-06-30"
  },
  {
    "name": "Colombia Huila",
    "roaster": "Ready After",
    "origin": "Colombia",
    "process": null,
    "roast_type": "espresso",
    "price": 14.50,
    "weight_g": 250,
    "url": "https://www.readyafter.sk/produkty/kolumbia-huila",
    "last_seen": "2026-06-30"
  },
  {
    "name": "Brazil Cerrado",
    "roaster": "Kaffa Roastery",
    "origin": "Brazil",
    "process": "natural",
    "roast_type": "espresso",
    "price": 11.00,
    "weight_g": 250,
    "url": "https://kaffaroastery.sk/coffees/brazilia-cerrado",
    "last_seen": "2026-06-30"
  },
  {
    "name": "Kenya AA",
    "roaster": "Suca Roastery",
    "origin": "Kenya",
    "process": "washed",
    "roast_type": "filter",
    "price": 16.20,
    "weight_g": 250,
    "url": "https://www.sucaroastery.sk/coffee/kenya-aa",
    "last_seen": "2026-06-30"
  },
  {
    "name": "Guatemala Huehuetenango",
    "roaster": "Coffeein",
    "origin": "Guatemala",
    "process": "washed",
    "roast_type": "filter",
    "price": 15.90,
    "weight_g": 250,
    "url": "https://www.coffeein.sk/coffee/guatemala-huehuetenango",
    "last_seen": "2026-06-30"
  },
  {
    "name": "Honduras Marcala",
    "roaster": "Kavoholik",
    "origin": "Honduras",
    "process": null,
    "roast_type": "filter",
    "price": 13.40,
    "weight_g": 250,
    "url": "https://kavoholik.sk/coffee/honduras-marcala",
    "last_seen": "2026-06-30"
  },
  {
    "name": "Ethiopia Natural",
    "roaster": "Ready After",
    "origin": "Ethiopia",
    "process": "natural",
    "roast_type": "espresso",
    "price": 15.00,
    "weight_g": 250,
    "url": "https://www.readyafter.sk/produkty/ethiopia-natural",
    "last_seen": "2026-06-30"
  },
  {
    "name": "Rwanda Washed",
    "roaster": "Kaffa Roastery",
    "origin": "Rwanda",
    "process": "washed",
    "roast_type": "filter",
    "price": 17.50,
    "weight_g": 250,
    "url": "https://kaffaroastery.sk/coffees/rwanda-washed",
    "last_seen": "2026-06-30"
  },
  {
    "name": "Peru Organic",
    "roaster": "Suca Roastery",
    "origin": "Peru",
    "process": "washed",
    "roast_type": "filter",
    "price": 13.90,
    "weight_g": 1000,
    "url": "https://www.sucaroastery.sk/coffee/peru-organic",
    "last_seen": "2026-06-30"
  }
]
```

- [ ] **Step 2: Verify dev mode renders correctly**

Run: `npm run dev`, visit the site, confirm all 9 sample coffees show with English origins, correctly colored process badges, and no `—` placeholders where data used to be null (only `Colombia Huila` and `Honduras Marcala` should show `—` for process, which is expected — process is allowed to be null).

- [ ] **Step 3: Commit**

```bash
git add _data/coffees.sample.json
git commit -m "chore(site): update dev sample data to the new products schema (English origin/process)"
```

---

### Task 10: Delete `_data/coffees.json`, update the scrape workflow

**Files:**
- Delete: `_data/coffees.json`
- Modify: `.github/workflows/scrape.yml`

**Interfaces:** None (CI config + dead file removal).

- [ ] **Step 1: Delete the generated file**

```bash
git rm _data/coffees.json
```

- [ ] **Step 2: Update the commit step in `.github/workflows/scrape.yml`**

Replace the last step:

```yaml
      - run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git diff --quiet -- _data/coffees.json data/products.yaml || (git add _data/coffees.json data/products.yaml && git commit -m "data: $(date -u +%F)" && git push)
```

With:

```yaml
      - run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git diff --quiet -- data/products.yaml || (git add data/products.yaml && git commit -m "data: $(date -u +%F)" && git push)
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/scrape.yml
git commit -m "chore(ci): stop committing _data/coffees.json, products.yaml is the sole scraped artifact"
```

---

### Task 11: Update `CLAUDE.md` and `Architecture.md`

**Files:**
- Modify: `CLAUDE.md`
- Modify: `Architecture.md`

**Interfaces:** None (documentation only).

- [ ] **Step 1: Update `CLAUDE.md`'s Architecture tree**

Replace:

```
_data/
  coffees.json         ← flattened scraper output; imported by the Astro page (plain import, no magic)
```

With:

```
_data/
  coffees.sample.json  ← hand-maintained dev fixture (import.meta.env.DEV only)
```

- [ ] **Step 2: Update `CLAUDE.md`'s Data Schema section**

Replace the whole "## Data Schema" section with:

```markdown
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
  state one (e.g. `"brazil • doce citrus"` → `Brazil`).

`price` is **EUR** as a JSON number with a `.` decimal. `last_seen` is the
date of the last successful scrape that included this item; it stops
advancing while the roaster is `failed`/`needs_js`.

The Astro build reads `data/products.yaml` + `roasters.yaml` directly at
build time (see `src/components/CoffeeTable.astro`) and flattens each
`ok`-status product's packaging tiers into one row per weight — there is no
separate generated JSON file for the site to import.
```

- [ ] **Step 3: Update `CLAUDE.md`'s Astro section**

Replace:

```markdown
- **Data source**: plain `import coffees from '../../_data/coffees.json'` inside `CoffeeTable.astro`. No `site.data` magic — JSON is bundled at build time, so a new scrape requires a rebuild (handled by `pages.yml`).
```

With:

```markdown
- **Data source**: `CoffeeTable.astro`'s frontmatter reads `data/products.yaml` + `roasters.yaml` directly at build time (via `js-yaml`) and flattens them into table rows — no separate generated JSON file. `import.meta.env.DEV` still uses the hand-maintained `_data/coffees.sample.json` fixture for local dev. A new scrape requires a rebuild (handled by `pages.yml`).
```

- [ ] **Step 4: Update the `scrape.yml` commit-guard line**

Replace:

```markdown
- Guard the commit so a no-change run doesn't fail the job:
  `git diff --quiet -- _data/coffees.json data/products.yaml || (git add _data/coffees.json data/products.yaml && git commit -m "data: $(date -u +%F)" && git push)`
```

With:

```markdown
- Guard the commit so a no-change run doesn't fail the job:
  `git diff --quiet -- data/products.yaml || (git add data/products.yaml && git commit -m "data: $(date -u +%F)" && git push)`
```

- [ ] **Step 5: Update `Architecture.md`'s Data Flow diagram**

Replace:

```
data/products.yaml (per-product fields, page_hash, status, packaging — the
      │              ONLY generated intermediate file; also the record of
      │              "what did we know about last time" for removal detection)
      ▼
flatten_to_coffees() — packaging exploded to flat rows, joined with roaster
      │                name from roasters.yaml by slug
      ▼
_data/coffees.json (the existing flat site schema, unchanged)
      │
      ▼
src/components/CoffeeTable.astro (site UI — reads coffees.json, no changes needed)
```

With:

```
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

- [ ] **Step 6: Update `Architecture.md`'s Files & Ownership table**

Replace:

```markdown
| File | Owner | Committed |
|---|---|---|
| `roasters.yaml` | Human-edited | yes |
| `data/products.yaml` | Generated, sole intermediate artifact | yes — must be committed so the *next* run can diff/hash-gate against it |
| `_data/coffees.json` | Generated by the flatten step | yes — this is what the Astro build imports |
```

With:

```markdown
| File | Owner | Committed |
|---|---|---|
| `roasters.yaml` | Human-edited | yes |
| `data/coffee_origins.yaml` | Human-edited (country list for origin normalization) | yes |
| `data/products.schema.yaml` | Human-edited (JSON Schema, validated on every scrape) | yes |
| `data/products.yaml` | Generated, sole scraped artifact | yes — must be committed so the *next* run can diff/hash-gate against it, and so the Astro build can read it directly |
```

- [ ] **Step 7: Update `Architecture.md`'s "Flatten / Build Step" section**

Replace:

```markdown
## Flatten / Build Step (`flatten_to_coffees`)

Explodes each product's `packaging` array into one flat row per `(product url, weight_g)`, deduped on that pair. Joins in the roaster's display `name` from `roasters.yaml` by `slug`. `not_a_product` entries (no `packaging`) are skipped. Output is written to `_data/coffees.json` in the exact schema documented in `CLAUDE.md` — **`CoffeeTable.astro` requires zero changes**.
```

With:

```markdown
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

## Flatten / Build Step

Exploding each `ok`-status product's `packaging` array into one flat row per
`(product url, weight_g)`, deduped on that pair, and joining in the
roaster's display `name` from `roasters.yaml` by `slug`, now happens in
`src/components/CoffeeTable.astro`'s frontmatter at site-build time — there
is no Python-side flatten step or generated `_data/coffees.json` file
anymore. `incomplete`/`not_a_product` entries never reach the site.
```

- [ ] **Step 8: Update `Architecture.md`'s CI / Publishing section**

Replace:

```markdown
`.github/workflows/scrape.yml` installs deps via `crawl4ai-setup` (replaces the old `playwright install --with-deps chromium` — verified to be a strict superset) and commits both `data/products.yaml` and `_data/coffees.json` — committing `products.yaml` is what makes cross-run removal-detection and hash-gating possible. `pages.yml` needs no changes; it builds from `_data/coffees.json` regardless of how that file was produced.
```

With:

```markdown
`.github/workflows/scrape.yml` installs deps via `crawl4ai-setup` (replaces the old `playwright install --with-deps chromium` — verified to be a strict superset) and commits `data/products.yaml` — this is what makes cross-run removal-detection and hash-gating possible, and it's also what the Astro build reads directly. `pages.yml` needs no changes; its `npm run build` step reads `data/products.yaml` at build time regardless of how that file was produced.
```

- [ ] **Step 9: Commit**

```bash
git add CLAUDE.md Architecture.md
git commit -m "docs: update CLAUDE.md and Architecture.md for the products.yaml schema migration"
```

---

## Post-plan note: the next scrape run will be more expensive than usual

Because `SCHEMA_VERSION` bumped, the next `scrape.yml` run (or manual `python scraper/scrape.py` run) will re-extract **every existing product across all 24 roasters** — one real LLM call per product, not just per changed page — since there's no cached raw extraction to replay against the new normalization rules. This is a one-time cost; hash-gating resumes normally on the run after that. No action needed, just don't be surprised by a slower-than-usual / more-LLM-calls-than-usual first run after this ships.
