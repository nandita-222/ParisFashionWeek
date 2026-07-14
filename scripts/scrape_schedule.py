"""Fashion schedule scraper. PLAN.md S3.1.

Discovery-first: fetch the live FHCM calendar with plain `requests` first;
only fall back to a Playwright-rendered fetch if the schedule markup is
missing from the static HTML response.

Real selectors below were recorded by hand-inspecting
https://www.fhcm.paris/en/paris-fashion-week/calendar on 2026-07-14 (the
schedule turned out to be static HTML, so the Playwright path is present
for spec compliance and future-proofing but is not currently exercised).
Re-verify these selectors before relying on this script long-term: FHCM's
markup has already changed once (venue/designer fields used to be part of
older calendar exports and are no longer in the live page at all).

KNOWN SOURCE GAP: FHCM's calendar HTML does not publish venue_name or
designer for any show, live or archived — confirmed against both the
calendar page and individual house detail pages. Both columns are written
as empty strings by this scraper. Filling them requires hand-editing
data/raw/schedule_raw.csv (see MANUAL FALLBACK below); that is the
documented, sanctioned path per PLAN.md S3.1, not a workaround.

SEASON NOTE: the live calendar only ever shows the currently-published
season. The season matching PLAN.md's date window (2026-02-16 to
2026-03-18, Womenswear SS26) has already rotated off the live calendar and
exists only as an archived PDF. Running this script now scrapes whichever
season is currently live, which exercises the pipeline end-to-end but will
not itself produce the 2026-02-16/2026-03-18 dataset. For that specific
dataset, hand-transcribe data/raw/schedule_raw.csv from the archived PDF
using the column contract below instead of running this scraper.

MANUAL FALLBACK - data/raw/schedule_raw.csv column contract:
    brand_name, brand_key, designer, show_date, show_time, venue_name
(show_id is derived later by build_database.py via utils.show_id, not
written by this script or required in a hand-authored CSV.)
"""

import csv
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from utils import normalize_brand, strip_corporate_suffixes

BASE_URL = "https://www.fhcm.paris"
CALENDAR_URL = f"{BASE_URL}/en/paris-fashion-week/calendar"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)
REQUEST_TIMEOUT = 20

# Recorded against the live calendar page, 2026-07-14.
SELECTOR_DAY = "div.day"
SELECTOR_HOUSE_ITEM = "div.cal-item"
SELECTOR_HOUSE_NAME = "h3"
SELECTOR_ENTRY = "div.entry"
SELECTOR_ENTRY_TIME = "div.time"
SELECTOR_ENTRY_FORMAT = "span.format"
SCHEDULE_MARKUP_PROBE = "div.calendar-houses"

# The source has no venue field to check against PLAN.md's
# Digital Show / Online Presentation / To Be Confirmed drop-list, so the
# physical-vs-non-physical signal used here is the entry's format instead.
NON_PHYSICAL_FORMATS = {"digital", "livestream"}

PARIS_TZ = ZoneInfo("Europe/Paris")
UTC_TZ = ZoneInfo("UTC")

OUTPUT_PATH = Path("data/raw/schedule_raw.csv")
OUTPUT_COLUMNS = ["brand_name", "brand_key", "designer", "show_date", "show_time", "venue_name"]


def fetch_static(url: str) -> str | None:
    try:
        response = requests.get(
            url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        return response.text
    except requests.RequestException as exc:
        print(f"WARNING: static fetch failed for {url}: {exc}", file=sys.stderr)
        return None


def has_schedule_markup(html: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    return bool(soup.select(SCHEDULE_MARKUP_PROBE))


def fetch_rendered(url: str) -> str:
    """JS-rendering fallback (PLAN.md S3.1). Not exercised against FHCM
    today (the calendar is static HTML) but kept as the documented path for
    when/if that changes."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Schedule markup was not found in the static HTML and Playwright "
            "is not installed. Run `pip install playwright && playwright "
            "install chromium` to enable the JS-rendering fallback, or use "
            "the manual-CSV fallback documented in this script's docstring."
        ) from exc

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(user_agent=USER_AGENT)
            page.goto(url, timeout=REQUEST_TIMEOUT * 1000)
            page.wait_for_selector(SCHEDULE_MARKUP_PROBE, timeout=15000)
            return page.content()
        finally:
            browser.close()


def fetch_calendar_html(url: str = CALENDAR_URL) -> str:
    html = fetch_static(url)
    if html and has_schedule_markup(html):
        return html
    print(
        "INFO: schedule markup not found in static HTML, falling back to "
        "Playwright-rendered fetch.",
        file=sys.stderr,
    )
    return fetch_rendered(url)


def derive_date_time(
    day_attr: str, entry_date_start: str, entry_time_text: str
) -> tuple[str, str] | tuple[None, None]:
    """Normalize the entry's timestamp to Europe/Paris (PLAN.md S2.1) and
    return (show_date, show_time) as YYYY-MM-DD / HH:MM:SS strings."""
    if entry_date_start:
        try:
            dt_utc = datetime.strptime(entry_date_start, "%Y%m%dT%H%M%SZ").replace(
                tzinfo=UTC_TZ
            )
            dt_paris = dt_utc.astimezone(PARIS_TZ)
            return dt_paris.strftime("%Y-%m-%d"), dt_paris.strftime("%H:%M:%S")
        except ValueError:
            pass

    if not day_attr:
        return None, None
    try:
        show_date = datetime.strptime(day_attr, "%Y%m%d").strftime("%Y-%m-%d")
    except ValueError:
        return None, None

    show_time = "00:00:00"
    if entry_time_text:
        first_time = entry_time_text.split("-")[0].strip()
        try:
            show_time = datetime.strptime(first_time, "%H:%M").strftime("%H:%M:%S")
        except ValueError:
            pass

    return show_date, show_time


def parse_schedule(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict] = []

    for day in soup.select(SELECTOR_DAY):
        day_attr = day.get("data-day", "")
        for house in day.select(SELECTOR_HOUSE_ITEM):
            name_el = house.select_one(SELECTOR_HOUSE_NAME)
            if not name_el:
                continue
            brand_name = strip_corporate_suffixes(name_el.get_text(strip=True))
            if not brand_name:
                continue
            brand_key = normalize_brand(brand_name)

            for entry in house.select(SELECTOR_ENTRY):
                format_el = entry.select_one(SELECTOR_ENTRY_FORMAT)
                format_text = format_el.get_text(strip=True).lower() if format_el else ""
                if format_text in NON_PHYSICAL_FORMATS:
                    continue

                date_start = entry.get("data-date-start", "")
                time_el = entry.select_one(SELECTOR_ENTRY_TIME)
                time_text = time_el.get_text(strip=True) if time_el else ""
                if not date_start and not time_text:
                    # No real scheduled timestamp at all (e.g. "Film of the
                    # show revealed later" placeholder entries) - nothing to
                    # record, and falling back to day_attr would fabricate a
                    # bogus 00:00:00 duplicate of the real entry.
                    continue

                show_date, show_time = derive_date_time(day_attr, date_start, time_text)
                if show_date is None:
                    continue

                rows.append(
                    {
                        "brand_name": brand_name,
                        "brand_key": brand_key,
                        "designer": "",
                        "show_date": show_date,
                        "show_time": show_time,
                        "venue_name": "",
                    }
                )

    return rows


def write_schedule_csv(rows: list[dict], path: Path = OUTPUT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    html = fetch_calendar_html()
    rows = parse_schedule(html)
    if not rows:
        print("WARNING: parsed zero schedule rows.", file=sys.stderr)
    write_schedule_csv(rows)
    print(f"Wrote {len(rows)} rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
