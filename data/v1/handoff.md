# Feature Pipeline Report — PMS Task Overdue Prediction

## Scope

This report documents the data preparation phase: how each feature is created, how missing values are handled, null rates, imputation rationale, and modeling relevance.

Two analysis-ready datasets are produced:

| Variant | File | Rows | Cols | Purpose |
|---|---|---|---|---|
| Creation-time | `data/v1/dataset_at_creation.csv` | 13,895 | 36 | Features known at task assignment |
| Halfway | `data/v1/dataset_at_halfway.csv` | 13,895 | 51 | Creation + 15 accumulation features (available at midpoint) |

Both share the same 13,895 tasks and the same target `calculated_overdue` (20.1% overdue rate).

## Data Sources (15 Tables)

### Core Tables

| # | Table | Rows (approx.) | Role |
|---|---|---|---|
| 1 | `tasks_task` | 13,895 | Primary table — one row per task. Status, dates, assignments, risk, weight. |
| 2 | `basedata_position` | 91 | Position/role definitions. Maps position → department, position → user (assignee). |
| 3 | `tasks_major_activity` | ~500 | Parent activity for task roll-up. MA status, approval status, KPI linkage. |
| 4 | `tasks_kpi` | ~200 | Key Performance Indicators. Overdue flag and status. |

### History Tables

| # | Table | Rows (approx.) | Role |
|---|---|---|---|
| 5 | `tasks_task_history` | ~120,000 | Revision log per task. Used for revision count, frequency, recency. |
| 6 | `tasks_sub_task_history` | 778,348 | Change log per subtask. Halfway completion & status churn. |
| 7 | `tasks_major_activity_history` | ~40,000 | Revision log per MA. Used for MA revision count. |
| 8 | `tasks_kpi_history` | ~7,000 | Revision log per KPI. Used for KPI revision count. |

### Junction / Detail Tables

| # | Table | Rows (approx.) | Role |
|---|---|---|---|
| 9 | `tasks_sub_task` | ~4,200 | Subtask-level data. Count, completion %, overdue %. |
| 10 | `tasks_task_challenge_groups` | ~7,400 | Challenges/roadblocks per task. |
| 11 | `tasks_cross_department_assignments` | ~200 | Cross-department assignment pairs. |
| 12 | `tasks_sub_task_challenge_groups` | ~40 | Challenges at subtask level. |
| 13 | `tasks_kpis_challegne_groups` | ~200 | Challenges at KPI level. |
| 14 | `tasks_kpis_potential_challenge_groups` | ~2,500 | Potential/planned KPI challenges. |
| 15 | `comments_comment` | ~95,000 | Polymorphic comments (content_type_id: 22=KPI, 23=MA, 24=Task). |

## Entity-Relationship Overview

```
basedata_position
    |
    +---> tasks_task ---> tasks_task_history
    |         |
    |         +---> tasks_sub_task ---> tasks_sub_task_history
    |         |         |
    |         |         +---> tasks_sub_task_challenge_groups
    |         |
    |         +---> tasks_task_challenge_groups
    |         |
    |         +---> tasks_cross_department_assignments
    |         |
    |         +---> tasks_major_activity ---> tasks_major_activity_history
    |                       |
    |                       +---> tasks_kpi ---> tasks_kpi_history
    |                                 |
    |                                 +---> tasks_kpis_challegne_groups
    |                                 +---> tasks_kpis_potential_challenge_groups
    |
comments_comment ---> (polymorphic FK via object_id + content_type_id)
```

## Join Strategy

### Key Resolution Cascades

**Department resolution** (2-level):
```
COALESCE(basedata_position.department_id, tasks_task.department_id) AS resolved_dept_id
```

**KPI resolution** (2-hop chain):
```
tasks_task.major_activity_id
    → tasks_major_activity.id
        → tasks_major_activity.kpi_id
            → tasks_kpi.id
```

### Join Types

| Source | FK | Target | Type |
|---|---|---|---|
| `tasks_task` | `position_id` | `basedata_position.id` | LEFT |
| `tasks_task` | `major_activity_id` | `tasks_major_activity.id` | LEFT |
| `tasks_task` | `department_id` | `basedata_department.id` | LEFT (fallback) |
| `tasks_task` | `derived_from_cross_department_assignment_id` | `tasks_cross_department_assignments.id` | LEFT |
| `tasks_major_activity` | `kpi_id` | `tasks_kpi.id` | LEFT |
| `tasks_task_history` | `history_relation_id` | `tasks_task.id` | LEFT (aggregated) |
| `tasks_sub_task` | `task_id` | `tasks_task.id` | LEFT (aggregated) |
| `tasks_task_challenge_groups` | `task_id` | `tasks_task.id` | LEFT (aggregated) |
| `comments_comment` | `object_id` + `content_type_id` | polymorphic | LEFT (aggregated) |

All joins are LEFT JOIN from `tasks_task` (preserving all 13,895 tasks). All 1:N relationships are aggregated via GROUP BY before merging.

## Implemented Pipeline

Pipeline source: [`src/v1/build_features.py`](../src/v1/build_features.py)  
Reusable feature functions: [`src/v1/feature_engineering.py`](../src/v1/feature_engineering.py)  
ETL SQL: [`sql/v1/analytical_dataset.sql`](../sql/v1/analytical_dataset.sql)  
Data quality SQL: [`sql/v1/data_quality_checks.sql`](../sql/v1/data_quality_checks.sql)  
Relationship docs: [`docs/handoff_H2.md`](../docs/handoff_H2.md)  
Data quality docs: [`docs/handoff_H5.md`](../docs/handoff_H5.md)  
Schema docs: [`docs/handoff_H1.md`](../docs/handoff_H1.md)

Build flow:

1. Load 13,895 base task rows from `tasks_task`.
2. Compute target (`calculated_overdue`) and temporal derivations.
3. Merge history aggregates: task revisions, subtasks, halfway subtask completion, MA info/revisions, KPI features/revisions, challenges (task/KPI/subtask/potential), comments, cross-department flags, department/employee/position aggregates.
4. Impute missing values (fill-0, fill-mean, fill-1, UNKNOWN category).
5. Encode categorical fields (ordinal encode statuses, one-hot weight_level, target-encode position_id).
6. Export two CSV variants (creation 34 feats, halfway 49 feats).

## Target Definition

`calculated_overdue` uses a three-tier approach to handle the missing `actual_end_date` problem:

- **Tier 1** — `actual_end_date` exists: `actual_end_date > end_date` → overdue
- **Tier 2** — no `actual_end_date`, but `tasks_task_history` has a `status='completed'` snapshot: use the **first** occurrence as the inferred completion date and compare to `end_date`
- **Tier 3** — no `actual_end_date`, no history signal: use `updated_date` as the best available proxy
- Open tasks (not `completed`, `terminated`, or `archived`) whose `end_date < '2026-07-14'` → overdue

**Why three tiers:** ~5,658 completed tasks (43%) have NULL `actual_end_date`. The v1 default of "not overdue" for these likely undercounts true overdue rate. Only 231 of the 5,658 have a `status='completed'` trace in the history table; the remaining 5,427 have zero history rows (bulk-loaded directly to the database). For those, `updated_date` is the best available proxy.

**Confidence tracking (`target_source`):** Each row includes a `target_source` column
indicating how its label was determined:

| target_source | Method | Count | Confidence |
|---|---|---|---|
| `actual_end_date` | Tier 1 — direct comparison | ~7,444 | High |
| `history_completion` | Tier 2 — first status='completed' from history | 231 | High |
| `updated_date` | Tier 3 — updated_date as proxy | ~5,427 | Low (approximate) |
| `open_task` | Open task past fixed cutoff | ~164 | High |
| `status_based` | Archived, terminated, or within deadline | remainder | High |

This allows modeling teams to filter or weight rows by label confidence.

**Cutoff date:** All date comparisons use `'2026-07-14'` (fixed) instead of `CURRENT_DATE`/`today()` to ensure reproducible labels. The old approach drifted day-to-day as more tasks crossed their deadline.

**Target distribution:**

| Class | Count | % |
|---|---|---|
| Not Overdue (0) | 11,102 | 79.9% |
| Overdue (1) | 2,793 | 20.1% |

**Status vs overdue rate:**

| Status | Count | % of All | Overdue Rate |
|---|---|---|---|
| not_started | 133 | 1.0% | 79.7% |
| ongoing | 31 | 0.2% | 100.0% |
| completed | 13,102 | 94.3% | 20.3% |
| terminated | 270 | 1.9% | 0.0% |
| archived | 359 | 2.6% | 0.0% |

## Feature Inventory — All 49 Features

### 1. Status & Approval Encodings (5 features)

All use `ordinal_encode_status(fallback=1)` — any null/unseen value maps to 1 (ongoing/in_review), a neutral middle-ground that avoids biasing toward 0 (not_started) or 2+ (completed).

| Feature | Construction | Imputation | Null % Before | After | Modeling Effect |
|---|---|---|---|---|---|
| `status_encoded` | Ordinal: not_started=0, ongoing/in_progress=1, completed=2, terminated=3, archived=4 | Fallback to 1 | 0% | 0 | Strong — lifecycle status directly relates to overdue risk |
| `approval_status_encoded` | Ordinal: pending=0, in_review=1, approved=2, rejected=3 | Fallback to 1 | 0% | 0 | Proxy for workflow progress and review friction |
| `lead_approval_status_encoded` | Same ordinal on `lead_approval_status` | Fallback to 1 | 0% | 0 | Second approval-stage signal |
| `ma_status_encoded` | Ordinal: not_started=0, ongoing=1, completed=2, terminated=3 | Fallback to 1 | 0% | 0 | Captures upstream MA progress |
| `ma_approval_status_encoded` | Same ordinal as approval on MA approval | Fallback to 1 | 0% | 0 | MA-level approval context |

### 2. Temporal Features (8 features)

| Feature | Construction | Imputation | Null % Before | After | Modeling Effect |
|---|---|---|---|---|---|
| `planned_duration` | `end_date - start_date` in days | None needed | 0% | 0 | Longer = more complex work. **Edge case:** 2 tasks have negative duration (end < start), 1,421 have zero (same-day tasks) |
| `creation_to_planned_start` | `start_date - created_date` in days | None needed | 0% | 0 | **76% negative** — retroactive scheduling (tasks created after work began), expected behavior |
| `days_since_update` | `today - updated_date` in days | None needed (always present) | 0% | 0 | Only in halfway dataset. Stale tasks correlate with overdue. Range: 10–457 days |
| `created_dow` | `EXTRACT(DOW FROM created_date)` | None needed | 0% | 0 | Weekly operating patterns |
| `created_is_weekend` | 1 if DOW >= 5 | None needed | 0% | 0 | Weak timing signal |
| `created_is_friday` | 1 if DOW == 4 | None needed | 0% | 0 | End-of-week batching effects |
| `created_month` | `EXTRACT(MONTH FROM created_date)` | None needed | 0% | 0 | Seasonality |
| `created_quarter` | `EXTRACT(QUARTER FROM created_date)` | None needed | 0% | 0 | Coarse seasonality |

### 3. Planning Features (5 features)

| Feature | Construction | Imputation | Null % Before | After | Modeling Effect |
|---|---|---|---|---|---|
| `is_planned` | Cast from `tasks_task.is_planned` to int | None needed | 0% | 0 | Distinguishes formal from ad-hoc work |
| `risk_mapping` | Direct from `tasks_task.risk_mapping` | None needed | 0% | 0 | Domain risk signal (0–10 scale) |
| `wl_high`, `wl_mid`, `wl_low` | One-hot of `tasks_task.weight_level` | Missing categories stay 0 | 0% | 0 | Priority differentiation. All 3 dummies present in data |

### 4. Revision Features (3 features) — Halfway only

| Feature | Construction | Imputation | Null % Before | After | Modeling Effect |
|---|---|---|---|---|---|
| `num_revisions` | COUNT of history rows per task | Fill 0 | ~8% | 0 | Churn/instability indicator |
| `revision_frequency` | `num_revisions / task_age_days` | Fill 0 | ~8% | 0 | Normalized revision rate |
| `revision_recency` | `today - MAX(history_date)` | Fill 0 | ~8% | 0 | How recently the task was changed |

**Leakage risk:** These must be computed using only history up to the prediction cutoff.

### 5. Subtask Features (5 features) — Halfway only

| Feature | Construction | Imputation | Null % Before | After | Modeling Effect |
|---|---|---|---|---|---|
| `num_subtasks` | COUNT of subtask rows per task | Fill 0 | ~92% | 0 | Work decomposition count |
| `has_subtasks` | 1 if num_subtasks > 0 | Fill 0 | ~92% | 0 | Sparse branch feature |
| `subtask_completion_pct` | `completed / total subtasks` | Fill 0 | ~92% | 0 | Strong progress signal |
| `subtask_overdue_rate` | `overdue / total subtasks` | Fill 0 | ~92% | 0 | Direct risk measure |
| `subtask_completion_pct_at_halfway` | Completion at `start + duration/2` from history | Fill 0 | ~92% | 0 | Midpoint progress — the most cutoff-aware halfway feature |

Tasks with subtasks have 11% overdue rate vs 24% without — subtask presence itself is protective.

### 6. Challenge Features (8 features)

| Feature | Construction | Imputation | Null % Before | After | Modeling Effect |
|---|---|---|---|---|---|
| `has_challenges` | Task challenge group exists | Fill 0 | ~47% | 0 | Operational blockers |
| `num_challenges` | COUNT of challenge groups | Fill 0 | ~47% | 0 | Blocker intensity |
| `has_subtask_challenge` | Subtask challenge exists | Fill 0 | ~99.8% | 0 | Very sparse (~0.2% present) |
| `num_subtask_challenges` | COUNT of subtask challenges | Fill 0 | ~99.8% | 0 | Same, richer |
| `has_kpi_challenge` | KPI challenge exists | Fill 0 | ~98.9% | 0 | Sparse |
| `num_kpi_challenges` | COUNT of KPI challenges | Fill 0 | ~98.9% | 0 | Same |
| `has_kpi_potential_challenge` | Potential KPI challenge exists | Fill 0 | ~87.4% | 0 | ~12.6% present |
| `num_kpi_potential_challenges` | COUNT of potential challenges | Fill 0 | ~87.4% | 0 | Same |

When present, these carry strong signal (overdue rate jumps to 30–55%). All retained as sparse high-precision features.

### 7. Cross-Department Features (2 features)

| Feature | Construction | Imputation | Null % Before | After | Modeling Effect |
|---|---|---|---|---|---|
| `is_cross_dept` | Derived from `derived_from_cross_department_assignment_id` | Fill 0 | ~1.4% | 0 | Cross-dept tasks: 27% overdue vs 19% same-dept |
| `cross_dept_pair_exists` | JOIN success with `tasks_cross_department_assignments` | Fill 0 | ~98.6% | 0 | Very sparse but informative |

### 8. MA Revision Feature (1 feature)

| Feature | Construction | Imputation | Null % Before | After | Modeling Effect |
|---|---|---|---|---|---|
| `num_ma_revisions` | COUNT of MA history rows | Fill 0 | ~3% | 0 | Higher-level process churn. **Outlier:** 1 task has 247K revisions (data entry error, retained) |

### 9. KPI Features (3 features)

| Feature | Construction | Imputation | Null % Before | After | Modeling Effect |
|---|---|---|---|---|---|
| `kpi_is_overdue_flag` | `tasks_kpi.is_overdue` as int | Fill 0 | ~5% | 0 | KPI upstream overdue flag |
| `kpi_status_ordinal` | Ordinal: not_started=0, ongoing=1, completed=2, terminated=3, archived=4 | Fill 1 | ~5% | 0 | Neutral "ongoing" default |
| `num_kpi_revisions` | COUNT of KPI history rows | Fill 0 | ~5% | 0 | KPI churn indicator |

### 10. Comment Features (3 features)

| Feature | Construction | Imputation | Null % Before | After | Modeling Effect |
|---|---|---|---|---|---|
| `kpi_comment_count` | Comments WHERE content_type_id=22 | Fill 0 | ~95% | 0 | Discussion volume proxy |
| `ma_comment_count` | Comments WHERE content_type_id=23 | Fill 0 | 100% | 0 | **Dead feature** — zero MA comments exist |
| `task_comment_count` | Comments WHERE content_type_id=24 | Fill 0 | ~90% | 0 | Coordination/ambiguity signal |

`ma_comment_count` could be dropped if confirmed zero in future data refreshes.

### 11. Sub-Task History Feature (1 feature) — Halfway only

| Feature | Construction | Imputation | Null % Before | After | Modeling Effect |
|---|---|---|---|---|---|
| `avg_sub_status_changes` | Mean distinct statuses per subtask, grouped to task | Fill 0 | ~98.4% | 0 | Subtask state oscillation → rework indicator |

### 12. Aggregate Rate Features (4 features)

| Feature | Construction | Imputation | Null % Before | After | Modeling Effect |
|---|---|---|---|---|---|
| `dept_past_overdue_rate` | Dept-level mean of `calculated_overdue` | Fill global mean (~0.20) | ~2.7% | 0 | Department historical tendency |
| `dept_avg_revisions` | Dept-level mean revision count | Fill global mean | ~2.7% | 0 | Department process maturity |
| `emp_past_overdue_rate` | Employee-level mean of `calculated_overdue` | Fill global mean (~0.20) | ~7.7% | 0 | Employee historical tendency |
| `pos_past_overdue_rate` | Position-level mean of `calculated_overdue` | Fill global mean (~0.20) | ~4.8% | 0 | Role-specific workload patterns |

**Leakage risk:** These use full-history averages. In production, they must be recomputed within each training fold.

### 13. Position Target Encoding (1 feature)

| Feature | Construction | Imputation | Null % Before | After | Modeling Effect |
|---|---|---|---|---|---|
| `position_id_encoded` | Target-encode position_id → mean overdue per position | UNKNOWN → global mean (~0.20) | ~4.8% | 0 | High-cardinality categorical → dense float |

**Leakage risk:** Must be fit only within training folds, not on the full dataset.

## Imputation Strategy — Complete Reference

### Strategy A: Fill 0 — "Absence Means No Signal" (20 features)

Used when a missing value semantically means the event/condition did not occur.

| Feature | Why 0 Is Correct |
|---|---|
| `is_cross_dept` | Not cross-dept = no coordination overhead |
| `revision_frequency` | No revisions = no churn |
| `revision_recency` | No revisions = undefined; 0 = never revised |
| `subtask_completion_pct` | No subtasks = nothing completed |
| `subtask_overdue_rate` | No subtasks = no overdue subtasks |
| `subtask_completion_pct_at_halfway` | No history at halfway = 0% done |
| `num_challenges` | No challenges logged = 0 |
| `has_challenges` | No challenges = False |
| `cross_dept_pair_exists` | No cross-dept pair = False |
| `kpi_is_overdue_flag` | No KPI = not overdue at KPI level |
| `has_subtask_challenge` | No subtask challenges |
| `num_subtask_challenges` | 0 subtask challenges logged |
| `has_kpi_challenge` | No KPI challenges |
| `num_kpi_challenges` | 0 KPI challenges logged |
| `has_kpi_potential_challenge` | No potential KPI challenges |
| `num_kpi_potential_challenges` | 0 potential KPI challenges |
| `kpi_comment_count` | No KPI comments = 0 |
| `ma_comment_count` | No MA comments = 0 |
| `task_comment_count` | No task comments = 0 |
| `avg_sub_status_changes` | No subtask history = 0 changes |

### Strategy B: Fill 1 — "Neutral Default for Ordinal Status" (6 features)

All status/approval features use `ordinal_encode_status(fallback=1)`.

| Feature | Why 1, Not 0 or 2 |
|---|---|
| `status_encoded` | 1 = ongoing/in_progress — neutral. 0 = not_started (too aggressive), 2 = completed (misleading for null) |
| `approval_status_encoded` | 1 = in_review — neutral pending state |
| `lead_approval_status_encoded` | Same — in_review |
| `ma_status_encoded` | 1 = ongoing — MA is still active |
| `ma_approval_status_encoded` | 1 = in_review — neutral pending |
| `kpi_status_ordinal` | 1 = ongoing — KPI is still active. Also explicitly filled via `.fillna(1)` in `impute_features()` |

The value 1 minimizes bias. It is NOT the majority class (most tasks are completed=2).

### Strategy C: Fill Global Mean — Rate Aggregates (4 features)

| Feature | Null % | Fill Value | Reasoning |
|---|---|---|---|
| `dept_past_overdue_rate` | 2.7% | ~0.20 | New dept gets global average — conservative |
| `dept_avg_revisions` | 2.7% | ~2.1 | New dept gets average revision count |
| `emp_past_overdue_rate` | 7.7% | ~0.20 | New employee with no history gets global rate |
| `pos_past_overdue_rate` | 4.8% | ~0.20 | New position gets global rate |

### Strategy D: UNKNOWN Category — Position ID (1 feature)

`position_id` (4.8% null) → mapped to string `'UNKNOWN'` → then target-encoded to global mean (~0.20).

### Before vs After Imputation Summary

| Feature Group | Strategy | Before (null %) | After |
|---|---|---|---|
| Status/approval (5) | Fallback 1 | 0% | 0 |
| Temporal (8) | None / always present | 0% | 0 |
| Planning (5) | None | 0% | 0 |
| Revisions (3) | Fill 0 | ~8% | 0 |
| Subtask (5) | Fill 0 | ~92% | 0 |
| Challenge task (2) | Fill 0 | ~47% | 0 |
| Challenge sparse (6) | Fill 0 | 87–99.8% | 0 |
| Cross-dept (2) | Fill 0 | 1.4–98.6% | 0 |
| MA revisions (1) | Fill 0 | ~3% | 0 |
| KPI (3) | Fill 0 + Fill 1 | ~5% | 0 |
| Comments (3) | Fill 0 | 90–100% | 0 |
| Sub-task history (1) | Fill 0 | ~98.4% | 0 |
| Rate aggregates (4) | Fill global mean | 2.7–7.7% | 0 |
| Position encoding (1) | UNKNOWN + target encode | 4.8% | 0 |

**Final: 0 nulls across all 13,895 × 51 cells.**

## Data Quality Findings

Source: [`docs/handoff_H5.md`](../docs/handoff_H5.md), [`sql/v1/data_quality_checks.sql`](../sql/v1/data_quality_checks.sql)

| Check | Result | Detail |
|---|---|---|
| Task rows | PASS | 13,895 |
| Null `status` | PASS | 0% |
| Null `start_date` | PASS | 0% |
| Null `end_date` | PASS | 0% |
| Null `actual_end_date` (completed only) | WARN | 43.2% — resolved via three-tier target: history first-completed timestamp (231 tasks) + updated_date fallback (5,427 tasks) |
| Null department_id (resolved) | PASS | 2.7% — filled via global mean |
| Null position_id | PASS | 4.8% — mapped to UNKNOWN |
| Duplicate task IDs | PASS | 0 |
| Duplicate subtask IDs | PASS | 0 |
| Orphan history → task | PASS | 0 |
| Orphan subtask → task | PASS | 0 |
| Orphan challenge → task | PASS | 0 |
| `end_date < start_date` | WARN | 4 tasks (0.03%) — data entry errors, negligible |
| Future `created_date` | PASS | 0 |
| `planned_duration <= 0` | PASS | 1,421 (10.2%) — same-day tasks are legitimate |
| Content type IDs | VERIFIED | KPI=22, MA=23, Task=24 |

### Notable Observations

1. **Retroactive scheduling** — 76% of tasks have `start_date < created_date`. Tasks are often created after work has begun. This is expected, not a quality issue.

2. **Comment system sparsity** — MA comments (content_type_id=23) have zero rows. The `ma_comment_count` feature is dead weight.

3. **Negative durations** — 4 tasks have `end_date < start_date`. These are 0.03% of data — negligible for modeling.

## Duplicate Handling

| Check | Result |
|---|---|
| Duplicate task IDs (creation) | 0 — 13,895 unique |
| Duplicate rows (creation) | 0 |
| Duplicate task IDs (halfway) | 0 — 13,895 unique |
| Duplicate subtask IDs (source) | 0 |
| Orphaned history records | 0 |
| Orphaned challenge groups | 0 |

**Why no duplicates occurred:**
- `tasks_task.id` is a UUID primary key — no source duplicates possible
- All joins are LEFT JOIN from tasks_task (1 task = 1 row preserved)
- All 1:N relationships (subtasks, challenges, comments, history) are aggregated via GROUP BY before merging
- No deduplication code was needed

## Dataset Variants

### Creation-Time Dataset (34 features)

Features available at task assignment — split into groups:

| Group | Features | Count |
|---|---|---|
| Status & Approval | `status_encoded`, `approval_status_encoded`, `lead_approval_status_encoded`, `ma_status_encoded`, `ma_approval_status_encoded` | 5 |
| Temporal | `planned_duration`, `creation_to_planned_start`, `created_dow`, `created_is_weekend`, `created_is_friday`, `created_month`, `created_quarter` | 7 |
| Planning | `is_planned`, `risk_mapping`, `wl_high`, `wl_mid`, `wl_low` | 5 |
| Cross-Department | `is_cross_dept`, `cross_dept_pair_exists` | 2 |
| MA Revisions | `num_ma_revisions` | 1 |
| KPI | `kpi_is_overdue_flag`, `kpi_status_ordinal`, `num_kpi_revisions` | 3 |
| KPI Challenges (sparse) | `has_kpi_challenge`, `num_kpi_challenges`, `has_kpi_potential_challenge`, `num_kpi_potential_challenges` | 4 |
| Comments | `kpi_comment_count`, `ma_comment_count` | 2 |
| Rate Aggregates | `dept_past_overdue_rate`, `dept_avg_revisions`, `emp_past_overdue_rate`, `pos_past_overdue_rate` | 4 |
| Position Encoding | `position_id_encoded` | 1 |
| **Total** | | **34** |

**Use:** Baseline model for prediction at assignment — before work begins.

### Halfway Dataset (49 features)

Creation 34 + 15 accumulation features:

| Group | Features Added | Count |
|---|---|---|
| Revisions | `num_revisions`, `revision_frequency`, `revision_recency` | 3 |
| Subtask | `num_subtasks`, `has_subtasks`, `subtask_completion_pct`, `subtask_overdue_rate` | 4 |
| Halfway Subtask | `subtask_completion_pct_at_halfway` | 1 |
| Challenges | `has_challenges`, `num_challenges` | 2 |
| Sub-Task Challenges | `has_subtask_challenge`, `num_subtask_challenges` | 2 |
| Sub-Task History | `avg_sub_status_changes` | 1 |
| Activity | `days_since_update`, `task_comment_count` | 2 |
| **Total added** | | **15** |

**Halfway point formula:** `start_date + planned_duration / 2`  
**Subtask completion at halfway:** Queried from `tasks_sub_task_history` with cutoff at halfway date (not current subtask status) — it reflects the actual state at the prediction point, not current values.

**Use:** Mid-course correction — score tasks currently in flight.

## Overall Modeling Impact

### Strongest Features
`status_encoded`, `planned_duration`, `creation_to_planned_start`, `num_revisions`, `revision_frequency`, `subtask_completion_pct`, `subtask_overdue_rate`, `kpi_is_overdue_flag`, `position_id_encoded`, `dept_past_overdue_rate`, `emp_past_overdue_rate`, `pos_past_overdue_rate`

### Useful but Sparse
`has_subtask_challenge`, `num_subtask_challenges`, `has_kpi_challenge`, `num_kpi_challenges`, `has_kpi_potential_challenge`, `num_kpi_potential_challenges`, `cross_dept_pair_exists`, `avg_sub_status_changes`

### Potentially Weak / Dead
`ma_comment_count` — zero rows in current snapshot

### Leakage-Sensitive (must be fold-safe)
`days_since_update`, `revision_recency`, `dept_past_overdue_rate`, `dept_avg_revisions`, `emp_past_overdue_rate`, `pos_past_overdue_rate`, `position_id_encoded`, any count/rate from history

### Halfway Point Leakage Consideration

The halfway computation uses `subtask_completion_pct_at_halfway` — the subtask status at the theoretical midpoint, not the current status. However, features like `subtask_completion_pct` (current) and `revision_recency` use today's data, which includes information after the halfway point. For a strict halfway prediction scenario:

- **Safe:** `subtask_completion_pct_at_halfway`
- **Leaky if used at halfway:** `subtask_completion_pct`, `subtask_overdue_rate`, `num_revisions`, `revision_recency`, `days_since_update`, `num_subtasks` (current count may include subtasks created after halfway)

If building a strictly time-aware halfway model, the `subtask_completion_pct_at_halfway` feature was designed specifically to avoid this leak.

## References

- [`notebooks/v1/explore_tasks_task.ipynb`](../notebooks/v1/explore_tasks_task.ipynb) — target definition exploration & overdue analysis
- [`notebooks/v1/clean_and_build_dataset.ipynb`](../notebooks/v1/clean_and_build_dataset.ipynb) — end-to-end dataset construction notebook
- [`notebooks/v1/feature_analysis.ipynb`](../notebooks/v1/feature_analysis.ipynb) — feature analysis and impact exploration
- [`docs/handoff_H1.md`](../docs/handoff_H1.md) — dataset schema & data sources (full feature inventory with types)
- [`docs/handoff_H2.md`](../docs/handoff_H2.md) — table relationships & join strategy (PK/FK matrix, resolution cascades)
- [`docs/handoff_H5.md`](../docs/handoff_H5.md) — data quality findings (null rates, sparsity, date integrity)
- [`src/v1/build_features.py`](../src/v1/build_features.py) — end-to-end pipeline
- [`src/v1/feature_engineering.py`](../src/v1/feature_engineering.py) — reusable feature functions
- [`sql/v1/analytical_dataset.sql`](../sql/v1/analytical_dataset.sql) — full extraction SQL
- [`sql/v1/data_quality_checks.sql`](../sql/v1/data_quality_checks.sql) — 15+ validation checks
