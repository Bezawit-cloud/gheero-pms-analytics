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


def _get_expected_feature_names(model):
    """Finds the trained feature-name list across different estimator APIs.

    Plain scikit-learn estimators set `feature_names_in_` when fit on a
    DataFrame. LightGBM's sklearn wrapper (LGBMClassifier — what this project
    trains, per models/*_metrics.json) manages its own internal Dataset and
    does NOT set `feature_names_in_`; it exposes `feature_name_` instead (and
    the underlying Booster also exposes `.feature_name()`). Checking only
    `feature_names_in_` silently falls through to using the raw, unaligned
    input row (36 columns, including id/calculated_overdue/target_source)
    against a 29-feature model, which raises the "n_features_ mismatch" error.
    """
    if hasattr(model, "feature_names_in_"):
        return list(model.feature_names_in_)
    if hasattr(model, "feature_name_"):
        return list(model.feature_name_)
    if hasattr(model, "booster_"):
        try:
            return list(model.booster_.feature_name())
        except Exception:
            pass
    return None


def predict_task_risk(model, input_row_df: pd.DataFrame) -> float:
    """Strictly aligns input features to match the model's trained feature columns."""
    if model is None:
        return 0.0
    try:
        expected_features = _get_expected_feature_names(model)
        if expected_features:
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
    