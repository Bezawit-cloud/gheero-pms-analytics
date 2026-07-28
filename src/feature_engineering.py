"""Feature creation and preprocessing functions for PMS task overdue prediction.

Mirrors the logic in clean datasets and modeling notebooks.
Each function operates on a DataFrame and returns a Series or DataFrame.
"""

import pandas as pd
import numpy as np

FIXED_CUTOFF = pd.Timestamp('2026-07-14')


def preprocess_clean_creation_features(df_input):
    """Preprocess features for Creation Checkpoint (T0)."""
    df = df_input.copy()

    if 'planned_duration' in df.columns:
        df['planned_duration'] = df['planned_duration'].clip(lower=0)

    cols_to_drop = [
        'id', 'target_source', 'status_encoded', 'approval_status_encoded',
        'lead_approval_status_encoded', 'ma_status_encoded', 'ma_approval_status_encoded',
        'created_is_weekend', 'created_is_friday'
    ]
    return df.drop(columns=[c for c in cols_to_drop if c in df.columns], errors='ignore')


def preprocess_clean_halfway_features(df_input):
    """Preprocess features for Halfway Checkpoint (Tmid)."""
    df = df_input.copy()

    if 'planned_duration' in df.columns:
        df['planned_duration'] = df['planned_duration'].clip(lower=0)

    if 'num_ma_revisions' in df.columns:
        df['num_ma_revisions'] = df['num_ma_revisions'].clip(upper=78)
    if 'num_revisions' in df.columns:
        df['num_revisions'] = df['num_revisions'].clip(upper=9)

    if 'planned_duration' in df.columns and 'num_revisions' in df.columns:
        df['duration_revision_intensity'] = df['num_revisions'] / (df['planned_duration'] + 1)

    cols_to_drop = [
        'id', 'target_source', 'status_encoded', 'approval_status_encoded',
        'lead_approval_status_encoded', 'ma_status_encoded', 'ma_approval_status_encoded',
        'subtask_completion_pct', 'subtask_overdue_rate', 'created_is_weekend', 'created_is_friday'
    ]
    return df.drop(columns=[c for c in cols_to_drop if c in df.columns], errors='ignore')


def compute_target(df, first_completed=None):
    """Compute calculated_overdue target and target_source using three-tier logic."""
    cutoff = FIXED_CUTOFF.normalize()
    completed = df['status'] == 'completed'
    has_actual = df['actual_end_date'].notna()

    for col in ['actual_end_date', 'end_date', 'updated_date']:
        ser = pd.to_datetime(df[col], errors='coerce')
        if hasattr(ser.dt, 'tz') and ser.dt.tz is not None:
            df[col] = ser.dt.tz_localize(None)
        else:
            df[col] = ser

    completion_date = df['actual_end_date'].copy()
    if first_completed is not None:
        fc_map = first_completed.set_index('task_id')['first_completed_at']
        completion_date = completion_date.fillna(
            fc_map.dt.tz_localize(None).dt.normalize()
        )
    completion_date = completion_date.fillna(df['updated_date'].dt.normalize())
    end_date = df['end_date']

    target_source = np.select(
        [
            completed & has_actual,
            completed & ~has_actual & (df['first_completed_at'].notna() if first_completed is not None else False),
            completed & ~has_actual & (df['first_completed_at'].isna() if first_completed is not None else True),
            ~df['status'].isin(['completed', 'terminated', 'archived']) & (end_date < cutoff),
        ],
        [
            'actual_end_date',
            'history_completion',
            'updated_date',
            'open_task',
        ],
        default='status_based'
    )

    overdue_flag = np.where(
        completed & (completion_date > end_date),
        1,
        np.where(
            ~df['status'].isin(['completed', 'terminated', 'archived'])
            & (end_date < cutoff),
            1, 0
        )
    )

    return pd.DataFrame({
        'calculated_overdue': overdue_flag,
        'target_source': target_source,
    })


def compute_planned_duration(df):
    """planned_duration = end_date - start_date (in days)."""
    return (df['end_date'] - df['start_date']).dt.days


def compute_creation_to_planned_start(df):
    """creation_to_planned_start = start_date - created_date (in days)."""
    return (df['start_date'] - df['created_date']).dt.days


def compute_days_since_update(df):
    """days_since_update = cutoff - updated_date (in days)."""
    return (FIXED_CUTOFF.normalize() - df['updated_date']).dt.days


def compute_halfway_date(df):
    """halfway_date = start_date + planned_duration / 2."""
    duration = compute_planned_duration(df)
    return df['start_date'] + pd.to_timedelta(duration / 2, unit='D')


def compute_created_time_features(df):
    """Derive dow, weekend, friday, month, quarter from created_date."""
    dow = df['created_date'].dt.dayofweek
    return pd.DataFrame({
        'created_dow': dow,
        'created_is_weekend': (dow >= 5).astype(int),
        'created_is_friday': (dow == 4).astype(int),
        'created_month': df['created_date'].dt.month,
        'created_quarter': df['created_date'].dt.quarter,
    })


def compute_revision_features(rev_df, task_age_map):
    """Compute revision_frequency and revision_recency."""
    result = rev_df.copy()
    result['task_age_days'] = result['task_id'].map(task_age_map).fillna(0).clip(lower=1)
    result['revision_frequency'] = result['num_revisions'] / result['task_age_days']
    result['revision_recency'] = (
        FIXED_CUTOFF.normalize() - result['last_revision']
    ).dt.days
    return result[['task_id', 'num_revisions', 'revision_frequency', 'revision_recency']]


def compute_subtask_features(sub_df):
    """Compute subtask completion pct and overdue rate."""
    result = sub_df.copy()
    result['subtask_completion_pct'] = (
        result['num_completed_subtasks'] / result['num_subtasks']
    ).fillna(0)
    result['subtask_overdue_rate'] = (
        result['num_overdue_subtasks'] / result['num_subtasks']
    ).fillna(0)
    return result


def compute_subtask_halfway_features(halfway_sub_df):
    """Compute subtask_completion_pct_at_halfway."""
    result = halfway_sub_df.copy()
    result['subtask_completion_pct_at_halfway'] = (
        result['num_completed_at_halfway'] / result['num_subtasks_at_halfway']
    ).fillna(0)
    return result


def ordinal_encode_status(df, col, mapping, fallback=1):
    """Apply ordinal encoding with fallback for nulls/unseen values."""
    return df[col].map(mapping).fillna(fallback)


def target_encode(df, group_col, target_col, unknown_value=None):
    """Target encode a categorical column."""
    rates = df.groupby(group_col)[target_col].mean()
    encoded = df[group_col].map(rates)
    if unknown_value is not None:
        encoded = encoded.fillna(unknown_value)
    return encoded


def fill_zero_features(df, feature_list):
    """Fill NaN with 0 for features where absence means no signal."""
    for col in feature_list:
        if col in df.columns:
            df[col] = df[col].fillna(0)
    return df


def fill_global_mean(df, feature_list):
    """Fill NaN with the column's global mean."""
    for col in feature_list:
        if col in df.columns:
            df[col] = df[col].fillna(df[col].mean())
    return df
