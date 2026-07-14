# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

This repo currently contains only a specification: `.claude/plans/PLAN.md` ("Paris Fashion Week 2026 — The City Wrapped", v3.0). **No source code, `requirements.txt`, `data/`, `app/`, or `scripts/` directories exist yet.** PLAN.md is the authoritative architecture reference — build against it, and treat its file paths, schema, and constants as the contract. The plan explicitly states no coding proceeds until the spec is reviewed and the next step is issued.

## Tech stack

Python 3.10+ with a standard venv. Core libraries (see PLAN.md §1 for pinned versions): `requests`, `beautifulsoup4`, `pandas`, `numpy`, `geopy`, `duckdb`, `plotly`, `streamlit`, `folium`, `pytrends`.

## Commands

Once implemented per the plan:

```powershell
# Environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Data pipeline — run in dependency order (each writes CSV/DB consumed by the next)
python scripts/scrape_schedule.py     # -> data/raw/schedule_raw.csv
python scripts/geocode_venues.py      # -> data/interim/venues_geocoded.csv
python scripts/fetch_trends.py        # -> data/raw/trends_raw.csv
python scripts/scrape_news.py         # -> data/raw/news_raw.csv
python scripts/calculate_metrics.py   # -> data/interim/accessibility_matrix.csv
python scripts/build_database.py      # -> data/processed/pfw_analytics.db

# Run the dashboard (entrypoint is Home.py, not app.py)
streamlit run app/Home.py
```

No test framework is specified in the plan.

## Architecture

Two layers connected by a DuckDB file:

1. **ETL scripts (`scripts/`)** — independent extract/transform steps that write to a staged `data/` tree (`raw/` → `interim/` → `processed/`). They run in the order above because later scripts read earlier outputs (e.g. `geocode_venues.py` reads `schedule_raw.csv`; `calculate_metrics.py` reads `venues_geocoded.csv` plus the external RATP station file in `data/external/`). `build_database.py` loads everything into `data/processed/pfw_analytics.db`.

2. **Streamlit UI (`app/`)** — `Home.py` plus multipage files under `app/pages/` (Geographic Intelligence, Accessibility Analysis, Brand Intelligence, Paris Wrapped). All pages query the DuckDB file directly; no separate API layer.

### DuckDB schema (star schema — see PLAN.md §4)

- `dim_venues` (venue_id PK, arrondissement, lat/lon, accessibility_index)
- `fact_runway_shows` (show_id PK, brand_name, show_date, venue_id FK → dim_venues)
- `fact_brand_metrics` (metric_id PK, log_date, brand_name, search_index_score, news_article_count)

Join rules: `fact_runway_shows.venue_id = dim_venues.venue_id`; `fact_runway_shows` to `fact_brand_metrics` on the **composite** `brand_name AND show_date = log_date`.

## Domain constants that must stay consistent everywhere

These are hardcoded across scraping, DB queries, and UI filters (PLAN.md §2). Do not parameterize them at runtime:

- **Baseline (pre-event) window:** `2026-02-16` to `2026-03-01`
- **Active event window:** `2026-03-02` to `2026-03-10`
- **Post-event window:** `2026-03-11` to `2026-03-18`

The **MVP Index** (`fetch_trends`/`calculate_metrics` and the "Paris Wrapped" page) is a 50/50 blend of Google Trends lift (active mean / baseline mean) and media lift (active article sum / baseline sum + 1) — full formula in PLAN.md §5.1. `"Dior"` is the fixed Trends normalization control brand.

## Conventions from the plan worth honoring

- **Brand-name cleaning:** strip corporate suffixes (`SA`, `S.A.S.`, `LLC`) so joins on `brand_name` match across schedule/trends/news sources.
- **Geocoding:** `Nominatim(user_agent="pfw_wrapped_2026")`, query format `f"{venue_name}, Paris, France"`, mandatory `time.sleep(1.5)` between calls; derive `arrondissement` from the last two digits of the `75xxx` postcode.
- **Drop non-physical venues** (`Digital Show`, `Online Presentation`, `To Be Confirmed`) before any spatial processing.
- **Accessibility index:** count of unique RATP stations within a strict 500 m Haversine radius of each venue.
- Backoff on HTTP 429 (Trends/news scraping) with exponential (`2^n` seconds) delay.
