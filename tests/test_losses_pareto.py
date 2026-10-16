"""test_losses.py & test_pareto.py — combined test module."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.simulator import FactorySimulator
from src.lean.pareto import ParetoAnalyzer, ParetoItem
from src.oee.losses import LossAnalyzer, LossBreakdown


def make_events(seed=99, n_shifts=5, machines=None):
    machines = machines or ["M01", "M02"]
    sim = FactorySimulator(machines=machines, n_shifts=n_shifts,
                           start_date="2024-03-01")
    return sim.run(output_path=f"/tmp/test_losses_{seed}.csv")


class TestLossAnalyzer:

    def setup_method(self):
        self.events = make_events()
        self.analyzer = LossAnalyzer(self.events, planned_shift_min=450,
                                     ideal_cycle_time_sec=45)

    def test_compute_all_nonempty(self):
        results = self.analyzer.compute_all()
        assert len(results) > 0

    def test_all_results_are_loss_breakdown(self):
        for lb in self.analyzer.compute_all():
            assert isinstance(lb, LossBreakdown)

    def test_losses_non_negative(self):
        for lb in self.analyzer.compute_all():
            for k, v in lb.losses_dict.items():
                assert v >= 0, f"{k} loss is negative: {v}"

    def test_total_loss_sum_of_parts(self):
        for lb in self.analyzer.compute_all():
            expected = sum(lb.losses_dict.values())
            assert abs(lb.total_loss_min - expected) < 1e-8

    def test_total_loss_le_planned_time(self):
        for lb in self.analyzer.compute_all():
            assert lb.total_loss_min <= lb.planned_time_min + 1.0

    def test_losses_pct_sum_le_100(self):
        for lb in self.analyzer.compute_all():
            total_pct = sum(lb.losses_pct.values())
            assert total_pct <= 100.5, f"Loss percentages sum to {total_pct}"

    def test_category_totals_correct(self):
        for lb in self.analyzer.compute_all():
            cats = lb.category_totals()
            avail_total = lb.equipment_failure_min + lb.setup_adjustment_min
            assert abs(cats["Availability Losses"] - avail_total) < 1e-8

    def test_aggregate_by_machine_has_all_machines(self):
        agg = self.analyzer.aggregate_by_machine()
        machines_in_events = set(self.events["machine_id"].unique())
        machines_in_agg = set(agg["machine_id"].unique())
        assert machines_in_agg == machines_in_events

    def test_aggregate_total_keys(self):
        total = self.analyzer.aggregate_total()
        expected_keys = {"Equipment Failure", "Setup & Adjustment",
                         "Idling & Minor Stops", "Reduced Speed",
                         "Process Defects", "Reduced Yield"}
        assert set(total.keys()) == expected_keys

    def test_top_losses_sorted_descending(self):
        tops = self.analyzer.top_losses(top_n=3)
        values = [v for _, v in tops]
        assert values == sorted(values, reverse=True)

    def test_waterfall_data_has_result_row(self):
        df = self.analyzer.waterfall_data()
        assert "result" in df["type"].values

    def test_waterfall_planned_time_first(self):
        df = self.analyzer.waterfall_data()
        assert df.iloc[0]["type"] == "start"


class TestParetoAnalyzer:

    def setup_method(self):
        self.events = make_events()
        self.pareto = ParetoAnalyzer(self.events)

    def test_compute_returns_list(self):
        items = self.pareto.compute()
        assert isinstance(items, list)

    def test_all_items_are_pareto_item(self):
        for item in self.pareto.compute():
            assert isinstance(item, ParetoItem)

    def test_cumulative_pct_ends_at_100(self):
        items = self.pareto.compute()
        if items:
            assert items[-1].cumulative_pct >= 99.0

    def test_cumulative_pct_monotone(self):
        items = self.pareto.compute()
        cumul = [item.cumulative_pct for item in items]
        assert cumul == sorted(cumul)

    def test_ranks_sequential(self):
        items = self.pareto.compute()
        ranks = [item.rank for item in items]
        assert ranks == list(range(1, len(items) + 1))

    def test_values_descending(self):
        items = self.pareto.compute()
        values = [item.value for item in items]
        assert values == sorted(values, reverse=True)

    def test_abc_classes_valid(self):
        for item in self.pareto.compute():
            assert item.abc_class in {"A", "B", "C"}

    def test_vital_few_all_class_a(self):
        vital = self.pareto.vital_few()
        for item in vital:
            assert item.abc_class == "A"

    def test_to_dataframe_has_required_cols(self):
        df = self.pareto.to_dataframe()
        required = ["Rank","Cause","Total (min)","Occurrences","Cumulative %","ABC Class"]
        for col in required:
            assert col in df.columns, f"Missing column: {col}"

    def test_count_positive(self):
        for item in self.pareto.compute():
            assert item.count > 0

    def test_avg_duration_positive(self):
        for item in self.pareto.compute():
            assert item.avg_duration > 0

    def test_priority_labels_valid(self):
        valid_priorities = {"Critical", "Important", "Monitor"}
        for item in self.pareto.compute():
            assert item.priority in valid_priorities

    def test_empty_filter_returns_empty(self):
        pareto_empty = ParetoAnalyzer(self.events, filter_types={"NONEXISTENT"})
        assert pareto_empty.compute() == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
