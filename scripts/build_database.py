"""Database build script. PLAN.md S4 / S4.0.

Loads the pipeline's raw/interim CSV outputs into a DuckDB star schema at
data/processed/pfw_analytics.db: dim_venues, fact_runway_shows,
fact_brand_metrics. Wires the accessibility index into dim_venues via an
explicit SQL join (PLAN.md S4 "Accessibility Wiring Step") and runs the
Build Validation Rules before finishing.

ID OWNERSHIP - reconciled with what the upstream scripts actually write
(see their module docstrings): venue_id is computed once, upstream, by
geocode_venues.py, because it is a join key shared across two different raw
files (venues_geocoded.csv and schedule_raw.csv, joined by venue_name).
show_id and metric_id are deliberately NOT written by scrape_schedule.py /
fetch_trends.py - both scripts' manual-fallback column contracts exclude
them - so this script computes both at load time via utils.show_id /
utils.metric_id. PLAN.md S4.0's original text ("fetch_trends.py computes
metric_id") is superseded by this; see PLAN.md S4.0's confirmed note.

Shows whose venue_name has no matching row in dim_venues (either because
venue_name was never published - see PLAN.md S3.1's confirmed source gap -
or because geocoding failed for it) get venue_id = NULL rather than a
dangling foreign key. This is expected, not an error, and is logged.
"""

import csv
import sys
from pathlib import Path

import duckdb

from utils import metric_id as make_metric_id
from utils import show_id as make_show_id
from utils import venue_id as make_venue_id

VENUES_PATH = Path("data/interim/venues_geocoded.csv")
ACCESSIBILITY_PATH = Path("data/interim/accessibility_matrix.csv")
SCHEDULE_PATH = Path("data/raw/schedule_raw.csv")
TRENDS_PATH = Path("data/raw/trends_raw.csv")
DB_PATH = Path("data/processed/pfw_analytics.db")

SCHEMA_SQL = """
-- Drop in reverse dependency order: CREATE OR REPLACE on dim_venues alone
-- fails once fact_runway_shows' FK exists from a prior run ("Cannot drop
-- entry dim_venues because there are entries that depend on it") - only
-- ever showed up on a genuine rerun against an already-built database.
DROP TABLE IF EXISTS fact_runway_shows;
DROP TABLE IF EXISTS fact_brand_metrics;
DROP TABLE IF EXISTS dim_venues;

CREATE TABLE dim_venues (
    venue_id VARCHAR PRIMARY KEY,
    venue_name VARCHAR NOT NULL,
    arrondissement INTEGER,
    latitude DOUBLE,
    longitude DOUBLE,
    accessibility_index INTEGER
);

CREATE TABLE fact_runway_shows (
    show_id VARCHAR PRIMARY KEY,
    brand_name VARCHAR NOT NULL,
    brand_key VARCHAR NOT NULL,
    designer VARCHAR,
    show_date DATE NOT NULL,
    show_time TIME,
    venue_id VARCHAR,
    FOREIGN KEY (venue_id) REFERENCES dim_venues(venue_id)
);

CREATE TABLE fact_brand_metrics (
    metric_id VARCHAR PRIMARY KEY,
    log_date DATE NOT NULL,
    brand_name VARCHAR NOT NULL,
    brand_key VARCHAR NOT NULL,
    search_index_score DOUBLE,
    is_control BOOLEAN NOT NULL DEFAULT FALSE
);
"""


def read_csv_rows(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _blank_to_none(value):
    value = (value or "").strip()
    return value if value else None


def load_dim_venues(con: duckdb.DuckDBPyConnection, venues_path: Path = VENUES_PATH) -> set[str]:
    venues = read_csv_rows(venues_path)
    rows = [
        (
            v["venue_id"],
            v["venue_name"],
            int(v["arrondissement"]) if _blank_to_none(v.get("arrondissement")) else None,
            float(v["latitude"]) if _blank_to_none(v.get("latitude")) else None,
            float(v["longitude"]) if _blank_to_none(v.get("longitude")) else None,
            None,  # accessibility_index is filled in by wire_accessibility()
        )
        for v in venues
    ]
    if rows:
        con.executemany(
            "INSERT INTO dim_venues VALUES (?, ?, ?, ?, ?, ?)", rows
        )
    return {v["venue_id"] for v in venues}


def wire_accessibility(con: duckdb.DuckDBPyConnection, accessibility_path: Path = ACCESSIBILITY_PATH) -> None:
    """PLAN.md S4 Accessibility Wiring Step - explicit, not implicit."""
    if not accessibility_path.exists():
        return
    rows = read_csv_rows(accessibility_path)
    if not rows:
        return

    con.execute(
        "CREATE OR REPLACE TEMP TABLE stg_accessibility "
        "(venue_id VARCHAR, accessibility_index INTEGER)"
    )
    con.executemany(
        "INSERT INTO stg_accessibility VALUES (?, ?)",
        [(r["venue_id"], int(r["accessibility_index"])) for r in rows],
    )
    con.execute(
        """
        UPDATE dim_venues
        SET accessibility_index = stg_accessibility.accessibility_index
        FROM stg_accessibility
        WHERE dim_venues.venue_id = stg_accessibility.venue_id
        """
    )
    con.execute("DROP TABLE stg_accessibility")


def load_fact_runway_shows(
    con: duckdb.DuckDBPyConnection,
    known_venue_ids: set[str],
    schedule_path: Path = SCHEDULE_PATH,
) -> None:
    shows = read_csv_rows(schedule_path)
    rows = []
    unresolved_venues = 0

    for s in shows:
        show_id = make_show_id(s["brand_key"], s["show_date"], s["show_time"])
        venue_name = _blank_to_none(s.get("venue_name"))
        venue_id = None
        if venue_name:
            candidate = make_venue_id(venue_name)
            if candidate in known_venue_ids:
                venue_id = candidate
            else:
                unresolved_venues += 1

        rows.append(
            (
                show_id,
                s["brand_name"],
                s["brand_key"],
                _blank_to_none(s.get("designer")),
                s["show_date"],
                _blank_to_none(s.get("show_time")),
                venue_id,
            )
        )

    if unresolved_venues:
        print(
            f"WARNING: {unresolved_venues} show(s) reference a venue_name "
            "with no matching row in dim_venues; venue_id left NULL rather "
            "than writing a dangling foreign key.",
            file=sys.stderr,
        )

    if rows:
        con.executemany(
            "INSERT INTO fact_runway_shows VALUES (?, ?, ?, ?, ?, ?, ?)", rows
        )


def load_fact_brand_metrics(con: duckdb.DuckDBPyConnection, trends_path: Path = TRENDS_PATH) -> None:
    metrics = read_csv_rows(trends_path)
    rows = [
        (
            make_metric_id(m["brand_key"], m["log_date"]),
            m["log_date"],
            m["brand_name"],
            m["brand_key"],
            float(m["search_index_score"]) if _blank_to_none(m.get("search_index_score")) else None,
            (m.get("is_control") or "").strip().lower() == "true",
        )
        for m in metrics
    ]
    if rows:
        con.executemany(
            "INSERT INTO fact_brand_metrics VALUES (?, ?, ?, ?, ?, ?)", rows
        )


def run_build_validation(con: duckdb.DuckDBPyConnection) -> None:
    """PLAN.md S4 Build Validation Rules - fail loudly (raise), don't warn."""
    errors: list[str] = []

    for table, pk in (
        ("dim_venues", "venue_id"),
        ("fact_runway_shows", "show_id"),
        ("fact_brand_metrics", "metric_id"),
    ):
        null_count = con.execute(
            f"SELECT COUNT(*) FROM {table} WHERE {pk} IS NULL"
        ).fetchone()[0]
        if null_count:
            errors.append(f"{table}.{pk} has {null_count} NULL value(s)")

        row_count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        if row_count == 0:
            errors.append(f"{table} has zero rows")

    orphan_count = con.execute(
        """
        SELECT COUNT(*) FROM fact_runway_shows s
        WHERE s.venue_id IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM dim_venues v WHERE v.venue_id = s.venue_id)
        """
    ).fetchone()[0]
    if orphan_count:
        errors.append(
            f"fact_runway_shows has {orphan_count} row(s) whose venue_id "
            "does not exist in dim_venues"
        )

    if errors:
        raise RuntimeError("Build validation failed:\n  - " + "\n  - ".join(errors))


def main() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    try:
        con.execute(SCHEMA_SQL)
        known_venue_ids = load_dim_venues(con)
        wire_accessibility(con)
        load_fact_runway_shows(con, known_venue_ids)
        load_fact_brand_metrics(con)
        run_build_validation(con)
    finally:
        con.close()

    print(f"Built {DB_PATH}")


if __name__ == "__main__":
    main()
