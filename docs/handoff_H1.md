# Analytical Dataset — Schema Design & Documentation

This document defines the structure of `analytical_dataset.csv` — the single, analysis-ready
dataset Phase 1 produces for Phase 2. One row per task. This is a **schema design** document;
the actual extraction SQL and generated CSV are separate deliverables (`sql/analytical_dataset.sql`,
`data/analytical_dataset.csv`).

Every column below traces back to a tested finding in `docs/handoff_H2.md` (table relationship
analysis) or is required raw material for a decision explicitly deferred to Phase 2.

---

## Group Decisions (resolved 2026-07-25)

Three open questions were raised in group discussion. Resolved as follows, favoring the
**broader/more inclusive option** in each case — Phase 2 can narrow or ignore any of these later,
but Phase 1 should never withhold raw material that could remove an option from Phase 2 before
they've had a chance to decide.

### Decision 1 — What counts as an "active" / not-yet-resolved task?

**Resolved: broad definition.** `status != 'completed'` — includes `not_started`, `on_review`,
`ongoing`, `archived`, and `terminated`, all treated as "not completed" for overdue-calculation
purposes. This matches the existing `calculated_overdue` logic already in use since Week-0 —
**no SQL change was needed**, this decision formalizes and documents an existing implicit choice.

**Known simplification, flagged not fixed**: this definition technically also includes
`archived`/`terminated` tasks as "not completed," which may not perfectly reflect intent (an
archived task isn't "still open" the way an `ongoing` one is). Not corrected in Phase 1 —
documented here so Phase 2 can adjust if it affects their modeling.

### Decision 2 — When should the prediction point be (task creation vs. some time after)?

**Resolved: deferred entirely to Phase 2**, per the assignment brief (Section 12.2, under Part
Seven — Machine Learning Task, explicitly Phase 2's Major Activity 1.3). Phase 1's responsibility
is to ensure the dataset preserves **all raw timing material** needed to reconstruct _any_
prediction point Phase 2 chooses: `created_date`, `planned_start_date`, `planned_end_date`,
`actual_start_date`, plus full task history (`tasks_task_history`, extracted separately/available
for join). No single fixed prediction point is baked into this dataset.

### Decision 3 — Sub-task count vs. sub-task weight for completion features?

**Resolved: include both.** `tasks_sub_task.weight` (numeric) was confirmed to exist via schema
check. Both count-based and weight-based sub-task completion columns are included, so Phase 2
can build either a simple completion percentage or a weighted completion percentage, without
needing to request additional extraction later.

---

## Final Column List

### Core / Identity

| Column      | Type | Source                 | Why included                  |
| ----------- | ---- | ---------------------- | ----------------------------- |
| `task_id`   | uuid | `tasks_task.id`        | Primary key, one row per task |
| `task_name` | text | `tasks_task.task_name` | Human-readable reference      |

### Department / Position / Employee

| Column              | Type                               | Source                                                                             | Why included                                                                       |
| ------------------- | ---------------------------------- | ---------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `department_id`     | uuid                               | resolved: direct `tasks_task.department_id`, fallback via `position.department_id` | Strongest direct signal found (13.5%–46.2% overdue-rate spread across departments) |
| `department_source` | text ('direct'/'position_derived') | derived                                                                            | Documents which resolution path was used — direct field is null 89% of the time    |
| `position_id`       | uuid                               | `tasks_task.position_id`                                                           | Second-strongest direct signal (9.9%–48.0% spread)                                 |
| `employee_id`       | uuid                               | `basedata_position.user_id`                                                        | Needed for future employee-level features; ~92% resolvable                         |

### Dates & Status

| Column                | Type                                 | Source                         | Why included                                                                                                                                             |
| --------------------- | ------------------------------------ | ------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `planned_start_date`  | date                                 | `tasks_task.start_date`        | Timing/duration features; raw material for Phase 2's prediction-point choice                                                                             |
| `planned_end_date`    | date                                 | `tasks_task.end_date`          | Same; also defines the deadline used in the target label                                                                                                 |
| `actual_start_date`   | date                                 | `tasks_task.actual_start_date` | Raw material only — must not be used directly as a feature without a prediction-point cutoff (leakage risk, Phase 2's responsibility to apply correctly) |
| `actual_end_date`     | date                                 | `tasks_task.actual_end_date`   | Used only to compute the target label, never as a feature                                                                                                |
| `status`              | text                                 | `tasks_task.status`            | Needed to compute `calculated_overdue`; broad "active" definition applied (Decision 1)                                                                   |
| `is_overdue` (stored) | boolean                              | `tasks_task.is_overdue`        | Retained for comparison only — proven unreliable in Week-0 (~24% disagreement with calculated label)                                                     |
| `calculated_overdue`  | text ('true'/'false'/'undetermined') | derived                        | Independently-derived target label; do not use stored `is_overdue` as ground truth                                                                       |

### Direct Signals

| Column         | Type                      | Source                    | Why included                                                              |
| -------------- | ------------------------- | ------------------------- | ------------------------------------------------------------------------- |
| `task_weight`  | numeric                   | `tasks_task.weight`       | Direct signal, weak but real (non-monotonic across raw buckets)           |
| `weight_level` | text ('high'/'mid'/'low') | `tasks_task.weight_level` | Cleaner categorical alternative to raw weight; real ~5pt monotonic spread |
| `is_planned`   | boolean                   | `tasks_task.is_planned`   | Real ~6pt gap (23.37% planned vs 29.26% unplanned)                        |

### Indirect Signals

| Column                            | Type                 | Source                                                   | Why included                                                                                                      |
| --------------------------------- | -------------------- | -------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `has_cross_department_assignment` | boolean              | `tasks_cross_department_assignments`, presence of record | **Strongest finding overall** — ~19pt gap (24.23% vs 43.62%), empirically confirmed safe (188/188 timing-checked) |
| `ksi_linked_goal_count`           | integer (0 / 1 / 2+) | `tasks_ksi_goals`, via full hierarchy join               | Real ~12pt gap (19.51% at 0 goals vs ~30-32% at 1+)                                                               |

### Sub-Task Completion (count + weight, per Decision 3)

| Column                     | Type              | Source                                                       | Why included                                             |
| -------------------------- | ----------------- | ------------------------------------------------------------ | -------------------------------------------------------- |
| `n_subtasks`               | integer           | `tasks_sub_task`, count by `task_id`                         | Parent-child completeness signal                         |
| `n_completed_subtasks`     | integer           | `tasks_sub_task`, count where `status = 'completed'`         | Same                                                     |
| `subtask_completion_pct`   | numeric, nullable | derived (`n_completed_subtasks / n_subtasks`)                | Simple completion ratio; NULL (not 0) when zero subtasks |
| `total_subtask_weight`     | numeric           | `tasks_sub_task.weight`, summed by `task_id`                 | Enables weighted completion calculation in Phase 2       |
| `completed_subtask_weight` | numeric           | `tasks_sub_task.weight`, summed where `status = 'completed'` | Same                                                     |

### Traceability / History

| Column              | Type      | Source                              | Why included                                                                                 |
| ------------------- | --------- | ----------------------------------- | -------------------------------------------------------------------------------------------- |
| `n_revisions`       | integer   | `tasks_task_history`, count by task | Raw revision count baseline (Week-0)                                                         |
| `major_activity_id` | uuid      | `tasks_task.major_activity_id`      | Kept for traceability/rollups only — too high-cardinality (4,296 distinct values) to use raw |
| `created_date`      | timestamp | `tasks_task.created_date`           | Required for time-based train/test split; raw material for Phase 2's prediction-point choice |
| `updated_date`      | timestamp | `tasks_task.updated_date`           | QA/debugging reference                                                                       |

---

## Deliberately Excluded (with reasons)

| Field/relationship                        | Why excluded                                                                                                                                        |
| ----------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| Raw comment count / comment presence      | **Leakage, confirmed empirically** — 72% of comments post-date the task deadline (see `handoff_H2.md` Section 2.8)                                  |
| Live department/employee congestion count | Leakage risk requiring historical active-set reconstruction, not a simple column; also small-sample-fragile (see `handoff_H2.md` Sections 2.4, 2.7) |
| `tasks_ksi_goals.approval_status`         | Tested, not predictive (~2.3pt gap — noise)                                                                                                         |
| `tasks_kpi.goal_id` direct bypass flag    | Tested, not predictive (~2.8pt gap — noise)                                                                                                         |
| Task priority field                       | Does not exist in the schema (confirmed via `information_schema.columns`)                                                                           |

---

## Notes for Phase 2

- The dataset intentionally does **not** pre-select a prediction point. Use `created_date`,
  `planned_start_date`, `planned_end_date`, `actual_start_date`, and joinable
  `tasks_task_history` to construct whichever prediction point you choose.
- `actual_start_date` and `actual_end_date` are raw fields — apply your own leakage-safe
  cutoff logic before using either as a model input.
- Both count-based and weight-based sub-task completion columns are provided; choose one or
  compare both.
- `calculated_overdue` is `CURRENT_DATE`-dependent for incomplete tasks and will drift slightly
  on re-run (documented behavior — see Week-0 verification handoff). Treat exact percentages as
  directional; re-verify before quoting in a final report.

---

## Validation Results (2026-07-25)

Final validation performed directly on the generated `data/analytical_dataset.csv`:

| Check                             | Result                                                                                                                                                                                                                                     |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Total data rows                   | 13,895 (matches `tasks_task` base count exactly)                                                                                                                                                                                           |
| Unique `task_id` values           | 13,895 (zero duplicates)                                                                                                                                                                                                                   |
| Rows with empty `task_id`         | 0                                                                                                                                                                                                                                          |
| Column count consistency          | 27/27 columns on every row, verified via CSV-aware parser (note: naive comma-splitting tools like `awk -F','` will misreport this due to correctly-quoted commas inside `task_name` — verified this is proper CSV quoting, not corruption) |
| `calculated_overdue` distribution | true: 3,422 / false: 4,815 / undetermined: 5,658                                                                                                                                                                                           |
| `undetermined` count cross-check  | Exact match to Category 2 data-quality finding (5,658 completed tasks missing `actual_end_date`)                                                                                                                                           |
| `department_source` distribution  | direct: 1,493 (10.74%) / position_derived: 12,402 (89.26%) — exact match to Week-0's original 89.26% null-direct-department finding                                                                                                        |

**Status: validated and ready for Phase 2 handoff.**
