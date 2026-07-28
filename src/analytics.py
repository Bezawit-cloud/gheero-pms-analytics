import pandas as pd
import numpy as np

# Department risk tiers, matching the binning used in the EDA notebook
# (section 14 — Department-Wise Overdue Breakdown). The raw department_id
# isn't in the analytical dataset; it was encoded into dept_past_overdue_rate,
# so we reconstruct tiers from that instead of grouping on a "department"
# column, which doesn't exist in dataset_at_creation_clean.csv /
# dataset_at_halfway_clean.csv.
DEPT_RISK_BINS = [-0.001, 0.10, 0.20, 0.30, 1.0]
DEPT_RISK_LABELS = [
    "Low Risk (0-10%)",
    "Moderate (10-20%)",
    "High (20-30%)",
    "Critical (>30%)",
]


def compute_dept_risk_tiers(df: pd.DataFrame) -> pd.DataFrame:
    """Bins dept_past_overdue_rate into risk tiers and shows actual overdue rate per tier."""
    if df.empty or "dept_past_overdue_rate" not in df.columns or "calculated_overdue" not in df.columns:
        return pd.DataFrame()

    working = df.copy()
    working["Risk_Tier"] = pd.cut(
        working["dept_past_overdue_rate"], bins=DEPT_RISK_BINS, labels=DEPT_RISK_LABELS
    )

    tier_summary = (
        working.groupby("Risk_Tier", observed=True)
        .agg(
            Num_Tasks=("calculated_overdue", "count"),
            Actual_Overdue_Pct=("calculated_overdue", "mean"),
        )
        .reset_index()
    )
    tier_summary["Actual_Overdue_Pct"] = tier_summary["Actual_Overdue_Pct"] * 100
    tier_summary["Risk_Tier"] = pd.Categorical(
        tier_summary["Risk_Tier"], categories=DEPT_RISK_LABELS, ordered=True
    )
    return tier_summary.sort_values("Risk_Tier")


def compute_cross_dept_impact(df: pd.DataFrame) -> pd.DataFrame:
    """Single-department vs cross-department overdue rate (coordination friction)."""
    if df.empty or "is_cross_dept" not in df.columns or "calculated_overdue" not in df.columns:
        return pd.DataFrame()

    grp = df.groupby("is_cross_dept")["calculated_overdue"].mean() * 100
    return pd.DataFrame(
        {
            "Segment": ["Single Department", "Cross-Department"],
            "Overdue_Rate_Pct": [grp.get(0, 0.0), grp.get(1, 0.0)],
        }
    )


def compute_subtask_effect(df: pd.DataFrame) -> pd.DataFrame:
    """The 'Subtask Protection Effect' — decomposed tasks vs monolithic tasks."""
    if df.empty or "has_subtasks" not in df.columns or "calculated_overdue" not in df.columns:
        return pd.DataFrame()

    grp = df.groupby("has_subtasks")["calculated_overdue"].mean() * 100
    return pd.DataFrame(
        {
            "Segment": ["No Subtasks", "Has Subtasks"],
            "Overdue_Rate_Pct": [grp.get(0, 0.0), grp.get(1, 0.0)],
        }
    )


def compute_revision_spiral(df: pd.DataFrame) -> pd.DataFrame:
    """The 'Revision Death Spiral' — overdue rate by revision-count bucket."""
    if df.empty or "num_revisions" not in df.columns or "calculated_overdue" not in df.columns:
        return pd.DataFrame()

    working = df.copy()

    def bucket(n):
        if n <= 0:
            return "0"
        elif n == 1:
            return "1"
        elif n == 2:
            return "2"
        return "3+"

    working["Revisions"] = working["num_revisions"].apply(bucket)
    order = ["0", "1", "2", "3+"]

    summary = (
        working.groupby("Revisions")["calculated_overdue"]
        .agg(Num_Tasks="count", Overdue_Rate="mean")
        .reindex(order)
        .reset_index()
    )
    summary["Overdue_Rate_Pct"] = summary["Overdue_Rate"] * 100
    return summary


def compute_retroactive_impact(df: pd.DataFrame) -> pd.DataFrame:
    """Retroactive creation anomaly — tasks logged after their planned start date."""
    if df.empty or "creation_to_planned_start" not in df.columns or "calculated_overdue" not in df.columns:
        return pd.DataFrame()

    working = df.copy()
    working["Segment"] = np.where(
        working["creation_to_planned_start"] < 0, "Retroactive Creation", "Planned Ahead"
    )
    grp = working.groupby("Segment")["calculated_overdue"].mean() * 100
    counts = working["Segment"].value_counts()
    return pd.DataFrame(
        {
            "Segment": grp.index,
            "Overdue_Rate_Pct": grp.values,
            "Num_Tasks": [counts.get(s, 0) for s in grp.index],
        }
    )


def compute_seasonality(df: pd.DataFrame) -> pd.DataFrame:
    """Task volume and overdue rate by creation month."""
    if df.empty or "created_month" not in df.columns or "calculated_overdue" not in df.columns:
        return pd.DataFrame()

    monthly = (
        df.groupby("created_month")
        .agg(Num_Tasks=("calculated_overdue", "count"), Overdue_Rate=("calculated_overdue", "mean"))
        .reset_index()
    )
    monthly["Overdue_Rate_Pct"] = monthly["Overdue_Rate"] * 100
    return monthly


def compute_class_balance(df: pd.DataFrame) -> dict:
    """Baseline overdue rate and imbalance ratio, for the KPI row and metric-choice framing."""
    if df.empty or "calculated_overdue" not in df.columns:
        return {}

    overdue = int(df["calculated_overdue"].sum())
    total = len(df)
    not_overdue = total - overdue
    ratio = (not_overdue / overdue) if overdue else 0.0
    return {
        "total": total,
        "overdue": overdue,
        "not_overdue": not_overdue,
        "overdue_pct": (overdue / total * 100) if total else 0.0,
        "imbalance_ratio": ratio,
    }