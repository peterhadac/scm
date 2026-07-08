import argparse
import asyncio
import hashlib
import json
import os
import re
import unicodedata
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

# WooCommerce attribute-key substrings roasters use for a coffee's package
# weight ("hmotnosť"/"váha" are plain Slovak for "weight", "balenie" is
# Slovak for "packaging"; "weight" covers sites that keep the English
# WooCommerce taxonomy slug untranslated — sites pick whichever taxonomy
# name they set up; ponytail: extend if a roaster uses yet another term).
WEIGHT_ATTRIBUTE_KEYWORDS = ("hmotnost", "vaha", "weight", "balenie")

# Bump whenever normalize_product's rules change in a way that would alter
# the output for already-scraped pages — this forces process_roaster's
# hash-gate to re-extract every existing entry once, even if the page's
# content hasn't changed, since there's no cached raw LLM output to replay
# against the new rules.
SCHEMA_VERSION = 12

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
    "degustačný balíček",
    "degustacny balicek",
    "darčekový balíček",
    "darcekovy balicek",
    "poukážka",
    "poukazka",
    "gift card",
    "gift voucher",
    "voucher",
    # brewing equipment
    "mlynček",
    "mlyncek",
    "grinder",
    "kávovar",
    "kavovar",  # generic "coffee maker/brewer" - catches unbranded machines too
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
    "timemore",  # scale/grinder brand
    "tamper",
    "tampovacia",
    "hrnček",
    "hrncek",
    "šálka",
    "salka",
    " mug",
    "espresso cup",  # not bare "cup" - collides with "cupping score/notes"
    "s uškom",
    "s uskom",  # "with a handle" - mug/cup collection descriptor
    "bez uška",
    "bez uska",  # "without a handle" - same
    "štipec",
    "stipec",  # bag clip
    "baristický kurz",
    "baristicky kurz",  # barista course - a service, not a product
    "vakuová dóza",
    "vakuova doza",  # vacuum storage container
    "nádoba nahrádna",
    "nadoba nahradna",  # replacement storage container
    "kávoláda",
    "kavolada",  # coffee-flavored chocolate, not beans
    "víno s kávou",
    "vino s kavou",  # coffee-infused wine, a bottled drink not beans
    "eureka mignon",
    "bezzera",
    "ecm classica",
    "ecm portafilter",
    "ecm sada",
    "rocket appartamento",
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
    "news",
    "faq",
    "o-nas",
    "about",
    "sluzby",
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
                "origin": {
                    "type": ["string", "null"],
                    "description": (
                        "The coffee's source country, if stated. If the page's "
                        "'Krajina pôvodu' (or similar) attribute lists MULTIPLE "
                        "countries (e.g. 'Brazília, Honduras, India, Nikaragua'), "
                        "this is a multi-origin blend — reply with the literal "
                        "string 'Blend' rather than leaving this null or picking "
                        "just one of the listed countries. Null only if the page "
                        "states no origin information at all."
                    ),
                },
                "process": {"type": ["string", "null"]},
                "roast_type": {
                    "type": ["string", "null"],
                    "description": (
                        "How the coffee is roasted for brewing: 'Filter' (drip/filter "
                        "roast) or 'Espresso'. If the page doesn't state this directly, "
                        "check for a 'recommended preparation method' attribute/tag list "
                        "(e.g. 'Espresso, Moka, Pour-over') and infer from it: "
                        "'Espresso' if Espresso or Moka is listed, 'Filter' if only "
                        "pour-over/drip/V60/Chemex/Aeropress/French press methods are "
                        "listed. Raw text (or your inference) as a string, null only if "
                        "truly nothing on the page suggests either."
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


def strip_diacritics(text):
    """Fold accented characters to their plain ASCII base ("Salvádor" -> "Salvador").

    Product names inconsistently carry stray diacritics (a Slovak site
    styling a borrowed word, or vice versa) that would otherwise break a
    plain substring match against the (also inconsistently accented)
    alias list — comparing both sides post-strip makes matching robust to
    that noise instead of silently missing a country that IS named.
    """
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def load_country_aliases(path=COUNTRIES_PATH):
    """Flatten data/coffee_origins.yaml into a {diacritic-free lowercase alias: canonical name} map."""
    data = yaml.safe_load(path.read_text()) or {}
    aliases = {}
    for canonical, alias_list in data.items():
        for alias in alias_list:
            aliases[strip_diacritics(alias.lower())] = canonical
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



# Name/raw-origin substrings marking a coffee as a multi-origin blend — these
# genuinely have no single source country, so "Blend" is the honest origin
# rather than a gap to keep chasing. Slovak "zmes"/"zmesi" (blend/blends),
# English "blend"/"mix".
BLEND_KEYWORDS = ("blend", "zmes", "mix")


def normalize_origin(raw, name, aliases=None):
    """Translate a stated origin to its canonical English country name.

    Only falls back to scanning the product name when `raw` is empty —
    trusts an LLM-stated origin as-is (translating known aliases), it never
    cross-checks it against the name. Text that matches no known country is
    kept verbatim rather than discarded (better than losing real data for a
    producing country not yet in the list).

    A multi-origin blend (name or raw text names it as such) rarely states
    one source country at all — falls back to the sentinel "Blend" rather
    than staying null, since the coffee genuinely has no single origin to
    report, not a missed extraction.
    """
    aliases = COUNTRY_ALIASES if aliases is None else aliases
    if raw:
        lowered = strip_diacritics(raw.lower())
        for alias, canonical in aliases.items():
            if alias in lowered:
                return canonical
        stripped = raw.strip()
        return stripped or None
    if name:
        lowered = strip_diacritics(name.lower())
        for alias, canonical in aliases.items():
            if alias in lowered:
                return canonical
        if any(keyword in lowered for keyword in BLEND_KEYWORDS):
            return "Blend"
    return None


# WooCommerce attribute-key substrings for a coffee's source-country
# attribute ("krajina" + "povod" = Slovak "krajina pôvodu", "country of
# origin"; "origin" covers an untranslated English slug).
ORIGIN_ATTRIBUTE_KEYWORDS = ("krajina", "povod", "origin")


def extract_woocommerce_origin(html):
    """Parse a WooCommerce product's "Additional information" origin attribute row.

    WordPress/WooCommerce renders each product attribute as a
    `<tr class="...attribute_pa_<slug>...">` row regardless of theme — this
    reads that row's visible text directly rather than relying on the LLM to
    correctly resolve a possibly-multi-country list (some products list
    several source countries, e.g. "Brazília, Honduras, India, Nikaragua"
    for a blend) into one origin, which it does inconsistently.

    Returns a canonical origin (a COUNTRY_ALIASES value, or "Blend" when 2+
    distinct countries are listed), or None if no origin-like attribute row
    is found — the caller falls through to the LLM's own origin field.
    """
    soup = BeautifulSoup(html or "", "html.parser")
    row = soup.find("tr", class_=re.compile(r"attribute_pa_(?:%s)" % "|".join(ORIGIN_ATTRIBUTE_KEYWORDS), re.I))
    if not row:
        return None
    cell = row.find("td")
    if not cell:
        return None
    countries = set()
    for part in cell.get_text(", ").split(","):
        part = strip_diacritics(part.strip().lower())
        if not part:
            continue
        for alias, canonical in COUNTRY_ALIASES.items():
            if alias in part:
                countries.add(canonical)
                break
    if not countries:
        return None
    if len(countries) == 1:
        return next(iter(countries))
    return "Blend"


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
    if not isinstance(variations, list):
        return raw_json, []

    tiers = []
    seen_weights = set()
    for variation in variations:
        if not isinstance(variation, dict):
            continue
        # Any malformed nested field here (non-dict attributes, a non-string
        # weight slug, ...) makes this one variation unusable — skip it
        # rather than adding another narrow isinstance check per field; this
        # closes the whole class of untyped-nested-JSON crashes at once.
        try:
            attributes = variation.get("attributes") or {}
            weight_slug = next(
                (
                    v
                    for k, v in attributes.items()
                    if any(keyword in k.lower() for keyword in WEIGHT_ATTRIBUTE_KEYWORDS)
                ),
                None,
            )
            weight_g = parse_weight((weight_slug or "").replace("-", " "))
            price = variation.get("display_price")
        except (AttributeError, TypeError):
            continue
        if (
            weight_g is None
            or isinstance(price, bool)
            or not isinstance(price, (int, float))
            or price <= 0
        ):
            continue
        if weight_g in seen_weights:
            continue
        seen_weights.add(weight_g)
        tiers.append({"weight_g": weight_g, "price": float(price)})
    return raw_json, tiers


async def _crawl_listing_links(crawler, start_url, max_pages=MAX_PAGES):
    """Follow pagination from `start_url`, collecting same-domain product-ish links.

    Shared by discover_product_urls (the roaster's main listing) and
    discover_roast_type_hints (per-category listing pages) — both need the
    same fetch/filter/paginate loop; only what the caller does with a
    fetch failure differs (roaster-level "failed"/"needs_js" status vs. a
    category hint page simply contributing no hints).

    Returns (urls, first_result): `urls` is the set of discovered links
    (empty if the page had none or was unreachable). `first_result` is the
    crawl result for the first page fetched (None if unreachable) — callers
    needing roaster-level status inspect it themselves.
    """
    url = start_url
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
            # Strip fragment and query string — WooCommerce's filter widgets,
            # sort links, and "add to cart" actions all attach query params
            # to the listing page itself (e.g. "?filter_hmotnost=250-g",
            # "?add-to-cart=1909"), which would otherwise dedup as distinct
            # "discovered" URLs and get needlessly re-fetched/re-classified
            # as not_a_product every single run.
            href = href.split("#")[0].split("?")[0]
            parsed_href = urlparse(href)
            # Explicit scheme check, not just relying on the netloc mismatch
            # below to incidentally reject javascript:/data: URIs — a poisoned
            # page's link (or a future crawl4ai internal-link change) should
            # never let a non-http(s) scheme reach `discovered`, since this
            # URL is stored verbatim in products.yaml and rendered as a
            # clickable link on the site.
            if parsed_href.scheme not in ("http", "https"):
                continue
            if parsed_href.netloc != page_domain:
                continue
            if looks_like_product_link(href) and is_coffee(text):
                discovered.add(href)

        current_url = str(result.redirected_url or result.url or url)
        nxt = find_next_page_url(result.html, current_url)
        if not nxt or nxt in seen_pages:
            break
        url = nxt

    return discovered, first_result


async def discover_product_urls(crawler, roaster, max_pages=MAX_PAGES):
    """Crawl a roaster's listing (following pagination) and return (urls, status).

    Uses ``prefetch=True`` so this costs one plain HTTP fetch per page — no
    markdown generation, no LLM call. ``urls`` is None when the listing itself
    couldn't be read; ``status`` mirrors the roaster-level statuses this
    pipeline used before it went per-product ("ok" / "failed" / "needs_js").
    """
    discovered, first_result = await _crawl_listing_links(
        crawler, roaster["scrape_url"], max_pages
    )
    if first_result is None or not first_result.success:
        return None, "failed"
    if visible_html_text_length(first_result.html) < MIN_TEXT_LENGTH:
        return None, "needs_js"
    return discovered, "ok"


async def discover_roast_type_hints(crawler, roaster, max_pages=MAX_PAGES):
    """Crawl a roaster's optional `roast_type_urls` category pages for roast-type hints.

    Some sites (Shopify collections, Shoptet category pages) only reveal a
    product's roast type through which category page links to it — the
    product's own page never states "Filter" or "Espresso" at all. This is
    a best-effort hint, not authoritative: a fetch failure on one category
    just means no hints from it, not a roaster-level failure. Returns
    {url: roast_type}; last-write-wins on the rare case a product genuinely
    appears under both categories.
    """
    hints = {}
    for roast_type, url in (roaster.get("roast_type_urls") or {}).items():
        urls, _ = await _crawl_listing_links(crawler, url, max_pages)
        for discovered_url in urls:
            hints[discovered_url] = roast_type
    return hints


async def extract_shopify_variations(crawler, html, product_url):
    """Fetch and parse a Shopify product's price/weight tiers via its `.js` endpoint.

    A Shopify product page can hide non-default variant prices from visible
    markdown the same way WooCommerce's data-product_variations attribute
    does — but every Shopify storefront exposes the full product JSON
    (every variant's own price, in cents) at `{product_url}.js`, a stable
    documented public endpoint, regardless of theme. Only fires this extra
    fetch when `html` looks like a Shopify storefront (checked on the
    already-fetched product page — avoids a wasted request on every
    non-Shopify roaster's every product).

    Returns a list of {"weight_g": int, "price": float} tiers (deduped by
    weight_g, first-seen wins), or [] if this isn't a Shopify product page
    or the endpoint didn't return usable data.
    """
    if "cdn.shopify.com" not in (html or ""):
        return []
    variants_url = product_url.split("?")[0].rstrip("/") + ".js"
    try:
        result = await crawler.arun(variants_url, config=DETAIL_CONFIG)
    except Exception:
        return []
    if not result or not result.success:
        return []
    try:
        data = json.loads(result.html or "")
    except (ValueError, TypeError):
        return []
    if not isinstance(data, dict):
        return []

    tiers = []
    seen_weights = set()
    for variant in data.get("variants") or []:
        if not isinstance(variant, dict):
            continue
        weight_g = parse_weight(str(variant.get("title") or ""))
        price_cents = variant.get("price")
        if (
            weight_g is None
            or isinstance(price_cents, bool)
            or not isinstance(price_cents, (int, float))
            or price_cents <= 0
        ):
            continue
        if weight_g in seen_weights:
            continue
        seen_weights.add(weight_g)
        tiers.append({"weight_g": weight_g, "price": round(price_cents / 100, 2)})
    return tiers


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


def normalize_roast_type(raw, process_raw=None, name=None, category_hint=None):
    """Bucket free-text roast info into 'filter' / 'espresso' / None.

    Tries `raw` (the model's own roast_type field) first, then falls back to
    the raw `process` text, then the product name — e.g. `process: "filter
    roast"` already implies roast_type even when the model left roast_type
    itself blank. `category_hint` (from discover_roast_type_hints — which
    category/collection page linked to this product) is the last resort,
    used only when the page itself states nothing at all: some sites (Shopify
    collections, Shoptet category pages) never state a roast type on the
    product page, only via which listing links to it.
    """
    for text in (raw, process_raw, name):
        if not text:
            continue
        lowered = text.strip().lower()
        if "espresso" in lowered:
            return "espresso"
        if (
            "filter" in lowered
            or "prekvapk" in lowered
            or "filtrovan" in lowered
            or "zalievan" in lowered  # pour-over ("zaliať" = to pour)
            or "kvapkov" in lowered  # drip
        ):
            return "filter"
    if category_hint in ("filter", "espresso"):
        return category_hint
    return None


# WooCommerce attribute-key substring for a coffee's recommended preparation
# method ("odporúčaný spôsob prípravy") — deliberately NOT "prazenia" alone,
# which also matches the unrelated "stupeň praženia" (roast degree: light/
# medium/dark) attribute.
ROAST_TYPE_ATTRIBUTE_KEYWORD = "sposob-pripravy"


def extract_woocommerce_roast_type(html):
    """Parse a WooCommerce product's "recommended preparation method" attribute row.

    Same rationale and technique as `extract_woocommerce_origin()`: the LLM
    prompt hint for a multi-method list ("Espresso, Moka, Pour-over") isn't
    reliable on every call, so this reads the attribute row directly and
    reuses `normalize_roast_type()`'s keyword matching on its text. Returns
    None if no such attribute row is found or it names neither method.
    """
    soup = BeautifulSoup(html or "", "html.parser")
    row = soup.find("tr", class_=re.compile(r"attribute_pa_[a-z-]*" + ROAST_TYPE_ATTRIBUTE_KEYWORD, re.I))
    if not row:
        return None
    cell = row.find("td")
    if not cell:
        return None
    return normalize_roast_type(cell.get_text(", "))


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


def normalize_product(
    raw,
    url,
    today,
    variation_tiers=None,
    roast_type_hint=None,
    origin_hint=None,
    roast_type_attribute_hint=None,
):
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

    `roast_type_hint`, from `discover_roast_type_hints()`, is the last-resort
    fallback passed to `normalize_roast_type()` for sites that never state a
    roast type on the product page itself.

    `origin_hint`, from `extract_woocommerce_origin()`, is trusted over the
    LLM's own origin guess when present — same reasoning as variation_tiers:
    a WooCommerce attribute row beats an LLM inconsistently resolving a
    multi-country list.

    `roast_type_attribute_hint`, from `extract_woocommerce_roast_type()`, is
    trusted over the LLM's own roast_type guess when present — same
    reasoning as origin_hint. `roast_type_hint` (the discovery-category
    hint) remains the last resort inside `normalize_roast_type()` for pages
    with neither this attribute nor any stated text.
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

    process = normalize_process(raw.get("process"))
    roast_type = roast_type_attribute_hint or normalize_roast_type(
        raw.get("roast_type"), raw.get("process"), name, roast_type_hint
    )
    origin = origin_hint or normalize_origin(raw.get("origin"), name)

    # These two heuristics catch LLM extraction failures specifically — they
    # don't apply when packaging came from variation_tiers (WooCommerce's own
    # structured data), where a real price collision (e.g. a promo, or 250g
    # whole-bean vs. ground priced the same) is known-correct, not a guess.
    if variation_tiers:
        price_collision = False
        weight_as_price = False
    else:
        weighted_tiers = [t for t in packaging if t["weight_g"] is not None]
        distinct_weights = {t["weight_g"] for t in weighted_tiers}
        distinct_prices = {t["price"] for t in weighted_tiers}
        price_collision = len(distinct_weights) >= 2 and len(distinct_prices) == 1
        # Separate bug signature: the model read each tier's weight number as its
        # price (e.g. weight_g: 200, price: 200.0) — prices are distinct across
        # tiers so price_collision above misses it.
        weight_as_price = sum(1 for t in weighted_tiers if t["price"] == t["weight_g"]) >= 2

    missing_fields = []
    if origin is None:
        missing_fields.append("origin")
    if roast_type is None:
        missing_fields.append("roast_type")
    if any(t["weight_g"] is None for t in packaging):
        missing_fields.append("weight_g")
    if price_collision or weight_as_price:
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

    # {} immediately when the roaster has no roast_type_urls configured —
    # no extra crawl for the common case.
    roast_type_hints = await discover_roast_type_hints(crawler, roaster)

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

        variations_raw, variation_tiers = extract_woocommerce_variations(result.html)
        # WooCommerce shows only the default-selected variant's price as
        # visible text — a price change on another variant wouldn't touch
        # `markdown` at all, so the raw variations JSON is folded into the
        # hash too, or such a change would be silently hash-gated away forever.
        page_hash = hashlib.sha256((markdown + variations_raw).encode("utf-8")).hexdigest()
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

        if not variation_tiers:
            # Shopify's per-variant prices live behind a separate `.js`
            # fetch (see extract_shopify_variations) — a price-only change
            # there won't bust this page's hash, so it's only re-checked
            # when we're already re-extracting for some other reason. Not
            # gated into page_hash: that would force this extra fetch on
            # every run regardless of hash-gate, defeating the point of it.
            variation_tiers = await extract_shopify_variations(crawler, result.html, url)

        raw = extract_product(client, url, markdown)
        origin_hint = extract_woocommerce_origin(result.html)
        roast_type_attribute_hint = extract_woocommerce_roast_type(result.html)
        normalized = normalize_product(
            raw,
            url,
            today,
            variation_tiers,
            roast_type_hints.get(url),
            origin_hint,
            roast_type_attribute_hint,
        )
        if normalized is None:
            # A bare decline (Claude returned nothing, or no name at all) is
            # ambiguous — could be a transient hiccup — and worth protecting
            # prior data against. A name that Claude DID extract but that our
            # own is_coffee() rejects is a confident, deterministic
            # classification (e.g. a NON_COFFEE_KEYWORDS addition correctly
            # catching a product type that slipped through before) — that
            # must be allowed to reclassify a stale ok/incomplete entry to
            # not_a_product, not protect it forever.
            confidently_not_coffee = (
                isinstance(raw, dict) and raw.get("name") and not is_coffee(raw["name"])
            )
            if prior and prior.get("status") in ("ok", "incomplete") and not confidently_not_coffee:
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="limit the run to roasters whose name contains this substring")
    args = parser.parse_args()
    asyncio.run(run(only=args.only))


if __name__ == "__main__":
    main()
