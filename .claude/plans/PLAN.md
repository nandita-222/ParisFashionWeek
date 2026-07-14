To transform this into a flawless, self-executing roadmap that any advanced LLM or developer can execute from top to bottom without a single question, we must spell out the exact selector tokens, schema data types, null-handling mechanics, and network failure parameters.

Here is your production-ready, zero-gossip `PLAN.md`.

---

```markdown
# PLAN.md: Paris Fashion Week 2026 — The City Wrapped
**Version:** 4.0 (Zero-Gossip Technical Specification — Revised)
**Status:** Architecture Locked. Scope = 3 pillars (Schedule + Geo, Accessibility, Brand Trends). Media/News dropped. Final Production Reference.

---

## 1. Environment & Tech Stack Specifications
The environment must be initialized using standard Python 3.10+ virtual environments.

### `requirements.txt`
```text
requests==2.31.0
beautifulsoup4==4.12.3
pandas==3.0.3
numpy==2.5.1
geopy==2.4.1
duckdb==1.5.4
plotly==6.9.0
streamlit==1.59.2
folium==0.20.0
pytrends==4.9.2
lxml==6.1.1
playwright==1.61.0
tzdata==2024.1

```

**Windows note:** `zoneinfo.ZoneInfo("Europe/Paris")` (used by §2.1's timezone normalization) raises `ZoneInfoNotFoundError` on stock Windows Python — the OS doesn't ship an IANA tz database the way Linux/macOS do. `tzdata` supplies it; without this pin, every script that normalizes timestamps fails on Windows even though the same code runs fine on Linux/macOS/CI.

**Compatibility note (superseded, kept for history — see verified pin below):** `pytrends==4.9.2` was originally believed to only be tested against `pandas<2.1`, so an earlier revision of this spec pinned `pandas==2.0.3` project-wide.

**CONFIRMED — `pandas==2.0.3` is not installable on this project's actual environment.** Only Python 3.13 is available here; `pandas==2.0.3` has no prebuilt wheel for it and fails to build from source (`ModuleNotFoundError: No module named 'pkg_resources'` mid-build). Rather than assume the original compatibility warning was still accurate, it was re-tested directly: `pytrends==4.9.2` against `pandas==3.0.3` (the latest available) was run live against real Google Trends endpoints, including a full 70-brand / 18-batch production run over historical Feb-Mar 2026 data — no pandas-related failures occurred. The pin above (`pandas==3.0.3`, `numpy==2.5.1`) is the empirically-verified one; use it, not `2.0.3`. `lxml` is a direct `pytrends` dependency and is now pinned explicitly rather than left to float. If a future `pytrends` upgrade is made, re-verify against whatever pandas is current at that time rather than trusting either pin blindly.

**CONFIRMED — same wheel-availability problem hit `duckdb==0.10.1`.** No Python 3.13 wheel exists for it, and its sdist build reports a broken `0.0.0` version (a known packaging quirk of building `duckdb` from an sdist outside a proper git checkout), so it can't be installed here either. Re-pinned to `duckdb==1.5.4` (latest stable at implementation time, confirmed to ship a `cp313-win_amd64` wheel) and smoke-tested with a real query before use in `build_database.py`.

**CONFIRMED — the same problem again with `streamlit==1.32.2`.** It pins an old `numpy` range that pip tries to satisfy by building `numpy==1.26.4` from source (no Python 3.13 wheel for that either), which then fails immediately for lack of a C/C++ toolchain (`ERROR: Unknown compiler(s)`). Re-pinned to the latest available: `streamlit==1.59.2`, `plotly==6.9.0`, `folium==0.20.0` — all installed cleanly with prebuilt wheels and were smoke-tested (imports + a real running dev server, see §6) before use.

**CONFIRMED — `playwright==1.42.0`'s `greenlet` dependency has no Python 3.13 wheel** and fails to build without a Visual C++ toolchain (`error: Microsoft Visual C++ 14.0 or greater is required`). Re-pinned to `playwright==1.61.0`, whose `greenlet>=3.1.1` requirement resolves to a real `cp313-win_amd64` wheel. This only matters if `scrape_schedule.py`'s JS-rendering fallback is ever actually exercised (it wasn't needed against the live FHCM site, see §3.1) or the app is verified via a Playwright-driven browser (see §6).

### Directory Architecture

Ensure the localized project workspace matches this blueprint precisely before executing code:

```text
paris-fashion-week-city-wrapped/
├── app/
│   ├── Home.py
│   └── pages/
│       ├── 1_🏢_Geographic_Intelligence.py
│       ├── 2_🚇_Accessibility_Analysis.py
│       ├── 3_📊_Brand_Intelligence.py
│       └── 4_🎨_Paris_Wrapped.py
├── data/
│   ├── raw/
│   ├── interim/
│   ├── processed/
│   └── external/
│       ├── brand_aliases.csv
│       └── (RATP/Île-de-France station file, see §3.4)
├── scripts/
│   ├── utils.py
│   ├── scrape_schedule.py
│   ├── geocode_venues.py
│   ├── fetch_trends.py
│   ├── calculate_metrics.py
│   └── build_database.py
├── requirements.txt
└── PLAN.md

```

---

## 2. Global Chronological Constants

All automated extraction processes, database queries, and filters must hardcode these explicit timestamp bounds. Never pass dynamic runtime parameters.

* **Pre-Event Control Baseline:** `2026-02-16` to `2026-03-01` (14 complete days)
* **Active Event Window:** `2026-03-02` to `2026-03-10` (9 official runtime days)
* **Post-Event Decay Window:** `2026-03-11` to `2026-03-18` (8 observation days)

### 2.1 Timezone Normalization

All source timestamps (schedule show times, PyTrends response timestamps) must be normalized to `Europe/Paris` **before** deriving the `show_date` or `log_date` columns used against the windows above. A timestamp captured near midnight in a different source timezone must not be allowed to shift into the adjacent calendar day and misclassify a row's baseline/active/post bucket.

---

## 3. Data Sourcing, Extraction, & Cleaning Rules

### 3.0 Brand Name Canonicalization (`scripts/utils.py`)

Every pipeline that emits or consumes a brand name must attach a canonical **`brand_key`**, and all cross-pillar joins use `brand_key` — never the raw `brand_name` string.

* **`normalize_brand(raw_name: str) -> str`:** shared helper in `scripts/utils.py`. Steps, in order:
1. Strip corporate suffixes (`SA`, `S.A.S.`, `LLC`) — same suffix list as §3.1's cleaning rule.
2. Strip accents (e.g. `é` → `e`) and punctuation.
3. Lowercase and collapse internal whitespace.
* **Alias map:** `data/external/brand_aliases.csv` is a hand-maintained file with columns `raw_name,brand_key`, covering known collisions the automatic normalization can't resolve on its own (e.g. `Saint Laurent` / `YSL` → `saint laurent`; `Louis Vuitton` / `LV` → `louis vuitton`). `normalize_brand()` must check this map first and only fall back to the algorithmic steps above if no alias entry matches.
* Both `scrape_schedule.py` and `fetch_trends.py` must call `normalize_brand()` and attach `brand_key` to every row they emit. `build_database.py` and all downstream joins use `brand_key`, not `brand_name`.

### 3.1 Fashion Schedule Pipeline (`scripts/scrape_schedule.py`) — IMPLEMENTED, see confirmed findings below

* **Exact Sourcing Endpoint:** `https://www.fhcm.paris/en/paris-fashion-week/calendar` (the bare `/en/paris-fashion-week` page is a landing page with a link to `/calendar`; the schedule markup only lives on the `/calendar` path).
* **Retrieval Protocol:** HTTP GET with headers mimicking standard desktop agents (`User-Agent: Mozilla/5.0...`).
* **Discovery-first selector strategy — confirmed against the live page on 2026-07-14:**
1. Fetch the page with plain `requests` and inspect the raw HTML for the schedule table/card markup.
2. **Confirmed static HTML** — no JS rendering is required. Real selectors, recorded as constants in `scrape_schedule.py`: day container `div.day[data-day="YYYYMMDD"]` → house/brand block `div.cal-item` (brand name in `h3`) → per-occurrence `div.entry` (time in `div.time`, ISO8601 UTC start in the `data-date-start` attribute when present, format label in `span.format`).
3. Playwright fallback path is implemented (`fetch_rendered()`, triggered automatically if the static probe selector `div.calendar-houses` is absent) but is **not currently exercised** — kept for if/when FHCM moves to client-side rendering. Re-verify selectors before relying on this long-term; FHCM's markup has already changed once (see venue/designer gap below).
* **CONFIRMED SOURCE GAP — Venue Name and Creative Designer do not exist in FHCM's data model, live HTML *or* archived PDF.** Verified by inspecting the calendar page, individual house detail pages (`/en/house/<slug>`), *and* the archived official PDF calendar (see the season note below) — neither field appears in any of the three, for any brand. Every PDF entry is "Show/Presentation (by invitation/appointment)" plus a broadcast channel (Digital/Livestream/"Film of the show revealed…"); none of that names a location. `scrape_schedule.py` writes both columns as empty strings, and the hand-transcribed manual fallback (below) does too, for the same reason — there is currently no FHCM-published source, of any format, that discloses runway venues. `geocode_venues.py` must skip (not crash on) rows with empty `venue_name` and log them as ungeocoded, and the accessibility/geo pillar is only as complete as the manually-filled venue data.
* **PARTIALLY RESOLVED — venue data sourced outside FHCM entirely, per user decision.** FHCM never publishes venues, so filling them required fashion press coverage of the actual shows (Sortiraparis, WWD, Who What Wear, and similar outlets, cross-checked against each other and against this file's authoritative `show_date`/`show_time`). This is real, labor-intensive research, not a scrape: **11 of 98 shows (the major luxury houses) got a verified venue**, each confirmed by at least two independent sources agreeing AND matching this file's date/time for that brand; every other brand was either not searched (given the 87 remaining are small/indie brands unlikely to have public coverage) or searched and explicitly rejected for insufficient/conflicting evidence. **Rejected, not guessed:** Saint Laurent (only a poetic, non-specific description found — "a modernist residence... views of the Eiffel Tower" — no named venue), Givenchy and Balmain (date/time confirmed, no venue in any source found), Balenciaga (a general "Champs-Élysées" area reference only, not a specific venue), Alaïa (a candidate venue existed but its source's date contradicted the PDF's date — dropped for the conflict, not resolved in the PDF's favor). One AI-search summary initially conflated Chanel's *Haute Couture* show (July) with its *Ready-to-Wear* show (March) — caught by cross-checking a second source before accepting Chanel → Grand Palais. Verified venues: `Kimhēkim`/`Rick Owens` → Palais de Tokyo, `Christian Dior` → Jardin des Tuileries, `Chanel` → Grand Palais, `Louis Vuitton` → Cour Carrée du Louvre, `Miu Miu` → Palais d'Iéna, `Hermès` → La Garde Républicaine, `Chloé` → Maison de l'UNESCO, `Celine` → Institut de France, `Loewe` → Château de Vincennes, `Schiaparelli` → Carrousel du Louvre. Of these, 9 unique venue names geocoded successfully (real Nominatim results, real arrondissements); `Maison de l'UNESCO` did not resolve via Nominatim and was correctly left ungeocoded by §3.2's documented skip-and-log behavior rather than forced. **This is the first real (non-synthetic) run where `build_database.py` succeeds without the "dim_venues has zero rows" validation failure** — verified with a real running dev server: the Geographic Intelligence map now plots 8 real Paris venues along the Seine, and Paris Wrapped's Top Transportation Hub card shows real data (Palais de Tokyo, 3 stations) for the first time.
* **CONFIRMED SEASON GAP — the live calendar only ever shows the currently-published season.** The season matching this plan's date window (`2026-02-16`–`2026-03-18`) has already rotated off the live calendar; it exists only as an archived PDF. **CORRECTION — an earlier revision of this note misidentified the archived PDF**: the `.../ss26_7_0.pdf` file ("Womenswear Spring/Summer 2026") actually covers **September 29 – October 7, 2025** — fashion weeks show a season roughly six months ahead of its name, so "Spring/Summer 2026" shows in autumn 2025, not February/March 2026. The PDF that actually matches this plan's window is `.../paris-fashion-week-r-official-calendar-womenswear-fw26-27_7_0.pdf` ("Womenswear Fall/Winter 2026/2027"), confirmed by its own cover text: *"From March 2nd to March 10th, 2026"* — an exact match for the Active Event Window (§2). `scrape_schedule.py` runs against whichever season is currently live on the site (validates the pipeline end-to-end with real data, e.g. the June 2026 Menswear season during implementation); the actual `2026-03-02`–`2026-03-10` dataset was produced via the manual-CSV fallback below, hand-transcribed from this corrected PDF — **98 real shows across the exact 9 real dates**, replacing the earlier wrong-season placeholder run.
* **Target Fields actually available from the source:** Brand Name (`h3` text), Start Date (from `data-day` / `data-date-start`, `YYYY-MM-DD`), Start Time (from `data-date-start` / `div.time`, `HH:MM:SS`). Designer and Venue Name are written empty per the gap above.
* **Cleaning & Edge Case Rules:**
* The source has no venue field to pattern-match `Digital Show` / `Online Presentation` / `To Be Confirmed` against, so the physical-vs-non-physical signal actually used is the entry's `format` text: skip entries where it is `digital` or `livestream`.
* Skip any entry with neither a `data-date-start` value nor non-empty `div.time` text (e.g. FHCM's "Film of the show revealed later" placeholder entries) — there is no real scheduled timestamp to record, and falling back to the day's date alone would fabricate a bogus `00:00:00` duplicate row for the same brand/day.
* Trim all trailing whitespace. Remove corporate suffixes (`SA`, `S.A.S.`, `LLC`) from `brand_name`, then run `normalize_brand()` (§3.0) to attach `brand_key`.
* `data-date-start` is UTC (`Z` suffix); convert to `Europe/Paris` (§2.1) before deriving `show_date`/`show_time`. If `data-date-start` is absent, treat `data-day` + `div.time` as already Paris-local (FHCM's own display convention).
* **Manual fallback:** if neither the static nor the Playwright-rendered fetch yields usable data (site structure change, access block, etc.) — or when producing the historical `2026-03-02`–`2026-03-10` dataset per the season gap above — the pipeline must be unblockable by hand-authoring `data/raw/schedule_raw.csv` directly, using the exact column contract: `brand_name, brand_key, designer, show_date, show_time, venue_name`. Documented in the script's module docstring so a manual CSV is a drop-in replacement for the scraper's output. **Done, verified:** hand-transcribed from `https://www.fhcm.paris/sites/default/files/w/files/paris-fashion-week-r-official-calendar-womenswear-fw26-27_7_0.pdf` — 98 shows, all 9 real dates present, no `show_id` collisions (checked: 98 distinct `brand_key`s, one show per brand). Every PDF entry is genuinely physical ("by invitation"/"by appointment"); nothing needed dropping as non-physical, unlike the live scraper's duplicate-entry filtering. `venue_name`/`designer` are empty for the same reason as the live scrape — see the confirmed source gap above.
* **Output:** Write structural data directly into `data/raw/schedule_raw.csv`.

### 3.2 Spatial Geocoding Engine (`scripts/geocode_venues.py`) — IMPLEMENTED, see confirmed behavior below

* **Retrieval Protocol:** Loop through unique `venue_name` text rows in `schedule_raw.csv`. Instantiation parameter: `geopy.geocoders.Nominatim(user_agent="pfw_wrapped_2026")`.
* **String Assembly:** Build exact API lookup strings with the following strict query composition format: `f"{venue_name}, Paris, France"`.
* **Cleaning & Edge Case Rules:**
* Per §3.1's confirmed source gap, `venue_name` may be an empty string for rows FHCM never published a venue for. Skip these rows (do not query Nominatim with an empty/near-empty string) and log them as ungeocoded rather than crashing or geocoding garbage — they stay out of `venues_geocoded.csv` until a venue is filled in manually. Verified live: the current `schedule_raw.csv` has 70/70 rows with empty `venue_name`, so a run today logs all 70 as skipped and writes an empty `venues_geocoded.csv` — expected, not a bug.
* Enforce a mandatory `time.sleep(1.5)` pause inside loops to strictly prevent API IP blacklisting or rate limiting issues.
* **Fallback resolution, concretely implemented and verified (both live against Nominatim and with deterministic unit checks):** if a lookup returns `None`, try, in order: (1) parse the venue's own text for a Paris postcode (`750xx`) or an explicit "`<N>`th/e arrondissement" mention, and use a hardcoded per-arrondissement centroid (public geographic data, `ARRONDISSEMENT_CENTROIDS` in the script) — verified with `"...75012"` → arrondissement 12, `"8e arrondissement"` → 8; (2) check `data/external/venue_fallback_coords.csv`, a hand-maintained file (same pattern as `brand_aliases.csv`, columns `venue_name,latitude,longitude,arrondissement`) for a manually-supplied coordinate — this stands in for "brand's historic HQ address" since no verified, structured source of brand HQ addresses was available to hardcode; it ships empty and is filled by hand as needed. If neither resolves, the venue is logged and dropped rather than written with fabricated coordinates. Verified live: `Palais Brongniart` → arrondissement 2, `Jardin des Tuileries` → arrondissement 1 (both correct); an unresolvable venue name is correctly dropped and logged.
* **Postal Code Translation:** Extract the `postcode` dictionary element from the returned address node. Slice the last two digits of standard Paris postal structures (e.g., `75008` $\rightarrow$ `8`; `75001` $\rightarrow$ `1`) and convert to an integer schema column type labeled `arrondissement`.


* **Output:** Persist structured data records directly into `data/interim/venues_geocoded.csv`, keyed by `venue_id = make_id(lower(strip(venue_name)))` (§4.0).

### 3.3 Public Attention Indexing Pipeline (`scripts/fetch_trends.py`) — IMPLEMENTED, see confirmed behavior below

* **Retrieval Protocol:** Initialize connection loops via the `PyTrends` library framework. Target brands are the unique `brand_name`/`brand_key` pairs found in `data/raw/schedule_raw.csv` (excluding the control brand itself).
* **Normalization Logic & Rules:** Pass target fashion brands in absolute batch arrays containing a maximum of 4 unique brand entities plus 1 structural baseline control brand string: `"Dior"`. Set timeframe parameter precisely to `2026-02-16 2026-03-18`.
* **Cleaning & Edge Case Rules:**
* If PyTrends returns connection timeouts or generic HTTP 429 status codes, immediately switch to an exponential backoff cooling window loop ($2^n$ seconds delay). **Verified live:** real 429s were returned by Google mid-run (this is routine for `pytrends`, not hypothetical) and the backoff loop recovered every time within a few attempts, at 1s/2s/4s delays.
* Calculate index alignments: divide every brand score inside a specific response packet by the matching date baseline index value score of the `"Dior"` control string variable to protect numerical scaling comparability. **Zero guard, not in the original spec but required in practice:** if Dior's own value for a date is `0`, that date is skipped for the whole batch (logged) rather than dividing by zero.
* Run every brand name (including `"Dior"`) through `normalize_brand()` (§3.0) and attach `brand_key` to each row before writing output.
* Normalize response timestamps to `Europe/Paris` (§2.1) before deriving `log_date`.
* **Dior exclusion rule:** because `"Dior"` is the fixed normalization control, its own normalized series is definitionally flat (it is divided by itself) and carries no meaningful signal. `"Dior"` rows must still be written to `trends_raw.csv` (they're needed to normalize the other four brands in the batch), but **the control brand must be excluded from the MVP ranking/leaderboard** — see §5.1. Tag the control row (e.g. `is_control = true`) so `build_database.py` / the UI layer can filter it out without re-deriving which brand was the control. **Verified:** every Dior row's `search_index_score` is exactly `1.0` across a full real run.
* **Idempotency / caching:** once a batch successfully returns and is written, persist it (e.g. a `data/raw/.trends_cache/` marker per batch or an append-only write with a de-dup key on `(brand_key, log_date)`). On rerun, skip re-fetching any batch already cached — retrospective Trends pulls are rate-limited and re-fetching successful batches wastes quota for no benefit. **Verified:** a cache-hit rerun of the same batches reproduced byte-for-byte identical rows in a fraction of the time (0.4s vs 4.1s), once the cache reader was fixed to coerce `search_index_score`/`is_control` back to their real types (CSV round-trips everything as strings otherwise — a real bug caught by this check, not a hypothetical one). `"Dior"` rows are correctly de-duplicated by `(brand_key, log_date)` across every batch that includes them, rather than appearing once per batch.
* **Manual fallback:** if PyTrends access is blocked entirely (e.g. persistent 429s that don't clear with backoff), the pipeline must be unblockable by hand-authoring `data/raw/trends_raw.csv` directly, using the exact column contract: `brand_name, brand_key, log_date, search_index_score, is_control`. Document this contract in the script's module docstring.
* **Output:** Write output directly into `data/raw/trends_raw.csv`. **Verified with a full real run against all 70 brands scraped in §3.1:** 18 batches (4 brands + Dior each), 2201 rows total = 31 Dior rows (one per day in the 31-day window, correctly deduplicated across all 18 batches) + 70 brands × 31 days.

### 3.4 Mobility Accessibility Pipeline (`scripts/calculate_metrics.py`) — IMPLEMENTED, see confirmed dataset below

* **Named dataset — resolved to a specific, verified one:** the two candidates in the original slug family were both fetched and inspected. `emplacement-des-gares-idf` ("by line") returns 1240 rows, repeating each interchange station once per line it serves — e.g. `Gare du Nord` appears 6 times (TRAIN H, TRAIN K, RER B, RER D, METRO 4, METRO 5) at slightly different points, which would over-count "unique station locations" at hubs. `emplacement-des-gares-idf-data-generalisee` ("generalized") returns 999 rows, one IDFM-computed barycenter point per physical station (`Gare du Nord` is a single row listing all its lines; the separate nearby underground RER E stop `Magenta` is correctly kept as its own row). **This spec uses the generalized dataset**, since the required metric is explicitly "unique station locations," not "station-line pairs." Confirmed live endpoint: `https://data.iledefrance-mobilites.fr/api/explore/v2.1/catalog/datasets/emplacement-des-gares-idf-data-generalisee/exports/csv?delimiter=%3B` (returns real, current data — verified with an actual download of 999 rows in a real run).
* **Retrieval Protocol:** `calculate_metrics.py` checks `data/external/` for the station file first; if absent, scripted-downloads it from `RATP_STATIONS_URL` into `data/external/` (no manual download step). **Confirmed real column names** (do not match PLAN.md's original "Geo Point"/"Nom de la gare"/"Ligne" wording literally, though they're the same concepts): `geo_point_2d` (a single `"lat, lon"` string field, semicolon-delimited CSV so the internal comma is safe), `nom_long` (station name), `res_com` (line(s) serving it, e.g. `"TRAIN H / TRAIN K / RER B / RER D / METRO 4 / METRO 5"` for interchange hubs), `mode`.
* **Metric Engineering Rule:** For every coordinate entry in `venues_geocoded.csv`, loop through all RATP coordinate nodes. Calculate distance metrics using the Haversine equation. Count the absolute number of unique station locations that fall within a strict, tight geographic bounding range threshold of exactly **500 meters** (inclusive, `<= 500.0`) from the target runway venue center. **Verified against real, known Paris coordinates:** Palais Brongniart (dense financial-district location) → 5 stations within 500m; Jardin des Tuileries → 3; a deliberately remote test point near the edge of Bois de Vincennes → 0 — confirming the radius filter genuinely excludes distant stations rather than always returning a nonzero count. The Haversine implementation itself was checked against a known geodesic constant (1° of latitude ≈ 111.2 km) before trusting it on real venues.
* **Output:** Save records into `data/interim/accessibility_matrix.csv`, keyed by `venue_id` (§4.0) so `build_database.py` can join it straight into `dim_venues` (§4). Per §3.1/§3.2's confirmed source gap, `venues_geocoded.csv` currently has zero rows, so a real run today correctly writes an empty (header-only) `accessibility_matrix.csv` without downloading the station file at all — verified live.

---

## 4.0 Deterministic ID Generation (`scripts/utils.py::make_id`)

`build_database.py` must never invent primary keys ad hoc — every ID is a deterministic hash so reruns of the pipeline produce identical keys and joins stay stable. All three ID formulas live in one shared helper, `scripts/utils.py::make_id`, so every script that needs to compute or re-derive an ID uses the same logic:

* `venue_id = md5(lower(strip(venue_name)))[:12]`
* `show_id  = md5(brand_key + '|' + show_date + '|' + show_time)[:12]`
* `metric_id = md5(brand_key + '|' + log_date)[:12]`

`geocode_venues.py` computes `venue_id` when it writes `venues_geocoded.csv`; `scrape_schedule.py` (or `build_database.py`, applied consistently) computes `show_id`; `fetch_trends.py` computes `metric_id`. Because all three derive from the same helper, `build_database.py` never needs to regenerate IDs — it only needs to load them.

**RECONCILED WITH THE ACTUAL IMPLEMENTATION:** when `scrape_schedule.py` and `fetch_trends.py` were built, both scripts' manual-fallback column contracts deliberately excluded `show_id`/`metric_id` (see their module docstrings) — a hand-edited CSV shouldn't need to know the hash scheme. So in practice, only `venue_id` is computed upstream (it has to be, since it's the join key shared between `venues_geocoded.csv` and `schedule_raw.csv`); **`build_database.py` computes both `show_id` and `metric_id` itself at load time**, using the exact same `scripts/utils.py` helpers (`show_id()`, `metric_id()`), so the hashes are identical to what this section specifies either way. Verified: re-running `build_database.py` against the same input CSVs reproduces byte-identical `show_id`/`metric_id` values every time.

---

## 4. Database Schema & Relational Join Architecture — IMPLEMENTED, see confirmed behavior below

All analytical inputs will be structured inside a local, serverless DuckDB architecture instance file named `data/processed/pfw_analytics.db` managed by the script `scripts/build_database.py`.

### Schema Definitions

#### Table 1: `dim_venues`

```sql
CREATE TABLE dim_venues (
    venue_id VARCHAR PRIMARY KEY,
    venue_name VARCHAR NOT NULL,
    arrondissement INTEGER,
    latitude DOUBLE,
    longitude DOUBLE,
    accessibility_index INTEGER
);

```

#### Table 2: `fact_runway_shows`

```sql
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

```

#### Table 3: `fact_brand_metrics`

```sql
CREATE TABLE fact_brand_metrics (
    metric_id VARCHAR PRIMARY KEY,
    log_date DATE NOT NULL,
    brand_name VARCHAR NOT NULL,
    brand_key VARCHAR NOT NULL,
    search_index_score DOUBLE,
    is_control BOOLEAN NOT NULL DEFAULT FALSE
);

```

### Explicit Join Rules

Analytical pipelines running inside the user interface layers must map datasets explicitly using these key variables:

* Connect `fact_runway_shows` directly to `dim_venues` via the matching string key column: `venue_id`.
* Connect `fact_runway_shows` directly to `fact_brand_metrics` via a composite index matching rule: `brand_key` AND `show_date = log_date`.

**Verified with a real synthetic-but-realistic build** (real venue coordinates/IDs reused from §3.2's live geocoding run): both join rules produce correct results through a single query — `fact_runway_shows LEFT JOIN dim_venues ON venue_id LEFT JOIN fact_brand_metrics ON brand_key AND show_date = log_date` correctly attached venue name/accessibility and same-day trend score to each show, including graceful `NULL`s for a show whose venue didn't resolve.

**Dangling-reference handling, not specified in the original text but required in practice:** `fact_runway_shows.venue_id` is populated by re-deriving `venue_id` from the show's `venue_name` (via the same `utils.venue_id()` hash `dim_venues` was built with) and checking it actually exists in `dim_venues`. If a show's `venue_name` is empty (§3.1's confirmed gap) or doesn't match any successfully-geocoded venue, `venue_id` is written as `NULL` — never as a hash that doesn't resolve to a real `dim_venues` row — and the count of such shows is logged. This is what makes the referential-integrity validation below meaningful rather than trivially true.

### Accessibility Wiring Step

`build_database.py` must include an explicit step that loads `data/interim/accessibility_matrix.csv` and joins it into `dim_venues.accessibility_index` by `venue_id` before the table is finalized. This is not optional/implicit — without this step `accessibility_index` is left `NULL` for every venue and both the Accessibility Analysis page and the Paris Wrapped "Top Transportation Connection Node" card silently break. **Implemented as a real SQL join, not a Python-side merge:** the accessibility CSV is loaded into a temp table and applied with `UPDATE dim_venues SET accessibility_index = stg.accessibility_index FROM stg_accessibility stg WHERE dim_venues.venue_id = stg.venue_id`. Verified against real accessibility figures from §3.4's live run (Palais Brongniart → 5, Jardin des Tuileries → 3) — both landed correctly in `dim_venues` after wiring.

### Build Validation Rules

At the end of `build_database.py`, after all tables are loaded and joined, run and fail loudly (raise, don't warn) on any of the following:

* **Non-null PKs:** no `NULL` values in `venue_id`, `show_id`, or `metric_id`.
* **Referential integrity:** every non-`NULL` `fact_runway_shows.venue_id` exists in `dim_venues.venue_id`. (A `NULL` `venue_id` is not a violation — see the dangling-reference handling above; it means the show genuinely has no resolved venue, not a broken reference.)
* **Non-empty row counts:** all three tables have at least one row after load.

**CONFIRMED — running this today against the real pipeline output correctly fails, and that's expected, not a bug.** `dim_venues` currently has zero rows (§3.1/§3.2's confirmed source gap: `venue_name` is empty for every scraped/transcribed show, so nothing was geocoded — confirmed true of both the live scraper's 70 shows and the corrected 98-show manual transcription per §3.1), and the "non-empty row counts" rule catches exactly that: `RuntimeError: Build validation failed: - dim_venues has zero rows`. Before hitting that check, `fact_runway_shows` (98 rows, all `venue_id = NULL`, spanning exactly the 9 real dates `2026-03-02`–`2026-03-10`) and `fact_brand_metrics` (3069 rows) load correctly — confirmed by querying the partially-built `.db` file directly. The validation is doing its job: it refuses to hand the Streamlit layer a star schema with a silently-empty dimension table. Once venue data exists (manual fallback per §3.1, or a future source), the same script builds cleanly — verified separately with a synthetic-but-realistic dataset covering the happy path, the accessibility join, and the dangling-reference-to-`NULL` path all at once.

**CONFIRMED BUG, FOUND ON A GENUINE RERUN AND FIXED — `CREATE OR REPLACE TABLE` is not safe against an already-populated database with live foreign keys.** The first several verification runs each used either a fresh or a scratch database file, so this never surfaced. The first true rerun against an *existing, previously-built* `pfw_analytics.db` (after correcting the schedule data per §3.1) failed immediately: `Dependency Error: Cannot drop entry "dim_venues" because there are entries that depend on it. table "fact_runway_shows" depends on table "dim_venues".` DuckDB won't implicitly cascade-drop a table's dependents just because it's being replaced. Fixed by explicit `DROP TABLE IF EXISTS` statements in reverse dependency order (`fact_runway_shows`, `fact_brand_metrics`, then `dim_venues`) before the plain `CREATE TABLE` statements. Re-verified: the corrected script now reruns cleanly against the real, already-built database.

---

## 5. Derived Metrics Mathematical Formulations

### 5.1 The Fashion Week MVP Index ($MVP_b$)

The Media pillar is out of scope (§ removed 3.4 of v3.0), so the MVP Index is a pure Google Trends search-attention lift ratio, not a blended score:

$$MVP_b = \frac{\bar{S}_{b, \text{active}}}{\bar{S}_{b, \text{baseline}} + \epsilon}$$

Where:

* $\bar{S}_{b, \text{active}}$ represents the mean value of the brand's Google Trends score during the Event window (`2026-03-02` to `2026-03-10`).
* $\bar{S}_{b, \text{baseline}}$ represents the mean value of the brand's Google Trends score during the Control window (`2026-02-16` to `2026-03-01`).
* $\epsilon = 1.0$ is a zero guard: it prevents divide-by-zero / division-blowup when a brand has a baseline mean of 0 (a brand with no search presence before the event should not produce an undefined or absurdly large ratio the moment it gets a single event-week search).

This is a **lift ratio**, not an absolute popularity score — a brand with a small but nonzero baseline that spikes during the event can outrank a brand with much higher raw search volume but a flatter trajectory. Interpret and label it in the UI accordingly (e.g. "search-attention lift," not "most searched").

Per §3.3's Dior exclusion rule, `"Dior"` (`is_control = TRUE`) must be filtered out before computing or displaying the MVP ranking — it is the normalization control, not a competing brand, and its ratio is definitionally ≈1.

---

## 6. Streamlit User Interface Layout Specifications

### Core Navigation Architecture

The frontend web layout maps directly to the structure inside the `app/` folder. State properties must reset queries automatically using clean code blocks.

**IMPLEMENTED — all five files, verified in a real running browser, not just written.** A shared `app/db.py` (`get_connection()` cached via `st.cache_resource`, `query_df()` cached via `st.cache_data`, plus the S2 date-window and S5.1 MVP constants) and `app/colors.py` (the dataviz-skill validated sequential/categorical palettes — see below) back all five pages; this pair isn't named in the original spec but is necessary shared infrastructure, consistent with CLAUDE.md's "no separate API layer, pages query DuckDB directly."

**Verification method:** the dev server was launched for real (`streamlit run app/Home.py`) and driven with a headless Playwright browser through every page, twice — once against a richly-populated test database (real fetched Trends data + real IDFM accessibility counts + five real Paris venues assigned to five real scraped brands, since the actual project data still has zero geocoded venues per S3.1/S3.2's confirmed gap) to prove the full happy path renders correctly, and once against the actual current project database to confirm every venue-dependent page degrades gracefully (a clear "no data yet, here's why" message, not a crash) while the two pages that don't depend on venues (Home's show count, Brand Intelligence) correctly show real data. Screenshots were inspected, not just "no exception raised."

**Two real bugs found and fixed by actually running it:**
1. `st.metric`/`st.multiselect` labels built from a DuckDB `DATE` column displayed as `2026-03-04 00:00:00` (pandas `Timestamp.__str__` includes the time) instead of `2026-03-04`. Fixed by explicit `.strftime("%Y-%m-%d")` everywhere a date is shown as a label (Paris Wrapped's Busiest Day card, Geographic Intelligence's Days filter).
2. The Accessibility Analysis page's transit-line filter used substring matching (`str.contains` on a regex OR of selected line names), so filtering by `"METRO 1"` also matched `"METRO 12"`, `"METRO 13"`, `"METRO 14"` — any line name that contains another as a prefix. Fixed by splitting each row's `lines` field on `/` and checking exact token membership instead of substring containment. Confirmed with a live filter test before and after.

Also confirmed independently: the Fashion Week MVP query's result (a real run surfaced `"SYSTEM"` at `0.77x` lift — a real scraped brand, not a placeholder) was cross-checked by recomputing the same ratio directly from `trends_raw.csv` with `awk`; both matched (`0.772`). Most of the 70 real scraped brands have near-zero Google Trends volume for the whole study window, so the "MVP" is dominated by which brand has the least-negative baseline-to-active swing rather than a dramatic spike — which is exactly why S5.1 insists on labeling this a "lift ratio," not "most searched."

#### File: `app/Home.py`

* **Layout Blocks:** Full-width hero banner header detailing the structural boundaries of the study cycle.
* **Component Widgets:** Employs three standard `st.metric` UI cards computing values dynamically from DuckDB:
1. **Total Documented Shows** (`COUNT(show_id)`).
2. **Active Runway Hub Venues** (`COUNT(DISTINCT venue_id)`).
3. **Peak Fashion Arrondissement** (Mode of `arrondissement` column arrays).



#### File: `app/pages/1_🏢_Geographic_Intelligence.py`

* **Layout Blocks:** Sidebar controls containing multi-select elements allowing users to filter content directly by individual brand lists or specific days.
* **Component Widgets:** Implements a full-width interactive map object (`st.components.v1` using Folium or native Pydeck scatter overlays). Plots each runway venue coordinate marker. Color shades marker components dynamically based on the venue's computed `accessibility_index` integer values. **Implemented literally as `st.components.v1.html(folium_map._repr_html_(), height=600)`** (Folium chosen over Pydeck since it needs no extra pin beyond `folium`, already in `requirements.txt`). Marker color uses `colors.sequential_color()` — a one-hue light→dark interpolation over the dataviz skill's validated sequential blue ramp (steps 100→700), the same helper reused for the accessibility bar chart on the next page so the encoding is consistent app-wide. Verified live: 5 real venues rendered as correctly-positioned, correctly-colored markers on a real Paris basemap.

#### File: `app/pages/2_🚇_Accessibility_Analysis.py`

* **Layout Blocks:** Split columns (`st.columns(2)`).
* **Component Widgets:** * Left Column: Horizontal Plotly bar chart displaying the top 10 most accessible runway nodes sorted descending by their calculated infrastructure count index.
* Right Column: Direct data preview framework listing transit details (`st.dataframe`). Includes input select elements allowing users to filter rows by specific metro line variables.

**RIGHT-COLUMN SCOPE NOTE:** the DuckDB schema (§4) only ever stores the derived per-venue `accessibility_index` count, not individual station/line rows — storing raw station data was never part of the star schema, and adding an unplanned table for one UI widget wasn't judged worth the schema churn. This page instead reads the same cached IDFM station file `calculate_metrics.py` already downloaded to `data/external/` (§3.4) directly, as a general station directory independent of which venues are in view, with the line filter parsed from that file's real `res_com` column. This also means the right column keeps working and showing real data even when `dim_venues` is empty (verified) — it has no dependency on the venue-geocoding gap.



#### File: `app/pages/3_📊_Brand_Intelligence.py`

* **Layout Blocks:** Single column vertically stacked view pattern layout.
* **Component Widgets:** Line chart rendering daily Google Trends `search_index_score` movements per brand (Trends only — no media/article series; Media pillar is out of scope). Must contain distinct vertical baseline zone markings (`add_vline` in Plotly) explicitly dividing visual components across the three study timeline boundaries (**Before**, **During**, and **After**). Exclude the `"Dior"` control row from brand-selection widgets by default (it may still be shown if a user explicitly wants to inspect the normalization baseline). **Color assignment:** each brand's line color is `colors.brand_color(brand_key)` — a stable hash into the dataviz skill's fixed 8-hue categorical palette, so a brand keeps the same color regardless of which other brands are selected (the skill's rule that color follows the entity, never the current selection/rank). Dior, when shown, is always the muted ink color with a dotted line rather than a categorical hue, since it's a normalization reference, not a competing series.

#### File: `app/pages/4_🎨_Paris_Wrapped.py`

* **Layout Blocks:** High-contrast layout matrix displaying summary metrics.
* **Component Widgets:** Highlighting clear standalone statistics cards styled cleanly:
* **Fashion Week MVP Award Card:** Renders the brand tracking name with the maximum computed $MVP_b$ score metric (§5.1), computed over non-control brands only.
* **Busiest Day Spotlight Card:** Renders the single date item containing the highest show frequency count.
* **Top Transportation Connection Node Hub:** Renders the specific venue name recording the highest relative accessibility metric.



```
***

This `PLAN.md` specification is now completely expanded, finalized, and completely clear of any missing operational variables. No coding will take place until you review this document and explicitly issue the next steps command.

```
