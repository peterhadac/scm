import argparse
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urljoin, urlparse

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


def fetch_html(roaster):
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
    try:
        resp = httpx.get(
            roaster["url"],
            headers={"User-Agent": USER_AGENT},
            timeout=30,
            follow_redirects=True,
        )
        resp.raise_for_status()
        return resp.text
    except httpx.HTTPError:
        return None


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
    cleaned = re.sub(r"[^\d,.]", "", raw or "")
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def registrable_domain(host):
    """Best-effort registrable domain (eTLD+1) for the roaster domains in scope.

    All configured roasters use single-label public suffixes (.sk, .com, .eu,
    .coffee), so the last two labels are the registrable domain. This is NOT a
    full Public Suffix List implementation; multi-label suffixes (e.g. .co.uk)
    would need one, but none are in use here.
    """
    host = (host or "").lower().strip(".")
    labels = host.split(".")
    return ".".join(labels[-2:]) if len(labels) >= 2 else host


def safe_url(raw, roaster_url):
    """Resolve a scraped URL against the roaster's base URL and return it only if
    it is http(s) and on the same registrable domain as the roaster; otherwise
    return None.

    Defends against a poisoned/malicious roaster page (or prompt-injected model
    output) that injects dangerous schemes (javascript:, data:) or off-domain
    phishing links into coffees.json, which the site later renders as clickable
    links. Relative hrefs (which Claude routinely returns) are resolved to
    absolute URLs against the roaster base so legitimate links are preserved.
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    absolute = urljoin(roaster_url or "", raw.strip())
    parsed = urlparse(absolute)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return None
    if roaster_url:
        roaster_host = urlparse(roaster_url).hostname
        if registrable_domain(parsed.hostname) != registrable_domain(roaster_host):
            return None
    return absolute


def normalize(entry, today, roaster_url=None):
    price = normalize_price(entry.get("price", ""))
    url = safe_url(entry.get("url"), roaster_url)
    if not entry.get("name") or not entry.get("roaster") or url is None or price is None:
        return None
    return {
        "name": entry["name"],
        "roaster": entry["roaster"],
        "origin": entry.get("origin") or None,
        "process": entry.get("process") or None,
        "price": price,
        "weight_g": entry.get("weight_g") or None,
        "url": url,
        "last_seen": today,
    }


def merge(existing, roaster_name, status, new_entries, today, roaster_url=None):
    others = [c for c in existing if c["roaster"] != roaster_name]
    if status != "ok":
        kept = [c for c in existing if c["roaster"] == roaster_name]
        return others + kept
    normalized = [
        normalize({**e, "roaster": roaster_name}, today, roaster_url) for e in new_entries
    ]
    return others + [n for n in normalized if n is not None]


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
        existing = merge(existing, name, status, extracted or [], today, roaster.get("url"))

    COFFEES_PATH.parent.mkdir(parents=True, exist_ok=True)
    COFFEES_PATH.write_text(json.dumps(existing, indent=2, ensure_ascii=False) + "\n")

    print("scrape_status:")
    for name, status in statuses.items():
        print(f"  {name}: {status}")


if __name__ == "__main__":
    main()
