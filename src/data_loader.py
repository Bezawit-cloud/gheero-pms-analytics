import json
import os
import pandas as pd
import streamlit as st
from config import SCENARIOS


@st.cache_data
def load_scenario_dataset(scenario_key: str) -> pd.DataFrame:
    """Loads the clean CSV dataset for the specified scenario."""
    config = SCENARIOS.get(scenario_key)
    if not config or not os.path.exists(config["dataset_path"]):
        return pd.DataFrame()  # Returns empty dataframe if path missing
    return pd.read_csv(config["dataset_path"])


@st.cache_data
def load_scenario_metrics(scenario_key: str) -> dict:
    """Loads pre-computed evaluation metrics JSON."""
    config = SCENARIOS.get(scenario_key)
    if not config or not os.path.exists(config["metrics_path"]):
        return {}
    with open(config["metrics_path"], "r") as f:
        return json.load(f)


@st.cache_data
def load_scenario_artifact(scenario_key: str, artifact_type: str) -> pd.DataFrame:
    """Loads pre-computed CSV artifacts (feature importance, confusion matrix, ROC curve, SHAP values, predictions)."""
    config = SCENARIOS.get(scenario_key)
    if not config:
        return pd.DataFrame()

    path_map = {
        "feature_importance": config["feature_importance_path"],
        "confusion_matrix": config["confusion_matrix_path"],
        "roc_curve": config["roc_curve_path"],
        "shap": config["shap_path"],
        "predictions": config["predictions_path"],
    }

    target_path = path_map.get(artifact_type)
    if target_path and os.path.exists(target_path):
        return pd.read_csv(target_path)
    return pd.DataFrame()