"""
losses.py
---------
6 Big Losses analysis based on the TPM (Total Productive Maintenance) framework.

The 6 Big Losses are the primary causes of OEE reduction:

  Availability Losses:
    1. Equipment Failure   — Unplanned breakdowns
    2. Setup & Adjustment  — Planned changeovers, retooling

  Performance Losses:
    3. Idling & Minor Stops — Jams, sensor faults (< 5 min each)
    4. Reduced Speed        — Running below design speed

  Quality Losses:
    5. Process Defects      — Scrap during steady-state production
    6. Reduced Yield        — Startup losses, first-article inspection

Each loss is quantified in:
  - Minutes of equivalent lost time
  - Number of parts lost
  - Percentage of planned production time

Reference:
    Nakajima (1988). Introduction to TPM.
    OEE Foundation — https://www.oee.com/oee-factors/
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class LossBreakdown:
    """Detailed loss breakdown for one (machine, shift) or aggregated period."""
    machine_id: str
    period: str
    planned_time_min: float
    # Loss values (minutes)
    equipment_failure_min: float
    setup_adjustment_min: float
    idling_minor_stops_min: float
    reduced_speed_min: float
    process_defects_min: float
    reduced_yield_min: float

    @property
    def total_loss_min(self) -> float:
        return (
            self.equipment_failure_min
            + self.setup_adjustment_min
            + self.idling_minor_stops_min
            + self.reduced_speed_min
            + self.process_defects_min
            + self.reduced_yield_min
        )

    @property
    def losses_dict(self) -> dict[str, float]:
        return {
            "Equipment Failure":    self.equipment_failure_min,
            "Setup & Adjustment":   self.setup_adjustment_min,
            "Idling & Minor Stops": self.idling_minor_stops_min,
            "Reduced Speed":        self.reduced_speed_min,
            "Process Defects":      self.process_defects_min,
            "Reduced Yield":        self.reduced_yield_min,
        }

    @property
    def losses_pct(self) -> dict[str, float]:
        """Each loss as % of planned production time."""
        return {
            k: v / self.planned_time_min * 100
            for k, v in self.losses_dict.items()
        }

    def category_totals(self) -> dict[str, float]:
        """Aggregate by TPM category."""
        return {
            "Availability Losses": self.equipment_failure_min + self.setup_adjustment_min,
            "Performance Losses":  self.idling_minor_stops_min + self.reduced_speed_min,
            "Quality Losses":      self.process_defects_min + self.reduced_yield_min,
        }

    def __str__(self) -> str:
        lines = [f"\n  6 Big Losses — {self.machine_id} | {self.period}"]
        lines.append(f"  {'─'*40}")
        for name, val in self.losses_dict.items():
            pct = val / self.planned_time_min * 100
            bar = "█" * int(pct / 1.5)
            lines.append(f"  {name:<22}: {val:6.1f} min  {pct:5.1f}%  {bar}")
        lines.append(f"  {'─'*40}")
        lines.append(
            f"  Total losses: {self.total_loss_min:.1f} min "
            f"({self.total_loss_min/self.planned_time_min*100:.1f}% of planned time)"
        )
        return "\n".join(lines)


class LossAnalyzer:
    """
    Computes 6 Big Losses from a production event DataFrame.

    Args:
        events_df:            Raw events DataFrame (from simulator/CSV)
        planned_shift_min:    Planned shift duration (net, excl. planned breaks)
        ideal_cycle_time_sec: Ideal cycle time per part
    """

    LOSS_MAP = {
        "BREAKDOWN":  "Equipment Failure",
        "SETUP":      "Setup & Adjustment",
        "MINOR_STOP": "Idling & Minor Stops",
        "SPEED_LOSS": "Reduced Speed",
    }

    def __init__(
        self,
        events_df: pd.DataFrame,
        planned_shift_min: float = 450.0,
        ideal_cycle_time_sec: float = 45.0,
    ):
        self.df = events_df.copy()
        self.df["timestamp"] = pd.to_datetime(self.df["timestamp"])
        self.planned_min = planned_shift_min
        self.ideal_ct_min = ideal_cycle_time_sec / 60.0

    def _scrap_to_minutes(self, scrap_count: int) -> float:
        """Convert scrap parts to equivalent lost production time."""
        return scrap_count * self.ideal_ct_min

    def compute_shift(self, machine_id: str, shift: str) -> LossBreakdown:
        """Compute 6 Big Losses for one (machine, shift)."""
        group = self.df[
            (self.df["machine_id"] == machine_id) &
            (self.df["shift"] == shift)
        ]

        losses = {name: 0.0 for name in self.LOSS_MAP.values()}
        for etype, loss_name in self.LOSS_MAP.items():
            losses[loss_name] = group.loc[
                group["event_type"] == etype, "duration_min"
            ].sum()

        # Quality losses from scrap
        scrap_total = group["parts_scrap"].sum()
        process_defects_min = self._scrap_to_minutes(scrap_total)

        return LossBreakdown(
            machine_id=machine_id,
            period=shift,
            planned_time_min=self.planned_min,
            equipment_failure_min=losses["Equipment Failure"],
            setup_adjustment_min=losses["Setup & Adjustment"],
            idling_minor_stops_min=losses["Idling & Minor Stops"],
            reduced_speed_min=losses["Reduced Speed"],
            process_defects_min=process_defects_min,
            reduced_yield_min=0.0,
        )

    def compute_all(self) -> list[LossBreakdown]:
        """Compute 6 Big Losses for all (machine, shift) combinations."""
        results = []
        for (machine_id, shift), _ in self.df.groupby(["machine_id", "shift"]):
            results.append(self.compute_shift(machine_id, shift))
        return results

    def aggregate_by_machine(self) -> pd.DataFrame:
        """Aggregate total losses per machine across all shifts."""
        all_losses = self.compute_all()
        rows = []
        for lb in all_losses:
            row = {"machine_id": lb.machine_id, "shift": lb.period}
            row.update(lb.losses_dict)
            rows.append(row)

        df = pd.DataFrame(rows)
        return df.groupby("machine_id").sum(numeric_only=True).reset_index()

    def aggregate_total(self) -> dict[str, float]:
        """Grand total losses across all machines and shifts."""
        all_losses = self.compute_all()
        total: dict[str, float] = {}
        for lb in all_losses:
            for k, v in lb.losses_dict.items():
                total[k] = total.get(k, 0.0) + v
        return total

    def top_losses(self, top_n: int = 3) -> list[tuple[str, float]]:
        """Return top N loss causes sorted by total minutes lost."""
        total = self.aggregate_total()
        return sorted(total.items(), key=lambda x: -x[1])[:top_n]

    def waterfall_data(self) -> pd.DataFrame:
        """
        Build data for a waterfall chart showing how losses erode OEE.

        Returns DataFrame: [label, value, type]
        where type ∈ {start, loss, result}
        """
        total = self.aggregate_total()
        planned = self.planned_min * len(
            self.df[["machine_id", "shift"]].drop_duplicates()
        )
        rows = [
            {"label": "Planned Time", "value": planned, "type": "start"},
        ]
        running = planned
        category_map = {
            "Equipment Failure":    "Availability Loss",
            "Setup & Adjustment":   "Availability Loss",
            "Idling & Minor Stops": "Performance Loss",
            "Reduced Speed":        "Performance Loss",
            "Process Defects":      "Quality Loss",
            "Reduced Yield":        "Quality Loss",
        }
        for loss_name, minutes in sorted(total.items(), key=lambda x: -x[1]):
            running -= minutes
            rows.append({
                "label": loss_name,
                "value": -minutes,
                "cumulative": running,
                "type": category_map.get(loss_name, "loss"),
            })
        rows.append({"label": "Productive Time", "value": running, "type": "result"})
        return pd.DataFrame(rows)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")
    from src.data.simulator import FactorySimulator

    sim = FactorySimulator(machines=["M01", "M02"], n_shifts=3)
    df = sim.run(output_path="data/test_events.csv")

    analyzer = LossAnalyzer(df)
    for lb in analyzer.compute_all()[:2]:
        print(lb)

    print("\nTop 3 losses overall:")
    for name, minutes in analyzer.top_losses(3):
        print(f"  {name}: {minutes:.1f} min")
