"""Reproduce the README results and figure from a fresh simulation.

    python scripts/make_readme_figures.py

Simulates 15 shifts on 4 machines (3 shifts/day, 5 days, fixed seeds), then
writes assets/oee_overview.png and assets/sample_results.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data.simulator import FactorySimulator  # noqa: E402
from src.oee.calculator import OEECalculator  # noqa: E402
from src.oee.losses import LossAnalyzer  # noqa: E402

PLANNED, CT = 450, 45


def main() -> dict:
    events = FactorySimulator(n_shifts=15).run()
    calc = OEECalculator(events, planned_shift_min=PLANNED, ideal_cycle_time_sec=CT)
    shifts = calc.to_dataframe()
    losses = dict(LossAnalyzer(events, planned_shift_min=PLANNED, ideal_cycle_time_sec=CT).top_losses(6))
    res = calc.compute_all()
    mtbf = [r.mtbf_min for r in res if r.mtbf_min]
    mttr = [r.mttr_min for r in res if r.mttr_min]
    total_loss = sum(losses.values())
    summary = {
        "shifts": int(len(shifts)),
        "oee": round(float(shifts["oee"].mean()), 3),
        "availability": round(float(shifts["availability"].mean()), 3),
        "performance": round(float(shifts["performance"].mean()), 3),
        "quality": round(float(shifts["quality"].mean()), 3),
        "mtbf_min": round(float(np.mean(mtbf)), 0),
        "mttr_min": round(float(np.mean(mttr)), 1),
        "scrap_rate": round(float(events["parts_scrap"].sum() / events["parts_produced"].sum()), 3),
        "loss_share": {k: round(v / total_loss, 3) for k, v in losses.items()},
    }

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 3.8), gridspec_kw={"width_ratios": [1, 1.3]})
    by_m = shifts.groupby("machine_id")[["availability", "performance", "quality", "oee"]].mean()
    x = np.arange(len(by_m))
    for i, (col, c) in enumerate(zip(["availability", "performance", "quality", "oee"],
                                     ["#9fc3e7", "#a8d5ba", "#e7c59f", "#1f6feb"])):
        a1.bar(x + (i - 1.5) * 0.2, by_m[col] * 100, 0.18, color=c,
               label=col.capitalize() if col != "oee" else "OEE")
    a1.axhline(85, ls="--", lw=1, color="#1a7f37")
    a1.text(len(by_m) - 0.5, 86, "world class 85 %", ha="right", fontsize=8, color="#1a7f37")
    a1.set_xticks(x, by_m.index)
    a1.set_ylim(50, 104)
    a1.set_ylabel("%")
    a1.set_title("OEE and its three factors by machine", fontsize=10)
    a1.legend(frameon=False, fontsize=8, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.1))

    names = [n for n in losses if losses[n] > 0]
    vals = np.array([losses[n] for n in names]) / 60
    cum = np.cumsum(vals) / vals.sum() * 100
    a2.bar(names, vals, color="#d1242f", alpha=0.8)
    a2.set_ylabel("Hours lost")
    a2b = a2.twinx()
    a2b.plot(names, cum, color="#24292f", marker="o", ms=4)
    a2b.axhline(80, ls=":", lw=1, color="#57606a")
    a2b.set_ylim(0, 105)
    a2b.set_ylabel("Cumulative %")
    a2.set_title("Pareto of losses (where to act first)", fontsize=10)
    a2.tick_params(axis="x", labelsize=8, rotation=15)
    for ax in (a1, a2, a2b):
        ax.spines[["top"]].set_visible(False)
    fig.tight_layout()
    out = ROOT / "assets"
    out.mkdir(exist_ok=True)
    fig.savefig(out / "oee_overview.png", dpi=150)
    (out / "sample_results.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    main()
