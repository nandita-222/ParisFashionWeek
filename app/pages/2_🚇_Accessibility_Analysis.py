"""Accessibility Analysis page. PLAN.md S6.

SCOPE NOTE ON THE RIGHT COLUMN: PLAN.md's UI spec calls for a "transit
details" preview filterable "by specific metro line variables." The DuckDB
schema (S4) only ever stores the derived per-venue accessibility_index
count, not individual station/line records - storing raw station rows was
never part of the star schema. Rather than invent an unplanned DB table,
this page reads the same cached open-data station file
calculate_metrics.py already downloaded to data/external/ (S3.4) directly,
as a general station directory independent of which venues are in view,
and lets the user filter by real line names parsed out of its res_com
column (e.g. "RER B", "METRO 4").
"""

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from colors import sequential_color
from db import query_df

st.set_page_config(page_title="Accessibility Analysis", page_icon="\U0001f687", layout="wide")
st.title("\U0001f687 Accessibility Analysis")

STATIONS_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "data"
    / "external"
    / "emplacement-des-gares-idf-data-generalisee.csv"
)


@st.cache_data
def load_station_directory(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, sep=";", encoding="utf-8-sig")
    return df[["nom_long", "res_com", "mode"]].rename(
        columns={"nom_long": "station", "res_com": "lines", "mode": "modes"}
    )


col1, col2 = st.columns(2)

with col1:
    st.subheader("Top 10 Most Accessible Venues")
    top10_df = query_df(
        """
        SELECT venue_name, accessibility_index
        FROM dim_venues
        WHERE accessibility_index IS NOT NULL
        ORDER BY accessibility_index DESC
        LIMIT 10
        """
    )
    if top10_df.empty:
        st.info("No accessibility data yet - see PLAN.md S3.1's confirmed source gap.")
    else:
        ordered = top10_df.iloc[::-1]
        vmin, vmax = ordered["accessibility_index"].min(), ordered["accessibility_index"].max()
        bar_colors = [sequential_color(v, vmin, vmax) for v in ordered["accessibility_index"]]
        fig = go.Figure(
            go.Bar(
                x=ordered["accessibility_index"],
                y=ordered["venue_name"],
                orientation="h",
                marker_color=bar_colors,
            )
        )
        fig.update_layout(
            xaxis_title="Stations within 500m",
            yaxis_title=None,
            margin=dict(l=10, r=10, t=10, b=10),
        )
        st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("Transit Station Directory")
    if not STATIONS_PATH.exists():
        st.info("Station dataset not downloaded yet - run scripts/calculate_metrics.py.")
    else:
        stations_df = load_station_directory(STATIONS_PATH)
        all_lines = sorted(
            {
                token.strip()
                for row in stations_df["lines"].dropna()
                for token in str(row).split("/")
                if token.strip()
            }
        )
        selected_lines = st.multiselect("Filter by line", all_lines)
        filtered = stations_df
        if selected_lines:
            selected_set = set(selected_lines)

            def _matches_selected_line(lines_field) -> bool:
                tokens = {t.strip() for t in str(lines_field).split("/")}
                return bool(tokens & selected_set)

            filtered = stations_df[stations_df["lines"].apply(_matches_selected_line)]
        st.dataframe(filtered, use_container_width=True, hide_index=True)
