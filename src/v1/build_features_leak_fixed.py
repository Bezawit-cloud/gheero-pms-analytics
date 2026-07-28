import os
import argparse
from dotenv import load_dotenv
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text

load_dotenv()
DB_URL = os.getenv('DB_URL')

FIXED_CUTOFF = pd.Timestamp('2026-07-14').normalize()
STATUS_ORDER = {'not_started': 0, 'ongoing': 1, 'in_progress': 1, 'completed': 2, 'terminated': 3, 'archived': 4}
APR_ORDER = {'pending': 0, 'in_review': 1, 'approved': 2, 'rejected': 3}
MA_STATUS_ORDER = {'not_started': 0, 'ongoing': 1, 'completed': 2, 'terminated': 3}
KPI_STATUS_ORDER = {'not_started': 0, 'ongoing': 1, 'completed': 2, 'terminated': 3, 'archived': 4}


def q(sql, engine):
    return pd.read_sql(sql, engine)


def load_base_tasks(engine):
    sql = text("""
        SELECT t.id, t.status, t.approval_status, t.lead_approval_status,
               t.weight_level, t.is_planned::int AS is_planned, t.risk_mapping,
               t.start_date, t.end_date, t.actual_end_date,
               t.created_date, t.updated_date,
               t.major_activity_id, t.created_by_id, t.position_id, t.department_id,
               CASE WHEN t.derived_from_cross_department_assignment_id IS NOT NULL THEN 1 ELSE 0 END AS is_cross_dept,
               t.created_date AS creation_cutoff,
               GREATEST(t.created_date, t.start_date + (t.end_date - t.start_date) / 2) AS halfway_cutoff
        FROM tasks_task t
        WHERE t.start_date IS NOT NULL AND t.end_date IS NOT NULL
    """)
    base = q(sql, engine)
    for col in ['start_date', 'end_date', 'actual_end_date', 'created_date', 'updated_date',
                'creation_cutoff', 'halfway_cutoff']:
        ser = pd.to_datetime(base[col], errors='coerce')
        base[col] = ser.dt.tz_localize(None) if hasattr(ser.dt, 'tz') and ser.dt.tz is not None else ser
    print(f'Base tasks: {len(base)}')
    return base


def compute_target(base):
    FIXED_CUTOFF = pd.Timestamp('2026-07-14').normalize()
    completed = base['status'] == 'completed'
    has_actual = base['actual_end_date'].notna()

    completion_date = base['actual_end_date'].copy()
    completion_date = completion_date.fillna(base['first_completed_at'].dt.normalize())
    completion_date = completion_date.fillna(base['updated_date'].dt.normalize())

    conditions = [
        completed & has_actual,
        completed & ~has_actual & base['first_completed_at'].notna(),
        completed & ~has_actual & base['first_completed_at'].isna(),
        ~base['status'].isin(['completed', 'terminated', 'archived']) & (base['end_date'] < FIXED_CUTOFF),
    ]
    source_labels = ['actual_end_date', 'history_completion', 'updated_date', 'open_task']
    base['target_source'] = np.select(conditions, source_labels, default='status_based')

    overdue_conditions = [
        completed & (completion_date > base['end_date']),
        ~base['status'].isin(['completed', 'terminated', 'archived']) & (base['end_date'] < FIXED_CUTOFF),
    ]
    base['calculated_overdue'] = np.select(overdue_conditions, [1, 1], default=0)
    print(f'Overdue rate: {base["calculated_overdue"].mean():.2%}')
    return base


def compute_derived_features(base):
    base['planned_duration'] = (base['end_date'] - base['start_date']).dt.days
    base['creation_to_planned_start'] = (base['start_date'] - base['created_date']).dt.days
    base['created_dow'] = base['created_date'].dt.dayofweek
    base['created_is_weekend'] = (base['created_dow'] >= 5).astype(int)
    base['created_is_friday'] = (base['created_dow'] == 4).astype(int)
    base['created_month'] = base['created_date'].dt.month
    base['created_quarter'] = base['created_date'].dt.quarter
    base['days_since_update_halfway'] = (FIXED_CUTOFF - base['updated_date']).dt.days
    return base


def load_first_completed(engine, base):
    fc = q(text("""
        SELECT history_relation_id AS task_id, MIN(history_date) AS first_completed_at
        FROM tasks_task_history WHERE status = 'completed'
        GROUP BY history_relation_id
    """), engine)
    fc['first_completed_at'] = pd.to_datetime(fc['first_completed_at'], errors='coerce')
    if hasattr(fc['first_completed_at'].dt, 'tz') and fc['first_completed_at'].dt.tz is not None:
        fc['first_completed_at'] = fc['first_completed_at'].dt.tz_localize(None)
    base = base.merge(fc, left_on='id', right_on='task_id', how='left')
    base.drop(columns=['task_id'], inplace=True)
    return base


def load_revisions(engine, base):
    sql = text("""
        SELECT th.history_relation_id AS task_id,
               COUNT(*) FILTER (WHERE th.history_date <= b.creation_cutoff) AS num_revisions_at_creation,
               COUNT(*) FILTER (WHERE th.history_date <= b.halfway_cutoff) AS num_revisions_at_halfway,
               MAX(th.history_date) FILTER (WHERE th.history_date <= b.creation_cutoff) AS last_revision_at_creation,
               MAX(th.history_date) FILTER (WHERE th.history_date <= b.halfway_cutoff) AS last_revision_at_halfway
        FROM tasks_task_history th
        JOIN (SELECT id, created_date AS creation_cutoff,
                     GREATEST(created_date, start_date + (end_date - start_date) / 2) AS halfway_cutoff
              FROM tasks_task WHERE start_date IS NOT NULL AND end_date IS NOT NULL) b
          ON b.id = th.history_relation_id
        GROUP BY th.history_relation_id
    """)
    rev = q(sql, engine)
    for col in ['last_revision_at_creation', 'last_revision_at_halfway']:
        if col in rev.columns and rev[col].notna().any():
            rev[col] = pd.to_datetime(rev[col], errors='coerce')
            if hasattr(rev[col].dt, 'tz') and rev[col].dt.tz is not None:
                rev[col] = rev[col].dt.tz_localize(None)

    created_by_id = base.set_index('id')['created_date']

    rev['revision_frequency_at_creation'] = 0.0
    rev['revision_recency_at_creation'] = rev['task_id'].map(
        lambda tid: (FIXED_CUTOFF - created_by_id.loc[tid]).days if tid in created_by_id.index else 0
    )
    rev['revision_frequency_at_halfway'] = rev['num_revisions_at_halfway'].fillna(0).astype(float).clip(lower=0)
    rev['revision_recency_at_halfway'] = (
        (FIXED_CUTOFF - pd.to_datetime(rev['last_revision_at_halfway'], errors='coerce')).dt.days
        if rev['last_revision_at_halfway'].notna().any() else 0
    ).fillna(0).astype(int)

    base = base.merge(
        rev[['task_id', 'num_revisions_at_creation', 'num_revisions_at_halfway',
             'revision_frequency_at_creation', 'revision_frequency_at_halfway',
             'revision_recency_at_creation', 'revision_recency_at_halfway']],
        left_on='id', right_on='task_id', how='left'
    )
    for col in ['num_revisions_at_creation', 'num_revisions_at_halfway']:
        base[col] = base[col].fillna(0).astype(int)
    for col in ['revision_frequency_at_creation', 'revision_frequency_at_halfway',
                'revision_recency_at_creation', 'revision_recency_at_halfway']:
        base[col] = base[col].fillna(0)
    base.drop(columns=['task_id'], inplace=True)
    return base


def load_subtasks(engine, base):
    sql = text("""
        SELECT st.task_id,
               COUNT(*) FILTER (WHERE st.created_date <= b.creation_cutoff) AS num_subtasks_at_creation,
               COUNT(*) FILTER (WHERE st.created_date <= b.halfway_cutoff) AS num_subtasks_at_halfway,
               SUM(CASE WHEN st.status = 'completed' AND st.created_date <= b.creation_cutoff THEN 1 ELSE 0 END) AS num_completed_at_creation,
               SUM(CASE WHEN st.status = 'completed' AND st.created_date <= b.halfway_cutoff THEN 1 ELSE 0 END) AS num_completed_at_halfway,
               SUM(CASE WHEN st.is_overdue = TRUE AND st.created_date <= b.creation_cutoff THEN 1 ELSE 0 END) AS num_overdue_at_creation,
               SUM(CASE WHEN st.is_overdue = TRUE AND st.created_date <= b.halfway_cutoff THEN 1 ELSE 0 END) AS num_overdue_at_halfway
        FROM tasks_sub_task st
        JOIN (SELECT id, created_date AS creation_cutoff,
                     GREATEST(created_date, start_date + (end_date - start_date) / 2) AS halfway_cutoff
              FROM tasks_task WHERE start_date IS NOT NULL AND end_date IS NOT NULL) b
          ON b.id = st.task_id
        GROUP BY st.task_id
    """)
    sub = q(sql, engine)
    sub['subtask_completion_pct_at_creation'] = (sub['num_completed_at_creation'] / sub['num_subtasks_at_creation'].replace(0, np.nan)).fillna(0)
    sub['subtask_completion_pct_at_halfway'] = (sub['num_completed_at_halfway'] / sub['num_subtasks_at_halfway'].replace(0, np.nan)).fillna(0)
    sub['subtask_overdue_rate_at_creation'] = (sub['num_overdue_at_creation'] / sub['num_subtasks_at_creation'].replace(0, np.nan)).fillna(0)
    sub['subtask_overdue_rate_at_halfway'] = (sub['num_overdue_at_halfway'] / sub['num_subtasks_at_halfway'].replace(0, np.nan)).fillna(0)

    base = base.merge(
        sub[['task_id', 'num_subtasks_at_creation', 'num_subtasks_at_halfway',
             'subtask_completion_pct_at_creation', 'subtask_completion_pct_at_halfway',
             'subtask_overdue_rate_at_creation', 'subtask_overdue_rate_at_halfway']],
        left_on='id', right_on='task_id', how='left'
    )
    base['has_subtasks_at_creation'] = (base['num_subtasks_at_creation'] > 0).astype(int)
    base['has_subtasks_at_halfway'] = (base['num_subtasks_at_halfway'] > 0).astype(int)
    for col in ['num_subtasks_at_creation', 'num_subtasks_at_halfway']:
        base[col] = base[col].fillna(0).astype(int)
    for col in ['subtask_completion_pct_at_creation', 'subtask_completion_pct_at_halfway',
                'subtask_overdue_rate_at_creation', 'subtask_overdue_rate_at_halfway']:
        base[col] = base[col].fillna(0.0)
    base.drop(columns=['task_id'], inplace=True)
    return base


def load_status_lookup(engine, base):
    sql_creation = text("""
        SELECT DISTINCT ON (th.history_relation_id)
            th.history_relation_id AS task_id,
            th.status AS status_at_creation,
            th.approval_status AS approval_status_at_creation,
            th.lead_approval_status AS lead_approval_status_at_creation
        FROM tasks_task_history th
        JOIN (SELECT id, created_date AS creation_cutoff
              FROM tasks_task WHERE start_date IS NOT NULL AND end_date IS NOT NULL) b
          ON b.id = th.history_relation_id
        WHERE th.history_date <= b.creation_cutoff
        ORDER BY th.history_relation_id, th.history_date DESC
    """)
    sql_halfway = text("""
        SELECT DISTINCT ON (th.history_relation_id)
            th.history_relation_id AS task_id,
            th.status AS status_at_halfway,
            th.approval_status AS approval_status_at_halfway,
            th.lead_approval_status AS lead_approval_status_at_halfway
        FROM tasks_task_history th
        JOIN (SELECT id, GREATEST(created_date, start_date + (end_date - start_date) / 2) AS halfway_cutoff
              FROM tasks_task WHERE start_date IS NOT NULL AND end_date IS NOT NULL) b
          ON b.id = th.history_relation_id
        WHERE th.history_date <= b.halfway_cutoff
        ORDER BY th.history_relation_id, th.history_date DESC
    """)

    st_c = q(sql_creation, engine)
    st_h = q(sql_halfway, engine)

    base['status_creation'] = base['id'].map(st_c.set_index('task_id')['status_at_creation']).fillna(base['status'])
    base['status_halfway'] = base['id'].map(st_h.set_index('task_id')['status_at_halfway']).fillna(base['status'])
    base['apr_creation'] = base['id'].map(st_c.set_index('task_id')['approval_status_at_creation']).fillna(base['approval_status'])
    base['apr_halfway'] = base['id'].map(st_h.set_index('task_id')['approval_status_at_halfway']).fillna(base['approval_status'])
    base['lead_apr_creation'] = base['id'].map(st_c.set_index('task_id')['lead_approval_status_at_creation']).fillna(base['lead_approval_status'])
    base['lead_apr_halfway'] = base['id'].map(st_h.set_index('task_id')['lead_approval_status_at_halfway']).fillna(base['lead_approval_status'])

    base['status_encoded_creation'] = base['status_creation'].map(STATUS_ORDER).fillna(1).astype(int)
    base['status_encoded_halfway'] = base['status_halfway'].map(STATUS_ORDER).fillna(1).astype(int)
    base['approval_status_encoded_creation'] = base['apr_creation'].map(APR_ORDER).fillna(1).astype(int)
    base['approval_status_encoded_halfway'] = base['apr_halfway'].map(APR_ORDER).fillna(1).astype(int)
    base['lead_approval_status_encoded_creation'] = base['lead_apr_creation'].map(APR_ORDER).fillna(1).astype(int)
    base['lead_approval_status_encoded_halfway'] = base['lead_apr_halfway'].map(APR_ORDER).fillna(1).astype(int)

    base.drop(columns=['status_creation', 'status_halfway', 'apr_creation', 'apr_halfway',
                       'lead_apr_creation', 'lead_apr_halfway'], inplace=True)
    return base


def load_ma_info(engine, base):
    ma = q(text("""
        SELECT ma.id AS major_activity_id, ma.status AS ma_status,
               ma.approval_status AS ma_approval_status, ma.kpi_id
        FROM tasks_major_activity ma
    """), engine)
    base = base.merge(ma, on='major_activity_id', how='left')
    base['ma_status_encoded_creation'] = base['ma_status'].map(MA_STATUS_ORDER).fillna(1).astype(int)
    base['ma_status_encoded_halfway'] = base['ma_status'].map(MA_STATUS_ORDER).fillna(1).astype(int)
    base['ma_approval_status_encoded_creation'] = base['ma_approval_status'].map(APR_ORDER).fillna(1).astype(int)
    base['ma_approval_status_encoded_halfway'] = base['ma_approval_status'].map(APR_ORDER).fillna(1).astype(int)
    return base


def load_ma_revisions(engine, base):
    sql = text("""
        SELECT b.id, b.major_activity_id,
               COUNT(*) FILTER (WHERE mah.history_date <= b.creation_cutoff) AS num_ma_revisions_at_creation,
               COUNT(*) FILTER (WHERE mah.history_date <= b.halfway_cutoff) AS num_ma_revisions_at_halfway
        FROM (SELECT id, major_activity_id, created_date AS creation_cutoff,
                     GREATEST(created_date, start_date + (end_date - start_date) / 2) AS halfway_cutoff
              FROM tasks_task WHERE start_date IS NOT NULL AND end_date IS NOT NULL) b
        LEFT JOIN tasks_major_activity_history mah ON mah.id = b.major_activity_id
        GROUP BY b.id, b.major_activity_id
    """)
    mar = q(sql, engine)
    mar['num_ma_revisions_at_creation'] = mar['num_ma_revisions_at_creation'].fillna(0).astype(int)
    mar['num_ma_revisions_at_halfway'] = mar['num_ma_revisions_at_halfway'].fillna(0).astype(int)
    base = base.merge(mar[['id', 'num_ma_revisions_at_creation', 'num_ma_revisions_at_halfway']], on='id', how='left')
    base['num_ma_revisions_at_creation'] = base['num_ma_revisions_at_creation'].fillna(0).astype(int)
    base['num_ma_revisions_at_halfway'] = base['num_ma_revisions_at_halfway'].fillna(0).astype(int)
    return base


def load_kpi_features(engine, base):
    kc = q(text("""
        SELECT b.id,
               (SELECT kh.is_overdue::int FROM tasks_kpi_history kh
                WHERE kh.id = ma.kpi_id AND kh.history_date <= b.creation_cutoff
                ORDER BY kh.history_date DESC LIMIT 1) AS kpi_is_overdue_creation,
               (SELECT kh.status FROM tasks_kpi_history kh
                WHERE kh.id = ma.kpi_id AND kh.history_date <= b.creation_cutoff
                ORDER BY kh.history_date DESC LIMIT 1) AS kpi_status_creation,
               (SELECT kh.is_overdue::int FROM tasks_kpi_history kh
                WHERE kh.id = ma.kpi_id AND kh.history_date <= b.halfway_cutoff
                ORDER BY kh.history_date DESC LIMIT 1) AS kpi_is_overdue_halfway,
               (SELECT kh.status FROM tasks_kpi_history kh
                WHERE kh.id = ma.kpi_id AND kh.history_date <= b.halfway_cutoff
                ORDER BY kh.history_date DESC LIMIT 1) AS kpi_status_halfway
        FROM (SELECT t.id, t.major_activity_id, t.creation_cutoff, t.halfway_cutoff
              FROM (SELECT id, major_activity_id, created_date AS creation_cutoff,
                           GREATEST(created_date, start_date + (end_date - start_date) / 2) AS halfway_cutoff
                    FROM tasks_task WHERE start_date IS NOT NULL AND end_date IS NOT NULL) t) b
        LEFT JOIN tasks_major_activity ma ON ma.id = b.major_activity_id
    """), engine)

    base['kpi_is_overdue_flag_creation'] = kc['kpi_is_overdue_creation'].fillna(0).astype(int)
    base['kpi_is_overdue_flag_halfway'] = kc['kpi_is_overdue_halfway'].fillna(0).astype(int)
    base['kpi_status_ordinal_creation'] = kc['kpi_status_creation'].fillna('ongoing').map(KPI_STATUS_ORDER).fillna(1).astype(int)
    base['kpi_status_ordinal_halfway'] = kc['kpi_status_halfway'].fillna('ongoing').map(KPI_STATUS_ORDER).fillna(1).astype(int)
    return base


def load_kpi_revisions(engine, base):
    sql = text("""
        SELECT b.id,
               COALESCE((SELECT COUNT(*) FROM tasks_kpi_history kh
                         WHERE kh.id = ma.kpi_id AND kh.history_date <= b.creation_cutoff), 0)::int AS num_kpi_revisions_at_creation,
               COALESCE((SELECT COUNT(*) FROM tasks_kpi_history kh
                         WHERE kh.id = ma.kpi_id AND kh.history_date <= b.halfway_cutoff), 0)::int AS num_kpi_revisions_at_halfway
        FROM (SELECT t.id, t.major_activity_id, t.created_date AS creation_cutoff,
                     GREATEST(t.created_date, t.start_date + (t.end_date - t.start_date) / 2) AS halfway_cutoff
              FROM tasks_task t WHERE t.start_date IS NOT NULL AND t.end_date IS NOT NULL) b
        LEFT JOIN tasks_major_activity ma ON ma.id = b.major_activity_id
    """)
    kph = q(sql, engine)
    base['num_kpi_revisions_at_creation'] = kph['num_kpi_revisions_at_creation'].fillna(0).astype(int)
    base['num_kpi_revisions_at_halfway'] = kph['num_kpi_revisions_at_halfway'].fillna(0).astype(int)
    return base


def load_comments(engine, base):
    sql = text("""
        SELECT cc.object_id AS task_id,
               COUNT(*) FILTER (WHERE cc.created_date <= b.creation_cutoff) AS task_comment_count_at_creation,
               COUNT(*) FILTER (WHERE cc.created_date <= b.halfway_cutoff) AS task_comment_count_at_halfway
        FROM comments_comment cc
        JOIN (SELECT id, created_date AS creation_cutoff,
                     GREATEST(created_date, start_date + (end_date - start_date) / 2) AS halfway_cutoff
              FROM tasks_task WHERE start_date IS NOT NULL AND end_date IS NOT NULL) b
          ON b.id = cc.object_id
        WHERE cc.content_type_id = 24
        GROUP BY cc.object_id
    """)
    tc = q(sql, engine)
    base = base.merge(tc, left_on='id', right_on='task_id', how='left')
    base['task_comment_count_at_creation'] = base['task_comment_count_at_creation'].fillna(0).astype(int)
    base['task_comment_count_at_halfway'] = base['task_comment_count_at_halfway'].fillna(0).astype(int)
    base.drop(columns=['task_id'], inplace=True)
    return base


def load_subtask_history(engine, base):
    sql = text("""
        SELECT st.task_id,
               AVG(sh.num_status_changes_at_creation) AS avg_sub_status_changes_at_creation,
               AVG(sh.num_status_changes_at_halfway) AS avg_sub_status_changes_at_halfway
        FROM (
            SELECT sth.id AS sub_task_id,
                   COUNT(DISTINCT sth.status) FILTER (WHERE sth.history_date <= b.creation_cutoff) AS num_status_changes_at_creation,
                   COUNT(DISTINCT sth.status) FILTER (WHERE sth.history_date <= b.halfway_cutoff) AS num_status_changes_at_halfway
            FROM tasks_sub_task_history sth
            JOIN tasks_sub_task st ON st.id = sth.id
            JOIN (SELECT id, created_date AS creation_cutoff,
                         GREATEST(created_date, start_date + (end_date - start_date) / 2) AS halfway_cutoff
                  FROM tasks_task WHERE start_date IS NOT NULL AND end_date IS NOT NULL) b
              ON b.id = st.task_id
            GROUP BY sth.id
        ) sh
        JOIN tasks_sub_task st ON st.id = sh.sub_task_id
        GROUP BY st.task_id
    """)
    sh = q(sql, engine)
    base = base.merge(sh, left_on='id', right_on='task_id', how='left')
    base['avg_sub_status_changes_at_creation'] = base['avg_sub_status_changes_at_creation'].fillna(0)
    base['avg_sub_status_changes_at_halfway'] = base['avg_sub_status_changes_at_halfway'].fillna(0)
    base.drop(columns=['task_id'], inplace=True)
    return base


def load_cross_dept(engine, base):
    cd = q(text("""
        SELECT t.id AS task_id, 1 AS cross_dept_pair_exists
        FROM tasks_task t
        JOIN tasks_cross_department_assignments cda ON cda.id = t.derived_from_cross_department_assignment_id
    """), engine)
    base = base.merge(cd, left_on='id', right_on='task_id', how='left')
    base['cross_dept_pair_exists'] = base['cross_dept_pair_exists'].fillna(0).astype(int)
    base.drop(columns=['task_id'], inplace=True)
    return base


def build_dataset(engine):
    print('=== Loading base tasks ===')
    base = load_base_tasks(engine)

    print('=== Loading first completed timestamps ===')
    base = load_first_completed(engine, base)

    print('=== Computing target and derived features ===')
    base = compute_target(base)
    base = compute_derived_features(base)

    print('=== Loading revisions (cutoff-aware) ===')
    base = load_revisions(engine, base)

    print('=== Loading subtasks (cutoff-aware) ===')
    base = load_subtasks(engine, base)

    print('=== Loading status lookup (cutoff-aware) ===')
    base = load_status_lookup(engine, base)

    print('=== Loading MA info ===')
    base = load_ma_info(engine, base)

    print('=== Loading MA revisions (cutoff-aware) ===')
    base = load_ma_revisions(engine, base)

    print('=== Loading KPI features (cutoff-aware) ===')
    base = load_kpi_features(engine, base)

    print('=== Loading KPI revisions (cutoff-aware) ===')
    base = load_kpi_revisions(engine, base)

    print('=== Loading comments (cutoff-aware) ===')
    base = load_comments(engine, base)

    print('=== Loading subtask history (cutoff-aware) ===')
    base = load_subtask_history(engine, base)

    print('=== Loading cross-dept flags ===')
    base = load_cross_dept(engine, base)

    print('=== Loading department/employee/position aggregates (expanding window) ===')
    dept_sql = text("""
        SELECT id, dept_past_overdue_rate, dept_avg_revisions FROM (
            SELECT t.id,
                   AVG(CASE WHEN tov.status = 'completed' AND tov.actual_end_date IS NOT NULL AND tov.actual_end_date > tov.end_date THEN 1
                            WHEN tov.status = 'completed' AND tov.actual_end_date IS NULL AND tov.updated_date::date > tov.end_date THEN 1
                            WHEN tov.status NOT IN ('completed', 'terminated', 'archived') AND tov.end_date < '2026-07-14'::date THEN 1
                            ELSE 0 END)
                       OVER (PARTITION BY COALESCE(p.department_id, t.department_id)
                             ORDER BY t.created_date ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS dept_past_overdue_rate,
                   AVG(COALESCE(rev_cnt.num_revisions, 0))
                       OVER (PARTITION BY COALESCE(p.department_id, t.department_id)
                             ORDER BY t.created_date ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS dept_avg_revisions
            FROM tasks_task t
            LEFT JOIN basedata_position p ON p.id = t.position_id
            LEFT JOIN (SELECT history_relation_id AS task_id, COUNT(*) AS num_revisions
                       FROM tasks_task_history WHERE history_relation_id IS NOT NULL GROUP BY history_relation_id) rev_cnt
              ON rev_cnt.task_id = t.id
            WHERE t.start_date IS NOT NULL AND t.end_date IS NOT NULL
        ) sub
    """)
    emp_sql = text("""
        SELECT id, emp_past_overdue_rate FROM (
            SELECT t.id,
                   AVG(CASE WHEN tov.status = 'completed' AND tov.actual_end_date IS NOT NULL AND tov.actual_end_date > tov.end_date THEN 1
                            WHEN tov.status = 'completed' AND tov.actual_end_date IS NULL AND tov.updated_date::date > tov.end_date THEN 1
                            WHEN tov.status NOT IN ('completed', 'terminated', 'archived') AND tov.end_date < '2026-07-14'::date THEN 1
                            ELSE 0 END)
                       OVER (PARTITION BY p.user_id
                             ORDER BY t.created_date ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS emp_past_overdue_rate
            FROM tasks_task t
            LEFT JOIN basedata_position p ON p.id = t.position_id
            WHERE t.start_date IS NOT NULL AND t.end_date IS NOT NULL
        ) sub
    """)
    pos_sql = text("""
        SELECT id, pos_past_overdue_rate FROM (
            SELECT t.id,
                   AVG(CASE WHEN tov.status = 'completed' AND tov.actual_end_date IS NOT NULL AND tov.actual_end_date > tov.end_date THEN 1
                            WHEN tov.status = 'completed' AND tov.actual_end_date IS NULL AND tov.updated_date::date > tov.end_date THEN 1
                            WHEN tov.status NOT IN ('completed', 'terminated', 'archived') AND tov.end_date < '2026-07-14'::date THEN 1
                            ELSE 0 END)
                       OVER (PARTITION BY t.position_id
                             ORDER BY t.created_date ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS pos_past_overdue_rate
            FROM tasks_task t
            WHERE t.start_date IS NOT NULL AND t.end_date IS NOT NULL AND t.position_id IS NOT NULL
        ) sub
    """)

    dept_agg = q(dept_sql, engine)
    emp_agg = q(emp_sql, engine)
    pos_agg = q(pos_sql, engine)

    base = base.merge(dept_agg[['id', 'dept_past_overdue_rate', 'dept_avg_revisions']], on='id', how='left')
    base = base.merge(emp_agg[['id', 'emp_past_overdue_rate']], on='id', how='left')
    base = base.merge(pos_agg[['id', 'pos_past_overdue_rate']], on='id', how='left')

    global_mean_od = base['calculated_overdue'].mean()
    base['dept_past_overdue_rate'] = base['dept_past_overdue_rate'].fillna(global_mean_od)
    base['dept_avg_revisions'] = base['dept_avg_revisions'].fillna(0)
    base['emp_past_overdue_rate'] = base['emp_past_overdue_rate'].fillna(global_mean_od)
    base['pos_past_overdue_rate'] = base['pos_past_overdue_rate'].fillna(global_mean_od)

    print('=== Building creation and halfway datasets ===')

    wl_cols_in_use = ['wl_high', 'wl_mid']

    creation_col_map = {
        'status_encoded': 'status_encoded_creation',
        'approval_status_encoded': 'approval_status_encoded_creation',
        'lead_approval_status_encoded': 'lead_approval_status_encoded_creation',
        'ma_status_encoded': 'ma_status_encoded_creation',
        'ma_approval_status_encoded': 'ma_approval_status_encoded_creation',
        'num_ma_revisions': 'num_ma_revisions_at_creation',
        'kpi_is_overdue_flag': 'kpi_is_overdue_flag_creation',
        'kpi_status_ordinal': 'kpi_status_ordinal_creation',
        'num_kpi_revisions': 'num_kpi_revisions_at_creation',
        'kpi_comment_count': 'kpi_comment_count_creation',
        'num_revisions': 'num_revisions_at_creation',
        'revision_frequency': 'revision_frequency_at_creation',
        'revision_recency': 'revision_recency_at_creation',
        'num_subtasks': 'num_subtasks_at_creation',
        'has_subtasks': 'has_subtasks_at_creation',
        'subtask_completion_pct': 'subtask_completion_pct_at_creation',
        'subtask_overdue_rate': 'subtask_overdue_rate_at_creation',
        'task_comment_count': 'task_comment_count_at_creation',
        'avg_sub_status_changes': 'avg_sub_status_changes_at_creation',
    }

    halfway_col_map = {
        'status_encoded': 'status_encoded_halfway',
        'approval_status_encoded': 'approval_status_encoded_halfway',
        'lead_approval_status_encoded': 'lead_approval_status_encoded_halfway',
        'ma_status_encoded': 'ma_status_encoded_halfway',
        'ma_approval_status_encoded': 'ma_approval_status_encoded_halfway',
        'num_ma_revisions': 'num_ma_revisions_at_halfway',
        'kpi_is_overdue_flag': 'kpi_is_overdue_flag_halfway',
        'kpi_status_ordinal': 'kpi_status_ordinal_halfway',
        'num_kpi_revisions': 'num_kpi_revisions_at_halfway',
        'num_revisions': 'num_revisions_at_halfway',
        'revision_frequency': 'revision_frequency_at_halfway',
        'revision_recency': 'revision_recency_at_halfway',
        'num_subtasks': 'num_subtasks_at_halfway',
        'has_subtasks': 'has_subtasks_at_halfway',
        'subtask_completion_pct': 'subtask_completion_pct_at_halfway',
        'subtask_overdue_rate': 'subtask_overdue_rate_at_halfway',
        'task_comment_count': 'task_comment_count_at_halfway',
        'avg_sub_status_changes': 'avg_sub_status_changes_at_halfway',
        'days_since_update': 'days_since_update_halfway',
        'subtask_completion_pct_at_halfway': 'subtask_completion_pct_at_halfway',
    }

    static_cols = [
        'id', 'calculated_overdue', 'target_source',
        'planned_duration', 'creation_to_planned_start',
        'created_dow', 'created_is_weekend', 'created_is_friday',
        'created_month', 'created_quarter',
        'is_planned', 'risk_mapping', 'is_cross_dept', 'cross_dept_pair_exists',
        'dept_past_overdue_rate', 'dept_avg_revisions',
        'emp_past_overdue_rate', 'pos_past_overdue_rate',
    ] + wl_cols_in_use

    creation_data = base[static_cols].copy()
    for new_name, old_name in creation_col_map.items():
        if old_name in base.columns:
            creation_data[new_name] = base[old_name]

    halfway_data = base[static_cols].copy()
    for new_name, old_name in halfway_col_map.items():
        if old_name in base.columns:
            halfway_data[new_name] = base[old_name]

    for df in [creation_data, halfway_data]:
        for col in df.columns:
            if df[col].dtype == 'object' and col not in ('id', 'target_source'):
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            if col not in ('id', 'target_source'):
                df[col] = df[col].fillna(0)

    creation_feats = [c for c in creation_data.columns if c not in ('id', 'calculated_overdue', 'target_source')]
    halfway_feats = [c for c in halfway_data.columns if c not in ('id', 'calculated_overdue', 'target_source')]

    print(f'Creation dataset: {creation_data.shape[0]} rows, {creation_data.shape[1]} cols ({len(creation_feats)} features)')
    print(f'Halfway dataset:  {halfway_data.shape[0]} rows, {halfway_data.shape[1]} cols ({len(halfway_feats)} features)')
    print(f'Target rate: {creation_data["calculated_overdue"].mean():.2%}')

    return creation_data, halfway_data


def main():
    parser = argparse.ArgumentParser(description='Build leak-fixed PMS overdue prediction dataset')
    parser.add_argument('--output-dir', default='.', help='Directory to save CSV files')
    args = parser.parse_args()

    engine = create_engine(DB_URL)
    ds_creation, ds_halfway = build_dataset(engine)

    os.makedirs(args.output_dir, exist_ok=True)
    ds_creation.to_csv(os.path.join(args.output_dir, 'dataset_at_creation_clean.csv'), index=False)
    ds_halfway.to_csv(os.path.join(args.output_dir, 'dataset_at_halfway_clean.csv'), index=False)
    print(f'Saved to {args.output_dir}/')


if __name__ == '__main__':
    main()
