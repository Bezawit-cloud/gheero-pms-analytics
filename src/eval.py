"""Evaluation and visualization functions for model benchmarking and performance assessment.
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import (
    average_precision_score, roc_auc_score,
    precision_recall_fscore_support, classification_report,
    confusion_matrix, PrecisionRecallDisplay, RocCurveDisplay
)


def evaluate_predictions(y_true, y_probs, threshold=0.50):
    """Compute performance metrics for prediction probabilities."""
    pr_auc = average_precision_score(y_true, y_probs)
    roc_auc = roc_auc_score(y_true, y_probs)

    y_pred = (y_probs >= threshold).astype(int)
    p, r, f1, _ = precision_recall_fscore_support(y_true, y_pred, average='binary')
    acc = np.mean(y_true == y_pred)

    return {
        'PR-AUC': round(pr_auc, 4),
        'ROC-AUC': round(roc_auc, 4),
        'Precision': round(p, 4),
        'Recall': round(r, 4),
        'F1-Score': round(f1, 4),
        'Accuracy': round(acc, 4),
    }


def evaluate_benchmark_candidates(models_dict, X_train, y_train, X_val, y_val, threshold=0.50):
    """Evaluate candidate models on validation set and return a summary table."""
    benchmark_results = []

    for name, model in models_dict.items():
        model.fit(X_train, y_train)

        if hasattr(model, "predict_proba"):
            probs = model.predict_proba(X_val)[:, 1]
        else:
            probs = model.decision_function(X_val)

        metrics = evaluate_predictions(y_val, probs, threshold=threshold)
        metrics['Model Name'] = name
        benchmark_results.append(metrics)

    df_bm = pd.DataFrame(benchmark_results).sort_values(by='PR-AUC', ascending=False)
    cols = ['Model Name', 'PR-AUC', 'ROC-AUC', 'Precision', 'Recall', 'F1-Score', 'Accuracy']
    return df_bm[cols]


def evaluate_generalization_gap(y_train_val_true, y_train_val_probs, y_test_true, y_test_probs):
    """Compute PR-AUC generalization gap between Train+Val and held-out Test sets."""
    train_val_pr = average_precision_score(y_train_val_true, y_train_val_probs)
    test_pr = average_precision_score(y_test_true, y_test_probs)
    gap = abs(train_val_pr - test_pr)

    print("=== OVERFITTING & GENERALIZATION EVALUATION ===")
    print(f"Train+Val PR-AUC     : {train_val_pr:.4f}")
    print(f"Held-Out Test PR-AUC : {test_pr:.4f}")
    print(f"Generalization Gap   : {gap:.4f} ({gap*100:.2f}%)")

    return {
        'train_val_pr': train_val_pr,
        'test_pr': test_pr,
        'generalization_gap': gap
    }


def print_threshold_reports(y_test_true, y_test_probs, thresholds=[0.50, 0.40]):
    """Print classification reports across decision thresholds."""
    for thresh in thresholds:
        preds = (y_test_probs >= thresh).astype(int)
        print(f"\n=== FINAL TEST SET REPORT (Threshold = {thresh:.2f}) ===")
        print(classification_report(y_test_true, preds, target_names=['On-Time', 'Overdue']))


def plot_and_save_evaluations(y_test, y_probs, model_name, filename, output_dir='final_models', threshold=0.50):
    """Generate and save PR Curve, ROC Curve, and Confusion Matrix plots."""
    os.makedirs(output_dir, exist_ok=True)
    save_path = os.path.join(output_dir, filename)

    fig, axes = plt.subplots(1, 3, figsize=(18, 5))

    PrecisionRecallDisplay.from_predictions(
        y_test, y_probs, name=model_name, ax=axes[0], color='navy'
    )
    axes[0].set_title(f'Precision-Recall Curve — {model_name}', fontweight='bold')
    axes[0].grid(True, linestyle='--', alpha=0.6)

    RocCurveDisplay.from_predictions(
        y_test, y_probs, name=model_name, ax=axes[1], color='navy'
    )
    axes[1].set_title(f'ROC Curve — {model_name}', fontweight='bold')
    axes[1].grid(True, linestyle='--', alpha=0.6)

    preds = (y_probs >= threshold).astype(int)
    cm = confusion_matrix(y_test, preds)
    sns.heatmap(
        cm, annot=True, fmt='d', cmap='Blues', ax=axes[2],
        xticklabels=['On-Time', 'Overdue'], yticklabels=['On-Time', 'Overdue']
    )
    axes[2].set_title(f'Confusion Matrix (Threshold = {threshold:.2f})', fontweight='bold')
    axes[2].set_xlabel('Predicted Label')
    axes[2].set_ylabel('True Label')

    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    plt.close(fig)

    print(f"Saved evaluation plot to: {save_path}")
