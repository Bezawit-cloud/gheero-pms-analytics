-- ============================================================================
-- analytical_dataset.sql
-- Full extraction of the PMS overdue prediction analytical dataset.
-- Mirrors the logic in notebooks/clean_and_build_dataset.ipynb exactly.
--
-- Tables used (8 source tables + 5 junction/history tables):
--   tasks_task, basedata_position, tasks_task_history,
--   tasks_sub_task, tasks_sub_task_history,
--   tasks_task_challenge_groups,
--   tasks_cross_department_assignments,
--   tasks_major_activity, tasks_major_activity_history,
--   tasks_kpi, tasks_kpi_history,
--   tasks_sub_task_challenge_groups,
--   tasks_kpis_challegne_groups,
--   tasks_kpis_potential_challenge_groups,
--   comments_comment
-- ============================================================================

-- ── 1. Base Tasks with Target & Derived Features ──────────────────────────
WITH base AS (
    SELECT
        t.id,
        t.status,
        t.approval_status,
        t.lead_approval_status,
        t.weight_level,
        t.is_planned::int AS is_planned,
        t.risk_mapping,
        t.start_date,
        t.end_date,
        t.actual_end_date,
        t.created_date,
        t.updated_date,
        t.major_activity_id,
        t.created_by_id,
        t.position_id,
        t.department_id,
        CASE WHEN t.derived_from_cross_department_assignment_id IS NOT NULL THEN 1 ELSE 0 END AS is_cross_dept,

        -- Target
        CASE
            WHEN t.status = 'completed' AND t.actual_end_date > t.end_date THEN 1
            WHEN t.status NOT IN ('completed', 'terminated', 'archived')
                 AND t.end_date < CURRENT_DATE THEN 1
            ELSE 0
        END AS calculated_overdue,

        -- Derived features
        (t.end_date - t.start_date) AS planned_duration,
        (t.start_date - t.created_date) AS creation_to_planned_start,
        (CURRENT_DATE - t.updated_date::date) AS days_since_update,
        EXTRACT(DOW FROM t.created_date)::int AS created_dow,
        CASE WHEN EXTRACT(DOW FROM t.created_date)::int >= 5 THEN 1 ELSE 0 END AS created_is_weekend,
        CASE WHEN EXTRACT(DOW FROM t.created_date)::int = 4 THEN 1 ELSE 0 END AS created_is_friday,
        EXTRACT(MONTH FROM t.created_date)::int AS created_month,
        EXTRACT(QUARTER FROM t.created_date)::int AS created_quarter,

        -- Halfway date (for halfway-point features)
        t.start_date + (t.end_date - t.start_date) / 2 AS halfway_date

    FROM tasks_task t
    WHERE t.start_date IS NOT NULL AND t.end_date IS NOT NULL
),

-- ── 2. Revisions (tasks_task_history) ─────────────────────────────────────
revisions AS (
    SELECT
        history_relation_id AS task_id,
        COUNT(*) AS num_revisions,
        MAX(history_date) AS last_revision
    FROM tasks_task_history
    WHERE history_relation_id IS NOT NULL
    GROUP BY history_relation_id
),

-- ── 3. Subtasks (tasks_sub_task) ──────────────────────────────────────────
subtasks AS (
    SELECT
        task_id,
        COUNT(*) AS num_subtasks,
        SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS num_completed_subtasks,
        SUM(CASE WHEN is_overdue = TRUE THEN 1 ELSE 0 END) AS num_overdue_subtasks
    FROM tasks_sub_task
    WHERE task_id IS NOT NULL
    GROUP BY task_id
),

-- ── 3b. Subtask Completion at Halfway (tasks_sub_task_history) ────────────
task_halfway AS (
    SELECT id AS task_id, start_date + (end_date - start_date) / 2 AS halfway_date
    FROM tasks_task
    WHERE start_date IS NOT NULL AND end_date IS NOT NULL AND start_date <= end_date
),
latest_history AS (
    SELECT DISTINCT ON (sth.id)
        sth.id AS sub_task_id,
        sth.status AS status_at_halfway
    FROM tasks_sub_task_history sth
    JOIN tasks_sub_task st ON st.id = sth.id
    JOIN task_halfway th ON th.task_id = st.task_id
    WHERE sth.history_date <= th.halfway_date
    ORDER BY sth.id, sth.history_date DESC
),
halfway_sub AS (
    SELECT
        st.task_id,
        COUNT(*)::int AS num_subtasks_at_halfway,
        COUNT(*) FILTER (WHERE COALESCE(lh.status_at_halfway, st.status) = 'completed')::int
            AS num_completed_at_halfway
    FROM tasks_sub_task st
    JOIN task_halfway th ON th.task_id = st.task_id
    LEFT JOIN latest_history lh ON lh.sub_task_id = st.id
    WHERE st.created_date <= th.halfway_date
    GROUP BY st.task_id
),

-- ── 4. Challenges (tasks_task_challenge_groups) ───────────────────────────
challenges AS (
    SELECT
        tcg.task_id,
        COUNT(*) AS num_challenges
    FROM tasks_task_challenge_groups tcg
    WHERE tcg.task_id IS NOT NULL
    GROUP BY tcg.task_id
),

-- ── 5. Department Past Overdue Rate ───────────────────────────────────────
dept_agg AS (
    SELECT
        COALESCE(p.department_id, t.department_id) AS dept_id,
        COUNT(*) AS dept_task_count,
        AVG(CASE
            WHEN t.status = 'completed' AND t.actual_end_date > t.end_date THEN 1
            WHEN t.status NOT IN ('completed', 'terminated', 'archived') AND t.end_date < CURRENT_DATE THEN 1
            ELSE 0
        END) AS dept_past_overdue_rate,
        AVG(COALESCE(rev_cnt.num_revisions, 0)) AS dept_avg_revisions
    FROM tasks_task t
    LEFT JOIN basedata_position p ON p.id = t.position_id
    LEFT JOIN (
        SELECT history_relation_id AS task_id, COUNT(*) AS num_revisions
        FROM tasks_task_history WHERE history_relation_id IS NOT NULL GROUP BY history_relation_id
    ) rev_cnt ON rev_cnt.task_id = t.id
    GROUP BY COALESCE(p.department_id, t.department_id)
),

-- ── 6. Employee Past Overdue Rate ─────────────────────────────────────────
emp_agg AS (
    SELECT
        p.user_id AS assignee_id,
        AVG(CASE
            WHEN t.status = 'completed' AND t.actual_end_date > t.end_date THEN 1
            WHEN t.status NOT IN ('completed', 'terminated', 'archived') AND t.end_date < CURRENT_DATE THEN 1
            ELSE 0
        END) AS emp_past_overdue_rate
    FROM tasks_task t
    LEFT JOIN basedata_position p ON p.id = t.position_id
    WHERE p.user_id IS NOT NULL
    GROUP BY p.user_id
),

-- ── 7. Position Past Overdue Rate ─────────────────────────────────────────
pos_agg AS (
    SELECT
        t.position_id,
        AVG(CASE
            WHEN t.status = 'completed' AND t.actual_end_date > t.end_date THEN 1
            WHEN t.status NOT IN ('completed', 'terminated', 'archived') AND t.end_date < CURRENT_DATE THEN 1
            ELSE 0
        END) AS pos_past_overdue_rate
    FROM tasks_task t
    WHERE t.position_id IS NOT NULL
    GROUP BY t.position_id
),

-- ── 8. Cross-Department Pair Flag ─────────────────────────────────────────
cross_dept AS (
    SELECT t.id AS task_id, 1 AS cross_dept_pair_exists
    FROM tasks_task t
    JOIN tasks_cross_department_assignments cda ON cda.id = t.derived_from_cross_department_assignment_id
),

-- ── 9. Major Activity Info ────────────────────────────────────────────────
ma_info AS (
    SELECT
        ma.id AS major_activity_id,
        ma.status AS ma_status,
        ma.approval_status AS ma_approval_status,
        ma.kpi_id
    FROM tasks_major_activity ma
),

-- ── 10. MA Revisions ─────────────────────────────────────────────────────
ma_revisions AS (
    SELECT id AS major_activity_id, COUNT(*) AS num_ma_revisions
    FROM tasks_major_activity_history
    WHERE id IS NOT NULL
    GROUP BY id
),

-- ── 11. KPI Features ──────────────────────────────────────────────────────
kpi_features AS (
    SELECT
        kpi.id AS kpi_id,
        kpi.is_overdue::int AS kpi_is_overdue_flag,
        CASE kpi.status
            WHEN 'not_started' THEN 0 WHEN 'ongoing' THEN 1
            WHEN 'completed' THEN 2 WHEN 'terminated' THEN 3
            WHEN 'archived' THEN 4 ELSE 1
        END AS kpi_status_ordinal
    FROM tasks_kpi kpi
),

-- ── 12. KPI Revisions ────────────────────────────────────────────────────
kpi_hist AS (
    SELECT id AS kpi_id, COUNT(*) AS num_kpi_revisions
    FROM tasks_kpi_history
    WHERE id IS NOT NULL
    GROUP BY id
),

-- ── 13. Sub-Task Challenge Groups ─────────────────────────────────────────
sub_chal AS (
    SELECT stcg.subtask_id AS sub_task_id, st.task_id
    FROM tasks_sub_task_challenge_groups stcg
    JOIN tasks_sub_task st ON st.id = stcg.subtask_id
),
task_sub_chal AS (
    SELECT
        task_id,
        1 AS has_subtask_challenge,
        COUNT(*) AS num_subtask_challenges
    FROM sub_chal
    GROUP BY task_id
),

-- ── 14. KPI Challenge Groups ──────────────────────────────────────────────
kpi_chal AS (
    SELECT kpi_id, COUNT(*) AS num_kpi_challenges
    FROM tasks_kpis_challegne_groups
    GROUP BY kpi_id
),

-- ── 15. KPI Potential Challenge Groups ────────────────────────────────────
kpi_pot AS (
    SELECT kpi_id, COUNT(*) AS num_kpi_potential_challenges
    FROM tasks_kpis_potential_challenge_groups
    GROUP BY kpi_id
),

-- ── 16. Comments ──────────────────────────────────────────────────────────
kpi_cmt AS (
    SELECT object_id AS kpi_id, COUNT(*) AS kpi_comment_count
    FROM comments_comment WHERE content_type_id = 22
    GROUP BY object_id
),
ma_cmt AS (
    SELECT object_id AS major_activity_id, COUNT(*) AS ma_comment_count
    FROM comments_comment WHERE content_type_id = 23
    GROUP BY object_id
),
task_cmt AS (
    SELECT object_id AS task_id, COUNT(*) AS task_comment_count
    FROM comments_comment WHERE content_type_id = 24
    GROUP BY object_id
),

-- ── 17. Sub-Task Status Churn ─────────────────────────────────────────────
sub_hist AS (
    SELECT sth.id AS sub_task_id, COUNT(DISTINCT sth.status) AS num_status_changes
    FROM tasks_sub_task_history sth
    WHERE sth.id IS NOT NULL
    GROUP BY sth.id
),
task_sub_churn AS (
    SELECT st.task_id, AVG(sh.num_status_changes) AS avg_sub_status_changes
    FROM sub_hist sh
    JOIN tasks_sub_task st ON st.id = sh.sub_task_id
    WHERE st.task_id IS NOT NULL
    GROUP BY st.task_id
),

-- ── 18. Department Resolution ─────────────────────────────────────────────
position_dept AS (
    SELECT id AS position_id, department_id FROM basedata_position
)

-- ── Final SELECT ───────────────────────────────────────────────────────────
SELECT
    b.*,

    -- Revision features
    COALESCE(r.num_revisions, 0)::int AS num_revisions,
    COALESCE(r.num_revisions::float / NULLIF((CURRENT_DATE - b.created_date::date), 0), 0) AS revision_frequency,
    COALESCE((CURRENT_DATE - r.last_revision::date), 0) AS revision_recency,

    -- Subtask features
    COALESCE(s.num_subtasks, 0)::int AS num_subtasks,
    CASE WHEN COALESCE(s.num_subtasks, 0) > 0 THEN 1 ELSE 0 END AS has_subtasks,
    COALESCE(s.num_completed_subtasks::float / NULLIF(s.num_subtasks, 0), 0) AS subtask_completion_pct,
    COALESCE(s.num_overdue_subtasks::float / NULLIF(s.num_subtasks, 0), 0) AS subtask_overdue_rate,

    -- Subtask completion at halfway
    COALESCE(hs.num_completed_at_halfway::float / NULLIF(hs.num_subtasks_at_halfway, 0), 0) AS subtask_completion_pct_at_halfway,

    -- Challenge features
    COALESCE(ch.num_challenges, 0)::int AS num_challenges,
    CASE WHEN ch.num_challenges IS NOT NULL THEN 1 ELSE 0 END AS has_challenges,

    -- Department aggregates
    d.dept_past_overdue_rate,
    d.dept_avg_revisions,
    d.dept_task_count,

    -- Employee aggregate
    e.emp_past_overdue_rate,

    -- Position aggregate
    p.pos_past_overdue_rate,

    -- Cross-department pair flag
    COALESCE(cd.cross_dept_pair_exists, 0)::int AS cross_dept_pair_exists,

    -- MA info
    mai.ma_status,
    mai.ma_approval_status,

    -- MA revisions
    COALESCE(mar.num_ma_revisions, 0)::int AS num_ma_revisions,

    -- KPI features
    COALESCE(kpf.kpi_is_overdue_flag, 0)::int AS kpi_is_overdue_flag,
    COALESCE(kpf.kpi_status_ordinal, 1)::int AS kpi_status_ordinal,

    -- KPI revisions
    COALESCE(kph.num_kpi_revisions, 0)::int AS num_kpi_revisions,

    -- Sub-task challenges
    COALESCE(tsc.has_subtask_challenge, 0)::int AS has_subtask_challenge,
    COALESCE(tsc.num_subtask_challenges, 0)::int AS num_subtask_challenges,

    -- KPI challenges
    COALESCE(kc.num_kpi_challenges, 0)::int AS num_kpi_challenges,
    CASE WHEN kc.num_kpi_challenges IS NOT NULL THEN 1 ELSE 0 END AS has_kpi_challenge,

    -- KPI potential challenges
    COALESCE(kp.num_kpi_potential_challenges, 0)::int AS num_kpi_potential_challenges,
    CASE WHEN kp.num_kpi_potential_challenges IS NOT NULL THEN 1 ELSE 0 END AS has_kpi_potential_challenge,

    -- Comment counts
    COALESCE(kc2.kpi_comment_count, 0)::int AS kpi_comment_count,
    COALESCE(mc.ma_comment_count, 0)::int AS ma_comment_count,
    COALESCE(tc.task_comment_count, 0)::int AS task_comment_count,

    -- Sub-task status churn
    COALESCE(tsc2.avg_sub_status_changes, 0) AS avg_sub_status_changes,

    -- Department resolution
    COALESCE(pd.department_id, b.department_id) AS resolved_dept_id

FROM base b
LEFT JOIN revisions r ON r.task_id = b.id
LEFT JOIN subtasks s ON s.task_id = b.id
LEFT JOIN halfway_sub hs ON hs.task_id = b.id
LEFT JOIN challenges ch ON ch.task_id = b.id
LEFT JOIN dept_agg d ON d.dept_id = COALESCE(pd.department_id, b.department_id)
LEFT JOIN emp_agg e ON e.assignee_id = (SELECT p2.user_id FROM basedata_position p2 WHERE p2.id = b.position_id)
LEFT JOIN pos_agg p ON p.position_id = b.position_id
LEFT JOIN cross_dept cd ON cd.task_id = b.id
LEFT JOIN ma_info mai ON mai.major_activity_id = b.major_activity_id
LEFT JOIN ma_revisions mar ON mar.major_activity_id = b.major_activity_id
LEFT JOIN kpi_features kpf ON kpf.kpi_id = mai.kpi_id
LEFT JOIN kpi_hist kph ON kph.kpi_id = mai.kpi_id
LEFT JOIN task_sub_chal tsc ON tsc.task_id = b.id
LEFT JOIN kpi_chal kc ON kc.kpi_id = mai.kpi_id
LEFT JOIN kpi_pot kp ON kp.kpi_id = mai.kpi_id
LEFT JOIN kpi_cmt kc2 ON kc2.kpi_id = mai.kpi_id
LEFT JOIN ma_cmt mc ON mc.major_activity_id = b.major_activity_id
LEFT JOIN task_cmt tc ON tc.task_id = b.id
LEFT JOIN task_sub_churn tsc2 ON tsc2.task_id = b.id
LEFT JOIN position_dept pd ON pd.position_id = b.position_id

ORDER BY b.id;
