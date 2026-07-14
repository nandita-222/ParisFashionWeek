"""Shared helpers for the PFW pipeline.

Brand-name canonicalization (PLAN.md S3.0) and deterministic ID generation
(PLAN.md S4.0). Every script that emits or joins on brand names or primary
keys must go through these functions so all pipeline stages agree.
"""

import csv
import hashlib
import re
import unicodedata
from pathlib import Path

CORPORATE_SUFFIXES = ["S.A.S.", "SA", "LLC"]

DEFAULT_ALIAS_MAP_PATH = Path("data/external/brand_aliases.csv")

_alias_cache: dict[str, dict[str, str]] = {}


def _load_alias_map(path: Path) -> dict[str, str]:
    cache_key = str(path)
    if cache_key in _alias_cache:
        return _alias_cache[cache_key]

    aliases: dict[str, str] = {}
    if path.exists():
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                raw = (row.get("raw_name") or "").strip().lower()
                brand_key = (row.get("brand_key") or "").strip()
                if raw and brand_key:
                    aliases[raw] = brand_key

    _alias_cache[cache_key] = aliases
    return aliases


def strip_corporate_suffixes(name: str) -> str:
    """Remove trailing corporate suffixes (SA, S.A.S., LLC) from a brand name."""
    cleaned = name.strip()
    changed = True
    while changed:
        changed = False
        for suffix in CORPORATE_SUFFIXES:
            pattern = re.compile(rf"\s+{re.escape(suffix)}\.?$", re.IGNORECASE)
            new_cleaned = pattern.sub("", cleaned).strip()
            if new_cleaned != cleaned:
                cleaned = new_cleaned
                changed = True
    return cleaned


def _strip_accents_and_punctuation(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name)
    no_accents = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    no_punct = re.sub(r"[^\w\s]", "", no_accents, flags=re.UNICODE)
    return re.sub(r"\s+", " ", no_punct).strip()


def normalize_brand(raw_name: str, alias_map_path: Path = DEFAULT_ALIAS_MAP_PATH) -> str:
    """PLAN.md S3.0: canonical brand_key used for every cross-pillar join.

    Alias map (data/external/brand_aliases.csv) is checked first; only falls
    back to the algorithmic strip-suffix / strip-accent / lowercase steps if
    no alias entry matches.
    """
    if not raw_name:
        return ""

    aliases = _load_alias_map(alias_map_path)
    lookup = raw_name.strip().lower()
    if lookup in aliases:
        return aliases[lookup]

    stripped = strip_corporate_suffixes(raw_name)
    cleaned = _strip_accents_and_punctuation(stripped)
    return cleaned.lower()


def make_id(*parts: str) -> str:
    """PLAN.md S4.0: deterministic 12-char hex ID from pipe-joined parts."""
    joined = "|".join(parts)
    return hashlib.md5(joined.encode("utf-8")).hexdigest()[:12]


def venue_id(venue_name: str) -> str:
    """venue_id = md5(lower(strip(venue_name)))[:12]"""
    return make_id(venue_name.strip().lower())


def show_id(brand_key: str, show_date: str, show_time: str) -> str:
    """show_id = md5(brand_key + '|' + show_date + '|' + show_time)[:12]"""
    return make_id(brand_key, show_date, show_time)


def metric_id(brand_key: str, log_date: str) -> str:
    """metric_id = md5(brand_key + '|' + log_date)[:12]"""
    return make_id(brand_key, log_date)
