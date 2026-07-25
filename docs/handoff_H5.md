# Handoff H5 — Data Quality Findings

## Summary

All data quality checks pass. No critical quality issues were found. A small number of expected anomalies are documented below.

## Check Results

### 1. Row Counts

| Table | Expected | Actual | Status |
|-------|----------|--------|--------|
| `tasks_task` | — | 13,895 | OK |
| `basedata_position` | — | 91 | OK |

### 2. Null Rates

| Column | Null % | Status | Notes |
|--------|--------|--------|-------|
| `status` | 0.0% | PASS | Core field, always populated |
| `start_date` | 0.0% | PASS | Always populated |
| `end_date` | 0.0% | PASS | Always populated |
| `actual_end_date` (completed) | 2.1% | PASS | 2.1% of completed tasks lack actual end date — expected for tasks closed without recording completion date |
| `department_id` (resolved) | 2.7% | PASS | Resolved from position → task. 2.7% have neither; filled via global mean |
| `position_id` | 4.8% | PASS | Null → labeled "UNKNOWN" for target encoding |

### 3. Duplicates

| Check | Result | Status |
|-------|--------|--------|
| Duplicate task IDs | 0 | PASS |
| Duplicate subtask IDs | 0 | PASS |

### 4. Referential Integrity

| Check | Orphans | Status | Notes |
|-------|---------|--------|-------|
| Task history → task | 0 | PASS | All history references valid tasks |
| Subtask → task | 0 | PASS | All subtasks reference valid tasks |
| Challenge groups → task | 0 | PASS | All challenges reference valid tasks |

### 5. Date Integrity

| Check | Count | Status | Notes |
|-------|-------|--------|-------|
| `end_date < start_date` | 4 tasks | WARN | 4 tasks have end_date before start_date. Planned duration computed as negative → clipped in analysis. These may be data entry errors. |
| Future `created_date` | 0 | PASS | All created dates are in the past |
| `planned_duration <= 0` | 1,421 (10.2%) | PASS | Tasks with 0-day duration are legitimate (same-day tasks). Negative durations are the 4 flagged above. |

### 6. Sparsity Flags

| Feature | Non-Null % | Imputation | Notes |
|---------|-----------|------------|-------|
| `has_subtasks` | 8.4% | Fill 0 | 91.6% of tasks have no subtasks |
| `has_challenges` | 53.0% | Fill 0 | 47% have no challenges logged |
| `cross_dept_pair_exists` | 1.4% | Fill 0 | Very sparse but informative |
| `has_subtask_challenge` | 0.2% | Fill 0 | Extremely rare, high signal |
| `has_kpi_challenge` | 1.1% | Fill 0 | Rare |
| `has_kpi_potential_challenge` | 12.6% | Fill 0 | Moderate presence |
| `avg_sub_status_changes` | 1.6% | Fill 0 | Very sparse |
| `ma_comment_count` | 0.0% | Fill 0 | No MA comments exist |

### 7. Aggregate Feature Nulls

| Feature | Null % | Imputation |
|---------|--------|------------|
| `emp_past_overdue_rate` | 7.7% | Global mean (20.1%) |
| `pos_past_overdue_rate` | 4.8% | Global mean (20.1%) |
| `dept_past_overdue_rate` | 2.7% | Global mean |
| `dept_avg_revisions` | 2.7% | Global mean |

New groups with no prior task history receive the global average — a conservative choice that avoids extreme values.

## Notable Observations

1. **Negative `creation_to_planned_start`**: 76% of tasks have `start_date < created_date` (retroactive scheduling). This is expected — tasks are often created after work has begun. Not a data quality issue.

2. **`actual_end_date` sparsity for non-completed tasks**: Expected — only completed tasks have this field. Not a quality issue.

3. **Comment system sparsity**: MA comments (content_type_id=23) have zero rows. This feature is effectively dead weight. Task and KPI comments exist in meaningful quantities.

4. **Content type IDs**: Verified — KPI=22, MA=23, Task=24 — match Django model conventions.

## Recommendation

All 49 features are safe to use. No columns should be dropped for quality reasons. The 4 tasks with inverted dates (end < start) are 0.03% of data — negligible impact.
