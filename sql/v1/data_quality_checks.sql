-- ============================================================================
-- data_quality_checks.sql
--
-- Validates data quality across source tables used in the analytical dataset.
-- Run against the tasktracker_clone PostgreSQL database.
--
-- Each check returns a row with: check_name, status (PASS/FAIL/WARN), detail
-- ============================================================================

-- ── 1. Row Count Checks ───────────────────────────────────────────────────
SELECT 'row_count_tasks_task' AS check_name,
       CASE WHEN cnt = 13895 THEN 'PASS' ELSE 'FAIL' END AS status,
       format('Expected 13895, got %s', cnt) AS detail
FROM (SELECT COUNT(*) AS cnt FROM tasks_task) t;

SELECT 'row_count_basedata_position' AS check_name,
       CASE WHEN cnt > 0 THEN 'PASS' ELSE 'FAIL' END AS status,
       format('Got %s rows', cnt) AS detail
FROM (SELECT COUNT(*) AS cnt FROM basedata_position) t;

-- ── 2. Null Rate Checks (critical columns) ───────────────────────────────
SELECT 'null_status' AS check_name,
       CASE WHEN null_pct = 0 THEN 'PASS' ELSE 'FAIL' END AS status,
       format('status is %.1f%% null', null_pct * 100) AS detail
FROM (SELECT COUNT(*) FILTER (WHERE status IS NULL)::float / COUNT(*) AS null_pct FROM tasks_task) t;

SELECT 'null_start_date' AS check_name,
       CASE WHEN null_pct = 0 THEN 'PASS' ELSE 'WARN' END AS status,
       format('start_date is %.1f%% null (%s rows)', null_pct * 100, null_count) AS detail
FROM (
    SELECT COUNT(*) FILTER (WHERE start_date IS NULL) AS null_count,
           COUNT(*) FILTER (WHERE start_date IS NULL)::float / COUNT(*) AS null_pct
    FROM tasks_task
) t;

SELECT 'null_end_date' AS check_name,
       CASE WHEN null_pct = 0 THEN 'PASS' ELSE 'WARN' END AS status,
       format('end_date is %.1f%% null (%s rows)', null_pct * 100, null_count) AS detail
FROM (
    SELECT COUNT(*) FILTER (WHERE end_date IS NULL) AS null_count,
           COUNT(*) FILTER (WHERE end_date IS NULL)::float / COUNT(*) AS null_pct
    FROM tasks_task
) t;

SELECT 'null_department_id' AS check_name,
       CASE WHEN null_pct < 10 THEN 'PASS' ELSE 'WARN' END AS status,
       format('department_id is %.1f%% null (resolved from position)', null_pct * 100) AS detail
FROM (
    SELECT COUNT(*) FILTER (WHERE department_id IS NULL AND position_id IS NULL)::float / COUNT(*) AS null_pct
    FROM tasks_task
) t;

SELECT 'null_actual_end_date_completed' AS check_name,
       CASE WHEN null_pct < 5 THEN 'PASS' ELSE 'WARN' END AS status,
       format('%.1f%% of completed tasks have null actual_end_date', null_pct * 100) AS detail
FROM (
    SELECT COUNT(*) FILTER (WHERE status = 'completed' AND actual_end_date IS NULL)::float
           / NULLIF(COUNT(*) FILTER (WHERE status = 'completed'), 0) AS null_pct
    FROM tasks_task
) t;

-- ── 3. Duplicate Checks ───────────────────────────────────────────────────
SELECT 'dup_task_id' AS check_name,
       CASE WHEN dup_count = 0 THEN 'PASS' ELSE 'FAIL' END AS status,
       format('Found %s duplicate task IDs', dup_count) AS detail
FROM (SELECT COUNT(*) - COUNT(DISTINCT id) AS dup_count FROM tasks_task) t;

SELECT 'dup_subtask_id' AS check_name,
       CASE WHEN dup_count = 0 THEN 'PASS' ELSE 'FAIL' END AS status,
       format('Found %s duplicate subtask IDs', dup_count) AS detail
FROM (SELECT COUNT(*) - COUNT(DISTINCT id) AS dup_count FROM tasks_sub_task) t;

-- ── 4. Referential Integrity ─────────────────────────────────────────────
SELECT 'orphan_task_history' AS check_name,
       CASE WHEN orphan_count = 0 THEN 'PASS' ELSE 'WARN' END AS status,
       format('%s history rows reference non-existent tasks', orphan_count) AS detail
FROM (
    SELECT COUNT(*) AS orphan_count
    FROM tasks_task_history th
    LEFT JOIN tasks_task t ON t.id = th.history_relation_id
    WHERE th.history_relation_id IS NOT NULL AND t.id IS NULL
) t;

SELECT 'orphan_subtasks' AS check_name,
       CASE WHEN orphan_count = 0 THEN 'PASS' ELSE 'WARN' END AS status,
       format('%s subtasks reference non-existent tasks', orphan_count) AS detail
FROM (
    SELECT COUNT(*) AS orphan_count
    FROM tasks_sub_task st
    LEFT JOIN tasks_task t ON t.id = st.task_id
    WHERE st.task_id IS NOT NULL AND t.id IS NULL
) t;

SELECT 'orphan_challenge_groups' AS check_name,
       CASE WHEN orphan_count = 0 THEN 'PASS' ELSE 'WARN' END AS status,
       format('%s challenge group entries reference non-existent tasks', orphan_count) AS detail
FROM (
    SELECT COUNT(*) AS orphan_count
    FROM tasks_task_challenge_groups tcg
    LEFT JOIN tasks_task t ON t.id = tcg.task_id
    WHERE tcg.task_id IS NOT NULL AND t.id IS NULL
) t;

-- ── 5. Value Range & Distribution Checks ──────────────────────────────────
SELECT 'invalid_dates' AS check_name,
       CASE WHEN bad_count = 0 THEN 'PASS' ELSE 'WARN' END AS status,
       format('%s tasks have end_date < start_date', bad_count) AS detail
FROM (
    SELECT COUNT(*) AS bad_count
    FROM tasks_task
    WHERE start_date IS NOT NULL AND end_date IS NOT NULL AND end_date < start_date
) t;

SELECT 'future_created_dates' AS check_name,
       CASE WHEN future_count = 0 THEN 'PASS' ELSE 'WARN' END AS status,
       format('%s tasks have created_date in the future', future_count) AS detail
FROM (
    SELECT COUNT(*) AS future_count
    FROM tasks_task
    WHERE created_date > CURRENT_TIMESTAMP
) t;

SELECT 'status_distribution' AS check_name,
       'INFO' AS status,
       string_agg(format('%s: %s', status, cnt), ', ') AS detail
FROM (SELECT status, COUNT(*)::text AS cnt FROM tasks_task GROUP BY status ORDER BY COUNT(*) DESC) t;

SELECT 'planned_duration_zero_or_negative' AS check_name,
       CASE WHEN bad_pct < 5 THEN 'PASS' ELSE 'WARN' END AS status,
       format('%.1f%% of tasks have planned_duration <= 0', bad_pct * 100) AS detail
FROM (
    SELECT COUNT(*) FILTER (WHERE end_date <= start_date)::float / COUNT(*) AS bad_pct
    FROM tasks_task
    WHERE start_date IS NOT NULL AND end_date IS NOT NULL
) t;

-- ── 6. History Table Audit ────────────────────────────────────────────────
SELECT 'task_history_entries' AS check_name,
       'INFO' AS status,
       format('%s total history rows across %s tasks', total_rows, tasks_with_history) AS detail
FROM (
    SELECT COUNT(*) AS total_rows,
           COUNT(DISTINCT history_relation_id) AS tasks_with_history
    FROM tasks_task_history
    WHERE history_relation_id IS NOT NULL
) t;

SELECT 'subtask_history_entries' AS check_name,
       'INFO' AS status,
       format('%s total history rows across %s subtasks', total_rows, subtasks_with_history) AS detail
FROM (
    SELECT COUNT(*) AS total_rows,
           COUNT(DISTINCT id) AS subtasks_with_history
    FROM tasks_sub_task_history
    WHERE id IS NOT NULL
) t;

-- ── 7. Content Type ID Verification ──────────────────────────────────────
SELECT 'comment_content_types' AS check_name,
       'INFO' AS status,
       string_agg(format('type_id=%s: %s rows', content_type_id, cnt), ', ') AS detail
FROM (SELECT content_type_id, COUNT(*)::text AS cnt FROM comments_comment GROUP BY content_type_id) t;

-- ── 8. Cross-Department Assignment ─────────────────────────────────────────
SELECT 'cross_dept_coverage' AS check_name,
       'INFO' AS status,
       format('%s tasks have cross-dept assignments (%s%%)', match_count, round(match_pct::numeric, 1)) AS detail
FROM (
    SELECT COUNT(*) FILTER (WHERE derived_from_cross_department_assignment_id IS NOT NULL) AS match_count,
           COUNT(*) FILTER (WHERE derived_from_cross_department_assignment_id IS NOT NULL)::float * 100 / COUNT(*) AS match_pct
    FROM tasks_task
) t;

-- ── 9. KPI Resolution ─────────────────────────────────────────────────────
SELECT 'kpi_resolution_rate' AS check_name,
       'INFO' AS status,
       format('%s tasks resolve to a KPI via MA chain (%s%%)', resolved, round(pct::numeric, 1)) AS detail
FROM (
    SELECT COUNT(*) FILTER (WHERE ma.kpi_id IS NOT NULL) AS resolved,
           COUNT(*) FILTER (WHERE ma.kpi_id IS NOT NULL)::float * 100 / COUNT(*) AS pct
    FROM tasks_task t
    LEFT JOIN tasks_major_activity ma ON ma.id = t.major_activity_id
) t;
