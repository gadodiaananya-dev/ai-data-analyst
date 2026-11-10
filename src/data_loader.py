import pandas as pd
import duckdb
from src.cleaner import clean_dataset


def load_file(uploaded_file):
    """Read a CSV or Excel file, clean it, and return (clean_df, log)."""
    name = uploaded_file.name.lower()
    if name.endswith(".csv"):
        df = pd.read_csv(uploaded_file, encoding="utf-8-sig")
    elif name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(uploaded_file)
    else:
        raise ValueError("Only CSV and Excel files are supported.")
    return clean_dataset(df)


def create_connection(df, table_name="data"):
    """Load the DataFrame into an in-memory DuckDB database."""
    con = duckdb.connect(database=":memory:")
    con.register("df_view", df)
    con.execute(f"CREATE TABLE {table_name} AS SELECT * FROM df_view")
    return con