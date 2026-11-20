"""
data_input.py - shared "Data input" section (buses, prices, consumption, availability,
system parameters, Excel import/export). The same data is used by the Normal and the
Advanced schedule pages, so the user enters it only once.
"""

import hashlib
import io

import numpy as np
import pandas as pd
import streamlit as st

from hybrid_core import ProblemData, default_data
from state import get_table, get_value, persist, persist_editor, set_table, set_value

SYS_FIELDS = ["num_chargers", "charger_power", "battery_capacity", "min_energy",
              "degradation_cost_per_kWh"]


def data_to_frames(d: ProblemData) -> dict:
    return {
        "buses": pd.DataFrame({"Bus": d.bus_names,
                               "Initial Energy (kWh)": d.initial_energy,
                               "Target Energy (kWh)": d.target_energy}),
        "prices": pd.DataFrame({"Slot": d.slot_names, "Price (RM/kWh)": d.electricity_price}),
        "consumption": pd.DataFrame(d.energy_consumption, index=d.bus_names, columns=d.slot_names),
        "availability": pd.DataFrame(d.bus_availability.astype(bool), index=d.bus_names,
                                     columns=d.slot_names),
    }


def load_data(d: ProblemData):
    """Put a ProblemData into the input tables and fields."""
    for name, df in data_to_frames(d).items():
        set_table(name, df)
    set_value("n_buses", d.num_buses)
    set_value("n_slots", d.num_slots)
    set_value("num_chargers", int(d.num_chargers))
    for f in SYS_FIELDS[1:]:
        set_value(f, float(getattr(d, f)))


def resize(frames: dict, n_buses: int, n_slots: int) -> dict:
    old_b = frames["buses"]["Bus"].astype(str).tolist()
    old_s = frames["prices"]["Slot"].astype(str).tolist()
    buses = (old_b + [f"EB{i+1}" for i in range(len(old_b), n_buses)])[:n_buses]
    slots = (old_s + [f"t{t+1}" for t in range(len(old_s), n_slots)])[:n_slots]
    b = frames["buses"].reset_index(drop=True).reindex(range(n_buses))
    b["Bus"] = buses
    b = b.fillna({"Initial Energy (kWh)": 50.0, "Target Energy (kWh)": 50.0})
    p = frames["prices"].reset_index(drop=True).reindex(range(n_slots))
    p["Slot"] = slots
    p = p.fillna({"Price (RM/kWh)": 0.50})

    def grid(df, fill):
        g = pd.DataFrame(fill, index=buses, columns=slots, dtype=type(fill))
        r, k = min(len(df), n_buses), min(df.shape[1], n_slots)
        g.iloc[:r, :k] = df.to_numpy()[:r, :k]
        return g

    return {"buses": b, "prices": p, "consumption": grid(frames["consumption"], 0.0),
            "availability": grid(frames["availability"].astype(bool), True)}


def frames_to_data(f: dict, s: dict) -> ProblemData:
    return ProblemData(
        initial_energy=f["buses"]["Initial Energy (kWh)"].to_numpy(float),
        target_energy=f["buses"]["Target Energy (kWh)"].to_numpy(float),
        energy_consumption=f["consumption"].to_numpy(float),
        bus_availability=f["availability"].to_numpy().astype(int),
        electricity_price=f["prices"]["Price (RM/kWh)"].to_numpy(float),
        bus_names=f["buses"]["Bus"].astype(str).tolist(),
        slot_names=f["prices"]["Slot"].astype(str).tolist(), **s)


def frames_to_excel(f: dict, s: dict) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        pd.DataFrame(list(s.items()), columns=["Parameter", "Value"]).to_excel(
            xw, sheet_name="System", index=False)
        f["buses"].to_excel(xw, sheet_name="Buses", index=False)
        f["prices"].to_excel(xw, sheet_name="Prices", index=False)
        f["consumption"].to_excel(xw, sheet_name="Consumption")
        f["availability"].astype(int).to_excel(xw, sheet_name="Availability")
    return buf.getvalue()


def excel_to_data(file) -> ProblemData:
    x = pd.read_excel(file, sheet_name=None)
    sysd = dict(zip(x["System"]["Parameter"], x["System"]["Value"]))
    buses, prices = x["Buses"], x["Prices"]
    cons = x["Consumption"].set_index(x["Consumption"].columns[0])
    avail = x["Availability"].set_index(x["Availability"].columns[0])
    return ProblemData(
        initial_energy=buses.iloc[:, 1], target_energy=buses.iloc[:, 2],
        energy_consumption=cons.to_numpy(float), bus_availability=avail.to_numpy(int),
        electricity_price=prices.iloc[:, 1],
        bus_names=buses.iloc[:, 0].astype(str).tolist(),
        slot_names=prices.iloc[:, 0].astype(str).tolist(),
        num_chargers=int(sysd["num_chargers"]), charger_power=float(sysd["charger_power"]),
        battery_capacity=float(sysd["battery_capacity"]), min_energy=float(sysd["min_energy"]),
        degradation_cost_per_kWh=float(sysd["degradation_cost_per_kWh"]))


def ensure_data():
    if get_table("buses") is None:
        load_data(default_data())


def current_data() -> ProblemData:
    """The data as last edited (usable on any page, e.g. the Home page summary)."""
    ensure_data()
    frames = {n: get_table(n) for n in ["buses", "prices", "consumption", "availability"]}
    return frames_to_data(frames, {f: get_value(f) for f in SYS_FIELDS})


def fingerprint(d: ProblemData) -> str:
    """Short hash of the data, used to warn when results are out of date."""
    parts = [d.initial_energy, d.target_energy, d.energy_consumption, d.bus_availability,
             d.electricity_price, np.array([getattr(d, f) for f in SYS_FIELDS], float)]
    return hashlib.md5(b"".join(np.ascontiguousarray(p, float).tobytes() for p in parts)
                       ).hexdigest()


def render_data_input(prefix: str, min_energy_label="Min energy (kWh)"):
    """Draw the data-input section. Returns (ProblemData, list of errors)."""
    ensure_data()
    top = st.columns([1, 3])
    if top[0].button("↺ Load thesis data", key=f"{prefix}_reset"):
        load_data(default_data())
        st.rerun()
    up = top[1].file_uploader("Upload Excel input (same layout as the template)",
                              type=["xlsx"], key=f"{prefix}_upload")
    if up is not None and st.session_state.get("last_upload") != up.file_id:
        try:
            load_data(excel_to_data(up))
            st.session_state.last_upload = up.file_id
            st.rerun()
        except Exception as e:
            st.error(f"Could not read the file: {e}")

    st.markdown("**System parameters**")
    c = st.columns(7)
    with c[0]:
        n_buses = persist(st.number_input, "Buses", "n_buses", 15, 1, 100)
    with c[1]:
        n_slots = persist(st.number_input, "Time slots", "n_slots", 8, 2, 96)
    with c[2]:
        persist(st.number_input, "Chargers", "num_chargers", 6, 1, 100)
    with c[3]:
        persist(st.number_input, "kWh per slot", "charger_power", 30.0, 1.0, 500.0)
    with c[4]:
        persist(st.number_input, "Battery cap. (kWh)", "battery_capacity", 120.0, 10.0, 1000.0)
    with c[5]:
        persist(st.number_input, min_energy_label, "min_energy", 20.0, 0.0, 500.0)
    with c[6]:
        persist(st.number_input, "Degradation RM/kWh", "degradation_cost_per_kWh", 0.05,
                0.0, 5.0, step=0.01)
    s = {f: get_value(f) for f in SYS_FIELDS}

    left, right = st.columns(2)
    with left:
        st.markdown("**Buses**")
        buses = persist_editor("buses", get_table("buses"), hide_index=True, disabled=["Bus"])
    with right:
        st.markdown("**Electricity price per slot**")
        prices = persist_editor("prices", get_table("prices"), hide_index=True)
    st.markdown("**Energy consumption per slot (kWh)**")
    consumption = persist_editor("consumption", get_table("consumption"))
    st.markdown("**Bus availability for charging (✔ = at depot, can charge)**")
    availability = persist_editor("availability", get_table("availability"))

    edited = {"buses": buses, "prices": prices, "consumption": consumption,
              "availability": availability}
    if n_buses != len(buses) or n_slots != len(prices):
        for name, df in resize(edited, n_buses, n_slots).items():
            set_table(name, df)
        st.rerun()

    data = frames_to_data(edited, s)
    st.download_button("⬇️ Download these inputs as an Excel template",
                       frames_to_excel(edited, s), "ebus_input.xlsx", key=f"{prefix}_dl")
    errors = data.validate()
    m = st.columns(3)
    m[0].metric("Required charging slots", int(data.required_slots.sum()))
    m[1].metric("Charger capacity (slots)", data.num_chargers * data.num_slots)
    m[2].metric("Capacity utilisation",
                f"{data.required_slots.sum() / (data.num_chargers * data.num_slots):.0%}")
    for e in errors:
        st.error(e)
    return data, errors
