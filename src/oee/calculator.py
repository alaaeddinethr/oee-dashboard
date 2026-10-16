"""
calculator.py
-------------
Computes OEE (Overall Equipment Effectiveness) and its three components
from a production event log.

  OEE = Availability × Performance × Quality

Where:
  Availability = Run Time / Planned Production Time
  Performance  = (Ideal Cycle Time × Total Count) / Run Time
  Quality      = Good Count / Total Count

Also computes:
  - MTBF (Mean Time Between Failures)
  - MTTR (Mean Time To Repair)
  - Shift-level and machine-level aggregations

Reference:
    Nakajima, S. (1988). Introduction to TPM. Productivity Press.
    SEMI E10 Standard — Equipment Reliability, Availability, Maintainability.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import yaml

# ─── Event types (mirror simulator.py) ───────────────────────────────────────

DOWNTIME_EVENTS = {"BREAKDOWN", "MINOR_STOP", "SETUP"}
PLANNED_STOPS   = {"BREAK"}
PRODUCTION_EVENTS = {"PRODUCTION", "SPEED_LOSS"}


# ─── OEE Result ───────────────────────────────────────────────────────────────

@dataclass
class OEEResult:
    """OEE metrics for a single machine/shift."""
    machine_id:           str
    shift:                str
    # Time (minutes)
    planned_time_min:     float
    downtime_min:         float
    planned_stop_min:     float
    run_time_min:         float
    # Parts
    parts_total:          int
    parts_good:           int
    parts_scrap:          int
    # OEE components
    availability:         float
    performance:          float
    quality:              float
    oee:                  float
    # Reliability
    n_breakdowns:         int
    mtbf_min:             float   # Mean Time Between Failures
    mttr_min:             float   # Mean Time To Repair
    # Losses
    losses: dict = field(default_factory=dict)

    @property
    def availability_pct(self) -> float:
        return self.availability * 100

    @property
    def performance_pct(self) -> float:
        return self.performance * 100

    @property
    def quality_pct(self) -> float:
        return self.quality * 100

    @property
    def oee_pct(self) -> float:
        return self.oee * 100

    @property
    def scrap_rate(self) -> float:
        return self.parts_scrap / max(self.parts_total, 1)

    def classification(self) -> str:
        if self.oee >= 0.85:
            return "World Class"
        elif self.oee >= 0.75:
            return "Good"
        elif self.oee >= 0.60:
            return "Typical"
        else:
            return "Poor"

    def __str__(self) -> str:
        return (
            f"[{self.machine_id} | {self.shift}]\n"
            f"  OEE:          {self.oee_pct:6.1f}%  ({self.classification()})\n"
            f"  Availability: {self.availability_pct:6.1f}%\n"
            f"  Performance:  {self.performance_pct:6.1f}%\n"
            f"  Quality:      {self.quality_pct:6.1f}%\n"
            f"  MTBF:         {self.mtbf_min:6.1f} min | MTTR: {self.mttr_min:.1f} min\n"
            f"  Parts: {self.parts_total} total / {self.parts_good} good / {self.parts_scrap} scrap"
        )


# ─── OEE Calculator ───────────────────────────────────────────────────────────

class OEECalculator:
    """
    Computes OEE metrics from a production event DataFrame.

    Args:
        events_df:            DataFrame from simulator or CSV import
        planned_shift_min:    Planned production time per shift (minutes)
        ideal_cycle_time_sec: Ideal cycle time per part (seconds)
    """

    def __init__(
        self,
        events_df: pd.DataFrame,
        planned_shift_min: float = 450.0,   # 8h - 2×15min breaks
        ideal_cycle_time_sec: float = 45.0,
    ):
        self.df = events_df.copy()
        self.df["timestamp"] = pd.to_datetime(self.df["timestamp"])
        self.planned_shift_min = planned_shift_min
        self.ideal_ct_min = ideal_cycle_time_sec / 60.0

    def _compute_shift(self, group: pd.DataFrame) -> OEEResult:
        """Compute OEE for a single (machine, shift) group."""
        machine_id = group["machine_id"].iloc[0]
        shift      = group["shift"].iloc[0]

        # Time decomposition
        downtime_min     = group.loc[group["event_type"] == "BREAKDOWN",  "duration_min"].sum()
        minor_stop_min   = group.loc[group["event_type"] == "MINOR_STOP", "duration_min"].sum()
        setup_min        = group.loc[group["event_type"] == "SETUP",      "duration_min"].sum()
        planned_stop_min = group.loc[group["event_type"] == "BREAK",      "duration_min"].sum()
        speed_loss_min   = group.loc[group["event_type"] == "SPEED_LOSS", "duration_min"].sum()

        # planned_shift_min is already net of scheduled breaks (e.g. 480 - 30 = 450),
        # so BREAK events must not be subtracted a second time.
        # Six Big Losses (Nakajima): breakdowns and setups are availability
        # losses; minor stops and reduced speed are performance losses, so they
        # stay inside run time and show up as fewer parts than the ideal rate.
        total_loss_min = downtime_min + setup_min
        run_time_min   = self.planned_shift_min - total_loss_min
        run_time_min   = max(run_time_min, 0.0)

        # Part counts
        prod_mask    = group["event_type"].isin(PRODUCTION_EVENTS)
        parts_total  = group.loc[prod_mask, "parts_produced"].sum()
        parts_good   = group.loc[prod_mask, "parts_good"].sum()
        parts_scrap  = group.loc[prod_mask, "parts_scrap"].sum()

        # OEE components
        planned_net = self.planned_shift_min
        availability = run_time_min / planned_net if planned_net > 0 else 0.0
        availability = min(availability, 1.0)

        # Performance: (actual parts / theoretical max parts in run_time)
        theoretical_max = run_time_min / self.ideal_ct_min if self.ideal_ct_min > 0 else 1
        performance = parts_total / theoretical_max if theoretical_max > 0 else 0.0
        performance = min(performance, 1.0)

        quality = parts_good / parts_total if parts_total > 0 else 0.0
        quality = min(quality, 1.0)

        oee = availability * performance * quality

        # MTBF / MTTR
        breakdowns = group[group["event_type"] == "BREAKDOWN"]
        n_bd = len(breakdowns)
        mttr = breakdowns["duration_min"].mean() if n_bd > 0 else 0.0
        if n_bd > 1:
            mtbf = (planned_net - breakdowns["duration_min"].sum()) / n_bd
        elif n_bd == 1:
            mtbf = planned_net - breakdowns["duration_min"].sum()
        else:
            mtbf = planned_net  # no failures = full shift

        # 6 Big Losses breakdown (as minutes)
        losses = {
            "Equipment Failure": downtime_min,
            "Setup & Adjustment": setup_min,
            "Idling & Minor Stops": minor_stop_min,
            "Reduced Speed": speed_loss_min,
            "Process Defects": parts_scrap * self.ideal_ct_min,
            "Reduced Yield": 0.0,  # startup losses not modeled separately
        }

        return OEEResult(
            machine_id=machine_id,
            shift=shift,
            planned_time_min=self.planned_shift_min,
            downtime_min=downtime_min + minor_stop_min + setup_min,
            planned_stop_min=planned_stop_min,
            run_time_min=run_time_min,
            parts_total=int(parts_total),
            parts_good=int(parts_good),
            parts_scrap=int(parts_scrap),
            availability=availability,
            performance=performance,
            quality=quality,
            oee=oee,
            n_breakdowns=n_bd,
            mtbf_min=float(mtbf),
            mttr_min=float(mttr),
            losses=losses,
        )

    def compute_all(self) -> list[OEEResult]:
        """Compute OEE for every (machine, shift) combination."""
        results = []
        for (machine_id, shift), group in self.df.groupby(["machine_id", "shift"]):
            result = self._compute_shift(group)
            results.append(result)
        return results

    def to_dataframe(self) -> pd.DataFrame:
        """Return all OEE results as a tidy DataFrame."""
        results = self.compute_all()
        rows = []
        for r in results:
            rows.append({
                "machine_id":    r.machine_id,
                "shift":         r.shift,
                "oee":           round(r.oee, 4),
                "availability":  round(r.availability, 4),
                "performance":   round(r.performance, 4),
                "quality":       round(r.quality, 4),
                "parts_total":   r.parts_total,
                "parts_good":    r.parts_good,
                "parts_scrap":   r.parts_scrap,
                "run_time_min":  round(r.run_time_min, 1),
                "downtime_min":  round(r.downtime_min, 1),
                "n_breakdowns":  r.n_breakdowns,
                "mtbf_min":      round(r.mtbf_min, 1),
                "mttr_min":      round(r.mttr_min, 1),
                "classification": r.classification(),
            })
        return pd.DataFrame(rows)

    def summary(self) -> pd.DataFrame:
        """Aggregate OEE by machine (mean across shifts)."""
        df = self.to_dataframe()
        return df.groupby("machine_id").agg(
            oee_mean=("oee", "mean"),
            availability_mean=("availability", "mean"),
            performance_mean=("performance", "mean"),
            quality_mean=("quality", "mean"),
            parts_total=("parts_total", "sum"),
            parts_good=("parts_good", "sum"),
            n_breakdowns=("n_breakdowns", "sum"),
            mtbf_mean=("mtbf_min", "mean"),
            mttr_mean=("mttr_min", "mean"),
        ).round(4)

    def print_report(self) -> None:
        results = self.compute_all()
        print(f"\n{'═'*55}")
        print("  OEE REPORT — All Shifts")
        print(f"{'═'*55}")
        for r in results:
            print(r)
            print(f"  {'─'*50}")
        # Global average
        df = self.to_dataframe()
        print("\n  GLOBAL AVERAGE:")
        print(f"  OEE:          {df['oee'].mean()*100:.1f}%")
        print(f"  Availability: {df['availability'].mean()*100:.1f}%")
        print(f"  Performance:  {df['performance'].mean()*100:.1f}%")
        print(f"  Quality:      {df['quality'].mean()*100:.1f}%")
        print(f"{'═'*55}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/production_events.csv")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    if not Path(args.data).exists():
        print(f"No data file found at {args.data}. Running simulator first...")
        import subprocess
        subprocess.run(["python", "src/data/simulator.py", "--output", args.data])

    df = pd.read_csv(args.data)
    cfg = yaml.safe_load(open(args.config)) if Path(args.config).exists() else {}
    prod = cfg.get("production", {})

    calc = OEECalculator(
        df,
        planned_shift_min=prod.get("planned_shift_hours", 8) * 60
        - prod.get("breaks_per_shift", 2) * prod.get("break_duration_min", 15),
        ideal_cycle_time_sec=prod.get("ideal_cycle_time_sec", 45),
    )
    calc.print_report()
