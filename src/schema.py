import pandas as pd


def build_schema(df, table_name="data"):
    """Describe the table in text so the AI knows the exact columns and values."""
    lines = [f"Table name: {table_name} ({len(df):,} rows)", "Columns:"]
    for col in df.columns:
        s = df[col]
        if pd.api.types.is_datetime64_any_dtype(s):
            info = f"date, from {s.min().date()} to {s.max().date()}"
        elif pd.api.types.is_numeric_dtype(s):
            info = f"number, min {float(s.min()):.2f}, max {float(s.max()):.2f}"
        else:
            values = s.dropna().unique()
            if len(values) <= 15:
                info = "text, values: " + ", ".join(map(str, values))
            else:
                info = "text, examples: " + ", ".join(map(str, values[:3]))
        lines.append(f"- {col}: {info}")
    return "\n".join(lines)