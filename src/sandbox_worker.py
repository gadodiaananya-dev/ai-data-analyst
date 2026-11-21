"""
Runs AI-written analysis code in a separate process.
Usage (called by python_runner.py): python -m src.sandbox_worker in.pkl out.json
"""
import builtins
import contextlib
import io
import json
import pickle
import sys
import traceback

ALLOWED_IMPORTS = (
    "pandas", "numpy", "scipy", "sklearn",
    "plotly.express", "plotly.graph_objects", "plotly.subplots",
    "math", "statistics", "datetime", "itertools", "collections",
)

SAFE_BUILTIN_NAMES = [
    "abs", "all", "any", "bool", "dict", "enumerate", "filter", "float", "int",
    "isinstance", "len", "list", "map", "max", "min", "range", "round", "set",
    "sorted", "str", "sum", "tuple", "zip", "print", "reversed", "pow", "divmod",
    "slice", "iter", "next", "repr", "format", "hasattr",
    "Exception", "ValueError", "TypeError", "KeyError", "IndexError", "ZeroDivisionError",
    "True", "False", "None",
]


def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    if level == 0 and any(name == m or name.startswith(m + ".") for m in ALLOWED_IMPORTS):
        return builtins.__import__(name, globals, locals, fromlist, level)
    raise ImportError(f"Import not allowed: {name}")


def main(in_path, out_path):
    with open(in_path, "rb") as f:
        payload = pickle.load(f)          # written by our own app, so it is trusted
    df, code = payload["df"], payload["code"]

    import numpy as np
    import pandas as pd
    import plotly.express as px
    import plotly.graph_objects as go

    safe_builtins = {n: getattr(builtins, n) for n in SAFE_BUILTIN_NAMES if hasattr(builtins, n)}
    safe_builtins["__import__"] = _safe_import
    env = {"__builtins__": safe_builtins, "df": df.copy(), "pd": pd, "np": np, "px": px, "go": go}

    out = {"ok": False, "error": "Unknown error"}
    buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(buffer):
            exec(compile(code, "<analysis>", "exec"), env)
        result = env.get("result")
        if result is None:
            raise ValueError("The code did not create a variable named `result`.")
        if isinstance(result, pd.Series):
            result = result.reset_index()
        elif not isinstance(result, pd.DataFrame):
            result = pd.DataFrame({"value": [result]}) if not isinstance(result, (list, dict)) else pd.DataFrame(result)
        result = result.head(1000).copy()
        for col in result.columns:           # dates as plain text, e.g. 2025-01-01
            if pd.api.types.is_datetime64_any_dtype(result[col]):
                result[col] = result[col].dt.strftime("%Y-%m-%d")

        fig = env.get("fig")
        fig_json = fig.to_json() if hasattr(fig, "to_json") else None
        notes = env.get("notes")
        out = {
            "ok": True,
            "df": result.to_json(orient="split", date_format="iso"),
            "fig": fig_json,
            "notes": notes if isinstance(notes, str) else "",
            "stdout": buffer.getvalue()[:2000],
        }
    except BaseException:
        out = {"ok": False, "error": "".join(traceback.format_exc().splitlines(True)[-6:])[-800:]}

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])