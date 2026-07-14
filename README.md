# Paris Fashion Week 2026 — The City Wrapped

A small analytics project mapping Paris Fashion Week (Womenswear Fall/Winter 2026/2027, March 2–10, 2026) across three pillars — **Schedule + Geo**, **Accessibility**, and **Brand Trends** — into a DuckDB star schema, browsable through a Streamlit app.

Full architecture, schema, and formulas are documented in [`.claude/plans/PLAN.md`](.claude/plans/PLAN.md), which also carries a running log of every real-world gap and correction found while building this (wrong-season data sources, missing venue data, dependency pins that don't install on modern Python, an idempotency bug, etc.) — read it if something here looks incomplete and you want to know why.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Pipeline

Run in order — each step reads the previous step's output:

```powershell
python scripts/scrape_schedule.py     # -> data/raw/schedule_raw.csv
python scripts/geocode_venues.py      # -> data/interim/venues_geocoded.csv
python scripts/fetch_trends.py        # -> data/raw/trends_raw.csv
python scripts/calculate_metrics.py   # -> data/interim/accessibility_matrix.csv
python scripts/build_database.py      # -> data/processed/pfw_analytics.db
```

`scrape_schedule.py` pulls whichever season is currently live on FHCM's site — it will **not** reproduce the March 2026 dataset checked into this repo. That dataset was hand-transcribed from FHCM's archived official PDF calendar (the correct one — see PLAN.md's season-correction note) per the documented manual-fallback path, since FHCM's live calendar always shows the current season, not March 2026 in July 2026.

## Run the app

```powershell
streamlit run app/Home.py
```

- **Home** — headline metrics (shows, venues, peak arrondissement)
- **Geographic Intelligence** — Folium map of runway venues, colored by accessibility
- **Accessibility Analysis** — top 10 most accessible venues + a Paris transit station directory
- **Brand Intelligence** — Google Trends search-attention lift per brand, Before/During/After
- **Paris Wrapped** — Fashion Week MVP, Busiest Day, Top Transportation Hub

## Current data state

- **98 real shows** across the real 9-day window (2026-03-02 to 2026-03-10), transcribed from FHCM's official PDF calendar.
- **11 of 98 shows have a verified venue** (Palais de Tokyo, Jardin des Tuileries, Grand Palais, Cour Carrée du Louvre, Palais d'Iéna, La Garde Républicaine, Maison de l'UNESCO, Institut de France, Château de Vincennes, Carrousel du Louvre), sourced from fashion press coverage and cross-checked across independent sources — FHCM itself publishes no venue data anywhere, live or archived. The remaining 87 (mostly small/indie brands) have no public venue information to source.
- **9 of those venues are geocoded** with real accessibility indices (Nominatim + IDFM station data); 1 (Maison de l'UNESCO) didn't resolve via Nominatim and is left ungeocoded rather than guessed.
- **3,069 real Google Trends rows** across all 98 brands + the Dior normalization control, covering the full baseline/active/post-event window.
- `data/processed/pfw_analytics.db` builds and validates cleanly against the current data.

## Known gaps

- **Venue/designer data**: FHCM (live site, house pages, and archived PDF) never publishes this. It's sourced by hand from press coverage for major houses only — see PLAN.md §3.1 for the full methodology, including what was searched and explicitly rejected for insufficient evidence.
- **Media pillar**: out of scope (v4.0 plan revision) — this project tracks Trends only, not news coverage.
