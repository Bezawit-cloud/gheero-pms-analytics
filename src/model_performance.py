import plotly.express as px
import streamlit as st
from data_loader import load_scenario_metrics, load_scenario_artifact
from ui_components import render_header


def render(scenario_key: str):
    render_header(
        "Model Performance & Evaluation Artifacts",
        "Audit classification metrics, confusion matrices, and ROC curves"
        " directly from training runs.",
    )

    metrics = load_scenario_metrics(scenario_key)
    if not metrics:
        st.warning(
            "No evaluation metrics JSON found for this scenario under"
            " models/."
        )
        return

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(
            "ROC-AUC", f"{metrics.get('roc_auc', 0.0):.3f}", "Evaluation Metric"
        )
    with col2:
        st.metric(
            "Precision",
            f"{metrics.get('precision', 0.0):.3f}",
            "Positive Class",
        )
    with col3:
        st.metric("Recall", f"{metrics.get('recall', 0.0):.3f}", "Sensitivity")
    with col4:
        st.metric(
            "F1-Score",
            f"{metrics.get('f1_score', 0.0):.3f}",
            "Harmonic Mean",
        )

    st.markdown("---")
    col_cm, col_roc = st.columns(2)

    with col_cm:
        st.subheader("🧩 Confusion Matrix")
        cm_df = load_scenario_artifact(scenario_key, "confusion_matrix")
        if not cm_df.empty:
            st.dataframe(cm_df, use_container_width=True)
        else:
            st.info("Confusion matrix artifact not found.")

    with col_roc:
        st.subheader("📈 ROC Curve Analysis")
        roc_df = load_scenario_artifact(scenario_key, "roc_curve")
        if not roc_df.empty and len(roc_df.columns) >= 2:
            fig_roc = px.line(
                roc_df,
                x=roc_df.columns[0],
                y=roc_df.columns[1],
                title="Receiver Operating Characteristic",
            )
            fig_roc.update_layout(
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)"
            )
            st.plotly_chart(fig_roc, use_container_width=True)
        else:
            st.info("ROC curve artifact not found.")