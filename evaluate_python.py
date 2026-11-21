"""
Accuracy test for Python mode (statistics, forecasts, clustering).

Run:   python evaluate_python.py
Opts:  --data data/sample_sales.csv   --sleep 4
Output: results/eval_results_python.csv and results/eval_report_python.md

Each question has a small trusted "gold_python" snippet that computes the expected
answer directly with pandas. The AI's answer is correct if it matches.
"""
import argparse
import json
import math
import time
from pathlib import Path

import numpy as np
import pandas as pd

from evaluate import load_data
from src.schema import build_schema
from src.python_engine import answer_with_python

QUESTIONS_FILE = Path("tests/eval_python.json")
RESULTS_DIR = Path("results")


def numeric_cells(df):
    values = []
    for col in df.columns:
        nums = pd.to_numeric(df[col], errors="coerce").dropna()
        values += [float(x) for x in nums]
    return values


def close(a, b):
    return math.isclose(a, b, rel_tol=1e-3, abs_tol=0.01)


def check_answer(kind, expected, result):
    """Return (passed, note)."""
    if result is None or len(result) == 0:
        return False, "empty result"

    if kind == "number":
        cells = numeric_cells(result)
        ok = any(close(c, float(expected)) for c in cells)
        return ok, "" if ok else f"expected about {float(expected):.4f}, not found in the result"

    if kind == "all_numbers":
        cells = numeric_cells(result)
        missing = [e for e in expected if not any(close(c, e) for c in cells)]
        return (not missing), "" if not missing else f"missing values: {missing[:3]}"

    if kind == "forecast_rows":
        marked = 0
        for _, row in result.iterrows():
            for col, val in row.items():
                if "forecast" in str(val).lower() or (
                        "forecast" in str(col).lower() and str(val).lower() in ("true", "1", "yes")):
                    marked += 1
                    break
        ok = marked == expected
        return ok, "" if ok else f"{marked} rows marked as forecast, expected {expected}"

    if kind == "three_groups":
        ok = len(result) == expected or any(result[c].nunique() == expected for c in result.columns)
        return ok, "" if ok else "could not find exactly 3 groups"

    return False, f"unknown check: {kind}"


def run_one(q, schema, df):
    env = {"df": df, "pd": pd, "np": np}
    exec(q["gold_python"], env)                       # trusted snippet written by us
    expected = env["expected"]

    start = time.time()
    try:
        r = answer_with_python(q["question"], schema, df)
    except Exception as e:                            # network / quota problem, not a wrong answer
        return {"status": "api_error", "attempts": 0, "latency": round(time.time() - start, 1),
                "note": str(e)[:150], "code": ""}
    latency = round(time.time() - start, 1)

    if r["df"] is None:
        return {"status": "fail", "attempts": r["attempts"], "latency": latency,
                "note": f"error: {str(r['error'])[:120]}", "code": r["code"]}
    ok, note = check_answer(q["check"], expected, r["df"])
    return {"status": "pass" if ok else "fail", "attempts": r["attempts"],
            "latency": latency, "note": note, "code": r["code"]}


def write_report(res, path):
    scored = res[res["status"].isin(["pass", "fail"])]
    lines = ["# Python mode evaluation report", ""]
    if len(scored):
        lines.append(f"- **Accuracy:** {scored['status'].eq('pass').mean():.1%} "
                     f"({scored['status'].eq('pass').sum()}/{len(scored)} questions)")
        lines.append(f"- **Needed auto-fix retry:** {(scored['attempts'] > 1).mean():.1%}")
        lines.append(f"- **Average response time:** {scored['latency'].mean():.1f}s")
        lines += ["", "## By difficulty", "", "| Difficulty | Passed | Total |", "|---|---|---|"]
        for d, g in scored.groupby("difficulty"):
            lines.append(f"| {d} | {g['status'].eq('pass').sum()} | {len(g)} |")
    fails = scored[scored["status"] == "fail"]
    if len(fails):
        lines += ["", "## Failed questions", ""]
        for _, r in fails.iterrows():
            lines += [f"**{r['id']}. {r['question']}** ({r['note']})", "", "```python", str(r["code"]), "```", ""]
    skipped = res[res["status"] == "api_error"]
    if len(skipped):
        lines += ["", f"_{len(skipped)} questions were skipped because of API errors. Run the script again._"]
    Path(path).write_text("\n".join(lines), encoding="utf-8")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/sample_sales.csv")
    ap.add_argument("--sleep", type=float, default=4.0)
    args = ap.parse_args()

    RESULTS_DIR.mkdir(exist_ok=True)
    questions = json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))
    df, _ = load_data(args.data)
    schema = build_schema(df)

    rows = []
    for q in questions:
        r = run_one(q, schema, df)
        rows.append({"id": q["id"], "difficulty": q["difficulty"], "question": q["question"], **r})
        pd.DataFrame(rows).to_csv(RESULTS_DIR / "eval_results_python.csv", index=False)
        print(f"[{q['id']}/{len(questions)}] {r['status'].upper():9} {q['question'][:60]}")
        time.sleep(args.sleep)

    print("\n" + write_report(pd.DataFrame(rows), RESULTS_DIR / "eval_report_python.md"))


if __name__ == "__main__":
    main()
