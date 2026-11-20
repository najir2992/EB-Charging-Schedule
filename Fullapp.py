"""
app.py - Electric Bus Charging Scheduling System (entry point).

    streamlit run app.py

Login is required. After login, three pages are shown in the top navigation bar:
    Home · Normal Schedule (Hybrid MILP-ACO) · Advanced Schedule (Hybrid MILP-ACO + Fuzzy)
"""

import streamlit as st

import auth

st.set_page_config(page_title="E-Bus Charging Scheduling System", page_icon="⚡",
                   layout="wide")

user = auth.current_user()

if user is None:
    # Only the login page exists until the user logs in
    pg = st.navigation([st.Page(auth.login_form, title="Log in", icon="🔒")],
                       position="hidden")
else:
    home = st.Page("views/home.py", title="Home", icon="🏠", default=True)
    normal = st.Page("views/normal_schedule.py", title="Normal Schedule", icon="🗓️")
    advanced = st.Page("views/advanced_schedule.py", title="Advanced Schedule", icon="🏆")
    pg = st.navigation([home, normal, advanced], position="top")

    with st.sidebar:
        st.markdown(f"👤 **{user['name']}**  \n`{user['username']}` · {user['role']}")
        if st.button("Log out", icon="🚪"):
            auth.logout()
        st.divider()

pg.run()
