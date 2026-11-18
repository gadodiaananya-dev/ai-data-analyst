"""
Accuracy test for the AI Data Analyst.

Run:   python evaluate.py
Opts:  --data data/sample_sales.csv   --limit 10   --sleep 4   --fresh
       --questions tests/eval_unseen.json   --tag unseen
Output: results/eval_results.csv and results/eval_report.md
        (with --tag unseen: results/eval_results_unseen.csv and eval_report_unseen.md)
"""
import argparse
import json
import math
import time
from pathlib import Path

import duckdb
import pandas as pd

from src.cleaner import clean_dataset
from src.schema import build_schema
from src.llm_engine import answer_question

QUESTIONS_FILE = Path("tests/eval_questions.json")
RESULTS_DIR = Path("results")


# ---------- comparing results ----------
def _norm(series):
    """Turn a column into a sorted list so row order and text case don't matter."""
    nums = pd.to_numeric(series, errors="coerce")
    if nums.notna().all():
        return sorted(float(x) for x in nums)
    return sorted(str(x).strip().lower() for x in series)


def _same(a, b):
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if isinstance(x, float) or isinstance(y, float):
            if not (isinstance(x, float) and isinstance(y, float)
                    and math.isclose(x, y, rel_tol=1e-2, abs_tol=0.05)):
                return False
        elif x != y:
            return False
    return True


def results_match(gold, pred):
    """
    Correct if every column of the gold result appears (same values) in the
    prediction. Extra columns, column names, row order and NULL rows are ignored.
    """
    gold, pred = gold.dropna(), pred.dropna()
    if len(gold) != len(pred) or len(gold) == 0:
        return False
    pred_cols = [_norm(pred[c]) for c in pred.columns]
    return all(any(_same(_norm(gold[g]), p) for p in pred_cols) for g in gold.columns)


# ---------- running ----------
def load_data(path):
    raw = pd.read_csv(path, encoding="utf-8-sig")
    clean, _ = clean_dataset(raw)
    con = duckdb.connect(":memory:")
    con.register("v", clean)
    con.execute("CREATE TABLE data AS SELECT * FROM v")
    return clean, con


def run_one(q, schema, con):
    start = time.time()
    try:
        r = answer_question(q["question"], schema, con)
    except Exception as e:                       # network / quota problem, not a wrong answer
        return {"status": "api_error", "sql": "", "attempts": 0,
                "latency": round(time.time() - start, 1), "note": str(e)[:150]}
    latency = round(time.time() - start, 1)

    if q["type"] == "refuse":
        ok = r["error"] is not None and r["df"] is None
        note = "" if ok else "should have refused"
    else:
        gold = con.execute(q["gold_sql"]).df()
        if r["df"] is None:
            ok, note = False, f"error: {str(r['error'])[:120]}"
        else:
            ok = results_match(gold, r["df"])
            note = "" if ok else "wrong result"
    return {"status": "pass" if ok else "fail", "sql": r["sql"] or "",
            "attempts": r["attempts"], "latency": latency, "note": note}


def write_report(res, questions, report_file):
    scored = res[res["status"].isin(["pass", "fail"])]
    ans = scored[scored["type"] == "answer"]
    ref = scored[scored["type"] == "refuse"]
    lines = ["# Evaluation report", ""]
    if len(scored):
        lines.append(f"- **Overall accuracy:** {scored['status'].eq('pass').mean():.1%} "
                     f"({scored['status'].eq('pass').sum()}/{len(scored)} questions)")
    if len(ans):
        lines.append(f"- **Query accuracy (answerable questions):** "
                     f"{ans['status'].eq('pass').mean():.1%} ({ans['status'].eq('pass').sum()}/{len(ans)})")
        lines.append(f"- **Needed auto-fix retry:** {(ans['attempts'] > 1).mean():.1%}")
    if len(ref):
        lines.append(f"- **Safety (unsafe / unanswerable refused):** "
                     f"{ref['status'].eq('pass').mean():.1%} ({ref['status'].eq('pass').sum()}/{len(ref)})")
    lines.append(f"- **Average response time:** {scored['latency'].mean():.1f}s")
    lines += ["", "## Accuracy by difficulty", "", "| Difficulty | Passed | Total | Accuracy |", "|---|---|---|---|"]
    for d, g in scored.groupby("difficulty"):
        lines.append(f"| {d} | {g['status'].eq('pass').sum()} | {len(g)} | {g['status'].eq('pass').mean():.0%} |")
    fails = scored[scored["status"] == "fail"]
    if len(fails):
        gold = {q["id"]: q.get("gold_sql") for q in questions}
        lines += ["", "## Failed questions", ""]
        for _, r in fails.iterrows():
            lines += [f"**{r['id']}. {r['question']}** ({r['note']})", "",
                      f"- Model SQL: `{r['sql']}`", f"- Correct SQL: `{gold[r['id']]}`", ""]
    skipped = res[res["status"] == "api_error"]
    if len(skipped):
        lines += ["", f"_{len(skipped)} questions were skipped because of API errors. Run the script again._"]
    report_file.write_text("\n".join(lines), encoding="utf-8")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/sample_sales.csv")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--sleep", type=float, default=4.0, help="seconds between questions (free-tier limits)")
    ap.add_argument("--fresh", action="store_true", help="ignore saved results and start over")
    ap.add_argument("--questions", default=str(QUESTIONS_FILE), help="path to the questions JSON file")
    ap.add_argument("--tag", default="", help="name added to the output files, e.g. unseen")
    args = ap.parse_args()

    RESULTS_DIR.mkdir(exist_ok=True)
    suffix = f"_{args.tag}" if args.tag else ""
    out_file = RESULTS_DIR / f"eval_results{suffix}.csv"
    report_file = RESULTS_DIR / f"eval_report{suffix}.md"
    questions = json.loads(Path(args.questions).read_text(encoding="utf-8"))
    if args.limit:
        questions = questions[: args.limit]

    df, con = load_data(args.data)
    schema = build_schema(df)

    done = pd.DataFrame()
    if out_file.exists() and not args.fresh:
        done = pd.read_csv(out_file)
        done = done[done["status"].isin(["pass", "fail"])]      # re-run API errors
    finished = set(done["id"]) if len(done) else set()
    rows = done.to_dict("records") if len(done) else []

    for q in questions:
        if q["id"] in finished:
            continue
        r = run_one(q, schema, con)
        rows.append({"id": q["id"], "difficulty": q["difficulty"], "type": q["type"],
                     "question": q["question"], **r})
        pd.DataFrame(rows).to_csv(out_file, index=False)        # save after every question
        print(f"[{q['id']:>2}/{len(questions)}] {r['status'].upper():9} {q['question'][:60]}")
        time.sleep(args.sleep)

    res = pd.DataFrame(rows).sort_values("id")
    print("\n" + write_report(res, questions, report_file))


if __name__ == "__main__":
    main()