"""Paris Wrapped page. PLAN.md S6 / S5.1.

MVP Index computed here in SQL: active/(baseline + epsilon), non-control
brands only (PLAN.md S3.3's Dior-exclusion rule / S5.1).
"""

import streamlit as st

from db import ACTIVE_END, ACTIVE_START, BASELINE_END, BASELINE_START, MVP_EPSILON, query_df

st.set_page_config(page_title="Paris Wrapped", page_icon="\U0001f3a8", layout="wide")
st.title("\U0001f3a8 Paris Wrapped")

mvp_df = query_df(
    """
    WITH active AS (
        SELECT brand_key, MAX(brand_name) AS brand_name, AVG(search_index_score) AS active_mean
        FROM fact_brand_metrics
        WHERE is_control = FALSE AND log_date BETWEEN ? AND ?
        GROUP BY brand_key
    ),
    baseline AS (
        SELECT brand_key, AVG(search_index_score) AS baseline_mean
        FROM fact_brand_metrics
        WHERE is_control = FALSE AND log_date BETWEEN ? AND ?
        GROUP BY brand_key
    )
    SELECT a.brand_name,
           a.active_mean / (COALESCE(b.baseline_mean, 0) + ?) AS mvp_score
    FROM active a
    LEFT JOIN baseline b ON a.brand_key = b.brand_key
    ORDER BY mvp_score DESC
    LIMIT 1
    """,
    (ACTIVE_START, ACTIVE_END, BASELINE_START, BASELINE_END, MVP_EPSILON),
)

busiest_df = query_df(
    """
    SELECT show_date, COUNT(*) AS show_count
    FROM fact_runway_shows
    GROUP BY show_date
    ORDER BY show_count DESC
    LIMIT 1
    """
)

top_venue_df = query_df(
    """
    SELECT venue_name, accessibility_index
    FROM dim_venues
    WHERE accessibility_index IS NOT NULL
    ORDER BY accessibility_index DESC
    LIMIT 1
    """
)

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("#### \U0001f3c6 Fashion Week MVP")
    if mvp_df.empty:
        st.info("Not enough Trends data yet.")
    else:
        st.metric(mvp_df["brand_name"].iloc[0], f"{mvp_df['mvp_score'].iloc[0]:.2f}x lift")

with col2:
    st.markdown("#### \U0001f4c5 Busiest Day")
    if busiest_df.empty:
        st.info("No shows recorded yet.")
    else:
        busiest_date = busiest_df["show_date"].iloc[0].strftime("%Y-%m-%d")
        st.metric(busiest_date, f"{int(busiest_df['show_count'].iloc[0])} shows")

with col3:
    st.markdown("#### \U0001f687 Top Transportation Hub")
    if top_venue_df.empty:
        st.info("No accessibility data yet.")
    else:
        st.metric(
            top_venue_df["venue_name"].iloc[0],
            f"{int(top_venue_df['accessibility_index'].iloc[0])} stations",
        )
