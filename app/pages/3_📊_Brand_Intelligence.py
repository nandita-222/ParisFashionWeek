"""Brand Intelligence page. PLAN.md S6.

Trends-only line chart (Media pillar is out of scope). Dior excluded from
brand selection by default per PLAN.md S3.3's control-exclusion rule, with
an explicit opt-in checkbox to inspect it.
"""

import plotly.graph_objects as go
import streamlit as st

from colors import MUTED_INK, brand_color
from db import ACTIVE_END, ACTIVE_START, CONTROL_BRAND_KEY, query_df

st.set_page_config(page_title="Brand Intelligence", page_icon="\U0001f4ca", layout="wide")
st.title("\U0001f4ca Brand Intelligence")

brands_df = query_df(
    "SELECT DISTINCT brand_name FROM fact_brand_metrics WHERE is_control = FALSE ORDER BY brand_name"
)
brand_names = brands_df["brand_name"].tolist()

selected = st.multiselect("Brands", brand_names, default=brand_names[: min(3, len(brand_names))])
show_control = st.checkbox("Show Dior (normalization control)", value=False)

names_to_query = list(selected) + (["Dior"] if show_control else [])

if not names_to_query:
    st.info("Select at least one brand.")
else:
    df = query_df(
        f"""
        SELECT brand_key, brand_name, log_date, search_index_score
        FROM fact_brand_metrics
        WHERE brand_name IN ({",".join(["?"] * len(names_to_query))})
        ORDER BY log_date
        """,
        tuple(names_to_query),
    )

    if df.empty:
        st.info("No Trends data for the selected brand(s) yet.")
    else:
        fig = go.Figure()
        for brand_key, group in df.groupby("brand_key"):
            is_control = brand_key == CONTROL_BRAND_KEY
            color = MUTED_INK if is_control else brand_color(brand_key)
            fig.add_trace(
                go.Scatter(
                    x=group["log_date"],
                    y=group["search_index_score"],
                    mode="lines",
                    name=group["brand_name"].iloc[0] + (" (control)" if is_control else ""),
                    line=dict(color=color, width=2, dash="dot" if is_control else "solid"),
                )
            )

        fig.add_vline(x=ACTIVE_START, line_dash="dash", line_color=MUTED_INK)
        fig.add_vline(x=ACTIVE_END, line_dash="dash", line_color=MUTED_INK)
        fig.add_annotation(x=ACTIVE_START, y=1.02, yref="paper", showarrow=False, text="Before | During", font=dict(color=MUTED_INK, size=11))
        fig.add_annotation(x=ACTIVE_END, y=1.02, yref="paper", showarrow=False, text="During | After", font=dict(color=MUTED_INK, size=11))

        fig.update_layout(
            xaxis_title="Date",
            yaxis_title="Search-attention lift (Dior-relative)",
            legend_title="Brand",
            margin=dict(t=40),
        )
        st.plotly_chart(fig, use_container_width=True)
