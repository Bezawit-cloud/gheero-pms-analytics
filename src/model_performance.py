import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from data_loader import load_scenario_metrics, load_scenario_artifact
from config import COLOR_PRIMARY, COLOR_DANGER
from ui_components import render_header, render_insight


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

    st.subheader("📌 Model Summary")
    s1, s2, s3, s4 = st.columns(4)
    with s1:
        st.metric("Model", metrics.get("model_name", "—"))
    with s2:
        st.metric("Train Size", f"{metrics.get('n_train', 0):,}")
    with s3:
        st.metric("Test Size", f"{metrics.get('n_test', 0):,}")
    with s4:
        st.metric("# Features", metrics.get("n_features", 0))

    st.markdown("---")

    col1, col2, col3, col4, col5, col6 = st.columns(6)
    with col1:
        st.metric("Accuracy", f"{metrics.get('accuracy', 0.0):.3f}")
    with col2:
        st.metric("Precision", f"{metrics.get('precision', 0.0):.3f}")
    with col3:
        st.metric("Recall", f"{metrics.get('recall', 0.0):.3f}")
    with col4:
        # Saved metrics key is "f1", not "f1_score".
        st.metric("F1-Score", f"{metrics.get('f1', 0.0):.3f}")
    with col5:
        st.metric("ROC-AUC", f"{metrics.get('roc_auc', 0.0):.3f}")
    with col6:
        st.metric("PR-AUC", f"{metrics.get('pr_auc', 0.0):.3f}", "Imbalance-Aware")

    render_insight(
        "With overdue tasks at roughly 20% of the dataset, PR-AUC is the more trustworthy "
        "headline number here — ROC-AUC and accuracy can both look strong even when the model "
        "is mediocre at catching the minority (overdue) class, since the majority class "
        "dominates the score."
    )

    st.markdown("---")
    col_cm, col_roc = st.columns(2)

    with col_cm:
        st.subheader("🧩 Confusion Matrix")
        cm_df = load_scenario_artifact(scenario_key, "confusion_matrix")
        if not cm_df.empty and cm_df.shape == (2, 3):
            # The saved CSV has no header on its first column (row label),
            # so column names are unreliable (pandas/PowerShell auto-name it
            # "H1" or similar). Read by position instead.
            tn = int(cm_df.iloc[0, 1])
            fp = int(cm_df.iloc[0, 2])
            fn = int(cm_df.iloc[1, 1])
            tp = int(cm_df.iloc[1, 2])

            z = [[tn, fp], [fn, tp]]
            fig_cm = go.Figure(
                data=go.Heatmap(
                    z=z,
                    x=["Predicted Not Overdue", "Predicted Overdue"],
                    y=["Actual Not Overdue", "Actual Overdue"],
                    text=z,
                    texttemplate="%{text:,}",
                    textfont={"size": 16},
                    colorscale=[[0, "#eaf2fb"], [1, COLOR_PRIMARY]],
                    showscale=False,
                )
            )
            fig_cm.update_layout(
                title="Test Set Confusion Matrix",
                yaxis=dict(autorange="reversed"),
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig_cm, use_container_width=True)

            sensitivity = tp / (tp + fn) if (tp + fn) else 0.0
            specificity = tn / (tn + fp) if (tn + fp) else 0.0
            render_insight(
                f"The model catches {sensitivity:.0%} of tasks that actually go overdue "
                f"(sensitivity) and correctly clears {specificity:.0%} of tasks that stay on "
                f"track (specificity). The {fn} false negatives are the costlier error for a "
                f"management tool — those are tasks that will run overdue with no flag raised."
            )
        elif not cm_df.empty:
            st.dataframe(cm_df, use_container_width=True, hide_index=True)
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
            fig_roc.add_shape(
                type="line", line=dict(dash="dash", color="#7f7f7f"),
                x0=0, x1=1, y0=0, y1=1,
            )
            fig_roc.update_layout(
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)"
            )
            st.plotly_chart(fig_roc, use_container_width=True)
        else:
            st.info("ROC curve artifact not found.")

    st.markdown("---")
    col_fi, col_sep = st.columns(2)

    with col_fi:
        st.subheader("🔍 Feature Importance")
        fi_df = load_scenario_artifact(scenario_key, "feature_importance")
        if not fi_df.empty:
            fig_fi = px.bar(
                fi_df.head(15),
                x=fi_df.columns[1],
                y=fi_df.columns[0],
                orientation="h",
                title="Top 15 Features by Importance",
            )
            fig_fi.update_layout(
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                yaxis={"autorange": "reversed"},
            )
            st.plotly_chart(fig_fi, use_container_width=True)
        else:
            st.info(
                "No feature importance artifact found for this scenario."
            )

    with col_sep:
        st.subheader("🎯 Predicted Probability Separation")
        pred_df = load_scenario_artifact(scenario_key, "predictions")
        if not pred_df.empty and {"predicted_probability", "actual_overdue"}.issubset(pred_df.columns):
            plot_df = pred_df.copy()
            plot_df["Actual Outcome"] = plot_df["actual_overdue"].map(
                {0: "Not Overdue", 1: "Overdue"}
            )
            fig_sep = px.histogram(
                plot_df,
                x="predicted_probability",
                color="Actual Outcome",
                color_discrete_map={"Not Overdue": COLOR_PRIMARY, "Overdue": COLOR_DANGER},
                barmode="overlay",
                nbins=30,
                opacity=0.65,
                title="Predicted Probability by Actual Outcome (Test Set)",
                labels={"predicted_probability": "Predicted Overdue Probability"},
            )
            fig_sep.add_vline(x=0.5, line_dash="dash", line_color="#333")
            fig_sep.update_layout(
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)"
            )
            st.plotly_chart(fig_sep, use_container_width=True)
            render_insight(
                "The cleaner the separation between the two colored distributions, the more "
                "reliable the probability score is for triaging tasks — not just the binary "
                "flag. Overlap around the 0.5 line marks the genuinely ambiguous cases where a "
                "human review adds the most value."
            )
        else:
            st.info("Test predictions artifact not found for this scenario.")