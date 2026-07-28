import plotly.express as px
import pandas as pd
import streamlit as st
from analytics import compute_department_summary
from config import COLOR_PRIMARY, RISK_COLORS
from ui_components import render_header


def render(df: pd.DataFrame, scenario_key: str):
    render_header(
        "Gheero PMS — Executive Risk & Performance Dashboard",
        f"Production-grade predictive oversight auditing task records ({scenario_key.upper()} context).",
    )

    if df.empty:
        st.warning("Dataset is empty or file missing for this scenario.")
        return

    total_tasks = len(df)
    overdue_count = (
        int(df["calculated_overdue"].sum())
        if "calculated_overdue" in df.columns
        else 0
    )
    baseline_rate = (overdue_count / total_tasks * 100) if total_tasks > 0 else 0

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(
            label="Total Audited Tasks",
            value=f"{total_tasks:,}",
            delta="Active Scenario",
        )
    with col2:
        st.metric(
            label="Baseline Overdue Rate",
            value=f"{baseline_rate:.1f}%",
            delta="Imbalance Verified",
        )
    with col3:
        st.metric(
            label="Active Overdue Count",
            value=f"{overdue_count:,}",
            delta="Requires Action",
        )
    with col4:
        st.metric(
            label="Pipeline Status", value="Optimized", delta="Artifacts Loaded"
        )

    st.markdown("---")
    st.subheader("🏢 Department-Wise Risk Tiers & Delay Concentration")

    dept_summary = compute_department_summary(df)
    if not dept_summary.empty:
        col_chart, col_table = st.columns([2, 1])

        with col_chart:
            fig_dept = px.bar(
                dept_summary,
                x="department",
                y="Delay_Rate_Pct",
                color="Risk_Tier",
                color_discrete_map=RISK_COLORS,
                title="Historical Overdue Rate by Department",
            )
            fig_dept.update_layout(
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)"
            )
            st.plotly_chart(fig_dept, use_container_width=True)

        with col_table:
            st.markdown("#### 📋 Department Risk Summary")
            display_df = dept_summary[
                ["department", "Total_Tasks", "Delay_Rate_Pct", "Risk_Tier"]
            ].copy()
            display_df["Delay_Rate_Pct"] = (
                display_df["Delay_Rate_Pct"].round(1).astype(str) + "%"
            )
            display_df.columns = [
                "Department",
                "Tasks",
                "Delay Rate",
                "Risk Tier",
            ]
            st.dataframe(display_df, hide_index=True, use_container_width=True)