"""
fuzzy_core.py
=============
Integrated Hybrid MILP-ACO + Fuzzy MCDM framework (no Streamlit code).

STAGE 1  Generate alternatives: one charging policy (min SOC, end-of-day reserve)
         -> one Hybrid MILP-ACO schedule (engine in hybrid_core.py).
STAGE 2  Decision matrix on five criteria (C1..C5).
STAGE 3  Simple Fuzzy TOPSIS (crisp performance, fuzzy linguistic weights).
STAGE 4  Sensitivity analysis with different weight scenarios.
"""

from __future__ import annotations

import time
from dataclasses import replace

import numpy as np
import pandas as pd

from hybrid_core import HybridParams, HybridScheduler, ProblemData

# =============================================================
# DEFAULT SETTINGS (same as the thesis script)
# =============================================================

DEFAULT_POLICIES = pd.DataFrame(
    [("A1", 20, 0), ("A2", 22, 0), ("A3", 26, 0), ("A4", 29, 0),
     ("A5", 20, 5), ("A6", 26, 5), ("A7", 29, 5), ("A8", 29, 10)],
    columns=["Alternative", "Min SOC (kWh)", "Reserve (kWh)"])

CRITERIA = ["C1 Charging Cost (RM)", "C2 Degradation Cost (RM)",
            "C3 Minimum SOC (kWh)", "C4 End-of-day Reserve (kWh)",
            "C5 Charger Load Fluctuation"]
CRITERIA_TYPE = ["cost", "cost", "benefit", "benefit", "cost"]

LINGUISTIC_SCALE = {
    "VL": (0.00, 0.00, 0.25),   # Very Low importance
    "L":  (0.00, 0.25, 0.50),   # Low
    "M":  (0.25, 0.50, 0.75),   # Medium
    "H":  (0.50, 0.75, 1.00),   # High
    "VH": (0.75, 1.00, 1.00),   # Very High
}

DEFAULT_DMS = {
    "DM1 Depot Operator":       ["H", "M", "VH", "H", "M"],
    "DM2 Finance Manager":      ["VH", "H", "M", "L", "L"],
    "DM3 Maintenance Engineer": ["M", "VH", "H", "M", "H"],
}

DEFAULT_SCENARIOS = {
    "Cost-focused":   ["VH", "VH", "L", "L", "L"],
    "Safety-focused": ["L", "M", "VH", "VH", "M"],
    "Grid-focused":   ["M", "L", "M", "L", "VH"],
    "Equal weights":  ["M", "M", "M", "M", "M"],
}


# =============================================================
# STAGE 1 - ALTERNATIVES FROM HYBRID MILP-ACO
# =============================================================

def policy_data(base: ProblemData, min_soc: float, reserve: float) -> ProblemData:
    """Problem data for one policy: raise the min SOC and the final target."""
    return replace(base, min_energy=float(min_soc),
                   target_energy=base.target_energy + float(reserve),
                   bus_names=list(base.bus_names), slot_names=list(base.slot_names))


def solve_policy(base: ProblemData, name: str, min_soc: float, reserve: float,
                 params: HybridParams, n_runs: int = 5, base_seed: int = 100,
                 solve_exact: bool = True, progress_callback=None) -> dict:
    """Run the hybrid n_runs times for one policy and keep the best schedule.
    Returns a dict with status 'ok' or 'infeasible' (+ reason)."""
    data = policy_data(base, min_soc, reserve)
    out = dict(name=name, min_soc=float(min_soc), reserve=float(reserve), data=data)
    errors = data.validate()
    if errors:
        return {**out, "status": "infeasible", "reason": "; ".join(errors)}
    sched = HybridScheduler(data, params)
    sched.solve_lp_bound()
    if sched.X_LP is None:
        return {**out, "status": "infeasible",
                "reason": "LP relaxation infeasible (policy cannot be met)."}
    runs = []
    for r in range(n_runs):
        cb = None
        if progress_callback:
            cb = lambda it, tot, b, g, r=r: progress_callback(r, n_runs, it, tot, b)
        runs.append(sched.run(base_seed + r, progress_callback=cb))
    ok = [r for r in runs if r["schedule"] is not None]
    if not ok:
        return {**out, "status": "infeasible",
                "reason": "Hybrid found no feasible schedule in the given iterations."}
    best = min(ok, key=lambda r: r["objective"])
    milp_opt, milp_time = np.nan, np.nan
    if solve_exact:
        t0 = time.perf_counter()
        _, milp_opt, _ = sched.solve_milp()
        milp_time = time.perf_counter() - t0
    return {**out, "status": "ok", "scheduler": sched, "best": best, "runs": runs,
            "objective": best["objective"],
            "mean_objective": float(np.mean([r["objective"] for r in ok])),
            "time": float(np.mean([r["computation_time"] for r in ok])),
            "lp_bound": sched.LP_BOUND, "milp_opt": milp_opt, "milp_time": milp_time}


def alternatives_summary(alts: dict) -> pd.DataFrame:
    rows = []
    for n, a in alts.items():
        rows.append({"Alternative": n, "Min SOC Policy": a["min_soc"],
                     "Reserve Policy": a["reserve"], "Hybrid Cost RM": a["objective"],
                     "Mean Cost RM": a["mean_objective"], "MILP Cost RM": a["milp_opt"],
                     "Gap %": (a["objective"] - a["milp_opt"]) / a["milp_opt"] * 100,
                     "LP Bound RM": a["lp_bound"], "Time s/run": a["time"]})
    return pd.DataFrame(rows).set_index("Alternative")


# =============================================================
# STAGE 2 - DECISION MATRIX
# =============================================================

def decision_matrix(alts: dict, base_target: np.ndarray) -> pd.DataFrame:
    rows = {}
    for n, a in alts.items():
        b, s = a["best"], a["best"]["schedule"]
        profile = b["energy_profile"]
        rows[n] = [b["charging_cost"], b["degradation_cost"],
                   profile[:, 1:].min(),
                   (profile[:, -1] - base_target).mean(),
                   s.sum(axis=0).std()]
    return pd.DataFrame.from_dict(rows, orient="index", columns=CRITERIA)


# =============================================================
# STAGE 3 - SIMPLE FUZZY TOPSIS
# =============================================================

def aggregate_weights(opinions: dict, scale: dict) -> np.ndarray:
    """Average the decision makers' triangular fuzzy weights -> (criteria, 3)."""
    tfns = np.array([[scale[term] for term in terms] for terms in opinions.values()],
                    dtype=float)
    return tfns.mean(axis=0)


def fuzzy_topsis(matrix: pd.DataFrame, types: list, fuzzy_w: np.ndarray):
    """
    1. Min-max normalisation: benefit (x-min)/(max-min), cost (max-x)/(max-min)
    2. Weighted fuzzy value v = r * (l, m, u)
    3. FPIS = best v per criterion, FNIS = worst v per criterion
    4. Vertex distance d(a,b) = sqrt(((al-bl)^2 + (am-bm)^2 + (au-bu)^2) / 3)
    5. Closeness coefficient CC = d- / (d+ + d-)   (highest CC = best)
    Returns (ranking DataFrame, normalised matrix DataFrame, weighted fuzzy array).
    """
    X = matrix.to_numpy(dtype=float)
    R = np.zeros_like(X)
    for j, kind in enumerate(types):
        col = X[:, j]
        spread = col.max() - col.min()
        if np.isclose(spread, 0):
            R[:, j] = 1.0
        elif kind == "benefit":
            R[:, j] = (col - col.min()) / spread
        else:
            R[:, j] = (col.max() - col) / spread
    V = R[:, :, None] * fuzzy_w[None, :, :]
    fpis, fnis = V.max(axis=0), V.min(axis=0)
    dist = lambda a, b: np.sqrt(((a - b) ** 2).mean(axis=-1))
    d_plus = dist(V, fpis[None]).sum(axis=1)
    d_minus = dist(V, fnis[None]).sum(axis=1)
    denom = d_plus + d_minus
    cc = np.divide(d_minus, denom, out=np.full_like(d_minus, 0.5), where=denom > 0)
    res = pd.DataFrame({"D+": d_plus, "D-": d_minus, "CC": cc}, index=matrix.index)
    res["Rank"] = res["CC"].rank(ascending=False, method="min").astype(int)
    norm = pd.DataFrame(R, index=matrix.index, columns=matrix.columns)
    return res.sort_values("Rank"), norm, V


# =============================================================
# STAGE 4 - SENSITIVITY ANALYSIS
# =============================================================

def sensitivity(matrix: pd.DataFrame, types: list, scenarios: dict, scale: dict):
    """scenarios: {name: {dm_name: [terms]}} -> (CC table, rank table)."""
    cc, rank = pd.DataFrame(index=matrix.index), pd.DataFrame(index=matrix.index)
    for sc, opinions in scenarios.items():
        r, _, _ = fuzzy_topsis(matrix, types, aggregate_weights(opinions, scale))
        cc[sc], rank[sc] = r["CC"], r["Rank"]
    return cc, rank
