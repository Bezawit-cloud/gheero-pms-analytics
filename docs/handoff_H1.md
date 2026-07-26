# Handoff H1 — Dataset Schema & Data Sources

## Analytical Dataset Overview

The final analytical dataset contains **13,895 rows** (one per task) and **51 columns** (1 ID, 1 target, 49 features). It is built from **14 source tables** and outputs two prediction-time variants:

| Variant | Rows | Columns | Description |
|---------|------|---------|-------------|
| `dataset_at_creation.csv` | 13,895 | 36 | Features known when a task is first created/assigned |
| `dataset_at_halfway.csv` | 13,895 | 51 | Adds 15 features that accumulate during execution (available at halfway point) |

## Data Sources (All Tables Used)

### Core Tables

| # | Table | Rows (approx.) | Role |
|---|-------|----------------|------|
| 1 | `tasks_task` | 13,895 | Primary table — one row per task. Contains status, dates, assignments. |
| 2 | `basedata_position` | ~200 | Position/role definitions. Maps position → department, position → user (assignee). |
| 3 | `tasks_major_activity` | ~500 | Parent activity that tasks roll up to. Provides MA status, approval status, KPI linkage. |
| 4 | `tasks_kpi` | ~200 | Key Performance Indicators. Provides KPI overdue flag and status. |

### History Tables

| # | Table | Rows (approx.) | Role |
|---|-------|----------------|------|
| 5 | `tasks_task_history` | ~120,000 | Revision log per task. Used for revision count, frequency, recency. |
| 6 | `tasks_sub_task_history` | 778,348 | Change log per subtask. Used for halfway completion computation and status churn. |
| 7 | `tasks_major_activity_history` | ~40,000 | Revision log per MA. Used for MA revision count. |
| 8 | `tasks_kpi_history` | ~7,000 | Revision log per KPI. Used for KPI revision count. |

### Junction / Detail Tables

| # | Table | Rows (approx.) | Role |
|---|-------|----------------|------|
| 9 | `tasks_sub_task` | ~4,200 | Subtask-level data. Used for count, completion %, overdue %. |
| 10 | `tasks_task_challenge_groups` | ~7,400 | Challenges/roadblocks logged per task. |
| 11 | `tasks_cross_department_assignments` | ~200 | Cross-department assignment pairs. |
| 12 | `tasks_sub_task_challenge_groups` | ~40 | Challenges logged at the subtask level. |
| 13 | `tasks_kpis_challegne_groups` | ~200 | Challenges logged at the KPI level. |
| 14 | `tasks_kpis_potential_challenge_groups` | ~2,500 | Potential/planned challenges at the KPI level. |
| 15 | `comments_comment` | ~95,000 | Comments filtered by content_type_id (22=KPI, 23=MA, 24=Task). |

## Feature Inventory (49 Features, 14 Groups)

### Group 1: Status & Approval (5 features)
| Feature | Type | Source | Description |
|---------|------|--------|-------------|
| `status_encoded` | ordinal (0-4) | `tasks_task.status` | not_started=0, ongoing/in_progress=1, completed=2, terminated=3, archived=4 |
| `approval_status_encoded` | ordinal (0-3) | `tasks_task.approval_status` | pending=0, in_review=1, approved=2, rejected=3 |
| `lead_approval_status_encoded` | ordinal (0-3) | `tasks_task.lead_approval_status` | Same encoding as approval_status |
| `ma_status_encoded` | ordinal (0-3) | `tasks_major_activity.status` | not_started=0, ongoing=1, completed=2, terminated=3 |
| `ma_approval_status_encoded` | ordinal (0-3) | `tasks_major_activity.approval_status` | Same encoding as approval |

### Group 2: Temporal (8 features)
| Feature | Type | Source |
|---------|------|--------|
| `planned_duration` | int (days) | `end_date - start_date` |
| `creation_to_planned_start` | int (days) | `start_date - created_date` |
| `days_since_update` | int (days) | `today - updated_date` |
| `created_dow` | int (0-6) | `EXTRACT(DOW FROM created_date)` |
| `created_is_weekend` | binary | 1 if DOW >= 5 |
| `created_is_friday` | binary | 1 if DOW = 4 |
| `created_month` | int (1-12) | `EXTRACT(MONTH FROM created_date)` |
| `created_quarter` | int (1-4) | `EXTRACT(QUARTER FROM created_date)` |

### Group 3: Planning (5 features)
| Feature | Type | Source |
|---------|------|--------|
| `is_planned` | binary | `tasks_task.is_planned` |
| `risk_mapping` | float (0-10) | `tasks_task.risk_mapping` |
| `wl_high`, `wl_mid`, `wl_low` | binary dummies | One-hot from `tasks_task.weight_level` |

### Group 4: Revisions (3 features)
| Feature | Type | Source |
|---------|------|--------|
| `num_revisions` | int | COUNT of `tasks_task_history` entries |
| `revision_frequency` | float | `num_revisions / task_age_days` |
| `revision_recency` | int (days) | `today - MAX(history_date)` |

### Group 5: Subtasks (5 features)
| Feature | Type | Source |
|---------|------|--------|
| `num_subtasks` | int | COUNT of `tasks_sub_task` entries |
| `has_subtasks` | binary | 1 if num_subtasks > 0 |
| `subtask_completion_pct` | float (0-1) | `num_completed / num_subtasks` |
| `subtask_overdue_rate` | float (0-1) | `num_overdue / num_subtasks` |
| `subtask_completion_pct_at_halfway` | float (0-1) | Completion % at `start + duration/2` from history |

### Group 6: Challenges (2 features)
| Feature | Type | Source |
|---------|------|--------|
| `has_challenges` | binary | 1 if challenge group exists |
| `num_challenges` | int | COUNT of `tasks_task_challenge_groups` entries |

### Group 7: Cross-Department (2 features)
| Feature | Type | Source |
|---------|------|--------|
| `is_cross_dept` | binary | Derived from `derived_from_cross_department_assignment_id` |
| `cross_dept_pair_exists` | binary | 1 if JOIN to `tasks_cross_department_assignments` succeeds |

### Group 8: MA Revisions (1 feature)
| Feature | Type | Source |
|---------|------|--------|
| `num_ma_revisions` | int | COUNT of `tasks_major_activity_history` entries |

### Group 9: KPI (3 features)
| Feature | Type | Source |
|---------|------|--------|
| `kpi_is_overdue_flag` | binary | `tasks_kpi.is_overdue` |
| `kpi_status_ordinal` | ordinal (0-4) | Encode of `tasks_kpi.status` |
| `num_kpi_revisions` | int | COUNT of `tasks_kpi_history` entries |

### Group 10: Sparse Challenges (6 features)
| Feature | Type | Source |
|---------|------|--------|
| `has_subtask_challenge` | binary | From `tasks_sub_task_challenge_groups` |
| `num_subtask_challenges` | int | Same |
| `has_kpi_challenge` | binary | From `tasks_kpis_challegne_groups` |
| `num_kpi_challenges` | int | Same |
| `has_kpi_potential_challenge` | binary | From `tasks_kpis_potential_challenge_groups` |
| `num_kpi_potential_challenges` | int | Same |

### Group 11: Comments (3 features)
| Feature | Type | Source |
|---------|------|--------|
| `kpi_comment_count` | int | `comments_comment WHERE content_type_id=22` |
| `ma_comment_count` | int | `comments_comment WHERE content_type_id=23` |
| `task_comment_count` | int | `comments_comment WHERE content_type_id=24` |

### Group 12: Sub-Task History (1 feature)
| Feature | Type | Source |
|---------|------|--------|
| `avg_sub_status_changes` | float | Avg distinct statuses from `tasks_sub_task_history` |

### Group 13: Rate Aggregates (4 features)
| Feature | Type | Source |
|---------|------|--------|
| `dept_past_overdue_rate` | float | Dept-level avg of `calculated_overdue` |
| `dept_avg_revisions` | float | Dept-level avg of revision count |
| `emp_past_overdue_rate` | float | Employee-level avg of `calculated_overdue` |
| `pos_past_overdue_rate` | float | Position-level avg of `calculated_overdue` |

### Group 14: Position Encoding (1 feature)
| Feature | Type | Source |
|---------|------|--------|
| `position_id_encoded` | float (0-1) | Target encoding of `position_id` → mean `calculated_overdue` per position |

## Target Definition

`calculated_overdue` = 1 if EITHER:
- Task status is `completed` AND `actual_end_date > end_date` (completed late)
- Task is NOT in `{completed, terminated, archived}` AND `end_date < today` (still open but past deadline)

Otherwise 0.

Rate: **20.1%** of tasks are overdue.

## Imputation Strategy

| Strategy | Features | Count |
|----------|----------|-------|
| Fill 0 (absence = no signal) | `is_cross_dept`, `revision_frequency`, `revision_recency`, `subtask_completion_pct`, `subtask_overdue_rate`, `subtask_completion_pct_at_halfway`, `num_challenges`, `has_challenges`, `cross_dept_pair_exists`, `kpi_is_overdue_flag`, `has_subtask_challenge`, `num_subtask_challenges`, `has_kpi_challenge`, `num_kpi_challenges`, `has_kpi_potential_challenge`, `num_kpi_potential_challenges`, `kpi_comment_count`, `ma_comment_count`, `task_comment_count`, `avg_sub_status_changes` | 20 |
| Fill 1 (neutral state) | `kpi_status_ordinal` | 1 |
| Fill global mean | `dept_past_overdue_rate`, `dept_avg_revisions`, `emp_past_overdue_rate`, `pos_past_overdue_rate` | 4 |
| "UNKNOWN" category | `position_id` | 1 |

## Join Strategy Summary

All joins use LEFT JOIN from `tasks_task`. The resolution cascade for department is:
1. Lookup `basedata_position.department_id` via `tasks_task.position_id`
2. Fall back to `tasks_task.department_id` if position has no department

The KPI resolution cascade is: `tasks_task` → `tasks_major_activity` (via `major_activity_id`) → `tasks_kpi` (via `kpi_id`).
