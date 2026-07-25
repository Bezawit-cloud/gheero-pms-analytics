"""End-to-end feature pipeline for PMS task overdue prediction.

This script runs the full pipeline: connect to DB, execute SQL queries,
compute derived features, impute missing values, encode categories, and
export the analysis-ready dataset.

Usage:
    python -m src.build_features [--output-dir .]
"""

import os
import argparse
import pandas as pd
import numpy as np
from sqlalchemy import create_engine

from src.feature_engineering import (
    compute_target,
    compute_planned_duration,
    compute_creation_to_planned_start,
    compute_days_since_update,
    compute_halfway_date,
    compute_created_time_features,
    ordinal_encode_status,
    target_encode,
    fill_zero_features,
    fill_global_mean,
)

DB_URL = 'postgresql://postgres:12345678@172.31.237.108:5432/tasktracker_clone'

STATUS_ORDER = {
    'not_started': 0, 'ongoing': 1, 'in_progress': 1,
    'completed': 2, 'terminated': 3, 'archived': 4
}
APR_ORDER = {'pending': 0, 'in_review': 1, 'approved': 2, 'rejected': 3}
MA_STATUS_ORDER = {'not_started': 0, 'ongoing': 1, 'completed': 2, 'terminated': 3}
KPI_STATUS_ORDER = {
    'not_started': 0, 'ongoing': 1, 'completed': 2,
    'terminated': 3, 'archived': 4
}

FILL_ZERO_COLS = [
    'is_cross_dept', 'revision_frequency', 'revision_recency',
    'subtask_completion_pct', 'subtask_overdue_rate',
    'subtask_completion_pct_at_halfway',
    'num_challenges', 'has_challenges',
    'cross_dept_pair_exists',
    'kpi_is_overdue_flag',
    'has_subtask_challenge', 'num_subtask_challenges',
    'has_kpi_challenge', 'num_kpi_challenges',
    'has_kpi_potential_challenge', 'num_kpi_potential_challenges',
    'kpi_comment_count', 'ma_comment_count', 'task_comment_count',
    'avg_sub_status_changes',
]

FILL_MEAN_COLS = [
    'dept_past_overdue_rate', 'dept_avg_revisions',
    'emp_past_overdue_rate', 'pos_past_overdue_rate',
]

FINAL_FEATURES = [
    'status_encoded', 'approval_status_encoded', 'lead_approval_status_encoded',
    'ma_status_encoded', 'ma_approval_status_encoded',
    'planned_duration', 'creation_to_planned_start',
    'created_dow', 'created_is_weekend', 'created_is_friday',
    'created_month', 'created_quarter',
    'days_since_update',
    'is_planned', 'risk_mapping',
    'num_revisions', 'revision_frequency', 'revision_recency',
    'num_subtasks', 'has_subtasks',
    'subtask_completion_pct', 'subtask_overdue_rate',
    'subtask_completion_pct_at_halfway',
    'num_challenges', 'has_challenges',
    'num_ma_revisions',
    'is_cross_dept',
    'cross_dept_pair_exists',
    'kpi_is_overdue_flag', 'kpi_status_ordinal',
    'num_kpi_revisions',
    'has_subtask_challenge', 'num_subtask_challenges',
    'has_kpi_challenge', 'num_kpi_challenges',
    'has_kpi_potential_challenge', 'num_kpi_potential_challenges',
    'kpi_comment_count', 'ma_comment_count', 'task_comment_count',
    'avg_sub_status_changes',
    'dept_past_overdue_rate', 'dept_avg_revisions',
    'emp_past_overdue_rate', 'pos_past_overdue_rate',
    'position_id_encoded',
]

FEATURES_AT_ASSIGNMENT = [
    'status_encoded',
    'approval_status_encoded', 'lead_approval_status_encoded',
    'ma_status_encoded', 'ma_approval_status_encoded',
    'planned_duration', 'creation_to_planned_start',
    'created_dow', 'created_is_weekend', 'created_is_friday',
    'created_month', 'created_quarter',
    'is_planned', 'risk_mapping',
    'is_cross_dept', 'cross_dept_pair_exists',
    'num_ma_revisions',
    'kpi_is_overdue_flag', 'kpi_status_ordinal',
    'num_kpi_revisions',
    'has_kpi_challenge', 'num_kpi_challenges',
    'has_kpi_potential_challenge', 'num_kpi_potential_challenges',
    'kpi_comment_count', 'ma_comment_count',
    'dept_past_overdue_rate', 'dept_avg_revisions',
    'emp_past_overdue_rate', 'pos_past_overdue_rate',
    'position_id_encoded',
]

FEATURES_ADDED_AT_HALFWAY = [
    'days_since_update',
    'num_revisions', 'revision_frequency', 'revision_recency',
    'num_subtasks', 'has_subtasks',
    'subtask_completion_pct', 'subtask_overdue_rate',
    'subtask_completion_pct_at_halfway',
    'num_challenges', 'has_challenges',
    'has_subtask_challenge', 'num_subtask_challenges',
    'avg_sub_status_changes',
    'task_comment_count',
]

FEATURES_AT_HALFWAY = FEATURES_AT_ASSIGNMENT + FEATURES_ADDED_AT_HALFWAY


def q(sql, engine):
    return pd.read_sql(sql, engine)


def load_base_tasks(engine):
    sql = """
        SELECT
            id, status, approval_status, lead_approval_status,
            weight_level,
            is_planned::int AS is_planned,
            risk_mapping,
            start_date, end_date, actual_end_date,
            created_date, updated_date,
            major_activity_id, created_by_id, position_id, department_id,
            CASE WHEN derived_from_cross_department_assignment_id IS NOT NULL
                 THEN 1 ELSE 0 END AS is_cross_dept
        FROM tasks_task
    """
    base = q(sql, engine)
    print(f'Base tasks: {len(base)}')
    return base


def compute_derived_features(base):
    for col in ['start_date', 'end_date', 'actual_end_date']:
        base[col] = pd.to_datetime(base[col])
    for col in ['created_date', 'updated_date']:
        base[col] = base[col].dt.tz_localize(None)

    base['calculated_overdue'] = compute_target(base)
    base['planned_duration'] = compute_planned_duration(base)
    base['creation_to_planned_start'] = compute_creation_to_planned_start(base)
    base['days_since_update'] = compute_days_since_update(base)
    base['halfway_date'] = compute_halfway_date(base)

    time_feats = compute_created_time_features(base)
    base = pd.concat([base, time_feats], axis=1)

    print(f'Overdue rate: {base["calculated_overdue"].mean():.2%}')
    return base


def load_revisions(engine, base):
    sql = """
        SELECT
            history_relation_id AS task_id,
            COUNT(*) AS num_revisions,
            MAX(history_date) AS last_revision
        FROM tasks_task_history
        WHERE history_relation_id IS NOT NULL
        GROUP BY history_relation_id
    """
    rev = q(sql, engine)
    rev['last_revision'] = rev['last_revision'].dt.tz_localize(None)

    task_age_map = (pd.Timestamp.today().normalize() - base.set_index('id')['created_date']).dt.days
    rev['task_age_days'] = rev['task_id'].map(task_age_map).fillna(0).clip(lower=1)
    rev['revision_frequency'] = rev['num_revisions'] / rev['task_age_days']
    rev['revision_recency'] = (pd.Timestamp.today().normalize() - rev['last_revision']).dt.days

    base = base.merge(
        rev[['task_id', 'num_revisions', 'revision_frequency', 'revision_recency']],
        left_on='id', right_on='task_id', how='left'
    )
    base['num_revisions'] = base['num_revisions'].fillna(0).astype(int)
    base['revision_frequency'] = base['revision_frequency'].fillna(0)
    base['revision_recency'] = base['revision_recency'].fillna(0)
    base.drop(columns=['task_id'], inplace=True)
    return base


def load_subtasks(engine, base):
    sql = """
        SELECT
            task_id,
            COUNT(*) AS num_subtasks,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS num_completed_subtasks,
            SUM(CASE WHEN is_overdue = TRUE THEN 1 ELSE 0 END) AS num_overdue_subtasks
        FROM tasks_sub_task
        WHERE task_id IS NOT NULL
        GROUP BY task_id
    """
    sub = q(sql, engine)
    sub['subtask_completion_pct'] = (
        sub['num_completed_subtasks'] / sub['num_subtasks']
    ).fillna(0)
    sub['subtask_overdue_rate'] = (
        sub['num_overdue_subtasks'] / sub['num_subtasks']
    ).fillna(0)

    base = base.merge(
        sub[['task_id', 'num_subtasks', 'subtask_completion_pct', 'subtask_overdue_rate']],
        left_on='id', right_on='task_id', how='left'
    )
    base['has_subtasks'] = (base['num_subtasks'] > 0).astype(int)
    base['num_subtasks'] = base['num_subtasks'].fillna(0).astype(int)
    base['subtask_completion_pct'] = base['subtask_completion_pct'].fillna(0)
    base['subtask_overdue_rate'] = base['subtask_overdue_rate'].fillna(0)
    base.drop(columns=['task_id'], inplace=True)
    return base


def load_subtask_halfway(engine, base):
    sql = """
        WITH task_halfway AS (
            SELECT id AS task_id,
                   start_date + (end_date - start_date) / 2 AS halfway_date
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
        )
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
    """
    hw = q(sql, engine)
    hw['subtask_completion_pct_at_halfway'] = (
        hw['num_completed_at_halfway'] / hw['num_subtasks_at_halfway']
    ).fillna(0)

    base = base.merge(
        hw[['task_id', 'subtask_completion_pct_at_halfway']],
        left_on='id', right_on='task_id', how='left'
    )
    base['subtask_completion_pct_at_halfway'] = base['subtask_completion_pct_at_halfway'].fillna(0)
    base.drop(columns=['task_id'], inplace=True)
    return base


def load_challenges(engine, base):
    sql = """
        SELECT tcg.task_id, COUNT(*) AS num_challenges
        FROM tasks_task_challenge_groups tcg
        WHERE tcg.task_id IS NOT NULL
        GROUP BY tcg.task_id
    """
    ch = q(sql, engine)
    ch['has_challenges'] = 1
    base = base.merge(
        ch[['task_id', 'num_challenges', 'has_challenges']],
        left_on='id', right_on='task_id', how='left'
    )
    base['num_challenges'] = base['num_challenges'].fillna(0).astype(int)
    base['has_challenges'] = base['has_challenges'].fillna(0).astype(int)
    base.drop(columns=['task_id'], inplace=True)
    return base


def load_department_aggregates(engine, base):
    dept_sql = """
        SELECT
            COALESCE(p.department_id, t.department_id) AS dept_id,
            COUNT(*) AS dept_task_count,
            AVG(CASE
                WHEN t.status = 'completed' AND t.actual_end_date > t.end_date THEN 1
                WHEN t.status NOT IN ('completed','terminated','archived')
                     AND t.end_date < CURRENT_DATE THEN 1
                ELSE 0
            END) AS dept_past_overdue_rate,
            AVG(COALESCE(rev_cnt.num_revisions, 0)) AS dept_avg_revisions
        FROM tasks_task t
        LEFT JOIN basedata_position p ON p.id = t.position_id
        LEFT JOIN (
            SELECT history_relation_id AS task_id, COUNT(*) AS num_revisions
            FROM tasks_task_history WHERE history_relation_id IS NOT NULL
            GROUP BY history_relation_id
        ) rev_cnt ON rev_cnt.task_id = t.id
        GROUP BY COALESCE(p.department_id, t.department_id)
    """
    dept_agg = q(dept_sql, engine)

    pos_dept = q("SELECT id AS position_id, department_id FROM basedata_position", engine)
    base['resolved_dept_id'] = base['position_id'].map(
        pos_dept.set_index('position_id')['department_id']
    ).fillna(base['department_id'])

    base = base.merge(dept_agg, left_on='resolved_dept_id', right_on='dept_id', how='left')
    base.drop(columns=['dept_id'], inplace=True)
    return base


def load_employee_aggregates(engine, base):
    emp_sql = """
        SELECT
            p.user_id AS assignee_id,
            AVG(CASE
                WHEN t.status = 'completed' AND t.actual_end_date > t.end_date THEN 1
                WHEN t.status NOT IN ('completed','terminated','archived')
                     AND t.end_date < CURRENT_DATE THEN 1
                ELSE 0
            END) AS emp_past_overdue_rate
        FROM tasks_task t
        LEFT JOIN basedata_position p ON p.id = t.position_id
        WHERE p.user_id IS NOT NULL
        GROUP BY p.user_id
    """
    emp_agg = q(emp_sql, engine)

    task_assignee = q("""
        SELECT t.id AS task_id, p.user_id AS assignee_id
        FROM tasks_task t
        LEFT JOIN basedata_position p ON p.id = t.position_id
    """, engine)
    base['assignee_id'] = base['id'].map(task_assignee.set_index('task_id')['assignee_id'])
    base = base.merge(emp_agg, on='assignee_id', how='left')
    base.drop(columns=['assignee_id'], inplace=True)
    return base


def load_position_aggregates(engine, base):
    pos_sql = """
        SELECT
            t.position_id,
            AVG(CASE
                WHEN t.status = 'completed' AND t.actual_end_date > t.end_date THEN 1
                WHEN t.status NOT IN ('completed','terminated','archived')
                     AND t.end_date < CURRENT_DATE THEN 1
                ELSE 0
            END) AS pos_past_overdue_rate
        FROM tasks_task t
        WHERE t.position_id IS NOT NULL
        GROUP BY t.position_id
    """
    pos_agg = q(pos_sql, engine)
    base = base.merge(pos_agg, on='position_id', how='left')
    return base


def load_cross_dept(engine, base):
    sql = """
        SELECT t.id AS task_id, 1 AS cross_dept_pair_exists
        FROM tasks_task t
        JOIN tasks_cross_department_assignments cda
          ON cda.id = t.derived_from_cross_department_assignment_id
    """
    cd = q(sql, engine)
    base = base.merge(cd, left_on='id', right_on='task_id', how='left')
    base['cross_dept_pair_exists'] = base['cross_dept_pair_exists'].fillna(0).astype(int)
    base.drop(columns=['task_id'], inplace=True)
    return base


def load_ma_info(engine, base):
    ma = q("""
        SELECT ma.id AS major_activity_id, ma.status AS ma_status,
               ma.approval_status AS ma_approval_status, ma.kpi_id
        FROM tasks_major_activity ma
    """, engine)
    base = base.merge(ma, on='major_activity_id', how='left')
    return base


def load_ma_revisions(engine, base):
    sql = """
        SELECT id AS major_activity_id, COUNT(*) AS num_ma_revisions
        FROM tasks_major_activity_history
        WHERE id IS NOT NULL
        GROUP BY id
    """
    mar = q(sql, engine)
    base = base.merge(mar, on='major_activity_id', how='left')
    base['num_ma_revisions'] = base['num_ma_revisions'].fillna(0).astype(int)
    return base


def load_kpi_features(engine, base):
    kpi = q("""
        SELECT kpi.id AS kpi_id, kpi.is_overdue AS kpi_is_overdue, kpi.status AS kpi_status
        FROM tasks_kpi kpi
    """, engine)
    kpi['kpi_is_overdue_flag'] = kpi['kpi_is_overdue'].astype(int)
    kpi['kpi_status_ordinal'] = kpi['kpi_status'].map(KPI_STATUS_ORDER).fillna(1).astype(int)
    base = base.merge(
        kpi[['kpi_id', 'kpi_is_overdue_flag', 'kpi_status_ordinal']],
        on='kpi_id', how='left'
    )
    base['kpi_is_overdue_flag'] = base['kpi_is_overdue_flag'].fillna(0).astype(int)
    base['kpi_status_ordinal'] = base['kpi_status_ordinal'].fillna(1).astype(int)
    return base


def load_kpi_revisions(engine, base):
    sql = "SELECT id AS kpi_id, COUNT(*) AS num_kpi_revisions FROM tasks_kpi_history WHERE id IS NOT NULL GROUP BY id"
    kph = q(sql, engine)
    base = base.merge(kph, on='kpi_id', how='left')
    base['num_kpi_revisions'] = base['num_kpi_revisions'].fillna(0).astype(int)
    return base


def load_subtask_challenges(engine, base):
    sql = """
        SELECT stcg.subtask_id AS sub_task_id, st.task_id
        FROM tasks_sub_task_challenge_groups stcg
        JOIN tasks_sub_task st ON st.id = stcg.subtask_id
    """
    sc = q(sql, engine)
    task_sub_chal = sc.groupby('task_id').agg(
        has_subtask_challenge=('sub_task_id', lambda x: 1),
        num_subtask_challenges=('sub_task_id', 'count'),
    ).reset_index()
    base = base.merge(task_sub_chal, left_on='id', right_on='task_id', how='left')
    base['has_subtask_challenge'] = base['has_subtask_challenge'].fillna(0).astype(int)
    base['num_subtask_challenges'] = base['num_subtask_challenges'].fillna(0).astype(int)
    base.drop(columns=['task_id'], inplace=True)
    return base


def load_kpi_challenges(engine, base):
    kc = q("SELECT kpi_id, COUNT(*) AS num_kpi_challenges FROM tasks_kpis_challegne_groups GROUP BY kpi_id", engine)
    kc['has_kpi_challenge'] = 1
    base = base.merge(kc, on='kpi_id', how='left')
    base['has_kpi_challenge'] = base['has_kpi_challenge'].fillna(0).astype(int)
    base['num_kpi_challenges'] = base['num_kpi_challenges'].fillna(0).astype(int)
    return base


def load_kpi_potential_challenges(engine, base):
    kp = q("SELECT kpi_id, COUNT(*) AS num_kpi_potential_challenges FROM tasks_kpis_potential_challenge_groups GROUP BY kpi_id", engine)
    kp['has_kpi_potential_challenge'] = 1
    base = base.merge(kp, on='kpi_id', how='left')
    base['has_kpi_potential_challenge'] = base['has_kpi_potential_challenge'].fillna(0).astype(int)
    base['num_kpi_potential_challenges'] = base['num_kpi_potential_challenges'].fillna(0).astype(int)
    return base


def load_comments(engine, base):
    comments = q("SELECT object_id, content_type_id FROM comments_comment", engine)

    kpi_cmt = comments[comments['content_type_id'] == 22].groupby('object_id').size().reset_index(name='kpi_comment_count')
    kpi_cmt.rename(columns={'object_id': 'kpi_id'}, inplace=True)
    base = base.merge(kpi_cmt, on='kpi_id', how='left')
    base['kpi_comment_count'] = base['kpi_comment_count'].fillna(0).astype(int)

    ma_cmt = comments[comments['content_type_id'] == 23].groupby('object_id').size().reset_index(name='ma_comment_count')
    ma_cmt.rename(columns={'object_id': 'major_activity_id'}, inplace=True)
    base = base.merge(ma_cmt, on='major_activity_id', how='left')
    base['ma_comment_count'] = base['ma_comment_count'].fillna(0).astype(int)

    task_cmt = comments[comments['content_type_id'] == 24].groupby('object_id').size().reset_index(name='task_comment_count')
    base = base.merge(task_cmt, left_on='id', right_on='object_id', how='left')
    base['task_comment_count'] = base['task_comment_count'].fillna(0).astype(int)
    base.drop(columns=['object_id'], inplace=True)
    return base


def load_subtask_history(engine, base):
    sub_hist = q("""
        SELECT sth.id AS sub_task_id, COUNT(DISTINCT sth.status) AS num_status_changes
        FROM tasks_sub_task_history sth
        WHERE sth.id IS NOT NULL
        GROUP BY sth.id
    """, engine)
    st_map = q("SELECT id AS sub_task_id, task_id FROM tasks_sub_task WHERE task_id IS NOT NULL", engine)
    task_sub_churn = sub_hist.merge(st_map, on='sub_task_id', how='left')
    task_sub_churn_agg = task_sub_churn.groupby('task_id')['num_status_changes'].mean().reset_index(name='avg_sub_status_changes')
    base = base.merge(task_sub_churn_agg, left_on='id', right_on='task_id', how='left')
    base['avg_sub_status_changes'] = base['avg_sub_status_changes'].fillna(0)
    base.drop(columns=['task_id'], inplace=True)
    return base


def impute_features(base):
    fill_zero_features(base, FILL_ZERO_COLS)

    if 'kpi_status_ordinal' in base.columns:
        base['kpi_status_ordinal'] = base['kpi_status_ordinal'].fillna(1)

    fill_global_mean(base, FILL_MEAN_COLS)

    base['position_id'] = base['position_id'].fillna('UNKNOWN')
    return base


def encode_features(base):
    base['status_encoded'] = ordinal_encode_status(base, 'status', STATUS_ORDER)
    base['approval_status_encoded'] = ordinal_encode_status(base, 'approval_status', APR_ORDER)
    base['lead_approval_status_encoded'] = ordinal_encode_status(base, 'lead_approval_status', APR_ORDER)
    base['ma_status_encoded'] = ordinal_encode_status(base, 'ma_status', MA_STATUS_ORDER)
    base['ma_approval_status_encoded'] = ordinal_encode_status(base, 'ma_approval_status', APR_ORDER)

    wl_dummies = pd.get_dummies(base['weight_level'], prefix='wl')
    base = pd.concat([base, wl_dummies], axis=1)

    base['position_id_encoded'] = target_encode(
        base, 'position_id', 'calculated_overdue',
        unknown_value=base['calculated_overdue'].mean()
    )
    return base


def build_dataset(engine):
    print('=== Loading base tasks ===')
    base = load_base_tasks(engine)
    base = compute_derived_features(base)

    print('=== Loading revisions ===')
    base = load_revisions(engine, base)

    print('=== Loading subtasks ===')
    base = load_subtasks(engine, base)

    print('=== Loading subtask halfway completion ===')
    base = load_subtask_halfway(engine, base)

    print('=== Loading challenges ===')
    base = load_challenges(engine, base)

    print('=== Loading department aggregates ===')
    base = load_department_aggregates(engine, base)

    print('=== Loading employee aggregates ===')
    base = load_employee_aggregates(engine, base)

    print('=== Loading position aggregates ===')
    base = load_position_aggregates(engine, base)

    print('=== Loading cross-dept flags ===')
    base = load_cross_dept(engine, base)

    print('=== Loading MA info ===')
    base = load_ma_info(engine, base)

    print('=== Loading MA revisions ===')
    base = load_ma_revisions(engine, base)

    print('=== Loading KPI features ===')
    base = load_kpi_features(engine, base)

    print('=== Loading KPI revisions ===')
    base = load_kpi_revisions(engine, base)

    print('=== Loading subtask challenges ===')
    base = load_subtask_challenges(engine, base)

    print('=== Loading KPI challenges ===')
    base = load_kpi_challenges(engine, base)

    print('=== Loading KPI potential challenges ===')
    base = load_kpi_potential_challenges(engine, base)

    print('=== Loading comments ===')
    base = load_comments(engine, base)

    print('=== Loading subtask history ===')
    base = load_subtask_history(engine, base)

    print('=== Imputing ===')
    base = impute_features(base)

    print('=== Encoding ===')
    base = encode_features(base)

    print(f'After encoding: {base.shape[1]} cols')

    # Build final dataset
    wl_cols = [c for c in base.columns if c.startswith('wl_')]
    final_features = [f for f in FINAL_FEATURES if f in base.columns]
    final_features = [f for f in final_features]  # resolve wl_* dynamically
    final_features = [f if not f.startswith('wl_') else f for f in final_features]
    # Replace wl_* with dynamic resolution
    final_features_clean = []
    for f in final_features:
        if f == '*[c for c in base.columns if c.startswith(\'wl_\')]' or f.startswith('wl_*'):
            final_features_clean.extend(wl_cols)
        else:
            final_features_clean.append(f)
    if not final_features_clean:
        final_features_clean = final_features

    # Filter to existing columns
    dataset = base[['id', 'calculated_overdue'] + [c for c in final_features_clean if c in base.columns]].copy()

    print(f'Final dataset shape: {dataset.shape}')
    print(f'Features: {len([c for c in final_features_clean if c in base.columns])}')
    print(f'Target distribution:\n{dataset["calculated_overdue"].value_counts(normalize=True)}')

    # Build prediction-time variants
    features_at_assignment = [c for c in FEATURES_AT_ASSIGNMENT if c in dataset.columns]
    features_at_halfway = [c for c in FEATURES_AT_HALFWAY if c in dataset.columns]
    # Add wl_* to assignment features
    wl_in_dataset = [c for c in wl_cols if c in dataset.columns]
    features_at_assignment = [f for f in features_at_assignment if not f.startswith('wl_')] + wl_in_dataset
    features_at_halfway = [f for f in features_at_halfway if not f.startswith('wl_')] + wl_in_dataset

    dataset_at_assignment = dataset[['id', 'calculated_overdue'] + features_at_assignment].copy()
    dataset_at_halfway = dataset[['id', 'calculated_overdue'] + features_at_halfway].copy()

    print(f'Assignment dataset shape: {dataset_at_assignment.shape}')
    print(f'Halfway dataset shape: {dataset_at_halfway.shape}')

    return dataset, dataset_at_assignment, dataset_at_halfway


def main():
    parser = argparse.ArgumentParser(description='Build PMS overdue prediction dataset')
    parser.add_argument('--output-dir', default='.', help='Directory to save CSV files')
    args = parser.parse_args()

    engine = create_engine(DB_URL)
    dataset, ds_creation, ds_halfway = build_dataset(engine)

    os.makedirs(args.output_dir, exist_ok=True)
    ds_creation.to_csv(os.path.join(args.output_dir, 'dataset_at_creation.csv'), index=False)
    ds_halfway.to_csv(os.path.join(args.output_dir, 'dataset_at_halfway.csv'), index=False)
    print(f'Saved to {args.output_dir}/')


if __name__ == '__main__':
    main()
