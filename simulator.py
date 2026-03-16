"""
simulator.py
------------
Generates realistic production event logs for a manufacturing line.

Simulates a full shift timeline with:
  - Planned production windows
  - Scheduled breaks
  - Equipment breakdowns (Weibull-distributed inter-arrival times)
  - Minor stops / idling events
  - Setup & changeover events
  - Part counts with quality tracking (good / scrap / rework)
  - Reduced speed periods

Output: CSV of timestamped events consumable by the OEE calculator.

Event schema:
  timestamp     : datetime of event start
  machine_id    : which machine
  event_type    : PRODUCTION | BREAKDOWN | MINOR_STOP | SETUP | BREAK | SPEED_LOSS
  duration_min  : duration in minutes
  parts_produced: parts made during this event window
  parts_good    : conforming parts
  parts_scrap   : scrapped parts
  shift         : shift identifier (e.g. "2024-01-15_S1")
  operator      : operator ID
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd


# ─── Event types ─────────────────────────────────────────────────────────────

class EventType:
    PRODUCTION  = "PRODUCTION"
    BREAKDOWN   = "BREAKDOWN"
    MINOR_STOP  = "MINOR_STOP"
    SETUP       = "SETUP"
    BREAK       = "BREAK"
    SPEED_LOSS  = "SPEED_LOSS"


# ─── Shift Simulator ─────────────────────────────────────────────────────────

class ShiftSimulator:
    """
    Simulates a single production shift for one machine.

    Args:
        machine_id:           Machine identifier
        shift_start:          Datetime of shift start
        planned_hours:        Total planned shift duration (hours)
        ideal_cycle_time_sec: Seconds to produce one good part at full speed
        seed:                 Random seed for reproducibility
        config:               Dict of simulator parameters (from config.yaml)
    """

    BREAK_SCHEDULE = [(2.0, 15), (5.5, 15)]   # (hours_into_shift, duration_min)

    def __init__(
        self,
        machine_id: str,
        shift_start: datetime,
        planned_hours: float = 8.0,
        ideal_cycle_time_sec: float = 45.0,
        seed: int = 42,
        config: dict | None = None,
    ):
        self.machine_id    = machine_id
        self.shift_start   = shift_start
        self.planned_hours = planned_hours
        self.ideal_ct      = ideal_cycle_time_sec
        self.rng           = np.random.default_rng(seed)
        cfg = config or {}

        # Rates & durations from config
        self.breakdown_rate    = cfg.get("breakdown_rate",    1.4)
        self.minor_stop_rate   = cfg.get("minor_stop_rate",   6.0)
        self.setup_rate        = cfg.get("setup_rate",        0.8)
        self.breakdown_mean    = cfg.get("breakdown_mean_min", 22.0)
        self.breakdown_std     = cfg.get("breakdown_std_min",  12.0)
        self.minor_stop_mean   = cfg.get("minor_stop_mean_min", 2.5)
        self.setup_mean        = cfg.get("setup_mean_min",    18.0)
        self.scrap_rate        = cfg.get("scrap_rate",         0.076)
        self.rework_rate       = cfg.get("rework_rate",        0.023)

    def _planned_production_minutes(self) -> float:
        """Total shift time minus scheduled breaks."""
        break_total = sum(d for _, d in self.BREAK_SCHEDULE)
        return self.planned_hours * 60 - break_total

    def _sample_breakdowns(self) -> list[tuple[float, float]]:
        """
        Sample breakdown events during the shift.
        Returns list of (start_minute_into_shift, duration_min).
        Uses Poisson process for arrivals, log-normal for durations.
        """
        n = self.rng.poisson(self.breakdown_rate)
        events = []
        for _ in range(n):
            start = self.rng.uniform(0, self.planned_hours * 60)
            dur   = max(2.0, self.rng.lognormal(
                np.log(self.breakdown_mean), self.breakdown_std / self.breakdown_mean
            ))
            events.append((start, dur))
        return sorted(events)

    def _sample_minor_stops(self) -> list[tuple[float, float]]:
        """Sample minor stop events (< 5 min, idling, jams)."""
        n = self.rng.poisson(self.minor_stop_rate)
        events = []
        for _ in range(n):
            start = self.rng.uniform(0, self.planned_hours * 60)
            dur   = self.rng.exponential(self.minor_stop_mean)
            dur   = min(dur, 4.9)  # by definition minor stops < 5 min
            events.append((start, max(0.5, dur)))
        return sorted(events)

    def _sample_setups(self) -> list[tuple[float, float]]:
        """Sample setup / changeover events."""
        n = self.rng.poisson(self.setup_rate)
        events = []
        for _ in range(n):
            start = self.rng.uniform(10, self.planned_hours * 60 - 20)
            dur   = max(5.0, self.rng.normal(self.setup_mean, 5.0))
            events.append((start, dur))
        return sorted(events)

    def _parts_in_window(
        self, duration_min: float, speed_factor: float = 1.0
    ) -> tuple[int, int, int]:
        """
        Calculate parts produced, good parts, and scrap in a production window.

        Args:
            duration_min: Duration of production window in minutes
            speed_factor: 1.0 = ideal speed, < 1.0 = reduced speed

        Returns:
            (total_parts, good_parts, scrap_parts)
        """
        ideal_rate = 60 / self.ideal_ct   # parts/minute at full speed
        actual_rate = ideal_rate * speed_factor
        total = max(0, int(actual_rate * duration_min))

        scrap_n = self.rng.binomial(total, self.scrap_rate)
        rework_n = self.rng.binomial(total - scrap_n, self.rework_rate)
        good = total - scrap_n  # rework eventually becomes good

        return total, good, scrap_n

    def run(self) -> pd.DataFrame:
        """
        Simulate one full shift.

        Returns:
            DataFrame of production events for this shift.
        """
        shift_id = self.shift_start.strftime("%Y-%m-%d_S") + str(
            (self.shift_start.hour // 8) + 1
        )
        operator_id = f"OP{self.rng.integers(1, 20):03d}"

        # Build disruption timeline
        breakdowns  = {(t, d, EventType.BREAKDOWN)   for t, d in self._sample_breakdowns()}
        minor_stops = {(t, d, EventType.MINOR_STOP)  for t, d in self._sample_minor_stops()}
        setups      = {(t, d, EventType.SETUP)        for t, d in self._sample_setups()}

        # Breaks (fixed schedule)
        breaks = {
            (h * 60, dur, EventType.BREAK)
            for h, dur in self.BREAK_SCHEDULE
        }

        # Merge and sort all disruptions
        all_events = sorted(
            breakdowns | minor_stops | setups | breaks,
            key=lambda x: x[0]
        )

        records = []
        cursor = 0.0  # minutes into shift
        shift_end = self.planned_hours * 60

        def add_record(etype, start_offset, dur, speed=1.0):
            ts = self.shift_start + timedelta(minutes=start_offset)
            if etype == EventType.PRODUCTION:
                total, good, scrap = self._parts_in_window(dur, speed)
            else:
                total = good = scrap = 0
            records.append({
                "timestamp":      ts,
                "machine_id":     self.machine_id,
                "event_type":     etype,
                "duration_min":   round(dur, 2),
                "parts_produced": total,
                "parts_good":     good,
                "parts_scrap":    scrap,
                "shift":          shift_id,
                "operator":       operator_id,
            })

        for start_min, dur_min, etype in all_events:
            # Clamp to shift window
            if start_min >= shift_end:
                continue
            dur_min = min(dur_min, shift_end - start_min)

            # Production gap before this event
            if start_min > cursor:
                gap = start_min - cursor
                # Occasionally simulate speed loss before breakdown
                if etype == EventType.BREAKDOWN and self.rng.random() < 0.3:
                    speed_loss_dur = min(gap, self.rng.uniform(5, 15))
                    prod_dur = gap - speed_loss_dur
                    if prod_dur > 0:
                        add_record(EventType.PRODUCTION, cursor, prod_dur, 1.0)
                    add_record(EventType.SPEED_LOSS, cursor + prod_dur, speed_loss_dur, 0.6)
                else:
                    add_record(EventType.PRODUCTION, cursor, gap, 1.0)
                cursor = start_min

            # The disruption event itself
            add_record(etype, cursor, dur_min)
            cursor = start_min + dur_min

        # Remaining production at end of shift
        if cursor < shift_end:
            add_record(EventType.PRODUCTION, cursor, shift_end - cursor, 1.0)

        return pd.DataFrame(records)


# ─── Multi-machine, multi-shift factory ──────────────────────────────────────

class FactorySimulator:
    """
    Runs the shift simulator across multiple machines and shifts.

    Args:
        machines:   List of machine IDs
        n_shifts:   Total number of shifts to simulate
        start_date: First shift start date
        config:     Config dict (from config.yaml)
    """

    def __init__(
        self,
        machines: list[str] | None = None,
        n_shifts: int = 15,
        start_date: str = "2024-01-15",
        config: dict | None = None,
    ):
        self.machines   = machines or ["M01", "M02", "M03", "M04"]
        self.n_shifts   = n_shifts
        self.start_date = datetime.strptime(start_date, "%Y-%m-%d")
        self.config     = config or {}

    def _shift_starts(self) -> list[tuple[str, datetime]]:
        """Generate (machine_id, shift_start) pairs."""
        starts = []
        shift_hours = [0, 8, 16]  # 3 shifts per day
        dt = self.start_date
        count = 0
        while count < self.n_shifts:
            for h in shift_hours:
                if count >= self.n_shifts:
                    break
                shift_dt = dt.replace(hour=h, minute=0, second=0)
                for machine in self.machines:
                    starts.append((machine, shift_dt))
                count += 1
            dt += timedelta(days=1)
        return starts

    def run(self, output_path: str = "data/production_events.csv") -> pd.DataFrame:
        """
        Simulate all shifts and save to CSV.

        Returns:
            Full events DataFrame.
        """
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        all_dfs = []
        pairs = self._shift_starts()
        print(f"\n🏭 Simulating {self.n_shifts} shifts × {len(self.machines)} machines "
              f"= {len(pairs)} total...")

        for i, (machine_id, shift_start) in enumerate(pairs):
            sim = ShiftSimulator(
                machine_id=machine_id,
                shift_start=shift_start,
                ideal_cycle_time_sec=self.config.get("ideal_cycle_time_sec", 45),
                seed=i * 7 + 13,
                config=self.config.get("simulator", {}),
            )
            df = sim.run()
            all_dfs.append(df)

        result = pd.concat(all_dfs, ignore_index=True)
        result = result.sort_values(["machine_id", "timestamp"]).reset_index(drop=True)
        result.to_csv(output_path, index=False)

        print(f"✅ {len(result)} events saved to {output_path}")
        print(f"   Machines: {self.machines}")
        print(f"   Date range: {result['timestamp'].min()} → {result['timestamp'].max()}")
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulate production events")
    parser.add_argument("--shifts",   type=int,  default=15)
    parser.add_argument("--machines", nargs="+", default=["M01","M02","M03","M04"])
    parser.add_argument("--output",   default="data/production_events.csv")
    args = parser.parse_args()

    sim = FactorySimulator(machines=args.machines, n_shifts=args.shifts)
    sim.run(output_path=args.output)
