import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import streamlit as st
from model_utils import load_scenario_model, predict_task_risk
from data_loader import load_scenario_artifact
from ui_components import render_header, render_risk_badge


def render(df: pd.DataFrame, scenario_key: str):
    render_header(
        "Task Risk Predictor & Explainability",
        "Run inference and inspect real-time risk factors using saved models and SHAP values.",
    )

    if df.empty:
        st.warning("Dataset not available for prediction lookup.")
        return

    model = load_scenario_model(scenario_key)
    if model is None:
        st.error(f"Pre-trained model for '{scenario_key}' could not be loaded from models/.")
        return

    task_id_col = "task_id" if "task_id" in df.columns else ("id" if "id" in df.columns else df.columns[0])
    selected_task_id = st.selectbox("Select Task Record to Analyze", df[task_id_col].unique())

    task_row = df[df[task_id_col] == selected_task_id]
    if task_row.empty:
        return

    st.markdown("---")
    col1, col2 = st.columns(2)

    actual_overdue = None
    if "calculated_overdue" in task_row.columns:
        actual_overdue = int(task_row["calculated_overdue"].iloc[0])

    with col1:
        st.subheader("📋 Selected Task Summary")
        if actual_overdue is not None:
            st.metric(
                "Actual Outcome (if known)",
                "Overdue" if actual_overdue == 1 else "Not Overdue",
            )
        else:
            st.info("No ground-truth outcome column found for this record.")

        with st.expander("View All Engineered Features", expanded=False):
            st.dataframe(task_row.T, use_container_width=True)

    with col2:
        st.subheader("🎯 Real-Time Prediction Output")

        # Pass the exact row into the inference wrapper which handles alignment safely
        risk_prob = predict_task_risk(model, task_row)
        render_risk_badge(risk_prob)

        if actual_overdue is not None:
            predicted_label = 1 if risk_prob >= 0.5 else 0
            if predicted_label == actual_overdue:
                st.success("✅ Prediction matches the actual outcome.")
            else:
                st.warning("⚠️ Prediction differs from the actual outcome.")

        fig_gauge = go.Figure(
            go.Indicator(
                mode="gauge+number",
                value=risk_prob * 100,
                title={"text": "Overdue Probability Score (%)"},
                gauge={
                    "axis": {"range": [0, 100]},
                    "bar": {"color": "#1f77b4"},
                    "steps": [
                        {"range": [0, 20], "color": "#2ca02c"},
                        {"range": [20, 35], "color": "#ff7f0e"},
                        {"range": [35, 100], "color": "#d62728"},
                    ],
                },
            )
        )
        fig_gauge.update_layout(height=250, margin=dict(t=50, b=10, l=20, r=20))
        st.plotly_chart(fig_gauge, use_container_width=True)

    st.markdown("---")
    st.subheader("🔍 Explainability: SHAP Values & Feature Importance")

    shap_df = load_scenario_artifact(scenario_key, "shap")
    fi_df = load_scenario_artifact(scenario_key, "feature_importance")

    if not shap_df.empty:
        st.caption(
            "The saved SHAP export is a per-test-row matrix with no task_id column, "
            "so it can't be joined back to the specific task selected above. Shown "
            "below is the global ranking by mean |SHAP value| across the test set."
        )
        shap_cols = [c for c in shap_df.columns if c != "base_value"]
        mean_abs_shap = (
            shap_df[shap_cols].abs().mean().sort_values(ascending=False).head(10)
        )
        shap_plot_df = pd.DataFrame(
            {"feature": mean_abs_shap.index, "mean_abs_shap": mean_abs_shap.values}
        )
        fig_shap = px.bar(
            shap_plot_df,
            x="mean_abs_shap",
            y="feature",
            orientation="h",
            title="Top Features by Mean |SHAP Value| (Test Set)",
        )
        fig_shap.update_layout(
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            yaxis={"autorange": "reversed"},
        )
        st.plotly_chart(fig_shap, use_container_width=True)
    elif not fi_df.empty:
        fig_fi = px.bar(
            fi_df.head(10),
            x=fi_df.columns[1],
            y=fi_df.columns[0],
            orientation="h",
            title="Top Feature Importances (fallback — SHAP artifact unavailable)",
        )
        fig_fi.update_layout(
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            yaxis={"autorange": "reversed"},
        )
        st.plotly_chart(fig_fi, use_container_width=True)
    else:
        st.info(
            "No pre-computed SHAP values or feature importance artifact found "
            "for this scenario under models/."
        )
        
        