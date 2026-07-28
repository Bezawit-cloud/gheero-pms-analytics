"""Modularized Training Pipeline for PMS Task Overdue Prediction.

Executes end-to-end data loading, feature preprocessing, candidate benchmarking,
hyperparameter tuning, held-out test evaluation, evaluation plot generation, and artifact saving.

Usage:
    conda run -n ml_base python -m src.train
"""

import sys
import os
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils import load_clean_dataset, split_stratified_random, save_model_artifact
from src.feature_engineering import preprocess_clean_creation_features, preprocess_clean_halfway_features
from src.model import get_candidate_models, tune_random_forest, tune_gradient_boosting
from src.eval import (
    evaluate_benchmark_candidates, evaluate_generalization_gap,
    print_threshold_reports, plot_and_save_evaluations
)


def train_creation_pipeline(data_dir='data/clean', output_dir='final_models'):
    """Execute end-to-end training pipeline for Creation Checkpoint (T0)."""
    print("\n=======================================================")
    print("STARTING CREATION-TIME (T0) MODEL TRAINING PIPELINE")
    print("=======================================================")

    raw_df = load_clean_dataset(checkpoint='creation', data_dir=data_dir)
    print(f"Loaded raw creation dataset: {len(raw_df):,} rows × {raw_df.shape[1]} columns")

    clean_df = preprocess_clean_creation_features(raw_df)
    print(f"Preprocessed predictor features: {clean_df.shape[1] - 1} static columns")

    X_train, X_val, X_test, y_train, y_val, y_test = split_stratified_random(clean_df)
    print(f"Split completed — Train: {len(X_train):,} | Val: {len(X_val):,} | Test: {len(X_test):,}")

    print("\nCandidate Models Benchmark (Creation Validation Set):")
    candidate_models = get_candidate_models()
    benchmark_df = evaluate_benchmark_candidates(candidate_models, X_train, y_train, X_val, y_val)
    print(benchmark_df.to_string(index=False))

    print("\nHyperparameter Tuning Random Forest (T0 Champion)...")
    best_rf_model = tune_random_forest(X_train, y_train)

    X_train_val = pd.concat([X_train, X_val])
    y_train_val = pd.concat([y_train, y_val])
    best_rf_model.fit(X_train_val, y_train_val)

    y_train_val_probs = best_rf_model.predict_proba(X_train_val)[:, 1]
    y_test_probs = best_rf_model.predict_proba(X_test)[:, 1]

    evaluate_generalization_gap(y_train_val, y_train_val_probs, y_test, y_test_probs)
    print_threshold_reports(y_test, y_test_probs, thresholds=[0.50, 0.40])

    plot_and_save_evaluations(
        y_test=y_test,
        y_probs=y_test_probs,
        model_name='Creation Random Forest (T0)',
        filename='v1_creation_clean_randomforest_eval.png',
        output_dir=output_dir,
        threshold=0.50
    )

    saved_path = save_model_artifact(
        best_rf_model,
        filename='v1_creation_clean_randomforest.joblib',
        output_dir=output_dir
    )
    print(f"Creation-Time Pipeline Completed! Model saved at: {saved_path}")
    return best_rf_model


def train_halfway_pipeline(data_dir='data/clean', output_dir='final_models'):
    """Execute end-to-end training pipeline for Halfway Checkpoint (Tmid)."""
    print("\n=======================================================")
    print("STARTING HALFWAY EXECUTION (Tmid) MODEL TRAINING PIPELINE")
    print("=======================================================")

    raw_df = load_clean_dataset(checkpoint='halfway', data_dir=data_dir)
    print(f"Loaded raw halfway dataset: {len(raw_df):,} rows × {raw_df.shape[1]} columns")

    clean_df = preprocess_clean_halfway_features(raw_df)
    print(f"Preprocessed predictor features: {clean_df.shape[1] - 1} predictor columns")

    X_train, X_val, X_test, y_train, y_val, y_test = split_stratified_random(clean_df)
    print(f"Split completed — Train: {len(X_train):,} | Val: {len(X_val):,} | Test: {len(X_test):,}")

    print("\nCandidate Models Benchmark (Halfway Validation Set):")
    candidate_models = get_candidate_models()
    benchmark_df = evaluate_benchmark_candidates(candidate_models, X_train, y_train, X_val, y_val)
    print(benchmark_df.to_string(index=False))

    print("\nHyperparameter Tuning Gradient Boosting (Tmid Champion)...")
    best_gb_model = tune_gradient_boosting(X_train, y_train)

    X_train_val = pd.concat([X_train, X_val])
    y_train_val = pd.concat([y_train, y_val])
    best_gb_model.fit(X_train_val, y_train_val)

    y_train_val_probs = best_gb_model.predict_proba(X_train_val)[:, 1]
    y_test_probs = best_gb_model.predict_proba(X_test)[:, 1]

    evaluate_generalization_gap(y_train_val, y_train_val_probs, y_test, y_test_probs)
    print_threshold_reports(y_test, y_test_probs, thresholds=[0.50, 0.40])

    plot_and_save_evaluations(
        y_test=y_test,
        y_probs=y_test_probs,
        model_name='Halfway Gradient Boosting (Tmid)',
        filename='v1_halfway_clean_gradientboosting_eval.png',
        output_dir=output_dir,
        threshold=0.50
    )

    saved_path = save_model_artifact(
        best_gb_model,
        filename='v1_halfway_clean_gradientboosting.joblib',
        output_dir=output_dir
    )
    print(f"Halfway Execution Pipeline Completed! Model saved at: {saved_path}")
    return best_gb_model


if __name__ == '__main__':
    print("=== RUNNING FULL END-TO-END PMS MODEL TRAINING PIPELINE ===")
    train_creation_pipeline()
    train_halfway_pipeline()
    print("\nALL MODEL TRAINING PIPELINES COMPLETED SUCCESSFULLY!")
