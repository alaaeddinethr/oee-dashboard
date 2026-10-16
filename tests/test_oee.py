"""test_oee.py — Unit tests for OEE calculator."""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.simulator import FactorySimulator, ShiftSimulator
from src.oee.calculator import OEECalculator, OEEResult


def make_events(seed=0, n_shifts=3, machines=None):
    machines = machines or ["M01"]
    sim = FactorySimulator(machines=machines, n_shifts=n_shifts,
                           start_date="2024-01-15")
    return sim.run(output_path=f"/tmp/test_oee_{seed}.csv")


class TestShiftSimulator:

    def test_run_returns_dataframe(self):
        from datetime import datetime
        sim = ShiftSimulator("M01", datetime(2024, 1, 15, 6), seed=1)
        df = sim.run()
        assert isinstance(df, pd.DataFrame)

    def test_all_required_columns(self):
        from datetime import datetime
        sim = ShiftSimulator("M01", datetime(2024, 1, 15, 6), seed=2)
        df = sim.run()
        required = ["timestamp","machine_id","event_type","duration_min",
                    "parts_produced","parts_good","parts_scrap","shift","operator"]
        for col in required:
            assert col in df.columns, f"Missing column: {col}"

    def test_parts_good_le_parts_produced(self):
        from datetime import datetime
        sim = ShiftSimulator("M01", datetime(2024, 1, 15, 6), seed=3)
        df = sim.run()
        assert (df["parts_good"] <= df["parts_produced"]).all()

    def test_parts_scrap_non_negative(self):
        from datetime import datetime
        sim = ShiftSimulator("M01", datetime(2024, 1, 15, 6), seed=4)
        df = sim.run()
        assert (df["parts_scrap"] >= 0).all()

    def test_duration_positive(self):
        from datetime import datetime
        sim = ShiftSimulator("M01", datetime(2024, 1, 15, 6), seed=5)
        df = sim.run()
        assert (df["duration_min"] > 0).all()

    def test_machine_id_consistent(self):
        from datetime import datetime
        sim = ShiftSimulator("M99", datetime(2024, 1, 15, 6), seed=6)
        df = sim.run()
        assert (df["machine_id"] == "M99").all()


class TestOEECalculator:

    def setup_method(self):
        self.events = make_events(seed=42, n_shifts=5)
        self.calc = OEECalculator(self.events, planned_shift_min=450,
                                  ideal_cycle_time_sec=45)

    def test_compute_all_returns_list(self):
        results = self.calc.compute_all()
        assert isinstance(results, list)
        assert len(results) > 0

    def test_all_results_are_oee_result(self):
        for r in self.calc.compute_all():
            assert isinstance(r, OEEResult)

    def test_oee_bounded_0_1(self):
        for r in self.calc.compute_all():
            assert 0.0 <= r.oee <= 1.0, f"OEE={r.oee} out of bounds"

    def test_availability_bounded_0_1(self):
        for r in self.calc.compute_all():
            assert 0.0 <= r.availability <= 1.0

    def test_performance_bounded_0_1(self):
        for r in self.calc.compute_all():
            assert 0.0 <= r.performance <= 1.0

    def test_quality_bounded_0_1(self):
        for r in self.calc.compute_all():
            assert 0.0 <= r.quality <= 1.0

    def test_oee_equals_apq(self):
        for r in self.calc.compute_all():
            expected = r.availability * r.performance * r.quality
            assert abs(r.oee - expected) < 1e-8, \
                f"OEE={r.oee} != A×P×Q={expected}"

    def test_parts_good_le_total(self):
        for r in self.calc.compute_all():
            assert r.parts_good <= r.parts_total

    def test_mtbf_positive(self):
        for r in self.calc.compute_all():
            assert r.mtbf_min >= 0

    def test_to_dataframe_columns(self):
        df = self.calc.to_dataframe()
        for col in ["oee","availability","performance","quality","machine_id","shift"]:
            assert col in df.columns

    def test_summary_by_machine(self):
        summary = self.calc.summary()
        assert "oee_mean" in summary.columns
        assert len(summary) == len(self.events["machine_id"].unique())

    def test_perfect_production_oee_near_1(self):
        """Synthetic perfect-shift data should give OEE close to 1."""
        # Build a single pure-production shift with no scrap and no stops
        n_parts = int(450 / (45/60))  # all 450 min at ideal rate
        perfect_events = pd.DataFrame([{
            "timestamp":      "2024-01-15 06:00:00",
            "machine_id":     "M01",
            "event_type":     "PRODUCTION",
            "duration_min":   450.0,
            "parts_produced": n_parts,
            "parts_good":     n_parts,
            "parts_scrap":    0,
            "shift":          "2024-01-15_S1",
            "operator":       "OP001",
        }])
        calc = OEECalculator(perfect_events, planned_shift_min=450,
                             ideal_cycle_time_sec=45)
        result = calc.compute_all()[0]
        assert result.availability >= 0.99
        assert result.performance  >= 0.99
        assert result.quality      == 1.0

    def test_breaks_are_not_counted_twice(self):
        """Regression: scheduled breaks are already excluded from planned_shift_min.

        8 h shift = 420 min at ideal speed + 30 min at 60 % speed + 30 min of
        breaks. Net planned time is 450 min with no stops, so run time is
        450 min and performance must show the speed loss:
        (560 + 24) / (450 / 0.75) = 0.973. Subtracting the breaks again gave
        a 420-min run time, a performance above 100 % clipped to 1.0, and
        hid the speed loss entirely.
        """
        rows = [
            ("PRODUCTION", 420.0, 560),
            ("SPEED_LOSS", 30.0, 24),
            ("BREAK", 30.0, 0),
        ]
        events = pd.DataFrame([{
            "timestamp": "2024-01-15 06:00:00", "machine_id": "M01",
            "event_type": et, "duration_min": d,
            "parts_produced": n, "parts_good": n, "parts_scrap": 0,
            "shift": "2024-01-15_S1", "operator": "OP001",
        } for et, d, n in rows])
        result = OEECalculator(events, planned_shift_min=450,
                               ideal_cycle_time_sec=45).compute_all()[0]
        assert result.run_time_min == pytest.approx(450.0)
        assert result.availability == pytest.approx(1.0)
        assert result.performance == pytest.approx(584 / 600, abs=1e-3)

    def test_minor_stops_are_a_performance_loss(self):
        """Six Big Losses: minor stops lower performance, not availability."""
        rows = [("PRODUCTION", 420.0, 560), ("MINOR_STOP", 30.0, 0), ("BREAK", 30.0, 0)]
        events = pd.DataFrame([{
            "timestamp": "2024-01-15 06:00:00", "machine_id": "M01",
            "event_type": et, "duration_min": d,
            "parts_produced": n, "parts_good": n, "parts_scrap": 0,
            "shift": "2024-01-15_S1", "operator": "OP001",
        } for et, d, n in rows])
        result = OEECalculator(events, planned_shift_min=450,
                               ideal_cycle_time_sec=45).compute_all()[0]
        assert result.availability == pytest.approx(1.0)
        assert result.performance == pytest.approx(560 / 600, abs=1e-3)

    def test_zero_production_oee_zero(self):
        """A shift of only breakdowns should give OEE = 0."""
        zero_events = pd.DataFrame([{
            "timestamp": "2024-01-15 06:00:00",
            "machine_id": "M01", "event_type": "BREAKDOWN",
            "duration_min": 450.0,
            "parts_produced": 0, "parts_good": 0, "parts_scrap": 0,
            "shift": "2024-01-15_S1", "operator": "OP001",
        }])
        calc = OEECalculator(zero_events, planned_shift_min=450,
                             ideal_cycle_time_sec=45)
        result = calc.compute_all()[0]
        assert result.availability == 0.0
        assert result.oee == 0.0


class TestOEEClassification:

    def _make_result(self, oee):
        from src.oee.calculator import OEEResult
        return OEEResult(
            machine_id="M01", shift="test",
            planned_time_min=450, downtime_min=0,
            planned_stop_min=30, run_time_min=420,
            parts_total=560, parts_good=int(560*oee),
            parts_scrap=int(560*(1-oee)),
            availability=oee**(1/3), performance=oee**(1/3),
            quality=oee**(1/3), oee=oee,
            n_breakdowns=0, mtbf_min=450, mttr_min=0,
        )

    def test_world_class(self):
        assert self._make_result(0.87).classification() == "World Class"

    def test_good(self):
        assert self._make_result(0.78).classification() == "Good"

    def test_typical(self):
        assert self._make_result(0.65).classification() == "Typical"

    def test_poor(self):
        assert self._make_result(0.50).classification() == "Poor"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
