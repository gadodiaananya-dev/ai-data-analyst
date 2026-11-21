import json
import pickle
import subprocess
import sys
import tempfile
from io import StringIO
from pathlib import Path

import pandas as pd
import plotly.io as pio

ROOT = Path(__file__).resolve().parent.parent


def run_python_code(df, code, timeout=30):
    """
    Run code in a separate process with a time limit.
    Returns {"ok", "df", "fig", "notes"} or {"ok": False, "error"}.
    """
    with tempfile.TemporaryDirectory() as tmp:
        in_path, out_path = Path(tmp) / "in.pkl", Path(tmp) / "out.json"
        with open(in_path, "wb") as f:
            pickle.dump({"df": df, "code": code}, f)
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "src.sandbox_worker", str(in_path), str(out_path)],
                cwd=ROOT, timeout=timeout, capture_output=True, text=True,
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": f"The code took longer than {timeout} seconds and was stopped."}

        if not out_path.exists():
            return {"ok": False, "error": "The code crashed: " + (proc.stderr or "")[-300:]}
        out = json.loads(out_path.read_text(encoding="utf-8"))

    if not out["ok"]:
        return out
    result = pd.read_json(StringIO(out["df"]), orient="split", convert_dates=False)
    fig = pio.from_json(out["fig"]) if out.get("fig") else None
    return {"ok": True, "df": result, "fig": fig, "notes": out.get("notes", "")}