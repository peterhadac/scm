import argparse
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

import httpx
import yaml
from anthropic import Anthropic
from bs4 import BeautifulSoup, Comment

ROOT = Path(__file__).resolve().parent.parent
ROASTERS_PATH = ROOT / "roasters.yaml"
COFFEES_PATH = ROOT / "_data" / "coffees.json"

MODEL = "claude-haiku-4-5-20251001"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

# Safety cap so a mis-detected "next" link (e.g. one that loops) can't spin forever.
MAX_PAGES = 10

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

EXTRACT_TOOL = {
    "name": "extract_coffees",
    "description": "Extract every coffee product listed on a roaster's product page.",
    "input_schema": {
        "type": "object",
        "properties": {
            "coffees": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "origin": {"type": ["string", "null"]},
                        "process": {"type": ["string", "null"]},
                        "price": {
                            "type": "string",
                            "description": "Raw price as shown on the page, e.g. '12,90 €'",
                        },
                        "weight_g": {"type": ["integer", "null"]},
                        "url": {"type": "string"},
                    },
                    "required": ["name", "price", "url"],
                },
            }
        },
        "required": ["coffees"],
    },
}


def load_roasters(path=ROASTERS_PATH):
    return yaml.safe_load(path.read_text())["roasters"]


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


def fetch_html(roaster, max_pages=MAX_PAGES):
    """Fetch a roaster's listing, following pagination, and return combined HTML.

    Returns the concatenation of every fetched page's HTML, or None if even the
    first page could not be retrieved. Entry-level de-duplication downstream
    absorbs any products repeated across the joined pages. Playwright-flagged
    roasters fetch a single rendered page (JS shops rarely use crawlable
    next-page links).
    """
    if roaster.get("scraper") == "playwright":
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page(user_agent=USER_AGENT)
                page.goto(roaster["url"], wait_until="networkidle", timeout=30000)
                return page.content()
            finally:
                browser.close()

    url = roaster["url"]
    seen = set()
    pages = []
    for _ in range(max_pages):
        if not url or url in seen:
            break
        seen.add(url)
        try:
            resp = httpx.get(
                url,
                headers={"User-Agent": USER_AGENT},
                timeout=30,
                follow_redirects=True,
            )
            resp.raise_for_status()
        except httpx.HTTPError:
            # First page unreachable -> hard failure; a later page failing just
            # ends pagination with whatever we already collected.
            break
        pages.append(resp.text)
        nxt = find_next_page_url(resp.text, str(resp.url))
        if not nxt or nxt in seen:
            break
        url = nxt

    if not pages:
        return None
    return "\n<!-- page-break -->\n".join(pages)


def clean_html(html):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "head", "noscript", "svg"]):
        tag.decompose()
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        comment.extract()
    return str(soup.body or soup)


def extract_coffees(client, roaster_name, cleaned_html):
    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        tools=[EXTRACT_TOOL],
        tool_choice={"type": "tool", "name": "extract_coffees"},
        messages=[
            {
                "role": "user",
                "content": (
                    f"Extract every coffee product listed on this page from "
                    f"roaster '{roaster_name}'. Page HTML:\n\n{cleaned_html}"
                ),
            }
        ],
    )
    for block in response.content:
        if block.type == "tool_use" and block.name == "extract_coffees":
            coffees = block.input.get("coffees", [])
            return [c for c in coffees if isinstance(c, dict)]
    return None


def classify_status(html, cleaned, extracted):
    if html is None:
        return "failed"
    if extracted:
        return "ok"
    text_len = len(BeautifulSoup(cleaned, "html.parser").get_text(strip=True)) if cleaned else 0
    return "needs_js" if text_len < 200 else "failed"


def normalize_price(raw):
    """Parse the first EUR amount out of a raw price string into a float.

    Handles: plain "12,90 €", "od 12,90 €" (from/price ranges — takes the first
    number), thousands separators ("1.234,56 €", "1 234,56 €"), non-breaking
    spaces, and stray surrounding text. Returns None when no number is present.
    Per-kg vs per-package suffixes are ignored — the numeric value shown wins.
    """
    if not raw:
        return None
    text = raw.replace("\xa0", " ").replace(" ", " ")
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


def parse_weight(text):
    """Extract a package weight in grams from free text (usually the product name).

    Understands "250 g", "250g", "1 kg", "0,25 kg", "1000 g", "1,5kg". Returns an
    int number of grams, or None when no weight is stated. Prefers an explicit
    gram figure when both a gram and kg token are present.
    """
    if not text:
        return None
    normalized = text.replace("\xa0", " ").replace(" ", " ").lower()

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


def dedupe(entries):
    """Drop duplicate coffees within a roaster's fresh set, keeping first seen.

    An entry duplicates an earlier one if it shares the same URL, or the same
    (case-folded name, weight_g) pair — the latter catches the same product
    surfaced under two URLs (e.g. a listing card and a "featured" card).
    """
    seen_urls = set()
    seen_name_weight = set()
    result = []
    for entry in entries:
        url_key = (entry.get("url") or "").strip()
        name_weight_key = ((entry.get("name") or "").strip().lower(), entry.get("weight_g"))
        if url_key and url_key in seen_urls:
            continue
        if name_weight_key[0] and name_weight_key in seen_name_weight:
            continue
        if url_key:
            seen_urls.add(url_key)
        seen_name_weight.add(name_weight_key)
        result.append(entry)
    return result


def normalize(entry, today):
    price = normalize_price(entry.get("price", ""))
    if not entry.get("name") or not entry.get("roaster") or not entry.get("url") or price is None:
        return None
    # Fall back to parsing the weight out of the product name when the model
    # didn't return one (the single most common missing field).
    weight_g = entry.get("weight_g") or parse_weight(entry["name"])
    return {
        "name": entry["name"],
        "roaster": entry["roaster"],
        "origin": entry.get("origin") or None,
        "process": entry.get("process") or None,
        "price": price,
        "weight_g": weight_g or None,
        "url": entry["url"],
        "last_seen": today,
    }


def merge(existing, roaster_name, status, new_entries, today):
    others = [c for c in existing if c["roaster"] != roaster_name]
    if status != "ok":
        kept = [c for c in existing if c["roaster"] == roaster_name]
        return others + kept
    normalized = [normalize({**e, "roaster": roaster_name}, today) for e in new_entries]
    kept = [n for n in normalized if n is not None and is_coffee(n["name"])]
    return others + dedupe(kept)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="limit the run to roasters whose name contains this substring")
    args = parser.parse_args()

    client = Anthropic()
    roasters = load_roasters()
    if args.only:
        roasters = [r for r in roasters if args.only.lower() in r["name"].lower()]

    existing = json.loads(COFFEES_PATH.read_text()) if COFFEES_PATH.exists() else []
    today = date.today().isoformat()
    statuses = {}

    for roaster in roasters:
        name = roaster["name"]
        html = fetch_html(roaster)
        cleaned = clean_html(html) if html is not None else None
        extracted = extract_coffees(client, name, cleaned) if cleaned is not None else None
        status = classify_status(html, cleaned, extracted)
        statuses[name] = status
        existing = merge(existing, name, status, extracted or [], today)

    COFFEES_PATH.parent.mkdir(parents=True, exist_ok=True)
    COFFEES_PATH.write_text(json.dumps(existing, indent=2, ensure_ascii=False) + "\n")

    print("scrape_status:")
    for name, status in statuses.items():
        print(f"  {name}: {status}")


if __name__ == "__main__":
    main()
