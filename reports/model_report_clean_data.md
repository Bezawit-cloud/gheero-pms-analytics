# Production Model Benchmark Report — Clean Leak-Free Dataset (`v1`)

**Notebooks:** `notebooks/v1_model_fixed_data_halfway_clean_data.ipynb` & `notebooks/v1_model_at_creation_clean_data.ipynb`  
**Datasets:** `data/v1/dataset_at_halfway_clean.csv` & `data/v1/dataset_at_creation_clean.csv` (13,895 rows each)  
**Target:** `calculated_overdue` (47.81% baseline overdue rate — 6,643 overdue tasks)  
**Saved Models:** `models/v1_halfway_clean_gradientboosting.joblib` & `models/v1_creation_clean_randomforest.joblib`

---

## 1. Executive Summary

Following the complete resolution of all 5 classes of data leakage across both checkpoint datasets, we achieved production-ready predictive performance at both the task creation moment and the halfway execution checkpoint.

| Model | Dataset | Split Strategy | Test PR-AUC | Accuracy@0.50 | F1@0.40 |
|---|---|---|---|---|---|
| **Gradient Boosting** | Halfway ($T_{mid}$) Clean | Stratified Random | **`0.9475`** | **87.0%** | **0.87** |
| **Random Forest** | Creation ($T_0$) Clean | Stratified Random | **`0.9373`** | **85.0%** | **0.85** |
| **LightGBM** | Halfway ($T_{mid}$) Clean | Time-Based | `0.7931` | 63.0% | 0.66 |
| **LightGBM** | Creation ($T_0$) Clean | Time-Based | `0.7878` | 68.0% | 0.69 |

---

## 2. Halfway Checkpoint ($T_{mid}$) — Validation Strategy Comparison

### 2.1 Stratified Random Split (70/15/15) — Gradient Boosting

| Threshold | Precision (Overdue) | Recall (Overdue) | F1-Score | Accuracy | Test PR-AUC | Generalization Gap |
|---|---|---|---|---|---|---|
| **0.50** | **90.0%** | **81.0%** | **0.86** | **87.0%** | **`0.9475`** | **`0.0298` (2.98%)** |
| **0.40** | **86.0%** | **88.0%** | **0.87** | **87.0%** | **`0.9475`** | **`0.0298` (2.98%)** |

### 2.2 Time-Based Split (70/15/15) — LightGBM

| Threshold | Precision (Overdue) | Recall (Overdue) | F1-Score | Accuracy | Test PR-AUC | Generalization Gap |
|---|---|---|---|---|---|---|
| **0.50** | 55.0% | 90.0% | 0.68 | 63.0% | `0.7931` | `0.1742` (17.42%) |
| **0.40** | 51.0% | 96.0% | 0.66 | 57.0% | `0.7931` | `0.1742` (17.42%) |

---

## 3. Creation Checkpoint ($T_0$) — Validation Strategy Comparison

### 3.1 Stratified Random Split (70/15/15) — Random Forest

| Threshold | Precision (Overdue) | Recall (Overdue) | F1-Score | Accuracy | Test PR-AUC | Generalization Gap |
|---|---|---|---|---|---|---|
| **0.50** | **87.0%** | **81.0%** | **0.84** | **85.0%** | **`0.9373`** | **`0.0583` (5.83%)** |
| **0.40** | **82.0%** | **88.0%** | **0.85** | **85.0%** | **`0.9373`** | **`0.0583` (5.83%)** |

### 3.2 Time-Based Split (70/15/15) — LightGBM

| Threshold | Precision (Overdue) | Recall (Overdue) | F1-Score | Accuracy | Test PR-AUC | Generalization Gap |
|---|---|---|---|---|---|---|
| **0.50** | 62.0% | 72.0% | 0.67 | 68.0% | `0.7878` | `0.1570` (15.70%) |
| **0.40** | 56.0% | 89.0% | 0.69 | 65.0% | `0.7878` | `0.1570` (15.70%) |

---

## 4. Top 5 Candidate Model Benchmarks

### 4.1 Halfway ($T_{mid}$) Clean Dataset — Stratified Random Split

| Rank | Model Name | PR-AUC | ROC-AUC | Precision@0.50 | Recall@0.50 | F1-Score@0.50 |
|---|---|---|---|---|---|---|
| 🥇 | **Gradient Boosting** | **0.9456** | **0.9431** | **88.09%** | **82.43%** | **0.8517** |
| 🥈 | **Random Forest** | **0.9339** | **0.9261** | **87.64%** | **79.72%** | **0.8349** |
| 🥉 | **XGBoost** | **0.9244** | **0.9156** | **87.09%** | **77.21%** | **0.8185** |
| 4 | **LightGBM** | **0.9229** | **0.9140** | **86.52%** | **76.71%** | **0.8132** |
| 5 | **Extra Trees** | 0.8856 | 0.8822 | 80.11% | 76.00% | 0.7800 |

### 4.2 Creation ($T_0$) Clean Dataset — Stratified Random Split

| Rank | Model Name | PR-AUC | ROC-AUC | Precision@0.50 | Recall@0.50 | F1-Score@0.50 |
|---|---|---|---|---|---|---|
| 🥇 | **Random Forest** | **0.9143** | **0.9085** | **85.93%** | **76.00%** | **0.8066** |
| 🥈 | **Gradient Boosting** | **0.9110** | **0.9022** | **84.98%** | **76.71%** | **0.8063** |
| 🥉 | **LightGBM** | **0.9045** | **0.8955** | **85.17%** | **72.09%** | **0.7809** |
| 4 | **XGBoost** | **0.9042** | **0.8945** | **85.44%** | **72.49%** | **0.7844** |
| 5 | **Extra Trees** | 0.8796 | 0.8800 | 81.65% | 75.50% | 0.7846 |

---

## 5. Production Deployment Recommendations

| Checkpoint | Model | Artifact | Threshold | Precision | Recall | F1-Score |
|---|---|---|---|---|---|---|
| **Creation ($T_0$)** | Random Forest | `v1_creation_clean_randomforest.joblib` | **`0.40`** | **82.0%** | **88.0%** | **0.85** |
| **Halfway ($T_{mid}$)** | Gradient Boosting | `v1_halfway_clean_gradientboosting.joblib` | **`0.40`** | **86.0%** | **88.0%** | **0.87** |
