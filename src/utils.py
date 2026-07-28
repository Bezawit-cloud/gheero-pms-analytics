"""Utility functions for dataset loading, data splitting, and model artifact management.
"""

import os
import joblib
import pandas as pd
from sklearn.model_selection import train_test_split


def load_clean_dataset(checkpoint='halfway', data_dir='data/clean'):
    """Load clean leak-free dataset for specified checkpoint."""
    if checkpoint.lower() in ['halfway', 'tmid']:
        file_path = os.path.join(data_dir, 'dataset_at_halfway_clean.csv')
    elif checkpoint.lower() in ['creation', 't0']:
        file_path = os.path.join(data_dir, 'dataset_at_creation_clean.csv')
    else:
        raise ValueError(f"Unknown checkpoint: {checkpoint}. Choose 'halfway' or 'creation'.")

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Clean dataset file not found at: {file_path}")

    return pd.read_csv(file_path)


def split_stratified_random(df, target_col='calculated_overdue', test_size=0.30, random_state=42):
    """Perform 70/15/15 Stratified Random Split."""
    X = df.drop(columns=[target_col])
    y = df[target_col]

    X_train, X_temp, y_train, y_temp = train_test_split(
        X, y, test_size=test_size, random_state=random_state, stratify=y
    )
    X_val, X_test, y_val, y_test = train_test_split(
        X_temp, y_temp, test_size=0.50, random_state=random_state, stratify=y_temp
    )

    return X_train, X_val, X_test, y_train, y_val, y_test


def save_model_artifact(model, filename, output_dir='final_models'):
    """Save trained model binary artifact to destination folder."""
    os.makedirs(output_dir, exist_ok=True)
    file_path = os.path.join(output_dir, filename)
    joblib.dump(model, file_path)
    print(f"Saved model artifact to: {file_path}")
    return file_path


def load_model_artifact(filename, input_dir='final_models'):
    """Load model binary artifact from source folder."""
    file_path = os.path.join(input_dir, filename)
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Model artifact not found at: {file_path}")

    model = joblib.load(file_path)
    print(f"Loaded model artifact from: {file_path}")
    return model
