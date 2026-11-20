"""
auth.py - simple username/password login for the Streamlit system.

Users are stored in users.json as salted PBKDF2-SHA256 hashes (the plain password
is never saved). Add, remove or reset users with:   python manage_users.py
"""

import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

import streamlit as st

USERS_FILE = Path(__file__).with_name("users.json")
ITERATIONS = 200_000
MAX_ATTEMPTS = 5          # failed attempts before a short lock-out
LOCK_SECONDS = 30


# ---------------- password hashing ----------------
def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt, digest = stored.split("$")
        new = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iters))
        return hmac.compare_digest(new.hex(), digest)
    except (ValueError, AttributeError):
        return False


# ---------------- user store ----------------
def load_users() -> dict:
    if not USERS_FILE.exists():
        return {}
    return json.loads(USERS_FILE.read_text(encoding="utf-8"))


def save_users(users: dict):
    tmp = USERS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(users, indent=2), encoding="utf-8")
    os.replace(tmp, USERS_FILE)


def authenticate(username: str, password: str) -> dict | None:
    user = load_users().get(username.strip().lower())
    if user and verify_password(password, user["password"]):
        return {"username": username.strip().lower(), "name": user.get("name", username),
                "role": user.get("role", "user")}
    return None


# ---------------- session helpers ----------------
def current_user() -> dict | None:
    return st.session_state.get("user")


def logout():
    # Clear everything, so the next user starts with a clean session
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.rerun()


def login_form():
    """The login page (shown when nobody is logged in)."""
    ss = st.session_state
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        st.markdown("<div style='height:6vh'></div>", unsafe_allow_html=True)
        st.markdown("## ⚡ E-Bus Charging Scheduler")
        st.caption("Hybrid MILP–ACO and Fuzzy decision support for electric bus "
                   "charging scheduling")

        locked_until = ss.get("locked_until", 0)
        if time.time() < locked_until:
            st.error(f"Too many failed attempts. Try again in "
                     f"{int(locked_until - time.time()) + 1} s.")
            return

        with st.form("login", border=True):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            ok = st.form_submit_button("Log in", type="primary")
        if ok:
            user = authenticate(username, password)
            if user:
                ss.user = user
                ss.failed = 0
                st.rerun()
            else:
                ss.failed = ss.get("failed", 0) + 1
                if ss.failed >= MAX_ATTEMPTS:
                    ss.locked_until = time.time() + LOCK_SECONDS
                    ss.failed = 0
                st.error("Incorrect username or password.")
        if not load_users():
            st.warning("No users found. Create one first with:  python manage_users.py")
