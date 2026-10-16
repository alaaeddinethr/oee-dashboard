"""
app.py
------
Interactive OEE dashboard — Streamlit interface.

Sections:
  1. Live KPIs — real-time OEE, Availability, Performance, Quality
  2. 6 Big Losses — waterfall chart and breakdown table
  3. Pareto Analysis — 80/20 loss prioritization
  4. Machine Comparison — cross-machine OEE bar chart
  5. Trend — OEE over shifts with rolling average
  6. Anomaly Detection — flagged low-performance shifts

Run:
    streamlit run src/dashboard/app.py
"""

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.data.simulator import FactorySimulator
from src.lean.pareto import ParetoAnalyzer
from src.lean.report import ReportEngine
from src.oee.calculator import OEECalculator
from src.oee.losses import LossAnalyzer

# ─── Page config ─────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="OEE Dashboard",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@400;600;700&family=Barlow:wght@300;400;500&display=swap');
html,[class*="css"]{font-family:'Barlow',sans-serif}
.stApp{background:#f0f2f5}
h1,h2,h3{font-family:'Barlow Condensed',sans-serif;letter-spacing:.02em}
.kpi-card{background:#fff;border-radius:6px;padding:1.2rem;text-align:center;
  border-top:4px solid #2563eb;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.kpi-label{font-size:.68rem;color:#6b7280;text-transform:uppercase;letter-spacing:.1em;margin-bottom:.3rem}
.kpi-value{font-family:'Barlow Condensed',sans-serif;font-size:2.2rem;font-weight:700;line-height:1}
.kpi-sub{font-size:.7rem;color:#9ca3af;margin-top:.2rem}
.world-class{border-top-color:#16a34a}.good{border-top-color:#2563eb}
.typical{border-top-color:#d97706}.poor{border-top-color:#dc2626}
.section-header{font-family:'Barlow Condensed',sans-serif;font-size:1.1rem;
  font-weight:600;letter-spacing:.05em;color:#374151;
  border-bottom:2px solid #e5e7eb;padding-bottom:.4rem;margin-bottom:1rem}
</style>
""", unsafe_allow_html=True)

THEME = dict(
    paper_bgcolor="#ffffff",
    plot_bgcolor="#ffffff",
    font=dict(color="#374151", family="Barlow"),
    xaxis=dict(gridcolor="#f3f4f6", linecolor="#e5e7eb"),
    yaxis=dict(gridcolor="#f3f4f6", linecolor="#e5e7eb"),
)
OEE_COLORS = {"World Class": "#16a34a", "Good": "#2563eb",
               "Typical": "#d97706", "Poor": "#dc2626"}
LOSS_COLORS = {
    "Equipment Failure":    "#ef4444",
    "Setup & Adjustment":   "#f97316",
    "Idling & Minor Stops": "#eab308",
    "Reduced Speed":        "#84cc16",
    "Process Defects":      "#06b6d4",
    "Reduced Yield":        "#8b5cf6",
}

# ─── Helpers ─────────────────────────────────────────────────────────────────

def oee_class(oee: float) -> str:
    if oee >= 0.85: return "world-class"
    if oee >= 0.75: return "good"
    if oee >= 0.60: return "typical"
    return "poor"

def kpi_card(label, value, sub="", css_class=""):
    st.markdown(f"""
    <div class="kpi-card {css_class}">
      <div class="kpi-label">{label}</div>
      <div class="kpi-value">{value}</div>
      <div class="kpi-sub">{sub}</div>
    </div>""", unsafe_allow_html=True)

@st.cache_data(show_spinner=False)
def get_data(n_shifts: int, machines: tuple, seed: int) -> pd.DataFrame:
    sim = FactorySimulator(
        machines=list(machines),
        n_shifts=n_shifts,
        start_date="2024-01-15",
        config={"ideal_cycle_time_sec": 45,
                "simulator": {"breakdown_rate": 1.4, "minor_stop_rate": 6.0,
                              "setup_rate": 0.8, "scrap_rate": 0.076,
                              "breakdown_mean_min": 22, "breakdown_std_min": 12,
                              "minor_stop_mean_min": 2.5, "setup_mean_min": 18}},
    )
    return sim.run(output_path=f"data/sim_{n_shifts}_{seed}.csv")

# ─── Sidebar ─────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🏭 OEE Dashboard")
    st.divider()
    st.markdown("### Simulation Settings")
    n_shifts  = st.slider("Number of shifts", 5, 30, 15)
    n_machines = st.slider("Number of machines", 1, 4, 3)
    machines = tuple([f"M0{i+1}" for i in range(n_machines)])
    seed = st.number_input("Random seed", value=42, min_value=0, step=1)
    run_btn = st.button("▶  Simulate & Analyse", type="primary", use_container_width=True)
    st.divider()
    st.markdown("### Machine Selection")
    selected_machine = st.selectbox("Focus machine", options=list(machines))
    st.divider()
    st.markdown("### Thresholds")
    world_class = st.slider("World-class OEE (%)", 75, 95, 85)
    st.caption("Industry standard: 85%")

# ─── Main ─────────────────────────────────────────────────────────────────────

st.markdown("# 🏭 OEE Manufacturing Dashboard")
st.markdown("*Overall Equipment Effectiveness · 6 Big Losses · Pareto · Lean Analytics*")
st.divider()

if not run_btn:
    st.info("Configure your simulation in the sidebar and click **Simulate & Analyse**.")
    st.stop()

with st.spinner("Running simulation..."):
    events_df = get_data(n_shifts, machines, int(seed))
    calc = OEECalculator(events_df, planned_shift_min=450, ideal_cycle_time_sec=45)
    oee_df = calc.to_dataframe()
    loss_analyzer = LossAnalyzer(events_df, planned_shift_min=450, ideal_cycle_time_sec=45)
    pareto = ParetoAnalyzer(events_df)
    report = ReportEngine(events_df, planned_shift_min=450, ideal_cycle_time_sec=45)

# ─── Global KPIs ──────────────────────────────────────────────────────────────
st.markdown('<div class="section-header">GLOBAL KPIs</div>', unsafe_allow_html=True)

mean_oee  = oee_df["oee"].mean()
mean_avail = oee_df["availability"].mean()
mean_perf  = oee_df["performance"].mean()
mean_qual  = oee_df["quality"].mean()
total_good  = oee_df["parts_good"].sum()
total_scrap = oee_df["parts_scrap"].sum()
total_down  = oee_df["downtime_min"].sum()
total_bd    = oee_df["n_breakdowns"].sum()

c1,c2,c3,c4,c5,c6 = st.columns(6)
with c1: kpi_card("OEE", f"{mean_oee*100:.1f}%",
    "World Class" if mean_oee>=.85 else f"Gap: {(0.85-mean_oee)*100:.1f}pp",
    oee_class(mean_oee))
with c2: kpi_card("Availability", f"{mean_avail*100:.1f}%", "uptime / planned", "good")
with c3: kpi_card("Performance",  f"{mean_perf*100:.1f}%",  "actual vs ideal speed", "good")
with c4: kpi_card("Quality",      f"{mean_qual*100:.1f}%",  "good / total parts", "good")
with c5: kpi_card("Total Downtime", f"{total_down/60:.1f}h", f"{total_bd} breakdowns", "poor")
with c6: kpi_card("Scrap Rate",   f"{total_scrap/(total_good+total_scrap)*100:.1f}%",
    f"{total_scrap:,} parts scrapped", "typical")

st.divider()

# ─── OEE Gauge + Losses Waterfall ────────────────────────────────────────────
st.markdown('<div class="section-header">OEE BREAKDOWN</div>', unsafe_allow_html=True)

col_left, col_right = st.columns([1, 1.6])
with col_left:
    # Gauge chart
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=mean_oee * 100,
        delta={"reference": world_class, "valueformat": ".1f"},
        number={"suffix": "%", "font": {"size": 36}},
        gauge={
            "axis": {"range": [0, 100], "ticksuffix": "%"},
            "bar":  {"color": OEE_COLORS.get(
                "World Class" if mean_oee>=.85 else
                "Good" if mean_oee>=.75 else
                "Typical" if mean_oee>=.60 else "Poor", "#2563eb")},
            "steps": [
                {"range": [0,  60], "color": "#fee2e2"},
                {"range": [60, 75], "color": "#fef9c3"},
                {"range": [75, 85], "color": "#dbeafe"},
                {"range": [85,100], "color": "#dcfce7"},
            ],
            "threshold": {"line": {"color": "#374151", "width": 2},
                          "thickness": .8, "value": world_class},
        },
        title={"text": "Overall OEE"},
    ))
    fig.update_layout(height=280, margin=dict(l=20,r=20,t=40,b=20),
                      paper_bgcolor="#ffffff")
    st.plotly_chart(fig, use_container_width=True)

    # APQ bars
    fig2 = go.Figure()
    for label, val, color in [
        ("Availability", mean_avail, "#3b82f6"),
        ("Performance",  mean_perf,  "#10b981"),
        ("Quality",      mean_qual,  "#f59e0b"),
    ]:
        fig2.add_trace(go.Bar(
            x=[label], y=[val*100], name=label,
            marker_color=color,
            text=[f"{val*100:.1f}%"], textposition="outside",
        ))
    fig2.add_hline(y=world_class, line=dict(color="#374151", dash="dash", width=1.5),
                   annotation_text="World-class")
    fig2.update_layout(title="A × P × Q", yaxis_range=[0, 110],
                       height=220, showlegend=False, **THEME)
    st.plotly_chart(fig2, use_container_width=True)

with col_right:
    # 6 Big Losses stacked bar by machine
    machine_losses = loss_analyzer.aggregate_by_machine()
    loss_cols = ["Equipment Failure", "Setup & Adjustment", "Idling & Minor Stops",
                 "Reduced Speed", "Process Defects", "Reduced Yield"]
    loss_cols = [c for c in loss_cols if c in machine_losses.columns]

    fig3 = go.Figure()
    for loss in loss_cols:
        fig3.add_trace(go.Bar(
            name=loss, x=machine_losses["machine_id"],
            y=machine_losses[loss],
            marker_color=LOSS_COLORS.get(loss, "#94a3b8"),
        ))
    fig3.update_layout(
        barmode="stack", title="6 Big Losses by Machine (total minutes)",
        yaxis_title="Minutes", height=280, **THEME,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    st.plotly_chart(fig3, use_container_width=True)

    # Loss pie
    total_losses = loss_analyzer.aggregate_total()
    fig4 = go.Figure(go.Pie(
        labels=list(total_losses.keys()),
        values=list(total_losses.values()),
        marker_colors=[LOSS_COLORS.get(k, "#94a3b8") for k in total_losses],
        hole=.4, textinfo="label+percent",
    ))
    fig4.update_layout(title="Loss Distribution (all machines)", height=200,
                       paper_bgcolor="#ffffff", showlegend=False,
                       margin=dict(l=10,r=10,t=40,b=10))
    st.plotly_chart(fig4, use_container_width=True)

st.divider()

# ─── Pareto ───────────────────────────────────────────────────────────────────
st.markdown('<div class="section-header">PARETO ANALYSIS — 80/20 LOSS PRIORITIZATION</div>',
            unsafe_allow_html=True)

pareto_df = pareto.to_dataframe()
if not pareto_df.empty:
    col_p1, col_p2 = st.columns([1.5, 1])
    with col_p1:
        fig_p = go.Figure()
        bar_colors = [
            "#ef4444" if r["ABC Class"] == "A" else
            "#f97316" if r["ABC Class"] == "B" else "#94a3b8"
            for _, r in pareto_df.iterrows()
        ]
        fig_p.add_trace(go.Bar(
            x=pareto_df["Cause"], y=pareto_df["Total (min)"],
            marker_color=bar_colors, name="Loss (min)",
        ))
        fig_p.add_trace(go.Scatter(
            x=pareto_df["Cause"], y=pareto_df["Cumulative %"],
            mode="lines+markers", name="Cumulative %",
            yaxis="y2", line=dict(color="#374151", width=2),
            marker=dict(size=7),
        ))
        fig_p.add_hline(y=80, line=dict(color="#dc2626", dash="dot"),
                        annotation_text="80%", yref="y2")
        fig_p.update_layout(
            title="Pareto Chart — Production Losses",
            yaxis=dict(title="Total Loss (min)"),
            yaxis2=dict(title="Cumulative %", overlaying="y", side="right",
                        range=[0, 110]),
            height=340, **THEME,
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(fig_p, use_container_width=True)

    with col_p2:
        st.markdown("**ABC Classification**")
        for _, row in pareto_df.iterrows():
            badge = {"A": "🔴", "B": "🟡", "C": "🟢"}[row["ABC Class"]]
            st.markdown(
                f"{badge} **{row['Cause']}**  \n"
                f"  {row['Total (min)']:.0f} min · {row['Occurrences']} occ. · "
                f"cum. {row['Cumulative %']:.0f}%"
            )

st.divider()

# ─── Machine Comparison + Trend ───────────────────────────────────────────────
st.markdown('<div class="section-header">MACHINE COMPARISON & OEE TREND</div>',
            unsafe_allow_html=True)

col_mc, col_tr = st.columns([1, 1.5])
with col_mc:
    machine_sum = report.machine_summary()
    fig_mc = go.Figure()
    for component, color in [
        ("availability_mean", "#3b82f6"),
        ("performance_mean",  "#10b981"),
        ("quality_mean",      "#f59e0b"),
    ]:
        fig_mc.add_trace(go.Bar(
            name=component.replace("_mean","").capitalize(),
            x=machine_sum["machine_id"],
            y=machine_sum[component] * 100,
            marker_color=color, opacity=.8,
        ))
    fig_mc.add_trace(go.Scatter(
        x=machine_sum["machine_id"],
        y=machine_sum["oee_mean"] * 100,
        mode="markers+text",
        marker=dict(size=14, color="#374151", symbol="diamond"),
        text=[f"OEE: {v*100:.0f}%" for v in machine_sum["oee_mean"]],
        textposition="top center",
        name="OEE",
    ))
    fig_mc.add_hline(y=world_class, line=dict(color="#374151", dash="dash"))
    fig_mc.update_layout(
        barmode="group", title="A·P·Q + OEE by Machine",
        yaxis_range=[0, 115], height=360, **THEME,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    st.plotly_chart(fig_mc, use_container_width=True)

with col_tr:
    trend = report.trend_data(selected_machine)
    fig_tr = go.Figure()
    # Confidence band
    for col, color, label in [
        ("availability", "#3b82f6", "Availability"),
        ("performance",  "#10b981", "Performance"),
        ("quality",      "#f59e0b", "Quality"),
    ]:
        fig_tr.add_trace(go.Scatter(
            x=trend["shift_num"], y=trend[col]*100,
            mode="lines", name=label,
            line=dict(color=color, width=1.5, dash="dot"), opacity=0.6,
        ))
    fig_tr.add_trace(go.Scatter(
        x=trend["shift_num"], y=trend["oee"]*100,
        mode="lines+markers", name="OEE",
        line=dict(color="#374151", width=2),
        marker=dict(size=6, color="#374151"),
    ))
    fig_tr.add_trace(go.Scatter(
        x=trend["shift_num"], y=trend["oee_rolling3"]*100,
        mode="lines", name="OEE (3-shift avg)",
        line=dict(color="#dc2626", width=2.5, dash="dash"),
    ))
    fig_tr.add_hline(y=world_class, line=dict(color="#6b7280", dash="dot"),
                     annotation_text=f"Target {world_class}%")
    fig_tr.update_layout(
        title=f"OEE Trend — {selected_machine}",
        xaxis_title="Shift #", yaxis_title="%",
        yaxis_range=[0, 110], height=360, **THEME,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    st.plotly_chart(fig_tr, use_container_width=True)

st.divider()

# ─── Anomaly detection ────────────────────────────────────────────────────────
st.markdown('<div class="section-header">⚠ ANOMALY DETECTION — LOW-PERFORMANCE SHIFTS</div>',
            unsafe_allow_html=True)

anomalies = report.anomaly_shifts(threshold_std=1.3)
if anomalies.empty:
    st.success("No anomalous shifts detected.")
else:
    st.warning(f"{len(anomalies)} shifts significantly below machine average (>1.3σ)")
    display_cols = ["machine_id", "shift", "oee", "availability",
                    "performance", "quality", "downtime_min", "n_breakdowns"]
    disp = anomalies[display_cols].copy()
    for col in ["oee","availability","performance","quality"]:
        disp[col] = (disp[col] * 100).round(1).astype(str) + "%"
    st.dataframe(disp, use_container_width=True, height=220)

st.divider()
st.markdown(
    "<div style='text-align:center;font-size:.75rem;color:#9ca3af'>"
    "OEE Dashboard · Alaa Eddine TAHIR · Arts et Métiers ParisTech"
    "</div>", unsafe_allow_html=True
)
