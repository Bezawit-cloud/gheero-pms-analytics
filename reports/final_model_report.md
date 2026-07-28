# Modularized Model Training Pipeline Report (`v1 Clean`)

**Execution Script:** `python -m src.train`  
**Data Directory:** `data/clean/`  
**Artifact Output Directory:** `final_models/`  
**Target Variable:** `calculated_overdue` (47.81% baseline overdue rate — 6,643 overdue tasks)  
**Validation Strategy:** 70% Train / 15% Validation / 15% Test (Stratified Random Split)

---

## 1. Pipeline Architecture & Modular Structure

The model training pipeline is modularized within the `src/` package to support end-to-end retraining, benchmark evaluation, hyperparameter tuning, plot generation, and artifact saving:

```
src/
├── feature_engineering.py  # Checkpoint feature preprocessors & historical helper utilities
├── utils.py                # Dataset loaders (data/clean), stratified splitters, & joblib artifact manager
├── model.py                # 11 candidate model dictionary & hyperparameter tuning factories
├── eval.py                 # Benchmarking, generalization metrics, threshold reporting & PNG plot generator
└── train.py                # End-to-end executable pipeline runner
```

All trained binaries and evaluation plots are exported directly to the root `final_models/` directory:

```
final_models/
├── v1_creation_clean_randomforest.joblib
├── v1_creation_clean_randomforest_eval.png
├── v1_halfway_clean_gradientboosting.joblib
└── v1_halfway_clean_gradientboosting_eval.png
```

---

## 2. Checkpoint 1: Task Creation ($T_0$) Pipeline Results

The Creation Checkpoint evaluates risk at the exact moment a task is created, using 26 static features (planning window, department historical rates, cross-department relationships, and workload indicators).

### 2.1 Candidate Model Benchmark (Validation Set @ Threshold 0.50)

| Rank | Model Name | PR-AUC | ROC-AUC | Precision | Recall | F1-Score | Accuracy |
|---|---|---|---|---|---|---|---|
| 🥇 | **Random Forest** | **0.9143** | **0.9085** | **85.93%** | **76.00%** | **0.8066** | **82.58%** |
| 🥈 | **Gradient Boosting** | 0.9110 | 0.9022 | 84.98% | 76.71% | 0.8063 | 82.39% |
| 🥉 | **LightGBM** | 0.9045 | 0.8955 | 85.17% | 72.09% | 0.7809 | 80.66% |
| 4 | **XGBoost** | 0.9042 | 0.8945 | 85.44% | 72.49% | 0.7844 | 80.95% |
| 5 | **Extra Trees** | 0.8796 | 0.8800 | 81.65% | 75.50% | 0.7846 | 80.18% |
| 6 | **Decision Tree** | 0.8502 | 0.8594 | 80.67% | 75.00% | 0.7773 | 79.46% |
| 7 | **SVM (RBF Kernel)** | 0.8477 | 0.8448 | 77.21% | 71.79% | 0.7440 | 76.39% |
| 8 | **AdaBoost** | 0.8470 | 0.8292 | 76.90% | 69.18% | 0.7283 | 75.34% |
| 9 | **K-Nearest Neighbors** | 0.8410 | 0.8486 | 79.17% | 70.98% | 0.7485 | 77.21% |
| 10 | **Logistic Regression** | 0.7807 | 0.7778 | 71.37% | 66.06% | 0.6861 | 71.11% |
| 11 | **Naive Bayes (Gaussian)** | 0.7178 | 0.7281 | 66.50% | 68.17% | 0.6733 | 68.38% |

### 2.2 Tuned Champion Model Evaluation (Random Forest)
- **Tuned Cross-Validation Best PR-AUC**: `0.9212`
- **Train+Val PR-AUC**: `0.9956`
- **Held-Out Test Set PR-AUC**: **`0.9373`**
- **Generalization Gap**: **`0.0583` (5.83%)**

#### Classification Metrics on Held-Out Test Set (N = 2,085 Tasks):

| Decision Threshold | Precision (Overdue) | Recall (Overdue) | F1-Score | Overall Accuracy |
|---|---|---|---|---|
| **0.50** | **87.0%** | **81.0%** | **0.84** | **85.0%** |
| **0.40 (Recommended)** | **82.0%** | **88.0%** | **0.85** | **85.0%** |

---

## 3. Checkpoint 2: Halfway Execution ($T_{mid}$) Pipeline Results

The Halfway Checkpoint evaluates risk at 50% of the planned task duration, combining static features with 27 dynamic execution signals (revisions, subtask completion rates, comment volume, and update recency).

### 3.1 Candidate Model Benchmark (Validation Set @ Threshold 0.50)

| Rank | Model Name | PR-AUC | ROC-AUC | Precision | Recall | F1-Score | Accuracy |
|---|---|---|---|---|---|---|---|
| 🥇 | **Gradient Boosting** | **0.9470** | **0.9442** | **90.12%** | **82.43%** | **0.8610** | **87.28%** |
| 🥈 | **Random Forest** | 0.9313 | 0.9277 | 87.02% | 78.11% | 0.8233 | 83.97% |
| 🥉 | **XGBoost** | 0.9257 | 0.9199 | 88.88% | 75.40% | 0.8159 | 83.73% |
| 4 | **LightGBM** | 0.9257 | 0.9203 | 88.28% | 75.60% | 0.8145 | 83.54% |
| 5 | **Extra Trees** | 0.8883 | 0.8907 | 82.38% | 76.51% | 0.7933 | 80.95% |
| 6 | **Decision Tree** | 0.8742 | 0.8842 | 83.96% | 76.20% | 0.7989 | 81.67% |
| 7 | **AdaBoost** | 0.8666 | 0.8506 | 81.31% | 68.57% | 0.7440 | 77.45% |
| 8 | **SVM (RBF Kernel)** | 0.8570 | 0.8518 | 77.71% | 73.49% | 0.7554 | 77.26% |
| 9 | **K-Nearest Neighbors** | 0.8519 | 0.8597 | 80.60% | 70.08% | 0.7497 | 77.64% |
| 10 | **Logistic Regression** | 0.7793 | 0.7768 | 69.66% | 67.07% | 0.6834 | 70.30% |
| 11 | **Naive Bayes (Gaussian)** | 0.7121 | 0.7381 | 64.65% | 74.20% | 0.6910 | 68.28% |

### 3.2 Tuned Champion Model Evaluation (Gradient Boosting)
- **Tuned Cross-Validation Best PR-AUC**: `0.9406`
- **Train+Val PR-AUC**: `0.9779`
- **Held-Out Test Set PR-AUC**: **`0.9499`**
- **Generalization Gap**: **`0.0281` (2.81%)**

#### Classification Metrics on Held-Out Test Set (N = 2,085 Tasks):

| Decision Threshold | Precision (Overdue) | Recall (Overdue) | F1-Score | Overall Accuracy |
|---|---|---|---|---|
| **0.50** | **90.0%** | **83.0%** | **0.86** | **87.0%** |
| **0.40 (Recommended)** | **86.0%** | **90.0%** | **0.88** | **88.0%** |

---

## 4. Production Deployment Summary

| Target Checkpoint | Model | Binary Path | Evaluation Plot Path | Decision Threshold | Expected Precision | Expected Recall |
|---|---|---|---|---|---|---|
| **Creation ($T_0$)** | Random Forest | `final_models/v1_creation_clean_randomforest.joblib` | `final_models/v1_creation_clean_randomforest_eval.png` | **`0.40`** | **82.0%** | **88.0%** |
| **Halfway ($T_{mid}$)** | Gradient Boosting | `final_models/v1_halfway_clean_gradientboosting.joblib` | `final_models/v1_halfway_clean_gradientboosting_eval.png` | **`0.40`** | **86.0%** | **90.0%** |
