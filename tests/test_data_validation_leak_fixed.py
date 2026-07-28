import pytest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "v1"

CREATION_COLS = [
    "id", "calculated_overdue", "target_source",
    "planned_duration", "creation_to_planned_start",
    "created_dow", "created_is_weekend", "created_is_friday", "created_month", "created_quarter",
    "is_planned", "risk_mapping",
    "is_cross_dept", "cross_dept_pair_exists",
    "dept_past_overdue_rate", "dept_avg_revisions",
    "emp_past_overdue_rate", "pos_past_overdue_rate",
    "status_encoded", "approval_status_encoded", "lead_approval_status_encoded",
    "ma_status_encoded", "ma_approval_status_encoded",
    "num_ma_revisions",
    "kpi_is_overdue_flag", "kpi_status_ordinal", "num_kpi_revisions",
    "num_revisions", "revision_frequency", "revision_recency",
    "num_subtasks", "has_subtasks",
    "subtask_completion_pct", "subtask_overdue_rate",
    "task_comment_count",
    "avg_sub_status_changes",
]

HALFWAY_EXTRA = [
    "subtask_completion_pct_at_halfway",
    "days_since_update",
]

DROPPED_FEATURES = [
    "num_challenges", "has_challenges",
    "has_subtask_challenge", "num_subtask_challenges",
    "has_kpi_challenge", "num_kpi_challenges",
    "has_kpi_potential_challenge", "num_kpi_potential_challenges",
    "position_id_encoded",
]


class TestCleanCreationDataset:
    def test_csv_exists(self):
        assert (DATA_DIR / "dataset_at_creation_clean.csv").exists()

    def test_shape(self):
        import pandas as pd
        df = pd.read_csv(DATA_DIR / "dataset_at_creation_clean.csv")
        assert df.shape[0] == 13895, f"Expected 13895 rows, got {df.shape[0]}"
        expected_feats = len(CREATION_COLS) - 3
        actual_feats = len([c for c in df.columns if c not in ("id", "calculated_overdue", "target_source")])
        assert actual_feats == expected_feats, f"Expected {expected_feats} features, got {actual_feats}"

    def test_columns(self):
        import pandas as pd
        df = pd.read_csv(DATA_DIR / "dataset_at_creation_clean.csv")
        assert list(df.columns) == CREATION_COLS

    def test_no_duplicate_ids(self):
        import pandas as pd
        df = pd.read_csv(DATA_DIR / "dataset_at_creation_clean.csv")
        assert df["id"].is_unique, "Duplicate task IDs found"

    def test_no_nulls(self):
        import pandas as pd
        df = pd.read_csv(DATA_DIR / "dataset_at_creation_clean.csv")
        nulls = df.isnull().sum().sum()
        assert nulls == 0, f"Found {nulls} nulls"

    def test_target_rate(self):
        import pandas as pd
        df = pd.read_csv(DATA_DIR / "dataset_at_creation_clean.csv")
        rate = df["calculated_overdue"].mean()
        assert 0.46 <= rate <= 0.49, f"Target rate {rate:.4f} outside expected 0.46-0.49"

    def test_target_binary(self):
        import pandas as pd
        df = pd.read_csv(DATA_DIR / "dataset_at_creation_clean.csv")
        assert set(df["calculated_overdue"].unique()).issubset({0, 1})

    def test_dropped_features_absent(self):
        import pandas as pd
        df = pd.read_csv(DATA_DIR / "dataset_at_creation_clean.csv")
        for feat in DROPPED_FEATURES:
            assert feat not in df.columns, f"Dropped feature '{feat}' is still present"

    def test_status_encoded_valid_range(self):
        import pandas as pd
        df = pd.read_csv(DATA_DIR / "dataset_at_creation_clean.csv")
        invalid = df[~df["status_encoded"].isin([0, 1, 2, 3, 4])]
        assert len(invalid) == 0, f"Found {len(invalid)} invalid status_encoded values"


class TestCleanHalfwayDataset:
    def test_csv_exists(self):
        assert (DATA_DIR / "dataset_at_halfway_clean.csv").exists()

    def test_shape(self):
        import pandas as pd
        df = pd.read_csv(DATA_DIR / "dataset_at_halfway_clean.csv")
        assert df.shape[0] == 13895, f"Expected 13895 rows, got {df.shape[0]}"
        expected_feats = len(CREATION_COLS) - 3 + len(HALFWAY_EXTRA)
        actual_feats = len([c for c in df.columns if c not in ("id", "calculated_overdue", "target_source")])
        assert actual_feats == expected_feats, f"Expected {expected_feats} features, got {actual_feats}"

    def test_contains_all_creation_columns(self):
        import pandas as pd
        df = pd.read_csv(DATA_DIR / "dataset_at_halfway_clean.csv")
        for col in CREATION_COLS:
            assert col in df.columns, f"Missing creation column: {col}"

    def test_has_exactly_2_extra_columns(self):
        import pandas as pd
        df = pd.read_csv(DATA_DIR / "dataset_at_halfway_clean.csv")
        extra = [c for c in df.columns if c not in CREATION_COLS]
        assert len(extra) == len(HALFWAY_EXTRA), f"Expected {len(HALFWAY_EXTRA)} extra cols, got {len(extra)}: {extra}"

    def test_extra_columns_match_expected(self):
        import pandas as pd
        df = pd.read_csv(DATA_DIR / "dataset_at_halfway_clean.csv")
        extra = [c for c in df.columns if c not in CREATION_COLS]
        assert set(extra) == set(HALFWAY_EXTRA), f"Mismatch: {set(extra) ^ set(HALFWAY_EXTRA)}"

    def test_no_duplicate_ids(self):
        import pandas as pd
        df = pd.read_csv(DATA_DIR / "dataset_at_halfway_clean.csv")
        assert df["id"].is_unique, "Duplicate task IDs found"

    def test_no_nulls(self):
        import pandas as pd
        df = pd.read_csv(DATA_DIR / "dataset_at_halfway_clean.csv")
        nulls = df.isnull().sum().sum()
        assert nulls == 0, f"Found {nulls} nulls"

    def test_same_ids_as_creation(self):
        import pandas as pd
        df_c = pd.read_csv(DATA_DIR / "dataset_at_creation_clean.csv")
        df_h = pd.read_csv(DATA_DIR / "dataset_at_halfway_clean.csv")
        assert set(df_c["id"]) == set(df_h["id"]), "ID sets differ between datasets"

    def test_target_rate_matches_creation(self):
        import pandas as pd
        df = pd.read_csv(DATA_DIR / "dataset_at_halfway_clean.csv")
        assert df["calculated_overdue"].mean() == pytest.approx(0.478, abs=0.01)

    def test_dropped_features_absent(self):
        import pandas as pd
        df = pd.read_csv(DATA_DIR / "dataset_at_halfway_clean.csv")
        for feat in DROPPED_FEATURES:
            assert feat not in df.columns, f"Dropped feature '{feat}' is still present"


class TestLeakageValidation:
    def test_revisions_zero_at_creation(self):
        import pandas as pd
        df = pd.read_csv(DATA_DIR / "dataset_at_creation_clean.csv")
        assert (df["num_revisions"] == 0).all(), "num_revisions must be 0 at creation"

    def test_revisions_non_decreasing(self):
        import pandas as pd
        df_c = pd.read_csv(DATA_DIR / "dataset_at_creation_clean.csv")
        df_h = pd.read_csv(DATA_DIR / "dataset_at_halfway_clean.csv")
        assert (df_h["num_revisions"] >= df_c["num_revisions"]).all(), "num_revisions must not decrease"

    def test_subtasks_non_decreasing(self):
        import pandas as pd
        df_c = pd.read_csv(DATA_DIR / "dataset_at_creation_clean.csv")
        df_h = pd.read_csv(DATA_DIR / "dataset_at_halfway_clean.csv")
        assert (df_h["num_subtasks"] >= df_c["num_subtasks"]).all(), "num_subtasks must not decrease"

    def test_status_encoded_valid_range(self):
        import pandas as pd
        df_c = pd.read_csv(DATA_DIR / "dataset_at_creation_clean.csv")
        invalid = df_c[~df_c["status_encoded"].isin([0, 1, 2, 3, 4])]
        assert len(invalid) == 0, f"Found {len(invalid)} invalid status_encoded values at creation"

    def test_same_target_across_datasets(self):
        import pandas as pd
        df_c = pd.read_csv(DATA_DIR / "dataset_at_creation_clean.csv")
        df_h = pd.read_csv(DATA_DIR / "dataset_at_halfway_clean.csv")
        assert df_c["calculated_overdue"].equals(df_h["calculated_overdue"]), "Target differs between CSVs"

    def test_no_challenge_features(self):
        import pandas as pd
        df_c = pd.read_csv(DATA_DIR / "dataset_at_creation_clean.csv")
        df_h = pd.read_csv(DATA_DIR / "dataset_at_halfway_clean.csv")
        challenge_cols = [c for c in df_c.columns if 'challenge' in c.lower()]
        assert len(challenge_cols) == 0, f"Challenge features still present: {challenge_cols}"
        challenge_cols_h = [c for c in df_h.columns if 'challenge' in c.lower()]
        assert len(challenge_cols_h) == 0, f"Challenge features still present in halfway: {challenge_cols_h}"

    def test_no_position_id_encoded(self):
        import pandas as pd
        df_c = pd.read_csv(DATA_DIR / "dataset_at_creation_clean.csv")
        df_h = pd.read_csv(DATA_DIR / "dataset_at_halfway_clean.csv")
        assert "position_id_encoded" not in df_c.columns
        assert "position_id_encoded" not in df_h.columns
