# Data Quality Findings — Phase 1 Handoff

All checks below were re-run live against `tasktracker_clone` on 2026-07-25, reusing the same
six categories and methodology established in Week-0's `sql/data_quality_checks.sql`. This is a
**re-verification for the group**, not new discovery — the goal is to confirm which Week-0
findings are still accurate today, catch anything that's drifted, and flag genuinely new
anomalies found in the process.

**Reminder on drift**: several of these checks depend on `CURRENT_DATE` (notably Category 1) and
will naturally produce slightly different numbers each day. Others (Categories 2, 3, 5, and most
of 6) are based on fixed historical data and should not drift at all — when one of those _did_
show a difference from Week-0, it's called out explicitly below as a real change, not noise.

---

## Category 1 — Overdue Consistency (stored `is_overdue` vs. calculated)

|                                          | Week-0 (original) | Handoff check (~1wk later) | Today (2026-07-25) |
| ---------------------------------------- | ----------------- | -------------------------- | ------------------ |
| Determinable tasks                       | 8,237             | 8,237                      | 8,237              |
| Disagreement rate                        | 23.88%            | 24.45%                     | **24.68%**         |
| Under-flagged (calc=overdue, stored=not) | 1,946             | 1,993                      | **2,012**          |
| Over-flagged (calc=not, stored=overdue)  | 21                | 21                         | **21**             |
| Ratio                                    | ~93:1             | ~94.9:1                    | **~96:1**          |

**Status: expected drift, mechanism fully understood.** The under-flagged count keeps climbing
because `calculated_overdue` depends on `CURRENT_DATE` for incomplete tasks — more tasks cross
their deadline each day. The over-flagged count is fixed because it only depends on the
`status = 'completed'` branch, which has no time dependency. Direction and magnitude are
consistent with the pattern first documented in the Week-0→Week-1 handoff.

**Business impact**: the stored `is_overdue` field should not be used as ground truth for
reporting or modeling. This has been the standing recommendation since Week-0 and remains
correct today.

---

## Category 2 — Invalid Dates

| Check                                                          | Count | Status                                                   |
| -------------------------------------------------------------- | ----- | -------------------------------------------------------- |
| `end_date < start_date`                                        | 2     | Matches Week-0 exactly                                   |
| `actual_end_date < actual_start_date`                          | 1     | **New check, not run in Week-0** — genuine data error    |
| `actual_end_date < start_date` (completed before task started) | 27    | **New check, not run in Week-0** — genuine anomaly       |
| Completed tasks missing `actual_end_date`                      | 5,658 | Matches Week-0 exactly (43.18% of completed tasks)       |
| Incomplete tasks with an `actual_end_date` already set         | 16    | **New check, not run in Week-0** — logical contradiction |

**Status: core finding stable; three new sub-checks surfaced small but real anomalies.**

**Recommended action**: the 2 known `end_date < start_date` rows should continue to be
excluded/flagged as already handled in feature engineering (`prediction_point_applicable`). The
3 new small findings (1, 27, and 16 rows respectively) are low-volume but logically impossible —
recommend flagging these specific `task_id`s for the group rather than silently dropping them,
since they may indicate a specific data-entry pattern worth understanding.

---

## Category 3 — Department Consistency

|                                                        | Result     |
| ------------------------------------------------------ | ---------- |
| Tasks with both direct and position-derived department | 1,404      |
| Disagreements                                          | 31 (2.21%) |

**Status: fully stable, exact match to Week-0.** This check does not depend on `CURRENT_DATE`
and shows zero drift, as expected. The "intentional cross-department" theory remains unsupported
by evidence (0 of these 31 disagreements carry the cross-department marker — consistent with
Week-0's original finding).

---

## Category 4 — Missing Assignments

| Check                               | Week-0          | Today           | Status                          |
| ----------------------------------- | --------------- | --------------- | ------------------------------- |
| Tasks without a position            | 664 (4.78%)     | 664 (4.78%)     | Stable, exact match             |
| Vacant positions                    | 29/114 (25.44%) | 29/114 (25.44%) | Stable, exact match             |
| Tasks assigned to deactivated users | ~486 (3.49%)    | **0**           | **Real drift, explained below** |

**On the deactivated-users discrepancy**: confirmed via direct query that all 4 currently
deactivated users hold **zero** positions in `basedata_position` right now — meaning the
`task → position → user` join chain can no longer reach them at all. This is not a query error
(the `is_active` column and join logic were independently verified). Most likely explanation:
position reassignment or vacancy changes occurred between Week-0 and now. Unlike Categories 2, 3,
and 5, this specific check is inherently time-sensitive (it reflects _current_ position/user
assignments, not fixed historical data) — future re-runs should expect this number to keep
changing and should not be treated as a fixed fact.

**Business impact confirmed unchanged**: as in Week-0, all of this category's risk is historical
debris — 0% of currently-active tasks are affected by any missing-assignment issue.

---

## Category 5 — Parent-Child Consistency

| Check                                   | Result           | Status                                       |
| --------------------------------------- | ---------------- | -------------------------------------------- |
| Completed tasks with sub-tasks          | 422              | Stable, exact match                          |
| ...of which have ≥1 incomplete sub-task | 138 (32.70%)     | Stable, exact match                          |
| Sub-task date-range violations          | 40/1,169 (3.42%) | Stable, exact match                          |
| ...of which are zero-overlap (severe)   | 32/40 (80%)      | **New refinement, not broken out in Week-0** |

**Status: fully stable, with one new severity insight.** The 32/40 zero-overlap breakdown is new
information — it shows that most sub-task date violations aren't minor overruns, they're
sub-tasks whose dates don't overlap with their parent task's timeline at all. Worth flagging to
whoever manages the PMS as a more actionable, higher-priority subset of this finding.

---

## Category 6 — Duplicate Records (from naive joins)

| Join type                                         | Week-0                 | Today                          | Status                       |
| ------------------------------------------------- | ---------------------- | ------------------------------ | ---------------------------- |
| Task → History (naive)                            | 32,441 rows (+133.47%) | 24,398 rows (raw table count)  | **Real anomaly — see below** |
| Task → Sub-task (naive, correct LEFT JOIN method) | +5.19%                 | +5.19% (14,616 vs 13,895 base) | Stable, exact match          |

**On the history table row-count drop — flagged, not resolved.** `tasks_task_history` currently
contains 24,398 rows, compared to Week-0's reported 32,441 — a drop of roughly 25%. History/audit
tables should only grow over time, never shrink, so this is a genuine anomaly rather than
expected drift. Verified independently via both a direct `SELECT COUNT(*)` on the table and a
join-based count (24,398 vs 24,388 — consistent with each other, ruling out a query error on our
end). Possible explanations: a database cleanup/maintenance operation, a partial data
restore/refresh between Week-0 and now, or the original Week-0 number needs re-checking against
its source. **This needs a direct question to whoever manages the live PMS/database** — it should
not be silently assumed to be either number's error.

**Note on methodology**: initial attempt at re-testing the sub-task inflation figure used an
`INNER JOIN`, which incorrectly excluded all tasks with zero sub-tasks and produced a misleading
result (1,169, exactly equal to total sub-task count). Corrected to a `LEFT JOIN` against the
full task base (13,895), which reproduced Week-0's +5.19% figure exactly. Documented here as a
reminder for `analytical_dataset.sql`: this exact join-type mistake would silently corrupt the
real dataset if it slipped into the extraction query unnoticed.

---

## Summary for the Group

| Category                    | Status                                                                                                                          |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| 1. Overdue consistency      | Drifting as expected, mechanism understood, no action needed beyond continuing to avoid stored `is_overdue` as ground truth     |
| 2. Invalid dates            | Core finding stable; 3 new small anomalies found, recommend flagging specific rows rather than dropping silently                |
| 3. Department consistency   | Fully stable                                                                                                                    |
| 4. Missing assignments      | Mostly stable; deactivated-user metric confirmed time-sensitive by nature, not a fixed fact                                     |
| 5. Parent-child consistency | Fully stable; new severity breakdown adds actionable detail                                                                     |
| 6. Duplicate records        | Sub-task inflation confirmed stable; **history table row-count anomaly needs follow-up with whoever manages the live database** |

**Action items flagged for the group / Gheero, not resolved in this document:**

1. Confirm why `tasks_task_history` has ~8,000 fewer rows than Week-0's original count.
2. Consider whether the 3 new small date-anomaly categories (1, 27, 16 rows) warrant their own
   exclusion/flag columns in the analytical dataset, or are rare enough to leave as-is.
