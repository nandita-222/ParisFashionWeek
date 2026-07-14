"""Spatial geocoding engine. PLAN.md S3.2.

Reads the unique venue names out of data/raw/schedule_raw.csv, geocodes each
one via Nominatim, and derives arrondissement from the returned postcode.

CONFIRMED SOURCE GAP (see scrape_schedule.py / PLAN.md S3.1): FHCM publishes
no venue data at all, so venue_name is an empty string for every row the
live scraper produces today. This script skips empty venue_name rows rather
than querying Nominatim with an empty string, and logs how many were
skipped. It geocodes real data as soon as venue_name is filled in - either
by hand-editing schedule_raw.csv (the documented manual fallback) or once
FHCM's data model changes.

FALLBACK-COORDINATES IMPLEMENTATION NOTE: PLAN.md S3.2 says a failed lookup
should "route to fallback coordinates based on the brand's historic
headquarters address or use the central point of the listed arrondissement
if provided in text." This script implements that as two concrete, ordered
fallbacks when Nominatim returns nothing for a venue:
  1. If the venue_name text itself contains a Paris postcode (750xx) or an
     explicit "<N>th arrondissement" / "<N>e arrondissement" mention, use
     the hardcoded centroid for that arrondissement (public geographic
     fact, safe to hardcode - see ARRONDISSEMENT_CENTROIDS below).
  2. Otherwise, check data/external/venue_fallback_coords.csv, a
     hand-maintained file (same pattern as brand_aliases.csv) with columns
     venue_name,latitude,longitude,arrondissement. It ships empty - filling
     it with real coordinates (e.g. a brand's known historic HQ/showroom)
     is a manual, human-curated step. This script does not fabricate
     specific business addresses on its own.
If neither fallback resolves, the venue is logged and dropped from the
output rather than written with fabricated coordinates.
"""

import csv
import re
import sys
import time
from pathlib import Path

from geopy.exc import GeocoderServiceError, GeocoderTimedOut
from geopy.geocoders import Nominatim

from utils import venue_id

INPUT_PATH = Path("data/raw/schedule_raw.csv")
OUTPUT_PATH = Path("data/interim/venues_geocoded.csv")
FALLBACK_COORDS_PATH = Path("data/external/venue_fallback_coords.csv")

GEOCODE_USER_AGENT = "pfw_wrapped_2026"
GEOCODE_SLEEP_SECONDS = 1.5
GEOCODE_TIMEOUT_SECONDS = 10

OUTPUT_COLUMNS = ["venue_id", "venue_name", "latitude", "longitude", "arrondissement"]

# Public, verifiable centroid for each Paris arrondissement (1-20). Only used
# when Nominatim fails AND the venue's own text names an arrondissement.
ARRONDISSEMENT_CENTROIDS = {
    1: (48.8625, 2.3359), 2: (48.8686, 2.3411), 3: (48.8630, 2.3620),
    4: (48.8543, 2.3563), 5: (48.8448, 2.3471), 6: (48.8496, 2.3324),
    7: (48.8560, 2.3122), 8: (48.8718, 2.3075), 9: (48.8768, 2.3372),
    10: (48.8760, 2.3600), 11: (48.8590, 2.3800), 12: (48.8352, 2.4198),
    13: (48.8322, 2.3561), 14: (48.8286, 2.3260), 15: (48.8422, 2.2986),
    16: (48.8637, 2.2769), 17: (48.8874, 2.3078), 18: (48.8927, 2.3454),
    19: (48.8837, 2.3831), 20: (48.8632, 2.4012),
}

POSTCODE_IN_TEXT = re.compile(r"\b750?(\d{2})\b")
ARR_WORD_IN_TEXT = re.compile(r"\b(\d{1,2})\s*(?:st|nd|rd|th|e|er|eme|ème)\b\.?\s*arrondissement", re.IGNORECASE)


def load_schedule_venue_names(path: Path = INPUT_PATH) -> tuple[list[str], int]:
    with open(path, newline="", encoding="utf-8") as f:
        names = [row["venue_name"].strip() for row in csv.DictReader(f)]

    seen: set[str] = set()
    unique: list[str] = []
    skipped_empty = 0
    for name in names:
        if not name:
            skipped_empty += 1
            continue
        if name not in seen:
            seen.add(name)
            unique.append(name)
    return unique, skipped_empty


def load_fallback_coords(path: Path = FALLBACK_COORDS_PATH) -> dict[str, dict]:
    mapping: dict[str, dict] = {}
    if not path.exists():
        return mapping
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = (row.get("venue_name") or "").strip().lower()
            lat = (row.get("latitude") or "").strip()
            lon = (row.get("longitude") or "").strip()
            if name and lat and lon:
                mapping[name] = {
                    "latitude": float(lat),
                    "longitude": float(lon),
                    "arrondissement": int(row["arrondissement"]) if (row.get("arrondissement") or "").strip() else None,
                }
    return mapping


def geocode_venue(geolocator: Nominatim, venue_name: str):
    query = f"{venue_name}, Paris, France"
    try:
        return geolocator.geocode(query, addressdetails=True, timeout=GEOCODE_TIMEOUT_SECONDS)
    except (GeocoderTimedOut, GeocoderServiceError) as exc:
        print(f"WARNING: geocode error for {venue_name!r}: {exc}", file=sys.stderr)
        return None


def arrondissement_from_postcode(location) -> int | None:
    address = location.raw.get("address", {}) if location else {}
    postcode = address.get("postcode", "")
    if not re.fullmatch(r"75\d{3}", postcode or ""):
        return None
    return int(postcode[-2:]) or None


def arrondissement_from_text(venue_name: str) -> int | None:
    for pattern in (POSTCODE_IN_TEXT, ARR_WORD_IN_TEXT):
        match = pattern.search(venue_name)
        if match:
            arr = int(match.group(1))
            if arr in ARRONDISSEMENT_CENTROIDS:
                return arr
    return None


def geocode_all(
    venue_names: list[str], fallback_map: dict[str, dict]
) -> tuple[list[dict], list[str]]:
    geolocator = Nominatim(user_agent=GEOCODE_USER_AGENT)
    rows: list[dict] = []
    ungeocoded: list[str] = []

    for name in venue_names:
        location = geocode_venue(geolocator, name)
        time.sleep(GEOCODE_SLEEP_SECONDS)

        if location is not None:
            latitude, longitude = location.latitude, location.longitude
            arrondissement = arrondissement_from_postcode(location)
        else:
            arr_from_text = arrondissement_from_text(name)
            if arr_from_text is not None:
                latitude, longitude = ARRONDISSEMENT_CENTROIDS[arr_from_text]
                arrondissement = arr_from_text
            elif name.strip().lower() in fallback_map:
                fb = fallback_map[name.strip().lower()]
                latitude, longitude, arrondissement = fb["latitude"], fb["longitude"], fb["arrondissement"]
            else:
                ungeocoded.append(name)
                continue

        rows.append(
            {
                "venue_id": venue_id(name),
                "venue_name": name,
                "latitude": latitude,
                "longitude": longitude,
                "arrondissement": arrondissement if arrondissement is not None else "",
            }
        )

    return rows, ungeocoded


def write_venues_csv(rows: list[dict], path: Path = OUTPUT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    venue_names, skipped_empty = load_schedule_venue_names()
    if skipped_empty:
        print(
            f"INFO: skipped {skipped_empty} schedule row(s) with empty "
            "venue_name (confirmed source gap, see PLAN.md S3.1).",
            file=sys.stderr,
        )

    if not venue_names:
        print("WARNING: no non-empty venue names to geocode.", file=sys.stderr)
        write_venues_csv([])
        print(f"Wrote 0 rows to {OUTPUT_PATH}")
        return

    fallback_map = load_fallback_coords()
    rows, ungeocoded = geocode_all(venue_names, fallback_map)

    if ungeocoded:
        print(
            f"WARNING: {len(ungeocoded)} venue(s) could not be geocoded and "
            f"were dropped: {ungeocoded}",
            file=sys.stderr,
        )

    write_venues_csv(rows)
    print(f"Wrote {len(rows)} geocoded venues to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
