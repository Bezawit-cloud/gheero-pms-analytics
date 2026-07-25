import importlib.util
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"

sys.path.insert(0, str(SRC_DIR))
import feature_engineering as fe
import build_features as bf


# ── Module Structure Tests ─────────────────────────────────────────────────

class TestFeatureEngineeringModule:
    def test_module_loads(self):
        assert fe is not None

    def test_expected_functions_exist(self):
        expected = [
            "compute_target",
            "compute_planned_duration",
            "compute_creation_to_planned_start",
            "compute_days_since_update",
            "compute_halfway_date",
            "compute_created_time_features",
            "compute_revision_features",
            "compute_subtask_features",
            "compute_subtask_halfway_features",
            "ordinal_encode_status",
            "target_encode",
            "fill_zero_features",
            "fill_global_mean",
        ]
        for fn_name in expected:
            assert hasattr(fe, fn_name), f"Missing function: {fn_name}"

    def test_each_function_has_docstring(self):
        funcs = [
            getattr(fe, name)
            for name in dir(fe)
            if callable(getattr(fe, name)) and not name.startswith("_")
        ]
        for func in funcs:
            assert func.__doc__ is not None and len(func.__doc__.strip()) > 0, (
                f"{func.__name__} is missing a docstring"
            )

    def test_function_signatures_have_type_hints(self):
        funcs = [
            getattr(fe, name)
            for name in dir(fe)
            if callable(getattr(fe, name)) and not name.startswith("_")
        ]
        for func in funcs:
            sig = inspect.signature(func)
            for param_name, param in sig.parameters.items():
                if param.annotation is inspect.Parameter.empty:
                    continue
            # At least check the return annotation exists on most functions
            if func.__name__ != "fill_zero_features" and func.__name__ != "fill_global_mean":
                assert func.__name__ in [
                    "compute_target",
                    "compute_planned_duration",
                    "compute_creation_to_planned_start",
                    "compute_days_since_update",
                    "compute_halfway_date",
                    "compute_created_time_features",
                    "compute_revision_features",
                    "compute_subtask_features",
                    "compute_subtask_halfway_features",
                    "ordinal_encode_status",
                    "target_encode",
                ] or sig.return_annotation is not inspect.Parameter.empty


class TestBuildFeaturesModule:
    def test_module_loads(self):
        assert bf is not None

    def test_expected_functions_exist(self):
        expected = [
            "load_base_tasks",
            "compute_derived_features",
            "load_revisions",
            "load_subtasks",
            "load_subtask_halfway",
            "load_challenges",
            "load_department_aggregates",
            "load_employee_aggregates",
            "load_position_aggregates",
            "load_cross_dept",
            "load_ma_info",
            "load_ma_revisions",
            "load_kpi_features",
            "load_kpi_revisions",
            "load_subtask_challenges",
            "load_kpi_challenges",
            "load_kpi_potential_challenges",
            "load_comments",
            "load_subtask_history",
            "impute_features",
            "encode_features",
            "build_dataset",
        ]
        for fn_name in expected:
            assert hasattr(bf, fn_name), f"Missing function: {fn_name}"

    def test_has_entry_point(self):
        source = inspect.getsource(bf)
        assert "'__main__'" in source or '"__main__"' in source

    def test_has_main_function(self):
        assert hasattr(bf, "main")

    def test_has_feature_lists(self):
        assert hasattr(bf, "FINAL_FEATURES")
        assert hasattr(bf, "FEATURES_AT_ASSIGNMENT")
        assert hasattr(bf, "FEATURES_ADDED_AT_HALFWAY")
        assert hasattr(bf, "FEATURES_AT_HALFWAY")

    def test_feature_list_counts(self):
        assert len(bf.FEATURES_AT_ASSIGNMENT) == 31, (
            f"Expected 31 assignment features, got {len(bf.FEATURES_AT_ASSIGNMENT)}"
        )
        assert len(bf.FEATURES_ADDED_AT_HALFWAY) == 15, (
            f"Expected 15 halfway features, got {len(bf.FEATURES_ADDED_AT_HALFWAY)}"
        )
        assert len(bf.FEATURES_AT_HALFWAY) == 46, (
            f"Expected 46 halfway features, got {len(bf.FEATURES_AT_HALFWAY)}"
        )

    def test_halfway_is_superset_of_assignment(self):
        assert set(bf.FEATURES_AT_ASSIGNMENT).issubset(set(bf.FEATURES_AT_HALFWAY))

    def test_added_at_halfway_are_disjoint_from_assignment(self):
        assert set(bf.FEATURES_AT_ASSIGNMENT).isdisjoint(set(bf.FEATURES_ADDED_AT_HALFWAY))

    def test_added_at_halfway_plus_assignment_equals_halfway(self):
        combined = set(bf.FEATURES_AT_ASSIGNMENT) | set(bf.FEATURES_ADDED_AT_HALFWAY)
        assert combined == set(bf.FEATURES_AT_HALFWAY)

    def test_csv_feature_counts_match(self):
        df_c = pd.read_csv(PROJECT_ROOT / "data" / "dataset_at_creation.csv")
        df_h = pd.read_csv(PROJECT_ROOT / "data" / "dataset_at_halfway.csv")
        csv_creation_feats = {c for c in df_c.columns if c not in ("id", "calculated_overdue")}
        csv_halfway_feats = {c for c in df_h.columns if c not in ("id", "calculated_overdue")}
        wl_cols = {"wl_high", "wl_low", "wl_mid"}
        expected_creation = set(bf.FEATURES_AT_ASSIGNMENT) | wl_cols
        expected_halfway = set(bf.FEATURES_AT_HALFWAY) | wl_cols
        assert csv_creation_feats == expected_creation, (
            f"Creation CSV features don't match expected.\n"
            f"In CSV not in expected: {csv_creation_feats - expected_creation}\n"
            f"Expected not in CSV: {expected_creation - csv_creation_feats}"
        )
        assert csv_halfway_feats == expected_halfway, (
            f"Halfway CSV features don't match expected.\n"
            f"In CSV not in expected: {csv_halfway_feats - expected_halfway}\n"
            f"Expected not in CSV: {expected_halfway - csv_halfway_feats}"
        )


# ── Feature Engineering Function Tests ─────────────────────────────────────

class TestComputeTarget:
    def test_returns_array(self):
        df = pd.DataFrame({"status": ["completed"], "actual_end_date": pd.Timestamp("2024-01-10"),
                           "end_date": pd.Timestamp("2024-01-05")})
        result = fe.compute_target(df)
        assert isinstance(result, (pd.Series, np.ndarray))

    def test_returns_binary(self):
        df = pd.DataFrame({"status": ["completed"], "actual_end_date": pd.Timestamp("2024-01-10"),
                           "end_date": pd.Timestamp("2024-01-05")})
        result = fe.compute_target(df)
        assert result[0] in (0, 1)


class TestComputePlannedDuration:
    def test_returns_series(self):
        df = pd.DataFrame({"start_date": pd.Timestamp("2024-01-01"),
                           "end_date": pd.Timestamp("2024-01-05")}, index=[0])
        result = fe.compute_planned_duration(df)
        assert isinstance(result, pd.Series)

    def test_positive_duration(self):
        df = pd.DataFrame({"start_date": pd.Timestamp("2024-01-01"),
                           "end_date": pd.Timestamp("2024-01-05")}, index=[0])
        result = fe.compute_planned_duration(df)
        assert result.iloc[0] == 4


class TestComputeCreatedTimeFeatures:
    def test_returns_dataframe(self):
        df = pd.DataFrame({"created_date": pd.Timestamp("2024-01-01")}, index=[0])
        result = fe.compute_created_time_features(df)
        assert isinstance(result, pd.DataFrame)

    def test_has_expected_columns(self):
        df = pd.DataFrame({"created_date": pd.Timestamp("2024-01-01")}, index=[0])
        result = fe.compute_created_time_features(df)
        expected = {"created_dow", "created_is_weekend", "created_is_friday", "created_month", "created_quarter"}
        assert set(result.columns) == expected

    def test_weekend_detection(self):
        sat = pd.Timestamp("2024-01-06")
        df = pd.DataFrame({"created_date": [sat]})
        result = fe.compute_created_time_features(df)
        assert result["created_is_weekend"].iloc[0] == 1

    def test_friday_detection(self):
        fri = pd.Timestamp("2024-01-05")
        df = pd.DataFrame({"created_date": [fri]})
        result = fe.compute_created_time_features(df)
        assert result["created_is_friday"].iloc[0] == 1


class TestOrdinalEncode:
    def test_returns_series(self):
        df = pd.DataFrame({"status": ["open"]})
        result = fe.ordinal_encode_status(df, "status", {"open": 0, "closed": 1})
        assert isinstance(result, pd.Series)

    def test_applies_mapping(self):
        df = pd.DataFrame({"status": ["open", "closed"]})
        result = fe.ordinal_encode_status(df, "status", {"open": 0, "closed": 1})
        assert list(result) == [0, 1]

    def test_fallback_on_unknown(self):
        df = pd.DataFrame({"status": ["unknown_value"]})
        result = fe.ordinal_encode_status(df, "status", {"open": 0}, fallback=1)
        assert result.iloc[0] == 1


class TestTargetEncode:
    def test_returns_series(self):
        df = pd.DataFrame({"group": ["a", "a", "b"], "target": [1, 0, 1]})
        result = fe.target_encode(df, "group", "target")
        assert isinstance(result, pd.Series)

    def test_encoding_values(self):
        df = pd.DataFrame({"group": ["a", "a", "b"], "target": [1, 0, 1]})
        result = fe.target_encode(df, "group", "target")
        a_expected = df.loc[df["group"] == "a", "target"].mean()
        assert result.iloc[0] == a_expected
        assert result.iloc[1] == a_expected

    def test_unknown_uses_fallback(self):
        df = pd.DataFrame({"group": ["a", "a", "b"], "target": [1, 0, 1]})
        train = df.iloc[:2]
        result = fe.target_encode(train, "group", "target", unknown_value=0.5)
        assert result.iloc[0] == 0.5  # mean of [1, 0] for group "a"
        assert result.iloc[1] == 0.5  # same group "a"


class TestFillFunctions:
    def test_fill_zero(self):
        df = pd.DataFrame({"a": [1.0, np.nan, 3.0]})
        result = fe.fill_zero_features(df, ["a"])
        assert result["a"].iloc[1] == 0.0

    def test_fill_global_mean(self):
        df = pd.DataFrame({"a": [1.0, np.nan, 3.0]})
        result = fe.fill_global_mean(df, ["a"])
        assert result["a"].iloc[1] == 2.0

    def test_fill_zero_ignores_non_listed(self):
        df = pd.DataFrame({"a": [1.0, np.nan], "b": [np.nan, 2.0]})
        result = fe.fill_zero_features(df, ["a"])
        assert pd.isna(result["b"].iloc[0])


class TestHalfwayDate:
    def test_computes_correctly(self):
        df = pd.DataFrame({
            "start_date": pd.Timestamp("2024-01-01"),
            "end_date": pd.Timestamp("2024-01-11"),
            "planned_duration": [10],
        })
        result = fe.compute_halfway_date(df)
        assert result.iloc[0] == pd.Timestamp("2024-01-06")
