import pytest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
SQL_DIR = PROJECT_ROOT / "sql"
DOCS_DIR = PROJECT_ROOT / "docs"

CREATION_COLS = [
    "id", "calculated_overdue",
    "status_encoded", "approval_status_encoded", "lead_approval_status_encoded",
    "ma_status_encoded", "ma_approval_status_encoded",
    "planned_duration", "creation_to_planned_start",
    "created_dow", "created_is_weekend", "created_is_friday", "created_month", "created_quarter",
    "is_planned", "risk_mapping",
    "wl_high", "wl_low", "wl_mid",
    "is_cross_dept", "cross_dept_pair_exists",
    "num_ma_revisions",
    "kpi_is_overdue_flag", "kpi_status_ordinal", "num_kpi_revisions",
    "has_kpi_challenge", "num_kpi_challenges",
    "has_kpi_potential_challenge", "num_kpi_potential_challenges",
    "kpi_comment_count", "ma_comment_count",
    "dept_past_overdue_rate", "dept_avg_revisions",
    "emp_past_overdue_rate", "pos_past_overdue_rate",
    "position_id_encoded",
]

HALFWAY_EXTRA = [
    "days_since_update", "num_revisions", "revision_frequency", "revision_recency",
    "num_subtasks", "has_subtasks", "subtask_completion_pct", "subtask_overdue_rate",
    "subtask_completion_pct_at_halfway",
    "num_challenges", "has_challenges",
    "has_subtask_challenge", "num_subtask_challenges",
    "avg_sub_status_changes", "task_comment_count",
]


# ── CSV Dataset Tests ──────────────────────────────────────────────────────

class TestCreationDataset:
    def test_csv_exists(self):
        assert (DATA_DIR / "dataset_at_creation.csv").exists()

    def test_shape(self):
        import pandas as pd
        df = pd.read_csv(DATA_DIR / "dataset_at_creation.csv")
        assert df.shape == (13895, 36), f"Expected (13895, 36), got {df.shape}"

    def test_columns(self):
        import pandas as pd
        df = pd.read_csv(DATA_DIR / "dataset_at_creation.csv")
        assert list(df.columns) == CREATION_COLS

    def test_no_duplicate_ids(self):
        import pandas as pd
        df = pd.read_csv(DATA_DIR / "dataset_at_creation.csv")
        assert df["id"].is_unique, "Duplicate task IDs found"

    def test_no_nulls(self):
        import pandas as pd
        df = pd.read_csv(DATA_DIR / "dataset_at_creation.csv")
        assert df.isnull().sum().sum() == 0, f"Found {df.isnull().sum().sum()} nulls"

    def test_target_rate(self):
        import pandas as pd
        df = pd.read_csv(DATA_DIR / "dataset_at_creation.csv")
        rate = df["calculated_overdue"].mean()
        assert 0.19 <= rate <= 0.22, f"Target rate {rate:.4f} outside expected 0.19–0.22"

    def test_target_binary(self):
        import pandas as pd
        df = pd.read_csv(DATA_DIR / "dataset_at_creation.csv")
        assert set(df["calculated_overdue"].unique()).issubset({0, 1})

    def test_feature_count(self):
        import pandas as pd
        df = pd.read_csv(DATA_DIR / "dataset_at_creation.csv")
        feature_cols = [c for c in df.columns if c not in ("id", "calculated_overdue")]
        assert len(feature_cols) == 34, f"Expected 34 features, got {len(feature_cols)}"


class TestHalfwayDataset:
    def test_csv_exists(self):
        assert (DATA_DIR / "dataset_at_halfway.csv").exists()

    def test_shape(self):
        import pandas as pd
        df = pd.read_csv(DATA_DIR / "dataset_at_halfway.csv")
        assert df.shape == (13895, 51), f"Expected (13895, 51), got {df.shape}"

    def test_contains_all_creation_columns(self):
        import pandas as pd
        df = pd.read_csv(DATA_DIR / "dataset_at_halfway.csv")
        for col in CREATION_COLS:
            assert col in df.columns, f"Missing creation column: {col}"

    def test_has_exactly_15_extra_columns(self):
        import pandas as pd
        df = pd.read_csv(DATA_DIR / "dataset_at_halfway.csv")
        extra = [c for c in df.columns if c not in CREATION_COLS]
        assert len(extra) == 15, f"Expected 15 extra cols, got {len(extra)}: {extra}"

    def test_extra_columns_match_expected(self):
        import pandas as pd
        df = pd.read_csv(DATA_DIR / "dataset_at_halfway.csv")
        extra = [c for c in df.columns if c not in CREATION_COLS]
        assert set(extra) == set(HALFWAY_EXTRA), f"Mismatch: {set(extra) ^ set(HALFWAY_EXTRA)}"

    def test_no_duplicate_ids(self):
        import pandas as pd
        df = pd.read_csv(DATA_DIR / "dataset_at_halfway.csv")
        assert df["id"].is_unique, "Duplicate task IDs found"

    def test_no_nulls(self):
        import pandas as pd
        df = pd.read_csv(DATA_DIR / "dataset_at_halfway.csv")
        assert df.isnull().sum().sum() == 0, f"Found {df.isnull().sum().sum()} nulls"

    def test_same_ids_as_creation(self):
        import pandas as pd
        df_c = pd.read_csv(DATA_DIR / "dataset_at_creation.csv")
        df_h = pd.read_csv(DATA_DIR / "dataset_at_halfway.csv")
        assert set(df_c["id"]) == set(df_h["id"]), "ID sets differ between datasets"

    def test_target_rate_matches_creation(self):
        import pandas as pd
        df = pd.read_csv(DATA_DIR / "dataset_at_halfway.csv")
        assert df["calculated_overdue"].mean() == pytest.approx(0.201, abs=0.01)


# ── SQL File Tests ─────────────────────────────────────────────────────────

class TestAnalyticalDatasetSQL:
    def test_file_exists(self):
        assert (SQL_DIR / "analytical_dataset.sql").exists()

    def test_file_not_empty(self):
        content = (SQL_DIR / "analytical_dataset.sql").read_text()
        assert len(content.strip()) > 500

    def test_has_minimum_ctes(self):
        content = (SQL_DIR / "analytical_dataset.sql").read_text()
        cte_count = content.count(" AS (")
        assert cte_count >= 10, f"Expected >=10 CTEs, found {cte_count}"

    def test_selects_from_base(self):
        content = (SQL_DIR / "analytical_dataset.sql").read_text()
        assert "FROM base" in content.upper() or "from base" in content.lower()

    def test_ends_with_select_and_order_by(self):
        content = (SQL_DIR / "analytical_dataset.sql").read_text().strip()
        lines = content.splitlines()
        last_block = "\n".join(lines[-20:]).upper()
        assert "SELECT" in last_block
        assert "ORDER BY" in last_block

    def test_references_tasks_task(self):
        content = (SQL_DIR / "analytical_dataset.sql").read_text().lower()
        assert "tasks_task" in content

    def test_references_basedata_position(self):
        content = (SQL_DIR / "analytical_dataset.sql").read_text().lower()
        assert "basedata_position" in content

    def test_references_sub_task_history(self):
        content = (SQL_DIR / "analytical_dataset.sql").read_text().lower()
        assert "sub_task_history" in content or "tasks_sub_task_history" in content


class TestDataQualitySQL:
    def test_file_exists(self):
        assert (SQL_DIR / "data_quality_checks.sql").exists()

    def test_file_not_empty(self):
        content = (SQL_DIR / "data_quality_checks.sql").read_text()
        assert len(content.strip()) > 500

    def test_has_minimum_selects(self):
        content = (SQL_DIR / "data_quality_checks.sql").read_text()
        select_count = content.upper().count("SELECT ")
        assert select_count >= 15, f"Expected >=15 SELECTs, found {select_count}"

    def test_has_check_name_column(self):
        content = (SQL_DIR / "data_quality_checks.sql").read_text().lower()
        assert "check_name" in content

    def test_has_status_column(self):
        content = (SQL_DIR / "data_quality_checks.sql").read_text().lower()
        assert "status" in content

    def test_first_check_name(self):
        content = (SQL_DIR / "data_quality_checks.sql").read_text().lower()
        assert "row_count_tasks_task" in content


# ── Documentation Tests ───────────────────────────────────────────────────

class TestHandoffH1:
    def test_file_exists(self):
        assert (DOCS_DIR / "handoff_H1.md").exists()

    def test_file_not_empty(self):
        content = (DOCS_DIR / "handoff_H1.md").read_text()
        assert len(content.strip()) > 1000

    def test_has_expected_sections(self):
        content = (DOCS_DIR / "handoff_H1.md").read_text()
        sections = ["Dataset Schema", "Data Sources", "Feature Inventory", "Target Definition",
                     "Imputation Strategy", "Join Strategy"]
        found = [s for s in sections if s.lower() in content.lower() or s in content]
        assert len(found) >= 4, f"Only found {len(found)}/6 expected sections: {found}"

    def test_lists_features(self):
        content = (DOCS_DIR / "handoff_H1.md").read_text()
        assert "planned_duration" in content
        assert "calculated_overdue" in content
        assert "position_id_encoded" in content

    def test_mentions_imputation(self):
        content = (DOCS_DIR / "handoff_H1.md").read_text().lower()
        assert "imput" in content


class TestHandoffH2:
    def test_file_exists(self):
        assert (DOCS_DIR / "handoff_H2.md").exists()

    def test_file_not_empty(self):
        content = (DOCS_DIR / "handoff_H2.md").read_text()
        assert len(content.strip()) > 500

    def test_has_expected_sections(self):
        content = (DOCS_DIR / "handoff_H2.md").read_text().lower()
        terms = ["relationship", "join", "foreign key", "primary key", "halfway"]
        found = [t for t in terms if t in content]
        assert len(found) >= 3, f"Only found {len(found)}/5 key terms: {found}"

    def test_mentions_department_resolution(self):
        content = (DOCS_DIR / "handoff_H2.md").read_text().lower()
        assert "department" in content or "dept" in content


class TestHandoffH5:
    def test_file_exists(self):
        assert (DOCS_DIR / "handoff_H5.md").exists()

    def test_file_not_empty(self):
        content = (DOCS_DIR / "handoff_H5.md").read_text()
        assert len(content.strip()) > 500

    def test_has_expected_sections(self):
        content = (DOCS_DIR / "handoff_H5.md").read_text().lower()
        terms = ["row count", "null", "duplicate", "integrity", "sparsity"]
        found = [t for t in terms if t in content]
        assert len(found) >= 3, f"Only found {len(found)}/5 key terms: {found}"

    def test_mentions_recommendation(self):
        content = (DOCS_DIR / "handoff_H5.md").read_text().lower()
        assert "recommendation" in content or "recommend" in content
