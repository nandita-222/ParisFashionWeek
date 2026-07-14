"""Home page. PLAN.md S6 - app/Home.py."""

import streamlit as st

from db import ACTIVE_END, ACTIVE_START, BASELINE_END, BASELINE_START, POST_END, POST_START, query_df

st.set_page_config(
    page_title="Paris Fashion Week 2026 - The City Wrapped", page_icon="\U0001f5fc", layout="wide"
)

st.title("Paris Fashion Week 2026 — The City Wrapped")
st.markdown(
    f"**Baseline** {BASELINE_START} → {BASELINE_END}  ·  "
    f"**Active Event** {ACTIVE_START} → {ACTIVE_END}  ·  "
    f"**Post-Event** {POST_START} → {POST_END}"
)
st.divider()

shows_count = query_df("SELECT COUNT(show_id) AS n FROM fact_runway_shows")["n"].iloc[0]
venue_count = query_df(
    "SELECT COUNT(DISTINCT venue_id) AS n FROM fact_runway_shows WHERE venue_id IS NOT NULL"
)["n"].iloc[0]
peak_arr_df = query_df(
    """
    SELECT arrondissement, COUNT(*) AS n
    FROM dim_venues
    WHERE arrondissement IS NOT NULL
    GROUP BY arrondissement
    ORDER BY n DESC
    LIMIT 1
    """
)
peak_arr = str(int(peak_arr_df["arrondissement"].iloc[0])) if not peak_arr_df.empty else "—"

col1, col2, col3 = st.columns(3)
col1.metric("Total Documented Shows", int(shows_count))
col2.metric("Active Runway Hub Venues", int(venue_count))
col3.metric("Peak Fashion Arrondissement", peak_arr)
