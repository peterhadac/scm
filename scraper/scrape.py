import argparse
import asyncio
import hashlib
import json
import os
import re
from contextlib import AsyncExitStack
from datetime import date
from pathlib import Path
from urllib.parse import urljoin, urlparse

import jsonschema
import yaml
from bs4 import BeautifulSoup
from openai import OpenAI
from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CacheMode,
    CrawlerRunConfig,
    DefaultMarkdownGenerator,
)
from crawl4ai.async_configs import HTTPCrawlerConfig
from crawl4ai.async_crawler_strategy import AsyncHTTPCrawlerStrategy

ROOT = Path(__file__).resolve().parent.parent
ROASTERS_PATH = ROOT / "roasters.yaml"
PRODUCTS_PATH = ROOT / "data" / "products.yaml"
SCHEMA_PATH = ROOT / "data" / "products.schema.yaml"
COUNTRIES_PATH = ROOT / "data" / "coffee_origins.yaml"
COFFEES_PATH = ROOT / "_data" / "coffees.json"

# Bump whenever normalize_product's rules change in a way that would alter
# the output for already-scraped pages — this forces process_roaster's
# hash-gate to re-extract every existing entry once, even if the page's
# content hasn't changed, since there's no cached raw LLM output to replay
# against the new rules.
SCHEMA_VERSION = 2

MODEL = "google/gemini-2.5-flash-lite"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

# Safety cap so a mis-detected "next" link (e.g. one that loops) can't spin forever.
MAX_PAGES = 10

# A page whose extracted text is shorter than this is almost certainly a
# JS-rendered shell rather than real content (used for both listing and
# product pages).
MIN_TEXT_LENGTH = 200

# Link text that commonly marks a "next page" control on Slovak/English shops.
NEXT_LINK_TEXTS = ("next", "ďalšia", "dalsia", "ďalej", "další", "nasledujúca", "»", "›", "→")

# Name substrings that flag an item as NOT a coffee (equipment, gift cards,
# subscriptions, accessories). Kept deliberately conservative — each token is
# unambiguous enough that a real single-origin coffee won't contain it. Note we
# intentionally do NOT list "kapsule"/"capsule" (those can be actual coffee).
NON_COFFEE_KEYWORDS = (
    # subscriptions / vouchers / gifts
    "predplatné",
    "predplatne",
    "subscription",
    "darčeková poukážka",
    "darcekova poukazka",
    "darčekový poukaz",
    "darcekovy poukaz",
    "poukážka",
    "poukazka",
    "gift card",
    "gift voucher",
    "voucher",
    # brewing equipment
    "mlynček",
    "mlyncek",
    "grinder",
    "french press",
    "aeropress",
    "chemex",
    "dripper",
    "moka kanvica",
    "kanvica",
    "konvica",
    "kettle",
    "váhy",
    "vahy",
    "kuchynská váha",
    "scale",
    "tamper",
    "tampovacia",
    "hrnček",
    "hrncek",
    "šálka",
    "salka",
    " mug",
    # consumables / accessories that aren't coffee
    "filtračné papiere",
    "filtracne papiere",
    "filter papers",
    "papierové filtre",
    "papierove filtre",
    "čistiaci",
    "cistiaci",
    "cleaning",
    "odvápňovač",
    "odvapnovac",
    "descaler",
    "tričko",
    "tricko",
    "t-shirt",
    "nálepka",
    "nalepka",
    "sticker",
)

# URL path segments that mark a discovered link as site plumbing (cart,
# account, legal, nav) rather than a product page. Same conservative-substring
# approach as NON_COFFEE_KEYWORDS, applied to the link's path instead of a
# product name — a cheap first-pass filter, not a guarantee: any non-product
# page that slips through still gets rejected downstream because Claude's
# extraction of it will yield no usable price/packaging (see normalize_product).
NON_PRODUCT_PATH_SEGMENTS = (
    "kosik",
    "cart",
    "checkout",
    "registracia",
    "prihlasenie",
    "login",
    "zabudnute-heslo",
    "kontakt",
    "vop",
    "obchodne-podmienky",
    "ochrana-osobnych-udajov",
    "ochrany-osobnych-udajov",
    "gdpr",
    "privacy",
    "b2b",
    "menu",
    "eventy",
    "blog",
    "faq",
    "o-nas",
    "about",
)

DISCOVERY_CONFIG = CrawlerRunConfig(prefetch=True, cache_mode=CacheMode.BYPASS)
# No content_filter: PruningContentFilter's density-based pruning discards
# compact widgets (verified against a real product page) — including the
# weight/price selector, which is exactly the data extraction needs. Plain
# markdown conversion still cuts a ~79KB page to ~6KB versus sending raw HTML,
# without losing that widget text.
DETAIL_CONFIG = CrawlerRunConfig(
    cache_mode=CacheMode.BYPASS,
    markdown_generator=DefaultMarkdownGenerator(),
)

EXTRACT_PRODUCT_TOOL = {
    "type": "function",
    "function": {
        "name": "extract_product",
        "description": (
            "Extract structured data for a single coffee product. Only call this "
            "if the page is a single specific coffee's product-detail page — not "
            "a category/listing page, homepage, cart, account page, or a page "
            "for something that isn't drinking coffee (tea, matcha, equipment, "
            "gift cards, subscriptions). If the page doesn't qualify, don't call "
            "this tool at all — just reply in plain text with a short reason."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "origin": {"type": ["string", "null"]},
                "process": {"type": ["string", "null"]},
                "roast_type": {
                    "type": ["string", "null"],
                    "description": (
                        "How the coffee is roasted for brewing, if the page states it: "
                        "'Filter' (drip/filter roast) or 'Espresso'. Raw text as shown, "
                        "null if not stated."
                    ),
                },
                "packaging": {
                    "type": "array",
                    "description": "Every weight/price option this coffee is sold in.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "weight": {
                                "type": ["string", "null"],
                                "description": "Raw package weight as shown, e.g. '250 g' or '1 kg'.",
                            },
                            "price": {
                                "type": "string",
                                "description": "Raw price as shown, e.g. '12,90 €'",
                            },
                        },
                        "required": ["price"],
                    },
                },
            },
            "required": ["name", "packaging"],
        },
    },
}


def load_roasters(path=ROASTERS_PATH):
    return yaml.safe_load(path.read_text())["roasters"]


def load_products(path=PRODUCTS_PATH):
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text()) or {}
    # PyYAML's implicit resolver parses an unquoted "2026-07-04" scalar back
    # into a datetime.date object, not the str this pipeline stores it as —
    # coerce it back at the load boundary so every caller sees a plain string.
    for entries in data.values():
        for entry in entries:
            last_seen = entry.get("last_seen")
            if isinstance(last_seen, date):
                entry["last_seen"] = last_seen.isoformat()
    return data


def save_products(products, path=PRODUCTS_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(products, allow_unicode=True, sort_keys=True) or "")


def load_country_aliases(path=COUNTRIES_PATH):
    """Flatten data/coffee_origins.yaml into a {lowercase alias: canonical name} map."""
    data = yaml.safe_load(path.read_text()) or {}
    aliases = {}
    for canonical, alias_list in data.items():
        for alias in alias_list:
            aliases[alias.lower()] = canonical
    return aliases


COUNTRY_ALIASES = load_country_aliases()


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


def find_next_page_url(html, current_url):
    """Return the absolute URL of the "next" page of a product listing, or None.

    Pure function (no network) so it can be unit-tested offline. Looks, in order,
    for a ``<link rel="next">``, an ``<a rel="next">``, an anchor whose class name
    contains ``next``, or an anchor whose visible text is a known next-page label
    ("Next", "Ďalšia", "»", …). Returns None when nothing plausible is found or
    when the only candidate resolves back to ``current_url`` (guards infinite loops).
    """
    soup = BeautifulSoup(html or "", "html.parser")

    def resolve(href):
        if not href:
            return None
        target = urljoin(current_url, href.strip())
        # Ignore fragment-only or self-referential links.
        if target.split("#")[0] == current_url.split("#")[0]:
            return None
        return target

    # 1. rel="next" on <link> or <a> (most reliable, standards-based).
    for tag in soup.find_all(["link", "a"], rel=True):
        rel = tag.get("rel") or []
        rel = [rel] if isinstance(rel, str) else rel
        if any(r.lower() == "next" for r in rel):
            resolved = resolve(tag.get("href"))
            if resolved:
                return resolved

    # 2. Anchor whose class hints at pagination-next.
    for a in soup.find_all("a", href=True):
        classes = " ".join(a.get("class") or []).lower()
        if "next" in classes and "context" not in classes:
            resolved = resolve(a["href"])
            if resolved:
                return resolved

    # 3. Anchor whose visible text is a known next-page label.
    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True).lower()
        if text and any(text == t or text.startswith(t) for t in NEXT_LINK_TEXTS):
            resolved = resolve(a["href"])
            if resolved:
                return resolved

    return None


def looks_like_product_link(href):
    path = urlparse(href).path.lower()
    return not any(segment in path for segment in NON_PRODUCT_PATH_SEGMENTS)


def visible_html_text_length(html):
    """Visible text length of a raw HTML page, ignoring script/style/head noise.

    Used on discovery's raw ``prefetch=True`` HTML (no markdown available
    there) to detect a JS-rendered empty shell — a naive ``get_text()`` over
    unstripped HTML would count inline `<script>` bodies as "content" and miss
    a genuinely empty page.
    """
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "head", "noscript", "svg"]):
        tag.decompose()
    return len(soup.get_text(strip=True))


async def discover_product_urls(crawler, roaster, max_pages=MAX_PAGES):
    """Crawl a roaster's listing (following pagination) and return (urls, status).

    Uses ``prefetch=True`` so this costs one plain HTTP fetch per page — no
    markdown generation, no LLM call. ``urls`` is None when the listing itself
    couldn't be read; ``status`` mirrors the roaster-level statuses this
    pipeline used before it went per-product ("ok" / "failed" / "needs_js").
    """
    url = roaster["url"]
    seen_pages = set()
    discovered = set()
    first_result = None

    for _ in range(max_pages):
        if not url or url in seen_pages:
            break
        seen_pages.add(url)
        try:
            result = await crawler.arun(url, config=DISCOVERY_CONFIG)
        except Exception:
            result = None
        if first_result is None:
            first_result = result
        if not result or not result.success:
            break

        page_domain = urlparse(str(result.redirected_url or result.url or url)).netloc
        for link in (result.links or {}).get("internal", []):
            href = link.get("href")
            text = link.get("text") or ""
            if not href:
                continue
            href = href.split("#")[0]
            if urlparse(href).netloc != page_domain:
                continue
            if looks_like_product_link(href) and is_coffee(text):
                discovered.add(href)

        current_url = str(result.redirected_url or result.url or url)
        nxt = find_next_page_url(result.html, current_url)
        if not nxt or nxt in seen_pages:
            break
        url = nxt

    if first_result is None or not first_result.success:
        return None, "failed"
    if visible_html_text_length(first_result.html) < MIN_TEXT_LENGTH:
        return None, "needs_js"
    return discovered, "ok"


def normalize_price(raw):
    """Parse the first EUR amount out of a raw price string into a float.

    Handles: plain "12,90 €", "od 12,90 €" (from/price ranges — takes the first
    number), thousands separators ("1.234,56 €", "1 234,56 €"), non-breaking
    spaces, and stray surrounding text. Returns None when no number is present.
    Per-kg vs per-package suffixes are ignored — the numeric value shown wins.
    """
    if not raw:
        return None
    text = raw.replace("\xa0", " ").replace(" ", " ")
    # Grab the first number-like token (digits plus internal spaces/.,), which
    # naturally takes the low end of a "12,90 - 15,90" range or "od 12,90".
    match = re.search(r"\d[\d.,\s]*\d|\d", text)
    if not match:
        return None
    token = match.group(0).strip().replace(" ", "")

    if "," in token and "." in token:
        # Whichever separator appears last is the decimal point; the other groups
        # thousands. Covers both "1.234,56" (SK/EU) and "1,234.56" (EN).
        if token.rfind(",") > token.rfind("."):
            token = token.replace(".", "").replace(",", ".")
        else:
            token = token.replace(",", "")
    elif "," in token:
        # Slovak sites use a comma as the decimal separator.
        token = token.replace(",", ".")
    # Only dots (or bare digits): treat the dot as a decimal point as-is.

    try:
        return float(token)
    except ValueError:
        return None


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


def parse_weight(text):
    """Extract a package weight in grams from free text (usually the product name).

    Understands "250 g", "250g", "1 kg", "0,25 kg", "1000 g", "1,5kg". Returns an
    int number of grams, or None when no weight is stated. Prefers an explicit
    gram figure when both a gram and kg token are present.
    """
    if not text:
        return None
    normalized = text.replace("\xa0", " ").replace(" ", " ").lower()

    grams_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:g|gr|gram(?:ov|s)?)\b", normalized)
    if grams_match:
        value = float(grams_match.group(1).replace(",", "."))
        return int(round(value))

    kg_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:kg|kilo(?:gram)?(?:ov|s)?)\b", normalized)
    if kg_match:
        value = float(kg_match.group(1).replace(",", ".")) * 1000
        return int(round(value))

    return None


def is_coffee(name):
    """Heuristic: True unless the name clearly names non-coffee (gear/gift/subscription).

    Conservative by design — a false negative (dropping a real coffee) is worse
    than letting an odd accessory through, so only unambiguous keywords match.
    """
    if not name:
        return True
    lowered = name.replace("\xa0", " ").lower()
    return not any(keyword in lowered for keyword in NON_COFFEE_KEYWORDS)


def extract_product(client, url, markdown):
    """Ask the model to extract one product, or decline for a non-product page.

    ``tool_choice`` is deliberately left at the default ("auto") rather than
    forced — forcing the tool made the model fabricate a product from category
    pages, the homepage, and non-coffee pages that slipped past the discovery
    link filter (verified against real listing pages). Declining is a plain
    text reply with no tool call, which this treats as "not a product."
    """
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=1024,
        tools=[EXTRACT_PRODUCT_TOOL],
        messages=[
            {
                "role": "user",
                "content": (
                    f"Extract this page's coffee product details, if it has "
                    f"exactly one (URL: {url}). Page content:\n\n{markdown}"
                ),
            }
        ],
    )
    for call in response.choices[0].message.tool_calls or []:
        if call.function.name == "extract_product":
            return json.loads(call.function.arguments)
    return None


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


def flatten_to_coffees(products, roasters):
    """Explode every product's packaging tiers into flat coffees.json rows."""
    roaster_by_slug = {r["slug"]: r for r in roasters}
    seen = set()
    rows = []
    for slug, entries in products.items():
        roaster = roaster_by_slug.get(slug)
        roaster_name = roaster["name"] if roaster else slug
        for product in entries:
            # "not_a_product" markers (declined nav/category links, cached so
            # they aren't re-fetched every run) carry no packaging — skip them.
            for tier in product.get("packaging") or []:
                key = (product["url"], tier.get("weight_g"))
                if key in seen:
                    continue
                seen.add(key)
                rows.append(
                    {
                        "name": product["name"],
                        "roaster": roaster_name,
                        "origin": product.get("origin"),
                        "process": product.get("process"),
                        "roast_type": product.get("roast_type"),
                        "price": tier["price"],
                        "weight_g": tier.get("weight_g"),
                        "url": product["url"],
                        "last_seen": product["last_seen"],
                    }
                )
    return rows


async def run(only=None, roasters_path=ROASTERS_PATH, products_path=PRODUCTS_PATH, coffees_path=COFFEES_PATH):
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
    rows = flatten_to_coffees(products, all_roasters)
    coffees_path.parent.mkdir(parents=True, exist_ok=True)
    coffees_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")

    print("scrape_status:")
    for name, status in statuses.items():
        print(f"  {name}: {status}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="limit the run to roasters whose name contains this substring")
    args = parser.parse_args()
    asyncio.run(run(only=args.only))


if __name__ == "__main__":
    main()
