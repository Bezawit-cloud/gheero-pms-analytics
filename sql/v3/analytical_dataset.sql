-- ============================================================================
-- Analytical Dataset — PMS Overdue Prediction (Phase 1, Week 1)
-- One row per task. Built from verified, individually-tested CTEs.
-- See docs/handoff_H1.md for full schema documentation and column justifications.
-- See docs/handoff_H2.md for the relationship analysis this schema is based on.
-- ============================================================================

WITH department_resolution AS (
  SELECT
    t.id AS task_id,
    COALESCE(t.department_id, p.department_id) AS resolved_department_id,
    CASE WHEN t.department_id IS NOT NULL THEN 'direct' ELSE 'position_derived' END AS department_source
  FROM tasks_task t
  LEFT JOIN basedata_position p ON t.position_id = p.id
),

subtask_agg AS (
  SELECT
    task_id,
    COUNT(*) AS n_subtasks,
    COUNT(*) FILTER (WHERE status = 'completed') AS n_completed_subtasks,
    SUM(weight) AS total_subtask_weight,
    SUM(weight) FILTER (WHERE status = 'completed') AS completed_subtask_weight
  FROM tasks_sub_task
  GROUP BY task_id
),

history_agg AS (
  SELECT
    id AS task_id,
    COUNT(*) AS n_revisions
  FROM tasks_task_history
  GROUP BY id
),

ksi_goal_count AS (
  SELECT
    ma.id AS major_activity_id,
    COUNT(DISTINCT kg.goal_id) AS n_linked_goals
  FROM tasks_major_activity ma
  JOIN tasks_kpi kpi ON ma.kpi_id = kpi.id
  JOIN tasks_milestone m ON kpi.milestone_id = m.id
  JOIN tasks_ksi k ON m.ksi_id = k.id
  LEFT JOIN tasks_ksi_goals kg ON k.id = kg.ksi_id
  GROUP BY ma.id
)

SELECT
  -- Core / Identity
  t.id AS task_id,
  t.task_name,

  -- Department / Position / Employee
  dr.resolved_department_id AS department_id,
  dr.department_source,
  t.position_id,
  p.user_id AS employee_id,

  -- Dates & Status
  t.start_date AS planned_start_date,
  t.end_date AS planned_end_date,
  t.actual_start_date,
  t.actual_end_date,
  t.status,
  t.is_overdue,
  CASE
    WHEN t.status = 'completed' AND t.actual_end_date IS NULL THEN 'undetermined'
    WHEN t.status = 'completed' AND t.actual_end_date > t.end_date THEN 'true'
    WHEN t.status = 'completed' AND t.actual_end_date <= t.end_date THEN 'false'
    WHEN t.status != 'completed' AND t.end_date < CURRENT_DATE THEN 'true'
    WHEN t.status != 'completed' AND t.end_date >= CURRENT_DATE THEN 'false'
  END AS calculated_overdue,

  -- Direct Signals
  t.weight AS task_weight,
  t.weight_level,
  t.is_planned,

  -- Indirect Signals
  (t.derived_from_cross_department_assignment_id IS NOT NULL) AS has_cross_department_assignment,
  CASE
    WHEN kgc.n_linked_goals IS NULL THEN NULL
    WHEN kgc.n_linked_goals = 0 THEN '0'
    WHEN kgc.n_linked_goals = 1 THEN '1'
    ELSE '2+'
  END AS ksi_linked_goal_count,

  -- Sub-Task Completion (count + weight)
  COALESCE(sa.n_subtasks, 0) AS n_subtasks,
  COALESCE(sa.n_completed_subtasks, 0) AS n_completed_subtasks,
  CASE WHEN sa.n_subtasks > 0
       THEN ROUND(100.0 * sa.n_completed_subtasks / sa.n_subtasks, 2)
       ELSE NULL END AS subtask_completion_pct,
  sa.total_subtask_weight,
  sa.completed_subtask_weight,

  -- Traceability / History
  COALESCE(ha.n_revisions, 0) AS n_revisions,
  t.major_activity_id,
  t.created_date,
  t.updated_date

FROM tasks_task t
LEFT JOIN department_resolution dr ON dr.task_id = t.id
LEFT JOIN basedata_position p ON t.position_id = p.id
LEFT JOIN subtask_agg sa ON sa.task_id = t.id
LEFT JOIN history_agg ha ON ha.task_id = t.id
LEFT JOIN ksi_goal_count kgc ON kgc.major_activity_id = t.major_activity_id
ORDER BY t.id;