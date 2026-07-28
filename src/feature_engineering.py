"""Feature creation functions for PMS task overdue prediction.

Mirrors the logic in notebooks/clean_and_build_dataset.ipynb exactly.
Each function operates on a DataFrame and returns a Series or DataFrame.

Usage:
    from src.feature_engineering import compute_target, compute_temporal_features
"""

import pandas as pd
import numpy as np

FIXED_CUTOFF = pd.Timestamp('2026-07-14')


def compute_target(df, first_completed=None):
    """Compute calculated_overdue target and target_source using three-tier logic.

    Tier 1: actual_end_date exists -> compare directly to end_date.
    Tier 2: no actual_end_date, but history shows status='completed' ->
            use first_completed_at (first occurrence) as completion date.
    Tier 3: no actual_end_date, no history -> use updated_date as proxy.

    Returns:
        DataFrame with columns [calculated_overdue, target_source]
    """
    cutoff = FIXED_CUTOFF.normalize()
    completed = df['status'] == 'completed'
    has_actual = df['actual_end_date'].notna()

    # Ensure all date columns are tz-naive datetime64 to avoid mixing tz-aware/naive
    for col in ['actual_end_date', 'end_date', 'updated_date']:
        ser = pd.to_datetime(df[col], errors='coerce')
        if hasattr(ser.dt, 'tz') and ser.dt.tz is not None:
            df[col] = ser.dt.tz_localize(None)
        else:
            df[col] = ser

    # Infer completion date: actual_end_date > first_completed_at > updated_date
    completion_date = df['actual_end_date'].copy()
    if first_completed is not None:
        fc_map = first_completed.set_index('task_id')['first_completed_at']
        completion_date = completion_date.fillna(
            fc_map.dt.tz_localize(None).dt.normalize()
        )
    completion_date = completion_date.fillna(df['updated_date'].dt.normalize())

    end_date = df['end_date']

    # Source per row
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
    """creation_to_planned_start = start_date - created_date (in days).

    Negative values mean the task started before it was formally created
    (retroactive scheduling). Positive values mean planning ahead.
    """
    return (df['start_date'] - df['created_date']).dt.days


def compute_days_since_update(df):
    """days_since_update = cutoff - updated_date (in days).

    Uses fixed cutoff date (2026-07-14) as reference for reproducibility.
    """
    return (FIXED_CUTOFF.normalize() - df['updated_date']).dt.days


def compute_halfway_date(df):
    """halfway_date = start_date + planned_duration / 2.

    Used as prediction point for the halfway model variant.
    """
    duration = compute_planned_duration(df)
    return df['start_date'] + pd.to_timedelta(duration / 2, unit='D')


def compute_created_time_features(df):
    """Derive dayofweek, weekend, friday, month, quarter from created_date.

    Returns:
        DataFrame with columns: created_dow, created_is_weekend,
        created_is_friday, created_month, created_quarter
    """
    dow = df['created_date'].dt.dayofweek
    return pd.DataFrame({
        'created_dow': dow,
        'created_is_weekend': (dow >= 5).astype(int),
        'created_is_friday': (dow == 4).astype(int),
        'created_month': df['created_date'].dt.month,
        'created_quarter': df['created_date'].dt.quarter,
    })


def compute_revision_features(rev_df, task_age_map):
    """Compute revision_frequency and revision_recency.

    Args:
        rev_df: DataFrame with columns [task_id, num_revisions, last_revision]
        task_age_map: Series mapping task_id -> age in days (from created_date)

    Returns:
        DataFrame with columns [task_id, num_revisions, revision_frequency, revision_recency]
    """
    result = rev_df.copy()
    result['task_age_days'] = result['task_id'].map(task_age_map).fillna(0).clip(lower=1)
    result['revision_frequency'] = result['num_revisions'] / result['task_age_days']
    result['revision_recency'] = (
        FIXED_CUTOFF.normalize() - result['last_revision']
    ).dt.days
    return result[['task_id', 'num_revisions', 'revision_frequency', 'revision_recency']]


def compute_subtask_features(sub_df):
    """Compute subtask completion pct and overdue rate.

    Args:
        sub_df: DataFrame with columns [task_id, num_subtasks,
                num_completed_subtasks, num_overdue_subtasks]

    Returns:
        DataFrame with computed rates added.
    """
    result = sub_df.copy()
    result['subtask_completion_pct'] = (
        result['num_completed_subtasks'] / result['num_subtasks']
    ).fillna(0)
    result['subtask_overdue_rate'] = (
        result['num_overdue_subtasks'] / result['num_subtasks']
    ).fillna(0)
    return result


def compute_subtask_halfway_features(halfway_sub_df):
    """Compute subtask_completion_pct_at_halfway.

    Args:
        halfway_sub_df: DataFrame with columns [task_id, num_subtasks_at_halfway,
                         num_completed_at_halfway]

    Returns:
        DataFrame with subtask_completion_pct_at_halfway added.
    """
    result = halfway_sub_df.copy()
    result['subtask_completion_pct_at_halfway'] = (
        result['num_completed_at_halfway'] / result['num_subtasks_at_halfway']
    ).fillna(0)
    return result


def ordinal_encode_status(df, col, mapping, fallback=1):
    """Apply ordinal encoding with fallback for nulls/unseen values."""
    return df[col].map(mapping).fillna(fallback)


def target_encode(df, group_col, target_col, unknown_value=None):
    """Target encode a categorical column.

    Returns:
        Series: encoded values, one per row of df.
    """
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
