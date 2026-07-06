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


# --- is_coffee (non-coffee filtering) ---------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "Etiópia Yirgacheffe",
        "Colombia Huila Washed 250 g",
        "House Espresso Blend",
        "Kenya AA",
        "Kapsule Guatemala",  # capsules ARE coffee — must be kept
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


def test_normalize_origin_keeps_unmatched_raw_text_as_is():
    assert scrape.normalize_origin("Fantasyland", None) == "Fantasyland"


def test_normalize_origin_none_when_nothing_matches():
    assert scrape.normalize_origin(None, "House Blend") is None


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
    discovered, status = await scrape.discover_product_urls(crawler, {"url": "https://x.sk/"})
    assert status == "ok"
    assert discovered == {"https://x.sk/rwanda/"}  # /kosik/ filtered out


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
    discovered, status = await scrape.discover_product_urls(crawler, {"url": "https://x.sk/shop"})
    assert status == "ok"
    assert discovered == {"https://x.sk/coffee-a/", "https://x.sk/coffee-b/"}


@pytest.mark.asyncio
async def test_discover_product_urls_failed_when_first_page_unreachable():
    crawler = FakeCrawler({})  # no responses -> fake_result(success=False)
    discovered, status = await scrape.discover_product_urls(crawler, {"url": "https://x.sk/"})
    assert discovered is None
    assert status == "failed"


@pytest.mark.asyncio
async def test_discover_product_urls_needs_js_when_text_too_short():
    crawler = FakeCrawler({"https://x.sk/": fake_result(html="<div>hi</div>")})
    discovered, status = await scrape.discover_product_urls(crawler, {"url": "https://x.sk/"})
    assert discovered is None
    assert status == "needs_js"


# --- process_roaster (async, offline via FakeCrawler) ------------------------


ROASTER = {"name": "Test Roastery", "slug": "test-roastery", "url": "https://x.sk/"}
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


# --- flatten_to_coffees -------------------------------------------------------


def test_flatten_to_coffees_explodes_packaging_and_joins_roaster_name():
    products = {
        "jungle-roastery": [
            {
                "name": "RWANDA - Kigali",
                "url": "https://x.sk/rwanda/",
                "origin": "Rwanda",
                "process": "washed",
                "roast_type": "filter",
                "last_seen": "2026-07-04",
                "packaging": [
                    {"weight_g": 1000, "price": 44.0},
                    {"weight_g": 250, "price": 12.5},
                ],
            },
            {
                # a cached "not a product" marker must be skipped, not crash
                "url": "https://x.sk/kava/",
                "status": "not_a_product",
                "last_seen": "2026-07-04",
            },
        ]
    }
    roasters = [{"name": "Jungle Roastery", "slug": "jungle-roastery"}]
    rows = scrape.flatten_to_coffees(products, roasters)
    assert len(rows) == 2
    assert {r["weight_g"] for r in rows} == {1000, 250}
    assert all(r["roaster"] == "Jungle Roastery" for r in rows)


def test_flatten_to_coffees_dedupes_same_url_and_weight():
    products = {
        "jungle-roastery": [
            {
                "name": "Rwanda",
                "url": "https://x.sk/rwanda/",
                "last_seen": "2026-07-04",
                "packaging": [{"weight_g": 250, "price": 12.5}, {"weight_g": 250, "price": 12.5}],
            }
        ]
    }
    roasters = [{"name": "Jungle Roastery", "slug": "jungle-roastery"}]
    rows = scrape.flatten_to_coffees(products, roasters)
    assert len(rows) == 1


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
