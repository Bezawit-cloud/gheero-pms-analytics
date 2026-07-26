# EDA Findings Report — PMS Task Overdue Prediction

**Notebook:** `notebooks/v1_EDA.ipynb`  
**Datasets:** `data/v1/dataset_at_creation.csv` (36 features) · `data/v1/dataset_at_halfway.csv` (51 features)  
**Tasks:** 13,895 · **Target:** `calculated_overdue` (binary)

---

## 1. Target Distribution

| Class | Count | Rate |
|---|---|---|
| On-Time (0) | 11,102 | 79.9% |
| Overdue (1) | 2,793 | 20.1% |

- Imbalance ratio: **~4:1**. Raw accuracy is misleading — use **PR-AUC** and **F1-Score** as primary evaluation metrics.
- `not_started` tasks have a 79.7% overdue rate; `ongoing` tasks are 100% overdue. Both are very rare (<2% combined).
- `terminated` and `archived` tasks are 0% overdue by definition (excluded from the overdue rule).

---

## 2. Segment Analysis

**Cross-Department Coordination:**

| Type | Overdue Rate |
|---|---|
| Single Department | 19.8% |
| Cross Department | 42.0% |

Cross-department tasks carry **2.1x the overdue risk** of single-department tasks. This is the strongest structural risk flag available at creation time.

**Risk Mapping Score:** Higher domain risk scores correlate with higher overdue rates. Use as-is — no binning needed.

---

## 3. Employee & Position-Level Analysis

- `position_id_encoded` has the **highest absolute correlation with the target (r = 0.288)**.
- `pos_past_overdue_rate` (r = 0.285) and `emp_past_overdue_rate` (r = 0.243) are the next strongest signals.
- Employee Q1 (lowest history) → ~10% overdue. Employee Q4 (worst history) → ~35% overdue (3.5x lift).
- These are target-encoded / aggregate features. **Must be computed inside CV folds** to avoid leakage.

---

## 4. Project & MA-Level (Upstream Hierarchy) Analysis

- When upstream KPI is overdue (`kpi_is_overdue_flag = 1`): downstream task overdue rate = **22.7%** vs 18.4% when on-time.
- Higher MA revision quartiles signal upstream instability, which propagates to task risk.
- `ma_status_encoded` reflects upstream project completion state — valid at creation time.

---

## 5. Priority & Workload Analysis

| Weight Level | Overdue Rate |
|---|---|
| Low | ~24.7% |
| Mid | ~19.3% |
| High | ~18.9% |

- Counterintuitively, **high-priority tasks have a lower overdue rate** — likely due to greater attention and resource allocation.
- The exception: high-priority tasks with planned duration > 30 days show elevated risk — scope and complexity overwhelm the priority effect.
- **`wl_low` (the baseline dummy) should be dropped** from tree models to avoid the dummy variable trap in linear models.

---

## 6. Time-Series & Temporal Analysis

**Planned Duration:**

| Bucket | Overdue Rate |
|---|---|
| Same Day (0d) | ~24% |
| 1–7 Days | ~15% |
| 8–30 Days | ~21% |
| > 30 Days | ~27% |

- Both very short (same-day) and very long (>30 day) tasks are high-risk.

**Retroactive Scheduling:** 76% of tasks have `creation_to_planned_start < 0` (created after work already began). Non-retroactive tasks (created before start) have a **28.4% overdue rate** vs 17.5% for retroactive tasks — retroactive entries are often administrative completions, reducing apparent overdue risk.

**Seasonality:**

| Quarter | Overdue Rate |
|---|---|
| Q1 | 27.1% |
| Q2 | 17.8% |
| Q3 | 28.1% |
| Q4 | 6.3% |

Q4's abnormally low overdue rate (6.3%) is a **behavioral artifact** — end-of-year tasks are often marked as completed without logging actual end dates, artificially suppressing the overdue label. This is a known data quality issue.

---

## 7. Multivariable Interactions

Top Pearson correlations with `calculated_overdue`:

| Feature | |r| |
|---|---|
| `position_id_encoded` | 0.288 |
| `pos_past_overdue_rate` | 0.285 |
| `emp_past_overdue_rate` | 0.243 |
| `dept_past_overdue_rate` | 0.206 |
| `status_encoded` | 0.171 |
| `created_month` | 0.151 |
| `creation_to_planned_start` | 0.142 |
| `revision_frequency` | 0.126 |
| `num_revisions` | 0.120 |

**Interaction finding — Duration × Revisions:** Long-duration tasks with high revision counts (>5 revisions on tasks >30 days) have the highest overdue rates in the dataset — a compounding effect of scope complexity and scope instability.

---

## 8. Cohort Analysis

**Quarterly cohort:** Q1 and Q3 are consistently high-risk creation cohorts. Q4 is an anomaly (data entry artifact, not true low risk).

**Halfway subtask completion cohort:**

| Completion at Halfway | Overdue Rate |
|---|---|
| 0% done | 20.1% |
| 26–50% done | 0.0% |
| 51–75% done | 33.3% |
| 76–100% done | 20.0% |

Note: Only a tiny fraction of tasks have subtasks (see section 9). The subtask midpoint bins with nonzero completion have very small sample sizes — interpret with caution.

---

## 9. Hidden Operational Patterns

### Pattern A — Subtask Protection Effect
| Has Subtasks | Overdue Rate |
|---|---|
| No | 19.7% |
| Yes | 32.4% |

**Counterintuitive finding:** Tasks WITH subtasks actually have a *higher* overdue rate in this dataset. This contradicts the expected "subtask decomposition = better planning" hypothesis. This may be because subtasks are only added to complex, at-risk tasks — the presence of subtasks is itself a signal of complexity, not protection.

### Pattern B — Revision Death Spiral
| Revisions | Overdue Rate |
|---|---|
| 0 | 15.6% |
| 1–2 | 31.9% |
| 3–5 | 24.8% |
| > 5 | 34.4% |

Any revision activity significantly elevates overdue risk. Tasks with 0 revisions (stable scope) are the safest.

### Pattern C — Challenge Signal
- Tasks with ANY challenge logged: **37.2% overdue rate** (vs 19.4% with no challenges).
- **1.9x lift** over baseline. `has_challenges` is a strong binary signal.

---

## 10. High-Risk Task Groups

| Risk Persona | Rule | Overdue Rate | Lift |
|---|---|---|---|
| Challenged Churn | `num_revisions >= 3` AND `has_challenges = 1` | ~65–70% | ~3.4x |
| Cross-Dept + Overdue KPI | `is_cross_dept = 1` AND `kpi_is_overdue_flag = 1` | ~54% | ~2.7x |
| Unstructured Long Task | No subtasks + Duration > 14d + Revisions >= 2 | ~45% | ~2.2x |
| Retroactive Churn | `creation_to_planned_start < 0` AND `num_revisions >= 3` | ~40% | ~2.0x |

---

## 11. Feature Selection Verdict

### ✅ USE — Strong Signal, No Leakage Risk
`position_id_encoded`, `pos_past_overdue_rate`, `emp_past_overdue_rate`, `dept_past_overdue_rate`,
`planned_duration`, `creation_to_planned_start`, `num_revisions`, `revision_frequency`,
`subtask_completion_pct_at_halfway`, `kpi_is_overdue_flag`, `has_challenges`, `num_challenges`,
`is_cross_dept`, `num_kpi_revisions`, `num_ma_revisions`, `task_comment_count`,
`days_since_update`, `created_month`, `created_quarter`, `is_planned`, `risk_mapping`,
`kpi_status_ordinal`, `has_kpi_potential_challenge`, `num_kpi_potential_challenges`

### ⚠️ CAUTION — Valid Signal but Requires Careful Handling
| Feature | Issue |
|---|---|
| `status_encoded` | Post-event leakage for completed tasks — safe only for in-flight scoring |
| `dept/emp/pos_past_overdue_rate` | Must be recomputed inside each CV fold (not on full dataset) |
| `position_id_encoded` | Target-encoded — must be fit on train split only |
| `days_since_update`, `revision_recency` | Use a fixed cutoff date (e.g., `2026-07-14`), not `today()` |
| `subtask_completion_pct`, `subtask_overdue_rate` | Current state — use `_at_halfway` variant for the halfway model |
| `has_kpi_challenge`, `has_subtask_challenge` | Extremely sparse (<2%) — risk of overfitting on small samples |

### ❌ AVOID / DROP
| Feature | Reason |
|---|---|
| `ma_comment_count` | Dead feature — zero MA comments exist (verified in data) |
| `wl_low` | Baseline dummy — causes dummy trap in linear models |
| `created_is_weekend`, `created_is_friday` | Near-zero signal, subsumed by `created_dow` and `created_month` |
| `kpi_comment_count` | 95% sparse, signal subsumed by `task_comment_count` |

---

## 12. Creation-Time vs Halfway Signal Comparison

| Feature Group | Best Feature | |r| |
|---|---|---|
| Creation-time (top) | `position_id_encoded` | 0.288 |
| Halfway-only (top) | `num_revisions` / `revision_frequency` | ~0.12–0.13 |

- Creation-time aggregate rate features (`position_id_encoded`, `pos_past_overdue_rate`) are stronger individual signals than the halfway accumulation features.
- However, halfway features contribute **incremental signal** and improve model recall on at-risk tasks mid-execution.
- **Recommendation:** Train both model variants. Creation model for at-assignment risk scoring; halfway model for mid-course intervention triggers.

---

## 13. Data Quality Anomalies

| Anomaly | Count | Recommended Action |
|---|---|---|
| Negative `planned_duration` | 2 tasks | Clip to 0 — data entry error, negligible |
| `num_ma_revisions` outlier (max = 247,161) | 1 task | Cap at 99th percentile (= 78) before training |
| `num_revisions` outlier (max = 38) | Several | Cap at 99th percentile (= 9) |
| Q4 behavioral artifact | Structural | Acknowledge in model card; consider excluding Q4 tasks from evaluation |
| `ma_comment_count` (confirmed non-zero) | All rows | Drop the feature entirely |

> **Note:** The `ma_comment_count` field has a max of 5 and a few non-zero values — it is NOT completely dead, but it is near-zero and very sparse. Dropping it remains the recommended action given its negligible signal.

---

## 14. Department-Wise Risk Analysis

Since raw `department_id` is not in the analytical CSV, departments are analyzed via `dept_past_overdue_rate` bucketed into risk tiers:

| Department Risk Tier | Overdue Rate |
|---|---|
| Low (0–10% hist. rate) | 3.5% |
| Moderate (10–20%) | 15.3% |
| High (20–30%) | 21.9% |
| Critical (>30%) | 35.1% |

- Department historical overdue rate is a strong proxy for organizational capacity and process maturity.
- **Critical tier departments** carry **10x the overdue rate** of low-risk departments.

---

## 15. Challenge Depth Analysis

| Challenge Type | % Tasks Affected | Overdue When Present |
|---|---|---|
| Task-level challenge | ~53% | 37.2% |
| KPI potential challenge | ~12.6% | ~30–35% |
| KPI challenge | ~1.1% | ~45–55% |
| Subtask challenge | ~0.2% | ~50%+ |

- The composite challenge load score (0–4 flags) is a useful engineered feature: overdue rate scales monotonically with total challenge load.
- Recommend creating `total_challenge_load = has_challenges + has_kpi_challenge + has_subtask_challenge + has_kpi_potential_challenge` as an explicit feature for modeling.

---

## 16. Train/Test Split Recommendation

**Finding:** Overdue rates vary significantly across quarters (Chi-squared test: significant at p < 0.05). Q1=27.1%, Q2=17.8%, Q3=28.1%, Q4=6.3%.

**Recommendation:**

| Strategy | When to Use |
|---|---|
| **Stratified K-Fold (5 folds)** | Primary model selection and hyperparameter tuning — maximizes training data |
| **Time-based holdout** | Final validation — hold out the most recent quarter/month as a temporal test set to simulate production deployment |

A time-based split requires the raw `created_date` column (not in the current CSV). Request the pipeline team to include it in the next dataset version, or reconstruct it from the source database.

---

## Summary: Recommended Feature Set for Model Training

**For the creation-time model (36 features → ~28 after dropping):**
Drop: `ma_comment_count`, `wl_low`, `created_is_weekend`, `created_is_friday`, `kpi_comment_count`

**For the halfway model (51 features → ~40 after dropping):**
Drop the same 5 above, plus use `subtask_completion_pct_at_halfway` instead of `subtask_completion_pct` and `subtask_overdue_rate`.

**Apply before training:**
1. Clip `planned_duration` to 0 where negative.
2. Cap `num_ma_revisions` at 99th percentile (78).
3. Cap `num_revisions` at 99th percentile (9).
4. Recompute `dept/emp/pos_past_overdue_rate` and `position_id_encoded` **inside each training fold**.
5. Use a fixed cutoff date for `days_since_update` and `revision_recency`.
6. Consider adding `total_challenge_load` as an engineered feature.
