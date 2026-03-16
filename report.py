"""
report.py
---------
Generates structured shift and machine performance reports.

Provides:
  - ShiftReport:   per-shift summary with trend vs previous shift
  - MachineReport: cross-machine OEE comparison
  - TrendAnalyzer: OEE trends, rolling averages, anomaly detection
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.oee.calculator import OEECalculator


@dataclass
class ShiftSummary:
    """One-shift performance summary."""
    shift: str
    machine_id: str
    oee: float
    availability: float
    performance: float
    quality: float
    parts_good: int
    parts_scrap: int
    downtime_min: float
    n_breakdowns: int
    trend_oee: float   # vs previous shift (delta)

    @property
    def trend_symbol(self) -> str:
        if self.trend_oee > 0.01:
            return "▲"
        elif self.trend_oee < -0.01:
            return "▼"
        return "═"

    @property
    def trend_color(self) -> str:
        if self.trend_oee > 0.01:
            return "green"
        elif self.trend_oee < -0.01:
            return "red"
        return "gray"


class ReportEngine:
    """
    Generates comprehensive reports from OEE data.

    Args:
        events_df: Raw production events DataFrame
        planned_shift_min: Net planned minutes per shift
        ideal_cycle_time_sec: Ideal cycle time per part
    """

    def __init__(
        self,
        events_df: pd.DataFrame,
        planned_shift_min: float = 450.0,
        ideal_cycle_time_sec: float = 45.0,
    ):
        self.df = events_df.copy()
        self.df["timestamp"] = pd.to_datetime(self.df["timestamp"])
        self.planned_min = planned_shift_min
        self.ideal_ct = ideal_cycle_time_sec

        calc = OEECalculator(
            self.df,
            planned_shift_min=planned_shift_min,
            ideal_cycle_time_sec=ideal_cycle_time_sec,
        )
        self.oee_df = calc.to_dataframe()

    def machine_summary(self) -> pd.DataFrame:
        """Cross-machine OEE summary sorted by OEE descending."""
        return (
            self.oee_df
            .groupby("machine_id")
            .agg(
                oee_mean=("oee", "mean"),
                oee_min=("oee", "min"),
                oee_max=("oee", "max"),
                oee_std=("oee", "std"),
                availability_mean=("availability", "mean"),
                performance_mean=("performance", "mean"),
                quality_mean=("quality", "mean"),
                parts_good_total=("parts_good", "sum"),
                parts_scrap_total=("parts_scrap", "sum"),
                downtime_total=("downtime_min", "sum"),
                n_breakdowns_total=("n_breakdowns", "sum"),
                shifts=("shift", "count"),
            )
            .round(4)
            .sort_values("oee_mean", ascending=False)
            .reset_index()
        )

    def trend_data(self, machine_id: str | None = None) -> pd.DataFrame:
        """
        OEE trend over shifts for a given machine (or all machines averaged).

        Returns DataFrame: shift × [oee, availability, performance, quality]
        with a rolling 3-shift average.
        """
        df = self.oee_df.copy()
        if machine_id:
            df = df[df["machine_id"] == machine_id]

        if machine_id:
            trend = df[["shift", "oee", "availability", "performance", "quality"]].copy()
        else:
            trend = (
                df.groupby("shift")[["oee", "availability", "performance", "quality"]]
                .mean()
                .reset_index()
            )

        trend = trend.sort_values("shift").reset_index(drop=True)
        trend["oee_rolling3"] = trend["oee"].rolling(3, min_periods=1).mean()
        trend["shift_num"] = range(1, len(trend) + 1)
        return trend

    def shift_summaries(self, machine_id: str) -> list[ShiftSummary]:
        """
        Ordered list of shift summaries for a machine, with trend vs previous.
        """
        df = self.oee_df[self.oee_df["machine_id"] == machine_id].sort_values("shift")
        summaries = []
        prev_oee = None
        for _, row in df.iterrows():
            trend = (row["oee"] - prev_oee) if prev_oee is not None else 0.0
            summaries.append(ShiftSummary(
                shift=row["shift"],
                machine_id=machine_id,
                oee=row["oee"],
                availability=row["availability"],
                performance=row["performance"],
                quality=row["quality"],
                parts_good=int(row["parts_good"]),
                parts_scrap=int(row["parts_scrap"]),
                downtime_min=row["downtime_min"],
                n_breakdowns=int(row["n_breakdowns"]),
                trend_oee=trend,
            ))
            prev_oee = row["oee"]
        return summaries

    def anomaly_shifts(self, threshold_std: float = 1.5) -> pd.DataFrame:
        """
        Flag shifts where OEE is more than `threshold_std` standard deviations
        below the machine's mean.

        These are candidate shifts for root cause analysis.
        """
        results = []
        for machine_id, group in self.oee_df.groupby("machine_id"):
            mu  = group["oee"].mean()
            std = group["oee"].std(ddof=1)
            if std == 0:
                continue
            low_shifts = group[group["oee"] < mu - threshold_std * std].copy()
            low_shifts["machine_mean_oee"] = mu
            low_shifts["z_score"] = (low_shifts["oee"] - mu) / std
            results.append(low_shifts)

        if not results:
            return pd.DataFrame()
        return pd.concat(results, ignore_index=True).sort_values("z_score")

    def best_worst_shifts(self, top_n: int = 3) -> dict[str, pd.DataFrame]:
        """Return top_n best and worst shifts per machine."""
        best = (
            self.oee_df
            .sort_values("oee", ascending=False)
            .groupby("machine_id")
            .head(top_n)
        )
        worst = (
            self.oee_df
            .sort_values("oee", ascending=True)
            .groupby("machine_id")
            .head(top_n)
        )
        return {"best": best, "worst": worst}

    def print_machine_summary(self) -> None:
        summary = self.machine_summary()
        print(f"\n{'═'*65}")
        print("  MACHINE PERFORMANCE COMPARISON")
        print(f"{'═'*65}")
        print(f"  {'Machine':<8} {'OEE':>6} {'Avail':>7} {'Perf':>7} {'Qual':>7} "
              f"{'Shifts':>7} {'Breakdowns':>12}")
        print(f"  {'─'*8} {'─'*6} {'─'*7} {'─'*7} {'─'*7} {'─'*7} {'─'*12}")
        for _, row in summary.iterrows():
            print(
                f"  {row['machine_id']:<8} "
                f"{row['oee_mean']*100:>5.1f}%"
                f"{row['availability_mean']*100:>7.1f}%"
                f"{row['performance_mean']*100:>7.1f}%"
                f"{row['quality_mean']*100:>7.1f}%"
                f"{row['shifts']:>7}"
                f"{row['n_breakdowns_total']:>12}"
            )
        print(f"{'═'*65}")
