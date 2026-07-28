import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import streamlit as st
from analytics import (
    compute_dept_risk_tiers,
    compute_cross_dept_impact,
    compute_subtask_effect,
    compute_revision_spiral,
    compute_retroactive_impact,
    compute_seasonality,
    compute_class_balance,
)
from config import COLOR_PRIMARY, COLOR_DANGER, RISK_COLORS
from ui_components import render_header, render_insight


def render(df: pd.DataFrame, scenario_key: str):
    render_header(
        "Gheero PMS — Executive Risk & Performance Dashboard",
        f"Production-grade predictive oversight auditing task records ({scenario_key.upper()} context).",
    )

    if df.empty:
        st.warning("Dataset is empty or file missing for this scenario.")
        return

    balance = compute_class_balance(df)
    avg_duration = df["planned_duration"].mean() if "planned_duration" in df.columns else None

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Audited Tasks", f"{balance.get('total', 0):,}")
    with col2:
        st.metric("Baseline Overdue Rate", f"{balance.get('overdue_pct', 0):.1f}%")
    with col3:
        st.metric(
            "Class Imbalance",
            f"{balance.get('imbalance_ratio', 0):.1f} : 1",
            "On-time : Overdue",
        )
    with col4:
        st.metric(
            "Avg. Planned Duration",
            f"{avg_duration:.1f} days" if avg_duration is not None else "—",
        )

    st.caption(
        "With overdue tasks at only ~20% of the dataset, accuracy alone is misleading — "
        "precision, recall, and ROC/PR-AUC (shown on the Model Performance page) are the "
        "metrics that actually reflect how well the model catches at-risk tasks."
    )

    st.markdown("---")

    # ---- Department risk tiers ----------------------------------------
    st.subheader("🏢 Department Risk Tier Reconstruction")
    st.caption(
        "The dataset doesn't retain raw department names — only each task's "
        "`dept_past_overdue_rate`. Tiers below reconstruct department risk bands "
        "from that historical rate."
    )
    tier_df = compute_dept_risk_tiers(df)
    if not tier_df.empty:
        col_chart, col_table = st.columns([2, 1])
        with col_chart:
            fig_tier = px.bar(
                tier_df,
                x="Risk_Tier",
                y="Actual_Overdue_Pct",
                color="Risk_Tier",
                color_discrete_map=RISK_COLORS,
                title="Actual Overdue Rate by Reconstructed Department Risk Tier",
                labels={"Actual_Overdue_Pct": "Overdue Rate (%)", "Risk_Tier": "Risk Tier"},
            )
            fig_tier.update_layout(
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", showlegend=False
            )
            st.plotly_chart(fig_tier, use_container_width=True)
        with col_table:
            st.markdown("#### 📋 Tier Summary")
            display_df = tier_df.copy()
            display_df["Actual_Overdue_Pct"] = display_df["Actual_Overdue_Pct"].round(1).astype(str) + "%"
            display_df.columns = ["Risk Tier", "Tasks", "Overdue Rate"]
            st.dataframe(display_df, hide_index=True, use_container_width=True)

        worst = tier_df.iloc[-1]
        best = tier_df.iloc[0]
        render_insight(
            f"Tasks in the '{worst['Risk_Tier']}' tier run overdue "
            f"{worst['Actual_Overdue_Pct']:.1f}% of the time versus "
            f"{best['Actual_Overdue_Pct']:.1f}% in '{best['Risk_Tier']}' — roughly "
            f"{(worst['Actual_Overdue_Pct'] / max(best['Actual_Overdue_Pct'], 0.1)):.1f}x the risk. "
            f"Departments in the Critical/High tiers are the highest-leverage place to focus "
            f"process intervention and staffing review."
        )
    else:
        st.info("dept_past_overdue_rate not available for this scenario.")

    st.markdown("---")

    # ---- Cross-department + subtask effect side by side ----------------
    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("🔗 Cross-Department Coordination Friction")
        cross_df = compute_cross_dept_impact(df)
        if not cross_df.empty:
            fig_cross = px.bar(
                cross_df,
                x="Segment",
                y="Overdue_Rate_Pct",
                color="Segment",
                color_discrete_sequence=[COLOR_PRIMARY, COLOR_DANGER],
                title="Overdue Rate: Single vs Cross-Department Tasks",
                labels={"Overdue_Rate_Pct": "Overdue Rate (%)"},
            )
            fig_cross.update_layout(
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", showlegend=False
            )
            st.plotly_chart(fig_cross, use_container_width=True)

            single_rate = cross_df.loc[cross_df["Segment"] == "Single Department", "Overdue_Rate_Pct"].iloc[0]
            cross_rate = cross_df.loc[cross_df["Segment"] == "Cross-Department", "Overdue_Rate_Pct"].iloc[0]
            lift = cross_rate / single_rate if single_rate else 0
            render_insight(
                f"Cross-department tasks run overdue {cross_rate:.1f}% of the time versus "
                f"{single_rate:.1f}% for single-department tasks — a {lift:.1f}x risk lift. "
                f"Coordination handoffs are a concrete bottleneck worth a dedicated review, "
                f"not just a modeling feature."
            )
        else:
            st.info("is_cross_dept not available for this scenario.")

    with col_b:
        st.subheader("🧩 Subtask Protection Effect")
        subtask_df = compute_subtask_effect(df)
        if not subtask_df.empty:
            fig_sub = px.bar(
                subtask_df,
                x="Segment",
                y="Overdue_Rate_Pct",
                color="Segment",
                color_discrete_sequence=[COLOR_DANGER, COLOR_PRIMARY],
                title="Overdue Rate: With vs Without Subtasks",
                labels={"Overdue_Rate_Pct": "Overdue Rate (%)"},
            )
            fig_sub.update_layout(
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", showlegend=False
            )
            st.plotly_chart(fig_sub, use_container_width=True)

            no_sub = subtask_df.loc[subtask_df["Segment"] == "No Subtasks", "Overdue_Rate_Pct"].iloc[0]
            has_sub = subtask_df.loc[subtask_df["Segment"] == "Has Subtasks", "Overdue_Rate_Pct"].iloc[0]
            render_insight(
                f"Tasks broken into subtasks run overdue {has_sub:.1f}% of the time versus "
                f"{no_sub:.1f}% for monolithic tasks. Decomposition tends to track with more "
                f"upfront planning — encouraging subtask breakdown for large or ambiguous work "
                f"is a low-cost, high-signal process nudge."
            )
        else:
            st.info("has_subtasks not available for this scenario.")

    st.markdown("---")

    # ---- Revision death spiral + retroactive creation -------------------
    col_c, col_d = st.columns(2)

    with col_c:
        st.subheader("🌀 Revision Death Spiral")
        rev_df = compute_revision_spiral(df)
        if not rev_df.empty:
            fig_rev = px.line(
                rev_df,
                x="Revisions",
                y="Overdue_Rate_Pct",
                markers=True,
                title="Overdue Rate by Number of Revisions",
                labels={"Revisions": "Number of Revisions", "Overdue_Rate_Pct": "Overdue Rate (%)"},
            )
            fig_rev.update_traces(line_color=COLOR_DANGER, marker=dict(size=10))
            fig_rev.update_layout(
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)"
            )
            st.plotly_chart(fig_rev, use_container_width=True)

            low = rev_df.iloc[0]["Overdue_Rate_Pct"]
            high = rev_df.iloc[-1]["Overdue_Rate_Pct"]
            render_insight(
                f"Overdue rate climbs from {low:.1f}% at zero revisions to {high:.1f}% at 3+ "
                f"revisions. Repeated revisions are a leading indicator, not a lagging one — "
                f"flagging a task at its 2nd revision gives management a window to intervene "
                f"before it becomes overdue."
            )
        else:
            st.info("num_revisions not available for this scenario.")

    with col_d:
        st.subheader("⏱️ Retroactive Creation Anomaly")
        retro_df = compute_retroactive_impact(df)
        if not retro_df.empty:
            fig_retro = px.bar(
                retro_df,
                x="Segment",
                y="Overdue_Rate_Pct",
                color="Segment",
                color_discrete_sequence=[COLOR_PRIMARY, COLOR_DANGER],
                title="Overdue Rate: Planned Ahead vs Retroactive Logging",
                labels={"Overdue_Rate_Pct": "Overdue Rate (%)"},
            )
            fig_retro.update_layout(
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", showlegend=False
            )
            st.plotly_chart(fig_retro, use_container_width=True)

            retro_row = retro_df[retro_df["Segment"] == "Retroactive Creation"]
            retro_pct_of_tasks = (
                retro_row["Num_Tasks"].iloc[0] / len(df) * 100 if not retro_row.empty else 0
            )
            render_insight(
                f"About {retro_pct_of_tasks:.0f}% of tasks in this dataset are logged in the "
                f"system after their planned start date has already passed. That's a data-entry "
                f"discipline gap as much as a scheduling one — tightening how promptly tasks are "
                f"logged would improve both planning accuracy and this model's input quality."
            )
        else:
            st.info("creation_to_planned_start not available for this scenario.")

    st.markdown("---")

    # ---- Seasonality ------------------------------------------------------
    st.subheader("📅 Seasonal Volume & Overdue Drift")
    monthly_df = compute_seasonality(df)
    if not monthly_df.empty:
        fig_season = go.Figure()
        fig_season.add_trace(
            go.Bar(
                x=monthly_df["created_month"],
                y=monthly_df["Num_Tasks"],
                name="Task Volume",
                marker_color=COLOR_PRIMARY,
                opacity=0.55,
                yaxis="y1",
            )
        )
        fig_season.add_trace(
            go.Scatter(
                x=monthly_df["created_month"],
                y=monthly_df["Overdue_Rate_Pct"],
                name="Overdue Rate (%)",
                marker_color=COLOR_DANGER,
                mode="lines+markers",
                yaxis="y2",
            )
        )
        fig_season.update_layout(
            title="Task Volume vs Overdue Rate by Creation Month",
            xaxis=dict(title="Month", tickmode="linear"),
            yaxis=dict(title="Task Volume", side="left"),
            yaxis2=dict(title="Overdue Rate (%)", overlaying="y", side="right"),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig_season, use_container_width=True)

        peak_month = monthly_df.loc[monthly_df["Overdue_Rate_Pct"].idxmax()]
        render_insight(
            f"Overdue risk is not evenly spread across the year — month "
            f"{int(peak_month['created_month'])} peaks at {peak_month['Overdue_Rate_Pct']:.1f}% "
            f"overdue, well above other months. This kind of seasonal drift is also why a "
            f"stratified k-fold split needs a held-out temporal slice to validate against, "
            f"rather than assuming performance is stable across the year."
        )
    else:
        st.info("created_month not available for this scenario.")