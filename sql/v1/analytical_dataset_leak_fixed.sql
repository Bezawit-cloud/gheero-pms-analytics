-- ============================================================================
-- analytical_dataset_leak_fixed.sql
-- Cutoff-aware analytical dataset for PMS overdue prediction.
-- Mirrors build_features_leak_fixed.py exactly.
--
-- Every dynamic/historical feature is produced for both the creation cutoff
-- and the halfway cutoff, using a dual-column approach:
--   creation_cutoff = created_date
--   halfway_cutoff  = GREATEST(created_date, start_date + (end_date - start_date)/2)
--
-- Patterns demonstrated:
--   * COUNT(*) FILTER (WHERE ... <= cutoff)
--   * MAX/SUM FILTER (WHERE ... <= cutoff)
--   * DISTINCT ON with history lookup at each cutoff
--   * Expanding window aggregates (ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING)
--   * Three-tier target calculation for calculated_overdue
--
-- Tables used:
--   tasks_task, tasks_task_history,
--   tasks_sub_task, tasks_sub_task_history,
--   tasks_major_activity, tasks_major_activity_history,
--   tasks_kpi, tasks_kpi_history,
--   tasks_cross_department_assignments,
--   comments_comment, basedata_position
-- ============================================================================

WITH
-- ── 1. BASE ──────────────────────────────────────────────────────────────────
-- Base tasks with dual cutoff columns and derived temporal features.
base AS (
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

        -- Derived features (static — same value at both cutoffs)
        (t.end_date - t.start_date) AS planned_duration,
        (t.start_date - t.created_date) AS creation_to_planned_start,
        EXTRACT(DOW FROM t.created_date)::int AS created_dow,
        CASE WHEN EXTRACT(DOW FROM t.created_date)::int >= 5 THEN 1 ELSE 0 END AS created_is_weekend,
        CASE WHEN EXTRACT(DOW FROM t.created_date)::int = 4 THEN 1 ELSE 0 END AS created_is_friday,
        EXTRACT(MONTH FROM t.created_date)::int AS created_month,
        EXTRACT(QUARTER FROM t.created_date)::int AS created_quarter,
        ('2026-07-14'::date - t.updated_date::date) AS days_since_update_halfway,

        -- Dual cutoff columns
        t.created_date AS creation_cutoff,
        GREATEST(t.created_date, t.start_date + (t.end_date - t.start_date) / 2) AS halfway_cutoff

    FROM tasks_task t
    WHERE t.start_date IS NOT NULL AND t.end_date IS NOT NULL
),

-- ── 2. FIRST COMPLETED ───────────────────────────────────────────────────────
-- Earliest history timestamp where the task was marked completed.
-- Used in the three-tier target calculation.
first_completed AS (
    SELECT
        th.history_relation_id AS task_id,
        MIN(th.history_date)::date AS first_completed_at
    FROM tasks_task_history th
    WHERE th.status = 'completed'
    GROUP BY th.history_relation_id
),

-- ── 3. REVISIONS ─────────────────────────────────────────────────────────────
-- Task revision counts and last revision timestamp at each cutoff.
revisions AS (
    SELECT
        th.history_relation_id AS task_id,
        COUNT(*) FILTER (WHERE th.history_date <= b.creation_cutoff) AS num_revisions_at_creation,
        COUNT(*) FILTER (WHERE th.history_date <= b.halfway_cutoff) AS num_revisions_at_halfway,
        MAX(th.history_date) FILTER (WHERE th.history_date <= b.creation_cutoff) AS last_revision_at_creation,
        MAX(th.history_date) FILTER (WHERE th.history_date <= b.halfway_cutoff) AS last_revision_at_halfway
    FROM tasks_task_history th
    JOIN base b ON b.id = th.history_relation_id
    GROUP BY th.history_relation_id
),

-- ── 4. SUBTASKS ──────────────────────────────────────────────────────────────
-- Subtask counts, completion, and overdue at each cutoff.
subtasks AS (
    SELECT
        st.task_id,
        COUNT(*) FILTER (WHERE st.created_date <= b.creation_cutoff) AS num_subtasks_at_creation,
        COUNT(*) FILTER (WHERE st.created_date <= b.halfway_cutoff) AS num_subtasks_at_halfway,
        COUNT(*) FILTER (WHERE st.status = 'completed' AND st.created_date <= b.creation_cutoff) AS num_completed_at_creation,
        COUNT(*) FILTER (WHERE st.status = 'completed' AND st.created_date <= b.halfway_cutoff) AS num_completed_at_halfway,
        COUNT(*) FILTER (WHERE st.is_overdue = TRUE AND st.created_date <= b.creation_cutoff) AS num_overdue_at_creation,
        COUNT(*) FILTER (WHERE st.is_overdue = TRUE AND st.created_date <= b.halfway_cutoff) AS num_overdue_at_halfway
    FROM tasks_sub_task st
    JOIN base b ON b.id = st.task_id
    GROUP BY st.task_id
),

-- ── 5. TASK STATUS AT CREATION ──────────────────────────────────────────────
-- Snapshot of status, approval_status, lead_approval_status at creation cutoff
-- using DISTINCT ON with history_date DESC.
task_status_at_creation AS (
    SELECT DISTINCT ON (th.history_relation_id)
        th.history_relation_id AS task_id,
        th.status AS status_at_creation_val,
        th.approval_status AS approval_status_at_creation_val,
        th.lead_approval_status AS lead_approval_status_at_creation_val
    FROM tasks_task_history th
    JOIN base b ON b.id = th.history_relation_id
    WHERE th.history_date <= b.creation_cutoff
    ORDER BY th.history_relation_id, th.history_date DESC
),

-- ── 6. TASK STATUS AT HALFWAY ───────────────────────────────────────────────
-- Snapshot of status, approval_status, lead_approval_status at halfway cutoff.
task_status_at_halfway AS (
    SELECT DISTINCT ON (th.history_relation_id)
        th.history_relation_id AS task_id,
        th.status AS status_at_halfway_val,
        th.approval_status AS approval_status_at_halfway_val,
        th.lead_approval_status AS lead_approval_status_at_halfway_val
    FROM tasks_task_history th
    JOIN base b ON b.id = th.history_relation_id
    WHERE th.history_date <= b.halfway_cutoff
    ORDER BY th.history_relation_id, th.history_date DESC
),

-- ── 7. DEPARTMENT AGGREGATES (expanding window) ──────────────────────────────
-- Past overdue rate and avg revisions per department, computed using an
-- expanding window that excludes the current row to prevent data leakage.
dept_agg_raw AS (
    SELECT
        t.id,
        COALESCE(p.department_id, t.department_id) AS dept_id,
        t.created_date,
        CASE
            WHEN t.status = 'completed' AND t.actual_end_date IS NOT NULL AND t.actual_end_date > t.end_date THEN 1
            WHEN t.status = 'completed' AND t.actual_end_date IS NULL AND t.updated_date::date > t.end_date THEN 1
            WHEN t.status NOT IN ('completed', 'terminated', 'archived') AND t.end_date < '2026-07-14'::date THEN 1
            ELSE 0
        END AS is_overdue,
        COALESCE(rc.num_revisions, 0) AS rev_count
    FROM tasks_task t
    LEFT JOIN basedata_position p ON p.id = t.position_id
    LEFT JOIN (
        SELECT history_relation_id AS task_id, COUNT(*) AS num_revisions
        FROM tasks_task_history WHERE history_relation_id IS NOT NULL
        GROUP BY history_relation_id
    ) rc ON rc.task_id = t.id
    WHERE t.start_date IS NOT NULL AND t.end_date IS NOT NULL
),
dept_agg AS (
    SELECT
        id,
        AVG(is_overdue) OVER (
            PARTITION BY dept_id ORDER BY created_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
        ) AS dept_past_overdue_rate,
        AVG(rev_count) OVER (
            PARTITION BY dept_id ORDER BY created_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
        ) AS dept_avg_revisions
    FROM dept_agg_raw
),

-- ── 8. EMPLOYEE AGGREGATES (expanding window) ───────────────────────────────
emp_agg_raw AS (
    SELECT
        t.id,
        p.user_id AS assignee_id,
        t.created_date,
        CASE
            WHEN t.status = 'completed' AND t.actual_end_date IS NOT NULL AND t.actual_end_date > t.end_date THEN 1
            WHEN t.status = 'completed' AND t.actual_end_date IS NULL AND t.updated_date::date > t.end_date THEN 1
            WHEN t.status NOT IN ('completed', 'terminated', 'archived') AND t.end_date < '2026-07-14'::date THEN 1
            ELSE 0
        END AS is_overdue
    FROM tasks_task t
    LEFT JOIN basedata_position p ON p.id = t.position_id
    WHERE t.start_date IS NOT NULL AND t.end_date IS NOT NULL AND p.user_id IS NOT NULL
),
emp_agg AS (
    SELECT
        id,
        AVG(is_overdue) OVER (
            PARTITION BY assignee_id ORDER BY created_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
        ) AS emp_past_overdue_rate
    FROM emp_agg_raw
),

-- ── 9. POSITION AGGREGATES (expanding window) ───────────────────────────────
pos_agg_raw AS (
    SELECT
        t.id,
        t.position_id,
        t.created_date,
        CASE
            WHEN t.status = 'completed' AND t.actual_end_date IS NOT NULL AND t.actual_end_date > t.end_date THEN 1
            WHEN t.status = 'completed' AND t.actual_end_date IS NULL AND t.updated_date::date > t.end_date THEN 1
            WHEN t.status NOT IN ('completed', 'terminated', 'archived') AND t.end_date < '2026-07-14'::date THEN 1
            ELSE 0
        END AS is_overdue
    FROM tasks_task t
    WHERE t.start_date IS NOT NULL AND t.end_date IS NOT NULL AND t.position_id IS NOT NULL
),
pos_agg AS (
    SELECT
        id,
        AVG(is_overdue) OVER (
            PARTITION BY position_id ORDER BY created_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
        ) AS pos_past_overdue_rate
    FROM pos_agg_raw
),

-- ── 10. MA INFO ──────────────────────────────────────────────────────────────
ma_info AS (
    SELECT
        ma.id AS major_activity_id,
        ma.status AS ma_status,
        ma.approval_status AS ma_approval_status,
        ma.kpi_id
    FROM tasks_major_activity ma
),

-- ── 11. MA REVISIONS (cutoff-aware) ──────────────────────────────────────────
ma_revisions AS (
    SELECT
        mah.id AS major_activity_id,
        COUNT(*) FILTER (WHERE mah.history_date <= b.creation_cutoff) AS num_ma_revisions_at_creation,
        COUNT(*) FILTER (WHERE mah.history_date <= b.halfway_cutoff) AS num_ma_revisions_at_halfway
    FROM tasks_major_activity_history mah
    JOIN base b ON b.major_activity_id = mah.id
    GROUP BY mah.id
),

-- ── 12. KPI REVISIONS (cutoff-aware) ─────────────────────────────────────────
kpi_revisions AS (
    SELECT
        kh.id AS kpi_id,
        COUNT(*) FILTER (WHERE kh.history_date <= b.creation_cutoff) AS num_kpi_revisions_at_creation,
        COUNT(*) FILTER (WHERE kh.history_date <= b.halfway_cutoff) AS num_kpi_revisions_at_halfway
    FROM tasks_kpi_history kh
    JOIN tasks_kpi kpi ON kpi.id = kh.id
    JOIN tasks_major_activity ma ON ma.kpi_id = kpi.id
    JOIN base b ON b.major_activity_id = ma.id
    GROUP BY kh.id
),

-- ── 13. KPI STATUS LOOKUP AT CREATION ────────────────────────────────────────
-- DISTINCT ON history lookup to get KPI state at creation cutoff.
kpi_features_at_creation AS (
    SELECT DISTINCT ON (kh.id)
        kh.id AS kpi_id,
        kh.is_overdue::int AS kpi_is_overdue_flag_at_creation,
        kh.status AS kpi_status_at_creation
    FROM tasks_kpi_history kh
    JOIN tasks_kpi kpi ON kpi.id = kh.id
    JOIN tasks_major_activity ma ON ma.kpi_id = kpi.id
    JOIN base b ON b.major_activity_id = ma.id
    WHERE kh.history_date <= b.creation_cutoff
    ORDER BY kh.id, kh.history_date DESC
),

-- ── 14. KPI STATUS LOOKUP AT HALFWAY ─────────────────────────────────────────
kpi_features_at_halfway AS (
    SELECT DISTINCT ON (kh.id)
        kh.id AS kpi_id,
        kh.is_overdue::int AS kpi_is_overdue_flag_at_halfway,
        kh.status AS kpi_status_at_halfway
    FROM tasks_kpi_history kh
    JOIN tasks_kpi kpi ON kpi.id = kh.id
    JOIN tasks_major_activity ma ON ma.kpi_id = kpi.id
    JOIN base b ON b.major_activity_id = ma.id
    WHERE kh.history_date <= b.halfway_cutoff
    ORDER BY kh.id, kh.history_date DESC
),

-- ── 15. COMMENTS ON TASKS (cutoff-aware) ────────────────────────────────────
comments_task AS (
    SELECT
        cc.object_id AS task_id,
        COUNT(*) FILTER (WHERE cc.created_date <= b.creation_cutoff) AS task_comment_count_at_creation,
        COUNT(*) FILTER (WHERE cc.created_date <= b.halfway_cutoff) AS task_comment_count_at_halfway
    FROM comments_comment cc
    JOIN base b ON b.id = cc.object_id
    WHERE cc.content_type_id = 24
    GROUP BY cc.object_id
),

-- ── 16. COMMENTS ON MA (creation cutoff only, aliased as kpi_comment) ────────
comments_kpi AS (
    SELECT
        cc.object_id AS major_activity_id,
        COUNT(*) FILTER (WHERE cc.created_date <= b.creation_cutoff) AS kpi_comment_count_at_creation
    FROM comments_comment cc
    JOIN base b ON b.major_activity_id = cc.object_id
    WHERE cc.content_type_id = 23
    GROUP BY cc.object_id
),

-- ── 17. SUB-TASK STATUS CHURN (cutoff-aware) ────────────────────────────────
-- Per sub-task: count of distinct status values at each cutoff.
-- Then averaged per parent task.
sub_hist AS (
    SELECT
        sth.id AS sub_task_id,
        COUNT(DISTINCT sth.status) FILTER (WHERE sth.history_date <= b.creation_cutoff) AS num_status_changes_at_creation,
        COUNT(DISTINCT sth.status) FILTER (WHERE sth.history_date <= b.halfway_cutoff) AS num_status_changes_at_halfway
    FROM tasks_sub_task_history sth
    JOIN tasks_sub_task st ON st.id = sth.id
    JOIN base b ON b.id = st.task_id
    GROUP BY sth.id
),
task_sub_churn AS (
    SELECT
        st.task_id,
        AVG(sh.num_status_changes_at_creation) AS avg_sub_status_changes_at_creation,
        AVG(sh.num_status_changes_at_halfway) AS avg_sub_status_changes_at_halfway
    FROM sub_hist sh
    JOIN tasks_sub_task st ON st.id = sh.sub_task_id
    GROUP BY st.task_id
),

-- ── 18. CROSS-DEPARTMENT PAIR FLAG ──────────────────────────────────────────
cross_dept AS (
    SELECT t.id AS task_id, 1 AS cross_dept_pair_exists
    FROM tasks_task t
    JOIN tasks_cross_department_assignments cda ON cda.id = t.derived_from_cross_department_assignment_id
),

-- ── 19. POSITION-TO-DEPARTMENT RESOLUTION ────────────────────────────────────
position_dept AS (
    SELECT id AS position_id, department_id FROM basedata_position
)

-- ══════════════════════════════════════════════════════════════════════════════
-- FINAL SELECT
-- ══════════════════════════════════════════════════════════════════════════════
SELECT
    -- ── Identity ─────────────────────────────────────────────────────────────
    b.id,

    -- ── TARGET: Three-tier overdue logic ─────────────────────────────────────
    -- Tier 1: actual_end_date exists → compare to end_date
    -- Tier 2: no actual_end_date, but first_completed_at exists → use that
    -- Tier 3: no actual_end_date, no history → use updated_date
    CASE
        WHEN b.status = 'completed' AND b.actual_end_date IS NOT NULL
             AND b.actual_end_date > b.end_date THEN 1
        WHEN b.status = 'completed' AND b.actual_end_date IS NULL
             AND fc.first_completed_at IS NOT NULL
             AND fc.first_completed_at > b.end_date THEN 1
        WHEN b.status = 'completed' AND b.actual_end_date IS NULL
             AND fc.first_completed_at IS NULL
             AND b.updated_date::date > b.end_date THEN 1
        WHEN b.status NOT IN ('completed', 'terminated', 'archived')
             AND b.end_date < '2026-07-14'::date THEN 1
        ELSE 0
    END AS calculated_overdue,

    -- Target source: explains which tier was used
    CASE
        WHEN b.status = 'completed' AND b.actual_end_date IS NOT NULL THEN 'actual_end_date'
        WHEN b.status = 'completed' AND b.actual_end_date IS NULL
             AND fc.first_completed_at IS NOT NULL THEN 'history_completion'
        WHEN b.status = 'completed' AND b.actual_end_date IS NULL THEN 'updated_date'
        WHEN b.status NOT IN ('completed', 'terminated', 'archived')
             AND b.end_date < '2026-07-14'::date THEN 'open_task'
        ELSE 'status_based'
    END AS target_source,

    -- ── Static features (no cutoff suffix — identical for both prediction
    --    points) ─────────────────────────────────────────────────────────────
    b.planned_duration,
    b.creation_to_planned_start,
    b.created_dow,
    b.created_is_weekend,
    b.created_is_friday,
    b.created_month,
    b.created_quarter,
    b.is_planned,
    b.risk_mapping,
    b.is_cross_dept,
    COALESCE(cd.cross_dept_pair_exists, 0)::int AS cross_dept_pair_exists,

    -- Days since update is halfway-only in the pipeline
    b.days_since_update_halfway,

    -- ── Expanding window aggregates (static — no cutoff needed) ─────────────
    d.dept_past_overdue_rate,
    d.dept_avg_revisions,
    e.emp_past_overdue_rate,
    p.pos_past_overdue_rate,

    -- Resolved department id
    COALESCE(pd.department_id, b.department_id) AS resolved_dept_id,

    -- ── CREATION-CUTOFF features ────────────────────────────────────────────

    -- Status encoded at creation (fallback to current value)
    CASE
        WHEN tsc.status_at_creation_val IS NOT NULL
            THEN CASE tsc.status_at_creation_val
                WHEN 'not_started' THEN 0 WHEN 'ongoing' THEN 1
                WHEN 'in_progress' THEN 1 WHEN 'completed' THEN 2
                WHEN 'terminated' THEN 3 WHEN 'archived' THEN 4
                ELSE 1 END
        ELSE CASE b.status
            WHEN 'not_started' THEN 0 WHEN 'ongoing' THEN 1
            WHEN 'in_progress' THEN 1 WHEN 'completed' THEN 2
            WHEN 'terminated' THEN 3 WHEN 'archived' THEN 4
            ELSE 1 END
    END AS status_encoded_at_creation,

    CASE
        WHEN tsc.approval_status_at_creation_val IS NOT NULL
            THEN CASE tsc.approval_status_at_creation_val
                WHEN 'pending' THEN 0 WHEN 'in_review' THEN 1
                WHEN 'approved' THEN 2 WHEN 'rejected' THEN 3
                ELSE 1 END
        ELSE CASE b.approval_status
            WHEN 'pending' THEN 0 WHEN 'in_review' THEN 1
            WHEN 'approved' THEN 2 WHEN 'rejected' THEN 3
            ELSE 1 END
    END AS approval_status_encoded_at_creation,

    CASE
        WHEN tsc.lead_approval_status_at_creation_val IS NOT NULL
            THEN CASE tsc.lead_approval_status_at_creation_val
                WHEN 'pending' THEN 0 WHEN 'in_review' THEN 1
                WHEN 'approved' THEN 2 WHEN 'rejected' THEN 3
                ELSE 1 END
        ELSE CASE b.lead_approval_status
            WHEN 'pending' THEN 0 WHEN 'in_review' THEN 1
            WHEN 'approved' THEN 2 WHEN 'rejected' THEN 3
            ELSE 1 END
    END AS lead_approval_status_encoded_at_creation,

    -- MA status at creation (static, same value duplicated)
    CASE ma.ma_status
        WHEN 'not_started' THEN 0 WHEN 'ongoing' THEN 1
        WHEN 'completed' THEN 2 WHEN 'terminated' THEN 3
        ELSE 1
    END AS ma_status_encoded_at_creation,

    CASE ma.ma_approval_status
        WHEN 'pending' THEN 0 WHEN 'in_review' THEN 1
        WHEN 'approved' THEN 2 WHEN 'rejected' THEN 3
        ELSE 1
    END AS ma_approval_status_encoded_at_creation,

    -- MA revisions
    COALESCE(mar.num_ma_revisions_at_creation, 0)::int AS num_ma_revisions_at_creation,

    -- KPI features at creation
    COALESCE(kfc.kpi_is_overdue_flag_at_creation, 0)::int AS kpi_is_overdue_flag_at_creation,
    CASE
        WHEN kfc.kpi_status_at_creation IS NOT NULL
            THEN CASE kfc.kpi_status_at_creation
                WHEN 'not_started' THEN 0 WHEN 'ongoing' THEN 1
                WHEN 'completed' THEN 2 WHEN 'terminated' THEN 3
                WHEN 'archived' THEN 4 ELSE 1 END
        ELSE 1
    END AS kpi_status_ordinal_at_creation,

    -- KPI revisions
    COALESCE(kr.num_kpi_revisions_at_creation, 0)::int AS num_kpi_revisions_at_creation,

    -- KPI comment count (creation only)
    COALESCE(ck.kpi_comment_count_at_creation, 0)::int AS kpi_comment_count_at_creation,

    -- Task revisions at creation
    COALESCE(r.num_revisions_at_creation, 0)::int AS num_revisions_at_creation,
    CASE
        WHEN b.planned_duration > 0
            THEN COALESCE(r.num_revisions_at_creation::numeric / NULLIF(b.planned_duration, 0), 0)
        ELSE 0
    END AS revision_frequency_at_creation,
    CASE
        WHEN r.last_revision_at_creation IS NOT NULL
            THEN ('2026-07-14'::date - r.last_revision_at_creation::date)
        ELSE 0
    END AS revision_recency_at_creation,

    -- Subtasks at creation
    COALESCE(s.num_subtasks_at_creation, 0)::int AS num_subtasks_at_creation,
    CASE WHEN COALESCE(s.num_subtasks_at_creation, 0) > 0 THEN 1 ELSE 0 END AS has_subtasks_at_creation,
    CASE
        WHEN COALESCE(s.num_subtasks_at_creation, 0) > 0
            THEN COALESCE(s.num_completed_at_creation::numeric / NULLIF(s.num_subtasks_at_creation, 0), 0)
        ELSE 0
    END AS subtask_completion_pct_at_creation,
    CASE
        WHEN COALESCE(s.num_subtasks_at_creation, 0) > 0
            THEN COALESCE(s.num_overdue_at_creation::numeric / NULLIF(s.num_subtasks_at_creation, 0), 0)
        ELSE 0
    END AS subtask_overdue_rate_at_creation,

    -- Task comments at creation
    COALESCE(ct.task_comment_count_at_creation, 0)::int AS task_comment_count_at_creation,

    -- Sub-task status churn at creation
    COALESCE(tsc2.avg_sub_status_changes_at_creation, 0) AS avg_sub_status_changes_at_creation,

    -- ── HALFWAY-CUTOFF features ─────────────────────────────────────────────

    -- Status encoded at halfway
    CASE
        WHEN tsh.status_at_halfway_val IS NOT NULL
            THEN CASE tsh.status_at_halfway_val
                WHEN 'not_started' THEN 0 WHEN 'ongoing' THEN 1
                WHEN 'in_progress' THEN 1 WHEN 'completed' THEN 2
                WHEN 'terminated' THEN 3 WHEN 'archived' THEN 4
                ELSE 1 END
        ELSE CASE b.status
            WHEN 'not_started' THEN 0 WHEN 'ongoing' THEN 1
            WHEN 'in_progress' THEN 1 WHEN 'completed' THEN 2
            WHEN 'terminated' THEN 3 WHEN 'archived' THEN 4
            ELSE 1 END
    END AS status_encoded_at_halfway,

    CASE
        WHEN tsh.approval_status_at_halfway_val IS NOT NULL
            THEN CASE tsh.approval_status_at_halfway_val
                WHEN 'pending' THEN 0 WHEN 'in_review' THEN 1
                WHEN 'approved' THEN 2 WHEN 'rejected' THEN 3
                ELSE 1 END
        ELSE CASE b.approval_status
            WHEN 'pending' THEN 0 WHEN 'in_review' THEN 1
            WHEN 'approved' THEN 2 WHEN 'rejected' THEN 3
            ELSE 1 END
    END AS approval_status_encoded_at_halfway,

    CASE
        WHEN tsh.lead_approval_status_at_halfway_val IS NOT NULL
            THEN CASE tsh.lead_approval_status_at_halfway_val
                WHEN 'pending' THEN 0 WHEN 'in_review' THEN 1
                WHEN 'approved' THEN 2 WHEN 'rejected' THEN 3
                ELSE 1 END
        ELSE CASE b.lead_approval_status
            WHEN 'pending' THEN 0 WHEN 'in_review' THEN 1
            WHEN 'approved' THEN 2 WHEN 'rejected' THEN 3
            ELSE 1 END
    END AS lead_approval_status_encoded_at_halfway,

    -- MA status at halfway (same as creation — static)
    CASE ma.ma_status
        WHEN 'not_started' THEN 0 WHEN 'ongoing' THEN 1
        WHEN 'completed' THEN 2 WHEN 'terminated' THEN 3
        ELSE 1
    END AS ma_status_encoded_at_halfway,

    CASE ma.ma_approval_status
        WHEN 'pending' THEN 0 WHEN 'in_review' THEN 1
        WHEN 'approved' THEN 2 WHEN 'rejected' THEN 3
        ELSE 1
    END AS ma_approval_status_encoded_at_halfway,

    -- MA revisions at halfway
    COALESCE(mar.num_ma_revisions_at_halfway, 0)::int AS num_ma_revisions_at_halfway,

    -- KPI features at halfway
    COALESCE(kfh.kpi_is_overdue_flag_at_halfway, 0)::int AS kpi_is_overdue_flag_at_halfway,
    CASE
        WHEN kfh.kpi_status_at_halfway IS NOT NULL
            THEN CASE kfh.kpi_status_at_halfway
                WHEN 'not_started' THEN 0 WHEN 'ongoing' THEN 1
                WHEN 'completed' THEN 2 WHEN 'terminated' THEN 3
                WHEN 'archived' THEN 4 ELSE 1 END
        ELSE 1
    END AS kpi_status_ordinal_at_halfway,

    -- KPI revisions at halfway
    COALESCE(kr.num_kpi_revisions_at_halfway, 0)::int AS num_kpi_revisions_at_halfway,

    -- Task revisions at halfway
    COALESCE(r.num_revisions_at_halfway, 0)::int AS num_revisions_at_halfway,
    CASE
        WHEN b.planned_duration > 0
            THEN COALESCE(r.num_revisions_at_halfway::numeric / NULLIF(b.planned_duration, 0), 0)
        ELSE 0
    END AS revision_frequency_at_halfway,
    CASE
        WHEN r.last_revision_at_halfway IS NOT NULL
            THEN ('2026-07-14'::date - r.last_revision_at_halfway::date)
        ELSE 0
    END AS revision_recency_at_halfway,

    -- Subtasks at halfway
    COALESCE(s.num_subtasks_at_halfway, 0)::int AS num_subtasks_at_halfway,
    CASE WHEN COALESCE(s.num_subtasks_at_halfway, 0) > 0 THEN 1 ELSE 0 END AS has_subtasks_at_halfway,
    CASE
        WHEN COALESCE(s.num_subtasks_at_halfway, 0) > 0
            THEN COALESCE(s.num_completed_at_halfway::numeric / NULLIF(s.num_subtasks_at_halfway, 0), 0)
        ELSE 0
    END AS subtask_completion_pct_at_halfway,
    CASE
        WHEN COALESCE(s.num_subtasks_at_halfway, 0) > 0
            THEN COALESCE(s.num_overdue_at_halfway::numeric / NULLIF(s.num_subtasks_at_halfway, 0), 0)
        ELSE 0
    END AS subtask_overdue_rate_at_halfway,

    -- Task comments at halfway
    COALESCE(ct.task_comment_count_at_halfway, 0)::int AS task_comment_count_at_halfway,

    -- Sub-task status churn at halfway
    COALESCE(tsc2.avg_sub_status_changes_at_halfway, 0) AS avg_sub_status_changes_at_halfway

FROM base b
LEFT JOIN first_completed fc ON fc.task_id = b.id
LEFT JOIN revisions r ON r.task_id = b.id
LEFT JOIN subtasks s ON s.task_id = b.id
LEFT JOIN task_status_at_creation tsc ON tsc.task_id = b.id
LEFT JOIN task_status_at_halfway tsh ON tsh.task_id = b.id
LEFT JOIN dept_agg d ON d.id = b.id
LEFT JOIN emp_agg e ON e.id = b.id
LEFT JOIN pos_agg p ON p.id = b.id
LEFT JOIN ma_info ma ON ma.major_activity_id = b.major_activity_id
LEFT JOIN ma_revisions mar ON mar.major_activity_id = b.major_activity_id
LEFT JOIN kpi_revisions kr ON kr.kpi_id = ma.kpi_id
LEFT JOIN kpi_features_at_creation kfc ON kfc.kpi_id = ma.kpi_id
LEFT JOIN kpi_features_at_halfway kfh ON kfh.kpi_id = ma.kpi_id
LEFT JOIN comments_task ct ON ct.task_id = b.id
LEFT JOIN comments_kpi ck ON ck.major_activity_id = b.major_activity_id
LEFT JOIN task_sub_churn tsc2 ON tsc2.task_id = b.id
LEFT JOIN cross_dept cd ON cd.task_id = b.id
LEFT JOIN position_dept pd ON pd.position_id = b.position_id

ORDER BY b.id;
