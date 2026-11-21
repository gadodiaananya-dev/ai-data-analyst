import re
from google.genai import types
from src.llm_engine import _generate
from src.python_safety import check_python
from src.python_runner import run_python_code

PYTHON_SYSTEM_PROMPT = """You are an expert Python data analyst. Write Python code that answers the
user's question about a pandas DataFrame named `df`.

Environment:
- `df` is already loaded and cleaned. `pd`, `np`, `px` (plotly.express) and `go` (plotly.graph_objects) are already imported.
- You may also import from sklearn (e.g. from sklearn.linear_model import LinearRegression) and scipy (e.g. from scipy import stats).
- There is no file, network or system access. Do not use open(), eval(), exec(), os, sys, df.query() or df.plot().

Rules:
- Use only the columns listed in the schema. Date columns are datetime64. Drop or fill NaN/NaT values before modelling or resampling.
- Put the final answer in a pandas DataFrame named `result` (at most 200 rows, clear column names, values rounded to 2 decimals).
- If nothing qualifies (for example no outliers exist), do not return an empty DataFrame. Return a one-row DataFrame with a `count` of 0 and a short `message` column.
- Optionally create a Plotly figure named `fig` that shows the result.
- Set a string `notes` with 1-2 sentences describing the method and any caveat (for example: the forecast is a simple trend estimate).
- For forecasts: drop rows with a missing date, aggregate by month (df.set_index('order_date').resample('MS')), fit a simple model (linear trend or sklearn), and return history and forecast together with a column that marks which rows are forecast.
- Output ONLY Python code. No explanations, no markdown.
"""


def _extract_code(text):
    text = text.strip()
    match = re.search(r"```(?:python)?\s*(.*?)```", text, flags=re.S | re.I)
    return (match.group(1) if match else text).strip()


def _ask(schema, messages):
    contents = [
        types.Content(
            role="model" if m["role"] == "assistant" else "user",
            parts=[types.Part(text=m["content"])],
        )
        for m in messages
    ]
    return _extract_code(_generate(contents, f"{PYTHON_SYSTEM_PROMPT}\nDATAFRAME SCHEMA:\n{schema}"))


def answer_with_python(question, schema, df, max_retries=2):
    """
    Returns {"code", "df", "fig", "notes", "error", "attempts"}.
    If the code is rejected or fails, the reason is sent back to the AI so it can fix it.
    """
    messages = [{"role": "user", "content": question}]
    code, last_error = "", None

    for attempt in range(1, max_retries + 2):
        code = _ask(schema, messages)

        safe, reason = check_python(code)
        if not safe:
            last_error = f"Blocked for safety: {reason}"
            messages += [
                {"role": "assistant", "content": code},
                {"role": "user", "content": f"The safety checker rejected that code ({reason}). "
                                            "Rewrite it without that, using only pandas, numpy, sklearn, scipy and plotly. "
                                            "Return Python code only."},
            ]
            continue

        out = run_python_code(df, code)
        if out["ok"]:
            return {"code": code, "df": out["df"], "fig": out["fig"], "notes": out["notes"],
                    "error": None, "attempts": attempt}

        last_error = out["error"]
        messages += [
            {"role": "assistant", "content": code},
            {"role": "user", "content": f"That code failed with this error:\n{last_error}\nReturn corrected Python code only."},
        ]

    return {"code": code, "df": None, "fig": None, "notes": "", "error": last_error,
            "attempts": max_retries + 1}