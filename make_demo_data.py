"""
Creates data/demo_sales.csv: a small SYNTHETIC and deliberately messy sales dataset
(text prices, mixed date formats, typos, duplicates, blanks) for trying the app.
All values are randomly generated, so there are no licence or privacy concerns.

Run:  python make_demo_data.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

rng = np.random.default_rng(42)
N = 800

CATALOG = {
    "Furniture": {"Chairs": (60, 180), "Tables": (150, 420), "Bookcases": (90, 260)},
    "Office Supplies": {"Binders": (5, 30), "Paper": (4, 25), "Storage": (20, 90)},
    "Technology": {"Phones": (120, 700), "Accessories": (15, 120), "Copiers": (300, 1500)},
}
STATES = {  # state -> (region, cities)
    "California": ("West", ["Los Angeles", "San Francisco"]),
    "Washington": ("West", ["Seattle"]),
    "Texas": ("South", ["Houston", "Austin"]),
    "Florida": ("South", ["Miami", "Orlando"]),
    "New York": ("East", ["New York City", "Buffalo"]),
    "Pennsylvania": ("East", ["Philadelphia"]),
    "Illinois": ("Central", ["Chicago"]),
    "Ohio": ("Central", ["Columbus", "Cleveland"]),
}
FIRST = ["Ava", "Liam", "Noah", "Mia", "Ethan", "Zoe", "Lucas", "Maya", "Omar", "Priya", "Ben", "Sara"]
LAST = ["Smith", "Johnson", "Brown", "Lee", "Patel", "Garcia", "Khan", "Miller", "Davis", "Wilson"]
REPS = ["Alex Carter", "Dana Brooks", "Evan Cole", "Fiona Reed", "Gus Hall", "Hana Kim"]

customers = [(f"CU-{10000 + i}", f"{rng.choice(FIRST)} {rng.choice(LAST)}",
              rng.choice(["Consumer", "Corporate", "Home Office"], p=[0.5, 0.3, 0.2]))
             for i in range(150)]

rows = []
for i in range(N):
    cat = rng.choice(list(CATALOG))
    sub = rng.choice(list(CATALOG[cat]))
    lo, hi = CATALOG[cat][sub]
    price = round(float(rng.uniform(lo, hi)), 2)
    qty = int(rng.integers(1, 9))
    disc = float(rng.choice([0, 0, 0.05, 0.1, 0.15, 0.2, 0.3]))
    sales = round(price * qty * (1 - disc), 2)
    profit = round(sales * float(rng.normal(0.12, 0.18)), 2)
    state = rng.choice(list(STATES))
    region, cities = STATES[state]
    cid, cname, seg = customers[int(rng.integers(len(customers)))]
    order = pd.Timestamp("2021-01-01") + pd.Timedelta(days=int(rng.integers(0, 1460)))
    ship = order + pd.Timedelta(days=int(rng.integers(1, 8)))
    rows.append({
        "Row ID": i + 1,
        "Order ID": f"US-{order.year}-{100000 + int(rng.integers(0, 600))}",
        "Order Date": order, "Ship Date": ship,
        "Ship Mode": rng.choice(["Standard Class", "First Class", "Second Class", "Same Day"], p=[0.6, 0.2, 0.15, 0.05]),
        "Customer ID": cid, "Customer Name": cname, "Segment": seg,
        "Country": "United States", "City": rng.choice(cities), "State": state, "Region": region,
        "Product ID": f"{cat[:3].upper()}-{sub[:2].upper()}-{1000 + int(rng.integers(0, 40))}",
        "Category": cat, "Sub Category": sub,
        "Product Name": f"{sub[:-1] if sub.endswith('s') else sub} {int(rng.integers(100, 999))}",
        "Unit Price": price, "Quantity": qty, "Discount": disc, "Sales": sales, "Profit": profit,
        "Shipping Cost": round(float(rng.uniform(2, 60)), 2),
        "Order Priority": rng.choice(["Low", "Medium", "High", "Critical"], p=[0.2, 0.4, 0.3, 0.1]),
        "Payment Method": rng.choice(["Credit Card", "Debit Card", "PayPal", "Bank Transfer", "Cash on Delivery"]),
        "Sales Rep": rng.choice(REPS),
        "Return Status": rng.choice(["Not Returned", "Returned"], p=[0.88, 0.12]),
        "Customer Rating": int(rng.integers(1, 6)),
    })
df = pd.DataFrame(rows)

# ---------- make it messy ----------
def pick(frac):
    return rng.random(len(df)) < frac

# mixed date formats
fmts = ["%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%b %d, %Y", "%d.%m.%Y"]
for col in ["Order Date", "Ship Date"]:
    df[col] = [d.strftime(fmts[int(rng.integers(len(fmts)))]) for d in df[col]]

# prices and amounts as text
df["Sales"] = df["Sales"].astype(object)
m = pick(0.15); df.loc[m, "Sales"] = ["$" + format(float(v), ",.2f") for v in df.loc[m, "Sales"]]
m = pick(0.05); df.loc[m, "Sales"] = ["USD " + str(v) for v in df.loc[m, "Sales"]]
df["Unit Price"] = df["Unit Price"].astype(object)
m = pick(0.10); df.loc[m, "Unit Price"] = ["$" + str(v) for v in df.loc[m, "Unit Price"]]
df["Customer Rating"] = df["Customer Rating"].astype(object)
m = pick(0.06); df.loc[m, "Customer Rating"] = [f"{v} stars" for v in df.loc[m, "Customer Rating"]]
df["Discount"] = df["Discount"].astype(object)
m = pick(0.05); df.loc[m, "Discount"] = [f"{round(float(v) * 100)}%" for v in df.loc[m, "Discount"]]

# typos and inconsistent labels
typos = {"Furniture": ["Furnitre", "furniture"], "Office Supplies": ["Ofice Supplies", "office supplies"],
         "Technology": ["Tech", "technology"]}
for i in np.where(pick(0.10))[0]:
    df.at[i, "Category"] = rng.choice(typos[df.at[i, "Category"]])
m = pick(0.08); df.loc[m, "Region"] = df.loc[m, "Region"].str.lower()
m = pick(0.05); df.loc[m, "Payment Method"] = df.loc[m, "Payment Method"].replace(
    {"Credit Card": "CC", "Cash on Delivery": "COD"})
m = pick(0.06); df.loc[m, "Ship Mode"] = df.loc[m, "Ship Mode"].replace(
    {"Standard Class": "std class", "First Class": "1st Class"})
m = pick(0.08); df.loc[m, "City"] = df.loc[m, "City"].str.lower()
m = pick(0.06); df.loc[m, "Customer Name"] = df.loc[m, "Customer Name"].str.upper()
m = pick(0.05); df.loc[m, "Customer Name"] = "  " + df.loc[m, "Customer Name"] + " "

# impossible values and junk tokens
m = pick(0.01); df.loc[m, "Quantity"] = 999
m = pick(0.01); df.loc[m, "Customer Rating"] = 10
for col, frac in {"Profit": 0.03, "Shipping Cost": 0.03, "Sales Rep": 0.02, "Ship Date": 0.01}.items():
    df[col] = df[col].astype(object)
    df.loc[pick(frac), col] = rng.choice(["", "missing", "?", "-"])

# duplicate rows
df = pd.concat([df, df.sample(25, random_state=1)], ignore_index=True)

out = Path("data"); out.mkdir(exist_ok=True)
df.to_csv(out / "demo_sales.csv", index=False)
print(f"Saved data/demo_sales.csv with {len(df)} rows and {df.shape[1]} columns.")