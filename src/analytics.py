import pandas as pd
import numpy as np


def compute_department_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Computes department-wise overdue rates and classifies them into risk tiers."""
    if df.empty or "department" not in df.columns or "calculated_overdue" not in df.columns:
        return pd.DataFrame()

    dept_summary = (
        df.groupby("department")
        .agg(
            Total_Tasks=("calculated_overdue", "count"),
            Overdue_Tasks=("calculated_overdue", "sum"),
            Delay_Rate=("calculated_overdue", "mean"),
        )
        .reset_index()
    )
    
    dept_summary["Delay_Rate_Pct"] = dept_summary["Delay_Rate"] * 100
    dept_summary = dept_summary.sort_values(by="Delay_Rate", ascending=False)

    def assign_tier(rate):
        if rate >= 35:
            return "Critical (35%+)"
        elif rate >= 20:
            return "High (20%-35%)"
        elif rate >= 10:
            return "Moderate (10%-20%)"
        else:
            return "Low (<10%)"

    dept_summary["Risk_Tier"] = dept_summary["Delay_Rate_Pct"].apply(assign_tier)
    return dept_summary


def compute_priority_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregates metrics by priority tier."""
    if df.empty or "priority" not in df.columns:
        return pd.DataFrame()

    priority_df = (
        df.groupby("priority")["calculated_overdue"]
        .agg(Total=("count"), Overdue_Rate=("mean"))
        .reset_index()
    )
    priority_df["Overdue_Rate"] = priority_df["Overdue_Rate"] * 100
    return priority_df