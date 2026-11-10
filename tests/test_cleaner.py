import numpy as np
import pandas as pd

from src.cleaner import clean_dataset


def make_messy():
    return pd.DataFrame({
        "Order Date": ["2021/02/05", "17/09/2021", "Sep 28, 2022", "2021/02/05"],
        "Sales": ["$1,200.50", "USD 59.04", "missing", "$1,200.50"],
        "Quantity": ["five", "999", "-3", "five"],
        "Discount": ["10%", "ten percent", "150%", "10%"],
        "Customer Rating": ["4 stars", "10", "3", "4 stars"],
        "Category": ["Furnitre", "Ofice Supplies", "tech", "Furnitre"],
        "Region": ["east", "W", "South", "east"],
        "Unnamed: 9": [np.nan, np.nan, np.nan, np.nan],
    })


def test_column_names_become_sql_friendly():
    df, _ = clean_dataset(make_messy())
    assert "order_date" in df.columns
    assert "customer_rating" in df.columns


def test_empty_columns_are_dropped():
    df, log = clean_dataset(make_messy())
    assert not any(c.startswith("unnamed") for c in df.columns)
    assert any("Dropped" in item for item in log)


def test_money_text_becomes_numbers():
    df, _ = clean_dataset(make_messy())
    assert df["sales"].iloc[0] == 1200.50
    assert df["sales"].iloc[1] == 59.04
    assert pd.isna(df["sales"].iloc[2])            # "missing" becomes a real null


def test_word_numbers_are_converted():
    df, _ = clean_dataset(make_messy())
    assert df["quantity"].iloc[0] == 5


def test_impossible_values_become_null():
    df, _ = clean_dataset(make_messy())
    assert pd.isna(df["quantity"].iloc[1])         # 999
    assert pd.isna(df["quantity"].iloc[2])         # -3
    assert pd.isna(df["discount"].iloc[2])         # 150%
    assert pd.isna(df["customer_rating"].iloc[1])  # 10


def test_discount_text_becomes_fraction():
    df, _ = clean_dataset(make_messy())
    assert df["discount"].iloc[0] == 0.10
    assert df["discount"].iloc[1] == 0.10


def test_mixed_date_formats_are_parsed():
    df, _ = clean_dataset(make_messy())
    assert pd.api.types.is_datetime64_any_dtype(df["order_date"])
    assert df["order_date"].notna().all()


def test_category_typos_are_fixed():
    df, _ = clean_dataset(make_messy())
    assert set(df["category"]) == {"Furniture", "Office Supplies", "Technology"}


def test_region_codes_are_standardised():
    df, _ = clean_dataset(make_messy())
    assert set(df["region"]) == {"East", "West", "South"}


def test_duplicate_rows_are_removed():
    df, log = clean_dataset(make_messy())
    assert len(df) == 3
    assert any("duplicate" in item.lower() for item in log)


def test_year_first_dates_are_not_day_month_swapped():
    raw = pd.DataFrame({"Row ID": [1, 2, 3], "Order Date": ["2024-05-06", "2024/05/06", "2024-12-04"]})
    df, _ = clean_dataset(raw)
    assert [d.strftime("%Y-%m-%d") for d in df["order_date"]] == ["2024-05-06", "2024-05-06", "2024-12-04"]


def test_day_first_and_text_dates():
    raw = pd.DataFrame({"Row ID": [1, 2, 3], "Order Date": ["20/05/2024", "06.05.2024", "May 06, 2024"]})
    df, _ = clean_dataset(raw)
    assert [d.strftime("%Y-%m-%d") for d in df["order_date"]] == ["2024-05-20", "2024-05-06", "2024-05-06"]


def test_unclear_dates_follow_the_style_of_the_clear_ones():
    # 05-31-2024 can only be month-first, so 03-10-2023 in the same column is 10 March
    raw = pd.DataFrame({"Row ID": [1, 2], "Order Date": ["05-31-2024", "03-10-2023"]})
    df, _ = clean_dataset(raw)
    assert df["order_date"].iloc[1].strftime("%Y-%m-%d") == "2023-03-10"