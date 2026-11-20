"""Advanced Schedule page - Hybrid MILP-ACO integrated with Fuzzy TOPSIS."""

import io

import numpy as np
import pandas as pd
import streamlit as st

import charts
from data_input import fingerprint, render_data_input
from fuzzy_core import (CRITERIA, CRITERIA_TYPE, DEFAULT_DMS, DEFAULT_POLICIES,
                        DEFAULT_SCENARIOS, LINGUISTIC_SCALE, aggregate_weights,
                        alternatives_summary, decision_matrix, fuzzy_topsis,
                        sensitivity, solve_policy)
from hybrid_core import HybridParams
from state import persist, persist_editor

SHORT = ["C1 Charging cost", "C2 Degradation", "C3 Min SOC", "C4 Reserve", "C5 Load fluct."]
TERMS = list(LINGUISTIC_SCALE)
DEF_DMS = pd.DataFrame([[n] + t for n, t in DEFAULT_DMS.items()],
                       columns=["Decision maker"] + SHORT)
DEF_SCALE = pd.DataFrame([[k, *v] for k, v in LINGUISTIC_SCALE.items()],
                         columns=["Term", "l", "m", "u"])
DEF_SCEN = pd.DataFrame([[n] + t for n, t in DEFAULT_SCENARIOS.items()],
                        columns=["Scenario"] + SHORT)
TERM_COLS = {c: st.column_config.SelectboxColumn(c, options=TERMS, required=True) for c in SHORT}

st.title("🏆 Advanced Schedule · Hybrid MILP–ACO + Fuzzy TOPSIS")
st.caption("Stage 1 Hybrid MILP-ACO alternatives → Stage 2 decision matrix → "
           "Stage 3 Fuzzy TOPSIS ranking → Stage 4 sensitivity analysis")

# ---------------- sidebar settings ----------------
with st.sidebar:
    st.header("⚙️ Hybrid MILP-ACO settings")
    num_ants = persist(st.slider, "Number of ants", "a_ants", 30, 5, 100, step=5)
    num_iterations = persist(st.slider, "Max iterations", "a_iters", 100, 10, 300, step=10)
    c1, c2 = st.columns(2)
    with c1:
        alpha = persist(st.number_input, "α", "a_alpha", 1.0, 0.0, 5.0, step=0.1)
        rho = persist(st.number_input, "ρ", "a_rho", 0.3, 0.01, 0.99, step=0.05)
    with c2:
        beta = persist(st.number_input, "β", "a_beta", 2.0, 0.0, 5.0, step=0.1)
        Q = persist(st.number_input, "Q", "a_Q", 100.0, 1.0, 10000.0, step=10.0)
    patience = persist(st.number_input, "Patience", "a_pat", 20, 1, 200)
    with st.expander("Hybrid parameters (H1/H2)"):
        lp_weight = persist(st.number_input, "LP weight", "a_lpw", 2.0, 0.0, 10.0, step=0.5)
        lns_moves = persist(st.number_input, "Sub-MILPs per LNS call", "a_lnsm", 3, 1, 20)
        lns_frac = persist(st.slider, "Share of buses freed", "a_lnsf", 0.3, 0.1, 1.0, step=0.05)
        sub_tl = persist(st.number_input, "Sub-MILP time limit (s)", "a_subtl", 5.0, 0.5, 60.0,
                         step=0.5)
    st.subheader("Experiment")
    runs_per_alt = persist(st.number_input, "Runs per alternative (best kept)", "a_runs",
                           5, 1, 30)
    base_seed = persist(st.number_input, "Base seed", "a_seed", 100, 0, 10_000)
    solve_exact = persist(st.checkbox, "Validate each alternative with exact MILP",
                          "a_exact", True)

params = HybridParams(num_ants=num_ants, num_iterations=num_iterations, alpha=alpha, beta=beta,
                      rho=rho, Q=Q, patience=int(patience), lp_weight=lp_weight,
                      lns_moves=int(lns_moves), lns_bus_fraction=lns_frac,
                      sub_milp_time_limit=sub_tl)

tabs = st.tabs(["📥 Data & policies", "🧪 Stage 1–2 Alternatives", "⚖️ Stage 3 Fuzzy TOPSIS",
                "🗓️ Selected schedule", "🔁 Stage 4 Sensitivity"])

# ---------------- TAB: DATA & POLICIES ----------------
with tabs[0]:
    with st.expander("Base problem data (shared with Normal Schedule)", expanded=False):
        data, errors = render_data_input("adv", min_energy_label="Technical min (kWh)")
    if errors:
        st.error("Fix the base data errors (open the section above) before running.")
    st.subheader("Charging policies → alternatives")
    st.caption("Each policy = minimum SOC the depot keeps (safety buffer) + extra energy kept "
               "at the end of the day (reserve). The hybrid finds the cheapest schedule for each.")
    pol = persist_editor(
        "policies", DEFAULT_POLICIES, num_rows="dynamic", hide_index=True,
        column_config={
            "Alternative": st.column_config.TextColumn(required=True),
            "Min SOC (kWh)": st.column_config.NumberColumn(min_value=0, step=1, required=True),
            "Reserve (kWh)": st.column_config.NumberColumn(min_value=0, step=1, required=True)})
    pol = pol.dropna()
    dup = pol["Alternative"].astype(str).duplicated().any()
    if dup:
        st.error("Alternative names must be unique.")
    if len(pol) < 2:
        st.warning("Add at least two policies to rank.")
    n_total = len(pol) * int(runs_per_alt)
    st.info(f"{len(pol)} policies × {int(runs_per_alt)} runs = {n_total} hybrid runs "
            f"(roughly {n_total * 0.8:.0f}–{n_total * 3:.0f} s with the thesis data).")
    run = st.button("🚀 Generate & rank alternatives", type="primary",
                    disabled=bool(errors) or dup or len(pol) < 2)

# ---------------- RUN STAGE 1 ----------------
if run:
    alts, skipped = {}, {}
    with st.status("Stage 1: generating alternatives with Hybrid MILP-ACO…",
                   expanded=True) as status:
        bar, info = st.progress(0.0), st.empty()
        rows = list(pol.itertuples(index=False))
        for k, (name, min_soc, reserve) in enumerate(rows):
            def cb(r, nr, it, tot, best, k=k, name=name):
                bar.progress(min(1.0, (k + (r + it / tot) / nr) / len(rows)))
                b = f"RM {best:.2f}" if np.isfinite(best) else "–"
                info.write(f"{name}: run {r+1}/{nr}, iteration {it}, best {b}")
            a = solve_policy(data, str(name), min_soc, reserve, params, int(runs_per_alt),
                             int(base_seed), solve_exact, cb)
            if a["status"] == "ok":
                alts[a["name"]] = a
                st.write(f"✅ {name}: min SOC {min_soc:g}, reserve {reserve:g} → "
                         f"RM {a['objective']:.2f}"
                         + (f" (MILP RM {a['milp_opt']:.2f})" if solve_exact else ""))
            else:
                skipped[a["name"]] = a["reason"]
                st.write(f"⚠️ {name}: skipped – {a['reason']}")
        bar.progress(1.0)
        status.update(label=f"Stage 1 done: {len(alts)} alternatives", state="complete",
                      expanded=False)
    st.session_state.adv_results = dict(alts=alts, skipped=skipped,
                                        base_target=data.target_energy.copy(),
                                        fp=fingerprint(data))
    st.toast("Alternatives ready. See the Stage tabs.", icon="✅")

R = st.session_state.get("adv_results")
ready = R is not None and len(R["alts"]) >= 2
if R is not None and R["fp"] != fingerprint(data):
    st.warning("The input data has changed since the last run. Press **Generate & rank** "
               "again to update.")


def need_results():
    st.info("Press **Generate & rank alternatives** in the first tab "
            "(at least two feasible policies are needed).")


def read_scale(df):
    scale, bad = {}, []
    for _, r in df.iterrows():
        l, m, u = float(r["l"]), float(r["m"]), float(r["u"])
        if not (0 <= l <= m <= u <= 1):
            bad.append(r["Term"])
        scale[r["Term"]] = (l, m, u)
    return scale, bad


def table_to_opinions(df, name_col):
    return {str(r[name_col]): [r[c] for c in SHORT] for _, r in df.dropna().iterrows()}


if ready:
    alts = R["alts"]
    dm_matrix = decision_matrix(alts, R["base_target"])

# ---------------- TAB: ALTERNATIVES ----------------
with tabs[1]:
    if not ready:
        need_results()
    else:
        if R["skipped"]:
            st.warning("Skipped (infeasible) policies: " +
                       ", ".join(f"**{k}** ({v})" for k, v in R["skipped"].items()))
        st.subheader("Alternatives (Hybrid vs exact MILP)")
        st.dataframe(alternatives_summary(alts).round(4))
        st.subheader("Stage 2: decision matrix")
        st.caption("C1, C2, C5 are cost criteria (lower is better); "
                   "C3, C4 are benefit criteria (higher is better).")
        st.dataframe(dm_matrix.round(4))

# ---------------- TAB: FUZZY TOPSIS ----------------
with tabs[2]:
    st.subheader("Decision makers' opinions on criteria importance")
    st.caption("Choose a linguistic term for each criterion. Add or remove rows to change the "
               "group. The ranking updates instantly without re-running Stage 1.")
    dms_df = persist_editor("dms", DEF_DMS, num_rows="dynamic", hide_index=True,
                            column_config=TERM_COLS)
    with st.expander("Linguistic scale (triangular fuzzy numbers)"):
        scale_df = persist_editor("scale", DEF_SCALE, hide_index=True, disabled=["Term"])
    scale, bad_terms = read_scale(scale_df)
    opinions = table_to_opinions(dms_df, "Decision maker")
    if bad_terms:
        st.error(f"Each term needs 0 ≤ l ≤ m ≤ u ≤ 1. Check: {', '.join(bad_terms)}")
    elif not opinions:
        st.error("Add at least one decision maker.")
    else:
        fw = aggregate_weights(opinions, scale)
        w_df = pd.DataFrame(fw, index=CRITERIA, columns=["l", "m", "u"])
        w_df["Defuzzified (l+m+u)/3"] = fw.mean(axis=1)
        c1, c2 = st.columns(2)
        c1.markdown("**Aggregated fuzzy weights**")
        c1.dataframe(w_df.round(4))
        c2.plotly_chart(charts.fuzzy_weights_chart(w_df))
        if not ready:
            need_results()
        else:
            ranking, norm, _ = fuzzy_topsis(dm_matrix, CRITERIA_TYPE, fw)
            best_name = ranking.index[0]
            st.session_state.adv_best = best_name
            b = alts[best_name]
            st.success(f"🏆 Selected charging schedule: **{best_name}** "
                       f"(min SOC {b['min_soc']:g} kWh, reserve {b['reserve']:g} kWh, "
                       f"cost RM {b['objective']:.2f}, CC {ranking['CC'].iloc[0]:.4f})")
            c1, c2 = st.columns(2)
            c1.markdown("**Fuzzy TOPSIS ranking**")
            c1.dataframe(ranking.round(4))
            c2.plotly_chart(charts.cc_bar_chart(ranking))
            c1, c2 = st.columns(2)
            c1.markdown("**Normalised decision matrix**")
            c1.dataframe(norm.round(4))
            c2.plotly_chart(charts.tradeoff_scatter(dm_matrix, best_name))

# ---------------- TAB: SELECTED SCHEDULE ----------------
with tabs[3]:
    if not ready:
        need_results()
    else:
        names = list(alts)
        best_default = st.session_state.get("adv_best", names[0])
        pick = st.selectbox("Alternative to display (default = Fuzzy TOPSIS winner)", names,
                            index=names.index(best_default) if best_default in names else 0)
        a = alts[pick]
        sched, best, d = a["scheduler"], a["best"], a["data"]
        k = st.columns(5)
        k[0].metric("Total cost", f"RM {best['objective']:.2f}")
        k[1].metric("Charging cost", f"RM {best['charging_cost']:.2f}")
        k[2].metric("Degradation cost", f"RM {best['degradation_cost']:.2f}")
        k[3].metric("Policy min SOC", f"{a['min_soc']:g} kWh")
        k[4].metric("End-of-day reserve", f"{a['reserve']:g} kWh")
        st.plotly_chart(charts.schedule_heatmap(best["schedule"], d.bus_availability,
                                                d.bus_names, d.slot_names, d.electricity_price))
        c1, c2 = st.columns(2)
        c1.plotly_chart(charts.energy_profile_chart(best["energy_profile"], d.bus_names,
                                                    d.slot_names, a["min_soc"],
                                                    d.battery_capacity))
        c2.plotly_chart(charts.charger_utilisation_chart(best["schedule"], d.slot_names,
                                                         d.electricity_price, d.num_chargers))
        c1, c2 = st.columns([2, 1])
        bus_df = pd.DataFrame({
            "Bus": d.bus_names, "Initial (kWh)": d.initial_energy,
            "Final target (kWh)": d.target_energy, "Final (kWh)": best["final_energy"],
            "Min SOC (kWh)": best["energy_profile"][:, 1:].min(axis=1),
            "Slots used": best["schedule"].sum(axis=1),
            "Charging slots": [", ".join(np.array(d.slot_names)[row == 1])
                               for row in best["schedule"]]})
        c1.markdown("**Per-bus summary**")
        c1.dataframe(bus_df, hide_index=True)
        c2.markdown("**Feasibility check (policy constraints)**")
        for name, ok in sched.feasibility_checks(best["schedule"],
                                                 best["energy_profile"]).items():
            c2.write(("✅ " if ok else "❌ ") + name)
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as xw:
            pd.DataFrame(best["schedule"], index=d.bus_names, columns=d.slot_names).to_excel(
                xw, sheet_name="Schedule")
            pd.DataFrame(best["energy_profile"], index=d.bus_names,
                         columns=["Initial"] + d.slot_names).round(2).to_excel(
                xw, sheet_name="Energy profile")
            bus_df.to_excel(xw, sheet_name="Bus summary", index=False)
        st.download_button(f"⬇️ Download schedule {pick} (Excel)", buf.getvalue(),
                           f"advanced_schedule_{pick}.xlsx")

# ---------------- TAB: SENSITIVITY ----------------
with tabs[4]:
    st.subheader("Weight scenarios")
    st.caption("The group decision from Stage 3 is always included as the first scenario. "
               "Add, remove or edit the other scenarios below.")
    sc_df = persist_editor("scenarios", DEF_SCEN, num_rows="dynamic", hide_index=True,
                           column_config=TERM_COLS)
    if not ready:
        need_results()
    elif bad_terms or not opinions:
        st.error("Fix the decision makers / linguistic scale in the Stage 3 tab first.")
    else:
        scenarios = {"Group decision (DMs)": opinions,
                     **{n: {"DM": t} for n, t in table_to_opinions(sc_df, "Scenario").items()}}
        cc_t, rank_t = sensitivity(dm_matrix, CRITERIA_TYPE, scenarios, scale)
        winners = rank_t.idxmin()
        group_best = winners.iloc[0]
        k = st.columns(3)
        k[0].metric("Group decision winner", group_best)
        k[1].metric("Scenarios agreeing with it",
                    f"{(winners == group_best).sum()} of {len(winners)}")
        k[2].metric("Most frequent winner", winners.value_counts().idxmax())
        c1, c2 = st.columns(2)
        c1.plotly_chart(charts.rank_heatmap(rank_t))
        with c2:
            st.markdown("**Best alternative per scenario**")
            st.dataframe(pd.DataFrame({"Best alternative": winners,
                                       "CC": [cc_t.loc[w, s] for s, w in winners.items()]})
                         .round(4))
        st.plotly_chart(charts.sensitivity_bar_chart(cc_t))

        ranking, norm, _ = fuzzy_topsis(dm_matrix, CRITERIA_TYPE,
                                        aggregate_weights(opinions, scale))
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as xw:
            alternatives_summary(alts).to_excel(xw, sheet_name="Alternatives")
            dm_matrix.to_excel(xw, sheet_name="Decision matrix")
            dms_df.to_excel(xw, sheet_name="Decision makers", index=False)
            norm.to_excel(xw, sheet_name="Normalised")
            ranking.to_excel(xw, sheet_name="Fuzzy TOPSIS")
            rank_t.to_excel(xw, sheet_name="Sensitivity ranks")
            cc_t.to_excel(xw, sheet_name="Sensitivity CC")
        st.download_button("⬇️ Download full report (Excel)", buf.getvalue(),
                           "advanced_fuzzy_report.xlsx")
