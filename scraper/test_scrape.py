import asyncio
import json
import re
from types import SimpleNamespace
from unittest.mock import MagicMock

import jsonschema
import openai
import pytest
import yaml
from bs4 import BeautifulSoup

import scrape

# Captured before anything ever monkeypatches it. `scrape.asyncio` is the
# very same module object as this `asyncio` import (module identity, not a
# separate copy) — the autouse `_no_real_politeness_sleep` fixture below
# patches `scrape.asyncio.sleep` globally, so any later `asyncio.sleep`
# lookup (including from this test file itself) would otherwise also see
# the stub, not the real function, making it impossible to restore real
# sleep()-based yielding within a single test.
_REAL_ASYNCIO_SLEEP = asyncio.sleep


def _soup(html):
    """Build a BeautifulSoup the same way process_roaster does (issue #27:
    the extraction helpers now take an already-parsed soup instead of a raw
    HTML string, since a product page used to be re-parsed from scratch by
    each one of them)."""
    return BeautifulSoup(html or "", scrape.HTML_PARSER)


def fake_tool_call(name, arguments):
    call = MagicMock()
    call.function.name = name
    call.function.arguments = json.dumps(arguments)
    return call


def fake_completion(tool_calls=None, content=None, finish_reason="stop"):
    message = MagicMock(tool_calls=tool_calls or [], content=content)
    return MagicMock(choices=[MagicMock(message=message, finish_reason=finish_reason)])


def fake_result(
    success=True,
    html="",
    markdown=None,
    links=None,
    url="https://x.sk/",
    redirected_url=None,
):
    return SimpleNamespace(
        success=success,
        html=html,
        markdown=markdown,
        links=links or {"internal": []},
        url=url,
        redirected_url=redirected_url,
    )


def fake_markdown(text):
    return SimpleNamespace(fit_markdown=None, raw_markdown=text)


class FakeCrawler:
    """Duck-typed stand-in for crawl4ai's AsyncWebCrawler: `.arun(url, config)`."""

    def __init__(self, responses):
        self.responses = responses  # dict url -> fake_result(...)
        self.calls = []

    async def arun(self, url, config=None):
        self.calls.append(url)
        result = self.responses.get(url)
        if result is None:
            return fake_result(success=False)
        return result


@pytest.fixture(autouse=True)
def _no_real_politeness_sleep(monkeypatch):
    """process_roaster/run() now insert a real POLITENESS_DELAY_SECONDS
    sleep (issue #27) between same-domain fetches, and most tests exercise
    a roaster with several discovered pages/products — without this, the
    suite would burn several real seconds per such test. Stub
    asyncio.sleep to return instantly by default; the dedicated
    politeness-delay tests below install their own instrumented stub (via
    the same `monkeypatch` fixture instance, which simply overrides this)
    to actually verify the call happens with the right arguments.
    """

    async def instant_sleep(seconds):
        return None

    monkeypatch.setattr(scrape.asyncio, "sleep", instant_sleep)


# --- load_products (YAML date round-trip) ------------------------------------


def test_load_products_coerces_yaml_date_back_to_string(tmp_path):
    # An unquoted "2026-07-04" scalar is parsed by PyYAML as a datetime.date,
    # not the str this pipeline stores it as — load_products must undo that.
    path = tmp_path / "products.yaml"
    path.write_text("roaster:\n- url: https://x.sk/a\n  last_seen: 2026-07-04\n")
    data = scrape.load_products(path)
    assert data["roaster"][0]["last_seen"] == "2026-07-04"
    assert isinstance(data["roaster"][0]["last_seen"], str)


# --- load_roasters (roasters.schema.yaml validation) -------------------------


def test_load_roasters_accepts_well_formed_entry(tmp_path):
    path = tmp_path / "roasters.yaml"
    path.write_text(
        "roasters:\n"
        "  - name: Example\n"
        "    slug: example\n"
        "    url: https://example.sk/\n"
        "    scrape_url: https://example.sk/\n"
        "    metadata:\n"
        "      city: Bratislava\n"
    )
    roasters = scrape.load_roasters(path)
    assert roasters[0]["metadata"]["city"] == "Bratislava"


def test_load_roasters_rejects_entry_missing_city(tmp_path):
    # metadata.city is required (issue: roasters without it silently fell
    # into the map's "not on the map yet" list instead of failing the run).
    path = tmp_path / "roasters.yaml"
    path.write_text(
        "roasters:\n"
        "  - name: Example\n"
        "    slug: example\n"
        "    url: https://example.sk/\n"
        "    scrape_url: https://example.sk/\n"
        "    metadata: {}\n"
    )
    with pytest.raises(jsonschema.ValidationError):
        scrape.load_roasters(path)


def test_load_roasters_rejects_entry_missing_metadata(tmp_path):
    path = tmp_path / "roasters.yaml"
    path.write_text(
        "roasters:\n"
        "  - name: Example\n"
        "    slug: example\n"
        "    url: https://example.sk/\n"
        "    scrape_url: https://example.sk/\n"
    )
    with pytest.raises(jsonschema.ValidationError):
        scrape.load_roasters(path)


def test_normalize_price_comma_decimal():
    assert scrape.normalize_price("12,90 €") == 12.90


def test_normalize_price_thousands_and_decimal():
    assert scrape.normalize_price("1.234,56 €") == 1234.56


# --- normalize_price edge cases ---------------------------------------------


def test_normalize_price_from_prefix():
    # "od" = "from" — take the number that follows.
    assert scrape.normalize_price("od 12,90 €") == 12.90


def test_normalize_price_range_takes_first():
    assert scrape.normalize_price("12,90 - 15,90 €") == 12.90


def test_normalize_price_space_thousands_separator():
    assert scrape.normalize_price("1 234,56 €") == 1234.56


def test_normalize_price_english_thousands_and_decimal():
    # "1,234.56" — comma is the thousands separator here (dot is last => decimal).
    assert scrape.normalize_price("1,234.56 €") == 1234.56


def test_normalize_price_nbsp_and_whitespace():
    assert scrape.normalize_price("  12,90 € ") == 12.90


def test_normalize_price_per_kg_suffix_does_not_crash():
    assert scrape.normalize_price("24,90 € / kg") == 24.90


def test_normalize_price_no_number_returns_none():
    assert scrape.normalize_price("Vypredané") is None
    assert scrape.normalize_price("") is None
    assert scrape.normalize_price(None) is None


# --- parse_weight ------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Etiópia Yirgacheffe 250 g", 250),
        ("Brazil Cerrado 200g", 200),
        ("House Blend 1 kg", 1000),
        ("Sample pack 0,25 kg", 250),
        ("Big bag 1000 g", 1000),
        ("Espresso 1,5kg", 1500),
        ("Kenya AA", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_weight(text, expected):
    assert scrape.parse_weight(text) == expected


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
    raw_json, tiers = scrape.extract_woocommerce_variations(_soup(WOO_VARIATIONS_HTML))
    assert raw_json  # non-empty, used for hashing
    assert tiers == [
        {"weight_g": 1000, "price": 34.0},
        {"weight_g": 250, "price": 11.0},
    ]


def test_extract_woocommerce_variations_recognizes_vaha_weight_slug():
    # casa-del-caffe.sk uses "attribute_pa_vaha-balenia" ("package weight")
    # instead of Trip Coffee Roasters' "attribute_pa_hmotnost" — both mean
    # "weight" in Slovak, sites pick either taxonomy name.
    html = (
        '<form data-product_variations="'
        "[{&quot;attributes&quot;:{&quot;attribute_pa_vaha-balenia&quot;:&quot;500g&quot;},"
        "&quot;display_price&quot;:16.9},"
        "{&quot;attributes&quot;:{&quot;attribute_pa_vaha-balenia&quot;:&quot;1000g&quot;},"
        "&quot;display_price&quot;:29.9}]"
        '"></form>'
    )
    _, tiers = scrape.extract_woocommerce_variations(_soup(html))
    assert tiers == [
        {"weight_g": 500, "price": 16.9},
        {"weight_g": 1000, "price": 29.9},
    ]


def test_extract_woocommerce_variations_recognizes_weight_slug():
    # sweetbeans.coffee uses the untranslated English WooCommerce slug
    # "attribute_pa_weight", and disambiguation suffixes like "-2" on a
    # value ("500-gr-2") must not break weight parsing.
    html = (
        '<form data-product_variations="'
        "[{&quot;attributes&quot;:{&quot;attribute_pa_weight&quot;:&quot;200-gr&quot;},"
        "&quot;display_price&quot;:14},"
        "{&quot;attributes&quot;:{&quot;attribute_pa_weight&quot;:&quot;500-gr-2&quot;},"
        "&quot;display_price&quot;:29}]"
        '"></form>'
    )
    _, tiers = scrape.extract_woocommerce_variations(_soup(html))
    assert tiers == [
        {"weight_g": 200, "price": 14.0},
        {"weight_g": 500, "price": 29.0},
    ]


def test_extract_woocommerce_variations_recognizes_balenie_weight_slug():
    # simplecoffee.sk uses "attribute_pa_balenie" ("packaging").
    html = (
        '<form data-product_variations="'
        "[{&quot;attributes&quot;:{&quot;attribute_pa_balenie&quot;:&quot;250g&quot;},"
        "&quot;display_price&quot;:9.9},"
        "{&quot;attributes&quot;:{&quot;attribute_pa_balenie&quot;:&quot;1000g&quot;},"
        "&quot;display_price&quot;:35.9}]"
        '"></form>'
    )
    _, tiers = scrape.extract_woocommerce_variations(_soup(html))
    assert tiers == [
        {"weight_g": 250, "price": 9.9},
        {"weight_g": 1000, "price": 35.9},
    ]


def test_extract_woocommerce_variations_absent_returns_empty():
    raw_json, tiers = scrape.extract_woocommerce_variations(_soup("<html><body>no form here</body></html>"))
    assert raw_json == ""
    assert tiers == []


def test_extract_woocommerce_variations_malformed_json_returns_raw_and_empty_tiers():
    html = '<form data-product_variations="not valid json"></form>'
    raw_json, tiers = scrape.extract_woocommerce_variations(_soup(html))
    assert raw_json == "not valid json"
    assert tiers == []


def test_extract_woocommerce_variations_keeps_distinct_tiers_for_a_second_variant_axis():
    # Same weight, but a second attribute (grind) genuinely distinguishes
    # the two variations — both tiers must survive, each tagged with its
    # own variant label, instead of collapsing into one.
    html = (
        '<form data-product_variations="'
        "[{&quot;attributes&quot;:{&quot;attribute_pa_hmotnost&quot;:&quot;250-g&quot;,"
        "&quot;attribute_pa_typ&quot;:&quot;zrnkova&quot;},"
        "&quot;display_price&quot;:11,&quot;display_regular_price&quot;:11},"
        "{&quot;attributes&quot;:{&quot;attribute_pa_hmotnost&quot;:&quot;250-g&quot;,"
        "&quot;attribute_pa_typ&quot;:&quot;mleta&quot;},"
        "&quot;display_price&quot;:13,&quot;display_regular_price&quot;:13}]"
        '"></form>'
    )
    _, tiers = scrape.extract_woocommerce_variations(_soup(html))
    assert tiers == [
        {"weight_g": 250, "price": 11.0, "variant": "zrnkova"},
        {"weight_g": 250, "price": 13.0, "variant": "mleta"},
    ]


def test_extract_woocommerce_variations_dedupes_true_duplicate_first_wins():
    # Same weight, no second axis at all — a genuine duplicate variation
    # (e.g. a site glitch) still collapses to the first-seen price.
    html = (
        '<form data-product_variations="'
        "[{&quot;attributes&quot;:{&quot;attribute_pa_hmotnost&quot;:&quot;250-g&quot;},"
        "&quot;display_price&quot;:11,&quot;display_regular_price&quot;:11},"
        "{&quot;attributes&quot;:{&quot;attribute_pa_hmotnost&quot;:&quot;250-g&quot;},"
        "&quot;display_price&quot;:13,&quot;display_regular_price&quot;:13}]"
        '"></form>'
    )
    _, tiers = scrape.extract_woocommerce_variations(_soup(html))
    assert tiers == [{"weight_g": 250, "price": 11.0}]


def test_extract_woocommerce_variations_skips_unparseable_weight():
    # No "hmotnost" (weight) attribute key on this variation at all.
    html = (
        '<form data-product_variations="'
        "[{&quot;attributes&quot;:{&quot;attribute_pa_sposob-prazenia&quot;:&quot;espresso&quot;},"
        "&quot;display_price&quot;:11}]"
        '"></form>'
    )
    _, tiers = scrape.extract_woocommerce_variations(_soup(html))
    assert tiers == []


def test_extract_woocommerce_variations_skips_zero_and_missing_price():
    html = (
        '<form data-product_variations="'
        "[{&quot;attributes&quot;:{&quot;attribute_pa_hmotnost&quot;:&quot;250-g&quot;},"
        "&quot;display_price&quot;:0},"
        "{&quot;attributes&quot;:{&quot;attribute_pa_hmotnost&quot;:&quot;1000-g&quot;}}]"
        '"></form>'
    )
    _, tiers = scrape.extract_woocommerce_variations(_soup(html))
    assert tiers == []


def test_extract_woocommerce_variations_non_list_json_returns_raw_and_empty_tiers():
    # Well-formed JSON that isn't a list (e.g. a bare number) must degrade
    # gracefully rather than raising when iterated.
    html = '<form data-product_variations="5"></form>'
    raw_json, tiers = scrape.extract_woocommerce_variations(_soup(html))
    assert raw_json == "5"
    assert tiers == []


def test_extract_woocommerce_variations_skips_non_dict_attributes():
    # A variation whose "attributes" value isn't an object must be skipped,
    # not raise, when .items() would otherwise be called on it.
    html = (
        '<form data-product_variations="'
        "[{&quot;attributes&quot;:&quot;x&quot;,&quot;display_price&quot;:11}]"
        '"></form>'
    )
    _, tiers = scrape.extract_woocommerce_variations(_soup(html))
    assert tiers == []


def test_extract_woocommerce_variations_skips_non_string_weight_slug():
    # A weight attribute value that isn't a string (e.g. a bare number) must
    # be skipped, not raise, when .replace() would otherwise be called on it.
    html = (
        '<form data-product_variations="'
        "[{&quot;attributes&quot;:{&quot;attribute_pa_hmotnost&quot;:1000},"
        "&quot;display_price&quot;:34}]"
        '"></form>'
    )
    _, tiers = scrape.extract_woocommerce_variations(_soup(html))
    assert tiers == []


def test_extract_woocommerce_variations_skips_boolean_price():
    # bool is an int subclass in Python — "display_price": true must not be
    # silently coerced into price 1.0.
    html = (
        '<form data-product_variations="'
        "[{&quot;attributes&quot;:{&quot;attribute_pa_hmotnost&quot;:&quot;250-g&quot;},"
        "&quot;display_price&quot;:true}]"
        '"></form>'
    )
    _, tiers = scrape.extract_woocommerce_variations(_soup(html))
    assert tiers == []


def test_woocommerce_extraction_helpers_accept_a_pre_parsed_soup():
    # issue #27: all four extraction helpers take an already-built
    # BeautifulSoup, not a raw HTML string, so process_roaster can parse a
    # product page once and reuse the soup across all of them. Passing a
    # BeautifulSoup object in directly (no HTML string in sight) is the
    # contract this locks in.
    soup = BeautifulSoup(WOO_VARIATIONS_HTML, scrape.HTML_PARSER)
    assert isinstance(scrape.extract_woocommerce_variations(soup), tuple)
    assert scrape.extract_woocommerce_origin(soup) is None or isinstance(scrape.extract_woocommerce_origin(soup), str)
    assert scrape.extract_woocommerce_roast_type(soup) in (None, "filter", "espresso")
    assert scrape.extract_woocommerce_weight(soup) is None or isinstance(scrape.extract_woocommerce_weight(soup), int)


# --- extract_shoptet_variations ----------------------------------------------


def _shoptet_html(records, product_id="1290"):
    """Build a minimal Shoptet product page: trackingScript data-products
    JSON + the add-to-cart form's hidden productId input."""
    payload = json.dumps({"products": records}, ensure_ascii=False).replace("'", "&#39;")
    return (
        f"<script id=\"trackingScript\" data-products='{payload}'></script>"
        f'<input type="hidden" name="productId" value="{product_id}" />'
    )


# The real shape from praziarenvelkezaluzie.sk (issue: LLM fabricated 15
# weight tiers for a 2-weight product): weight axis × grind axis, every
# grind of a weight at the same price, plus a related-products-carousel
# record under a different base_id.
SHOPTET_RECORDS = {
    "2406": {
        "base_id": 1290,
        "variant": "Hmotnosť: 500g, Zomlieť kávu?: Zrnková káva",
        "value": "17",
    },
    "2412": {
        "base_id": 1290,
        "variant": "Hmotnosť: 500g, Zomlieť kávu?: Mletá káva na zalievanie",
        "value": "17",
    },
    "2409": {
        "base_id": 1290,
        "variant": "Hmotnosť: 1000g, Zomlieť kávu?: Zrnková káva",
        "value": "34",
    },
    "2415": {
        "base_id": 1290,
        "variant": "Hmotnosť: 1000g, Zomlieť kávu?: Mletá káva na frenchpress",
        "value": "34",
    },
    "2316": {
        "base_id": 1284,
        "variant": "Hmotnosť: 500g, Zomlieť kávu?: Zrnková káva",
        "value": "15",
    },
}


def test_extract_shoptet_variations_keeps_only_whole_beans_per_weight():
    # Shoptet sites have a weight selector (500g, 1000g) and a grind-type
    # selector (Zrnková káva, Mletá káva...). The grind type is a configuration,
    # not a separate variant — all grind types share the same price and weight.
    # Only the "Zrnková káva" (whole beans) option should be recorded.
    raw, tiers = scrape.extract_shoptet_variations(_soup(_shoptet_html(SHOPTET_RECORDS)))
    assert raw  # non-empty, folded into the page hash
    # Only 2 tiers: 500g whole beans and 1000g whole beans
    assert sorted(tiers, key=lambda t: (t["weight_g"], t["variant"])) == [
        {"weight_g": 500, "price": 17.0, "variant": "Zrnková káva"},
        {"weight_g": 1000, "price": 34.0, "variant": "Zrnková káva"},
    ]


def test_extract_shoptet_variations_excludes_related_product_records():
    # The base_id 1284 record (€15) belongs to the related-products carousel,
    # not this page's product — it must appear in neither tiers nor the hash
    # projection.
    raw, tiers = scrape.extract_shoptet_variations(_soup(_shoptet_html(SHOPTET_RECORDS)))
    assert all(t["price"] != 15.0 for t in tiers)
    assert "15.0" not in raw


def test_extract_shoptet_variations_hash_projection_is_deterministic():
    # Same records in a different dict order must produce the identical
    # projection string, or the hash-gate would leak on serialization order.
    reordered = dict(reversed(list(SHOPTET_RECORDS.items())))
    raw_a, _ = scrape.extract_shoptet_variations(_soup(_shoptet_html(SHOPTET_RECORDS)))
    raw_b, _ = scrape.extract_shoptet_variations(_soup(_shoptet_html(reordered)))
    assert raw_a == raw_b


def test_extract_shoptet_variations_absent_returns_empty():
    raw, tiers = scrape.extract_shoptet_variations(_soup("<html><body>plain page</body></html>"))
    assert raw == ""
    assert tiers == []


def test_extract_shoptet_variations_missing_product_id_returns_empty():
    # Without the hidden productId input there's no way to tell this page's
    # own variant records from the related-products carousel — bail rather
    # than risk folding a related product's price into the tiers.
    payload = json.dumps({"products": SHOPTET_RECORDS})
    html = f"<script id=\"trackingScript\" data-products='{payload}'></script>"
    raw, tiers = scrape.extract_shoptet_variations(_soup(html))
    assert raw == ""
    assert tiers == []


def test_extract_shoptet_variations_malformed_json_returns_empty():
    html = (
        "<script id=\"trackingScript\" data-products='not json {'></script>"
        '<input type="hidden" name="productId" value="1290" />'
    )
    raw, tiers = scrape.extract_shoptet_variations(_soup(html))
    assert raw == ""
    assert tiers == []


def test_extract_shoptet_variations_skips_unparseable_weight_and_bad_price():
    records = {
        "1": {"base_id": 7, "variant": "Zomlieť kávu?: Zrnková káva", "value": "17"},
        "2": {"base_id": 7, "variant": "Hmotnosť: 500g", "value": "zero"},
        "3": {"base_id": 7, "variant": "Hmotnosť: 500g", "value": None},
        "4": {"base_id": 7, "variant": "Hmotnosť: 250g", "value": "9.5"},
    }
    _, tiers = scrape.extract_shoptet_variations(_soup(_shoptet_html(records, product_id="7")))
    assert tiers == [{"weight_g": 250, "price": 9.5}]


# --- is_coffee (non-coffee filtering) ---------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "Etiópia Yirgacheffe",
        "Colombia Huila Washed 250 g",
        "House Espresso Blend",
        "Kenya AA",
        "Kapsule Guatemala",  # capsules ARE coffee — must be kept
        "Ethiopia Cupping Score 87",  # "cupping" must not collide with "cup"
    ],
)
def test_is_coffee_keeps_real_coffees(name):
    assert scrape.is_coffee(name) is True


@pytest.mark.parametrize(
    "name",
    [
        "Darčeková poukážka 50 €",
        "Mesačné predplatné kávy",
        "Coffee subscription box",
        "Wilfa Uniform mlynček na kávu",
        "Hario V60 dripper",
        "Fellow Stagg kettle",
        "Aeropress Go",
        "Espresso tamper 58mm",
        "Gift card",
        "Brandované tričko",
        "Degustačný balíček, Spoznaj krajinu kávy",
        "Darčekový balíček pre kávičkárov",
        "Espresso cup 60ml – Grey",
        "ECM Classica PID II",
        "Bezzera Unica PID",
        "Rocket Appartamento TCA BLACK/COPER",
        "Eureka Mignon Silenzio 55, 16CR Chrome",
        "Timemore Chestnut C3S Max",
        "Prskaná kolekcia (s uškom)",
        "Modrá & Ružová kolekcia (bez uška)",
        "Štipec na kávový balík",
        "Baristický kurz BASIC",
        "Turn-N-Seal vakuová dóza 600 ml",
        "Hario nádoba nahrádna V60-02 600 ml",
        "Kávoláda GENTLEMAN 50g",
        "Červené víno s kávou 0,75l",
        "Alternatívny kávovar Hario V60 - set",
        "Vianočný punč cascara",
    ],
)
def test_is_coffee_drops_non_coffee(name):
    assert scrape.is_coffee(name) is False


# --- looks_like_product_link -------------------------------------------------


@pytest.mark.parametrize(
    "href",
    [
        "https://x.sk/kosik/",
        "https://x.sk/prihlasenie/",
        "https://x.sk/kontakt/",
        "https://x.sk/vop/",
        "https://x.sk/b2b/",
        "https://x.sk/sluzby/",
        "https://x.sk/news/colombia-el-rubi",
        # issue #37: category / brand / account / legal listings that used to
        # slip through and get cached as not_a_product (1,042 entries strong)
        "https://x.sk/kategoria/zrnkova-kava/",
        "https://x.sk/kategoria-produktu/espresso/",
        "https://x.sk/znacka/la-marzocco/",
        "https://x.sk/moj-ucet/",
        "https://x.sk/odstupenie-od-zmluvy/",
        "https://x.sk/clanky/ako-pripravit-v60/",
        "https://x.sk/collections/filter-coffee",  # Shopify collection listing
        "https://x.sk/velkoobchod/",
        "https://x.sk/prislusenstvo/salky/",
        "https://x.sk/",  # bare site root, never a product page
        "https://x.sk",
    ],
)
def test_looks_like_product_link_rejects_site_plumbing(href):
    assert scrape.looks_like_product_link(href) is False


@pytest.mark.parametrize(
    "href",
    [
        "https://x.sk/rwanda/",
        "https://x.sk/produkty/kolumbia-huila/",
        # issue #37: exact-segment matching must not reject product slugs
        # that merely CONTAIN a blocked word as a substring
        "https://x.sk/produkt/kava-info-brazil/",
        "https://x.sk/produkt/vychutnajte-si-etiopiu/",  # contains "chut"
        # Shopify nests real product pages under a collection
        "https://x.sk/collections/filter/products/ethiopia-sidamo",
    ],
)
def test_looks_like_product_link_accepts_plausible_products(href):
    assert scrape.looks_like_product_link(href) is True


# --- find_next_page_url (offline) -------------------------------------------


def test_find_next_page_url_rel_next_link():
    html = '<html><head><link rel="next" href="/shop?page=2"></head><body></body></html>'
    assert scrape.find_next_page_url(html, "https://x.sk/shop") == "https://x.sk/shop?page=2"


def test_find_next_page_url_anchor_class():
    html = '<a class="pagination__next" href="/shop/page/2">Next</a>'
    assert scrape.find_next_page_url(html, "https://x.sk/shop") == "https://x.sk/shop/page/2"


def test_find_next_page_url_slovak_text():
    html = '<div class="pager"><a href="?page=3">Ďalšia</a></div>'
    assert (
        scrape.find_next_page_url(html, "https://x.sk/shop?page=2")
        == "https://x.sk/shop?page=3"
    )


def test_find_next_page_url_none_when_absent():
    html = "<html><body><div class='product'>Coffee</div></body></html>"
    assert scrape.find_next_page_url(html, "https://x.sk/shop") is None


def test_find_next_page_url_ignores_self_reference():
    # A "next" link pointing back at the current URL must not create a loop.
    html = '<a rel="next" href="https://x.sk/shop">Next</a>'
    assert scrape.find_next_page_url(html, "https://x.sk/shop") is None


# --- normalize_roast_type ----------------------------------------------------


def test_normalize_roast_type_from_free_text():
    assert scrape.normalize_roast_type("Espresso") == "espresso"


def test_normalize_roast_type_filter_slovak_text():
    assert scrape.normalize_roast_type("Prekvapkávaná") == "filter"


def test_normalize_roast_type_pour_over_slovak_text():
    # "Zalievaná" (pour-over) and "kvapkovú" (drip) — common values in a
    # WooCommerce "recommended preparation method" attribute list.
    assert scrape.normalize_roast_type("Zalievaná") == "filter"
    assert scrape.normalize_roast_type("kvapkovú kávu") == "filter"


def test_normalize_roast_type_espresso_wins_in_multi_method_list():
    # "Espresso, Moka, Zalievaná" — a real WooCommerce recommended-method
    # list — must resolve to espresso, not filter.
    assert scrape.normalize_roast_type("Espresso, Moka, Zalievaná") == "espresso"


def test_normalize_roast_type_nespresso_not_swallowed_by_espresso():
    # "nespresso" contains "espresso" as a substring — the capsule check must
    # run before the espresso one or every capsule misclassifies as espresso.
    assert scrape.normalize_roast_type("Nespresso") == "nespresso"
    assert scrape.normalize_roast_type(None, None, "Ethiopia — Nespresso kompatibilné kapsule") == "nespresso"


def test_normalize_roast_type_capsule_keywords():
    assert scrape.normalize_roast_type("Kávové kapsule") == "nespresso"
    assert scrape.normalize_roast_type(None, None, "Brazil coffee capsules 10 ks") == "nespresso"


def test_normalize_roast_type_drip_bag():
    assert scrape.normalize_roast_type("Drip bag") == "drip-bag"
    assert scrape.normalize_roast_type(None, None, "Kolumbia dripbag 12 g") == "drip-bag"


def test_normalize_roast_type_dripper_equipment_is_not_drip_bag():
    # Bare "drip" must not match — "Hario V60 dripper" is brewing equipment.
    assert scrape.normalize_roast_type(None, None, "Hario V60 dripper") is None


def test_normalize_roast_type_category_hint_is_last_resort():
    # Only used when the page itself states nothing at all.
    assert scrape.normalize_roast_type(None, None, "Some Coffee", category_hint="filter") == "filter"
    assert scrape.normalize_roast_type(None, None, "Some Coffee", category_hint="nespresso") == "nespresso"
    assert scrape.normalize_roast_type(None, None, "Some Coffee", category_hint="drip-bag") == "drip-bag"


def test_normalize_roast_type_page_text_wins_over_category_hint():
    # A category hint must not override what the page actually states.
    assert scrape.normalize_roast_type("Espresso", None, None, category_hint="filter") == "espresso"


# --- extract_woocommerce_roast_type --------------------------------------------


def test_extract_woocommerce_roast_type_espresso_wins_in_multi_method_list():
    html = (
        '<tr class="woocommerce-product-attributes-item--attribute_pa_odporucany-sposob-pripravy">'
        '<td><span class="wd-term-name">Espresso</span><span class="wd-term-sep">, </span>'
        '<span class="wd-term-name">Zalievaná</span></td></tr>'
    )
    assert scrape.extract_woocommerce_roast_type(_soup(html)) == "espresso"


def test_extract_woocommerce_roast_type_filter_only():
    html = (
        '<tr class="woocommerce-product-attributes-item--attribute_pa_odporucany-sposob-pripravy">'
        '<td><span class="wd-term-name">Zalievaná</span></td></tr>'
    )
    assert scrape.extract_woocommerce_roast_type(_soup(html)) == "filter"


def test_extract_woocommerce_roast_type_ignores_unrelated_roast_degree_attribute():
    # "Stupeň praženia" (roast degree: light/medium/dark) is a DIFFERENT
    # attribute and must not be mistaken for the prep-method one.
    html = (
        '<tr class="woocommerce-product-attributes-item--attribute_pa_stupen-prazenia">'
        '<td><span class="wd-term-name">Tmavé</span></td></tr>'
    )
    assert scrape.extract_woocommerce_roast_type(_soup(html)) is None


def test_extract_woocommerce_roast_type_absent_returns_none():
    assert scrape.extract_woocommerce_roast_type(_soup("<html><body>nothing here</body></html>")) is None


# --- extract_woocommerce_weight -------------------------------------------------


def test_extract_woocommerce_weight_parses_core_field():
    html = (
        '<tr class="woocommerce-product-attributes-item woocommerce-product-attributes-item--weight">'
        "<td>0,06 kg</td></tr>"
    )
    assert scrape.extract_woocommerce_weight(_soup(html)) == 60


def test_extract_woocommerce_weight_ignores_custom_attribute_rows():
    # A custom attribute_pa_* row must not be mistaken for the core field.
    html = (
        '<tr class="woocommerce-product-attributes-item--attribute_pa_hmotnost">'
        "<td>250 g</td></tr>"
    )
    assert scrape.extract_woocommerce_weight(_soup(html)) is None


def test_extract_woocommerce_weight_absent_returns_none():
    assert scrape.extract_woocommerce_weight(_soup("<html><body>nothing here</body></html>")) is None


def test_normalize_roast_type_none_when_unstated():
    assert scrape.normalize_roast_type(None) is None
    assert scrape.normalize_roast_type("") is None


# --- normalize_roast_type fallback chain --------------------------------------


def test_normalize_roast_type_falls_back_to_process_text():
    assert scrape.normalize_roast_type(None, "filter roast", "Some Blend") == "filter"


def test_normalize_roast_type_falls_back_to_name():
    assert scrape.normalize_roast_type(None, None, "Espresso Blend") == "espresso"


def test_normalize_roast_type_raw_wins_over_process_and_name():
    assert scrape.normalize_roast_type("Espresso", "filter roast", "Filter Blend") == "espresso"


# --- normalize_origin ---------------------------------------------------------


def test_normalize_origin_translates_slovak_text():
    assert scrape.normalize_origin("Etiópia", "some name") == "Ethiopia"


def test_normalize_origin_falls_back_to_name_when_raw_missing():
    assert scrape.normalize_origin(None, "brazil • doce citrus") == "Brazil"


def test_normalize_origin_trusts_raw_over_name_when_both_present():
    # LLM origin wins as-is — no cross-check against a differing name mention.
    assert scrape.normalize_origin("Colombia", "brazil • doce citrus") == "Colombia"


# --- normalize_origin diacritic-insensitive matching --------------------------


def test_strip_diacritics_folds_accents_to_ascii():
    assert scrape.strip_diacritics("Salvádor") == "Salvador"
    assert scrape.strip_diacritics("Brazília") == "Brazilia"


def test_normalize_origin_matches_alias_despite_stray_accent_in_name():
    # "Salvádor" (stray accent) must still match the "salvador" alias.
    assert scrape.normalize_origin(None, "Salvádor El Borbollon") == "El Salvador"


def test_normalize_origin_matches_brasil_spelling():
    assert scrape.normalize_origin(None, "Brasil Santos Mogiana") == "Brazil"


def test_normalize_origin_matches_costarica_no_space():
    assert scrape.normalize_origin(None, "Costarica Palmichal Los Vindas") == "Costa Rica"


def test_normalize_origin_discards_unmatched_raw_text_instead_of_keeping_it_verbatim():
    # issue #14: raw LLM free text that matches no known country/blend signal
    # must not leak into the origin field verbatim — it would pollute the
    # site's origin filter dropdown with one-off values. Note this does NOT
    # fall back to scanning `name` — raw, once present, is still never
    # cross-checked against name (same invariant as before).
    assert scrape.normalize_origin("Fantasyland", None) is None
    assert scrape.normalize_origin("Fantasyland", "Ethiopia Sidamo") is None


def test_normalize_origin_unmatched_raw_still_falls_back_to_blend_keyword_in_raw():
    assert scrape.normalize_origin("Zmes rôznych krajín", None) == "Blend"


def test_normalize_origin_none_when_nothing_matches():
    assert scrape.normalize_origin(None, "Mystery Coffee") is None
    assert scrape.normalize_origin("Mystery Coffee", None) is None


def test_normalize_origin_none_for_whitespace_only_raw():
    # A blank-but-truthy raw origin must not survive as "" (schema requires minLength 1).
    assert scrape.normalize_origin("   ", "some name") is None


@pytest.mark.parametrize(
    "raw, expected",
    [
        # Unambiguous single-country regions heal to their country (issue #106)
        # rather than being stored raw as "Huila"/"Tolima"/"Blue Mountain".
        ("Huila", "Colombia"),
        ("Tolima", "Colombia"),
        ("Blue Mountain", "Jamaica"),
        # Czech spelling of a country name.
        ("Indonézie", "Indonesia"),
    ],
)
def test_normalize_origin_heals_region_and_foreign_country_aliases(raw, expected):
    assert scrape.normalize_origin(raw, None) == expected


def test_normalize_origin_svet_world_is_not_a_country():
    # "Svet" (Slovak/Czech for "world") pins no source country — stays null
    # rather than leaking into the origin dropdown (issue #106).
    assert scrape.normalize_origin("Svet", None) is None


# --- normalize_origin blend fallback ------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["House Blend", "Espresso zmes", "Ranná zmesi", "Morning Mix"],
)
def test_normalize_origin_blend_name_falls_back_to_blend(name):
    # A multi-origin blend rarely states one source country — "Blend" is the
    # honest origin here, not a gap to keep chasing.
    assert scrape.normalize_origin(None, name) == "Blend"


def test_normalize_origin_country_alias_wins_over_blend_keyword():
    assert scrape.normalize_origin(None, "Brazil Espresso Blend") == "Brazil"


@pytest.mark.parametrize(
    "name",
    ["Balíček VARIETY 3 x 200g", "Balíček DOBRODRUH 3x200g"],
)
def test_normalize_origin_variety_bundle_falls_back_to_blend(name):
    assert scrape.normalize_origin(None, name) == "Blend"


def test_normalize_origin_balicek_alone_without_multiplier_does_not_trigger_blend():
    # "balíček" alone is too generic (any packaged coffee) - only a
    # "balíček" + "N x" combination signals a multi-coffee variety pack.
    assert scrape.normalize_origin(None, "Espresso balíček 250g") is None


# --- extract_woocommerce_origin ------------------------------------------------


WOO_ORIGIN_ROW_HTML = (
    '<tr class="woocommerce-product-attributes-item woocommerce-product-attributes-item--attribute_pa_krajina-povodu">'
    '<th><span class="wd-attr-name">Krajina pôvodu</span></th>'
    '<td><span class="wd-term-name">Brazília</span><span class="wd-term-sep">, </span>'
    '<span class="wd-term-name">Honduras</span></td></tr>'
)


def test_extract_woocommerce_origin_multi_country_is_blend():
    assert scrape.extract_woocommerce_origin(_soup(WOO_ORIGIN_ROW_HTML)) == "Blend"


def test_extract_woocommerce_origin_single_country():
    html = (
        '<tr class="woocommerce-product-attributes-item--attribute_pa_krajina-povodu">'
        '<td><span class="wd-term-name">Etiópia</span></td></tr>'
    )
    assert scrape.extract_woocommerce_origin(_soup(html)) == "Ethiopia"


def test_extract_woocommerce_origin_absent_returns_none():
    assert scrape.extract_woocommerce_origin(_soup("<html><body>no attribute table</body></html>")) is None


def test_extract_woocommerce_origin_unrecognized_text_returns_none():
    html = (
        '<tr class="woocommerce-product-attributes-item--attribute_pa_krajina-povodu">'
        '<td><span class="wd-term-name">Neznáma planéta</span></td></tr>'
    )
    assert scrape.extract_woocommerce_origin(_soup(html)) is None


# --- normalize_product --------------------------------------------------------


def test_normalize_product_multi_weight_packaging():
    raw = {
        "name": "RWANDA - Kigali",
        "origin": "Rwanda",
        "process": "washed",
        "roast_type": "Filter",
        "packaging": [
            {"weight": "1000 g", "price": "44 €"},
            {"weight": "250 g", "price": "12,50 €"},
        ],
    }
    result = scrape.normalize_product(raw, "https://x.sk/rwanda/", "2026-07-04")
    assert result["name"] == "RWANDA - Kigali"
    assert result["roast_type"] == "filter"
    assert result["status"] == "ok"
    assert result["last_seen"] == "2026-07-04"
    assert result["packaging"] == [
        {"weight_g": 1000, "price": 44.0},
        {"weight_g": 250, "price": 12.5},
    ]


def test_normalize_product_keeps_distinct_same_weight_tiers_by_variant():
    # Real-world shape (coffeeart.me): the same weight sold whole-bean and
    # ground at different prices — both tiers must survive, each carrying
    # its own variant label, not collide into one.
    raw = {
        "name": "9 Grams Coffee Ethiopia Yirgacheffe Grade 2 CO2 Decaf washed",
        "origin": "Ethiopia",
        "roast_type": "Filter",
        "packaging": [
            {"weight": "1000 g", "price": "34 €", "variant": "Whole bean"},
            {"weight": "1000 g", "price": "48 €", "variant": "Ground"},
        ],
    }
    result = scrape.normalize_product(raw, "https://x.sk/decaf/", "2026-07-04")
    assert result["status"] == "ok"
    assert result["packaging"] == [
        {"weight_g": 1000, "price": 34.0, "variant": "Whole bean"},
        {"weight_g": 1000, "price": 48.0, "variant": "Ground"},
    ]


def test_normalize_product_strips_and_omits_blank_variant():
    raw = {
        "name": "Kenya AA",
        "origin": "Kenya",
        "roast_type": "Filter",
        "packaging": [
            {"weight": "250 g", "price": "10 €", "variant": "  Whole bean  "},
            {"weight": "500 g", "price": "18 €", "variant": ""},
            {"weight": "1000 g", "price": "32 €", "variant": "   "},
        ],
    }
    result = scrape.normalize_product(raw, "https://x.sk/kenya/", "2026-07-04")
    assert result["packaging"] == [
        {"weight_g": 250, "price": 10.0, "variant": "Whole bean"},
        {"weight_g": 500, "price": 18.0},
        {"weight_g": 1000, "price": 32.0},
    ]


def test_normalize_product_falls_back_to_weight_in_name():
    raw = {"name": "Colombia Huila 200 g", "packaging": [{"weight": None, "price": "14,50 €"}]}
    result = scrape.normalize_product(raw, "https://x.sk/colombia/", "2026-07-04")
    assert result["packaging"] == [{"weight_g": 200, "price": 14.50}]


def test_normalize_product_drops_tiers_with_no_price():
    raw = {
        "name": "Kenya AA",
        "packaging": [{"weight": "250 g", "price": "Vypredané"}, {"weight": "1 kg", "price": "30 €"}],
    }
    result = scrape.normalize_product(raw, "https://x.sk/kenya/", "2026-07-04")
    assert result["packaging"] == [{"weight_g": 1000, "price": 30.0}]


def test_normalize_product_none_when_no_valid_packaging():
    raw = {"name": "Kenya AA", "packaging": [{"weight": "250 g", "price": "Vypredané"}]}
    assert scrape.normalize_product(raw, "https://x.sk/kenya/", "2026-07-04") is None


def test_normalize_product_none_for_non_coffee_name():
    raw = {"name": "Darčeková poukážka", "packaging": [{"price": "20 €"}]}
    assert scrape.normalize_product(raw, "https://x.sk/gift/", "2026-07-04") is None


def test_normalize_product_none_when_claude_declined():
    assert scrape.normalize_product(None, "https://x.sk/kava/", "2026-07-04") is None


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
    result = scrape.normalize_product(raw, "https://x.sk/mexico/", "2026-07-08", hints=scrape.Hints(variation_tiers=tiers))
    assert result["status"] == "ok"
    assert result["packaging"] == tiers


def test_normalize_product_uses_roast_type_hint_when_page_states_nothing():
    # Site (e.g. a Shopify collection) never states roast_type on the
    # product page itself — the discovery-category hint fills it in.
    raw = {
        "name": "Some Coffee",
        "origin": "Brazil",
        "packaging": [{"weight": "250 g", "price": "12,00 €"}],
    }
    result = scrape.normalize_product(
        raw, "https://x.sk/some-coffee/", "2026-07-08", hints=scrape.Hints(category_roast_type="espresso")
    )
    assert result["status"] == "ok"
    assert result["roast_type"] == "espresso"


def test_normalize_product_origin_hint_wins_over_llm_guess():
    # LLM left origin null (multi-country list confused it) — the
    # deterministic WooCommerce attribute-row hint fills it in.
    raw = {
        "name": "BUDÍČEK",
        "roast_type": "Espresso",
        "packaging": [{"weight": "250 g", "price": "8,00 €"}],
    }
    result = scrape.normalize_product(
        raw, "https://x.sk/budicek/", "2026-07-08", hints=scrape.Hints(origin="Blend")
    )
    assert result["status"] == "ok"
    assert result["origin"] == "Blend"


def test_normalize_product_unrecognized_origin_hint_falls_through_to_llm():
    # A hint source must never store raw text verbatim (issue #106): an
    # unrecognized hint origin is discarded and the LLM's own (recognized)
    # origin is used instead, rather than "Fantasyland" reaching products.yaml.
    raw = {
        "name": "Kolumbia Excelso",
        "origin": "Colombia",
        "roast_type": "Filter",
        "packaging": [{"weight": "250 g", "price": "10,00 €"}],
    }
    result = scrape.normalize_product(
        raw, "https://x.sk/kolumbia/", "2026-07-13", hints=scrape.Hints(origin="Fantasyland")
    )
    assert result["origin"] == "Colombia"


def test_normalize_product_roast_type_attribute_hint_wins_over_llm_guess():
    # LLM left roast_type null — the deterministic WooCommerce attribute-row
    # hint fills it in, overriding whatever the LLM would otherwise guess.
    raw = {
        "name": "Kolumbia Excelso",
        "origin": "Colombia",
        "packaging": [{"weight": "250 g", "price": "10,00 €"}],
    }
    result = scrape.normalize_product(
        raw, "https://x.sk/kolumbia/", "2026-07-08", hints=scrape.Hints(roast_type="filter")
    )
    assert result["status"] == "ok"
    assert result["roast_type"] == "filter"


def test_normalize_product_weight_hint_fills_single_tier_gap():
    # Neither the tier text nor the name states a weight — the WooCommerce
    # core Weight field fills it in as a last resort.
    raw = {
        "name": "SweetDrip x Kenya",
        "origin": "Kenya",
        "roast_type": "Filter",
        "packaging": [{"price": "9,99 €", "weight": None}],
    }
    result = scrape.normalize_product(raw, "https://x.sk/sweetdrip/", "2026-07-08", hints=scrape.Hints(weight_g=60))
    assert result["status"] == "ok"
    assert result["packaging"] == [{"weight_g": 60, "price": 9.99}]


def test_normalize_product_name_weight_wins_over_weight_hint():
    # An explicit weight in the name is more specific than the generic
    # core-field fallback — it must not be overridden.
    raw = {
        "name": "Colombia Huila 200 g",
        "origin": "Colombia",
        "roast_type": "Filter",
        "packaging": [{"price": "14,50 €", "weight": None}],
    }
    result = scrape.normalize_product(raw, "https://x.sk/colombia/", "2026-07-08", hints=scrape.Hints(weight_g=999))
    assert result["packaging"] == [{"weight_g": 200, "price": 14.50}]


def test_normalize_product_variation_tiers_still_requires_a_name():
    # variation_tiers alone doesn't make a page a product — the model declining
    # (raw=None) or a non-coffee name must still return None.
    tiers = [{"weight_g": 250, "price": 11.0}]
    assert scrape.normalize_product(None, "https://x.sk/mexico/", "2026-07-08", hints=scrape.Hints(variation_tiers=tiers)) is None
    raw = {"name": "Darčeková poukážka", "packaging": []}
    assert scrape.normalize_product(raw, "https://x.sk/gift/", "2026-07-08", hints=scrape.Hints(variation_tiers=tiers)) is None


def test_normalize_product_variation_tiers_same_price_is_not_a_collision():
    # The price_collision heuristic exists to catch the LLM hallucinating the
    # same price across tiers — it doesn't apply to variation_tiers, where
    # WooCommerce's own JSON can legitimately price two weights the same.
    raw = {"name": "Guatemala Huehuetenango", "origin": "Guatemala", "roast_type": "filter"}
    tiers = [{"weight_g": 250, "price": 12.0}, {"weight_g": 1000, "price": 12.0}]
    result = scrape.normalize_product(raw, "https://x.sk/guatemala/", "2026-07-08", hints=scrape.Hints(variation_tiers=tiers))
    assert result["status"] == "ok"
    assert result["packaging"] == tiers


# --- normalize_product: blend flag + composition (issue #91) -------------------


def test_normalize_product_stamps_blend_on_origin_sentinel():
    # Existing keyword path ("zmes" in the name) must now also carry the
    # explicit flag, plus the normalized composition when the model lists it.
    raw = {
        "name": "Ranná zmes",
        "roast_type": "Espresso",
        "blend": True,
        "blend_origins": ["Brazília", "Honduras", "India"],
        "packaging": [{"weight": "250 g", "price": "12,00 €"}],
    }
    result = scrape.normalize_product(raw, "https://x.sk/ranna-zmes/", "2026-07-13")
    assert result["status"] == "ok"
    assert result["origin"] == "Blend"
    assert result["blend"] is True
    assert result["blend_origins"] == ["Brazil", "Honduras", "India"]


def test_normalize_product_llm_blend_flag_heals_missing_origin():
    # A blend recognized only from description text (no keyword in the
    # name, no origin attribute) used to land origin: null → incomplete.
    raw = {
        "name": "Morning Ritual",
        "roast_type": "Espresso",
        "blend": True,
        "packaging": [{"weight": "250 g", "price": "12,00 €"}],
    }
    result = scrape.normalize_product(raw, "https://x.sk/morning-ritual/", "2026-07-13")
    assert result["status"] == "ok"
    assert result["origin"] == "Blend"
    assert result["blend"] is True
    assert "blend_origins" not in result  # page listed no components


def test_normalize_product_two_component_countries_imply_blend_without_flag():
    raw = {
        "name": "Duo",
        "roast_type": "Filter",
        "blend_origins": ["Brazília", "Nikaragua"],
        "packaging": [{"weight": "250 g", "price": "12,00 €"}],
    }
    result = scrape.normalize_product(raw, "https://x.sk/duo/", "2026-07-13")
    assert result["origin"] == "Blend"
    assert result["blend_origins"] == ["Brazil", "Nicaragua"]


def test_normalize_product_single_origin_gets_no_blend_keys():
    raw = {
        "name": "Colombia Huila",
        "origin": "Colombia",
        "roast_type": "Filter",
        "blend": False,
        "packaging": [{"weight": "250 g", "price": "12,00 €"}],
    }
    result = scrape.normalize_product(raw, "https://x.sk/colombia/", "2026-07-13")
    assert result["origin"] == "Colombia"
    assert "blend" not in result
    assert "blend_origins" not in result


def test_normalize_product_stated_country_wins_over_llm_blend_opinion():
    # A stated origin (or WooCommerce hint) always beats the model's blend
    # opinion — blend only ever FILLS a missing origin, never overrides.
    raw = {
        "name": "Fazenda Santa Ines",
        "origin": "Brazília",
        "roast_type": "Espresso",
        "blend": True,  # model misfire
        "blend_origins": ["Brazília"],
        "packaging": [{"weight": "250 g", "price": "12,00 €"}],
    }
    result = scrape.normalize_product(raw, "https://x.sk/fazenda/", "2026-07-13")
    assert result["origin"] == "Brazil"
    assert "blend" not in result
    assert "blend_origins" not in result


def test_normalize_product_single_listed_component_does_not_imply_blend():
    # One known component + no flag + no keywords is not enough evidence —
    # the entry stays incomplete on origin rather than guessing Blend.
    raw = {
        "name": "Mystery Series No. 4",
        "roast_type": "Filter",
        "blend_origins": ["Brazília"],
        "packaging": [{"weight": "250 g", "price": "12,00 €"}],
    }
    result = scrape.normalize_product(raw, "https://x.sk/mystery-4/", "2026-07-13")
    assert result["status"] == "incomplete"
    assert "origin" in result["missing_fields"]
    assert "blend" not in result


def test_normalize_blend_origins_dedupes_and_drops_unmatchable():
    assert scrape.normalize_blend_origins(
        ["Brazília", "brasil", "Yirgacheffe region", "Nikaragua", 42]
    ) == ["Brazil", "Nicaragua"]
    assert scrape.normalize_blend_origins(None) == []
    assert scrape.normalize_blend_origins("Brazil") == []


# --- normalize_product: incomplete status ------------------------------------


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


def test_normalize_product_incomplete_when_price_decreases_with_weight():
    # Real bug: a page shows only its cheapest tier's price as visible text
    # (e.g. an Upgates "od X€" from-price) and the model fabricates a lower
    # price for a larger tier — a smaller package costing more than a
    # larger one is never legitimate, so the guessed price is untrustworthy.
    raw = {
        "name": "Colombia Ombligon sugarcane decaf",
        "origin": "Colombia",
        "roast_type": "filter",
        "packaging": [
            {"weight": "250 g", "price": "15,90 €"},
            {"weight": "500 g", "price": "8,90 €"},
        ],
    }
    result = scrape.normalize_product(raw, "https://x.sk/ombligon/", "2026-07-09")
    assert result["status"] == "incomplete"
    assert "price" in result["missing_fields"]
    assert len(result["packaging"]) == 2


def test_normalize_product_ok_when_price_increases_with_weight():
    raw = {
        "name": "Colombia Huila",
        "origin": "Colombia",
        "roast_type": "filter",
        "packaging": [
            {"weight": "250 g", "price": "8,90 €"},
            {"weight": "500 g", "price": "15,90 €"},
        ],
    }
    result = scrape.normalize_product(raw, "https://x.sk/huila/", "2026-07-09")
    assert result["status"] == "ok"


def test_normalize_product_price_decreasing_skipped_for_variation_tiers():
    # Deterministic WooCommerce/Shopify data is trusted as-is even if a
    # smaller tier is genuinely priced higher (e.g. a promo) — this
    # heuristic only guards against LLM guesswork.
    raw = {"name": "Some Coffee", "origin": "Brazil", "roast_type": "filter", "packaging": []}
    tiers = [{"weight_g": 250, "price": 15.90}, {"weight_g": 500, "price": 8.90}]
    result = scrape.normalize_product(raw, "https://x.sk/some/", "2026-07-09", hints=scrape.Hints(variation_tiers=tiers))
    assert result["status"] == "ok"


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


# --- normalize_product: schema-invalid raw shapes (final-review regressions) --


def test_normalize_product_drops_tier_with_zero_price():
    # "0,00 €" parses to 0.0, not None — must be treated as no price, same as
    # an unparseable price, or an ok-status 0.0 would fail the schema's
    # exclusiveMinimum: 0.
    raw = {"name": "Kenya AA", "packaging": [{"weight": "250 g", "price": "0,00 €"}]}
    assert scrape.normalize_product(raw, "https://x.sk/kenya/", "2026-07-04") is None


def test_normalize_product_nulls_zero_weight_and_marks_incomplete():
    raw = {
        "name": "Kenya AA",
        "origin": "Kenya",
        "roast_type": "filter",
        "packaging": [{"weight": "0 g", "price": "12,00 €"}],
    }
    result = scrape.normalize_product(raw, "https://x.sk/kenya/", "2026-07-04")
    assert result["packaging"][0]["weight_g"] is None
    assert result["status"] == "incomplete"
    assert "weight_g" in result["missing_fields"]
    result["page_hash"] = "deadbeef"
    scrape.validate_entry(result)


def test_normalize_product_incomplete_when_origin_whitespace_only():
    raw = {
        "name": "House Blend",
        "origin": "   ",
        "roast_type": "filter",
        "packaging": [{"weight": "250 g", "price": "12,00 €"}],
    }
    result = scrape.normalize_product(raw, "https://x.sk/house-blend/", "2026-07-04")
    assert result["status"] == "incomplete"
    assert "origin" in result["missing_fields"]
    assert result["origin"] is None
    result["page_hash"] = "deadbeef"
    scrape.validate_entry(result)


def test_normalize_product_incomplete_on_weight_read_as_price():
    # Real bug seen in production data ("Kostarika BACH"): the model read each
    # tier's weight number as its price. price_collision alone misses this
    # because the prices ARE distinct across tiers (200.0, 500.0).
    raw = {
        "name": "Kostarika BACH",
        "origin": "Costa Rica",
        "roast_type": "filter",
        "packaging": [
            {"weight": "200 g", "price": "200 €"},
            {"weight": "500 g", "price": "500 €"},
        ],
    }
    result = scrape.normalize_product(raw, "https://x.sk/kostarika-bach/", "2026-07-04")
    assert result["status"] == "incomplete"
    assert "price" in result["missing_fields"]
    assert len(result["packaging"]) == 2
    result["page_hash"] = "deadbeef"
    scrape.validate_entry(result)


def test_normalize_product_ok_does_not_false_positive_on_weight_as_price():
    # Legitimate prices that don't equal their own tier's weight must not trip
    # the new weight_as_price signal.
    raw = {
        "name": "Rwanda Kigali",
        "origin": "Rwanda",
        "roast_type": "filter",
        "packaging": [
            {"weight": "250 g", "price": "12,50 €"},
            {"weight": "1000 g", "price": "40,00 €"},
        ],
    }
    result = scrape.normalize_product(raw, "https://x.sk/rwanda/", "2026-07-04")
    assert result["status"] == "ok"
    result["page_hash"] = "deadbeef"
    scrape.validate_entry(result)


# --- normalize_product: blend flag + composition (issue #91) -----------------


def test_normalize_product_llm_blend_with_composition():
    # Model flags the blend and lists its source countries — origin stays the
    # canonical "Blend" filter key, composition is carried as display data.
    raw = {
        "name": "Espresso Zmes",
        "origin": "Blend",
        "roast_type": "espresso",
        "blend": True,
        "blend_origins": ["Brazília", "Honduras", "India", "Nikaragua"],
        "packaging": [{"weight": "250 g", "price": "12,00 €"}],
    }
    result = scrape.normalize_product(raw, "https://x.sk/espresso-zmes/", "2026-07-13")
    assert result["status"] == "ok"
    assert result["origin"] == "Blend"
    assert result["blend"] is True
    # Slovak aliases normalized to canonical English country names.
    assert result["blend_origins"] == ["Brazil", "Honduras", "India", "Nicaragua"]
    result["page_hash"] = "deadbeef"
    scrape.validate_entry(result)


def test_normalize_product_keyword_fallback_sets_blend_without_llm_flag():
    # No `blend` flag from the model, but the name reads as a blend — the
    # existing "Blend" origin heuristic still marks it, composition just absent.
    raw = {
        "name": "House Blend",
        "roast_type": "espresso",
        "packaging": [{"weight": "250 g", "price": "10,00 €"}],
    }
    result = scrape.normalize_product(raw, "https://x.sk/house-blend/", "2026-07-13")
    assert result["origin"] == "Blend"
    assert result["blend"] is True
    assert "blend_origins" not in result


def test_normalize_product_blend_origins_drops_unmatchable_and_dedupes():
    raw = {
        "name": "Zmes",
        "origin": "Blend",
        "roast_type": "filter",
        "blend": True,
        "blend_origins": ["Brazília", "Fantasyland", "brazil", "Etiópia"],
        "packaging": [{"weight": "250 g", "price": "11,00 €"}],
    }
    result = scrape.normalize_product(raw, "https://x.sk/zmes/", "2026-07-13")
    # "Fantasyland" dropped (never stored raw, issue #14); "brazil" deduped.
    assert result["blend_origins"] == ["Brazil", "Ethiopia"]


def test_normalize_product_blend_flag_without_composition_uses_sentinel_origin():
    # Model flags a blend but states no single country and no composition — the
    # honest origin is the "Blend" sentinel rather than null.
    raw = {
        "name": "Mystery Espresso",
        "roast_type": "espresso",
        "blend": True,
        "packaging": [{"weight": "250 g", "price": "9,00 €"}],
    }
    result = scrape.normalize_product(raw, "https://x.sk/mystery/", "2026-07-13")
    assert result["origin"] == "Blend"
    assert result["blend"] is True
    assert "blend_origins" not in result


def test_normalize_product_single_country_wins_over_blend_flag():
    # A blend of lots from ONE country (e.g. "Brazil espresso blend") is filed
    # under that country — a resolved single origin beats the blend flag, so
    # neither the sentinel origin nor the blend field is applied.
    raw = {
        "name": "Brazil Espresso Blend",
        "origin": "Brazil",
        "roast_type": "espresso",
        "blend": True,
        "blend_origins": ["Brazil"],
        "packaging": [{"weight": "250 g", "price": "10,00 €"}],
    }
    result = scrape.normalize_product(raw, "https://x.sk/brazil-blend/", "2026-07-13")
    assert result["origin"] == "Brazil"
    assert "blend" not in result
    assert "blend_origins" not in result


def test_normalize_product_single_origin_has_no_blend_fields():
    raw = {
        "name": "Kenya AA",
        "origin": "Kenya",
        "roast_type": "filter",
        "packaging": [{"weight": "250 g", "price": "13,00 €"}],
    }
    result = scrape.normalize_product(raw, "https://x.sk/kenya/", "2026-07-13")
    assert "blend" not in result
    assert "blend_origins" not in result


# --- normalize_products (roast-type-axis packaging split) --------------------


def test_normalize_products_splits_by_distinct_tier_roast_type():
    # Suca Roastery (Upgates platform): a page's "Praženie a balenie" widget
    # crosses roast type with weight as two independent selector axes — the
    # LLM correctly reports all 4 tiers, tagged per-tier.
    raw = {
        "name": "Colombia Jesus Barahona Buenavista",
        "origin": "Colombia",
        "process": "natural",
        "packaging": [
            {"weight": "250 g", "price": "11 €", "roast_type": "Espresso"},
            {"weight": "500 g", "price": "18 €", "roast_type": "Espresso"},
            {"weight": "250 g", "price": "10,50 €", "roast_type": "Filter"},
            {"weight": "500 g", "price": "17,50 €", "roast_type": "Filter"},
        ],
    }
    result = scrape.normalize_products(raw, "https://x.sk/colombia/", "2026-07-04")
    assert len(result) == 2
    by_roast_type = {e["roast_type"]: e for e in result}
    assert set(by_roast_type) == {"filter", "espresso"}
    assert by_roast_type["espresso"]["packaging"] == [
        {"weight_g": 250, "price": 11.0},
        {"weight_g": 500, "price": 18.0},
    ]
    assert by_roast_type["filter"]["packaging"] == [
        {"weight_g": 250, "price": 10.5},
        {"weight_g": 500, "price": 17.5},
    ]
    assert by_roast_type["espresso"]["status"] == "ok"
    assert by_roast_type["filter"]["status"] == "ok"


def test_normalize_products_variant_survives_roast_type_split():
    # A tier's `variant` label must come through untouched when
    # normalize_products() regroups raw packaging tiers by roast_type and
    # delegates to normalize_product() per group.
    raw = {
        "name": "Colombia Jesus Barahona Buenavista",
        "origin": "Colombia",
        "process": "natural",
        "packaging": [
            {"weight": "250 g", "price": "11 €", "roast_type": "Espresso", "variant": "Whole bean"},
            {"weight": "250 g", "price": "13 €", "roast_type": "Espresso", "variant": "Ground"},
            {"weight": "250 g", "price": "10,50 €", "roast_type": "Filter"},
        ],
    }
    result = scrape.normalize_products(raw, "https://x.sk/colombia/", "2026-07-04")
    by_roast_type = {e["roast_type"]: e for e in result}
    assert by_roast_type["espresso"]["packaging"] == [
        {"weight_g": 250, "price": 11.0, "variant": "Whole bean"},
        {"weight_g": 250, "price": 13.0, "variant": "Ground"},
    ]
    assert by_roast_type["filter"]["packaging"] == [{"weight_g": 250, "price": 10.5}]


def test_normalize_products_no_split_when_all_tiers_share_one_roast_type():
    raw = {
        "name": "Kenya Endebess natural",
        "origin": "Kenya",
        "packaging": [
            {"weight": "250 g", "price": "9,80 €", "roast_type": "Filter"},
            {"weight": "500 g", "price": "11,50 €", "roast_type": "Filter"},
        ],
    }
    result = scrape.normalize_products(raw, "https://x.sk/kenya/", "2026-07-04")
    assert len(result) == 1
    assert result[0]["roast_type"] == "filter"
    assert result[0]["packaging"] == [
        {"weight_g": 250, "price": 9.80},
        {"weight_g": 500, "price": 11.50},
    ]


def test_normalize_products_no_split_when_tiers_carry_no_roast_type_tags():
    # Exact fixture from test_normalize_product_multi_weight_packaging — the
    # common (no per-tier tagging at all) path must be byte-for-byte
    # unaffected by normalize_products() existing.
    raw = {
        "name": "RWANDA - Kigali",
        "origin": "Rwanda",
        "process": "washed",
        "roast_type": "Filter",
        "packaging": [
            {"weight": "1000 g", "price": "44 €"},
            {"weight": "250 g", "price": "12,50 €"},
        ],
    }
    direct = scrape.normalize_product(raw, "https://x.sk/rwanda/", "2026-07-04")
    result = scrape.normalize_products(raw, "https://x.sk/rwanda/", "2026-07-04")
    assert result == [direct]


def test_normalize_products_drops_untagged_tier_when_split_triggered():
    raw = {
        "name": "Colombia Test",
        "origin": "Colombia",
        "packaging": [
            {"weight": "250 g", "price": "11 €", "roast_type": "Filter"},
            {"weight": "500 g", "price": "18 €", "roast_type": "Espresso"},
            {"weight": "1000 g", "price": "30 €"},  # no roast_type tag at all
        ],
    }
    result = scrape.normalize_products(raw, "https://x.sk/colombia/", "2026-07-04")
    assert len(result) == 2
    all_weights = {t["weight_g"] for e in result for t in e["packaging"]}
    assert all_weights == {250, 500}  # the untagged 1000g tier is in neither


def test_normalize_products_heuristics_scoped_per_split_group():
    # Reproduces the live production bug shape: each roast type's own tiers
    # are internally consistent (price rises with weight), even though the
    # SAME price repeats across the two roast types at each weight — a
    # whole-list check (pre-split) would flag this; grouped, neither should.
    raw = {
        "name": "Colombia Jesus Barahona Buenavista",
        "origin": "Colombia",
        "process": "natural",
        "packaging": [
            {"weight": "250 g", "price": "11 €", "roast_type": "Filter"},
            {"weight": "500 g", "price": "18 €", "roast_type": "Filter"},
            {"weight": "250 g", "price": "11 €", "roast_type": "Espresso"},
            {"weight": "500 g", "price": "18 €", "roast_type": "Espresso"},
        ],
    }
    result = scrape.normalize_products(raw, "https://x.sk/colombia/", "2026-07-04")
    assert len(result) == 2
    assert all(e["status"] == "ok" for e in result)


def test_normalize_products_returns_empty_list_when_claude_declined():
    assert scrape.normalize_products(None, "https://x.sk/kava/", "2026-07-04") == []


def test_normalize_products_variation_tiers_bypasses_split_logic():
    # variation_tiers (WooCommerce/Shopify structured data) takes precedence
    # and has no per-tier roast_type concept — splitting stays out of scope
    # for that path even if the raw LLM packaging looks splittable.
    raw = {
        "name": "Colombia Test",
        "origin": "Colombia",
        "roast_type": "Filter",
        "packaging": [
            {"weight": "250 g", "price": "11 €", "roast_type": "Filter"},
            {"weight": "250 g", "price": "11 €", "roast_type": "Espresso"},
        ],
    }
    variation_tiers = [{"weight_g": 250, "price": 11.0}]
    result = scrape.normalize_products(raw, "https://x.sk/colombia/", "2026-07-04", scrape.Hints(variation_tiers=variation_tiers))
    assert len(result) == 1


# --- extract_product (mocked OpenRouter/OpenAI client) -----------------------


def test_extract_product_returns_tool_input():
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = fake_completion(
        [fake_tool_call("extract_product", {"name": "Rwanda", "packaging": [{"price": "12,50 €"}]})]
    )

    result = scrape.extract_product(fake_client, "https://x.sk/rwanda/", "markdown text")
    assert result == {"name": "Rwanda", "packaging": [{"price": "12,50 €"}]}


def test_extract_product_returns_none_when_model_explicitly_declines():
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = fake_completion(
        content="This is a category listing page, not a single coffee product."
    )

    result = scrape.extract_product(fake_client, "https://x.sk/kava/", "markdown text")
    assert result is None


def test_extract_product_raises_on_empty_response():
    # No tool call AND no textual decline reason — ambiguous (could be
    # truncation, a safety refusal, model laziness), so this must NOT be
    # treated as a confident "not a product" the way a real decline is.
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = fake_completion()

    with pytest.raises(scrape.ExtractionFailed):
        scrape.extract_product(fake_client, "https://x.sk/kava/", "markdown text")


def test_extract_product_raises_on_truncated_response():
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = fake_completion(finish_reason="length")

    with pytest.raises(scrape.ExtractionFailed):
        scrape.extract_product(fake_client, "https://x.sk/kava/", "markdown text")


def test_extract_product_raises_on_malformed_tool_call_json():
    fake_client = MagicMock()
    bad_call = MagicMock()
    bad_call.function.name = "extract_product"
    bad_call.function.arguments = "{not valid json"
    fake_client.chat.completions.create.return_value = fake_completion([bad_call])

    with pytest.raises(scrape.ExtractionFailed):
        scrape.extract_product(fake_client, "https://x.sk/kava/", "markdown text")


def test_extract_product_truncates_markdown_before_sending():
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = fake_completion(
        [fake_tool_call("extract_product", {"name": "Rwanda", "packaging": [{"price": "12,50 €"}]})]
    )
    huge_markdown = "x" * (scrape.MAX_MARKDOWN_CHARS + 5000)

    scrape.extract_product(fake_client, "https://x.sk/rwanda/", huge_markdown)

    sent_messages = fake_client.chat.completions.create.call_args.kwargs["messages"]
    user_content = sent_messages[-1]["content"]
    assert len(user_content) <= scrape.MAX_MARKDOWN_CHARS + len("<page_content>\n\n</page_content>")


def test_extract_product_omits_url_and_uses_system_message():
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = fake_completion(
        [fake_tool_call("extract_product", {"name": "Rwanda", "packaging": [{"price": "12,50 €"}]})]
    )

    scrape.extract_product(fake_client, "https://x.sk/rwanda-250g/", "markdown text")

    kwargs = fake_client.chat.completions.create.call_args.kwargs
    assert kwargs["temperature"] == 0
    messages = kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "https://x.sk/rwanda-250g/" not in messages[0]["content"]
    assert "https://x.sk/rwanda-250g/" not in messages[1]["content"]
    assert "<page_content>" in messages[1]["content"]


def test_extract_product_retries_on_transient_api_error(monkeypatch):
    import httpx

    monkeypatch.setattr(scrape.time, "sleep", lambda *_: None)
    fake_client = MagicMock()
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    fake_client.chat.completions.create.side_effect = [
        openai.APIConnectionError(request=request),
        fake_completion([fake_tool_call("extract_product", {"name": "Rwanda", "packaging": [{"price": "12,50 €"}]})]),
    ]

    result = scrape.extract_product(fake_client, "https://x.sk/rwanda/", "markdown text")
    assert result == {"name": "Rwanda", "packaging": [{"price": "12,50 €"}]}
    assert fake_client.chat.completions.create.call_count == 2


def test_extract_product_raises_after_exhausting_retries_on_every_model(monkeypatch):
    import httpx

    monkeypatch.setattr(scrape.time, "sleep", lambda *_: None)
    fake_client = MagicMock()
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    fake_client.chat.completions.create.side_effect = openai.APIConnectionError(request=request)

    with pytest.raises(scrape.ExtractionFailed):
        scrape.extract_product(fake_client, "https://x.sk/rwanda/", "markdown text")
    # issue #42: a transient error burns its full retry budget on each
    # configured model before the call is given up on entirely.
    assert fake_client.chat.completions.create.call_count == scrape.EXTRACT_RETRY_ATTEMPTS * len(
        scrape.MODELS
    )


# --- model fallback (issue #42) -------------------------------------------------


def _model_error(cls):
    import httpx

    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    response = httpx.Response(
        404 if cls is openai.NotFoundError else 400, request=request, json={"error": "nope"}
    )
    return cls("model error", response=response, body=None)


def test_extract_product_falls_back_to_next_model_on_model_level_error(monkeypatch, capsys):
    monkeypatch.setattr(scrape, "MODELS", ("dead/model", "live/model"))
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = [
        _model_error(openai.NotFoundError),  # primary model deprecated/gone
        fake_completion(
            [fake_tool_call("extract_product", {"name": "Rwanda", "packaging": [{"price": "12,50 €"}]})]
        ),
    ]

    result = scrape.extract_product(fake_client, "https://x.sk/rwanda/", "markdown text")
    assert result == {"name": "Rwanda", "packaging": [{"price": "12,50 €"}]}
    # a model-level rejection moves on immediately: no retries wasted on it
    assert fake_client.chat.completions.create.call_count == 2
    assert fake_client.chat.completions.create.call_args_list[0].kwargs["model"] == "dead/model"
    assert fake_client.chat.completions.create.call_args_list[1].kwargs["model"] == "live/model"
    assert "falling back to the next configured model" in capsys.readouterr().out


def test_extract_product_reports_all_tried_models_when_everything_fails(monkeypatch):
    monkeypatch.setattr(scrape, "MODELS", ("dead/model", "deader/model"))
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = _model_error(openai.NotFoundError)

    with pytest.raises(scrape.ExtractionFailed, match="dead/model, deader/model"):
        scrape.extract_product(fake_client, "https://x.sk/rwanda/", "markdown text")
    assert fake_client.chat.completions.create.call_count == 2  # one shot per model, no retries


def test_parse_models_splits_and_strips():
    assert scrape._parse_models("a/x, b/y ,c/z,") == ("a/x", "b/y", "c/z")
    assert scrape.MODELS == scrape._parse_models(scrape.DEFAULT_MODELS)  # no env override in tests


# --- discover_product_urls (async, offline via FakeCrawler) ------------------


@pytest.mark.asyncio
async def test_discover_product_urls_collects_internal_links():
    html = "<html><body>listing</body></html>" + "x" * 200
    crawler = FakeCrawler(
        {
            "https://x.sk/": fake_result(
                html=html,
                links={
                    "internal": [
                        {"href": "https://x.sk/rwanda/", "text": "Rwanda"},
                        {"href": "https://x.sk/kosik/", "text": "Košík"},
                    ]
                },
                url="https://x.sk/",
            )
        }
    )
    discovered, status = await scrape.discover_product_urls(crawler, {"url": "https://x.sk/", "scrape_url": "https://x.sk/"})
    assert status == "ok"
    assert discovered == {"https://x.sk/rwanda/"}  # /kosik/ filtered out


@pytest.mark.asyncio
async def test_discover_product_urls_strips_query_string_before_dedup():
    # WooCommerce filter-widget/sort/add-to-cart links attach query params to
    # the listing page itself — without stripping them, each variant would be
    # discovered as a distinct URL and re-fetched/re-classified every run.
    html = "<html><body>listing</body></html>" + "x" * 200
    crawler = FakeCrawler(
        {
            "https://x.sk/shop": fake_result(
                html=html,
                links={
                    "internal": [
                        {"href": "https://x.sk/shop?filter_hmotnost=250-g", "text": "250g"},
                        {"href": "https://x.sk/shop?add-to-cart=1909", "text": "Add"},
                        {"href": "https://x.sk/rwanda/?utm_source=x", "text": "Rwanda"},
                    ]
                },
                url="https://x.sk/shop",
            )
        }
    )
    discovered, status = await scrape.discover_product_urls(
        crawler, {"url": "https://x.sk/shop", "scrape_url": "https://x.sk/shop"}
    )
    assert status == "ok"
    # Both query-string variants of the listing page collapse to the one bare
    # URL, and the tracked product link loses its query string too.
    assert discovered == {"https://x.sk/shop", "https://x.sk/rwanda/"}


@pytest.mark.asyncio
async def test_discover_product_urls_rejects_dangerous_schemes():
    # A poisoned page's link (or a future crawl4ai internal-link change)
    # must never let a javascript:/data: URI reach `discovered` — it's stored
    # verbatim in products.yaml and rendered as a clickable href on the site.
    html = "<html><body>listing</body></html>" + "x" * 200
    crawler = FakeCrawler(
        {
            "https://x.sk/": fake_result(
                html=html,
                links={
                    "internal": [
                        {"href": "https://x.sk/rwanda/", "text": "Rwanda"},
                        {"href": "javascript:alert(1)", "text": "Kenya"},
                        {"href": "data:text/html,<script>alert(1)</script>", "text": "Guatemala"},
                    ]
                },
                url="https://x.sk/",
            )
        }
    )
    discovered, status = await scrape.discover_product_urls(crawler, {"url": "https://x.sk/", "scrape_url": "https://x.sk/"})
    assert status == "ok"
    assert discovered == {"https://x.sk/rwanda/"}


@pytest.mark.asyncio
async def test_discover_product_urls_rejects_offdomain_link():
    # An off-domain link (e.g. a phishing pivot injected into a poisoned
    # roaster page) must be dropped even though it otherwise looks like a
    # plausible product link.
    html = "<html><body>listing</body></html>" + "x" * 200
    crawler = FakeCrawler(
        {
            "https://x.sk/": fake_result(
                html=html,
                links={
                    "internal": [
                        {"href": "https://x.sk/rwanda/", "text": "Rwanda"},
                        {"href": "https://evil-phish.example/kenya/", "text": "Kenya"},
                    ]
                },
                url="https://x.sk/",
            )
        }
    )
    discovered, status = await scrape.discover_product_urls(crawler, {"url": "https://x.sk/", "scrape_url": "https://x.sk/"})
    assert status == "ok"
    assert discovered == {"https://x.sk/rwanda/"}


@pytest.mark.asyncio
async def test_discover_product_urls_follows_pagination():
    long_text = "x" * 200
    page1 = fake_result(
        html=f'<a rel="next" href="/shop?page=2">Next</a>{long_text}',
        links={"internal": [{"href": "https://x.sk/coffee-a/", "text": "A"}]},
        url="https://x.sk/shop",
    )
    page2 = fake_result(
        html=long_text,
        links={"internal": [{"href": "https://x.sk/coffee-b/", "text": "B"}]},
        url="https://x.sk/shop?page=2",
    )
    crawler = FakeCrawler({"https://x.sk/shop": page1, "https://x.sk/shop?page=2": page2})
    discovered, status = await scrape.discover_product_urls(crawler, {"url": "https://x.sk/shop", "scrape_url": "https://x.sk/shop"})
    assert status == "ok"
    assert discovered == {"https://x.sk/coffee-a/", "https://x.sk/coffee-b/"}


@pytest.mark.asyncio
async def test_discover_product_urls_failed_when_first_page_unreachable():
    crawler = FakeCrawler({})  # no responses -> fake_result(success=False)
    discovered, status = await scrape.discover_product_urls(crawler, {"url": "https://x.sk/", "scrape_url": "https://x.sk/"})
    assert discovered is None
    assert status == "failed"


@pytest.mark.asyncio
async def test_discover_product_urls_needs_js_when_text_too_short():
    crawler = FakeCrawler({"https://x.sk/": fake_result(html="<div>hi</div>")})
    discovered, status = await scrape.discover_product_urls(crawler, {"url": "https://x.sk/", "scrape_url": "https://x.sk/"})
    assert discovered is None
    assert status == "needs_js"


# --- _crawl_listing_links pagination completeness (issue #22) ----------------


@pytest.mark.asyncio
async def test_crawl_listing_links_reports_complete_on_natural_end():
    html = "<html><body>listing</body></html>" + "x" * 200
    crawler = FakeCrawler({"https://x.sk/": fake_result(html=html, url="https://x.sk/")})
    urls, first_result, pagination_status = await scrape._crawl_listing_links(crawler, "https://x.sk/")
    assert pagination_status == "complete"


@pytest.mark.asyncio
async def test_crawl_listing_links_reports_failed_midway_on_page2_fetch_failure():
    # Page 1 succeeds and links to page 2; page 2's fetch fails outright
    # (not in the fake crawler's responses -> success=False) — a transient
    # timeout mid-pagination, not a natural end.
    page1 = fake_result(
        html='<a rel="next" href="/shop?page=2">Next</a>' + "x" * 200,
        links={"internal": [{"href": "https://x.sk/coffee-a/", "text": "A"}]},
        url="https://x.sk/shop",
    )
    crawler = FakeCrawler({"https://x.sk/shop": page1})  # page 2 deliberately absent
    urls, first_result, pagination_status = await scrape._crawl_listing_links(crawler, "https://x.sk/shop")
    assert pagination_status == "failed_midway"
    assert urls == {"https://x.sk/coffee-a/"}  # page 1's links are still returned


@pytest.mark.asyncio
async def test_crawl_listing_links_page1_failure_is_not_failed_midway():
    # A first-page failure is a total discovery failure (reported via
    # first_result being unsuccessful/None), not "partial progress that
    # should be preserved" — pagination_status must stay "complete" so
    # discover_product_urls's existing "failed" handling isn't shadowed by
    # the new partial-discovery path.
    crawler = FakeCrawler({})  # every fetch fails
    urls, first_result, pagination_status = await scrape._crawl_listing_links(crawler, "https://x.sk/")
    assert pagination_status == "complete"
    assert first_result.success is False


@pytest.mark.asyncio
async def test_crawl_listing_links_reports_capped_when_max_pages_hit_with_more_linked():
    page1 = fake_result(
        html='<a rel="next" href="/shop?page=2">Next</a>' + "x" * 200,
        links={"internal": [{"href": "https://x.sk/coffee-a/", "text": "A"}]},
        url="https://x.sk/shop",
    )
    page2 = fake_result(
        html='<a rel="next" href="/shop?page=3">Next</a>' + "x" * 200,
        links={"internal": [{"href": "https://x.sk/coffee-b/", "text": "B"}]},
        url="https://x.sk/shop?page=2",
    )
    crawler = FakeCrawler({"https://x.sk/shop": page1, "https://x.sk/shop?page=2": page2})
    urls, first_result, pagination_status = await scrape._crawl_listing_links(
        crawler, "https://x.sk/shop", max_pages=2
    )
    assert pagination_status == "capped"
    assert urls == {"https://x.sk/coffee-a/", "https://x.sk/coffee-b/"}


@pytest.mark.asyncio
async def test_crawl_listing_links_not_capped_when_max_pages_hit_with_no_further_link():
    # max_pages happens to equal the true page count exactly, and the last
    # page has no next link — this is a natural end, not a cap; the cap
    # signal must only fire when a further page was left unvisited.
    page1 = fake_result(
        html="x" * 200,  # no next link at all
        links={"internal": [{"href": "https://x.sk/coffee-a/", "text": "A"}]},
        url="https://x.sk/shop",
    )
    crawler = FakeCrawler({"https://x.sk/shop": page1})
    urls, first_result, pagination_status = await scrape._crawl_listing_links(
        crawler, "https://x.sk/shop", max_pages=1
    )
    assert pagination_status == "complete"


# --- discover_product_urls "partial" status (issue #22) ----------------------


@pytest.mark.asyncio
async def test_discover_product_urls_partial_on_mid_pagination_failure(capsys):
    page1 = fake_result(
        html='<a rel="next" href="/shop?page=2">Next</a>' + "x" * 200,
        links={"internal": [{"href": "https://x.sk/coffee-a/", "text": "A"}]},
        url="https://x.sk/shop",
    )
    crawler = FakeCrawler({"https://x.sk/shop": page1})
    roaster = {"name": "Test Roastery", "url": "https://x.sk/shop", "scrape_url": "https://x.sk/shop"}
    discovered, status = await scrape.discover_product_urls(crawler, roaster)
    assert status == "partial"
    assert discovered == {"https://x.sk/coffee-a/"}
    assert "Test Roastery" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_discover_product_urls_partial_on_max_pages_cap(capsys):
    page1 = fake_result(
        html='<a rel="next" href="/shop?page=2">Next</a>' + "x" * 200,
        links={"internal": [{"href": "https://x.sk/coffee-a/", "text": "A"}]},
        url="https://x.sk/shop",
    )
    page2 = fake_result(
        html='<a rel="next" href="/shop?page=3">Next</a>' + "x" * 200,
        links={"internal": [{"href": "https://x.sk/coffee-b/", "text": "B"}]},
        url="https://x.sk/shop?page=2",
    )
    crawler = FakeCrawler({"https://x.sk/shop": page1, "https://x.sk/shop?page=2": page2})
    roaster = {"name": "Test Roastery", "url": "https://x.sk/shop", "scrape_url": "https://x.sk/shop"}
    discovered, status = await scrape.discover_product_urls(crawler, roaster, max_pages=2)
    assert status == "partial"
    assert discovered == {"https://x.sk/coffee-a/", "https://x.sk/coffee-b/"}
    out = capsys.readouterr().out
    assert "Test Roastery" in out
    assert "MAX_PAGES" in out


# --- discover_roast_type_hints (async, offline via FakeCrawler) --------------


@pytest.mark.asyncio
async def test_discover_roast_type_hints_tags_urls_by_category():
    html_a = "<html><body>listing</body></html>" + "x" * 200
    html_b = "<html><body>listing</body></html>" + "x" * 200
    crawler = FakeCrawler(
        {
            "https://x.sk/espresso/": fake_result(
                html=html_a,
                links={"internal": [{"href": "https://x.sk/rwanda/", "text": "Rwanda"}]},
                url="https://x.sk/espresso/",
            ),
            "https://x.sk/filter/": fake_result(
                html=html_b,
                links={"internal": [{"href": "https://x.sk/kenya/", "text": "Kenya"}]},
                url="https://x.sk/filter/",
            ),
        }
    )
    roaster = {
        "url": "https://x.sk/",
        "scrape_url": "https://x.sk/",
        "roast_type_urls": {"espresso": "https://x.sk/espresso/", "filter": "https://x.sk/filter/"},
    }
    hints = await scrape.discover_roast_type_hints(crawler, roaster)
    assert hints == {"https://x.sk/rwanda/": "espresso", "https://x.sk/kenya/": "filter"}


@pytest.mark.asyncio
async def test_discover_roast_type_hints_empty_when_not_configured():
    crawler = FakeCrawler({})
    hints = await scrape.discover_roast_type_hints(crawler, {"url": "https://x.sk/", "scrape_url": "https://x.sk/"})
    assert hints == {}
    assert crawler.calls == []  # no wasted crawl for roasters without the config


@pytest.mark.asyncio
async def test_discover_roast_type_hints_failed_category_contributes_nothing():
    # A failed/unreachable category page is a missing hint, not a roaster
    # failure — the other configured category still contributes normally.
    html = "<html><body>listing</body></html>" + "x" * 200
    crawler = FakeCrawler(
        {
            "https://x.sk/filter/": fake_result(
                html=html,
                links={"internal": [{"href": "https://x.sk/kenya/", "text": "Kenya"}]},
                url="https://x.sk/filter/",
            ),
        }
    )
    roaster = {
        "url": "https://x.sk/",
        "scrape_url": "https://x.sk/",
        "roast_type_urls": {"espresso": "https://x.sk/unreachable/", "filter": "https://x.sk/filter/"},
    }
    hints = await scrape.discover_roast_type_hints(crawler, roaster)
    assert hints == {"https://x.sk/kenya/": "filter"}


# --- extract_shopify_variations (async, offline via FakeCrawler) -------------


SHOPIFY_MARKER_HTML = '<script src="https://cdn.shopify.com/s/files/theme.js"></script>'


@pytest.mark.asyncio
async def test_extract_shopify_variations_parses_variant_prices():
    variants_json = json.dumps(
        {
            "variants": [
                {"title": "250g", "price": 1150},
                {"title": "1kg", "price": 3300},
            ]
        }
    )
    crawler = FakeCrawler({"https://x.sk/products/brazil.js": fake_result(html=variants_json)})
    tiers = await scrape.extract_shopify_variations(crawler, SHOPIFY_MARKER_HTML, "https://x.sk/products/brazil")
    assert tiers == [
        {"weight_g": 250, "price": 11.50},
        {"weight_g": 1000, "price": 33.0},
    ]


@pytest.mark.asyncio
async def test_extract_shopify_variations_keeps_distinct_tiers_for_a_second_option_axis():
    # Shopify joins multiple option axes with " / " in a variant's title
    # (e.g. weight crossed with grind) — both same-weight tiers must
    # survive, each tagged with its own variant label.
    variants_json = json.dumps(
        {
            "variants": [
                {"title": "250g / Whole Bean", "price": 1200},
                {"title": "250g / Ground", "price": 1300},
            ]
        }
    )
    crawler = FakeCrawler({"https://x.sk/products/decaf.js": fake_result(html=variants_json)})
    tiers = await scrape.extract_shopify_variations(crawler, SHOPIFY_MARKER_HTML, "https://x.sk/products/decaf")
    assert tiers == [
        {"weight_g": 250, "price": 12.0, "variant": "Whole Bean"},
        {"weight_g": 250, "price": 13.0, "variant": "Ground"},
    ]


@pytest.mark.asyncio
async def test_extract_shopify_variations_non_shopify_page_returns_empty_without_fetching():
    crawler = FakeCrawler({})
    tiers = await scrape.extract_shopify_variations(crawler, "<html>not shopify</html>", "https://x.sk/products/brazil")
    assert tiers == []
    assert crawler.calls == []  # no wasted fetch


@pytest.mark.asyncio
async def test_extract_shopify_variations_strips_query_string_from_endpoint_url():
    variants_json = json.dumps({"variants": [{"title": "250g", "price": 1150}]})
    crawler = FakeCrawler({"https://x.sk/products/brazil.js": fake_result(html=variants_json)})
    await scrape.extract_shopify_variations(crawler, SHOPIFY_MARKER_HTML, "https://x.sk/products/brazil?variant=123")
    assert crawler.calls == ["https://x.sk/products/brazil.js"]


@pytest.mark.asyncio
async def test_extract_shopify_variations_endpoint_failure_returns_empty():
    crawler = FakeCrawler({})  # unreachable -> fake_result(success=False)
    tiers = await scrape.extract_shopify_variations(crawler, SHOPIFY_MARKER_HTML, "https://x.sk/products/brazil")
    assert tiers == []


@pytest.mark.asyncio
async def test_extract_shopify_variations_malformed_json_returns_empty():
    crawler = FakeCrawler({"https://x.sk/products/brazil.js": fake_result(html="not json")})
    tiers = await scrape.extract_shopify_variations(crawler, SHOPIFY_MARKER_HTML, "https://x.sk/products/brazil")
    assert tiers == []


# --- process_roaster (async, offline via FakeCrawler) ------------------------


ROASTER = {"name": "Test Roastery", "slug": "test-roastery", "url": "https://x.sk/", "scrape_url": "https://x.sk/"}
LONG_TEXT = "x" * 200


def listing_result(product_urls):
    links = {"internal": [{"href": u, "text": "Coffee"} for u in product_urls]}
    return fake_result(html=LONG_TEXT, links=links, url="https://x.sk/")


@pytest.mark.asyncio
async def test_process_roaster_extracts_new_product():
    crawler = FakeCrawler(
        {
            "https://x.sk/": listing_result(["https://x.sk/rwanda/"]),
            "https://x.sk/rwanda/": fake_result(markdown=fake_markdown(LONG_TEXT + " 12,50 €")),
        }
    )
    client = MagicMock()
    client.chat.completions.create.return_value = fake_completion(
        [fake_tool_call("extract_product", {"name": "Rwanda", "packaging": [{"price": "12,50 €", "weight": "250 g"}]})]
    )

    entries, status = await scrape.process_roaster(crawler, client, ROASTER, [], "2026-07-04")
    assert status == "ok"
    assert len(entries) == 1
    assert entries[0]["name"] == "Rwanda"
    assert entries[0]["page_hash"]


@pytest.mark.asyncio
async def test_process_roaster_parses_product_html_only_once(monkeypatch):
    # issue #27: extract_woocommerce_variations/origin/roast_type/weight
    # used to each build their own BeautifulSoup from result.html — up to
    # 4 separate parses of the very same product page. process_roaster
    # should now parse a given product page's HTML exactly once and hand
    # every helper the same soup object.
    product_html = (
        '<form data-product_variations="'
        "[{&quot;attributes&quot;:{&quot;attribute_pa_hmotnost&quot;:&quot;250-g&quot;},"
        "&quot;display_price&quot;:11}]"
        '"></form>'
    )
    crawler = FakeCrawler(
        {
            "https://x.sk/": listing_result(["https://x.sk/rwanda/"]),
            "https://x.sk/rwanda/": fake_result(html=product_html, markdown=fake_markdown(LONG_TEXT + " 12,50 €")),
        }
    )
    client = MagicMock()
    client.chat.completions.create.return_value = fake_completion(
        [fake_tool_call("extract_product", {"name": "Rwanda", "packaging": [{"price": "12,50 €", "weight": "250 g"}]})]
    )

    parse_calls = []
    real_beautifulsoup = scrape.BeautifulSoup

    def counting_beautifulsoup(*args, **kwargs):
        parse_calls.append(args[0] if args else kwargs.get("markup"))
        return real_beautifulsoup(*args, **kwargs)

    monkeypatch.setattr(scrape, "BeautifulSoup", counting_beautifulsoup)

    entries, status = await scrape.process_roaster(crawler, client, ROASTER, [], "2026-07-04")
    assert status == "ok"
    # Discovery's own listing-page parses (find_next_page_url,
    # visible_html_text_length) are a separate, earlier phase and not what
    # this test is about — filter down to parses of THIS product page's
    # HTML specifically, which the four extraction helpers all used to
    # parse independently.
    product_page_parses = [c for c in parse_calls if c == product_html]
    assert len(product_page_parses) == 1


@pytest.mark.asyncio
async def test_process_roaster_uses_roast_type_hint_when_page_never_states_it():
    # Site never states roast_type on the product page itself — only the
    # discovery category ("espresso/") it's linked from reveals it.
    crawler = FakeCrawler(
        {
            "https://x.sk/": listing_result(["https://x.sk/rwanda/"]),
            "https://x.sk/rwanda/": fake_result(markdown=fake_markdown(LONG_TEXT + " 12,50 €")),
            "https://x.sk/espresso/": fake_result(
                html=LONG_TEXT,
                links={"internal": [{"href": "https://x.sk/rwanda/", "text": "Rwanda"}]},
                url="https://x.sk/espresso/",
            ),
        }
    )
    client = MagicMock()
    client.chat.completions.create.return_value = fake_completion(
        [
            fake_tool_call(
                "extract_product",
                {"name": "Rwanda", "origin": "Rwanda", "packaging": [{"price": "12,50 €", "weight": "250 g"}]},
            )
        ]
    )
    roaster = dict(ROASTER, roast_type_urls={"espresso": "https://x.sk/espresso/"})

    entries, status = await scrape.process_roaster(crawler, client, roaster, [], "2026-07-04")
    assert status == "ok"
    assert entries[0]["roast_type"] == "espresso"
    assert entries[0]["status"] == "ok"


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
async def test_process_roaster_falls_back_to_shopify_variations_when_no_woocommerce_data():
    variants_json = json.dumps(
        {"variants": [{"title": "250g", "price": 1150}, {"title": "1kg", "price": 3300}]}
    )
    crawler = FakeCrawler(
        {
            "https://x.sk/": listing_result(["https://x.sk/brazil/"]),
            "https://x.sk/brazil/": fake_result(
                html=SHOPIFY_MARKER_HTML, markdown=fake_markdown(LONG_TEXT + " 11,50 €")
            ),
            "https://x.sk/brazil.js": fake_result(html=variants_json),
        }
    )
    client = MagicMock()
    client.chat.completions.create.return_value = fake_completion(
        [
            fake_tool_call(
                "extract_product",
                # Deliberately wrong/incomplete — only the visible default price.
                {"name": "Brazil", "origin": "Brazil", "roast_type": "Filter", "packaging": [{"price": "11,50 €"}]},
            )
        ]
    )
    entries, status = await scrape.process_roaster(crawler, client, ROASTER, [], "2026-07-08")
    assert status == "ok"
    assert entries[0]["packaging"] == [
        {"weight_g": 250, "price": 11.50},
        {"weight_g": 1000, "price": 33.0},
    ]


def suca_tool_call(price_filter_250=11.0, price_filter_500=18.0, price_espresso_250=11.0, price_espresso_500=18.0):
    return fake_tool_call(
        "extract_product",
        {
            "name": "Colombia Jesus Barahona Buenavista",
            "origin": "Colombia",
            "packaging": [
                {"weight": "250 g", "price": f"{price_filter_250} €", "roast_type": "Filter"},
                {"weight": "500 g", "price": f"{price_filter_500} €", "roast_type": "Filter"},
                {"weight": "250 g", "price": f"{price_espresso_250} €", "roast_type": "Espresso"},
                {"weight": "500 g", "price": f"{price_espresso_500} €", "roast_type": "Espresso"},
            ],
        },
    )


@pytest.mark.asyncio
async def test_process_roaster_splits_two_roast_types_from_one_url():
    crawler = FakeCrawler(
        {
            "https://x.sk/": listing_result(["https://x.sk/colombia/"]),
            "https://x.sk/colombia/": fake_result(markdown=fake_markdown(LONG_TEXT + " 11,00 €")),
        }
    )
    client = MagicMock()
    client.chat.completions.create.return_value = fake_completion([suca_tool_call()])

    entries, status = await scrape.process_roaster(crawler, client, ROASTER, [], "2026-07-08")
    assert status == "ok"
    assert len(entries) == 2
    assert {e["roast_type"] for e in entries} == {"filter", "espresso"}
    assert all(e["url"] == "https://x.sk/colombia/" for e in entries)
    assert entries[0]["page_hash"] == entries[1]["page_hash"]
    for e in entries:
        assert e["packaging"] == [
            {"weight_g": 250, "price": 11.0},
            {"weight_g": 500, "price": 18.0},
        ]


@pytest.mark.asyncio
async def test_process_roaster_hash_gate_matches_both_split_entries_on_second_run():
    markdown_text = LONG_TEXT + " 11,00 €"
    client = MagicMock()
    client.chat.completions.create.return_value = fake_completion([suca_tool_call()])

    crawler_v1 = FakeCrawler(
        {
            "https://x.sk/": listing_result(["https://x.sk/colombia/"]),
            "https://x.sk/colombia/": fake_result(markdown=fake_markdown(markdown_text)),
        }
    )
    entries_v1, _ = await scrape.process_roaster(crawler_v1, client, ROASTER, [], "2026-07-08")
    assert len(entries_v1) == 2
    assert client.chat.completions.create.call_count == 1

    crawler_v2 = FakeCrawler(
        {
            "https://x.sk/": listing_result(["https://x.sk/colombia/"]),
            "https://x.sk/colombia/": fake_result(markdown=fake_markdown(markdown_text)),
        }
    )
    entries_v2, _ = await scrape.process_roaster(crawler_v2, client, ROASTER, entries_v1, "2026-07-09")
    assert client.chat.completions.create.call_count == 1  # not called again — both entries gated together
    assert len(entries_v2) == 2
    assert {e["roast_type"] for e in entries_v2} == {"filter", "espresso"}
    assert all(e["last_seen"] == "2026-07-09" for e in entries_v2)
    # No cross-matching: each entry's packaging still belongs to its own roast_type.
    for e in entries_v2:
        assert e["packaging"] == [
            {"weight_g": 250, "price": 11.0},
            {"weight_g": 500, "price": 18.0},
        ]


@pytest.mark.asyncio
async def test_process_roaster_reextracts_both_split_entries_when_page_changes():
    client = MagicMock()
    client.chat.completions.create.return_value = fake_completion([suca_tool_call()])

    crawler_v1 = FakeCrawler(
        {
            "https://x.sk/": listing_result(["https://x.sk/colombia/"]),
            "https://x.sk/colombia/": fake_result(markdown=fake_markdown(LONG_TEXT + " 11,00 €")),
        }
    )
    entries_v1, _ = await scrape.process_roaster(crawler_v1, client, ROASTER, [], "2026-07-08")
    assert client.chat.completions.create.call_count == 1

    client.chat.completions.create.return_value = fake_completion(
        [suca_tool_call(price_filter_500=19.0, price_espresso_500=19.0)]
    )
    crawler_v2 = FakeCrawler(
        {
            "https://x.sk/": listing_result(["https://x.sk/colombia/"]),
            "https://x.sk/colombia/": fake_result(markdown=fake_markdown(LONG_TEXT + " changed 11,00 €")),
        }
    )
    entries_v2, _ = await scrape.process_roaster(crawler_v2, client, ROASTER, entries_v1, "2026-07-09")
    assert client.chat.completions.create.call_count == 2  # re-extracted, not hash-gated away
    assert len(entries_v2) == 2
    for e in entries_v2:
        assert e["packaging"][1] == {"weight_g": 500, "price": 19.0}


@pytest.mark.asyncio
async def test_process_roaster_schema_version_bump_forces_resplit_of_legacy_single_entry():
    # Mirrors the real production bug shape: one legacy entry, stale/missing
    # schema_version, packaging with the duplicate-pair signature.
    markdown_text = LONG_TEXT + " 11,00 €"
    page_hash = scrape.compute_page_hash(markdown_text)
    crawler = FakeCrawler(
        {
            "https://x.sk/": listing_result(["https://x.sk/colombia/"]),
            "https://x.sk/colombia/": fake_result(markdown=fake_markdown(markdown_text)),
        }
    )
    client = MagicMock()
    client.chat.completions.create.return_value = fake_completion([suca_tool_call()])
    existing = [
        {
            "name": "Colombia Jesus Barahona Buenavista",
            "url": "https://x.sk/colombia/",
            "origin": "Colombia",
            "roast_type": "filter",
            "status": "ok",
            "last_seen": "2026-07-01",
            "page_hash": page_hash,  # page content unchanged
            "packaging": [
                {"weight_g": 250, "price": 11.0},
                {"weight_g": 250, "price": 11.0},
                {"weight_g": 500, "price": 18.0},
                {"weight_g": 500, "price": 18.0},
            ],
            # no schema_version key — a legacy entry predating this migration
        }
    ]
    entries, status = await scrape.process_roaster(crawler, client, ROASTER, existing, "2026-07-04")
    assert status == "ok"
    client.chat.completions.create.assert_called_once()  # re-extracted despite unchanged hash
    assert len(entries) == 2
    assert {e["roast_type"] for e in entries} == {"filter", "espresso"}
    for e in entries:
        assert e["schema_version"] == scrape.SCHEMA_VERSION
        assert e["packaging"] == [
            {"weight_g": 250, "price": 11.0},
            {"weight_g": 500, "price": 18.0},
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
    # The extraction is deliberately complete (`ok`) — an incomplete entry
    # now intentionally bypasses the gate for a few runs (issue #36), which
    # is not what this test is about.
    markdown_text = LONG_TEXT + " 12,50 €"
    crawler_v1 = FakeCrawler(
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
                    "roast_type": "Filter",
                    "packaging": [{"price": "12,50 €", "weight": "250 g"}],
                },
            )
        ]
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


@pytest.mark.asyncio
async def test_process_roaster_skips_claude_when_hash_unchanged():
    markdown_text = LONG_TEXT + " 12,50 €"
    page_hash = scrape.compute_page_hash(markdown_text)
    crawler = FakeCrawler(
        {
            "https://x.sk/": listing_result(["https://x.sk/rwanda/"]),
            "https://x.sk/rwanda/": fake_result(markdown=fake_markdown(markdown_text)),
        }
    )
    client = MagicMock()
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
    entries, status = await scrape.process_roaster(crawler, client, ROASTER, existing, "2026-07-04")
    assert status == "ok"
    client.chat.completions.create.assert_not_called()
    assert entries[0]["last_seen"] == "2026-07-04"  # bumped even though unchanged


@pytest.mark.asyncio
async def test_process_roaster_forces_reextraction_when_schema_version_stale():
    markdown_text = LONG_TEXT + " 12,50 €"
    page_hash = scrape.compute_page_hash(markdown_text)
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


# --- incomplete re-extraction budget (issue #36) -------------------------------


def _incomplete_prior(page_hash, **overrides):
    entry = {
        "name": "Mystery Coffee",
        "url": "https://x.sk/mystery/",
        "status": "incomplete",
        "missing_fields": ["origin", "roast_type"],
        "last_seen": "2026-07-01",
        "page_hash": page_hash,
        "packaging": [{"weight_g": 250, "price": 12.5}],
        "schema_version": scrape.SCHEMA_VERSION,
    }
    entry.update(overrides)
    return entry


def _mystery_crawler(markdown_text):
    return FakeCrawler(
        {
            "https://x.sk/": listing_result(["https://x.sk/mystery/"]),
            "https://x.sk/mystery/": fake_result(markdown=fake_markdown(markdown_text)),
        }
    )


@pytest.mark.asyncio
async def test_process_roaster_reextracts_incomplete_despite_unchanged_hash():
    # issue #36: an incomplete entry used to hash-gate exactly like an ok
    # one, so a flaky extraction (model missed a field the page states)
    # could never self-heal until the roaster edited the page.
    markdown_text = LONG_TEXT + " 12,50 €"
    page_hash = scrape.compute_page_hash(markdown_text)
    crawler = _mystery_crawler(markdown_text)
    client = MagicMock()
    client.chat.completions.create.return_value = fake_completion(
        [
            fake_tool_call(
                "extract_product",
                {
                    "name": "Mystery Coffee",
                    "origin": "Rwanda",
                    "roast_type": "Filter",
                    "packaging": [{"price": "12,50 €", "weight": "250 g"}],
                },
            )
        ]
    )

    entries, status = await scrape.process_roaster(
        crawler, client, ROASTER, [_incomplete_prior(page_hash)], "2026-07-04"
    )
    assert status == "ok"
    client.chat.completions.create.assert_called_once()  # gate bypassed
    assert entries[0]["status"] == "ok"  # healed
    assert "reextract_attempts" not in entries[0]  # counter only exists while incomplete


@pytest.mark.asyncio
async def test_process_roaster_increments_reextract_attempts_when_still_incomplete():
    markdown_text = LONG_TEXT + " 12,50 €"
    page_hash = scrape.compute_page_hash(markdown_text)
    crawler = _mystery_crawler(markdown_text)
    client = MagicMock()
    # Model still can't find origin/roast_type — page genuinely omits them.
    client.chat.completions.create.return_value = fake_completion(
        [
            fake_tool_call(
                "extract_product",
                {"name": "Mystery Coffee", "packaging": [{"price": "12,50 €", "weight": "250 g"}]},
            )
        ]
    )

    entries, status = await scrape.process_roaster(
        crawler, client, ROASTER, [_incomplete_prior(page_hash, reextract_attempts=1)], "2026-07-04"
    )
    assert status == "ok"
    client.chat.completions.create.assert_called_once()  # 1 < budget, so retried
    assert entries[0]["status"] == "incomplete"
    assert entries[0]["reextract_attempts"] == 2


@pytest.mark.asyncio
async def test_process_roaster_gates_incomplete_once_retry_budget_spent():
    markdown_text = LONG_TEXT + " 12,50 €"
    page_hash = scrape.compute_page_hash(markdown_text)
    crawler = _mystery_crawler(markdown_text)
    client = MagicMock()

    prior = _incomplete_prior(
        page_hash, reextract_attempts=scrape.MAX_INCOMPLETE_REEXTRACTIONS
    )
    entries, status = await scrape.process_roaster(crawler, client, ROASTER, [prior], "2026-07-04")
    assert status == "ok"
    client.chat.completions.create.assert_not_called()  # budget spent — gated again
    assert entries[0]["status"] == "incomplete"
    assert entries[0]["last_seen"] == "2026-07-04"  # still bumped like any gated entry


@pytest.mark.asyncio
async def test_process_roaster_resets_reextract_counter_when_page_changes():
    # A changed page is a fresh start: the counter must not carry over from
    # the old page's spent budget, or a roaster who reworks a product page
    # (still without stating origin) would never get its retry chances back.
    new_markdown = LONG_TEXT + " now with new description 12,50 €"
    crawler = _mystery_crawler(new_markdown)
    client = MagicMock()
    client.chat.completions.create.return_value = fake_completion(
        [
            fake_tool_call(
                "extract_product",
                {"name": "Mystery Coffee", "packaging": [{"price": "12,50 €", "weight": "250 g"}]},
            )
        ]
    )

    prior = _incomplete_prior(
        scrape.compute_page_hash(LONG_TEXT + " 12,50 €"),  # old page's hash
        reextract_attempts=scrape.MAX_INCOMPLETE_REEXTRACTIONS,
    )
    entries, status = await scrape.process_roaster(crawler, client, ROASTER, [prior], "2026-07-04")
    assert status == "ok"
    client.chat.completions.create.assert_called_once()  # hash mismatch re-extracts as before
    assert entries[0]["status"] == "incomplete"
    assert "reextract_attempts" not in entries[0]  # fresh page, fresh budget


# --- compute_page_hash (issue #13: hash-gate leaks on dynamic page chrome) -----


def test_compute_page_hash_deterministic_for_identical_content():
    text = "Rwanda Kigali, washed, 12,50 € " * 50
    assert scrape.compute_page_hash(text) == scrape.compute_page_hash(text)


def test_compute_page_hash_ignores_dynamic_chrome_beyond_truncation_window():
    # A real product's identifying content (title/price/description) fills
    # the whole MAX_MARKDOWN_CHARS window that gets hashed (same window sent
    # to the LLM). A "5 people are viewing this" stock-urgency widget, a
    # rotating testimonial, or a "customers also bought" carousel tacked on
    # past that window — the kind of dynamic chrome that changes between two
    # fetches of an otherwise-unchanged page — must not flip the hash.
    base = "Rwanda Kigali, washed, filter roast, 12,50 € for 250 g. " * 400
    assert len(base) > scrape.MAX_MARKDOWN_CHARS
    dynamic_chrome = (
        "5 people are viewing this product right now! "
        "Customers also bought: Ethiopia Yirgacheffe, Kenya Nyeri. "
        "In stock: 3 left. " * 100
    )
    assert scrape.compute_page_hash(base) == scrape.compute_page_hash(base + dynamic_chrome)


def test_compute_page_hash_changes_when_content_inside_window_changes():
    # A genuine product change (price, name, description) sitting inside the
    # hashed window must still reliably change the hash.
    base = "Rwanda Kigali, washed, filter roast, 12,50 € for 250 g. " * 400
    price_changed = base.replace("12,50 €", "14,90 €")
    assert scrape.compute_page_hash(base) != scrape.compute_page_hash(price_changed)


def test_compute_page_hash_folds_in_variations_raw():
    assert scrape.compute_page_hash("same markdown", "v1") != scrape.compute_page_hash("same markdown", "v2")


@pytest.mark.asyncio
async def test_process_roaster_hash_gate_survives_dynamic_chrome_appended_between_runs():
    # End-to-end regression for issue #13: appending plausible dynamic page
    # chrome between two fetches of an otherwise-unchanged product must not
    # force a fresh (paid, nondeterministic) re-extraction.
    base_markdown = "Rwanda Kigali, washed, filter roast, 12,50 € for 250 g. " * 400
    assert len(base_markdown) > scrape.MAX_MARKDOWN_CHARS
    client = MagicMock()
    # Complete (`ok`) extraction on purpose — an incomplete entry now
    # bypasses the gate for a few runs (issue #36), which would mask the
    # dynamic-chrome regression this test guards.
    client.chat.completions.create.return_value = fake_completion(
        [
            fake_tool_call(
                "extract_product",
                {
                    "name": "Rwanda",
                    "roast_type": "Filter",
                    "packaging": [{"price": "12,50 €", "weight": "250 g"}],
                },
            )
        ]
    )
    crawler_v1 = FakeCrawler(
        {
            "https://x.sk/": listing_result(["https://x.sk/rwanda/"]),
            "https://x.sk/rwanda/": fake_result(markdown=fake_markdown(base_markdown)),
        }
    )
    entries_v1, _ = await scrape.process_roaster(crawler_v1, client, ROASTER, [], "2026-07-08")
    assert client.chat.completions.create.call_count == 1

    dynamic_markdown = base_markdown + (
        "5 people are viewing this product right now! In stock: 3 left. " * 50
    )
    crawler_v2 = FakeCrawler(
        {
            "https://x.sk/": listing_result(["https://x.sk/rwanda/"]),
            "https://x.sk/rwanda/": fake_result(markdown=fake_markdown(dynamic_markdown)),
        }
    )
    entries_v2, _ = await scrape.process_roaster(crawler_v2, client, ROASTER, entries_v1, "2026-07-09")
    assert client.chat.completions.create.call_count == 1  # not re-called: chrome fell outside the window
    assert entries_v2[0]["last_seen"] == "2026-07-09"


@pytest.mark.asyncio
async def test_process_roaster_removes_delisted_product():
    # This run discovers a different, still-live product — "old-coffee" is
    # genuinely gone, not just a suspicious zero-link crawl.
    crawler = FakeCrawler(
        {
            "https://x.sk/": listing_result(["https://x.sk/still-here/"]),
            "https://x.sk/still-here/": fake_result(markdown=fake_markdown(LONG_TEXT + " 9,00 €")),
        }
    )
    client = MagicMock()
    client.chat.completions.create.return_value = fake_completion(
        [fake_tool_call("extract_product", {"name": "Still Here", "packaging": [{"price": "9,00 €"}]})]
    )

    existing = [
        {
            "name": "Old Coffee",
            "url": "https://x.sk/old-coffee/",
            "status": "ok",
            "last_seen": "2026-07-01",
            "page_hash": "deadbeef",
            "packaging": [{"weight_g": 250, "price": 9.0}],
        }
    ]
    entries, status = await scrape.process_roaster(crawler, client, ROASTER, existing, "2026-07-04")
    assert status == "ok"
    assert [e["url"] for e in entries] == ["https://x.sk/still-here/"]


# --- mass-delisting guard (issue #39) -----------------------------------------


def _ok_prior_entry(url, name="Old Coffee"):
    return {
        "name": name,
        "url": url,
        "status": "ok",
        "last_seen": "2026-07-01",
        "page_hash": "deadbeef",
        "packaging": [{"weight_g": 250, "price": 9.0}],
        "schema_version": scrape.SCHEMA_VERSION,
    }


def _single_product_crawler():
    return FakeCrawler(
        {
            "https://x.sk/": listing_result(["https://x.sk/new-one/"]),
            "https://x.sk/new-one/": fake_result(markdown=fake_markdown(LONG_TEXT + " 12,50 €")),
        }
    )


def _ok_extraction_client():
    client = MagicMock()
    client.chat.completions.create.return_value = fake_completion(
        [
            fake_tool_call(
                "extract_product",
                {
                    "name": "New One",
                    "origin": "Rwanda",
                    "roast_type": "Filter",
                    "packaging": [{"price": "12,50 €", "weight": "250 g"}],
                },
            )
        ]
    )
    return client


@pytest.mark.asyncio
async def test_process_roaster_mass_delist_guard_preserves_entries_and_reports_suspect(capsys):
    # A clean-looking discovery that would drop 4 of 4 known-good products
    # in one run is a suspected site redesign, not a real wipeout — priors
    # must survive untouched and the roaster must report "suspect".
    existing = [_ok_prior_entry(f"https://x.sk/old-{i}/", f"Old {i}") for i in range(4)]

    entries, status = await scrape.process_roaster(
        _single_product_crawler(), _ok_extraction_client(), ROASTER, existing, "2026-07-04"
    )
    assert status == "suspect"
    assert "suspect" in scrape.ROASTER_STATUS_NOTES  # warns in summary/annotations
    urls = {e["url"] for e in entries}
    assert urls == {f"https://x.sk/old-{i}/" for i in range(4)} | {"https://x.sk/new-one/"}
    # preserved exactly like a partial run: untouched, last_seen frozen
    for e in entries:
        if e["url"] != "https://x.sk/new-one/":
            assert e["last_seen"] == "2026-07-01"
    assert "would drop 4 of 4 known products" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_process_roaster_mass_delist_guard_ignores_not_a_product_drops():
    # Tightening the discovery filter (issue #37) legitimately drops
    # hundreds of not_a_product entries at once — that must NOT trip the
    # guard; only ok/incomplete priors count as "known products".
    existing = [
        {
            "url": f"https://x.sk/kategoria-{i}/",
            "status": "not_a_product",
            "last_seen": "2026-07-01",
            "page_hash": "deadbeef",
        }
        for i in range(6)
    ]

    entries, status = await scrape.process_roaster(
        _single_product_crawler(), _ok_extraction_client(), ROASTER, existing, "2026-07-04"
    )
    assert status == "ok"
    assert [e["url"] for e in entries] == ["https://x.sk/new-one/"]  # noise really dropped


@pytest.mark.asyncio
async def test_process_roaster_mass_delist_guard_floor_lets_small_real_delistings_through():
    # 2 of 3 products delisted clears the fraction but not the
    # MASS_DELIST_GUARD_MIN_DROPPED floor — a tiny catalogue shrinking is
    # ordinary churn, and the drop must go through as a plain "ok" run.
    markdown_text = LONG_TEXT + " 12,50 €"
    page_hash = scrape.compute_page_hash(markdown_text)
    crawler = FakeCrawler(
        {
            "https://x.sk/": listing_result(["https://x.sk/keeper/"]),
            "https://x.sk/keeper/": fake_result(markdown=fake_markdown(markdown_text)),
        }
    )
    keeper = _ok_prior_entry("https://x.sk/keeper/", "Keeper")
    keeper["page_hash"] = page_hash  # hash-gates, no LLM call needed
    existing = [
        keeper,
        _ok_prior_entry("https://x.sk/old-1/", "Old 1"),
        _ok_prior_entry("https://x.sk/old-2/", "Old 2"),
    ]

    client = MagicMock()
    entries, status = await scrape.process_roaster(crawler, client, ROASTER, existing, "2026-07-04")
    assert status == "ok"
    assert [e["url"] for e in entries] == ["https://x.sk/keeper/"]
    client.chat.completions.create.assert_not_called()


# --- politeness delay (issue #27) --------------------------------------------


@pytest.mark.asyncio
async def test_politeness_wait_skips_the_first_fetch_then_sleeps(monkeypatch):
    sleep_calls = []

    async def recording_sleep(seconds):
        sleep_calls.append(seconds)

    monkeypatch.setattr(scrape.asyncio, "sleep", recording_sleep)

    throttle = [True]
    await scrape._politeness_wait(throttle)  # this roaster's very first fetch: no sleep
    assert sleep_calls == []
    await scrape._politeness_wait(throttle)
    await scrape._politeness_wait(throttle)
    assert sleep_calls == [scrape.POLITENESS_DELAY_SECONDS, scrape.POLITENESS_DELAY_SECONDS]


@pytest.mark.asyncio
async def test_politeness_wait_disabled_when_throttle_is_none(monkeypatch):
    # throttle=None is the "fetching a single URL in isolation" case (e.g.
    # a direct unit test of a helper) — never sleeps, regardless of how
    # many times it's called.
    sleep_calls = []

    async def recording_sleep(seconds):
        sleep_calls.append(seconds)

    monkeypatch.setattr(scrape.asyncio, "sleep", recording_sleep)

    await scrape._politeness_wait(None)
    await scrape._politeness_wait(None)
    assert sleep_calls == []


@pytest.mark.asyncio
async def test_process_roaster_delays_between_same_domain_fetches_but_not_the_first(monkeypatch):
    # One listing fetch + two product fetches = 3 same-domain fetches for
    # this roaster -> exactly 2 politeness sleeps, never before the very
    # first fetch.
    sleep_calls = []

    async def recording_sleep(seconds):
        sleep_calls.append(seconds)

    monkeypatch.setattr(scrape.asyncio, "sleep", recording_sleep)

    crawler = FakeCrawler(
        {
            "https://x.sk/": listing_result(["https://x.sk/rwanda/", "https://x.sk/kenya/"]),
            "https://x.sk/rwanda/": fake_result(markdown=fake_markdown(LONG_TEXT + " 12,50 €")),
            "https://x.sk/kenya/": fake_result(markdown=fake_markdown(LONG_TEXT + " 13,50 €")),
        }
    )
    client = MagicMock()
    client.chat.completions.create.return_value = fake_completion(
        [
            fake_tool_call(
                "extract_product", {"name": "Coffee", "packaging": [{"price": "12,50 €", "weight": "250 g"}]}
            )
        ]
    )

    entries, status = await scrape.process_roaster(crawler, client, ROASTER, [], "2026-07-04")
    assert status == "ok"
    assert len(entries) == 2
    assert sleep_calls == [scrape.POLITENESS_DELAY_SECONDS, scrape.POLITENESS_DELAY_SECONDS]


@pytest.mark.asyncio
async def test_process_roaster_shares_throttle_across_discovery_hints_and_products(monkeypatch):
    # A roast_type_urls-configured roaster fetches: the main listing, the
    # "espresso" hint category listing, and one product page -> 3 total
    # same-domain fetches -> 2 politeness sleeps. Confirms the throttle
    # flows through discover_product_urls AND discover_roast_type_hints,
    # not just the per-product loop.
    sleep_calls = []

    async def recording_sleep(seconds):
        sleep_calls.append(seconds)

    monkeypatch.setattr(scrape.asyncio, "sleep", recording_sleep)

    crawler = FakeCrawler(
        {
            "https://x.sk/": listing_result(["https://x.sk/rwanda/"]),
            "https://x.sk/rwanda/": fake_result(markdown=fake_markdown(LONG_TEXT + " 12,50 €")),
            "https://x.sk/espresso/": fake_result(
                html=LONG_TEXT,
                links={"internal": [{"href": "https://x.sk/rwanda/", "text": "Rwanda"}]},
                url="https://x.sk/espresso/",
            ),
        }
    )
    client = MagicMock()
    client.chat.completions.create.return_value = fake_completion(
        [
            fake_tool_call(
                "extract_product", {"name": "Rwanda", "packaging": [{"price": "12,50 €", "weight": "250 g"}]}
            )
        ]
    )
    roaster = dict(ROASTER, roast_type_urls={"espresso": "https://x.sk/espresso/"})

    entries, status = await scrape.process_roaster(crawler, client, roaster, [], "2026-07-04")
    assert status == "ok"
    assert len(sleep_calls) == 2


# --- process_roaster "partial" discovery (issue #22) --------------------------


@pytest.mark.asyncio
async def test_process_roaster_partial_mid_pagination_failure_preserves_undiscovered_entries():
    # Page 1 discovers "still-here" and links to page 2, whose fetch fails
    # outright (a transient timeout) rather than pagination naturally
    # ending. "old-coffee" is prior data for a URL that was never
    # rediscovered this run (it might well live on the unreached page 2) —
    # it must be preserved, not treated as delisted, and the roaster status
    # must be "partial", not "ok".
    page1 = fake_result(
        html='<a rel="next" href="/shop?page=2">Next</a>' + LONG_TEXT,
        links={"internal": [{"href": "https://x.sk/still-here/", "text": "Coffee"}]},
        url="https://x.sk/shop",
    )
    crawler = FakeCrawler(
        {
            "https://x.sk/shop": page1,  # page 2 deliberately absent -> fetch fails
            "https://x.sk/still-here/": fake_result(markdown=fake_markdown(LONG_TEXT + " 9,00 €")),
        }
    )
    client = MagicMock()
    client.chat.completions.create.return_value = fake_completion(
        [fake_tool_call("extract_product", {"name": "Still Here", "packaging": [{"price": "9,00 €"}]})]
    )
    roaster = dict(ROASTER, scrape_url="https://x.sk/shop")
    existing = [
        {
            "name": "Old Coffee",
            "url": "https://x.sk/old-coffee/",
            "status": "ok",
            "last_seen": "2026-07-01",
            "page_hash": "deadbeef",
            "packaging": [{"weight_g": 250, "price": 9.0}],
        }
    ]
    entries, status = await scrape.process_roaster(crawler, client, roaster, existing, "2026-07-04")
    assert status == "partial"
    urls = {e["url"] for e in entries}
    assert urls == {"https://x.sk/old-coffee/", "https://x.sk/still-here/"}
    old = next(e for e in entries if e["url"] == "https://x.sk/old-coffee/")
    # Untouched: last_seen doesn't advance and the stored hash isn't
    # disturbed, so a later successful run still re-extracts it if the page
    # actually changed rather than treating it as freshly confirmed.
    assert old["last_seen"] == "2026-07-01"
    assert old["page_hash"] == "deadbeef"


@pytest.mark.asyncio
async def test_process_roaster_max_pages_cap_reports_partial_and_preserves_entries():
    page1 = fake_result(
        html='<a rel="next" href="/shop?page=2">Next</a>' + LONG_TEXT,
        links={"internal": [{"href": "https://x.sk/still-here/", "text": "Coffee"}]},
        url="https://x.sk/shop",
    )
    page2 = fake_result(
        html='<a rel="next" href="/shop?page=3">Next</a>' + LONG_TEXT,  # page 3 never fetched: capped
        links={"internal": []},
        url="https://x.sk/shop?page=2",
    )
    crawler = FakeCrawler(
        {
            "https://x.sk/shop": page1,
            "https://x.sk/shop?page=2": page2,
            "https://x.sk/still-here/": fake_result(markdown=fake_markdown(LONG_TEXT + " 9,00 €")),
        }
    )
    client = MagicMock()
    client.chat.completions.create.return_value = fake_completion(
        [fake_tool_call("extract_product", {"name": "Still Here", "packaging": [{"price": "9,00 €"}]})]
    )
    roaster = dict(ROASTER, scrape_url="https://x.sk/shop")
    existing = [
        {
            "name": "Old Coffee",
            "url": "https://x.sk/old-coffee/",  # would only ever appear on the unreached page 3
            "status": "ok",
            "last_seen": "2026-07-01",
            "page_hash": "deadbeef",
            "packaging": [{"weight_g": 250, "price": 9.0}],
        }
    ]
    entries, status = await scrape.process_roaster(
        crawler, client, roaster, existing, "2026-07-04", max_pages=2
    )
    assert status == "partial"
    urls = {e["url"] for e in entries}
    assert urls == {"https://x.sk/old-coffee/", "https://x.sk/still-here/"}


@pytest.mark.asyncio
async def test_process_roaster_full_natural_pagination_still_drops_delisted_and_reports_ok():
    # Regression guard: pagination that runs across multiple pages but
    # completes naturally (no cap, no mid-run failure) must keep behaving
    # exactly as before "partial" was introduced — genuinely-delisted priors
    # are dropped and the status stays "ok", not "partial".
    page1 = fake_result(
        html='<a rel="next" href="/shop?page=2">Next</a>' + LONG_TEXT,
        links={"internal": [{"href": "https://x.sk/still-here/", "text": "Coffee"}]},
        url="https://x.sk/shop",
    )
    page2 = fake_result(
        html=LONG_TEXT,  # no further next link -> natural end
        links={"internal": [{"href": "https://x.sk/also-here/", "text": "Coffee"}]},
        url="https://x.sk/shop?page=2",
    )
    crawler = FakeCrawler(
        {
            "https://x.sk/shop": page1,
            "https://x.sk/shop?page=2": page2,
            "https://x.sk/still-here/": fake_result(markdown=fake_markdown(LONG_TEXT + " 9,00 €")),
            "https://x.sk/also-here/": fake_result(markdown=fake_markdown(LONG_TEXT + " 10,00 €")),
        }
    )
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        fake_completion([fake_tool_call("extract_product", {"name": "Still Here", "packaging": [{"price": "9,00 €"}]})]),
        fake_completion([fake_tool_call("extract_product", {"name": "Also Here", "packaging": [{"price": "10,00 €"}]})]),
    ]
    roaster = dict(ROASTER, scrape_url="https://x.sk/shop")
    existing = [
        {
            "name": "Old Coffee",
            "url": "https://x.sk/old-coffee/",
            "status": "ok",
            "last_seen": "2026-07-01",
            "page_hash": "deadbeef",
            "packaging": [{"weight_g": 250, "price": 9.0}],
        }
    ]
    entries, status = await scrape.process_roaster(crawler, client, roaster, existing, "2026-07-04")
    assert status == "ok"
    assert {e["url"] for e in entries} == {"https://x.sk/still-here/", "https://x.sk/also-here/"}


@pytest.mark.asyncio
async def test_process_roaster_keeps_existing_entries_on_listing_failure():
    crawler = FakeCrawler({})  # listing fetch fails
    client = MagicMock()
    existing = [{"name": "Old Coffee", "url": "https://x.sk/old-coffee/"}]
    entries, status = await scrape.process_roaster(crawler, client, ROASTER, existing, "2026-07-04")
    assert status == "failed"
    assert entries == existing
    client.chat.completions.create.assert_not_called()


@pytest.mark.asyncio
async def test_process_roaster_keeps_good_product_when_extraction_declines():
    # A previously-good product whose page still hashes differently, but the model
    # declines this time — must not clobber the known-good data.
    crawler = FakeCrawler(
        {
            "https://x.sk/": listing_result(["https://x.sk/rwanda/"]),
            "https://x.sk/rwanda/": fake_result(markdown=fake_markdown(LONG_TEXT + " changed")),
        }
    )
    client = MagicMock()
    client.chat.completions.create.return_value = fake_completion(
        content="This page no longer shows a specific coffee product."
    )  # explicit decline, no tool call
    existing = [
        {
            "name": "Rwanda",
            "url": "https://x.sk/rwanda/",
            "status": "ok",
            "last_seen": "2026-07-01",
            "page_hash": "old-hash-does-not-match",
            "packaging": [{"weight_g": 250, "price": 12.5}],
        }
    ]
    entries, status = await scrape.process_roaster(crawler, client, ROASTER, existing, "2026-07-04")
    assert status == "ok"
    assert entries == existing  # untouched, not downgraded


@pytest.mark.asyncio
async def test_process_roaster_keeps_good_product_when_extraction_fails_ambiguously():
    # No tool call AND no textual decline reason — extract_product raises
    # ExtractionFailed rather than being treated as a confident decline.
    # Same protection as a real decline: a previously-good product must not
    # be clobbered by an ambiguous/failed extraction.
    crawler = FakeCrawler(
        {
            "https://x.sk/": listing_result(["https://x.sk/rwanda/"]),
            "https://x.sk/rwanda/": fake_result(markdown=fake_markdown(LONG_TEXT + " changed")),
        }
    )
    client = MagicMock()
    client.chat.completions.create.return_value = fake_completion()  # empty, ambiguous
    existing = [
        {
            "name": "Rwanda",
            "url": "https://x.sk/rwanda/",
            "status": "ok",
            "last_seen": "2026-07-01",
            "page_hash": "old-hash-does-not-match",
            "packaging": [{"weight_g": 250, "price": 12.5}],
        }
    ]
    entries, status = await scrape.process_roaster(crawler, client, ROASTER, existing, "2026-07-04")
    assert status == "ok"
    assert entries == existing  # untouched, not downgraded, not cached as not_a_product


@pytest.mark.asyncio
async def test_process_roaster_does_not_cache_not_a_product_on_ambiguous_failure():
    # Without an existing prior, an ambiguous/failed extraction must not
    # produce a not_a_product cache entry either — it should simply yield no
    # entry for the url, leaving it eligible for retry on the next run.
    markdown_text = LONG_TEXT + " some page"
    crawler = FakeCrawler(
        {
            "https://x.sk/": listing_result(["https://x.sk/mystery/"]),
            "https://x.sk/mystery/": fake_result(markdown=fake_markdown(markdown_text)),
        }
    )
    client = MagicMock()
    client.chat.completions.create.return_value = fake_completion()  # empty, ambiguous

    entries, status = await scrape.process_roaster(crawler, client, ROASTER, [], "2026-07-04")
    assert status == "ok"
    assert entries == []


@pytest.mark.asyncio
async def test_process_roaster_reclassifies_stale_incomplete_when_confidently_not_coffee():
    # The model DID extract a name this run (unlike a bare decline) — our own
    # is_coffee() rejects it. That's a confident, deterministic
    # classification (e.g. a NON_COFFEE_KEYWORDS addition catching a gift
    # set that slipped through before) and must reclassify the stale
    # incomplete entry to not_a_product, not protect it forever.
    crawler = FakeCrawler(
        {
            "https://x.sk/": listing_result(["https://x.sk/tasting-set/"]),
            "https://x.sk/tasting-set/": fake_result(markdown=fake_markdown(LONG_TEXT + " changed")),
        }
    )
    client = MagicMock()
    client.chat.completions.create.return_value = fake_completion(
        [fake_tool_call("extract_product", {"name": "Degustačný balíček", "packaging": [{"price": "32,90 €"}]})]
    )
    existing = [
        {
            "name": "Degustačný balíček",
            "url": "https://x.sk/tasting-set/",
            "status": "incomplete",
            "missing_fields": ["origin", "roast_type"],
            "last_seen": "2026-07-01",
            "page_hash": "old-hash-does-not-match",
            "packaging": [{"weight_g": None, "price": 32.9}],
            "schema_version": scrape.SCHEMA_VERSION,
        }
    ]
    entries, status = await scrape.process_roaster(crawler, client, ROASTER, existing, "2026-07-04")
    assert status == "ok"
    assert entries[0]["status"] == "not_a_product"
    assert entries[0]["last_seen"] == "2026-07-04"


@pytest.mark.asyncio
async def test_process_roaster_caches_not_a_product_to_avoid_repeat_calls():
    markdown_text = LONG_TEXT + " category page"
    crawler = FakeCrawler(
        {
            "https://x.sk/": listing_result(["https://x.sk/kava/"]),
            "https://x.sk/kava/": fake_result(markdown=fake_markdown(markdown_text)),
        }
    )
    client = MagicMock()
    client.chat.completions.create.return_value = fake_completion(
        content="This is a category/listing page, not a single coffee product."
    )  # explicit decline

    entries, _ = await scrape.process_roaster(crawler, client, ROASTER, [], "2026-07-04")
    assert entries[0]["status"] == "not_a_product"
    assert client.chat.completions.create.call_count == 1

    # Second run, page unchanged: must not call the model again.
    entries2, _ = await scrape.process_roaster(crawler, client, ROASTER, entries, "2026-07-05")
    assert client.chat.completions.create.call_count == 1
    assert entries2[0]["last_seen"] == "2026-07-05"


@pytest.mark.asyncio
async def test_process_roaster_zero_discovered_with_existing_is_needs_js_not_wipeout():
    crawler = FakeCrawler({"https://x.sk/": listing_result([])})
    client = MagicMock()
    existing = [{"name": "Old Coffee", "url": "https://x.sk/old-coffee/"}]
    entries, status = await scrape.process_roaster(crawler, client, ROASTER, existing, "2026-07-04")
    assert status == "needs_js"
    assert entries == existing


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


# --- run() (checkpointing / per-roaster error isolation, issue #23) ---------


class FakeWebCrawler:
    """Duck-typed async-context-manager stand-in for crawl4ai's AsyncWebCrawler.

    run() only ever awaits `__aenter__`/`__aexit__` on it (via
    AsyncExitStack) before handing it to process_roaster — which is itself
    monkeypatched in these tests — so no arun()/network behavior is needed.
    """

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


def three_roasters():
    return [
        {"name": "Roaster One", "slug": "roaster-one", "url": "https://a.sk/", "scrape_url": "https://a.sk/", "metadata": {"city": "Bratislava"}},
        {"name": "Roaster Two", "slug": "roaster-two", "url": "https://b.sk/", "scrape_url": "https://b.sk/", "metadata": {"city": "Bratislava"}},
        {"name": "Roaster Three", "slug": "roaster-three", "url": "https://c.sk/", "scrape_url": "https://c.sk/", "metadata": {"city": "Bratislava"}},
    ]


def write_roasters_yaml(path, roasters):
    path.write_text(yaml.safe_dump({"roasters": roasters}))


@pytest.mark.asyncio
async def test_run_checkpoints_save_products_after_each_roaster(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(scrape, "AsyncWebCrawler", FakeWebCrawler)
    roasters = three_roasters()
    roasters_path = tmp_path / "roasters.yaml"
    write_roasters_yaml(roasters_path, roasters)
    products_path = tmp_path / "products.yaml"

    async def fake_process_roaster(crawler, client, roaster, existing_entries, today, max_pages=scrape.MAX_PAGES):
        return [{"name": roaster["name"], "url": roaster["url"] + "p"}], "ok"

    monkeypatch.setattr(scrape, "process_roaster", fake_process_roaster)

    save_calls = []
    real_save_products = scrape.save_products

    def spy_save_products(products, path=scrape.PRODUCTS_PATH):
        save_calls.append(len(products))
        return real_save_products(products, path)

    monkeypatch.setattr(scrape, "save_products", spy_save_products)

    await scrape.run(roasters_path=roasters_path, products_path=products_path, status_path=tmp_path / "scrape_status.yaml", history_path=tmp_path / "price_history.csv")

    # One checkpoint save per roaster, not just one at the very end — and
    # each successive checkpoint has one more roaster's worth of data than
    # the last, confirming it isn't just called 3 times with the same
    # (fully-built) dict.
    assert len(save_calls) == len(roasters)
    assert save_calls == [1, 2, 3]

    on_disk = scrape.load_products(products_path)
    assert set(on_disk.keys()) == {"roaster-one", "roaster-two", "roaster-three"}


@pytest.mark.asyncio
async def test_run_isolates_roaster_exception_and_continues(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(scrape, "AsyncWebCrawler", FakeWebCrawler)
    roasters = three_roasters()
    roasters_path = tmp_path / "roasters.yaml"
    write_roasters_yaml(roasters_path, roasters)
    products_path = tmp_path / "products.yaml"

    async def fake_process_roaster(crawler, client, roaster, existing_entries, today, max_pages=scrape.MAX_PAGES):
        if roaster["slug"] == "roaster-two":
            raise ValueError("boom: simulated bug processing roaster two")
        return [{"name": roaster["name"], "url": roaster["url"] + "p"}], "ok"

    monkeypatch.setattr(scrape, "process_roaster", fake_process_roaster)

    # Should not raise — the exception on roaster-two must be caught and
    # isolated, letting roaster-three still be processed.
    await scrape.run(roasters_path=roasters_path, products_path=products_path, status_path=tmp_path / "scrape_status.yaml", history_path=tmp_path / "price_history.csv")

    on_disk = scrape.load_products(products_path)
    assert on_disk["roaster-one"] == [{"name": "Roaster One", "url": "https://a.sk/p"}]
    # roaster-two blew up before producing any entries — no data invented,
    # existing (empty, first-run) entries preserved as-is.
    assert on_disk["roaster-two"] == []
    assert on_disk["roaster-three"] == [{"name": "Roaster Three", "url": "https://c.sk/p"}]


@pytest.mark.asyncio
async def test_run_records_failed_status_for_roaster_that_raised(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(scrape, "AsyncWebCrawler", FakeWebCrawler)
    roasters = three_roasters()
    roasters_path = tmp_path / "roasters.yaml"
    write_roasters_yaml(roasters_path, roasters)
    products_path = tmp_path / "products.yaml"

    async def fake_process_roaster(crawler, client, roaster, existing_entries, today, max_pages=scrape.MAX_PAGES):
        if roaster["slug"] == "roaster-two":
            raise RuntimeError("simulated failure")
        return [], "ok"

    monkeypatch.setattr(scrape, "process_roaster", fake_process_roaster)

    await scrape.run(roasters_path=roasters_path, products_path=products_path, status_path=tmp_path / "scrape_status.yaml", history_path=tmp_path / "price_history.csv")

    out = capsys.readouterr().out
    assert "Roaster One: ok" in out
    assert "Roaster Two: failed" in out
    assert "Roaster Three: ok" in out
    # issue #38: every summary line carries the roaster's own processing
    # duration so a run creeping toward the job timeout shows which
    # roasters to look at.
    assert re.search(r"Roaster One: ok \(\d+s\)", out)
    assert re.search(r"Roaster Two: failed \(\d+s\)", out)


@pytest.mark.asyncio
async def test_run_preserves_prior_roaster_entries_when_it_later_raises(monkeypatch, tmp_path):
    # A roaster that previously had good data, and this run's process_roaster
    # call blows up before returning anything: the crash must not wipe out
    # that roaster's existing products.yaml entries.
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(scrape, "AsyncWebCrawler", FakeWebCrawler)
    roasters = [
        {"name": "Roaster Two", "slug": "roaster-two", "url": "https://b.sk/", "scrape_url": "https://b.sk/", "metadata": {"city": "Bratislava"}},
    ]
    roasters_path = tmp_path / "roasters.yaml"
    write_roasters_yaml(roasters_path, roasters)
    products_path = tmp_path / "products.yaml"
    prior_entry = {
        "name": "Old Coffee",
        "url": "https://b.sk/old-coffee/",
        "origin": "Rwanda",
        "process": None,
        "roast_type": "filter",
        "status": "ok",
        "last_seen": "2026-07-01",
        "page_hash": "abc123",
        "packaging": [{"weight_g": 250, "price": 12.5}],
        "schema_version": scrape.SCHEMA_VERSION,
    }
    scrape.save_products({"roaster-two": [prior_entry]}, products_path)

    async def fake_process_roaster(crawler, client, roaster, existing_entries, today, max_pages=scrape.MAX_PAGES):
        raise ValueError("boom")

    monkeypatch.setattr(scrape, "process_roaster", fake_process_roaster)

    await scrape.run(roasters_path=roasters_path, products_path=products_path, status_path=tmp_path / "scrape_status.yaml", history_path=tmp_path / "price_history.csv")

    on_disk = scrape.load_products(products_path)
    assert on_disk["roaster-two"] == [prior_entry]


@pytest.mark.asyncio
async def test_run_checkpointing_survives_later_fatal_crash(monkeypatch, tmp_path):
    # Simulates a genuinely-fatal crash that happens OUTSIDE the per-roaster
    # try/except (e.g. a disk error in save_products itself) partway through
    # the run — the whole point of per-roaster checkpointing (issue #23) is
    # that the roasters processed before the crash are already durably on
    # disk, not just held in memory.
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(scrape, "AsyncWebCrawler", FakeWebCrawler)
    roasters = three_roasters()
    roasters_path = tmp_path / "roasters.yaml"
    write_roasters_yaml(roasters_path, roasters)
    products_path = tmp_path / "products.yaml"

    async def fake_process_roaster(crawler, client, roaster, existing_entries, today, max_pages=scrape.MAX_PAGES):
        return [{"name": roaster["name"], "url": roaster["url"] + "p"}], "ok"

    monkeypatch.setattr(scrape, "process_roaster", fake_process_roaster)

    real_save_products = scrape.save_products
    call_count = {"n": 0}

    def crashing_save_products(products, path=scrape.PRODUCTS_PATH):
        call_count["n"] += 1
        if call_count["n"] == 3:
            raise OSError("simulated disk failure on the third checkpoint")
        return real_save_products(products, path)

    monkeypatch.setattr(scrape, "save_products", crashing_save_products)

    with pytest.raises(OSError):
        await scrape.run(roasters_path=roasters_path, products_path=products_path, status_path=tmp_path / "scrape_status.yaml", history_path=tmp_path / "price_history.csv")

    # The crash happened on the 3rd checkpoint write, so the 2nd checkpoint
    # (roaster-one + roaster-two) already made it to disk before the crash.
    on_disk = scrape.load_products(products_path)
    assert set(on_disk.keys()) == {"roaster-one", "roaster-two"}


# --- run() cross-roaster concurrency (issue #27) -----------------------------


@pytest.mark.asyncio
async def test_run_processes_roasters_concurrently_not_sequentially(monkeypatch, tmp_path):
    # Give each fake process_roaster a real await point (like a genuine
    # network fetch would be) so the event loop actually gets a chance to
    # interleave them. A strictly sequential run() would produce
    # start/end/start/end/start/end; true concurrency produces every
    # "start" before any "end" (all 3 roasters overlap).
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(scrape, "AsyncWebCrawler", FakeWebCrawler)
    # This test needs asyncio.sleep(0) to genuinely yield control (to prove
    # real interleaving) — undo the autouse fixture's no-op stub, which
    # would otherwise also swallow this explicit sleep(0) since it patches
    # the same shared asyncio module object that `import asyncio` above
    # refers to. process_roaster itself is fully replaced by the fake
    # below, so no *real* politeness delay is at risk of firing here.
    monkeypatch.setattr(scrape.asyncio, "sleep", _REAL_ASYNCIO_SLEEP)
    roasters = three_roasters()
    roasters_path = tmp_path / "roasters.yaml"
    write_roasters_yaml(roasters_path, roasters)
    products_path = tmp_path / "products.yaml"

    events = []
    in_flight = {"current": 0, "peak": 0}

    async def fake_process_roaster(crawler, client, roaster, existing_entries, today, max_pages=scrape.MAX_PAGES):
        events.append(("start", roaster["slug"]))
        in_flight["current"] += 1
        in_flight["peak"] = max(in_flight["peak"], in_flight["current"])
        await asyncio.sleep(0)  # yields control, standing in for real network I/O
        in_flight["current"] -= 1
        events.append(("end", roaster["slug"]))
        return [{"name": roaster["name"], "url": roaster["url"] + "p"}], "ok"

    monkeypatch.setattr(scrape, "process_roaster", fake_process_roaster)

    await scrape.run(roasters_path=roasters_path, products_path=products_path, status_path=tmp_path / "scrape_status.yaml", history_path=tmp_path / "price_history.csv")

    starts = [i for i, (kind, _) in enumerate(events) if kind == "start"]
    ends = [i for i, (kind, _) in enumerate(events) if kind == "end"]
    assert len(starts) == len(ends) == 3
    assert max(starts) < min(ends), f"expected all starts before any end, got {events}"
    assert in_flight["peak"] >= 2  # genuinely overlapped, not one-at-a-time

    # Checkpointing still lands every roaster's data correctly under
    # concurrency, whatever order they actually completed in.
    on_disk = scrape.load_products(products_path)
    assert on_disk == {
        "roaster-one": [{"name": "Roaster One", "url": "https://a.sk/p"}],
        "roaster-two": [{"name": "Roaster Two", "url": "https://b.sk/p"}],
        "roaster-three": [{"name": "Roaster Three", "url": "https://c.sk/p"}],
    }


@pytest.mark.asyncio
async def test_run_respects_cross_roaster_concurrency_limit(monkeypatch, tmp_path):
    # More roasters than CROSS_ROASTER_CONCURRENCY — peak concurrent
    # in-flight processing must never exceed the semaphore's limit.
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(scrape, "AsyncWebCrawler", FakeWebCrawler)
    # See test_run_processes_roasters_concurrently_not_sequentially: restore
    # real asyncio.sleep so this test's own sleep(0) actually yields.
    monkeypatch.setattr(scrape.asyncio, "sleep", _REAL_ASYNCIO_SLEEP)
    roasters = [
        {"name": f"Roaster {i}", "slug": f"roaster-{i}", "url": f"https://r{i}.sk/", "scrape_url": f"https://r{i}.sk/", "metadata": {"city": "Bratislava"}}
        for i in range(scrape.CROSS_ROASTER_CONCURRENCY * 2)
    ]
    roasters_path = tmp_path / "roasters.yaml"
    write_roasters_yaml(roasters_path, roasters)
    products_path = tmp_path / "products.yaml"

    in_flight = {"current": 0, "peak": 0}

    async def fake_process_roaster(crawler, client, roaster, existing_entries, today, max_pages=scrape.MAX_PAGES):
        in_flight["current"] += 1
        in_flight["peak"] = max(in_flight["peak"], in_flight["current"])
        await asyncio.sleep(0)
        in_flight["current"] -= 1
        return [], "ok"

    monkeypatch.setattr(scrape, "process_roaster", fake_process_roaster)

    await scrape.run(roasters_path=roasters_path, products_path=products_path, status_path=tmp_path / "scrape_status.yaml", history_path=tmp_path / "price_history.csv")

    assert in_flight["peak"] == scrape.CROSS_ROASTER_CONCURRENCY


@pytest.mark.asyncio
async def test_run_isolates_roaster_exception_under_real_concurrency(monkeypatch, tmp_path):
    # Same guarantee as test_run_isolates_roaster_exception_and_continues,
    # but with a real await point in each fake process_roaster so the
    # roasters genuinely overlap — a raise inside one concurrently-running
    # task must not cancel or otherwise disturb the others.
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(scrape, "AsyncWebCrawler", FakeWebCrawler)
    # See test_run_processes_roasters_concurrently_not_sequentially: restore
    # real asyncio.sleep so this test's own sleep(0) actually yields.
    monkeypatch.setattr(scrape.asyncio, "sleep", _REAL_ASYNCIO_SLEEP)
    roasters = three_roasters()
    roasters_path = tmp_path / "roasters.yaml"
    write_roasters_yaml(roasters_path, roasters)
    products_path = tmp_path / "products.yaml"

    async def fake_process_roaster(crawler, client, roaster, existing_entries, today, max_pages=scrape.MAX_PAGES):
        await asyncio.sleep(0)
        if roaster["slug"] == "roaster-two":
            raise ValueError("boom: simulated bug processing roaster two")
        await asyncio.sleep(0)
        return [{"name": roaster["name"], "url": roaster["url"] + "p"}], "ok"

    monkeypatch.setattr(scrape, "process_roaster", fake_process_roaster)

    # Should not raise — the exception on roaster-two must be caught and
    # isolated, letting roaster-one and roaster-three still complete.
    await scrape.run(roasters_path=roasters_path, products_path=products_path, status_path=tmp_path / "scrape_status.yaml", history_path=tmp_path / "price_history.csv")

    on_disk = scrape.load_products(products_path)
    assert on_disk["roaster-one"] == [{"name": "Roaster One", "url": "https://a.sk/p"}]
    assert on_disk["roaster-two"] == []
    assert on_disk["roaster-three"] == [{"name": "Roaster Three", "url": "https://c.sk/p"}]


@pytest.mark.asyncio
async def test_run_checkpoint_lock_serializes_concurrent_saves(monkeypatch, tmp_path):
    # Every roaster's checkpoint save dumps the WHOLE products dict —
    # instrument save_products to detect any overlap between two
    # concurrent calls (which would indicate a torn/interleaved write).
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(scrape, "AsyncWebCrawler", FakeWebCrawler)
    # See test_run_processes_roasters_concurrently_not_sequentially: restore
    # real asyncio.sleep so this test's own sleep(0) actually yields.
    monkeypatch.setattr(scrape.asyncio, "sleep", _REAL_ASYNCIO_SLEEP)
    roasters = three_roasters()
    roasters_path = tmp_path / "roasters.yaml"
    write_roasters_yaml(roasters_path, roasters)
    products_path = tmp_path / "products.yaml"

    async def fake_process_roaster(crawler, client, roaster, existing_entries, today, max_pages=scrape.MAX_PAGES):
        await asyncio.sleep(0)
        return [{"name": roaster["name"], "url": roaster["url"] + "p"}], "ok"

    monkeypatch.setattr(scrape, "process_roaster", fake_process_roaster)

    real_save_products = scrape.save_products
    concurrent_calls = {"active": 0, "max_overlap": 0}

    def instrumented_save_products(products, path=scrape.PRODUCTS_PATH):
        concurrent_calls["active"] += 1
        concurrent_calls["max_overlap"] = max(concurrent_calls["max_overlap"], concurrent_calls["active"])
        try:
            return real_save_products(products, path)
        finally:
            concurrent_calls["active"] -= 1

    monkeypatch.setattr(scrape, "save_products", instrumented_save_products)

    await scrape.run(roasters_path=roasters_path, products_path=products_path, status_path=tmp_path / "scrape_status.yaml", history_path=tmp_path / "price_history.csv")

    assert concurrent_calls["max_overlap"] == 1
    on_disk = scrape.load_products(products_path)
    assert set(on_disk.keys()) == {"roaster-one", "roaster-two", "roaster-three"}


# --- _require_openrouter_api_key ---------------------------------------------


def test_require_openrouter_api_key_missing_raises_clear_error(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        scrape._require_openrouter_api_key()


def test_require_openrouter_api_key_empty_raises_clear_error(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        scrape._require_openrouter_api_key()


def test_require_openrouter_api_key_present_returns_it(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-123")
    assert scrape._require_openrouter_api_key() == "sk-test-123"


@pytest.mark.asyncio
async def test_run_raises_fast_on_missing_api_key_before_processing_any_roaster(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(scrape, "AsyncWebCrawler", FakeWebCrawler)
    roasters = three_roasters()
    roasters_path = tmp_path / "roasters.yaml"
    write_roasters_yaml(roasters_path, roasters)
    products_path = tmp_path / "products.yaml"

    calls = []

    async def fake_process_roaster(crawler, client, roaster, existing_entries, today, max_pages=scrape.MAX_PAGES):
        calls.append(roaster["slug"])
        return [], "ok"

    monkeypatch.setattr(scrape, "process_roaster", fake_process_roaster)

    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        await scrape.run(roasters_path=roasters_path, products_path=products_path, status_path=tmp_path / "scrape_status.yaml", history_path=tmp_path / "price_history.csv")

    assert calls == []


# --- Observability (issue #28): GITHUB_STEP_SUMMARY, ::warning:: annotations,
# --- data/scrape_status.yaml persistence, and repeated-failure escalation ---


def _statuses_by_slug(*, ok=(), failed=(), needs_js=(), partial=()):
    result = {}
    for slug in ok:
        result[slug] = {"name": slug.replace("-", " ").title(), "status": "ok"}
    for slug in failed:
        result[slug] = {"name": slug.replace("-", " ").title(), "status": "failed"}
    for slug in needs_js:
        result[slug] = {"name": slug.replace("-", " ").title(), "status": "needs_js"}
    for slug in partial:
        result[slug] = {"name": slug.replace("-", " ").title(), "status": "partial"}
    return result


def test_write_github_step_summary_writes_table(tmp_path):
    summary_path = tmp_path / "step_summary.md"
    statuses = _statuses_by_slug(ok=["kavoholik"], failed=["broken-roaster"], needs_js=["js-roaster"])

    scrape.write_github_step_summary(statuses, summary_path=str(summary_path))

    content = summary_path.read_text()
    assert "## Scrape run health" in content
    assert "| Roaster | Status | Note |" in content
    assert "Kavoholik" in content and "| ok |" in content
    assert "Broken Roaster" in content and "| failed |" in content
    assert "Js Roaster" in content and "| needs_js |" in content


def test_write_github_step_summary_appends_not_overwrites(tmp_path):
    summary_path = tmp_path / "step_summary.md"
    summary_path.write_text("# Previous step's summary\n")
    statuses = _statuses_by_slug(ok=["kavoholik"])

    scrape.write_github_step_summary(statuses, summary_path=str(summary_path))

    content = summary_path.read_text()
    assert content.startswith("# Previous step's summary\n")
    assert "## Scrape run health" in content


def test_write_github_step_summary_reads_env_var_when_no_path_given(monkeypatch, tmp_path):
    summary_path = tmp_path / "step_summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_path))
    statuses = _statuses_by_slug(failed=["broken-roaster"])

    scrape.write_github_step_summary(statuses)

    assert "Broken Roaster" in summary_path.read_text()


def test_write_github_step_summary_noop_without_env_var(monkeypatch):
    # Not set locally (guard case from the issue) — must not raise, must not
    # try to write anywhere.
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    scrape.write_github_step_summary(_statuses_by_slug(ok=["kavoholik"]))  # no exception


def test_emit_warning_annotations_only_for_non_ok(capsys):
    statuses = _statuses_by_slug(ok=["kavoholik"], failed=["broken-roaster"], needs_js=["js-roaster"])

    scrape.emit_warning_annotations(statuses)

    out = capsys.readouterr().out
    assert "::warning::Roaster 'Broken Roaster' has status 'failed'" in out
    assert "::warning::Roaster 'Js Roaster' has status 'needs_js'" in out
    assert "Kavoholik" not in out


def test_emit_warning_annotations_silent_when_all_ok(capsys):
    scrape.emit_warning_annotations(_statuses_by_slug(ok=["kavoholik", "ready-after"]))
    assert capsys.readouterr().out == ""


# --- build_scrape_status_records --------------------------------------------


def test_build_scrape_status_records_first_ok_run_has_zero_streak():
    records = scrape.build_scrape_status_records(
        _statuses_by_slug(ok=["kavoholik"]), "2026-07-06", previous=None
    )
    assert records["kavoholik"] == {
        "name": "Kavoholik",
        "status": "ok",
        "last_run": "2026-07-06",
        "consecutive_non_ok": 0,
    }


def test_build_scrape_status_records_increments_streak_across_two_failed_runs():
    # Simulate two consecutive scrape runs where the same roaster stays
    # "failed" both times.
    run1 = scrape.build_scrape_status_records(
        _statuses_by_slug(failed=["broken-roaster"]), "2026-07-06", previous=None
    )
    assert run1["broken-roaster"]["consecutive_non_ok"] == 1

    run2 = scrape.build_scrape_status_records(
        _statuses_by_slug(failed=["broken-roaster"]), "2026-07-13", previous=run1
    )
    assert run2["broken-roaster"]["consecutive_non_ok"] == 2
    assert run2["broken-roaster"]["last_run"] == "2026-07-13"
    assert run2["broken-roaster"]["status"] == "failed"


def test_build_scrape_status_records_resets_streak_on_recovery():
    run1 = scrape.build_scrape_status_records(
        _statuses_by_slug(failed=["flaky-roaster"]), "2026-07-06", previous=None
    )
    assert run1["flaky-roaster"]["consecutive_non_ok"] == 1

    run2 = scrape.build_scrape_status_records(
        _statuses_by_slug(ok=["flaky-roaster"]), "2026-07-13", previous=run1
    )
    assert run2["flaky-roaster"]["consecutive_non_ok"] == 0
    assert run2["flaky-roaster"]["status"] == "ok"


def test_build_scrape_status_records_preserves_untouched_roasters():
    # A roaster not processed this run (e.g. --only filtered it out) keeps
    # its previous record untouched rather than being dropped.
    previous = {
        "untouched-roaster": {
            "name": "Untouched Roaster",
            "status": "failed",
            "last_run": "2026-06-01",
            "consecutive_non_ok": 5,
        }
    }
    records = scrape.build_scrape_status_records(
        _statuses_by_slug(ok=["kavoholik"]), "2026-07-06", previous=previous
    )
    assert records["untouched-roaster"] == previous["untouched-roaster"]
    assert records["kavoholik"]["consecutive_non_ok"] == 0


def test_build_scrape_status_records_partial_and_needs_js_count_as_non_ok():
    records = scrape.build_scrape_status_records(
        _statuses_by_slug(partial=["partial-roaster"], needs_js=["js-roaster"]),
        "2026-07-06",
        previous=None,
    )
    assert records["partial-roaster"]["consecutive_non_ok"] == 1
    assert records["js-roaster"]["consecutive_non_ok"] == 1


# --- load_scrape_status / save_scrape_status ---------------------------------


def test_save_and_load_scrape_status_roundtrip(tmp_path):
    path = tmp_path / "scrape_status.yaml"
    records = {
        "kavoholik": {"name": "Kavoholik", "status": "ok", "last_run": "2026-07-06", "consecutive_non_ok": 0},
        "broken-roaster": {
            "name": "Broken Roaster",
            "status": "failed",
            "last_run": "2026-07-06",
            "consecutive_non_ok": 3,
        },
    }
    scrape.save_scrape_status(records, path)

    loaded = scrape.load_scrape_status(path)
    assert loaded == records
    # Structural sanity check on the on-disk YAML shape.
    raw = yaml.safe_load(path.read_text())
    assert set(raw["broken-roaster"]) == {"name", "status", "last_run", "consecutive_non_ok"}


def test_load_scrape_status_missing_file_returns_empty_dict(tmp_path):
    assert scrape.load_scrape_status(tmp_path / "does-not-exist.yaml") == {}


def test_load_scrape_status_coerces_yaml_date_back_to_string(tmp_path):
    path = tmp_path / "scrape_status.yaml"
    path.write_text("roaster:\n  name: Roaster\n  status: failed\n  last_run: 2026-07-06\n  consecutive_non_ok: 1\n")
    loaded = scrape.load_scrape_status(path)
    assert loaded["roaster"]["last_run"] == "2026-07-06"
    assert isinstance(loaded["roaster"]["last_run"], str)


# --- escalate_repeated_failures -----------------------------------------------


def test_escalate_repeated_failures_prints_error_at_threshold(capsys):
    records = {
        "broken-roaster": {
            "name": "Broken Roaster",
            "status": "failed",
            "last_run": "2026-07-06",
            "consecutive_non_ok": 3,
        },
        "flaky-roaster": {
            "name": "Flaky Roaster",
            "status": "needs_js",
            "last_run": "2026-07-06",
            "consecutive_non_ok": 2,
        },
    }
    scrape.escalate_repeated_failures(records)

    out = capsys.readouterr().out
    assert "::error::Roaster 'Broken Roaster' has been non-ok for 3 consecutive runs" in out
    assert "Flaky Roaster" not in out


def test_escalate_repeated_failures_silent_below_threshold(capsys):
    records = {
        "flaky-roaster": {
            "name": "Flaky Roaster",
            "status": "needs_js",
            "last_run": "2026-07-06",
            "consecutive_non_ok": 2,
        },
    }
    scrape.escalate_repeated_failures(records)
    assert capsys.readouterr().out == ""


def test_escalate_repeated_failures_respects_custom_threshold(capsys):
    records = {
        "roaster": {"name": "Roaster", "status": "failed", "last_run": "2026-07-06", "consecutive_non_ok": 1},
    }
    scrape.escalate_repeated_failures(records, threshold=1)
    assert "::error::Roaster 'Roaster' has been non-ok for 1 consecutive runs" in capsys.readouterr().out


# --- run() integration: scrape_status.yaml persisted end-to-end -------------


@pytest.mark.asyncio
async def test_run_persists_scrape_status_with_consecutive_non_ok_tracking(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(scrape, "AsyncWebCrawler", FakeWebCrawler)
    roasters = [
        {"name": "Broken Roaster", "slug": "broken-roaster", "url": "https://b.sk/", "scrape_url": "https://b.sk/", "metadata": {"city": "Bratislava"}},
        {"name": "Good Roaster", "slug": "good-roaster", "url": "https://g.sk/", "scrape_url": "https://g.sk/", "metadata": {"city": "Bratislava"}},
    ]
    roasters_path = tmp_path / "roasters.yaml"
    write_roasters_yaml(roasters_path, roasters)
    products_path = tmp_path / "products.yaml"
    status_path = tmp_path / "scrape_status.yaml"

    async def fake_process_roaster(crawler, client, roaster, existing_entries, today, max_pages=scrape.MAX_PAGES):
        if roaster["slug"] == "broken-roaster":
            return existing_entries, "failed"
        return [{"name": roaster["name"], "url": roaster["url"] + "p"}], "ok"

    monkeypatch.setattr(scrape, "process_roaster", fake_process_roaster)

    # Run 1: broken-roaster fails for the first time.
    await scrape.run(roasters_path=roasters_path, products_path=products_path, status_path=status_path, history_path=tmp_path / "price_history.csv")
    records = scrape.load_scrape_status(status_path)
    assert records["broken-roaster"]["status"] == "failed"
    assert records["broken-roaster"]["consecutive_non_ok"] == 1
    assert records["good-roaster"]["status"] == "ok"
    assert records["good-roaster"]["consecutive_non_ok"] == 0

    # Run 2: broken-roaster fails again — streak must climb to 2. Recreate
    # products.yaml's roaster entry so the second run starts from what the
    # first run actually persisted (mirrors a real second cron run).
    await scrape.run(roasters_path=roasters_path, products_path=products_path, status_path=status_path, history_path=tmp_path / "price_history.csv")
    records = scrape.load_scrape_status(status_path)
    assert records["broken-roaster"]["consecutive_non_ok"] == 2
    assert records["good-roaster"]["consecutive_non_ok"] == 0


@pytest.mark.asyncio
async def test_run_resets_consecutive_non_ok_when_roaster_recovers(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(scrape, "AsyncWebCrawler", FakeWebCrawler)
    roasters = [
        {"name": "Flaky Roaster", "slug": "flaky-roaster", "url": "https://f.sk/", "scrape_url": "https://f.sk/", "metadata": {"city": "Bratislava"}},
    ]
    roasters_path = tmp_path / "roasters.yaml"
    write_roasters_yaml(roasters_path, roasters)
    products_path = tmp_path / "products.yaml"
    status_path = tmp_path / "scrape_status.yaml"

    call_count = {"n": 0}

    async def fake_process_roaster(crawler, client, roaster, existing_entries, today, max_pages=scrape.MAX_PAGES):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return existing_entries, "failed"
        return [{"name": roaster["name"], "url": roaster["url"] + "p"}], "ok"

    monkeypatch.setattr(scrape, "process_roaster", fake_process_roaster)

    await scrape.run(roasters_path=roasters_path, products_path=products_path, status_path=status_path, history_path=tmp_path / "price_history.csv")
    records = scrape.load_scrape_status(status_path)
    assert records["flaky-roaster"]["consecutive_non_ok"] == 1

    await scrape.run(roasters_path=roasters_path, products_path=products_path, status_path=status_path, history_path=tmp_path / "price_history.csv")
    records = scrape.load_scrape_status(status_path)
    assert records["flaky-roaster"]["status"] == "ok"
    assert records["flaky-roaster"]["consecutive_non_ok"] == 0


@pytest.mark.asyncio
async def test_run_emits_warning_and_writes_step_summary_for_non_ok_roaster(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "step_summary.md"))
    monkeypatch.setattr(scrape, "AsyncWebCrawler", FakeWebCrawler)
    roasters = [
        {"name": "Broken Roaster", "slug": "broken-roaster", "url": "https://b.sk/", "scrape_url": "https://b.sk/", "metadata": {"city": "Bratislava"}},
    ]
    roasters_path = tmp_path / "roasters.yaml"
    write_roasters_yaml(roasters_path, roasters)
    products_path = tmp_path / "products.yaml"
    status_path = tmp_path / "scrape_status.yaml"

    async def fake_process_roaster(crawler, client, roaster, existing_entries, today, max_pages=scrape.MAX_PAGES):
        return existing_entries, "failed"

    monkeypatch.setattr(scrape, "process_roaster", fake_process_roaster)

    await scrape.run(roasters_path=roasters_path, products_path=products_path, status_path=status_path, history_path=tmp_path / "price_history.csv")

    out = capsys.readouterr().out
    assert "::warning::Roaster 'Broken Roaster' has status 'failed'" in out

    summary_path = tmp_path / "step_summary.md"
    assert summary_path.exists()
    assert "Broken Roaster" in summary_path.read_text()


@pytest.mark.asyncio
async def test_run_escalates_after_three_consecutive_non_ok_runs(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(scrape, "AsyncWebCrawler", FakeWebCrawler)
    roasters = [
        {"name": "Broken Roaster", "slug": "broken-roaster", "url": "https://b.sk/", "scrape_url": "https://b.sk/", "metadata": {"city": "Bratislava"}},
    ]
    roasters_path = tmp_path / "roasters.yaml"
    write_roasters_yaml(roasters_path, roasters)
    products_path = tmp_path / "products.yaml"
    status_path = tmp_path / "scrape_status.yaml"

    async def fake_process_roaster(crawler, client, roaster, existing_entries, today, max_pages=scrape.MAX_PAGES):
        return existing_entries, "failed"

    monkeypatch.setattr(scrape, "process_roaster", fake_process_roaster)

    for _ in range(3):
        await scrape.run(roasters_path=roasters_path, products_path=products_path, status_path=status_path, history_path=tmp_path / "price_history.csv")

    out = capsys.readouterr().out
    assert "::error::Roaster 'Broken Roaster' has been non-ok for 3 consecutive runs" in out


# --- price history (issue #41) -------------------------------------------------


def _history_products():
    return {
        "roaster-a": [
            {
                "name": "Rwanda",
                "url": "https://a.sk/rwanda/",
                "status": "ok",
                "packaging": [{"weight_g": 250, "price": 12.5}, {"weight_g": 1000, "price": 39.0}],
            },
            {
                "name": "Mystery",
                "url": "https://a.sk/mystery/",
                "status": "incomplete",
                "packaging": [{"weight_g": 250, "price": None}],
            },
            {"url": "https://a.sk/kosik/", "status": "not_a_product"},
        ],
    }


def test_build_price_history_rows_records_every_ok_tier_on_first_run():
    rows = scrape.build_price_history_rows(_history_products(), "2026-07-12", {})
    # only the ok entry contributes — incomplete/not_a_product never do
    assert [(r["weight_g"], r["price"]) for r in rows] == [(250, 12.5), (1000, 39.0)]
    assert all(r["date"] == "2026-07-12" and r["roaster"] == "roaster-a" for r in rows)


def test_build_price_history_rows_appends_only_changed_prices():
    last = {
        ("roaster-a", "https://a.sk/rwanda/", 250, ""): 12.5,   # unchanged
        ("roaster-a", "https://a.sk/rwanda/", 1000, ""): 35.0,  # changed 35 -> 39
    }
    rows = scrape.build_price_history_rows(_history_products(), "2026-07-12", last)
    assert [(r["weight_g"], r["price"]) for r in rows] == [(1000, 39.0)]


def test_build_price_history_rows_treats_distinct_variants_as_distinct_keys():
    # Two tiers sharing a weight but with different `variant` labels (e.g.
    # whole bean vs ground) must each get their own history key/row instead
    # of colliding into one.
    products = {
        "roaster-a": [
            {
                "name": "Decaf",
                "url": "https://a.sk/decaf/",
                "status": "ok",
                "packaging": [
                    {"weight_g": 1000, "price": 34.0, "variant": "Whole bean"},
                    {"weight_g": 1000, "price": 48.0, "variant": "Ground"},
                ],
            },
        ],
    }
    last = {("roaster-a", "https://a.sk/decaf/", 1000, "Whole bean"): 34.0}
    rows = scrape.build_price_history_rows(products, "2026-07-12", last)
    # Only the ground tier is new/changed — the whole-bean tier's price is
    # unchanged and must not be re-recorded just because a same-weight
    # sibling tier exists.
    assert [(r["price"], r["variant"]) for r in rows] == [(48.0, "Ground")]


def test_price_history_round_trip_last_wins(tmp_path):
    path = tmp_path / "price_history.csv"
    scrape.append_price_history(
        [
            {"date": "2026-07-05", "roaster": "r", "url": "https://a.sk/x/", "weight_g": 250, "price": 10.0, "name": "X"},
        ],
        path,
    )
    scrape.append_price_history(
        [
            {"date": "2026-07-12", "roaster": "r", "url": "https://a.sk/x/", "weight_g": 250, "price": 11.0, "name": "X"},
        ],
        path,
    )
    assert path.read_text().splitlines()[0] == "date,roaster,url,weight_g,price,name,variant"  # header once
    last = scrape.load_last_known_prices(path)
    assert last == {("r", "https://a.sk/x/", 250, ""): 11.0}


def test_price_history_migrated_header_resolves_legacy_rows_to_blank_variant(tmp_path):
    # A file written before this column existed has a 6-name header and
    # 6-field rows; migrating just the header line (the only change this
    # fix makes to the real committed file, no per-row backfill) must still
    # let old rows load correctly, with their missing variant resolving to
    # the same "" key new variant-less tiers use.
    path = tmp_path / "price_history.csv"
    path.write_text(
        "date,roaster,url,weight_g,price,name,variant\n"
        "2026-07-05,r,https://a.sk/x/,250,10.0,X\n"
    )
    assert scrape.load_last_known_prices(path) == {("r", "https://a.sk/x/", 250, ""): 10.0}


def test_price_history_unmigrated_header_silently_drops_variant_not_crashes(tmp_path):
    # Documents exactly why the header migration (old 6-name header ->
    # 7-name header, done once as a pure text edit to the real committed
    # file) is required rather than optional: appending a 7-field row under
    # the OLD 6-name header doesn't raise — csv.DictReader stuffs the extra
    # value under a `None` key instead — so the row's variant is silently
    # lost (falls back to "", same as a genuinely variant-less tier) rather
    # than the read failing loudly. Locks in this degrade-not-crash
    # behavior so it isn't accidentally "fixed" into a KeyError later.
    path = tmp_path / "price_history.csv"
    path.write_text(
        "date,roaster,url,weight_g,price,name\n"
        "2026-07-05,r,https://a.sk/x/,1000,48.0,X,Ground\n"
    )
    assert scrape.load_last_known_prices(path) == {("r", "https://a.sk/x/", 1000, ""): 48.0}


def test_append_price_history_no_rows_is_a_no_op(tmp_path):
    path = tmp_path / "price_history.csv"
    scrape.append_price_history([], path)
    assert not path.exists()  # a no-change week must not create/touch the file


def test_load_last_known_prices_skips_malformed_rows(tmp_path):
    path = tmp_path / "price_history.csv"
    path.write_text(
        "date,roaster,url,weight_g,price,name,variant\n"
        "2026-07-05,r,https://a.sk/x/,250,10.0,X,\n"
        "2026-07-06,r,https://a.sk/x/,not-a-weight,11.0,X,\n"
    )
    assert scrape.load_last_known_prices(path) == {("r", "https://a.sk/x/", 250, ""): 10.0}


@pytest.mark.asyncio
async def test_run_appends_price_history_for_ok_products(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(scrape, "AsyncWebCrawler", FakeWebCrawler)
    roasters = [
        {"name": "Roaster A", "slug": "roaster-a", "url": "https://a.sk/", "scrape_url": "https://a.sk/", "metadata": {"city": "Bratislava"}},
    ]
    roasters_path = tmp_path / "roasters.yaml"
    write_roasters_yaml(roasters_path, roasters)
    history_path = tmp_path / "price_history.csv"

    async def fake_process_roaster(crawler, client, roaster, existing_entries, today, max_pages=scrape.MAX_PAGES):
        return [
            {
                "name": "Rwanda",
                "url": "https://a.sk/rwanda/",
                "status": "ok",
                "last_seen": today,
                "page_hash": "h",
                "packaging": [{"weight_g": 250, "price": 12.5}],
                "schema_version": scrape.SCHEMA_VERSION,
            }
        ], "ok"

    monkeypatch.setattr(scrape, "process_roaster", fake_process_roaster)

    await scrape.run(roasters_path=roasters_path, products_path=tmp_path / "products.yaml", status_path=tmp_path / "scrape_status.yaml", history_path=history_path)
    lines = history_path.read_text().splitlines()
    assert len(lines) == 2  # header + one observation

    # identical second run appends nothing
    await scrape.run(roasters_path=roasters_path, products_path=tmp_path / "products.yaml", status_path=tmp_path / "scrape_status.yaml", history_path=history_path)
    assert len(history_path.read_text().splitlines()) == 2


# --- LLM usage tracking + canary (issue #62) ------------------------------------


def _usage_response(prompt=100, completion=20):
    resp = fake_completion(
        [fake_tool_call("extract_product", {"name": "Rwanda", "packaging": [{"price": "12,50 €"}]})]
    )
    resp.usage = SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion)
    return resp


def test_record_usage_accumulates_and_reports(tmp_path):
    scrape._reset_usage()
    client = MagicMock()
    client.chat.completions.create.return_value = _usage_response(100, 20)
    scrape.extract_product(client, "https://x.sk/a/", "markdown")
    scrape.extract_product(client, "https://x.sk/b/", "markdown")
    assert scrape.LLM_USAGE == {"calls": 2, "prompt_tokens": 200, "completion_tokens": 40}

    summary = tmp_path / "summary.md"
    scrape.report_llm_usage(summary_path=str(summary))
    assert "2 call(s), 200 prompt / 40 completion tokens" in summary.read_text()
    scrape._reset_usage()


def test_record_usage_tolerates_missing_or_mock_usage():
    scrape._reset_usage()
    client = MagicMock()
    # MagicMock auto-attributes are not ints — must count the call but add 0.
    client.chat.completions.create.return_value = fake_completion(
        [fake_tool_call("extract_product", {"name": "Rwanda", "packaging": [{"price": "1 €"}]})]
    )
    scrape.extract_product(client, "https://x.sk/a/", "markdown")
    assert scrape.LLM_USAGE["calls"] == 1
    assert scrape.LLM_USAGE["prompt_tokens"] == 0
    scrape._reset_usage()


def _canary_client(arguments):
    client = MagicMock()
    client.chat.completions.create.return_value = fake_completion(
        [fake_tool_call("extract_product", arguments)]
    )
    return client


CANARY_GOOD_ARGS = {
    "name": "Colombia El Canario",
    "origin": "Kolumbia",
    "process": "natural",
    "roast_type": "filter",
    "packaging": [{"price": "12,50 €", "weight": "250 g"}],
}


def test_run_canary_passes_on_expected_extraction(capsys):
    assert scrape.run_canary(_canary_client(CANARY_GOOD_ARGS)) is True
    out = capsys.readouterr().out
    assert "LLM canary: ok" in out
    assert "::warning::" not in out


def test_run_canary_warns_on_field_drift(capsys):
    args = dict(CANARY_GOOD_ARGS, origin="Brazil")  # wrong on purpose
    assert scrape.run_canary(_canary_client(args)) is False
    out = capsys.readouterr().out
    assert "::warning::LLM canary: extraction drift" in out
    assert "origin" in out


def test_run_canary_warns_on_decline(capsys):
    client = MagicMock()
    client.chat.completions.create.return_value = fake_completion(content="not a product page")
    assert scrape.run_canary(client) is False
    assert "::warning::LLM canary: model declined" in capsys.readouterr().out


# ── Data integrity: stored origins stay canonical (see also issue #14) ──────
# normalize_origin() gates new extractions through coffee_origins.yaml, but
# entries written before that gating existed kept raw LLM text forever
# (hash-gating never re-extracts an unchanged page) — "Huila", "Svet",
# "Indonézie" and friends each became a bogus origin filter option and a
# mangled landing-page slug (/origins/indon-zie/). Guard the artifact
# itself so a regression from any cause fails CI, not just the normalizer.


def test_products_yaml_origins_are_canonical():
    products = scrape.load_products()
    canonical = set(scrape.load_country_aliases().values()) | {"Blend"}
    bad = [
        (slug, entry.get("name"), value)
        for slug, entries in products.items()
        for entry in entries
        for value in [entry.get("origin"), *(entry.get("blend_origins") or [])]
        if value is not None and value not in canonical
    ]
    assert bad == [], f"non-canonical origins stored in products.yaml: {bad}"


# ── Issue #143: non-coffee URL path & keyword filters ──────────────────────


def test_non_coffee_keywords_include_tea_and_accessories():
    assert "cajik" in scrape.NON_COFFEE_KEYWORDS
    assert "caj" in scrape.NON_COFFEE_KEYWORDS
    assert "čaj" in scrape.NON_COFFEE_KEYWORDS
    assert "zaváralo" in scrape.NON_COFFEE_KEYWORDS
    assert "termoska" in scrape.NON_COFFEE_KEYWORDS
    assert "použité" in scrape.NON_COFFEE_KEYWORDS
    assert "second hand" in scrape.NON_COFFEE_KEYWORDS
    assert "setkačka" in scrape.NON_COFFEE_KEYWORDS
    assert "káviar" in scrape.NON_COFFEE_KEYWORDS
    assert "kávica" in scrape.NON_COFFEE_KEYWORDS


def test_is_non_coffee_url_detects_teapots():
    assert scrape._is_non_coffee_url("https://example.sk/zaváralo/thermos") is True
    assert scrape._is_non_coffee_url("https://example.sk/termoska/classic") is True
    assert scrape._is_non_coffee_url("https://example.sk/príslušenstvo/filter") is True
    assert scrape._is_non_coffee_url("https://example.sk/accessories/mug") is True
    assert scrape._is_non_coffee_url("https://example.sk/gear/pump") is True


def test_is_non_coffee_url_detects_accessories():
    assert scrape._is_non_coffee_url("https://example.sk/kávovar/drip") is True
    assert scrape._is_non_coffee_url("https://example.sk/mlynok/ceramic") is True
    assert scrape._is_non_coffee_url("https://example.sk/kávovar/v4") is True
    assert scrape._is_non_coffee_url("https://example.sk/mlynky/burgr") is True


def test_is_non_coffee_url_detects_segment_match():
    # segment-based: "cajik" / "čaj" as path component
    assert scrape._is_non_coffee_url("https://example.sk/cajik/abc") is True
    assert scrape._is_non_coffee_url("https://example.sk/čaj/premium") is True
    assert scrape._is_non_coffee_url("https://example.sk/caj/blend") is True


def test_is_non_coffee_url_allows_coffee():
    assert scrape._is_non_coffee_url("https://example.sk/capsules/espresso") is False
    assert scrape._is_non_coffee_url("https://example.sk/brand/ethiopia-natural") is False
    assert scrape._is_non_coffee_url("https://example.sk/kava-espresso-roast") is False
    assert scrape._is_non_coffee_url("https://example.sk/drip-bag/brazil") is False


def test_is_non_coffee_url_no_false_positive_on_longer_segments():
    # A product slug containing "caj" or "cajik" as substring should NOT match
    # (segment matching only matches exact path segments)
    assert scrape._is_non_coffee_url("https://example.sk/some-cajik-product") is False
    assert scrape._is_non_coffee_url("https://example.sk/moje-caj-kava") is False


# ── Issue #144: deduplicate packaging tiers with same weight + price ──────


def test_deduplicate_packaging_preserves_different_weights():
    packaging = [
        {"weight_g": 250, "price": 8.90, "variant": "Whole bean"},
        {"weight_g": 500, "price": 15.90, "variant": "Ground"},
    ]
    result = scrape._deduplicate_packaging(packaging)
    assert len(result) == 2


def test_deduplicate_packaging_removes_exact_duplicates():
    packaging = [
        {"weight_g": 250, "price": 8.90, "variant": "Whole bean"},
        {"weight_g": 250, "price": 8.90, "variant": "Ground"},  # different variant → both kept
    ]
    result = scrape._deduplicate_packaging(packaging)
    assert len(result) == 2


def test_deduplicate_packaging_removes_identical_tiers():
    packaging = [
        {"weight_g": 250, "price": 8.90},
        {"weight_g": 250, "price": 8.90},  # exact duplicate
    ]
    result = scrape._deduplicate_packaging(packaging)
    assert len(result) == 1


def test_deduplicate_packaging_different_prices_different_weights():
    packaging = [
        {"weight_g": 250, "price": 8.90},
        {"weight_g": 250, "price": 9.50},  # same weight, diff price → different triplet → both kept
    ]
    result = scrape._deduplicate_packaging(packaging)
    assert len(result) == 2


def test_deduplicate_packaging_empty():
    result = scrape._deduplicate_packaging([])
    assert result == []


def test_deduplicate_packaging_single_entry():
    result = scrape._deduplicate_packaging([{"weight_g": 250, "price": 8.90}])
    assert len(result) == 1


def test_deduplicate_packaging_null_weights():
    packaging = [
        {"weight_g": None, "price": 5.00},
        {"weight_g": None, "price": 5.00},  # both null → same key → dedup
    ]
    result = scrape._deduplicate_packaging(packaging)
    assert len(result) == 1


# ── Issue #145: infer missing process from origin/name ──────────────────────


def test_infer_process_from_origin():
    assert scrape._infer_process("Test Coffee", "brazil") == "natural"
    assert scrape._infer_process("Test Coffee", "colombia") == "washed"
    assert scrape._infer_process("Test Coffee", "indonesia") == "wet-hulled"
    assert scrape._infer_process("Test Coffee", "kenya") == "washed"
    assert scrape._infer_process("Test Coffee", "costa-rica") == "honey"


def test_infer_process_from_name():
    assert scrape._infer_process("Natural Process Ethiopia 250g", "colombia") == "natural"
    assert scrape._infer_process("Anaerobic Washed Arabica", "colombia") == "anaerobic"
    assert scrape._infer_process("Washed Filter Coffee", "kenya") == "washed"
    assert scrape._infer_process("Honey Process Brazil", "brazil") == "honey"


def test_infer_process_name_takes_precedence():
    # When both name and origin hint, name pattern should win
    assert scrape._infer_process("Washed Ethiopian Coffee", "brazil") == "washed"


def test_infer_process_returns_null_no_match():
    assert scrape._infer_process("Random Product", "somalia") is None


def test_infer_process_empty_name_or_origin():
    assert scrape._infer_process("", "brazil") is None
    assert scrape._infer_process("Some Product", None) is None


def test_infer_process_slovak_patterns():
    assert scrape._infer_process("Káva spracovaná 250g", "brazil") == "washed"
# ── Schema v22: new optional fields ──────────────────────────────────────────


def test_normalize_product_new_optional_fields():
    raw = {
        "name": "Test Decaf",
        "origin": "colombia",
        "roast_type": "decaf",
        "packaging": [{"price": "8,90 €", "weight": "250 g"}],
        "is_decaffeinated": True,
        "tasting_notes": "chocolate, caramel",
        "brewing_recommendations": "filter, French press",
        "sweetness": 7,
        "acidity": 4,
        "body": 6,
        "bitterness": 2,
        "stock_status": "in-stock",
        "price_from": 8.90,
        "price_to": 12.50,
        "quantity": 50,
    }
    product = scrape.normalize_product(raw, "https://x.sk/decaf/", "2026-07-04")
    assert product["is_decaffeinated"] is True
    assert product["tasting_notes"] == "chocolate, caramel"
    assert product["brewing_recommendations"] == "filter, French press"
    assert product["sweetness"] == 7
    assert product["acidity"] == 4
    assert product["body"] == 6
    assert product["bitterness"] == 2
    assert product["stock_status"] == "in-stock"
    assert product["price_from"] == 8.90
    assert product["price_to"] == 12.50
    assert product["quantity"] == 50


def test_normalize_product_clamps_ratings():
    raw = {
        "name": "Test",
        "origin": "brazil",
        "roast_type": "filter",
        "packaging": [{"price": "8,90 €", "weight": "250 g"}],
        "sweetness": 15,
        "acidity": -2,
        "body": 0,
    }
    product = scrape.normalize_product(raw, "https://x.sk/test/", "2026-07-04")
    assert product["sweetness"] == 10  # clamped to max
    assert product["acidity"] == 0     # clamped to min
    assert product["body"] == 0


def test_normalize_product_optional_fields_absent():
    raw = {
        "name": "Test",
        "origin": "brazil",
        "roast_type": "filter",
        "packaging": [{"price": "8,90 €", "weight": "250 g"}],
    }
    product = scrape.normalize_product(raw, "https://x.sk/test/", "2026-07-04")
    assert product.get("is_decaffeinated") is None
    assert product.get("tasting_notes") is None
