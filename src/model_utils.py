import os
import joblib
import pandas as pd
import streamlit as st
from config import SCENARIOS


@st.cache_resource
def load_scenario_model(scenario_key: str):
    """Loads the pre-trained model (.pkl) for the specified scenario."""
    config = SCENARIOS.get(scenario_key)
    if not config or not os.path.exists(config["model_path"]):
        return None
    try:
        model = joblib.load(config["model_path"])
        return model
    except Exception as e:
        st.error(f"Error loading model for {scenario_key}: {e}")
        return None


def predict_task_risk(model, input_row_df: pd.DataFrame) -> float:
    """Strictly aligns input features to match the model's trained feature columns (29 features)."""
    if model is None:
        return 0.0
    try:
        # If the model exposes training feature names, reindex the input row precisely to them
        if hasattr(model, "feature_names_in_"):
            expected_features = model.feature_names_in_
            # Reindex ensures missing columns are filled with 0 and extra columns are dropped
            inference_df = input_row_df.reindex(columns=expected_features, fill_value=0)
        else:
            inference_df = input_row_df

        if hasattr(model, "predict_proba"):
            probs = model.predict_proba(inference_df)
            return float(probs[0][1])
        else:
            pred = model.predict(inference_df)
            return float(pred[0])
    except Exception as e:
        st.error(f"Inference execution error: {e}")
        return 0.0