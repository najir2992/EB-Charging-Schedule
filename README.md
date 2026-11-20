# Electric Bus Charging Scheduling System
Hybrid MILP–ACO (Normal Schedule) + Hybrid MILP–ACO with Fuzzy TOPSIS (Advanced Schedule),
with login.

## 1. Run
```bash
pip install -r requirements.txt
streamlit run app.py
```
Log in with the default account, then **change its password straight away**:

| Username | Password   |
|----------|------------|
| admin    | admin123   |

## 2. Manage users
In a terminal inside this folder:
```bash
python manage_users.py            # menu: add / change password / remove / list
python manage_users.py add        # add a user directly
python manage_users.py password   # change a password
```
Users are kept in `users.json` as salted PBKDF2 hashes. Plain passwords are never stored.
After 5 wrong passwords, login is locked for 30 seconds.

## 3. Pages
| Page                  | What it does                                                        |
|-----------------------|---------------------------------------------------------------------|
| 🏠 Home               | Introduction, the two modules, workflow diagram, current data summary |
| 🗓️ Normal Schedule    | Hybrid MILP-ACO: data input → Run → schedule, charts, statistics     |
| 🏆 Advanced Schedule  | Hybrid MILP-ACO + Fuzzy TOPSIS: policies → alternatives → ranking → sensitivity |

The input data is **shared**: edit it on either schedule page and both pages use it.
Settings and tables are kept when you move between pages. If the data changes after a
run, the page warns you that the results are out of date.

## 4. Project structure
```
ebus_system/
├── app.py                 # entry point: login gate + top navigation
├── auth.py                # login, password hashing, logout
├── manage_users.py        # command-line user management
├── users.json             # user accounts (hashed passwords)
├── state.py               # keeps inputs when switching pages
├── data_input.py          # shared data-input section
├── hybrid_core.py         # Hybrid MILP-ACO engine
├── fuzzy_core.py          # Fuzzy TOPSIS stages 1-4
├── charts.py              # all Plotly charts
├── views/
│   ├── home.py
│   ├── normal_schedule.py
│   └── advanced_schedule.py
├── .streamlit/config.toml # theme colour
└── requirements.txt
```

## 5. Verified results (thesis data, default settings)
- Normal Schedule: RM 692.10 = exact MILP optimum (LP bound RM 683.10)
- Advanced Schedule: A1–A8 = RM 692.10 … 795.60, Fuzzy TOPSIS selects **A4** (CC 0.5892)

## 6. Note on security
This login is suitable for a research system or a demo. If you put it on the internet,
use HTTPS (Streamlit Community Cloud provides it) and strong passwords. Do not upload
`users.json` to a public GitHub repository.
