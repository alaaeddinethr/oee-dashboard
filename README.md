# 🏭 OEE Dashboard — Lean Manufacturing Analytics

<div align="center">

![Python](https://img.shields.io/badge/Python-3.10+-blue?style=flat-square&logo=python)
![Streamlit](https://img.shields.io/badge/Streamlit-1.35-red?style=flat-square&logo=streamlit)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)
![CI](https://img.shields.io/github/actions/workflow/status/alaaeddinethr/oee-dashboard/ci.yml?style=flat-square&label=CI)

**Production line efficiency analytics — OEE computation, 6 Big Losses decomposition,
Pareto analysis, and real-time monitoring dashboard.**

[Live Demo](#) · [Documentation](#architecture) · [Quickstart](#quickstart)

</div>

---

## 📌 Context & Motivation

Overall Equipment Effectiveness (OEE) is the gold standard KPI for measuring
manufacturing productivity. An OEE of 100% means perfect production: only good
parts, as fast as possible, with no downtime.

World-class OEE is considered **85%**. Most plants operate between 40–60%.
The gap represents recoverable capacity — without buying a single new machine.

This project implements a complete OEE analytics pipeline:
1. Realistic production event simulation (or live CSV import)
2. OEE computation with full loss decomposition
3. 6 Big Losses analysis with Pareto prioritization
4. Interactive real-time monitoring dashboard
5. Shift/machine/product comparison reports

> Inspired by hands-on experience during an industrial internship at **Stellantis Metz**
> (assembly line, quality, continuous improvement, 2024).

---

## 📐 OEE Formula

```
OEE = Availability × Performance × Quality

Availability = Run Time / Planned Production Time
Performance  = (Ideal Cycle Time × Total Count) / Run Time
Quality      = Good Count / Total Count
```

### The 6 Big Losses (Lean / TPM Framework)

| Category | Loss | Description |
|----------|------|-------------|
| **Availability** | Equipment Failure | Unplanned breakdowns |
| **Availability** | Setup & Adjustment | Planned changeovers, tool changes |
| **Performance** | Idling & Minor Stops | Jams, sensor faults (< 5 min) |
| **Performance** | Reduced Speed | Running below ideal cycle time |
| **Quality** | Process Defects | Scrap during steady-state production |
| **Quality** | Reduced Yield | Startup scrap / warm-up losses |

---

## 🏗️ Architecture

```
oee-dashboard/
│
├── src/
│   ├── data/
│   │   └── simulator.py           # Realistic production event generator
│   │
│   ├── oee/
│   │   ├── calculator.py          # OEE, Availability, Performance, Quality
│   │   └── losses.py              # 6 Big Losses decomposition + MTBF/MTTR
│   │
│   ├── lean/
│   │   ├── pareto.py              # Pareto analysis, 80/20 rule, priority ranking
│   │   └── report.py              # Shift reports, machine comparison, trend analysis
│   │
│   └── dashboard/
│       └── app.py                 # Streamlit interactive dashboard
│
├── tests/
│   ├── test_oee.py
│   ├── test_losses.py
│   └── test_pareto.py
│
├── notebooks/
│   └── 01_OEE_Analysis.ipynb
│
├── .github/workflows/ci.yml
├── config.yaml
└── requirements.txt
```

---

## 📊 Sample Results

On a simulated 3-shift automotive assembly line (8h/shift, 5 days):

| Metric | Value |
|--------|-------|
| **OEE** | **71.4%** |
| Availability | 87.2% |
| Performance | 88.6% |
| Quality | 92.4% |
| Top Loss | Equipment Failure (38% of downtime) |
| MTBF | 4.2 hours |
| MTTR | 22 minutes |
| Scrap Rate | 7.6% |

*Gap to world-class (85% OEE): 13.6 points — mostly recoverable via MTTR reduction*

---

## 🚀 Quick Start

```bash
git clone https://github.com/alaaeddinethr/oee-dashboard.git
cd oee-dashboard
pip install -r requirements.txt

# Generate sample data
python src/data/simulator.py --shifts 15 --machines 4

# Compute OEE report
python src/oee/calculator.py --data data/production_events.csv

# Launch dashboard
streamlit run src/dashboard/app.py
```

---

## 📚 References

- [1] Nakajima, S. (1988). *Introduction to TPM: Total Productive Maintenance*. Productivity Press.
- [2] Womack, J.P. & Jones, D.T. (1996). *Lean Thinking*. Simon & Schuster.
- [3] SEMI E10 Standard — Equipment Reliability, Availability, and Maintainability.
- [4] Rother, M. & Shook, J. (1999). *Learning to See: Value Stream Mapping*. LEI.

---

## 👤 Author

**Alaa Eddine TAHIR** — Engineering student at Arts et Métiers ParisTech
Industrial internship at Stellantis Metz (2024) — Assembly lines, quality, continuous improvement.
[LinkedIn](https://linkedin.com/in/alaaeddine-tahir) · [GitHub](https://github.com/alaaeddinethr)
