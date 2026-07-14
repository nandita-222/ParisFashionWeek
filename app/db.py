"""Shared DuckDB connection helper. PLAN.md S6.

All pages query data/processed/pfw_analytics.db directly - no separate API
layer (CLAUDE.md architecture). Also carries the study-window constants
(PLAN.md S2) and MVP formula constants (S5.1) that multiple pages need.

PFW_DB_PATH env var overrides the default DB path - used for pointing the
dev server at a scratch/test database without touching the real project
data. Unset in normal use.
"""

import os
from pathlib import Path

import duckdb
import streamlit as st

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "pfw_analytics.db"
DB_PATH = Path(os.environ["PFW_DB_PATH"]) if os.environ.get("PFW_DB_PATH") else DEFAULT_DB_PATH

BASELINE_START, BASELINE_END = "2026-02-16", "2026-03-01"
ACTIVE_START, ACTIVE_END = "2026-03-02", "2026-03-10"
POST_START, POST_END = "2026-03-11", "2026-03-18"

CONTROL_BRAND_KEY = "dior"
MVP_EPSILON = 1.0


@st.cache_resource
def get_connection() -> duckdb.DuckDBPyConnection:
    if not DB_PATH.exists():
        st.error(
            f"No database found at `{DB_PATH}`. Run the ETL pipeline "
            "(scripts/build_database.py) first."
        )
        st.stop()
    return duckdb.connect(str(DB_PATH), read_only=True)


@st.cache_data(ttl=300)
def query_df(sql: str, params: tuple = ()):
    con = get_connection()
    return con.execute(sql, params).df()
