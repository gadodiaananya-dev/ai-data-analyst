import pandas as pd


def dataset_summary(df):
    return {
        "rows": len(df),
        "columns": df.shape[1],
        "duplicate_rows": int(df.duplicated().sum()),
        "missing_cells": int(df.isna().sum().sum()),
    }


def profile_columns(df):
    """Per-column report: type, missing values, unique count, samples."""
    rows = []
    for col in df.columns:
        s = df[col]
        rows.append({
            "column": col,
            "type": str(s.dtype),
            "missing": int(s.isna().sum()),
            "missing_%": round(s.isna().mean() * 100, 2),
            "unique": int(s.nunique()),
            "sample_values": ", ".join(map(str, s.dropna().unique()[:3])),
        })
    return pd.DataFrame(rows)