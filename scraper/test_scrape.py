import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import scrape


def fake_tool_call(name, arguments):
    call = MagicMock()
    call.function.name = name
    call.function.arguments = json.dumps(arguments)
    return call


def fake_completion(tool_calls=None):
    return MagicMock(choices=[MagicMock(message=MagicMock(tool_calls=tool_calls or []))])


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


# --- load_products (YAML date round-trip) ------------------------------------


def test_load_products_coerces_yaml_date_back_to_string(tmp_path):
    # An unquoted "2026-07-04" scalar is parsed by PyYAML as a datetime.date,
    # not the str this pipeline stores it as — load_products must undo that.
    path = tmp_path / "products.yaml"
    path.write_text("roaster:\n- url: https://x.sk/a\n  last_seen: 2026-07-04\n")
    data = scrape.load_products(path)
    assert data["roaster"][0]["last_seen"] == "2026-07-04"
    assert isinstance(data["roaster"][0]["last_seen"], str)


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
    raw_json, tiers = scrape.extract_woocommerce_variations(WOO_VARIATIONS_HTML)
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
    _, tiers = scrape.extract_woocommerce_variations(html)
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
    _, tiers = scrape.extract_woocommerce_variations(html)
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
    _, tiers = scrape.extract_woocommerce_variations(html)
    assert tiers == [
        {"weight_g": 250, "price": 9.9},
        {"weight_g": 1000, "price": 35.9},
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


def test_extract_woocommerce_variations_non_list_json_returns_raw_and_empty_tiers():
    # Well-formed JSON that isn't a list (e.g. a bare number) must degrade
    # gracefully rather than raising when iterated.
    html = '<form data-product_variations="5"></form>'
    raw_json, tiers = scrape.extract_woocommerce_variations(html)
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
    _, tiers = scrape.extract_woocommerce_variations(html)
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
    _, tiers = scrape.extract_woocommerce_variations(html)
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
    _, tiers = scrape.extract_woocommerce_variations(html)
    assert tiers == []


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
    ],
)
def test_looks_like_product_link_rejects_site_plumbing(href):
    assert scrape.looks_like_product_link(href) is False


@pytest.mark.parametrize(
    "href",
    [
        "https://x.sk/rwanda/",
        "https://x.sk/produkty/kolumbia-huila/",
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


def test_normalize_roast_type_category_hint_is_last_resort():
    # Only used when the page itself states nothing at all.
    assert scrape.normalize_roast_type(None, None, "Some Coffee", category_hint="filter") == "filter"


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
    assert scrape.extract_woocommerce_roast_type(html) == "espresso"


def test_extract_woocommerce_roast_type_filter_only():
    html = (
        '<tr class="woocommerce-product-attributes-item--attribute_pa_odporucany-sposob-pripravy">'
        '<td><span class="wd-term-name">Zalievaná</span></td></tr>'
    )
    assert scrape.extract_woocommerce_roast_type(html) == "filter"


def test_extract_woocommerce_roast_type_ignores_unrelated_roast_degree_attribute():
    # "Stupeň praženia" (roast degree: light/medium/dark) is a DIFFERENT
    # attribute and must not be mistaken for the prep-method one.
    html = (
        '<tr class="woocommerce-product-attributes-item--attribute_pa_stupen-prazenia">'
        '<td><span class="wd-term-name">Tmavé</span></td></tr>'
    )
    assert scrape.extract_woocommerce_roast_type(html) is None


def test_extract_woocommerce_roast_type_absent_returns_none():
    assert scrape.extract_woocommerce_roast_type("<html><body>nothing here</body></html>") is None


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


def test_normalize_origin_keeps_unmatched_raw_text_as_is():
    assert scrape.normalize_origin("Fantasyland", None) == "Fantasyland"


def test_normalize_origin_none_when_nothing_matches():
    assert scrape.normalize_origin(None, "Mystery Coffee") is None


def test_normalize_origin_none_for_whitespace_only_raw():
    # A blank-but-truthy raw origin must not survive as "" (schema requires minLength 1).
    assert scrape.normalize_origin("   ", "some name") is None


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


# --- extract_woocommerce_origin ------------------------------------------------


WOO_ORIGIN_ROW_HTML = (
    '<tr class="woocommerce-product-attributes-item woocommerce-product-attributes-item--attribute_pa_krajina-povodu">'
    '<th><span class="wd-attr-name">Krajina pôvodu</span></th>'
    '<td><span class="wd-term-name">Brazília</span><span class="wd-term-sep">, </span>'
    '<span class="wd-term-name">Honduras</span></td></tr>'
)


def test_extract_woocommerce_origin_multi_country_is_blend():
    assert scrape.extract_woocommerce_origin(WOO_ORIGIN_ROW_HTML) == "Blend"


def test_extract_woocommerce_origin_single_country():
    html = (
        '<tr class="woocommerce-product-attributes-item--attribute_pa_krajina-povodu">'
        '<td><span class="wd-term-name">Etiópia</span></td></tr>'
    )
    assert scrape.extract_woocommerce_origin(html) == "Ethiopia"


def test_extract_woocommerce_origin_absent_returns_none():
    assert scrape.extract_woocommerce_origin("<html><body>no attribute table</body></html>") is None


def test_extract_woocommerce_origin_unrecognized_text_returns_none():
    html = (
        '<tr class="woocommerce-product-attributes-item--attribute_pa_krajina-povodu">'
        '<td><span class="wd-term-name">Neznáma planéta</span></td></tr>'
    )
    assert scrape.extract_woocommerce_origin(html) is None


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
    result = scrape.normalize_product(raw, "https://x.sk/mexico/", "2026-07-08", variation_tiers=tiers)
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
        raw, "https://x.sk/some-coffee/", "2026-07-08", roast_type_hint="espresso"
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
        raw, "https://x.sk/budicek/", "2026-07-08", origin_hint="Blend"
    )
    assert result["status"] == "ok"
    assert result["origin"] == "Blend"


def test_normalize_product_roast_type_attribute_hint_wins_over_llm_guess():
    # LLM left roast_type null — the deterministic WooCommerce attribute-row
    # hint fills it in, overriding whatever the LLM would otherwise guess.
    raw = {
        "name": "Kolumbia Excelso",
        "origin": "Colombia",
        "packaging": [{"weight": "250 g", "price": "10,00 €"}],
    }
    result = scrape.normalize_product(
        raw, "https://x.sk/kolumbia/", "2026-07-08", roast_type_attribute_hint="filter"
    )
    assert result["status"] == "ok"
    assert result["roast_type"] == "filter"


def test_normalize_product_variation_tiers_still_requires_a_name():
    # variation_tiers alone doesn't make a page a product — Claude declining
    # (raw=None) or a non-coffee name must still return None.
    tiers = [{"weight_g": 250, "price": 11.0}]
    assert scrape.normalize_product(None, "https://x.sk/mexico/", "2026-07-08", variation_tiers=tiers) is None
    raw = {"name": "Darčeková poukážka", "packaging": []}
    assert scrape.normalize_product(raw, "https://x.sk/gift/", "2026-07-08", variation_tiers=tiers) is None


def test_normalize_product_variation_tiers_same_price_is_not_a_collision():
    # The price_collision heuristic exists to catch the LLM hallucinating the
    # same price across tiers — it doesn't apply to variation_tiers, where
    # WooCommerce's own JSON can legitimately price two weights the same.
    raw = {"name": "Guatemala Huehuetenango", "origin": "Guatemala", "roast_type": "filter"}
    tiers = [{"weight_g": 250, "price": 12.0}, {"weight_g": 1000, "price": 12.0}]
    result = scrape.normalize_product(raw, "https://x.sk/guatemala/", "2026-07-08", variation_tiers=tiers)
    assert result["status"] == "ok"
    assert result["packaging"] == tiers


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


# --- extract_product (mocked OpenRouter/OpenAI client) -----------------------


def test_extract_product_returns_tool_input():
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = fake_completion(
        [fake_tool_call("extract_product", {"name": "Rwanda", "packaging": [{"price": "12,50 €"}]})]
    )

    result = scrape.extract_product(fake_client, "https://x.sk/rwanda/", "markdown text")
    assert result == {"name": "Rwanda", "packaging": [{"price": "12,50 €"}]}


def test_extract_product_returns_none_when_claude_declines():
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = fake_completion()

    result = scrape.extract_product(fake_client, "https://x.sk/kava/", "markdown text")
    assert result is None


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


@pytest.mark.asyncio
async def test_process_roaster_skips_claude_when_hash_unchanged():
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
    # A previously-good product whose page still hashes differently, but Claude
    # declines this time — must not clobber the known-good data.
    crawler = FakeCrawler(
        {
            "https://x.sk/": listing_result(["https://x.sk/rwanda/"]),
            "https://x.sk/rwanda/": fake_result(markdown=fake_markdown(LONG_TEXT + " changed")),
        }
    )
    client = MagicMock()
    client.chat.completions.create.return_value = fake_completion()  # declines, no tool call
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
async def test_process_roaster_reclassifies_stale_incomplete_when_confidently_not_coffee():
    # Claude DID extract a name this run (unlike a bare decline) — our own
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
    client.chat.completions.create.return_value = fake_completion()  # declines

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
