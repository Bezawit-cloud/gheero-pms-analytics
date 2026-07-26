# Table Relationship Analysis — Overdue Prediction

All queries were run live against `tasktracker_clone` (WSL Postgres instance) between 2026-07-23
and 2026-07-24, reusing the exact `calculated_overdue` CASE logic established in Week-0's
`sql/data_quality_checks.sql` Section 7.3:

```sql
CASE
  WHEN status = 'completed' AND actual_end_date IS NULL THEN 'undetermined'
  WHEN status = 'completed' AND actual_end_date > end_date THEN 'true'
  WHEN status = 'completed' AND actual_end_date <= end_date THEN 'false'
  WHEN status != 'completed' AND end_date < CURRENT_DATE THEN 'true'
  WHEN status != 'completed' AND end_date >= CURRENT_DATE THEN 'false'
END
```

**Note on drift**: this label is `CURRENT_DATE`-dependent for incomplete tasks — exact percentages
will shift slightly on re-run (documented behavior, see Week-0 verification handoff). The
*patterns* (which categories are higher/lower, and roughly by how much) are the stable,
reusable part of this analysis — treat exact decimals as directional, re-verify before quoting
in the final report.

Any group under ~30 tasks is flagged as too small to trust, per the standard applied throughout
Week-0 and this analysis.

---

## 1. Direct Relationships

### 1.1 Department (resolved: direct `department_id` with position fallback)
*(carried over from prior analysis — see original findings: 24 departments, 13.5%–46.2% spread,
strongest single categorical signal found)*

### 1.2 Position
*(carried over — 9.9%–48.0% spread among positions with 300+ tasks)*

### 1.3 Task Weight (bucketed, numeric)
*(carried over — non-monotonic, weak standalone signal, r=0.40 at best)*

### 1.4 Major Activity
*(carried over — 2%–55% swing among high-volume activities, but 4,296 distinct values, too
high-cardinality to use directly)*

### 1.5 Weight Level (categorical) — **NEW**
Join path: direct column, `tasks_task.weight_level`. No join required.

| weight_level | n_tasks | overdue_rate_pct |
|---|---|---|
| high | 5739 | 23.07 |
| mid | 5672 | 24.35 |
| low | 2484 | 28.10 |

All three buckets clear the sample-size threshold. Real, monotonic trend (higher weight → lower
overdue rate), though the spread is modest (~5 points). Cleaner and easier to interpret than the
raw numeric `weight` bucketing (1.3), which was non-monotonic and dominated by an
unweighted majority.

**Classification**: safe (available at prediction time — assigned at task creation).

**Business relevance**: weak but real; recommended as a replacement for raw weight bucketing,
not as a standalone strong feature.

### 1.6 Is Planned (direct boolean) — **NEW**
Join path: direct column, `tasks_task.is_planned`. No join required.

| is_planned | n_tasks | overdue_rate_pct |
|---|---|---|
| true | 11243 | 23.37 |
| false | 2652 | 29.26 |

Matches Week-0's org-wide planned/unplanned split exactly (11,243 / 2,652), confirming this
field is the direct source of that earlier metric. Real ~6-point gap, both groups well above
threshold.

**Classification**: safe (available at prediction time — set at task creation, not derived from
outcome).

**Business relevance**: moderate, real, cheap to include — unplanned tasks run meaningfully
later than planned ones.

### 1.7 Task Priority — **NEW (tested, does not exist)**
Checked full `tasks_task` schema (37 columns, via `information_schema.columns`). No
priority-related field exists on this table. Closed, not testable.

---

## 2. Indirect Relationships

### 2.1 KSI Linked-Goal Count
*(carried over — 0 goals: 19.51%, 1 goal: 31.64%, 2+ goals: 30.49% — real ~12pt gap, safe)*

### 2.2 Actual Cross-Department Assignment Record
*(carried over — 24.23% vs 43.62%, ~19pt gap, largest effect size found, empirically confirmed
safe: 188/188 tasks created at/after their assignment record)*

### 2.3 Task History Revision Types vs Raw Revision Count
*(carried over — "had status change" shows cleanest split: 56.94% vs 30.53%; leakage risk as
computed, fixable with the same `history_date <= prediction_date` pattern already proven for
`n_revisions_before_prediction`)*

### 2.4 Department Congestion (live snapshot)
*(carried over — counter-intuitive: low congestion 97.56%, medium 78.13%, high 30.95%; small,
fragile sample; needs more data before use)*

### 2.5 Sub-Task Completion Velocity
*(carried over — fast: 13.13%, medium: 16.88%, slow: 37.50% (under threshold); directionally
promising but only 1.4% coverage)*

### 2.6 KPI Direct Goal Bypass
*(carried over — 24.37% vs 27.15%, ~2.8pt gap, noise not signal)*

### 2.7 Employee-Level Active Workload — **NEW**
Join path: `tasks_task.position_id → basedata_position.user_id`, counting each employee's
other currently-active tasks (`status IN ('not_started', 'on_review', 'ongoing')`), restricted to
the 164 currently-active tasks (same scope restriction as 2.4, for the same reason — a live
snapshot can't be retroactively applied to finished tasks).

| workload_bucket | n_active_tasks | overdue_rate_pct |
|---|---|---|
| 1–3 (low) | 24 | 100.00 — under 30 tasks, borderline, do not fully trust |
| 4+ (high) | 123 | 64.23 |

147 of 164 active tasks resolved to an employee (17 excluded — same gap as 2.4's department
resolution). The high bucket clears the threshold; the low bucket doesn't quite. Direction
echoes 2.4 exactly: **lower workload associates with higher overdue rate**, not lower — the
same counter-intuitive pattern appearing at both the department and individual level. Plausible
explanation (not confirmed): tasks that are someone's *only* active task may be lower-priority,
easily-deprioritized items, while people carrying many tasks may be more experienced/senior
and better at meeting deadlines despite volume.

**Classification**: leakage risk as computed (live status snapshot) — same harder-to-fix family
as 2.4; a safe version would need historical active-set reconstruction, not a simple date filter.

**Business relevance**: genuine, repeating pattern across two independent tests (department and
individual level) — worth re-testing with more data before acting on it in either direction. Not
recommended as a production feature yet.

### 2.8 Task Comment Activity — **NEW, tested and rejected**
Join path: `tasks_task.id → comments_comment.object_id`, filtered to `content_type_id = 24`
(confirmed via `django_content_type` lookup: `24 = tasks.task`).

| comment_bucket | n_tasks | overdue_rate_pct |
|---|---|---|
| 0 (none) | 13837 | 24.35 |
| 1–3 | 58 | 58.62 |

Initially looked like the second-strongest finding in this entire analysis (~34pt gap, n=58
clears threshold). **Timing check performed before trusting this** (same method as 2.2's
empirical validation): compared each comment's `created_date` against its task's `end_date`.

| | count |
|---|---|
| Comments before deadline | 19 |
| Comments after deadline | 49 |

**72% of comments (49/68) occur after the task's deadline has already passed.** This is not a
predictive signal — it is the aftermath of lateness, not a cause of it (people commenting "what
happened here?" on tasks that are already overdue). Directly analogous to Week-0's
`actual_end_date` leakage trap.

**Classification**: leakage, confirmed empirically, not just suspected. A leakage-safe version
(filtering to `created_date <= prediction_date`) would only have 19 usable comments across the
*entire* 13,895-task dataset — far too sparse to be useful even if rebuilt safely.

**Business relevance**: none as a predictive feature. Valuable as a validated negative finding —
demonstrates a large apparent effect that was correctly identified and rejected as leakage
before contaminating the dataset.

### 2.9 KSI-Goal Approval Status — **NEW**
Join path: `tasks_task → tasks_major_activity → tasks_kpi → tasks_milestone → tasks_ksi →
tasks_ksi_goals`, reading `tasks_ksi_goals.approval_status`.

| approval_status | n_tasks | overdue_rate_pct |
|---|---|---|
| approved | 4949 | 31.50 |
| pending | 1007 | 29.20 |

5,956 tasks trace through to a KSI-goal link with a known approval status, both groups well
above threshold. Gap is only ~2.3 points — same "noise, not signal" range as 2.6.

**Classification**: safe (approval status set independent of task outcome), but not predictive.

**Business relevance**: minimal — not recommended as a standalone feature.

---

## 3. Relationships Tested but NOT Predictive

1. **Task weight (1.3)** — non-monotonic, weak at best (r=0.40); `weight_level` (1.5) is a
   cleaner substitute if a weight-related feature is wanted.
2. **KPI direct goal bypass (2.6)** — 2.78pt gap, smallest tested effect among safe relationships.
3. **KSI-goal approval status (2.9)** — 2.3pt gap, same order of magnitude as 2.6, real but
   negligible.
4. **Department congestion (2.4)** — not "no effect," the opposite: large but directionally
   surprising, small-sample-fragile. Needs more data, not more analysis, before acting on it.
5. **Employee workload (2.7)** — same caveat as 2.4, echoing the same surprising direction at
   the individual level. Two independent tests now show the same pattern — worth flagging to
   the group as a real open question, not dismissing as noise.
6. **Task comment activity (2.8)** — large apparent effect (~34pt), confirmed via timing check
   to be leakage (72% of comments post-date the deadline), not a genuine predictive signal.

---

## 4. Prediction-Time Availability Summary

| # | Relationship | Availability | Fixable with time cutoff? |
|---|---|---|---|
| 1.1 | Resolved department | Safe | n/a |
| 1.2 | Position | Safe | n/a |
| 1.3 | Task weight (numeric) | Safe (minor revisable-field caveat) | n/a |
| 1.4 | Major activity | Safe | n/a |
| 1.5 | Weight level | Safe | n/a |
| 1.6 | Is planned | Safe | n/a |
| 2.1 | KSI linked-goal count | Mostly safe | n/a |
| 2.2 | Cross-department assignment | Safe (empirically confirmed) | n/a |
| 2.3 | Task history revision types | Leakage as computed | Yes — reuse existing pattern |
| 2.4 | Department congestion (live) | Leakage as computed | Possible, harder |
| 2.5 | Sub-task completion velocity | Leakage as computed | Yes — reuse existing pattern |
| 2.6 | KPI direct goal bypass | Safe (not predictive) | n/a |
| 2.7 | Employee active workload | Leakage as computed | Possible, harder (same as 2.4) |
| 2.8 | Task comment activity | Leakage, confirmed — reject | Technically yes, but too sparse to matter |
| 2.9 | KSI-goal approval status | Safe (not predictive) | n/a |

**9 of 15 relationships tested are safe as computed; 4 are leakage risks with a known fix
pattern already proven in Week-0; 2 (department congestion, employee workload) are harder
leakage risks requiring historical reconstruction, not a simple cutoff.**

---

## 5. Recommendations for Feature Engineering (Handoff to Teammates)

1. **Highest priority, ready to use as-is**: `has_cross_department_assignment` (2.2) — largest
   effect size found (~19pts), safe today, minimal engineering.
2. **High priority, small lift**: `ksi_linked_goal_count` (2.1) — safe, ~12pt spread, join path
   already built.
3. **High priority, cheap and safe**: `is_planned` (1.6) and `weight_level` (1.5) — both direct
   columns, no joins needed, real (if modest) signal, zero leakage risk. These are the fastest,
   lowest-risk additions available.
4. **Medium priority, requires proven time-cutoff fix**: `had_status_change_before_prediction`
   (2.3) — cleaner signal than raw revision count; build the leakage-safe version and compare
   head-to-head against the existing `n_revisions_before_prediction`.
5. **Lower priority, same fix pattern, smaller payoff**: `subtask_velocity_before_prediction`
   (2.5) — only worth it if already extending sub-task features for other reasons.
6. **Needs more data before building — do not build yet**: department congestion (2.4) and
   employee workload (2.7). Both show a large, real, *repeating* counter-intuitive pattern across
   two independent tests — flag this explicitly to the group as a genuine open question worth
   revisiting once more active-task data accumulates, rather than a dead end.
7. **Do not build as standalone features**: task weight (1.3, superseded by 1.5), KPI direct
   goal bypass (2.6), KSI-goal approval status (2.9) — all tested with adequate sample size, all
   too small to be worth engineering time.
8. **Explicitly rejected — do not attempt to salvage**: task comment activity (2.8). Large
   apparent effect, confirmed via empirical timing check to be leakage (72% of comments
   post-date the task deadline). Even a leakage-safe rebuild would have unusably sparse coverage
   (19 comments across 13,895 tasks).
9. **Structural note for `major_activity_id`-based features (1.4)**: 4,296 distinct values, 95.9%
   under the 30-task threshold — aggregate via historical rate or roll up to KPI/department level,
   never one-hot encode directly.