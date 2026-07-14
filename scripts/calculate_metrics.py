"""Mobility accessibility pipeline. PLAN.md S3.4.

Downloads the Ile-de-France Mobilites open-data station-location dataset
(scripted, cached in data/external/) and, for every geocoded venue, counts
the number of unique station locations within a strict 500m Haversine
radius.

CONFIRMED DATASET CHOICE: PLAN.md named the dataset family
emplacement-des-gares-idf / emplacement-des-gares-ratp without picking one.
Both were fetched and inspected for real:
  - emplacement-des-gares-idf ("by line"): 1240 rows. A station served by
    multiple lines is repeated once per line - e.g. Gare du Nord appears 6
    times (TRAIN H, TRAIN K, RER B, RER D, METRO 4, METRO 5), each at a
    slightly different point (different platform/entrance). Counting these
    directly would over-count "unique station locations" at interchange
    hubs.
  - emplacement-des-gares-idf-data-generalisee ("generalized"): 999 rows,
    one barycenter point per physical station (IDFM's own dedup - e.g.
    Gare du Nord is a single row with res_com "TRAIN H / TRAIN K / RER B /
    RER D / METRO 4 / METRO 5"; the separate underground RER E stop
    "Magenta" a short walk away is correctly kept as a distinct row).
This script uses the generalized dataset, since PLAN.md S3.4's metric is
explicitly "unique station locations", not "station-line pairs".

Real column names (confirmed by downloading the dataset directly, not
assumed from PLAN.md's "Geo Point" / "Nom de la gare" / "Ligne" wording,
which don't literally match): geo_point_2d ("lat, lon" as one string),
nom_long (station name), res_com (line(s) serving it), mode.

MANUAL FALLBACK - data/interim/accessibility_matrix.csv column contract:
    venue_id, venue_name, accessibility_index
"""

import csv
import math
import sys
from pathlib import Path

import requests

INPUT_VENUES_PATH = Path("data/interim/venues_geocoded.csv")
STATIONS_CACHE_PATH = Path("data/external/emplacement-des-gares-idf-data-generalisee.csv")
OUTPUT_PATH = Path("data/interim/accessibility_matrix.csv")

RATP_STATIONS_URL = (
    "https://data.iledefrance-mobilites.fr/api/explore/v2.1/catalog/datasets/"
    "emplacement-des-gares-idf-data-generalisee/exports/csv?delimiter=%3B"
)
STATIONS_CSV_DELIMITER = ";"
REQUEST_TIMEOUT = 60

ACCESSIBILITY_RADIUS_METERS = 500.0
EARTH_RADIUS_METERS = 6371000.0

OUTPUT_COLUMNS = ["venue_id", "venue_name", "accessibility_index"]


def ensure_station_file(
    cache_path: Path = STATIONS_CACHE_PATH, url: str = RATP_STATIONS_URL
) -> Path:
    """PLAN.md S3.4: check data/external/ first; scripted-download if absent."""
    if cache_path.exists():
        return cache_path

    print(f"INFO: downloading RATP/IDFM station dataset from {url}", file=sys.stderr)
    response = requests.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(response.content)
    return cache_path


def load_stations(path: Path = STATIONS_CACHE_PATH) -> list[dict]:
    stations: list[dict] = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f, delimiter=STATIONS_CSV_DELIMITER):
            geo_point = (row.get("geo_point_2d") or "").strip()
            if not geo_point:
                continue
            try:
                lat_str, lon_str = geo_point.split(",")
                lat, lon = float(lat_str.strip()), float(lon_str.strip())
            except ValueError:
                continue
            stations.append(
                {
                    "name": row.get("nom_long", ""),
                    "latitude": lat,
                    "longitude": lon,
                    "line": row.get("res_com", ""),
                }
            )
    return stations


def load_venues(path: Path = INPUT_VENUES_PATH) -> list[dict]:
    venues: list[dict] = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                lat = float(row["latitude"])
                lon = float(row["longitude"])
            except (KeyError, ValueError):
                continue
            venues.append(
                {
                    "venue_id": row["venue_id"],
                    "venue_name": row["venue_name"],
                    "latitude": lat,
                    "longitude": lon,
                }
            )
    return venues


def haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_METERS * math.asin(math.sqrt(a))


def count_stations_within_radius(
    venue: dict, stations: list[dict], radius_m: float = ACCESSIBILITY_RADIUS_METERS
) -> int:
    return sum(
        1
        for station in stations
        if haversine_distance_meters(
            venue["latitude"], venue["longitude"], station["latitude"], station["longitude"]
        )
        <= radius_m
    )


def compute_accessibility_matrix(venues: list[dict], stations: list[dict]) -> list[dict]:
    return [
        {
            "venue_id": venue["venue_id"],
            "venue_name": venue["venue_name"],
            "accessibility_index": count_stations_within_radius(venue, stations),
        }
        for venue in venues
    ]


def write_accessibility_csv(rows: list[dict], path: Path = OUTPUT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    venues = load_venues()
    if not venues:
        print(
            "WARNING: no geocoded venues found (venues_geocoded.csv is "
            "empty - see PLAN.md S3.1/S3.2 confirmed source gap).",
            file=sys.stderr,
        )
        write_accessibility_csv([])
        print(f"Wrote 0 rows to {OUTPUT_PATH}")
        return

    station_file = ensure_station_file()
    stations = load_stations(station_file)
    print(f"INFO: loaded {len(stations)} unique station locations.", file=sys.stderr)

    rows = compute_accessibility_matrix(venues, stations)
    write_accessibility_csv(rows)
    print(f"Wrote {len(rows)} rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
