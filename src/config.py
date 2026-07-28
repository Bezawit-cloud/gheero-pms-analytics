import os

# --- BASE PATHS ---
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_CLEAN_DIR = os.path.join(BASE_DIR, "data", "clean")
MODELS_DIR = os.path.join(BASE_DIR, "models")

# --- SCENARIO REGISTRY ---
SCENARIOS = {
    "creation": {
        "display_name": "Model 1: At Task Creation",
        "dataset_path": os.path.join(
            DATA_CLEAN_DIR, "dataset_at_creation_clean.csv"
        ),
        "model_path": os.path.join(MODELS_DIR, "creation_model.pkl"),
        "metrics_path": os.path.join(MODELS_DIR, "creation_metrics.json"),
        "feature_importance_path": os.path.join(
            MODELS_DIR, "creation_feature_importance.csv"
        ),
        "confusion_matrix_path": os.path.join(
            MODELS_DIR, "creation_confusion_matrix.csv"
        ),
        "roc_curve_path": os.path.join(MODELS_DIR, "creation_roc_curve.csv"),
        "shap_path": os.path.join(MODELS_DIR, "creation_shap_values.csv"),
        "predictions_path": os.path.join(
            MODELS_DIR, "creation_test_predictions.csv"
        ),
    },
    "halfway": {
        "display_name": "Model 2: Halfway Through Task",
        "dataset_path": os.path.join(
            DATA_CLEAN_DIR, "dataset_at_halfway_clean.csv"
        ),
        "model_path": os.path.join(MODELS_DIR, "halfway_model.pkl"),
        "metrics_path": os.path.join(MODELS_DIR, "halfway_metrics.json"),
        "feature_importance_path": os.path.join(
            MODELS_DIR, "halfway_feature_importance.csv"
        ),
        "confusion_matrix_path": os.path.join(
            MODELS_DIR, "halfway_confusion_matrix.csv"
        ),
        "roc_curve_path": os.path.join(MODELS_DIR, "halfway_roc_curve.csv"),
        "shap_path": os.path.join(MODELS_DIR, "halfway_shap_values.csv"),
        "predictions_path": os.path.join(
            MODELS_DIR, "halfway_test_predictions.csv"
        ),
    },
}

# --- DESIGN SYSTEM & COLORS ---
COLOR_PRIMARY = "#1f77b4"
COLOR_DANGER = "#d62728"
COLOR_SUCCESS = "#2ca02c"
COLOR_WARNING = "#ff7f0e"
COLOR_NEUTRAL = "#7f7f7f"

# NOTE: keys must match analytics.DEPT_RISK_LABELS exactly — these are the
# reconstructed department risk tiers (binned from dept_past_overdue_rate),
# not a raw "department" column, which doesn't exist in the clean dataset.
RISK_COLORS = {
    "Low Risk (0-10%)": "#2ca02c",
    "Moderate (10-20%)": "#bcbd22",
    "High (20-30%)": "#ff7f0e",
    "Critical (>30%)": "#d62728",
}