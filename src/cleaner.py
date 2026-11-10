import re
import numpy as np
import pandas as pd

NULL_TOKENS = {"", "-", "?", "missing", "none", "nan", "n/a", "na", "null", "$nan"}
WORD_NUMS = {"zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
             "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10"}


def _strip_text(df):
    """Trim spaces and turn junk tokens into real nulls in text columns."""
    for col in df.select_dtypes(include=["object", "string"]).columns:
        s = df[col].astype("string").str.strip().str.replace(r"\s+", " ", regex=True)
        df[col] = s.mask(s.str.lower().isin(NULL_TOKENS))
    return df


def _to_number(s):
    s = s.astype("string").str.lower().str.strip()
    s = s.replace(WORD_NUMS)
    s = s.str.replace(r"usd|[$,]|stars?", "", regex=True).str.strip()
    return pd.to_numeric(s, errors="coerce")


def _to_discount(s):
    s = s.astype("string").str.lower().str.strip()
    s = s.replace({"ten percent": "10%", "twenty percent": "20%", "five percent": "5%"})
    pct = s.str.endswith("%", na=False)
    num = pd.to_numeric(s.str.replace("%", "", regex=False), errors="coerce").astype("Float64")
    return num.where(~pct, num / 100)


def _to_date(s):
    """
    Parse dates written in mixed formats without swapping day and month.
    - Year-first dates (2024-05-06, 2024/05/06) are always year-month-day.
    - Numeric dates like 06/05/2024 or 03-10-2023: if one part is above 12 it must be
      the day, so the order is clear. Unclear ones follow the style that the clear
      ones use for the same separator (day-first if there is no evidence).
    - Text dates like "May 06, 2024" are parsed normally.
    """
    s = s.astype("string").str.strip()

    year_first = s.str.match(r"^\d{4}[-/.]\d{1,2}[-/.]\d{1,2}").fillna(False).astype(bool)
    out = pd.to_datetime(s.where(year_first), format="mixed", dayfirst=False, errors="coerce")

    parts = s.str.extract(r"^(\d{1,2})([-/.])(\d{1,2})[-/.](\d{4})")
    numeric = parts[0].notna().astype(bool)
    a = pd.to_numeric(parts[0], errors="coerce")
    b = pd.to_numeric(parts[2], errors="coerce")

    month_first_style = {}
    for sep in parts[1].dropna().unique():
        same_sep = parts[1] == sep
        day_votes = int((same_sep & (a > 12)).sum())
        month_votes = int((same_sep & (b > 12)).sum())
        month_first_style[sep] = month_votes > day_votes
    style_mf = parts[1].map(month_first_style).fillna(False).astype(bool)
    month_first = numeric & ((b > 12) | (~(a > 12) & style_mf))

    out = out.fillna(pd.to_datetime(s.where(numeric & ~month_first), format="mixed", dayfirst=True, errors="coerce"))
    out = out.fillna(pd.to_datetime(s.where(month_first), format="mixed", dayfirst=False, errors="coerce"))
    other = ~year_first & ~numeric
    return out.fillna(pd.to_datetime(s.where(other), format="mixed", dayfirst=True, errors="coerce"))


STATES = {"FL": "Florida", "PA": "Pennsylvania", "MI": "Michigan", "IL": "Illinois",
          "OH": "Ohio", "MA": "Massachusetts", "GA": "Georgia", "OR": "Oregon",
          "CA": "California", "VA": "Virginia", "WA": "Washington", "NY": "New York",
          "CO": "Colorado", "TN": "Tennessee", "NC": "North Carolina", "TX": "Texas"}


def _merge_case_variants(s):
    """'PHONES', 'phones', 'Phones' -> the most common spelling."""
    low = s.astype("string").str.lower()
    best = s.groupby(low).agg(lambda x: x.value_counts().index[0])
    return low.map(best).astype("string")


def clean_dataset(df):
    """Returns (clean_df, log) where log lists what was fixed."""
    log = []
    df = df.copy()
    df.columns = [re.sub(r"\W+", "_", str(c).strip().lower()).strip("_") for c in df.columns]

    # drop empty / junk columns
    empty = [c for c in df.columns if df[c].isna().all() or c.startswith("unnamed")]
    if empty:
        df = df.drop(columns=empty)
        log.append(f"Dropped empty columns: {empty}")

    df = _strip_text(df)

    # numeric columns stored as text
    for col in ["unit_price", "quantity", "sales", "profit", "shipping_cost", "customer_rating"]:
        if col in df:
            df[col] = _to_number(df[col])
    if "discount" in df:
        df["discount"] = _to_discount(df["discount"])
    log.append("Converted price/quantity/sales/profit/discount/rating to numbers")

    # impossible values -> null (kept as missing instead of corrupting totals)
    if "quantity" in df:
        df.loc[(df["quantity"] <= 0) | (df["quantity"] > 100), "quantity"] = np.nan
    if "discount" in df:
        df.loc[(df["discount"] < 0) | (df["discount"] > 1), "discount"] = np.nan
    if "customer_rating" in df:
        df.loc[(df["customer_rating"] < 1) | (df["customer_rating"] > 5), "customer_rating"] = np.nan
    log.append("Set impossible values (negative/huge quantity, discount outside 0-100%, rating outside 1-5) to null")

    # dates (mixed formats)
    for col in ["order_date", "ship_date"]:
        if col in df:
            df[col] = _to_date(df[col])
    log.append("Standardised mixed date formats (year-first dates are year-month-day; unclear ones follow the style of the clear ones)")

    # category-like columns: fix case/typos
    def canon(col, rules):
        if col in df:
            low = df[col].astype("string").str.lower()
            for pattern, value in rules.items():
                df.loc[low.str.contains(pattern, na=False, regex=True), col] = value

    canon("category", {r"^of+i?c|^offic": "Office Supplies", r"^furn": "Furniture", r"^tech": "Technology"})
    canon("segment", {r"consumer": "Consumer", r"corporate": "Corporate", r"home": "Home Office"})
    canon("country", {r".*": "United States"})
    if "region" in df:
        df["region"] = df["region"].astype("string").str.lower().map(
            {"east": "East", "west": "West", "south": "South", "central": "Central",
             "w": "West", "e": "East", "s": "South", "c": "Central"})
    canon("payment_method", {r"^cc$|credit": "Credit Card", r"debit": "Debit Card",
                             r"^cod$|cash": "Cash on Delivery", r"paypal": "PayPal", r"bank": "Bank Transfer"})
    canon("order_priority", {r"^crit|urgent": "Critical", r"^high": "High", r"^med": "Medium", r"^low": "Low"})
    canon("ship_mode", {r"std|standard": "Standard Class", r"1st|first": "First Class",
                        r"second": "Second Class", r"same": "Same Day"})
    if "state" in df:
        df["state"] = df["state"].map(lambda v: STATES.get(v, v) if isinstance(v, str) else v)
    for col in df.columns:   # fix remaining case differences in small text columns
        if str(df[col].dtype) in ("string", "object", "str") and 1 < df[col].nunique() <= 60:
            df[col] = _merge_case_variants(df[col])
    if "return_status" in df:
        low = df["return_status"].astype("string").str.lower()
        yes = low.isin(["returned", "yes", "y", "true", "1"])
        df["return_status"] = np.where(yes, "Returned", "Not Returned")
    log.append("Standardised category/segment/country/region/payment/priority/return labels")

    # names to title case
    for col in ["customer_name", "city", "sales_rep", "product_name"]:
        if col in df:
            df[col] = df[col].astype("string").str.title()

    # flag (do not change) suspicious dates
    if "order_date" in df and "ship_date" in df:
        bad = int((df["ship_date"] < df["order_date"]).sum())
        if bad:
            log.append(f"Warning: {bad} rows have a ship date before the order date (kept as is)")

    # duplicates
    before = len(df)
    df = df.drop_duplicates()
    if before - len(df):
        log.append(f"Removed {before - len(df)} duplicate rows")
    return df.reset_index(drop=True), log