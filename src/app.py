import streamlit as st
from config import SCENARIOS
from data_loader import load_scenario_dataset
from ui_components import inject_custom_css
import dashboard
import predictor
import model_performance
import data_quality

st.set_page_config(
    page_title="Gheero PMS — Enterprise Dashboard", page_icon="📊", layout="wide"
)


def main():
    inject_custom_css()

    st.sidebar.title("Gheero PMS Navigation")

    # Scenario Switcher (At Creation vs Halfway)
    selected_scenario_label = st.sidebar.selectbox(
        "Select Lifecycle Scenario",
        [config["display_name"] for config in SCENARIOS.values()],
    )

    # Reverse lookup scenario key from display name
    scenario_key = next(
        (key for key, cfg in SCENARIOS.items() if cfg["display_name"] == selected_scenario_label),
        "creation",
    )

    st.sidebar.caption(f"Active dataset: `{scenario_key}`")
    st.sidebar.markdown("---")

    # Module Navigation Selector
    app_mode = st.sidebar.radio(
        "Choose Module",
        [
            "Executive Dashboard",
            "Task Risk Predictor",
            "Model Performance",
            "Data Quality & Insights",
        ],
    )

    # Load dataset for the active scenario
    df = load_scenario_dataset(scenario_key)

    # Route to selected module view
    if app_mode == "Executive Dashboard":
        dashboard.render(df, scenario_key)
    elif app_mode == "Task Risk Predictor":
        predictor.render(df, scenario_key)
    elif app_mode == "Model Performance":
        model_performance.render(scenario_key)
    elif app_mode == "Data Quality & Insights":
        data_quality.render(df)


if __name__ == "__main__":
    main()