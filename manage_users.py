"""
manage_users.py - add, remove, list users or change a password.

Usage (run in a terminal inside this folder):
    python manage_users.py                 # interactive menu
    python manage_users.py add             # add a user
    python manage_users.py password        # change a password
    python manage_users.py remove          # remove a user
    python manage_users.py list            # list users
"""

import getpass
import sys

from auth import hash_password, load_users, save_users


def ask_password() -> str:
    while True:
        p1 = getpass.getpass("Password (min 6 characters, hidden while typing): ")
        if len(p1) < 6:
            print("  Too short.")
            continue
        if p1 != getpass.getpass("Repeat password: "):
            print("  Passwords do not match.")
            continue
        return p1


def add():
    users = load_users()
    username = input("Username: ").strip().lower()
    if not username or username in users:
        print("  Empty or existing username.")
        return
    name = input("Full name: ").strip() or username
    role = input("Role [admin/user] (default user): ").strip().lower() or "user"
    users[username] = {"name": name, "role": role, "password": hash_password(ask_password())}
    save_users(users)
    print(f"  User '{username}' added.")


def change_password():
    users = load_users()
    username = input("Username: ").strip().lower()
    if username not in users:
        print("  No such user.")
        return
    users[username]["password"] = hash_password(ask_password())
    save_users(users)
    print("  Password changed.")


def remove():
    users = load_users()
    username = input("Username to remove: ").strip().lower()
    if users.pop(username, None) is None:
        print("  No such user.")
        return
    save_users(users)
    print(f"  User '{username}' removed.")


def list_users():
    for u, d in load_users().items():
        print(f"  {u:15s} {d.get('name', ''):30s} {d.get('role', 'user')}")


ACTIONS = {"add": add, "password": change_password, "remove": remove, "list": list_users}

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ACTIONS:
        ACTIONS[sys.argv[1]]()
    else:
        while True:
            print("\n1) add user  2) change password  3) remove user  4) list  5) quit")
            choice = input("> ").strip()
            if choice == "5":
                break
            {"1": add, "2": change_password, "3": remove, "4": list_users}.get(
                choice, lambda: print("  ?"))()
