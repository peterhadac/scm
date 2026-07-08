# WooCommerce Variation Pricing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract every price/weight tier of a WooCommerce variable product (e.g. `triproasters.sk/mexico-santa-cruz/`, which sells 250g and 1000g at different prices) deterministically from the page's raw HTML, instead of relying on the LLM to read a price off markdown that only ever shows the currently-selected variant.

**Architecture:** WooCommerce embeds every variation's price in a `data-product_variations` JSON attribute on the product page's `<form>` at initial page load (swapped into the visible price via JS on selection — no extra network request, no browser rendering required). `discover_product_urls` and `process_roaster` already fetch this raw HTML via crawl4ai's plain HTTP mode; a new `extract_woocommerce_variations()` parses that attribute with BeautifulSoup (already a dependency) into `{weight_g, price}` tiers. `normalize_product()` gains an optional `variation_tiers` parameter: when present, it replaces the LLM-guessed `packaging` array outright. `process_roaster`'s content hash is extended to include the raw variations JSON string, so a price-only change that doesn't touch visible markdown text still busts the hash-gate cache.

**Tech Stack:** Python 3, BeautifulSoup (`bs4`, already imported in `scraper/scrape.py`), `json` (stdlib), `pytest` + `pytest-asyncio` (existing test setup in `scraper/test_scrape.py`).

## Global Constraints

- No new dependencies — `bs4` and `json` are already used/imported in `scraper/scrape.py`.
- Follow the existing test file's fixture helpers (`fake_result`, `fake_markdown`, `FakeCrawler`, `fake_tool_call`, `fake_completion`, `listing_result`, `ROASTER`) — do not introduce parallel helpers.
- Every new/changed function keeps a docstring in the same style as neighboring functions in `scrape.py` (one-paragraph "what it returns and why", not a line-by-line description).
- Non-WooCommerce pages (no `data-product_variations` attribute) must be completely unaffected — `extract_woocommerce_variations` returns `("", [])` and every existing code path/test continues to behave exactly as today.

---

## File Structure

- **Modify: `scraper/scrape.py`**
  - New function `extract_woocommerce_variations(html)` — parses the WooCommerce variation JSON.
  - Modify `normalize_product(raw, url, today)` → `normalize_product(raw, url, today, variation_tiers=None)`.
  - Modify `process_roaster()` — call the new function, fold its raw JSON into the page hash, pass its tiers into `normalize_product`.
- **Modify: `scraper/test_scrape.py`** — unit tests for the new function, `normalize_product`'s new parameter, and an integration test through `process_roaster` (including the hash-gate regression case).
- **Modify: `Architecture.md`** — document the new price source and the hash change in the "Detail Extraction" section.

No new files.

---

### Task 1: `extract_woocommerce_variations()`

**Files:**
- Modify: `scraper/scrape.py` (add function after `visible_html_text_length`, i.e. after line 353, before `async def discover_product_urls`)
- Test: `scraper/test_scrape.py` (add new section after the `parse_weight` tests, i.e. after line ~523, before `def is_coffee`)

**Interfaces:**
- Produces: `extract_woocommerce_variations(html: str) -> tuple[str, list[dict]]`. First element is the raw `data-product_variations` attribute string verbatim (`""` if absent) — used later for hashing. Second element is a list of `{"weight_g": int, "price": float}` dicts, deduped by `weight_g` (first-seen wins), empty list if the page isn't a WooCommerce variable product or has no usable variations.

- [ ] **Step 1: Write the failing tests**

```python
# --- extract_woocommerce_variations -------------------------------------------


WOO_VARIATIONS_HTML = (
    '<form class="variations_form cart" data-product_variations="'
    "[{&quot;attributes&quot;:{&quot;attribute_pa_hmotnost&quot;:&quot;1000-g&quot;},"
    "&quot;display_price&quot;:34,&quot;display_regular_price&quot;:34},"
    "{&quot;attributes&quot;:{&quot;attribute_pa_hmotnost&quot;:&quot;250-g&quot;},"
    "&quot;display_price&quot;:11,&quot;display_regular_price&quot;:11}]"
    '"></form>'
)


def test_extract_woocommerce_variations_parses_weight_price_pairs():
    raw_json, tiers = scrape.extract_woocommerce_variations(WOO_VARIATIONS_HTML)
    assert raw_json  # non-empty, used for hashing
    assert tiers == [
        {"weight_g": 1000, "price": 34.0},
        {"weight_g": 250, "price": 11.0},
    ]


def test_extract_woocommerce_variations_absent_returns_empty():
    raw_json, tiers = scrape.extract_woocommerce_variations("<html><body>no form here</body></html>")
    assert raw_json == ""
    assert tiers == []


def test_extract_woocommerce_variations_malformed_json_returns_raw_and_empty_tiers():
    html = '<form data-product_variations="not valid json"></form>'
    raw_json, tiers = scrape.extract_woocommerce_variations(html)
    assert raw_json == "not valid json"
    assert tiers == []


def test_extract_woocommerce_variations_dedupes_same_weight_first_wins():
    # Same weight, different non-weight variant axis (e.g. roast type) —
    # keep only the first-seen price for that weight rather than a duplicate tier.
    html = (
        '<form data-product_variations="'
        "[{&quot;attributes&quot;:{&quot;attribute_pa_hmotnost&quot;:&quot;250-g&quot;},"
        "&quot;display_price&quot;:11,&quot;display_regular_price&quot;:11},"
        "{&quot;attributes&quot;:{&quot;attribute_pa_hmotnost&quot;:&quot;250-g&quot;},"
        "&quot;display_price&quot;:13,&quot;display_regular_price&quot;:13}]"
        '"></form>'
    )
    _, tiers = scrape.extract_woocommerce_variations(html)
    assert tiers == [{"weight_g": 250, "price": 11.0}]


def test_extract_woocommerce_variations_skips_unparseable_weight():
    # No "hmotnost" (weight) attribute key on this variation at all.
    html = (
        '<form data-product_variations="'
        "[{&quot;attributes&quot;:{&quot;attribute_pa_sposob-prazenia&quot;:&quot;espresso&quot;},"
        "&quot;display_price&quot;:11}]"
        '"></form>'
    )
    _, tiers = scrape.extract_woocommerce_variations(html)
    assert tiers == []


def test_extract_woocommerce_variations_skips_zero_and_missing_price():
    html = (
        '<form data-product_variations="'
        "[{&quot;attributes&quot;:{&quot;attribute_pa_hmotnost&quot;:&quot;250-g&quot;},"
        "&quot;display_price&quot;:0},"
        "{&quot;attributes&quot;:{&quot;attribute_pa_hmotnost&quot;:&quot;1000-g&quot;}}]"
        '"></form>'
    )
    _, tiers = scrape.extract_woocommerce_variations(html)
    assert tiers == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd scraper && python3 -m pytest test_scrape.py -k woocommerce_variations -v`
Expected: FAIL with `AttributeError: module 'scrape' has no attribute 'extract_woocommerce_variations'`

- [ ] **Step 3: Implement the function**

Add to `scraper/scrape.py`, directly after `visible_html_text_length` (after line 353):

```python
def extract_woocommerce_variations(html):
    """Parse a WooCommerce variable-product page's `data-product_variations` JSON.

    WooCommerce embeds every variation's price in the initial page load (an
    HTML attribute swapped into the visible price by on-page JS when a
    shopper picks a weight) — no browser rendering needed, crawl4ai's plain
    HTTP fetch already has it. Markdown conversion drops non-visible
    attributes though, so this reads the raw HTML directly instead of
    relying on the LLM to read a rendered price, which only ever shows the
    currently-selected variant.

    Returns (raw_json, tiers): `raw_json` is the attribute's exact string
    value (used by the caller to fold into the page hash so a price-only
    change still busts the cache), "" if this isn't a WooCommerce variable
    product page. `tiers` is a list of {"weight_g": int, "price": float},
    deduped by weight_g (first-seen wins — ponytail: a second variant axis,
    e.g. roast type, sharing a weight would otherwise produce duplicate
    tiers; revisit if a roaster's variations legitimately need >1 axis).
    """
    soup = BeautifulSoup(html or "", "html.parser")
    form = soup.find(attrs={"data-product_variations": True})
    if not form:
        return "", []
    raw_json = form["data-product_variations"]
    try:
        variations = json.loads(raw_json)
    except (ValueError, TypeError):
        return raw_json, []

    tiers = []
    seen_weights = set()
    for variation in variations:
        if not isinstance(variation, dict):
            continue
        attributes = variation.get("attributes") or {}
        weight_slug = next(
            (v for k, v in attributes.items() if "hmotnost" in k.lower()), None
        )
        weight_g = parse_weight((weight_slug or "").replace("-", " "))
        price = variation.get("display_price")
        if weight_g is None or not isinstance(price, (int, float)) or price <= 0:
            continue
        if weight_g in seen_weights:
            continue
        seen_weights.add(weight_g)
        tiers.append({"weight_g": weight_g, "price": float(price)})
    return raw_json, tiers
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd scraper && python3 -m pytest test_scrape.py -k woocommerce_variations -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add scraper/scrape.py scraper/test_scrape.py
git commit -m "feat: parse WooCommerce variation pricing from raw HTML"
```

---

### Task 2: `normalize_product()` accepts `variation_tiers`

**Files:**
- Modify: `scraper/scrape.py:566-641` (`normalize_product`)
- Test: `scraper/test_scrape.py` (add after `test_normalize_product_multi_weight_packaging`, i.e. after line 313)

**Interfaces:**
- Consumes: nothing new from Task 1 directly (Task 1's output shape — list of `{"weight_g": int, "price": float}` — is exactly what this task's new parameter expects, but this task can be implemented/tested independently by passing that shape by hand).
- Produces: `normalize_product(raw, url, today, variation_tiers=None)` — when `variation_tiers` is a non-empty list, `packaging` is taken verbatim from it (bypassing the `raw.get("packaging")` LLM-parsing loop and the single-tier name-fallback); `raw` is still required for `name`/`is_coffee`/`origin`/`process`/`roast_type`. When `variation_tiers` is `None` or `[]`, behavior is byte-for-byte identical to today.

- [ ] **Step 1: Write the failing test**

```python
def test_normalize_product_uses_variation_tiers_when_provided():
    # LLM-guessed packaging is deliberately wrong here — variation_tiers,
    # sourced from WooCommerce's own JSON, must win.
    raw = {
        "name": "Mexico Santa Cruz",
        "origin": "Mexico",
        "process": "Washed",
        "roast_type": "Espresso",
        "packaging": [{"weight": "1 g", "price": "99,00 €"}],
    }
    tiers = [{"weight_g": 1000, "price": 34.0}, {"weight_g": 250, "price": 11.0}]
    result = scrape.normalize_product(raw, "https://x.sk/mexico/", "2026-07-08", variation_tiers=tiers)
    assert result["status"] == "ok"
    assert result["packaging"] == tiers


def test_normalize_product_variation_tiers_still_requires_a_name():
    # variation_tiers alone doesn't make a page a product — Claude declining
    # (raw=None) or a non-coffee name must still return None.
    tiers = [{"weight_g": 250, "price": 11.0}]
    assert scrape.normalize_product(None, "https://x.sk/mexico/", "2026-07-08", variation_tiers=tiers) is None
    raw = {"name": "Darčeková poukážka", "packaging": []}
    assert scrape.normalize_product(raw, "https://x.sk/gift/", "2026-07-08", variation_tiers=tiers) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd scraper && python3 -m pytest test_scrape.py -k variation_tiers -v`
Expected: FAIL — `TypeError: normalize_product() got an unexpected keyword argument 'variation_tiers'`

- [ ] **Step 3: Implement**

In `scraper/scrape.py`, change the `normalize_product` signature and the packaging-construction block:

```python
def normalize_product(raw, url, today, variation_tiers=None):
    """Turn a raw Claude extraction into a products.yaml entry, or None if unusable.

    Returns None only when there's no coffee here at all (Claude declined, or
    the name reads as non-coffee/equipment) — same as before. Anything that
    IS a coffee but is missing a required field (origin, roast_type, or a
    tier's weight/price) is still returned, just as `status: incomplete` with
    `missing_fields` listing what's missing, rather than being dropped.

    `variation_tiers`, when non-empty, comes from
    `extract_woocommerce_variations()` and is trusted over the LLM's own
    packaging guess — deterministic data straight from the page beats an LLM
    reading a price off markdown that only shows the selected variant.
    """
    if not raw or not isinstance(raw, dict) or not raw.get("name") or not is_coffee(raw["name"]):
        return None

    name = raw["name"]
    if variation_tiers:
        packaging = list(variation_tiers)
    else:
        packaging = []
        for tier in raw.get("packaging") or []:
            if not isinstance(tier, dict):
                continue
            price = normalize_price(tier.get("price", ""))
            if price is None or price <= 0:
                continue
            weight_g = parse_weight(tier.get("weight") or "")
            if weight_g is not None and weight_g <= 0:
                weight_g = None
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
```

(Everything below `if not packaging: return None` — `process`/`roast_type`/`origin`/`missing_fields`/`entry` construction — is unchanged.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd scraper && python3 -m pytest test_scrape.py -v`
Expected: all tests pass (full file — this confirms the untouched-when-`variation_tiers=None`-path claim, not just the two new tests)

- [ ] **Step 5: Commit**

```bash
git add scraper/scrape.py scraper/test_scrape.py
git commit -m "feat: let normalize_product trust deterministic variation tiers over LLM guesses"
```

---

### Task 3: Wire into `process_roaster` + fix hash-gate blind spot

**Files:**
- Modify: `scraper/scrape.py:672-699` (inside `process_roaster`)
- Test: `scraper/test_scrape.py` (add after `test_process_roaster_extracts_new_product`, i.e. after line 646)

**Interfaces:**
- Consumes: `extract_woocommerce_variations(html) -> (raw_json, tiers)` (Task 1), `normalize_product(raw, url, today, variation_tiers=None)` (Task 2).
- Produces: no new public interface — this is the integration point. After this task, `process_roaster`'s `page_hash` is `sha256(markdown + variations_raw)` instead of `sha256(markdown)`.

This task exists because of a real correctness gap: the page hash currently only covers `markdown`, but a WooCommerce price swap (e.g. the site raises the 1000g price from €34 to €36) can leave the *visible* markdown text — which always shows just the currently-selected/default variant — completely unchanged. Without folding the variations JSON into the hash, that price change would be silently hash-gated away forever.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.asyncio
async def test_process_roaster_uses_variation_tiers_over_llm_packaging():
    html = (
        '<form data-product_variations="'
        "[{&quot;attributes&quot;:{&quot;attribute_pa_hmotnost&quot;:&quot;1000-g&quot;},"
        "&quot;display_price&quot;:34},"
        "{&quot;attributes&quot;:{&quot;attribute_pa_hmotnost&quot;:&quot;250-g&quot;},"
        "&quot;display_price&quot;:11}]"
        '"></form>'
    )
    crawler = FakeCrawler(
        {
            "https://x.sk/": listing_result(["https://x.sk/mexico/"]),
            "https://x.sk/mexico/": fake_result(
                html=html, markdown=fake_markdown(LONG_TEXT + " 11,00 €")
            ),
        }
    )
    client = MagicMock()
    client.chat.completions.create.return_value = fake_completion(
        [
            fake_tool_call(
                "extract_product",
                {
                    "name": "Mexico Santa Cruz",
                    "origin": "Mexico",
                    "roast_type": "Espresso",
                    # Deliberately wrong/incomplete — the page's default
                    # visible price only, no 1000g tier at all.
                    "packaging": [{"price": "11,00 €", "weight": "250 g"}],
                },
            )
        ]
    )

    entries, status = await scrape.process_roaster(crawler, client, ROASTER, [], "2026-07-08")
    assert status == "ok"
    assert entries[0]["packaging"] == [
        {"weight_g": 1000, "price": 34.0},
        {"weight_g": 250, "price": 11.0},
    ]


@pytest.mark.asyncio
async def test_process_roaster_hash_gate_catches_price_only_variation_change():
    # Same markdown both runs (visible text only ever shows the default
    # variant) but the 1000g variation price changes from 34 to 36 — the
    # hash must still change, or this price update would never be picked up.
    markdown_text = LONG_TEXT + " 11,00 €"
    html_v1 = (
        '<form data-product_variations="'
        "[{&quot;attributes&quot;:{&quot;attribute_pa_hmotnost&quot;:&quot;1000-g&quot;},"
        "&quot;display_price&quot;:34}]"
        '"></form>'
    )
    html_v2 = (
        '<form data-product_variations="'
        "[{&quot;attributes&quot;:{&quot;attribute_pa_hmotnost&quot;:&quot;1000-g&quot;},"
        "&quot;display_price&quot;:36}]"
        '"></form>'
    )
    client = MagicMock()
    client.chat.completions.create.return_value = fake_completion(
        [fake_tool_call("extract_product", {"name": "Mexico Santa Cruz", "packaging": []})]
    )

    crawler_v1 = FakeCrawler(
        {
            "https://x.sk/": listing_result(["https://x.sk/mexico/"]),
            "https://x.sk/mexico/": fake_result(html=html_v1, markdown=fake_markdown(markdown_text)),
        }
    )
    entries_v1, _ = await scrape.process_roaster(crawler_v1, client, ROASTER, [], "2026-07-08")
    assert entries_v1[0]["packaging"] == [{"weight_g": 1000, "price": 34.0}]

    crawler_v2 = FakeCrawler(
        {
            "https://x.sk/": listing_result(["https://x.sk/mexico/"]),
            "https://x.sk/mexico/": fake_result(html=html_v2, markdown=fake_markdown(markdown_text)),
        }
    )
    entries_v2, _ = await scrape.process_roaster(crawler_v2, client, ROASTER, entries_v1, "2026-07-09")
    assert entries_v2[0]["packaging"] == [{"weight_g": 1000, "price": 36.0}]
    assert client.chat.completions.create.call_count == 2  # re-extracted, not hash-gated away


@pytest.mark.asyncio
async def test_process_roaster_hash_gate_still_skips_when_nothing_changed():
    # Regression guard: identical markdown AND identical (or absent)
    # variations JSON across two runs must still hit the hash-gate.
    markdown_text = LONG_TEXT + " 12,50 €"
    crawler_v1 = FakeCrawler(
        {
            "https://x.sk/": listing_result(["https://x.sk/rwanda/"]),
            "https://x.sk/rwanda/": fake_result(markdown=fake_markdown(markdown_text)),
        }
    )
    client = MagicMock()
    client.chat.completions.create.return_value = fake_completion(
        [fake_tool_call("extract_product", {"name": "Rwanda", "packaging": [{"price": "12,50 €", "weight": "250 g"}]})]
    )
    entries_v1, _ = await scrape.process_roaster(crawler_v1, client, ROASTER, [], "2026-07-08")
    assert client.chat.completions.create.call_count == 1

    crawler_v2 = FakeCrawler(
        {
            "https://x.sk/": listing_result(["https://x.sk/rwanda/"]),
            "https://x.sk/rwanda/": fake_result(markdown=fake_markdown(markdown_text)),
        }
    )
    entries_v2, _ = await scrape.process_roaster(crawler_v2, client, ROASTER, entries_v1, "2026-07-09")
    assert client.chat.completions.create.call_count == 1  # not called again
    assert entries_v2[0]["last_seen"] == "2026-07-09"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd scraper && python3 -m pytest test_scrape.py -k "variation_tiers_over_llm or hash_gate_catches_price_only or hash_gate_still_skips" -v`
Expected: FAIL — `entries[0]["packaging"]` still comes from the LLM's fabricated tier (first test), and/or the price-change test's second run doesn't re-extract (second test) because `process_roaster` doesn't yet read `result.html` for variations or fold it into the hash.

- [ ] **Step 3: Implement**

In `scraper/scrape.py`, inside `process_roaster` (currently lines 673–699), replace:

```python
        markdown = ""
        if result.markdown:
            markdown = result.markdown.fit_markdown or result.markdown.raw_markdown or ""
        if len(markdown.strip()) < MIN_TEXT_LENGTH:
            if prior:
                kept.append(prior)
            continue

        page_hash = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
```

with:

```python
        markdown = ""
        if result.markdown:
            markdown = result.markdown.fit_markdown or result.markdown.raw_markdown or ""
        if len(markdown.strip()) < MIN_TEXT_LENGTH:
            if prior:
                kept.append(prior)
            continue

        variations_raw, variation_tiers = extract_woocommerce_variations(result.html)
        # WooCommerce shows only the default-selected variant's price as
        # visible text — a price change on another variant wouldn't touch
        # `markdown` at all, so the raw variations JSON is folded into the
        # hash too, or such a change would be silently hash-gated away forever.
        page_hash = hashlib.sha256((markdown + variations_raw).encode("utf-8")).hexdigest()
```

Then further down, replace:

```python
        raw = extract_product(client, url, markdown)
        normalized = normalize_product(raw, url, today)
```

with:

```python
        raw = extract_product(client, url, markdown)
        normalized = normalize_product(raw, url, today, variation_tiers)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd scraper && python3 -m pytest test_scrape.py -v`
Expected: all tests pass (full suite — confirms no existing `process_roaster` test regressed)

- [ ] **Step 5: Commit**

```bash
git add scraper/scrape.py scraper/test_scrape.py
git commit -m "fix: fold WooCommerce variation JSON into page hash so price-only changes aren't hash-gated away"
```

---

### Task 4: Document the new price source

**Files:**
- Modify: `Architecture.md` (the "Detail Extraction" section, lines 57–61)

**Interfaces:** none — documentation only.

- [ ] **Step 1: Update `Architecture.md`**

Replace the paragraph starting "Hash the resulting markdown (SHA-256)..." (line 59) with:

```markdown
If the page is a WooCommerce variable product, `extract_woocommerce_variations()` parses its `data-product_variations` JSON attribute (BeautifulSoup, on the raw HTML — WooCommerce embeds every variation's price at initial page load, no browser rendering needed) into `{weight_g, price}` tiers directly, bypassing the LLM for pricing on those pages: markdown only ever shows the currently-selected variant's price, so asking the LLM to read prices off markdown silently loses every other weight tier. `normalize_product()` trusts these tiers over anything the LLM guesses when present.

Hash the resulting markdown **plus the raw variations JSON string** (SHA-256) and compare to the product's stored `page_hash` — folding in the variations JSON matters because a price change on a non-default variant never touches the visible markdown text, so hashing markdown alone would hash-gate that change away forever:
```

(Keep the two bullet points that follow — "Unchanged..." / "Changed..." — unchanged, they still apply to the combined hash.)

- [ ] **Step 2: Commit**

```bash
git add Architecture.md
git commit -m "docs: document WooCommerce variation pricing and the extended page hash"
```

---

## Self-Review

**Spec coverage:**
- Extract every weight/price tier from WooCommerce's embedded JSON, not just the visible default → Task 1.
- Use it instead of LLM-guessed pricing on those pages → Task 2 + Task 3.
- Don't silently miss price-only changes on non-default variants → Task 3's hash fix (this was found during planning, not explicitly asked for, but is required for the feature to be correct over time — a scraper that only gets today's price right and then never updates it again isn't done).
- Non-WooCommerce roasters unaffected → covered by the "Global Constraints" section and Task 2/3's regression test runs (`pytest test_scrape.py -v` full suite after each task).
- Docs reflect the new behavior → Task 4.

**Placeholder scan:** none found — every step has complete, runnable code.

**Type consistency:** `extract_woocommerce_variations` returns `(str, list[dict])` consistently across Tasks 1–3; `variation_tiers` parameter name and shape (`list[{"weight_g": int, "price": float}]`) match between `normalize_product` (Task 2) and `process_roaster`'s call site (Task 3).
