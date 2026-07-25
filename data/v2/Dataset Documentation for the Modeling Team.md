# ml_feature_table (1-day and 3-day variants) — Dataset Documentation for the Modeling Team

**Prepared by:** [Henok] — Data Preparation
**Purpose:** predict whether an active PMS task will become overdue.
**Grain:** one row per task, at a fixed point in that task's own lifecycle (not "today").

---

## 1. What this dataset is, in one paragraph

Each row represents one task, snapshotted at a fixed point in that task's own lifecycle (not "today"). Two versions of this table were prepared — **`ml_feature_table_1d`** (prediction point = planned_start_date + 1 day) and **`ml_feature_table_3d`** (prediction point = planned_start_date + 3 days) — because the original design used a 7-day offset, but profiling showed most task windows in this data are only around **4 days long**. A 7-day offset was already past the deadline for the majority of tasks by the time of "prediction," which mechanically forced `started_late = True` almost universally and collapsed several features to near-constants (this was the root cause diagnosed in the error analysis of the first model version — see Section 2 below). Every feature in both versions is computed using only information that would have genuinely existed at that task's own prediction point. The target (`target`) is an independently recalculated overdue label, not the database's own `is_overdue` field, because that stored field was found to be wrong 21.2% of the time during data quality review. Rows are excluded if the task had already completed before its own prediction point.

**Row count:** run `SELECT COUNT(*) FROM ml_feature_table_1d` / `_3d` for exact counts — both will differ slightly from each other and from the original 7-day table, since the "already completed by prediction time" exclusion filters a different set of rows at each offset.

---

## 2. Why two versions (1-day and 3-day), not the original 7-day

**Root problem discovered:** most tasks in this dataset have a planned duration around 4 days. The original 7-day-after-start prediction point was chosen assuming `actual_start_date` needed time to populate, but with a 4-day median window, 7 days after start is already past the deadline for most tasks — meaning `started_late` was true almost everywhere regardless of real risk, and the model had little left to learn from (see the original error analysis: ROC-AUC 0.508, essentially chance-level, traced directly to this collapse).

Two shorter offsets were prepared instead, each with a different tradeoff:

- **`ml_feature_table_1d` (+1 day):** captures the very earliest signal — mostly whether the task was picked up promptly at all. Less information has accumulated (fewer sub-tasks/revisions will exist yet), but it gives management the maximum possible lead time to intervene, and avoids the deadline-already-passed problem for nearly all tasks.
- **`ml_feature_table_3d` (+3 days):** closer to (but still safely before) the ~4-day median deadline — `actual_start_date` is more likely to be populated by this point if the task started on time, and a few more days of revisions/sub-task activity can accumulate, at the cost of somewhat less lead time for intervention and a higher chance the window has already closed for the shortest tasks.

**Recommendation for the modeling team:** train and evaluate on both versions separately and compare — don't merge them into one table, since a task's row would have two different "prediction moments" with different feature values, and mixing them would blur what "prediction_date" means for time-based splitting. Whichever offset produces a materially better and more stable ROC-AUC (and doesn't just push the same started_late-collapse problem to a different day count) is the one to report as primary, with the other kept as a documented sensitivity check.

---

## 3. The target column

```sql
CASE
    WHEN status ILIKE '%complet%' AND actual_end_date > end_date THEN true
    WHEN status NOT ILIKE '%complet%' AND end_date < CURRENT_DATE THEN true
    ELSE false
END AS calculated_overdue
```
A task is "overdue" if it was completed after its planned end date, or if it's still incomplete and its planned end date has already passed. **Do not use the database's stored `is_overdue` field as a substitute or sanity check target — it disagreed with this calculated label on 21.2% of tasks (2,950 of 13,895) during data quality review.**

Class balance: ~75% not-overdue / ~25% overdue (moderately imbalanced — recommend `class_weight='balanced'` in whatever model is used, and evaluate with precision/recall/F1/ROC-AUC/PR-AUC, **not accuracy alone**, since a model that just predicts "not overdue" for everything can still score ~75% accuracy while being useless).

---

## 4. Full feature list and what each one means

| Column | What it measures | Cold-start handling |
|---|---|---|
| `task_weight` | Task's assigned importance weight | Median-imputed if missing |
| `planned_task_duration_days` | Planned end minus planned start | None needed (always populated) |
| `is_planned` | Whether the task was scheduled in advance vs. ad-hoc | None needed |
| `is_cross_department` | Whether the task involves another department | None needed — **note: only ~2-5% True across the dataset, expect low importance** |
| `major_activity_weight` | Weight of the parent Major Activity | None needed |
| `pct_of_planned_duration_elapsed` | (prediction_date − planned_start) / planned_duration, capped [0,1] | Zero-day tasks default to 1.0 (fully elapsed) |
| `days_remaining_at_prediction` | Planned end minus prediction date — deadline pressure | None needed |
| `started_late` | Whether the task started after its planned start, **only trusting `actual_start_date` if it occurred on or before the prediction date** | If not yet started by prediction time and planned start has passed, defaults to True |
| `num_subtasks_as_of_prediction` | Count of sub-tasks that existed by the prediction date (filtered by `created_date`) | Defaults to 0 |
| `subtask_completion_pct_as_of_prediction` | % of those sub-tasks with `actual_end_date` on or before the prediction date | **Left as NULL when zero sub-tasks exist — do not fill with 0 or 100, both are misleading. Use `has_subtasks_at_prediction` alongside it.** |
| `has_subtasks_at_prediction` | Boolean flag for the above | — |
| `num_revisions_before_prediction` | Task edit history count, filtered to `history_date <= prediction_date` | Defaults to 0 |
| `position_historical_overdue_rate` | This position's own overdue rate on **other** tasks whose deadline had already passed before this task's prediction date | Falls back to org-wide average; see `position_has_history` |
| `position_has_history` | Whether any prior resolved tasks existed for this position at prediction time | — |
| `employee_active_workload_at_prediction` | Count of other tasks the same position was actively juggling at the prediction moment | No cold-start risk — this is a live snapshot, not a backward average |
| `department_historical_overdue_rate` | Same idea as position rate, but department-level, lifetime window | Falls back to org-wide average; see `department_has_history` |
| `department_recent_overdue_rate_30d` | Same but a rolling 30-day window instead of lifetime — more reactive to current conditions | Falls back three levels: 30-day → lifetime dept rate → org rate |
| `department_has_history` | Whether any prior resolved tasks existed for this department at prediction time | — |

**Every historical/aggregate feature above explicitly excludes the task's own row and any task whose deadline hadn't yet passed by the prediction date** — this is the single most important design principle in the whole table (see Section 6).

---

## 5. Recommended train/test split — please read before touching this

**Use a time-based split, sorted by `prediction_date`. Do not use a random split.**

```python
df_sorted = df.sort_values("prediction_date").reset_index(drop=True)
split_idx = int(len(df_sorted) * 0.8)
train_df, test_df = df_sorted.iloc[:split_idx], df_sorted.iloc[split_idx:]
```

Why: several features (department/position historical rates, workload) reflect organizational conditions at a specific moment. A random split would let the model implicitly learn from conditions that, in real deployment, wouldn't exist yet relative to what it's being asked to predict. Only a time-based split honestly simulates "train on the past, predict the future," which is what this model will actually do once deployed. If you're doing cross-validation for hyperparameter tuning, use `sklearn.model_selection.TimeSeriesSplit`, not plain `KFold` — plain k-fold shuffles rows across time and reintroduces the same problem.

---

## 6. Leakage safeguards already built in — and what NOT to add back

This is the most important section for your team. While reviewing a comparison dataset built by someone else on the same underlying database, we found (and want you to avoid) these specific mistakes:

- **Do not use any "current status" field as a feature** (e.g. a task's live `status`/`approval_status`) — the target is itself partly derived from status, so any status field is dangerously close to leaking the answer directly.
- **Do not compute any historical rate (department, position, employee) without excluding the row itself and filtering to `planned_end_date < prediction_date`.** We found a comparable dataset where department/position "past overdue rate" was computed over the *entire* table with no such filter — meaning it included the task's own outcome and every future task's outcome. Always aggregate only over rows that had *already resolved* before this row's own prediction point.
- **Do not count revisions/comments/challenges over a table's full lifetime.** Always filter by a history/comment timestamp `<= prediction_date`. A "20 revisions" count is meaningless (and leaky) if 18 of those revisions happened after the task was already late.
- **Be cautious with high-cardinality raw ID columns as features** (e.g. a raw encoded position or department ID). A tree-based model can effectively memorize per-ID behavior from the ID alone, silently reintroducing a historical-rate leak even after you've removed the rate feature itself, if the ID has few enough unique values relative to row count. If you add any ID-like feature, sanity-check its feature importance — a suspiciously dominant ID feature is a red flag, not a coincidence.
- **`created_month`/`created_quarter`-style calendar features need care if any target logic references `CURRENT_DATE`.** In this table, the target does not reference `CURRENT_DATE` at all (it's computed relative to each task's own planned end date), so this specific trap doesn't apply here — but if you add any new feature or relabel the target later, re-verify this hasn't changed.

---

## 7. Known data quality context (for interpreting model behavior, not for you to re-fix)

- Task-level `department_id` is 89.3% missing on the source table — this table already resolves that via position-derived department with a fallback, documented in `sql/analytical_dataset.sql`.
- The source database's own `is_overdue` field disagreed with the recalculated target on 21.2% of tasks — already addressed by using the calculated label throughout.
- `tasks_sub_task_history` had a severe volume anomaly (99.7% of 778k history rows came from just 10 sub-tasks — an automation artifact, not real editing) — this table's revision-count logic already avoids that trap by using `tasks_task_history` instead, which doesn't show the same pattern.
- Full profiling detail: `sql/data_quality_checks.sql` and its findings write-up.

---

## 8. How this table is built (for reference/reproducibility)

Source query: `sql/ml_feature_table.sql`, parameterized to produce both `ml_feature_table_1d` and `ml_feature_table_3d` (change the `+ N` offset in the `prediction_date` calculation and re-run under each table name), built on top of `analytical_task_dataset`, itself built by `sql/analytical_dataset.sql`. Both use CTEs to pre-aggregate one-to-many relationships (sub-tasks, revisions) *before* joining, specifically to avoid row duplication — verified via an explicit duplicate-`task_id` check at the end of the build script (should always return 0 for each version).

---

## 9. Suggested first steps for your side

1. Run `src/quality_check.py` (or your own equivalent) before training anything — it checks for duplicates, class balance, feature variance, and cold-start rates, and screens for any correlation with target above 0.9 as a leakage tripwire.
2. Confirm the time-based split is implemented before the first model run — this is easy to get wrong by accident (e.g. `train_test_split(..., shuffle=True)` defaults to random).
3. If you want to iterate on the feature set, keep the exclusion logic (`task_id != other_task_id`, `planned_end_date < prediction_date`) as the non-negotiable template for any new historical feature.

Happy to walk through any of this together before you start training — especially the prediction-point/leakage logic, since that's the part most likely to need explaining live.