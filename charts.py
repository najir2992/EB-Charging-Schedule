"""
charts.py - Plotly figures for the Streamlit interface.
Each function takes plain numpy/pandas data and returns a plotly Figure,
so the charts can be reused in a notebook or exported for the thesis.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

CHARGE = "#2a9d8f"      # charging
IDLE = "#e9f5f3"        # available, not charging
BUSY = "#d9d9d9"        # on route / unavailable


def schedule_heatmap(schedule, availability, bus_names, slot_names, prices):
    """Grid of buses x slots: charging / available-idle / on route."""
    z = np.where(schedule == 1, 2, np.where(availability == 1, 1, 0))
    labels = np.where(z == 2, "Charging", np.where(z == 1, "Available", "On route"))
    x = [f"{s}<br>RM{p:.2f}" for s, p in zip(slot_names, prices)]
    fig = go.Figure(go.Heatmap(
        z=z, x=x, y=bus_names, text=np.where(z == 2, "⚡", ""),
        texttemplate="%{text}", customdata=labels,
        hovertemplate="%{y} · %{x}<br>%{customdata}<extra></extra>",
        colorscale=[[0, BUSY], [0.33, BUSY], [0.34, IDLE], [0.66, IDLE],
                    [0.67, CHARGE], [1, CHARGE]],
        zmin=0, zmax=2, showscale=False, xgap=2, ygap=2))
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(height=max(320, 28 * len(bus_names) + 80),
                      margin=dict(l=10, r=10, t=30, b=10),
                      title="Charging schedule (⚡ = charging, grey = on route)")
    return fig


def energy_profile_chart(energy_profile, bus_names, slot_names, min_energy, capacity):
    fig = go.Figure()
    x = ["Initial"] + list(slot_names)
    for i, name in enumerate(bus_names):
        fig.add_trace(go.Scatter(x=x, y=energy_profile[i], mode="lines+markers", name=name))
    fig.add_hline(y=min_energy, line_dash="dash", line_color="red",
                  annotation_text=f"Min {min_energy:g} kWh")
    fig.add_hline(y=capacity, line_dash="dash", line_color="gray",
                  annotation_text=f"Capacity {capacity:g} kWh")
    fig.update_layout(title="Battery energy level over time", yaxis_title="kWh",
                      height=460, margin=dict(l=10, r=10, t=40, b=10))
    return fig


def charger_utilisation_chart(schedule, slot_names, prices, num_chargers):
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=slot_names, y=schedule.sum(axis=0), name="Chargers used",
                         marker_color=CHARGE), secondary_y=False)
    fig.add_trace(go.Scatter(x=slot_names, y=prices, name="Price (RM/kWh)",
                             mode="lines+markers", line=dict(color="#e76f51")),
                  secondary_y=True)
    fig.add_hline(y=num_chargers, line_dash="dash", annotation_text=f"Max {num_chargers}")
    fig.update_yaxes(title_text="Chargers used", secondary_y=False)
    fig.update_yaxes(title_text="RM/kWh", secondary_y=True)
    fig.update_layout(title="Charger utilisation vs electricity price", height=400,
                      margin=dict(l=10, r=10, t=40, b=10))
    return fig


def convergence_chart(results, best_index, milp_opt=None, lp_bound=None):
    fig = go.Figure()
    for k, r in enumerate(results):
        h = r["history"]
        fig.add_trace(go.Scatter(
            x=list(range(1, len(h) + 1)), y=h, mode="lines",
            line=dict(color=CHARGE, width=3 if k == best_index else 1),
            opacity=1 if k == best_index else 0.3,
            name=f"Run {k+1}" + (" (best)" if k == best_index else ""),
            showlegend=k == best_index))
    if milp_opt is not None and np.isfinite(milp_opt):
        fig.add_hline(y=milp_opt, line_dash="dash", annotation_text=f"MILP optimum {milp_opt:.2f}")
    if lp_bound is not None:
        fig.add_hline(y=lp_bound, line_dash="dot", line_color="gray",
                      annotation_text=f"LP bound {lp_bound:.2f}",
                      annotation_position="bottom right")
    fig.update_layout(title="Convergence", xaxis_title="Iteration",
                      yaxis_title="Best feasible cost (RM)", height=400,
                      margin=dict(l=10, r=10, t=40, b=10))
    return fig


def runs_boxplot(results_df, milp_opt=None):
    fig = go.Figure(go.Box(y=results_df["Objective Cost RM"], boxpoints="all",
                           name="Hybrid runs", marker_color=CHARGE))
    if milp_opt is not None and np.isfinite(milp_opt):
        fig.add_hline(y=milp_opt, line_dash="dash", annotation_text="MILP optimum")
    fig.update_layout(title="Objective cost across runs", yaxis_title="RM",
                      height=380, margin=dict(l=10, r=10, t=40, b=10))
    return fig


# =============================================================
# FUZZY MCDM CHARTS
# =============================================================

BEST = "#2a9d8f"
OTHER = "#8ab6d6"


def cc_bar_chart(ranking):
    colors = [BEST if r == 1 else OTHER for r in ranking["Rank"]]
    fig = go.Figure(go.Bar(x=ranking.index, y=ranking["CC"], marker_color=colors,
                           text=ranking["CC"].round(4), textposition="outside"))
    fig.update_layout(title="Fuzzy TOPSIS ranking (closeness coefficient)",
                      xaxis_title="Alternative (charging schedule)", yaxis_title="CC",
                      yaxis_range=[0, max(1.0, ranking["CC"].max() * 1.15)],
                      height=400, margin=dict(l=10, r=10, t=40, b=10))
    return fig


def tradeoff_scatter(matrix, best_name):
    total = matrix.iloc[:, 0] + matrix.iloc[:, 1]
    fig = go.Figure(go.Scatter(
        x=total, y=matrix.iloc[:, 2], mode="markers+text", text=matrix.index,
        textposition="top center",
        marker=dict(size=[18 if n == best_name else 11 for n in matrix.index],
                    color=[BEST if n == best_name else OTHER for n in matrix.index]),
        hovertemplate="%{text}<br>Total cost RM %{x:.2f}<br>Min SOC %{y:.1f} kWh<extra></extra>"))
    fig.update_layout(title="Cost vs safety trade-off", xaxis_title="Total cost (RM)",
                      yaxis_title="Minimum SOC observed (kWh)", height=400,
                      margin=dict(l=10, r=10, t=40, b=10))
    return fig


def fuzzy_weights_chart(weights_df):
    """Draw each criterion's aggregated triangular fuzzy weight (l, m, u)."""
    fig = go.Figure()
    for name, row in weights_df.iterrows():
        fig.add_trace(go.Scatter(x=[row["l"], row["m"], row["u"]], y=[0, 1, 0],
                                 mode="lines+markers", name=name, fill="toself", opacity=0.55))
    fig.update_layout(title="Aggregated triangular fuzzy weights", xaxis_title="Importance",
                      yaxis_title="Membership μ", xaxis_range=[0, 1], height=380,
                      margin=dict(l=10, r=10, t=40, b=10))
    return fig


def sensitivity_bar_chart(cc_table):
    fig = go.Figure()
    for sc in cc_table.columns:
        fig.add_trace(go.Bar(x=cc_table.index, y=cc_table[sc], name=sc))
    fig.update_layout(barmode="group", title="Closeness coefficient per weight scenario",
                      yaxis_title="CC", height=420, margin=dict(l=10, r=10, t=40, b=10))
    return fig


def rank_heatmap(rank_table):
    fig = go.Figure(go.Heatmap(
        z=rank_table.to_numpy(), x=rank_table.columns, y=rank_table.index,
        text=rank_table.to_numpy(), texttemplate="%{text}", colorscale="Teal_r",
        showscale=False, xgap=2, ygap=2,
        hovertemplate="%{y} · %{x}<br>Rank %{z}<extra></extra>"))
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(title="Rank of each alternative per scenario (1 = best)",
                      height=max(300, 34 * len(rank_table) + 90),
                      margin=dict(l=10, r=10, t=40, b=10))
    return fig
