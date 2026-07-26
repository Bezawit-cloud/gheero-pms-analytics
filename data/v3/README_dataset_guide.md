# Understanding `analytical_dataset.csv`

A plain-language guide to what's in this file — for anyone on Phase 2 opening it for the
first time. For the technical reasoning behind these choices, see `docs/handoff_H1.md`.

**One row = one task.** 13,895 rows total, one row per task in the PMS system.

---

## Identity columns

| Column      | What it is                                                                |
| ----------- | ------------------------------------------------------------------------- |
| `task_id`   | Unique ID for the task. Never duplicated — every row has a different one. |
| `task_name` | The task's actual name/title, human-readable.                             |

## Who's responsible for the task

| Column              | What it is                                                                                                                                                                                                                                                              |
| ------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `department_id`     | Which department owns this task. Resolved automatically — see `department_source`.                                                                                                                                                                                      |
| `department_source` | Either `direct` (department was recorded directly on the task) or `position_derived` (we had to look up the department via the person's job position instead, since the direct field was empty). About 89% of tasks use the derived path — that's normal, not an error. |
| `position_id`       | The job position assigned to this task.                                                                                                                                                                                                                                 |
| `employee_id`       | The actual person (if resolvable) holding that position. Can be blank if the position is vacant.                                                                                                                                                                        |

## Dates

| Column               | What it is                                                     |
| -------------------- | -------------------------------------------------------------- |
| `planned_start_date` | When the task was supposed to start.                           |
| `planned_end_date`   | The deadline.                                                  |
| `actual_start_date`  | When work actually started. Often blank — see note below.      |
| `actual_end_date`    | When the task actually finished. Often blank — see note below. |
| `created_date`       | When the task was created in the system.                       |
| `updated_date`       | Last time anything about the task changed.                     |

**Important note on blanks**: `actual_start_date` and `actual_end_date` are frequently empty,
even for tasks marked "completed" — this isn't a mistake in the data, it's a real gap in how
the underlying system was used. About 5,658 completed tasks are missing their actual end date.
This is exactly why `calculated_overdue` (below) has an `undetermined` option instead of forcing
every task into true/false.

## Status & the target label (the thing we're trying to predict)

| Column               | What it is                                                                                                                                                                                                                                                                     |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `status`             | The task's current state: `not_started`, `on_review`, `ongoing`, `completed`, `archived`, or `terminated`.                                                                                                                                                                     |
| `is_overdue`         | A field that already exists in the original system. **Don't trust this one** — we proved it's wrong about 24% of the time. Kept only so you can compare it against the next column if curious.                                                                                 |
| `calculated_overdue` | **This is the real, trustworthy answer.** One of three values: `true` (was/is late), `false` (on time), or `undetermined` (we genuinely can't tell, usually because of the missing-date issue above). **Use this column, not `is_overdue`, for anything related to lateness.** |

## Task characteristics

| Column              | What it is                                                                                                                                                                                            |
| ------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `task_weight`       | A number representing how "heavy"/important the task is.                                                                                                                                              |
| `weight_level`      | The same idea, but as a simple category: `high`, `mid`, or `low`.                                                                                                                                     |
| `is_planned`        | `true` if the task was scheduled in advance, `false` if it was added on the fly. Unplanned tasks run late somewhat more often.                                                                        |
| `major_activity_id` | Which broader initiative this task belongs to. There are over 4,000 of these, most with very few tasks each — not very useful as a direct category, better rolled up into something bigger if needed. |

## The two strongest signals we found

| Column                            | What it is                                                                                                                                                                                    |
| --------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `has_cross_department_assignment` | `true` if this task is officially being worked across two departments. **This is the single strongest predictor we found** — these tasks run late nearly twice as often as normal.            |
| `ksi_linked_goal_count`           | How many strategic company goals this task's work ultimately connects up to: `0`, `1`, or `2+`. Tasks connected to zero goals run late notably less often than ones connected to one or more. |

## Sub-tasks

| Column                     | What it is                                                                                                                                   |
| -------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `n_subtasks`               | How many sub-tasks this task has. Often `0` — most tasks don't have any.                                                                     |
| `n_completed_subtasks`     | How many of those sub-tasks are finished.                                                                                                    |
| `subtask_completion_pct`   | Percent complete, by count. Blank (not zero) when there are no sub-tasks at all — don't treat blank as "0% done," it means "not applicable." |
| `total_subtask_weight`     | Sum of all sub-task weights (an alternative way to measure completion, by importance rather than raw count).                                 |
| `completed_subtask_weight` | Same, but only for the completed sub-tasks.                                                                                                  |

_We included both the count-based and weight-based versions on purpose — you can pick
whichever makes more sense once you start modeling, without needing to come back and ask us
for more data._

## History

| Column        | What it is                                                                 |
| ------------- | -------------------------------------------------------------------------- |
| `n_revisions` | How many times this task's record has been changed/revised since creation. |

---

## A few things worth knowing before you build features on this

1. **Don't use `actual_start_date` or `actual_end_date` directly as model inputs without
   thinking about timing.** These reflect what actually happened — using them without a proper
   "prediction point" cutoff would let your model cheat by peeking at the future. See
   `docs/handoff_H1.md` for the full explanation.
2. **`calculated_overdue` will look slightly different if you regenerate this file on a
   different day.** For tasks that are still ongoing, "overdue" depends on today's date — so
   the exact counts will drift a little day to day. This is expected, not a bug.
3. **We tested a bunch of other possible signals that turned out not to matter** (or were
   actively misleading) — task comments looked promising at first but turned out to be
   something people write _after_ a task is already late, not before, so we left that out
   entirely. Full details, including things we tested and rejected, are in `docs/handoff_H2.md`
   if you're curious.
