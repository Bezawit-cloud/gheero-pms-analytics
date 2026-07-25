# Handoff H2 — Table Relationships & Join Strategy

## Entity-Relationship Overview

(ER diagram generated separately: `reports/ER-Diagram.png`)

This document describes the table relationships and join strategy used to build the analytical dataset.

## Core Entity Hierarchy

```
basedata_position ──┐
                    ├──→ tasks_task ──→ tasks_task_history
                    │       │
basedata_department ┘       ├──→ tasks_sub_task ──→ tasks_sub_task_history
                            │       │
                            │       └──→ tasks_sub_task_challenge_groups
                            │
                            ├──→ tasks_task_challenge_groups
                            │
                            ├──→ tasks_cross_department_assignments
                            │
                            └──→ tasks_major_activity ──→ tasks_major_activity_history
                                      │
                                      └──→ tasks_kpi ──→ tasks_kpi_history
                                              │
                                              ├──→ tasks_kpis_challegne_groups
                                              └──→ tasks_kpis_potential_challenge_groups

comments_comment ──→ (polymorphic FK via object_id + content_type_id)
```

## Primary Key / Foreign Key Relationships

### Direct Joins (1:1 or M:1)

| Source Table | FK Column | Target Table | Target PK | Join Type |
|-------------|-----------|-------------|-----------|-----------|
| `tasks_task` | `position_id` | `basedata_position` | `id` | LEFT |
| `tasks_task` | `major_activity_id` | `tasks_major_activity` | `id` | LEFT |
| `tasks_task` | `department_id` | `basedata_department` | `id` | LEFT (fallback) |
| `tasks_task` | `derived_from_cross_department_assignment_id` | `tasks_cross_department_assignments` | `id` | LEFT |
| `tasks_major_activity` | `kpi_id` | `tasks_kpi` | `id` | LEFT |

### One-to-Many Joins (aggregated)

| Source Table | FK Column | Target Table | Aggregation | 
|-------------|-----------|-------------|-------------|
| `tasks_task_history` | `history_relation_id` | `tasks_task.id` | COUNT, MAX(history_date) |
| `tasks_sub_task` | `task_id` | `tasks_task.id` | COUNT, SUM(completion) |
| `tasks_sub_task_history` | `id` (sub_task_id) | `tasks_sub_task.id` | Latest status per cutoff |
| `tasks_task_challenge_groups` | `task_id` | `tasks_task.id` | COUNT |
| `tasks_major_activity_history` | `id` (ma_id) | `tasks_major_activity.id` | COUNT |
| `tasks_kpi_history` | `id` (kpi_id) | `tasks_kpi.id` | COUNT |
| `tasks_sub_task_challenge_groups` | `subtask_id` | `tasks_sub_task.id` | COUNT |

### Junction Table Joins

| Junction Table | FK1 | FK2 | Resolution |
|---------------|-----|-----|------------|
| `tasks_sub_task_challenge_groups` | `subtask_id` → `tasks_sub_task` | `tasks_sub_task.task_id` → `tasks_task` | Sub-task challenges rolled up to task level |
| `tasks_kpis_challegne_groups` | `kpi_id` → `tasks_kpi` | `tasks_kpi.id` → `tasks_major_activity.kpi_id` → `tasks_task.major_activity_id` | KPI challenges rolled up to task via MA chain |
| `tasks_kpis_potential_challenge_groups` | `kpi_id` → `tasks_kpi` | (same chain) | Potential KPI challenges |

### Polymorphic Joins (Comments)

`comments_comment` uses Django's generic foreign key pattern:
- `object_id` = FK value
- `content_type_id` = 22 (KPI), 23 (MA), 24 (Task)

Comments are aggregated per entity, then joined via the task → MA → KPI chain.

## Department Resolution Cascade

Department is resolved in a 2-level cascade:
1. `basedata_position.department_id` (via `tasks_task.position_id`)
2. Fallback: `tasks_task.department_id`

This is used both for:
- Computing the `dept_past_overdue_rate` aggregate
- Assigning each task to its resolved department

The SQL pattern:
```sql
COALESCE(p.department_id, t.department_id) AS resolved_dept_id
FROM tasks_task t
LEFT JOIN basedata_position p ON p.id = t.position_id
```

## KPI Resolution Chain

KPI data reaches tasks through a 2-hop chain:
```
tasks_task.major_activity_id
    → tasks_major_activity.id
        → tasks_major_activity.kpi_id
            → tasks_kpi.id
```

All KPI-level features (flags, challenges, comments, revisions) are joined via this chain.

## Cross-Department Flag Resolution

Two features capture cross-department work:
1. `is_cross_dept`: Boolean flag on `tasks_task.derived_from_cross_department_assignment_id IS NOT NULL`
2. `cross_dept_pair_exists`: Exists if `tasks_task` links to a record in `tasks_cross_department_assignments`

## Halfway-Point Feature Strategy

For the halfway-prediction variant, `subtask_completion_pct_at_halfway` is computed using:
1. Compute `halfway_date = start_date + (end_date - start_date) / 2`
2. Find subtasks with `created_date <= halfway_date`
3. For each, find the latest `tasks_sub_task_history` entry before `halfway_date`
4. If no history entry exists, use the current `tasks_sub_task.status`
5. `completion = completed_at_halfway / subtasks_at_halfway`

This is NOT simply the current completion rate — it reflects the actual state at the prediction point.
