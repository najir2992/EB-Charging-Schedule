"""
app.py - Electric Bus Charging Scheduling System (entry point).

    streamlit run app.py        (the file may be renamed, e.g. Fullapp.py)

Login is required. After login, three pages are shown in the top navigation bar:
    Home · Normal Schedule (Hybrid MILP-ACO) · Advanced Schedule (Hybrid MILP-ACO + Fuzzy)
"""

from pathlib import Path

import streamlit as st

import auth

st.set_page_config(page_title="E-Bus Charging Scheduling System", page_icon="⚡",
                   layout="wide")

# All page files are found relative to THIS file, wherever the app is run from
BASE = Path(__file__).resolve().parent
PAGE_FILES = {
    "home": BASE / "views" / "home.py",
    "normal": BASE / "views" / "normal_schedule.py",
    "advanced": BASE / "views" / "advanced_schedule.py",
}


def missing_files_page():
    st.error("Some files of the system are missing, so the pages cannot be opened.")
    st.markdown("**Missing:**\n" + "\n".join(
        f"- `{p.relative_to(BASE).as_posix()}`" for p in PAGE_FILES.values() if not p.exists()))
    st.markdown(
        "Every page file must be inside a folder called **`views`** (lower-case), "
        "in the **same folder as this main file**. On GitHub, open your repository and check "
        "that you can see the `views` folder containing `home.py`, `normal_schedule.py` and "
        "`advanced_schedule.py`.")
    st.markdown("**Files found next to the main file:**")
    st.code("\n".join(sorted(
        p.relative_to(BASE).as_posix() for p in BASE.rglob("*")
        if p.is_file() and ".git" not in p.parts)) or "(none)")


user = auth.current_user()

if user is None:
    # Only the login page exists until the user logs in
    pg = st.navigation([st.Page(auth.login_form, title="Log in", icon="🔒")],
                       position="hidden")
elif not all(p.exists() for p in PAGE_FILES.values()):
    pg = st.navigation([st.Page(missing_files_page, title="Setup problem", icon="⚠️")],
                       position="hidden")
else:
    pages = {
        "home": st.Page(PAGE_FILES["home"], title="Home", icon="🏠", default=True),
        "normal": st.Page(PAGE_FILES["normal"], title="Normal Schedule", icon="🗓️"),
        "advanced": st.Page(PAGE_FILES["advanced"], title="Advanced Schedule", icon="🏆"),
    }
    st.session_state["_pages"] = pages          # used by the links on the Home page
    pg = st.navigation(list(pages.values()), position="top")

if user is not None:
    with st.sidebar:
        st.markdown(f"👤 **{user['name']}**  \n`{user['username']}` · {user['role']}")
        if st.button("Log out", icon="🚪"):
            auth.logout()
        st.divider()

pg.run()
