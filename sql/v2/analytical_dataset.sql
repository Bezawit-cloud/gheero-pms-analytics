-- ============================================================
-- ML FEATURE TABLE v2
-- One row per task, at prediction_date = planned_start_date + 7 days.
-- Every dynamic/historical feature is paired with a "_has_history" flag
-- so the model can distinguish a real measurement from a cold-start fallback.
-- ============================================================

DROP TABLE IF EXISTS ml_feature_table_at_day_3;

CREATE TABLE ml_feature_table_at_day_3 AS
WITH base AS (
    SELECT
        a.task_id,
        a.department_id,
        a.position_id,
        a.major_activity_name,
        a.planned_start_date,
        a.planned_end_date,
        a.actual_start_date,
        a.actual_end_date,
        a.task_weight,
        a.planning_status,
        a.is_cross_department,
        a.calculated_overdue AS target,
        a.planned_start_date + 3 AS prediction_date  -- +7 (integer days), NOT INTERVAL '7 days'
                                                        -- adding an INTERVAL turns `date` into `timestamp`,
                                                        -- which breaks later date-minus-date arithmetic
    FROM analytical_task_dataset a
    WHERE a.planned_start_date IS NOT NULL
),
active_at_prediction AS (
    SELECT *
    FROM base
    WHERE actual_end_date IS NULL OR actual_end_date > prediction_date
),
subtask_snapshot AS (
    SELECT
        a.task_id,
        COUNT(*) FILTER (WHERE st.created_date <= a.prediction_date) AS num_subtasks,
        COUNT(*) FILTER (
            WHERE st.created_date <= a.prediction_date
              AND st.actual_end_date IS NOT NULL AND st.actual_end_date <= a.prediction_date
        ) AS num_completed_subtasks
    FROM active_at_prediction a
    LEFT JOIN tasks_sub_task st ON st.task_id = a.task_id
    GROUP BY a.task_id
),
revision_snapshot AS (
    SELECT h.id AS task_id, COUNT(*) AS num_revisions
    FROM tasks_task_history h
    JOIN active_at_prediction a ON a.task_id = h.id
    WHERE h.history_date <= a.prediction_date
    GROUP BY h.id
),
major_activity_weight AS (
    SELECT id, weight FROM tasks_major_activity
)
SELECT
    b.task_id,
    b.target,

    -- ---------- STATIC FEATURES ----------
    b.task_weight,
    (b.planned_end_date - b.planned_start_date)                        AS planned_task_duration_days,
    b.planning_status                                                   AS is_planned,
    b.is_cross_department,
    ma.weight                                                           AS major_activity_weight,

    -- ---------- TASK'S OWN PROGRESS (no cold-start risk) ----------
    -- Duration-relative instead of absolute -- fixes the zero-day-task
    -- collapse found in the first version of this feature table.
    CASE WHEN (b.planned_end_date - b.planned_start_date) > 0
         THEN LEAST(1.0, GREATEST(0.0,
                (b.prediction_date - b.planned_start_date)::numeric
                / (b.planned_end_date - b.planned_start_date)))
         ELSE 1.0  -- zero-day tasks: by the 7-day mark, planned window is already fully elapsed
    END                                                                  AS pct_of_planned_duration_elapsed,

    (b.planned_end_date - b.prediction_date)                            AS days_remaining_at_prediction,

    CASE
        WHEN b.actual_start_date IS NOT NULL AND b.actual_start_date <= b.prediction_date
            THEN (b.actual_start_date > b.planned_start_date)
        WHEN b.prediction_date > b.planned_start_date THEN TRUE
        ELSE FALSE
    END                                                                  AS started_late,

    COALESCE(ss.num_subtasks, 0)                                        AS num_subtasks_as_of_prediction,
    CASE WHEN COALESCE(ss.num_subtasks, 0) = 0 THEN NULL
         ELSE ROUND(100.0 * ss.num_completed_subtasks / ss.num_subtasks, 2)
    END                                                                  AS subtask_completion_pct_as_of_prediction,
    (COALESCE(ss.num_subtasks, 0) > 0)                                  AS has_subtasks_at_prediction,

    COALESCE(rs.num_revisions, 0)                                       AS num_revisions_before_prediction,

    -- ---------- POSITION HISTORY (cold-start risk -> fallback + flag) ----------
    COALESCE(
        (SELECT ROUND(AVG(CASE WHEN x.calculated_overdue THEN 1.0 ELSE 0.0 END), 3)
         FROM analytical_task_dataset x
         WHERE x.position_id = b.position_id
           AND x.task_id != b.task_id
           AND x.planned_end_date < b.prediction_date),
        (SELECT ROUND(AVG(CASE WHEN calculated_overdue THEN 1.0 ELSE 0.0 END), 3) FROM analytical_task_dataset)
    )                                                                    AS position_historical_overdue_rate,
    EXISTS (
        SELECT 1 FROM analytical_task_dataset x
        WHERE x.position_id = b.position_id AND x.task_id != b.task_id
          AND x.planned_end_date < b.prediction_date
    )                                                                    AS position_has_history,

    -- Current workload snapshot -- no cold-start risk, needs no prior history
    (SELECT COUNT(*) FROM analytical_task_dataset y
     WHERE y.position_id = b.position_id AND y.task_id != b.task_id
       AND y.planned_start_date <= b.prediction_date
       AND (y.actual_end_date IS NULL OR y.actual_end_date > b.prediction_date)
    )                                                                    AS employee_active_workload_at_prediction,

    -- ---------- DEPARTMENT HISTORY (cold-start risk -> fallback + flag) ----------
    COALESCE(
        (SELECT ROUND(AVG(CASE WHEN x.calculated_overdue THEN 1.0 ELSE 0.0 END), 3)
         FROM analytical_task_dataset x
         WHERE x.department_id = b.department_id
           AND x.task_id != b.task_id
           AND x.planned_end_date < b.prediction_date),
        (SELECT ROUND(AVG(CASE WHEN calculated_overdue THEN 1.0 ELSE 0.0 END), 3) FROM analytical_task_dataset)
    )                                                                    AS department_historical_overdue_rate,

    -- Rolling 30-day version: reacts to *current* department conditions,
    -- not lifetime average. Higher cold-start risk (narrower window), so
    -- also falls back to the lifetime rate, then to the org rate, if empty.
    COALESCE(
        (SELECT ROUND(AVG(CASE WHEN x.calculated_overdue THEN 1.0 ELSE 0.0 END), 3)
         FROM analytical_task_dataset x
         WHERE x.department_id = b.department_id
           AND x.task_id != b.task_id
           AND x.planned_end_date < b.prediction_date
           AND x.planned_end_date >= b.prediction_date - INTERVAL '30 days'),
        (SELECT ROUND(AVG(CASE WHEN x.calculated_overdue THEN 1.0 ELSE 0.0 END), 3)
         FROM analytical_task_dataset x
         WHERE x.department_id = b.department_id
           AND x.task_id != b.task_id
           AND x.planned_end_date < b.prediction_date),
        (SELECT ROUND(AVG(CASE WHEN calculated_overdue THEN 1.0 ELSE 0.0 END), 3) FROM analytical_task_dataset)
    )                                                                    AS department_recent_overdue_rate_30d,

    EXISTS (
        SELECT 1 FROM analytical_task_dataset x
        WHERE x.department_id = b.department_id AND x.task_id != b.task_id
          AND x.planned_end_date < b.prediction_date
    )                                                                    AS department_has_history

FROM active_at_prediction b
LEFT JOIN major_activity_weight ma ON ma.id = (
    SELECT major_activity_id FROM tasks_task WHERE id = b.task_id
)
LEFT JOIN subtask_snapshot ss ON ss.task_id = b.task_id
LEFT JOIN revision_snapshot rs ON rs.task_id = b.task_id;

SELECT COUNT(*) AS row_count FROM ml_feature_table_at_day_3;
SELECT COUNT(*) - COUNT(DISTINCT task_id) AS duplicate_check FROM ml_feature_table_at_day_3;
