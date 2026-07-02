from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import scrape

FIXTURES = Path(__file__).parent / "fixtures"


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
    assert scrape.normalize_price("  12,90 € ") == 12.90


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


def test_normalize_fills_weight_from_name():
    entry = {
        "name": "Colombia Huila 200 g",
        "roaster": "Ready After",
        "price": "14,50 €",
        "url": "https://www.readyafter.sk/x",
    }
    result = scrape.normalize(entry, "2026-06-30")
    assert result["weight_g"] == 200


def test_normalize_prefers_model_weight_over_name():
    entry = {
        "name": "Colombia Huila 200 g",
        "roaster": "Ready After",
        "price": "14,50 €",
        "weight_g": 250,
        "url": "https://www.readyafter.sk/x",
    }
    result = scrape.normalize(entry, "2026-06-30")
    assert result["weight_g"] == 250


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


def test_merge_filters_non_coffee_items():
    new_entries = [
        {"name": "Etiópia Yirgacheffe", "price": "12,90 €", "url": "https://k.sk/a"},
        {"name": "Darčeková poukážka", "price": "50,00 €", "url": "https://k.sk/voucher"},
        {"name": "Mlynček Comandante", "price": "250,00 €", "url": "https://k.sk/grinder"},
    ]
    merged = scrape.merge([], "Kavoholik", "ok", new_entries, "2026-06-30")
    assert [m["name"] for m in merged] == ["Etiópia Yirgacheffe"]


# --- dedupe ------------------------------------------------------------------


def test_dedupe_by_url():
    entries = [
        {"name": "A", "weight_g": 250, "url": "https://x.sk/a"},
        {"name": "A duplicate card", "weight_g": 500, "url": "https://x.sk/a"},
        {"name": "B", "weight_g": 250, "url": "https://x.sk/b"},
    ]
    result = scrape.dedupe(entries)
    assert [e["url"] for e in result] == ["https://x.sk/a", "https://x.sk/b"]


def test_dedupe_by_name_and_weight():
    entries = [
        {"name": "Kenya AA", "weight_g": 250, "url": "https://x.sk/kenya"},
        {"name": "kenya aa", "weight_g": 250, "url": "https://x.sk/kenya-featured"},
        {"name": "Kenya AA", "weight_g": 1000, "url": "https://x.sk/kenya-1kg"},
    ]
    result = scrape.dedupe(entries)
    # First two collapse (same name+weight); the 1kg variant is a distinct product.
    assert [e["url"] for e in result] == ["https://x.sk/kenya", "https://x.sk/kenya-1kg"]


def test_merge_dedupes_within_roaster():
    new_entries = [
        {"name": "Etiópia", "price": "12,90 €", "url": "https://k.sk/eth", "weight_g": 250},
        {"name": "Etiópia", "price": "12,90 €", "url": "https://k.sk/eth", "weight_g": 250},
    ]
    merged = scrape.merge([], "Kavoholik", "ok", new_entries, "2026-06-30")
    assert len(merged) == 1


# --- pagination link discovery (offline) ------------------------------------


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


def test_fetch_html_follows_pagination(monkeypatch):
    page1 = '<html><body><div>p1</div><a rel="next" href="/shop?page=2">Next</a></body></html>'
    page2 = "<html><body><div>p2</div></body></html>"  # no next link -> stop
    responses = {
        "https://x.sk/shop": page1,
        "https://x.sk/shop?page=2": page2,
    }

    def fake_get(url, **kwargs):
        resp = MagicMock()
        resp.text = responses[url]
        resp.url = url
        resp.raise_for_status = lambda: None
        return resp

    monkeypatch.setattr(scrape.httpx, "get", fake_get)
    combined = scrape.fetch_html({"name": "X", "url": "https://x.sk/shop"})
    assert "p1" in combined and "p2" in combined


def test_fetch_html_returns_none_on_first_page_error(monkeypatch):
    def fake_get(url, **kwargs):
        raise scrape.httpx.ConnectError("boom")

    monkeypatch.setattr(scrape.httpx, "get", fake_get)
    assert scrape.fetch_html({"name": "X", "url": "https://x.sk/shop"}) is None


def test_fetch_html_page_cap(monkeypatch):
    # Every page links to a fresh next page; the cap must bound the crawl.
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        n = len(calls)
        resp = MagicMock()
        resp.text = f'<a rel="next" href="/shop?page={n + 1}">Next</a>'
        resp.url = url
        resp.raise_for_status = lambda: None
        return resp

    monkeypatch.setattr(scrape.httpx, "get", fake_get)
    scrape.fetch_html({"name": "X", "url": "https://x.sk/shop"}, max_pages=3)
    assert len(calls) == 3


def test_normalize_fills_missing_optional_fields_with_null():
    entry = {
        "name": "Ethiopia Yirgacheffe",
        "roaster": "Kaffa Roastery",
        "price": "12,90 €",
        "url": "https://kaffaroastery.sk/coffees/x",
    }
    result = scrape.normalize(entry, "2026-06-30")
    assert result["origin"] is None
    assert result["process"] is None
    assert result["weight_g"] is None
    assert result["last_seen"] == "2026-06-30"


def test_normalize_drops_entry_missing_required_field():
    entry = {"name": "No URL Coffee", "roaster": "Kaffa Roastery", "price": "12,90 €"}
    assert scrape.normalize(entry, "2026-06-30") is None


def test_merge_keeps_existing_entries_on_failure():
    existing = [
        {
            "name": "Old Coffee",
            "roaster": "Kavoholik",
            "origin": None,
            "process": None,
            "price": 9.5,
            "weight_g": 250,
            "url": "https://kavoholik.sk/old",
            "last_seen": "2026-06-29",
        }
    ]
    merged = scrape.merge(existing, "Kavoholik", "failed", [], "2026-06-30")
    assert merged == existing


def test_extract_coffees_drops_non_dict_items_from_claude_response():
    # Claude's tool call isn't schema-enforced (no strict: true), so the
    # "coffees" array can contain items that don't match the object schema —
    # e.g. a bare string. This must not reach merge()/normalize(), which
    # assume every entry is a dict.
    tool_use_block = MagicMock()
    tool_use_block.type = "tool_use"
    tool_use_block.name = "extract_coffees"
    tool_use_block.input = {
        "coffees": [
            {"name": "Good Coffee", "price": "10,00 €", "url": "https://example.com/good"},
            "a malformed string entry Claude sometimes returns",
        ]
    }
    fake_response = MagicMock()
    fake_response.content = [tool_use_block]
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response

    result = scrape.extract_coffees(fake_client, "Test Roaster", "<html></html>")

    assert result == [
        {"name": "Good Coffee", "price": "10,00 €", "url": "https://example.com/good"}
    ]


def test_merge_replaces_existing_entries_on_ok():
    existing = [
        {
            "name": "Old Coffee",
            "roaster": "Kavoholik",
            "origin": None,
            "process": None,
            "price": 9.5,
            "weight_g": 250,
            "url": "https://kavoholik.sk/old",
            "last_seen": "2026-06-29",
        }
    ]
    new_entries = [{"name": "New Coffee", "price": "11,00 €", "url": "https://kavoholik.sk/new"}]
    merged = scrape.merge(existing, "Kavoholik", "ok", new_entries, "2026-06-30")
    assert len(merged) == 1
    assert merged[0]["name"] == "New Coffee"
    assert merged[0]["price"] == 11.0


@pytest.mark.parametrize(
    "fixture_name,roaster,fake_price,expected_price",
    [
        ("kavoholik.html", "Kavoholik", "12,90 €", 12.90),
        ("ready-after.html", "Ready After", "14,50 €", 14.50),
        ("kaffa-roastery.html", "Kaffa Roastery", "11,00 €", 11.00),
        ("suca-roastery.html", "Suca Roastery", "1.234,56 €", 1234.56),
        ("coffeein.html", "Coffeein", "15,90 €", 15.90),
    ],
)
def test_fixture_pipeline_strips_boilerplate_and_normalizes(
    fixture_name, roaster, fake_price, expected_price
):
    html = (FIXTURES / fixture_name).read_text()
    cleaned = scrape.clean_html(html)
    assert "<script" not in cleaned
    assert "<style" not in cleaned

    fake_response = [{"name": "Test Blend", "price": fake_price, "url": "https://example.com/test"}]
    with patch.object(scrape, "extract_coffees", return_value=fake_response):
        extracted = scrape.extract_coffees(None, roaster, cleaned)

    status = scrape.classify_status(html, cleaned, extracted)
    assert status == "ok"

    merged = scrape.merge([], roaster, status, extracted, "2026-06-30")
    assert len(merged) == 1
    assert merged[0]["roaster"] == roaster
    assert merged[0]["price"] == expected_price
