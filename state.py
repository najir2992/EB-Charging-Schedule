"""
state.py - keep widget values and edited tables when the user switches pages.

Streamlit deletes a widget's state when its page is not shown, so values typed on the
"Normal schedule" page would be lost after visiting another page. These helpers keep a
saved copy in st.session_state and restore it when the page is opened again.
"""

import streamlit as st


def persist(widget, label, key, default, *args, **kwargs):
    """Call a Streamlit input widget whose value survives page switches.
    Example: persist(st.slider, "Ants", "n_ants", 30, 5, 100, step=5)"""
    ss = st.session_state
    saved, wkey = f"_v_{key}", f"_w_{key}"
    if saved not in ss:
        ss[saved] = default
    if wkey not in ss:                      # page (re)opened -> restore saved value
        ss[wkey] = ss[saved]
    value = widget(label, *args, key=wkey, **kwargs)
    ss[saved] = value
    return value


def get_value(key, default=None):
    return st.session_state.get(f"_v_{key}", default)


def set_value(key, value):
    """Change a persisted widget value from code (e.g. 'Load thesis data')."""
    st.session_state[f"_v_{key}"] = value
    st.session_state.pop(f"_w_{key}", None)


def persist_editor(name, default_df, **kwargs):
    """st.data_editor whose edits survive page switches."""
    ss = st.session_state
    saved, base, ver = f"_saved_{name}", f"_base_{name}", f"_ver_{name}"
    if saved not in ss:
        ss[saved] = default_df.copy()
    ss.setdefault(ver, 0)
    key = f"_ed_{name}_{ss[ver]}"
    if key not in ss:                       # fresh editor -> start from last saved table
        ss[base] = ss[saved].copy()
    out = st.data_editor(ss[base], key=key, **kwargs)
    ss[saved] = out
    return out


def set_table(name, df):
    """Replace an editor's table from code (reset / resize / upload)."""
    ss = st.session_state
    ss[f"_saved_{name}"] = df.copy()
    ss[f"_ver_{name}"] = ss.get(f"_ver_{name}", 0) + 1


def get_table(name):
    return st.session_state.get(f"_saved_{name}")
