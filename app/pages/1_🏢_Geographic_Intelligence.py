"""Geographic Intelligence page. PLAN.md S6.

Full-width Folium map (embedded via st.components.v1, per the plan) of
runway venues, colored by accessibility_index on the shared sequential
ramp. Sidebar filters by brand and show day.
"""

import folium
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from colors import sequential_color
from db import query_df

st.set_page_config(page_title="Geographic Intelligence", page_icon="\U0001f3e2", layout="wide")
st.title("\U0001f3e2 Geographic Intelligence")

brands_df = query_df("SELECT DISTINCT brand_name FROM fact_runway_shows ORDER BY brand_name")
days_df = query_df("SELECT DISTINCT show_date FROM fact_runway_shows ORDER BY show_date")
day_options = days_df["show_date"].dt.strftime("%Y-%m-%d").tolist()

with st.sidebar:
    st.header("Filters")
    selected_brands = st.multiselect("Brands", brands_df["brand_name"].tolist())
    selected_days = st.multiselect("Days", day_options)

sql = """
    SELECT DISTINCT v.venue_id, v.venue_name, v.latitude, v.longitude, v.accessibility_index
    FROM fact_runway_shows s
    JOIN dim_venues v ON s.venue_id = v.venue_id
    WHERE v.latitude IS NOT NULL AND v.longitude IS NOT NULL
"""
params: list = []
if selected_brands:
    sql += f" AND s.brand_name IN ({','.join(['?'] * len(selected_brands))})"
    params.extend(selected_brands)
if selected_days:
    sql += f" AND CAST(s.show_date AS VARCHAR) IN ({','.join(['?'] * len(selected_days))})"
    params.extend(selected_days)

venues_df = query_df(sql, tuple(params))

if venues_df.empty:
    st.info(
        "No geocoded venues match the current filters. This is expected "
        "while venue_name is unpublished by the schedule source (see "
        "PLAN.md S3.1) - once venues are geocoded, they'll appear here."
    )
else:
    center = [venues_df["latitude"].mean(), venues_df["longitude"].mean()]
    fmap = folium.Map(location=center, zoom_start=13, tiles="cartodbpositron")

    acc = venues_df["accessibility_index"].fillna(0)
    vmin, vmax = acc.min(), acc.max()
    for _, row in venues_df.iterrows():
        value = row["accessibility_index"] if pd.notna(row["accessibility_index"]) else 0
        color = sequential_color(value, vmin, vmax)
        folium.CircleMarker(
            location=[row["latitude"], row["longitude"]],
            radius=9,
            color=color,
            weight=1,
            fill=True,
            fill_color=color,
            fill_opacity=0.85,
            popup=f"{row['venue_name']} — {int(value)} stations within 500m",
        ).add_to(fmap)

    components.html(fmap._repr_html_(), height=600)
