"""Public attention indexing pipeline. PLAN.md S3.3.

Reads unique brands from data/raw/schedule_raw.csv, batches them 4-at-a-time
plus the fixed control brand "Dior" (Google's interest_over_time endpoint
caps a single request at 5 terms), and fetches Google Trends daily interest
for PLAN.md's full study window (2026-02-16 to 2026-03-18).

CONFIRMED ENVIRONMENT GAP: PLAN.md S1 pins pandas==2.0.3 for pytrends
compatibility, but this pin has no wheel for Python 3.13 (the only
interpreter available in this environment) and fails to build from source.
Verified instead with a live pytrends==4.9.2 request against pandas==3.0.3
(see PLAN.md S1 for the updated, tested pin) - it worked cleanly, including
pulling real historical Feb-Mar 2026 data, so the compatibility risk PLAN.md
flagged did not materialize at this version pair. Re-verify if pytrends is
ever upgraded.

Every brand score returned in a batch - including Dior's own - is divided
by that date's Dior score (PLAN.md S3.3's normalization rule), so Dior's
own written series is a flat 1.0 by construction across every date. Dior
rows are still written (is_control=True) because later batches' brands
need Dior's per-batch value to normalize against, but PLAN.md S5.1 excludes
is_control rows from the MVP ranking.

MANUAL FALLBACK - data/raw/trends_raw.csv column contract:
    brand_name, brand_key, log_date, search_index_score, is_control
"""

import csv
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

from pytrends.request import TrendReq

from utils import make_id, normalize_brand

INPUT_PATH = Path("data/raw/schedule_raw.csv")
OUTPUT_PATH = Path("data/raw/trends_raw.csv")
CACHE_DIR = Path("data/raw/.trends_cache")

CONTROL_BRAND_NAME = "Dior"
BATCH_SIZE = 4  # + 1 control brand = 5 keywords, Google's per-request cap
TIMEFRAME = "2026-02-16 2026-03-18"
MAX_BACKOFF_ATTEMPTS = 6
INTER_BATCH_SLEEP_SECONDS = 1.0

PARIS_TZ = ZoneInfo("Europe/Paris")
UTC_TZ = ZoneInfo("UTC")

OUTPUT_COLUMNS = ["brand_name", "brand_key", "log_date", "search_index_score", "is_control"]


def load_target_brands(path: Path = INPUT_PATH) -> list[tuple[str, str]]:
    """Unique (brand_name, brand_key) pairs from the schedule, excluding the control brand."""
    control_key = normalize_brand(CONTROL_BRAND_NAME)
    seen: set[str] = set()
    brands: list[tuple[str, str]] = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = row["brand_name"].strip()
            key = (row.get("brand_key") or "").strip() or normalize_brand(name)
            if not name or not key or key == control_key or key in seen:
                continue
            seen.add(key)
            brands.append((name, key))
    return brands


def batch_brands(
    brands: list[tuple[str, str]], batch_size: int = BATCH_SIZE
):
    for i in range(0, len(brands), batch_size):
        yield brands[i : i + batch_size]


def batch_cache_path(batch: list[tuple[str, str]], cache_dir: Path = CACHE_DIR) -> Path:
    batch_key = make_id(*sorted(key for _, key in batch))
    return cache_dir / f"{batch_key}.csv"


def load_cached_batch(path: Path) -> list[dict] | None:
    """Load a cached batch, coercing types back so cached rows are
    indistinguishable from freshly-fetched ones (CSV round-trips everything
    as strings otherwise, e.g. is_control becomes "True" not True)."""
    if not path.exists():
        return None
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        row["search_index_score"] = float(row["search_index_score"])
        row["is_control"] = row["is_control"] == "True"
    return rows


def write_cached_batch(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def fetch_batch_interest(pytrends: TrendReq, kw_list: list[str]):
    """PLAN.md S3.3: exponential backoff (2^n seconds) on timeouts / HTTP 429."""
    attempt = 0
    while True:
        try:
            pytrends.build_payload(kw_list, timeframe=TIMEFRAME, geo="")
            return pytrends.interest_over_time()
        except Exception as exc:
            message = str(exc).lower()
            transient = "429" in message or "timeout" in message or "timed out" in message
            if not transient or attempt >= MAX_BACKOFF_ATTEMPTS:
                raise
            delay = 2**attempt
            print(
                f"WARNING: pytrends request failed ({exc}); backing off "
                f"{delay}s (attempt {attempt + 1}/{MAX_BACKOFF_ATTEMPTS}).",
                file=sys.stderr,
            )
            time.sleep(delay)
            attempt += 1


def normalize_index_date(raw_date) -> str:
    """PLAN.md S2.1: normalize to Europe/Paris before deriving log_date."""
    dt = raw_date.to_pydatetime() if hasattr(raw_date, "to_pydatetime") else raw_date
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC_TZ)
    return dt.astimezone(PARIS_TZ).strftime("%Y-%m-%d")


def process_batch_response(df, batch: list[tuple[str, str]]) -> list[dict]:
    """Divide every brand score in the batch - including Dior's own - by
    that date's Dior score (PLAN.md S3.3)."""
    rows: list[dict] = []
    if df is None or df.empty:
        return rows

    brand_columns = [(CONTROL_BRAND_NAME, normalize_brand(CONTROL_BRAND_NAME), True)] + [
        (name, key, False) for name, key in batch
    ]

    for raw_date, record in df.iterrows():
        control_value = record.get(CONTROL_BRAND_NAME)
        if not control_value:
            print(
                f"WARNING: Dior control value is 0 on {raw_date}; skipping "
                "this date for the batch (undefined ratio).",
                file=sys.stderr,
            )
            continue

        log_date = normalize_index_date(raw_date)
        for brand_name, brand_key, is_control in brand_columns:
            if brand_name not in record:
                continue
            score = record[brand_name] / control_value
            rows.append(
                {
                    "brand_name": brand_name,
                    "brand_key": brand_key,
                    "log_date": log_date,
                    "search_index_score": round(float(score), 6),
                    "is_control": is_control,
                }
            )

    return rows


def fetch_all(brands: list[tuple[str, str]]) -> list[dict]:
    pytrends = TrendReq(hl="en-US", tz=0)
    all_rows: list[dict] = []
    seen_keys: set[tuple[str, str]] = set()

    for batch in batch_brands(brands):
        cache_path = batch_cache_path(batch)
        cached = load_cached_batch(cache_path)
        if cached is not None:
            print(
                f"INFO: using cached batch {cache_path.name} "
                f"({[key for _, key in batch]}).",
                file=sys.stderr,
            )
            batch_rows = cached
        else:
            kw_list = [name for name, _ in batch] + [CONTROL_BRAND_NAME]
            df = fetch_batch_interest(pytrends, kw_list)
            batch_rows = process_batch_response(df, batch)
            write_cached_batch(cache_path, batch_rows)
            time.sleep(INTER_BATCH_SLEEP_SECONDS)

        for row in batch_rows:
            dedup_key = (row["brand_key"], row["log_date"])
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)
            all_rows.append(row)

    return all_rows


def write_trends_csv(rows: list[dict], path: Path = OUTPUT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    brands = load_target_brands()
    if not brands:
        print("WARNING: no target brands found in schedule_raw.csv.", file=sys.stderr)
        write_trends_csv([])
        print(f"Wrote 0 rows to {OUTPUT_PATH}")
        return

    rows = fetch_all(brands)
    write_trends_csv(rows)
    print(
        f"Wrote {len(rows)} rows to {OUTPUT_PATH} "
        f"({len(brands)} brands + Dior control)."
    )


if __name__ == "__main__":
    main()
