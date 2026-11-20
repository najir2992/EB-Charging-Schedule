"""Normal Schedule page - Hybrid MILP-ACO (minimum-cost schedule)."""

import io

import numpy as np
import pandas as pd
import streamlit as st

import charts
from data_input import fingerprint, render_data_input
from hybrid_core import HybridParams, HybridScheduler
from state import persist

st.title("🗓️ Normal Schedule · Hybrid MILP–ACO")
st.caption("LP-guided pheromone (H1) · MILP fix-and-optimise LNS (H2) · "
           "LP lower-bound certificate (H3)")

# ---------------- sidebar settings ----------------
with st.sidebar:
    st.header("⚙️ Algorithm settings")
    method = persist(st.radio, "Method", "n_method", "Hybrid MILP-ACO",
                     ["Hybrid MILP-ACO", "Plain ACO", "Custom (ablation)"],
                     help="Plain ACO switches off both hybrid components (H1 and H2).")
    if method == "Custom (ablation)":
        use_lp = persist(st.checkbox, "H1: LP-guided pheromone", "n_h1", True)
        use_lns = persist(st.checkbox, "H2: MILP fix-and-optimise LNS", "n_h2", True)
    else:
        use_lp = use_lns = method == "Hybrid MILP-ACO"
    st.subheader("ACO")
    num_ants = persist(st.slider, "Number of ants", "n_ants", 30, 5, 100, step=5)
    num_iterations = persist(st.slider, "Max iterations", "n_iters", 100, 10, 300, step=10)
    c1, c2 = st.columns(2)
    with c1:
        alpha = persist(st.number_input, "α (pheromone)", "n_alpha", 1.0, 0.0, 5.0, step=0.1)
        rho = persist(st.number_input, "ρ (evaporation)", "n_rho", 0.3, 0.01, 0.99, step=0.05)
    with c2:
        beta = persist(st.number_input, "β (heuristic)", "n_beta", 2.0, 0.0, 5.0, step=0.1)
        Q = persist(st.number_input, "Q", "n_Q", 100.0, 1.0, 10000.0, step=10.0)
    patience = persist(st.number_input, "Patience", "n_pat", 20, 1, 200)
    with st.expander("Hybrid parameters"):
        lp_weight = persist(st.number_input, "LP weight (H1)", "n_lpw", 2.0, 0.0, 10.0, step=0.5)
        lns_moves = persist(st.number_input, "Sub-MILPs per LNS call", "n_lnsm", 3, 1, 20)
        lns_frac = persist(st.slider, "Share of buses freed", "n_lnsf", 0.3, 0.1, 1.0, step=0.05)
        sub_tl = persist(st.number_input, "Sub-MILP time limit (s)", "n_subtl", 5.0, 0.5, 60.0,
                         step=0.5)
    st.subheader("Experiment")
    num_runs = persist(st.number_input, "Independent runs", "n_runs", 5, 1, 50,
                       help="The thesis used 30 runs; fewer runs is quicker for a demo.")
    base_seed = persist(st.number_input, "Base seed", "n_seed", 100, 0, 10_000)
    compare_milp = persist(st.checkbox, "Also solve the full MILP (exact optimum)",
                           "n_milp", True)

params = HybridParams(num_ants=num_ants, num_iterations=num_iterations, alpha=alpha,
                      beta=beta, rho=rho, Q=Q, patience=int(patience), use_lp_init=use_lp,
                      use_milp_lns=use_lns, lp_weight=lp_weight, lns_moves=int(lns_moves),
                      lns_bus_fraction=lns_frac, sub_milp_time_limit=sub_tl)

tab_input, tab_schedule, tab_stats = st.tabs(
    ["📥 Data input", "🗓️ Charging schedule", "📊 Run statistics"])

# ---------------- TAB: DATA INPUT ----------------
with tab_input:
    data, errors = render_data_input("normal")
    if not errors:
        st.success("Input data is consistent. Go ahead and run the scheduler.")
    run_clicked = st.button(f"🚀 Run {params.mode}", type="primary", disabled=bool(errors))

# ---------------- RUN ----------------
if run_clicked:
    sched = HybridScheduler(data, params)
    with st.status("Solving…", expanded=True) as status:
        st.write("Solving LP relaxation (lower bound)…")
        sched.solve_lp_bound()
        milp_res = None
        if compare_milp:
            st.write("Solving full MILP for reference…")
            milp_res = sched.solve_full_milp()
        bar, info = st.progress(0.0), st.empty()
        results, n = [], int(num_runs)
        for r in range(n):
            def cb(it, total, best_obj, gap, r=r):
                bar.progress(min(1.0, (r + it / total) / n))
                txt = (f"RM {best_obj:.2f}, gap {gap*100:.3f}%" if np.isfinite(best_obj)
                       else "no feasible yet")
                info.write(f"Run {r+1}/{n} · iteration {it} · best {txt}")
            results.append(sched.run(int(base_seed) + r, progress_callback=cb))
        bar.progress(1.0)
        status.update(label="Done", state="complete", expanded=False)
    st.session_state.normal_results = dict(results=results, scheduler=sched, milp=milp_res,
                                           mode=params.mode, fp=fingerprint(data))
    st.toast("Schedule ready. Open the 'Charging schedule' tab.", icon="✅")

R = st.session_state.get("normal_results")
if R is not None and R["fp"] != fingerprint(data):
    st.warning("The input data has changed since the last run. Press **Run** again to update.")

# ---------------- TAB: SCHEDULE ----------------
with tab_schedule:
    if R is None:
        st.info("Check the data and press **Run** in the Data input tab.")
    else:
        sched, results = R["scheduler"], R["results"]
        d = sched.d
        objs = np.array([r["objective"] for r in results], float)
        if not np.isfinite(objs).any():
            st.error("No feasible schedule was found. Try more iterations or check the data.")
        else:
            bi = int(np.nanargmin(objs))
            best = results[bi]
            milp_opt = R["milp"][1] if R["milp"] else None
            k = st.columns(5)
            k[0].metric(f"Best cost ({R['mode']})", f"RM {best['objective']:.2f}")
            if milp_opt is not None and np.isfinite(milp_opt):
                k[1].metric("MILP optimum", f"RM {milp_opt:.2f}",
                            f"gap {(best['objective'] - milp_opt) / milp_opt * 100:.3f}%",
                            delta_color="inverse")
            k[2].metric("LP lower bound", f"RM {sched.LP_BOUND:.2f}",
                        f"gap {best['lb_gap']:.3f}%", delta_color="off")
            k[3].metric("Iterations used", best["iterations_used"])
            k[4].metric("Time", f"{best['computation_time']:.2f} s")

            st.plotly_chart(charts.schedule_heatmap(best["schedule"], d.bus_availability,
                                                    d.bus_names, d.slot_names,
                                                    d.electricity_price))
            c1, c2 = st.columns(2)
            c1.plotly_chart(charts.charger_utilisation_chart(best["schedule"], d.slot_names,
                                                             d.electricity_price, d.num_chargers))
            c2.plotly_chart(charts.convergence_chart(results, bi, milp_opt, sched.LP_BOUND))
            st.plotly_chart(charts.energy_profile_chart(best["energy_profile"], d.bus_names,
                                                        d.slot_names, d.min_energy,
                                                        d.battery_capacity))
            c1, c2 = st.columns([2, 1])
            bus_df = pd.DataFrame({
                "Bus": d.bus_names, "Initial (kWh)": d.initial_energy,
                "Target (kWh)": d.target_energy, "Final (kWh)": best["final_energy"],
                "Required slots": sched.required_slots,
                "Slots used": best["schedule"].sum(axis=1),
                "Charging slots": [", ".join(np.array(d.slot_names)[row == 1])
                                   for row in best["schedule"]]})
            with c1:
                st.subheader("Per-bus summary")
                st.dataframe(bus_df, hide_index=True)
            with c2:
                st.subheader("Cost summary")
                st.dataframe(pd.DataFrame({
                    "Component": ["Charging cost", "Battery degradation", "Total"],
                    "RM": [best["charging_cost"], best["degradation_cost"], best["objective"]]
                }).round(2), hide_index=True)
                st.subheader("Feasibility check")
                for name, ok in sched.feasibility_checks(best["schedule"],
                                                         best["energy_profile"]).items():
                    st.write(("✅ " if ok else "❌ ") + name)
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as xw:
                pd.DataFrame(best["schedule"], index=d.bus_names, columns=d.slot_names).to_excel(
                    xw, sheet_name="Schedule")
                pd.DataFrame(best["energy_profile"], index=d.bus_names,
                             columns=["Initial"] + d.slot_names).round(2).to_excel(
                    xw, sheet_name="Energy profile")
                bus_df.to_excel(xw, sheet_name="Bus summary", index=False)
            st.download_button("⬇️ Download schedule (Excel)", buf.getvalue(),
                               "normal_schedule.xlsx")

# ---------------- TAB: STATISTICS ----------------
with tab_stats:
    if R is None:
        st.info("No results yet.")
    else:
        results = R["results"]
        milp_opt = R["milp"][1] if R["milp"] else None
        df = pd.DataFrame([{
            "Run": n, "Seed": r["seed"], "Charging Cost RM": r["charging_cost"],
            "Degradation Cost RM": r["degradation_cost"], "Objective Cost RM": r["objective"],
            "Gap to LP bound %": r["lb_gap"], "Iterations": r["iterations_used"],
            "Sub-MILPs": r["sub_milps"], "Computation Time s": r["computation_time"],
        } for n, r in enumerate(results, start=1)])
        valid = df.replace([np.inf, -np.inf], np.nan).dropna(subset=["Objective Cost RM"])
        if valid.empty:
            st.error("No feasible runs.")
        else:
            obj = valid["Objective Cost RM"]
            k = st.columns(5)
            k[0].metric("Best", f"RM {obj.min():.2f}")
            k[1].metric("Mean", f"RM {obj.mean():.2f}")
            k[2].metric("Worst", f"RM {obj.max():.2f}")
            k[3].metric("Std. dev.", f"{obj.std():.4f}" if len(obj) > 1 else "–")
            if milp_opt is not None:
                k[4].metric("Runs reaching optimum",
                            f"{np.isclose(obj, milp_opt).mean() * 100:.0f}%")
            c1, c2 = st.columns([2, 1])
            c1.dataframe(df.round(4), hide_index=True)
            c2.plotly_chart(charts.runs_boxplot(valid, milp_opt))
            if R["milp"]:
                st.caption(f"Full MILP solved in {R['milp'][3]:.3f} s · "
                           f"mean hybrid time {valid['Computation Time s'].mean():.3f} s")
            st.download_button("⬇️ Download run statistics (CSV)", df.to_csv(index=False),
                               "normal_runs.csv")
