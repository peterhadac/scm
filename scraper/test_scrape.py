from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import scrape

FIXTURES = Path(__file__).parent / "fixtures"


def test_normalize_price_comma_decimal():
    assert scrape.normalize_price("12,90 €") == 12.90


def test_normalize_price_thousands_and_decimal():
    assert scrape.normalize_price("1.234,56 €") == 1234.56


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
