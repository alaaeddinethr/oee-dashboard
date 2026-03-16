"""
pareto.py
---------
Pareto analysis for manufacturing losses.

The Pareto principle (80/20 rule) in Lean manufacturing:
  ~80% of production losses come from ~20% of causes.

This module identifies the vital few causes that, if resolved,
would yield the greatest OEE improvement.

Also implements:
  - ABC classification (A = top cumulative 80%, B = 80-95%, C = rest)
  - Priority matrix combining frequency × severity
  - Quick wins identification (high impact, short MTTR)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class ParetoItem:
    """One row in the Pareto table."""
    rank: int
    cause: str
    value: float           # total minutes lost
    count: int             # number of occurrences
    cumulative_pct: float  # cumulative % of total
    abc_class: str         # A / B / C
    avg_duration: float    # average duration per occurrence

    @property
    def priority(self) -> str:
        return {
            "A": "Critical",
            "B": "Important",
            "C": "Monitor",
        }.get(self.abc_class, "—")


class ParetoAnalyzer:
    """
    Computes Pareto analysis on production event data.

    Args:
        events_df: Production events DataFrame
        value_col: Column to aggregate (default: duration_min)
        cause_col: Column to group by (default: event_type)
        filter_types: Only include these event types
    """

    DOWNTIME_TYPES = {"BREAKDOWN", "MINOR_STOP", "SETUP", "SPEED_LOSS"}

    def __init__(
        self,
        events_df: pd.DataFrame,
        value_col: str = "duration_min",
        cause_col: str = "event_type",
        filter_types: set | None = None,
    ):
        self.df = events_df.copy()
        self.value_col = value_col
        self.cause_col = cause_col
        self.filter_types = filter_types or self.DOWNTIME_TYPES

    def compute(self) -> list[ParetoItem]:
        """
        Compute Pareto table.

        Returns:
            List of ParetoItem sorted descending by total loss value.
        """
        filtered = self.df[self.df[self.cause_col].isin(self.filter_types)]

        agg = filtered.groupby(self.cause_col).agg(
            total_value=(self.value_col, "sum"),
            count=(self.value_col, "count"),
            avg_duration=(self.value_col, "mean"),
        ).reset_index()

        agg = agg.sort_values("total_value", ascending=False).reset_index(drop=True)
        total = agg["total_value"].sum()

        if total == 0:
            return []

        items = []
        cumulative = 0.0
        for i, row in agg.iterrows():
            cumulative += row["total_value"] / total * 100
            abc = "A" if cumulative <= 80 else ("B" if cumulative <= 95 else "C")
            items.append(ParetoItem(
                rank=i + 1,
                cause=row[self.cause_col],
                value=round(float(row["total_value"]), 2),
                count=int(row["count"]),
                cumulative_pct=round(cumulative, 1),
                abc_class=abc,
                avg_duration=round(float(row["avg_duration"]), 2),
            ))

        return items

    def to_dataframe(self) -> pd.DataFrame:
        """Return Pareto analysis as DataFrame."""
        items = self.compute()
        return pd.DataFrame([{
            "Rank":             item.rank,
            "Cause":            item.cause,
            "Total (min)":      item.value,
            "Occurrences":      item.count,
            "Avg Duration (min)": item.avg_duration,
            "Cumulative %":     item.cumulative_pct,
            "ABC Class":        item.abc_class,
            "Priority":         item.priority,
        } for item in items])

    def vital_few(self) -> list[ParetoItem]:
        """Return only Class-A items (responsible for top 80% of losses)."""
        return [item for item in self.compute() if item.abc_class == "A"]

    def print_report(self) -> None:
        df = self.to_dataframe()
        total = df["Total (min)"].sum()
        print(f"\n{'═'*65}")
        print("  PARETO ANALYSIS — Production Losses")
        print(f"{'═'*65}")
        print(f"  Total downtime: {total:.1f} min across {len(df)} loss categories")
        print(f"{'─'*65}")
        print(f"  {'#':<3} {'Cause':<25} {'Total':>8} {'Occ':>5} {'Avg':>6} {'Cum%':>6} {'Class'}")
        print(f"  {'─'*3} {'─'*25} {'─'*8} {'─'*5} {'─'*6} {'─'*6} {'─'*5}")
        for _, row in df.iterrows():
            print(
                f"  {row['Rank']:<3} {row['Cause']:<25} "
                f"{row['Total (min)']:>7.1f} {row['Occurrences']:>5} "
                f"{row['Avg Duration (min)']:>6.1f} {row['Cumulative %']:>6.1f}%"
                f"  [{row['ABC Class']}]"
            )
        vf = self.vital_few()
        if vf:
            print(f"\n  ⚡ Vital Few (Class A — address these first):")
            for item in vf:
                print(f"     → {item.cause}: {item.value:.1f} min total, "
                      f"{item.count} occurrences")
        print(f"{'═'*65}")


class QuickWinFinder:
    """
    Identifies quick wins: high-impact losses with short mean repair time.

    Logic: A "quick win" is a loss category where:
      - Total lost time is above median (high impact)
      - Average duration is below median (easy to fix / short MTTR)

    Args:
        events_df: Production events DataFrame
    """

    def __init__(self, events_df: pd.DataFrame):
        self.df = events_df[
            events_df["event_type"].isin({"BREAKDOWN", "MINOR_STOP", "SETUP"})
        ].copy()

    def find(self) -> pd.DataFrame:
        if self.df.empty:
            return pd.DataFrame()

        agg = self.df.groupby("event_type").agg(
            total_min=("duration_min", "sum"),
            avg_min=("duration_min", "mean"),
            count=("duration_min", "count"),
        ).reset_index()

        med_total = agg["total_min"].median()
        med_avg   = agg["avg_min"].median()

        agg["impact"] = np.where(agg["total_min"] >= med_total, "High", "Low")
        agg["effort"] = np.where(agg["avg_min"] <= med_avg,     "Low",  "High")
        agg["quick_win"] = (agg["impact"] == "High") & (agg["effort"] == "Low")

        return agg.sort_values("total_min", ascending=False)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")
    from src.data.simulator import FactorySimulator

    sim = FactorySimulator(machines=["M01"], n_shifts=5, seed_offset=0)
    df = sim.run(output_path="data/test_pareto.csv")

    analyzer = ParetoAnalyzer(df)
    analyzer.print_report()
