"""Home page - introduction to the system."""

import streamlit as st

from data_input import current_data

user = st.session_state.user
st.title("⚡ Electric Bus Charging Scheduling System")
st.markdown(f"Welcome, **{user['name']}**.")

st.markdown("""
This system plans **when each electric bus should charge at the depot**. Every bus keeps
enough battery to run its trips, the chargers are never over-booked, and the total cost of
electricity plus battery degradation is kept as low as possible.

It uses a **hybrid MILP–ACO matheuristic**: Ant Colony Optimisation explores many schedules
quickly, and an exact Mixed-Integer Linear Programming model (HiGHS solver) guides and
improves them. The *Advanced* module adds **Fuzzy TOPSIS**, so decision makers can choose
between schedules using several criteria, not cost alone.
""")

c1, c2 = st.columns(2)
with c1.container(border=True):
    st.markdown("### 🗓️ Normal Schedule")
    st.markdown("""
**Hybrid MILP–ACO**, minimum-cost schedule.

- Enter or upload bus, price, consumption and availability data
- Get the cheapest feasible charging schedule
- Compare with the exact MILP optimum and the LP lower bound
- Repeat runs for statistics; run the ablation study (Plain ACO / H1 / H2)
""")
    st.page_link(st.session_state["_pages"]["normal"], label="Open Normal Schedule →", icon="🗓️")
with c2.container(border=True):
    st.markdown("### 🏆 Advanced Schedule")
    st.markdown("""
**Hybrid MILP–ACO + Fuzzy TOPSIS**, multi-criteria decision.

- Generate one optimal schedule per charging policy (safety buffer, reserve)
- Score them on cost, degradation, safety, readiness and grid impact
- Rank them using decision makers' linguistic opinions (Fuzzy TOPSIS)
- Check the robustness of the choice with sensitivity analysis
""")
    st.page_link(st.session_state["_pages"]["advanced"], label="Open Advanced Schedule →", icon="🏆")

st.subheader("How the system works")
st.graphviz_chart("""
digraph {
  rankdir=LR; bgcolor="transparent";
  node [shape=box, style="rounded,filled", fillcolor="#e9f5f3", color="#2a9d8f",
        fontname="Helvetica", fontsize=11];
  edge [color="#555555"];
  data [label="Input data\\nbuses · prices\\nconsumption · availability"];
  lp   [label="LP relaxation\\n(lower bound, H1 pheromone)"];
  aco  [label="Ant Colony\\nconstruction + repair"];
  lns  [label="MILP fix-and-optimise\\n(H2 local search)"];
  stop [label="Optimality gap check\\n(H3 stopping rule)"];
  sch  [label="Normal schedule\\n(minimum cost)", fillcolor="#2a9d8f", fontcolor="white"];
  pol  [label="Charging policies\\nA1 … An"];
  fz   [label="Fuzzy TOPSIS\\n(decision makers' weights)"];
  adv  [label="Advanced schedule\\n(best compromise)", fillcolor="#2a9d8f", fontcolor="white"];
  data -> lp -> aco -> lns -> stop -> sch;
  stop -> aco [style=dashed, label="pheromone\\nupdate", fontsize=9];
  data -> pol -> lp;
  sch -> fz [label="one per policy", fontsize=9];
  fz -> adv;
}
""")

st.subheader("Current input data")
try:
    d = current_data()
    m = st.columns(5)
    m[0].metric("Buses", d.num_buses)
    m[1].metric("Time slots", d.num_slots)
    m[2].metric("Chargers", d.num_chargers)
    m[3].metric("Required charging slots", int(d.required_slots.sum()))
    m[4].metric("Price range (RM/kWh)",
                f"{d.electricity_price.min():.2f} – {d.electricity_price.max():.2f}")
    st.caption("The thesis data is loaded by default. Edit it on either schedule page; "
               "both pages share the same data.")
except Exception as e:  # data being edited into an invalid state
    st.caption(f"Input data not ready: {e}")

with st.expander("How to use"):
    st.markdown("""
1. Open **Normal Schedule**, check or edit the input data, then press **Run**.
2. Read the schedule, battery levels and charger use, and download the results to Excel.
3. Open **Advanced Schedule**, define charging policies, then press **Generate & rank**.
4. Enter the decision makers' opinions; the Fuzzy TOPSIS ranking updates instantly.
5. Use **Stage 4 Sensitivity** to check that the chosen schedule is robust.
""")
