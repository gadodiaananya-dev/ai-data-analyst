import json
import math
import re

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from src.sql_safety import check_sql

MAX_KPIS, MAX_CHARTS = 4, 6
KPI_FORMATS = {"money", "number", "percent", "decimal"}
CHART_KINDS = {"bar", "line", "pie", "table"}

DASHBOARD_PROMPT = """You design a quick business dashboard for the table described below, using DuckDB SQL.
Return ONLY a JSON object, with no markdown, in exactly this shape:
{
  "title": "short dashboard title",
  "kpis": [{"label": "Total sales", "sql": "SELECT ...", "format": "money"}],
  "charts": [{"title": "Sales by region", "sql": "SELECT ...", "kind": "bar"}]
}
Rules:
- Exactly 4 kpis and 5 or 6 charts. Pick measures that matter for this data (money, volume, rates, ratings).
- "format" is one of: money, number, percent, decimal. A percent kpi must return a number from 0 to 100.
- Every kpi query returns ONE row and ONE column (a single number).
- Every chart query returns exactly two columns: the label first, the number second. Use ORDER BY, and LIMIT 10 for rankings.
- "kind" is one of: bar (rankings and comparisons), line (trend over time, with the label like strftime(date_column, '%Y-%m') sorted ascending), pie (at most 6 slices), table.
- Include at least one trend over time (line) if the table has a date column, and at least two category comparisons.
- Exclude rows where the label column is NULL.
- Use ONLY the table "data" and its exact column names. Only SELECT queries. Round to 2 decimals.
"""


# ---------- turning the AI reply into a plan ----------
def parse_plan(text):
    """Extract the JSON object from the AI reply (it may be wrapped in a code fence)."""
    text = (text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.S | re.I)
    if fenced:
        text = fenced.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("No JSON object found in the reply.")
    return json.loads(text[start:end + 1])


def _clean_item(item, name_key, kind_key, allowed, default):
    if not isinstance(item, dict):
        return None, "not an object"
    name, sql = item.get(name_key), item.get("sql")
    if not isinstance(name, str) or not name.strip():
        return None, "missing name"
    if not isinstance(sql, str) or not sql.strip():
        return None, "missing SQL"
    safe, reason = check_sql(sql)
    if not safe:
        return None, f"blocked: {reason}"
    kind = item.get(kind_key)
    return {name_key: name.strip()[:60], "sql": sql.strip(),
            kind_key: kind if kind in allowed else default}, None


def validate_plan(plan):
    """Keep only well-formed, read-only panels. Returns (clean_plan, problems)."""
    problems = []
    if not isinstance(plan, dict):
        return {"title": "Dashboard", "kpis": [], "charts": []}, ["The plan was not a JSON object."]

    kpis, charts = [], []
    for item in (plan.get("kpis") or [])[:MAX_KPIS]:
        clean, why = _clean_item(item, "label", "format", KPI_FORMATS, "number")
        if clean:
            kpis.append(clean)
        else:
            problems.append(f"A KPI was skipped ({why}).")
    for item in (plan.get("charts") or [])[:MAX_CHARTS]:
        clean, why = _clean_item(item, "title", "kind", CHART_KINDS, "bar")
        if clean:
            charts.append(clean)
        else:
            problems.append(f"A chart was skipped ({why}).")
    return {"title": str(plan.get("title") or "Dashboard")[:80], "kpis": kpis, "charts": charts}, problems


# ---------- drawing ----------
def format_kpi(value, fmt):
    sign = "-" if value < 0 else ""
    v = abs(value)
    if fmt == "money":
        return f"{sign}${v:,.0f}"
    if fmt == "percent":
        return f"{sign}{v:.1f}%"
    if fmt == "decimal":
        return f"{sign}{v:,.2f}"
    return f"{sign}{v:,.0f}"


PALETTE = ["#4C78A8", "#F58518", "#54A24B", "#E45756", "#72B7B2", "#B279A2"]
COLS = 12                      # the grid is 12 columns wide: 4 KPI tiles of 3, or 3 charts of 4
KPI_ROW_PX, CHART_ROW_PX = 110, 250


def _short(label, n=18):
    s = str(label)
    return s if len(s) <= n else s[: n - 1] + "…"


def _number_style(fmt):
    style = {"money": {"prefix": "$", "valueformat": ",.0f"},
             "percent": {"suffix": "%", "valueformat": ",.1f"},
             "decimal": {"valueformat": ",.2f"}}.get(fmt, {"valueformat": ",.0f"})
    return {**style, "font": {"size": 34}}


def _chart_data(df):
    """Label and number columns of a result, cleaned."""
    x, y = df.columns[0], df.columns[1]
    d = df[[x, y]].copy()
    d[y] = pd.to_numeric(d[y], errors="coerce")
    d = d.dropna(subset=[y])
    return d, x, y


def _kind_for(kind, n_rows):
    """Tables become bars; pies and lines need enough rows, otherwise use bars."""
    if kind == "pie" and 2 <= n_rows <= 8:
        return "pie"
    if kind == "line" and n_rows >= 2:
        return "line"
    return "bar"


def _trace(df, kind, color):
    d, x, y = _chart_data(df)
    if d.empty:
        return None, "bar"
    kind = _kind_for(kind, len(d))
    if kind == "pie":
        return go.Pie(labels=[_short(v) for v in d[x]], values=d[y], hole=0.45, sort=False,
                      textinfo="percent", textfont_size=11, showlegend=False,
                      marker=dict(colors=PALETTE)), kind
    if kind == "line":
        d = d.sort_values(x)
        return go.Scatter(x=d[x], y=d[y], mode="lines+markers", line=dict(color=color, width=2),
                          marker=dict(size=5), showlegend=False), kind
    d = d.sort_values(y, ascending=True)
    return go.Bar(x=d[y], y=[_short(v) for v in d[x]], orientation="h",
                  marker_color=color, showlegend=False), kind


def compose_figure(title, kpis, charts):
    """
    The whole dashboard as ONE Plotly figure: KPI tiles on top, charts in a 3-column grid.
    One figure means one screen, and the Plotly toolbar can save it as a single image.
    """
    n_k, n_c = len(kpis), len(charts)
    chart_rows = math.ceil(n_c / 3)
    if n_k + n_c == 0:
        return None

    built = [_trace(c["df"], c["kind"], PALETTE[i % len(PALETTE)]) for i, c in enumerate(charts)]

    specs, heights = [], []
    k_span = COLS // n_k if n_k else 0
    if n_k:
        row = [None] * COLS
        for i in range(n_k):
            row[i * k_span] = {"type": "indicator", "colspan": k_span}
        specs.append(row)
        heights.append(KPI_ROW_PX)
    for r in range(chart_rows):
        row = [None] * COLS
        for j, (trace, kind) in enumerate(built[r * 3: r * 3 + 3]):
            row[j * 4] = {"type": "domain" if kind == "pie" else "xy", "colspan": 4}
        specs.append(row)
        heights.append(CHART_ROW_PX)

    titles = [""] * n_k + [c["title"] for c in charts]
    fig = make_subplots(rows=len(specs), cols=COLS, specs=specs, subplot_titles=titles,
                        row_heights=heights, vertical_spacing=0.13, horizontal_spacing=0.02)

    for i, k in enumerate(kpis):
        fig.add_trace(go.Indicator(mode="number", value=k["value"], number=_number_style(k["format"]),
                                   title={"text": k["label"], "font": {"size": 14}}),
                      row=1, col=i * k_span + 1)
    for i, (trace, kind) in enumerate(built):
        if trace is not None:
            fig.add_trace(trace, row=(1 if n_k else 0) + i // 3 + 1, col=(i % 3) * 4 + 1)

    fig.update_layout(title=dict(text=title, x=0, font=dict(size=20)), showlegend=False,
                      height=sum(heights) + 70, margin=dict(l=10, r=10, t=60, b=10))
    fig.update_xaxes(tickfont_size=10)
    fig.update_yaxes(tickfont_size=10, automargin=True)
    fig.update_annotations(font_size=13)
    return fig


def _single_number(df):
    if len(df) != 1 or df.shape[1] < 1:
        return None
    value = pd.to_numeric(df.iloc[0, 0], errors="coerce")
    return None if pd.isna(value) else float(value)


# ---------- building ----------
def build_dashboard(plan, con):
    """Run every panel's SQL. Panels that fail are skipped instead of breaking the page."""
    plan, problems = validate_plan(plan)
    kpis, charts = [], []

    for k in plan["kpis"]:
        try:
            df = con.execute(k["sql"]).df()
        except Exception as e:
            problems.append(f"KPI '{k['label']}' failed: {str(e)[:80]}")
            continue
        value = _single_number(df)
        if value is None:
            problems.append(f"KPI '{k['label']}' did not return a single number.")
            continue
        kpis.append({"label": k["label"], "value": value, "format": k["format"],
                     "text": format_kpi(value, k["format"]), "sql": k["sql"]})

    for c in plan["charts"]:
        try:
            df = con.execute(c["sql"]).df()
        except Exception as e:
            problems.append(f"Chart '{c['title']}' failed: {str(e)[:80]}")
            continue
        if len(df) == 0 or df.shape[1] < 2:
            problems.append(f"Chart '{c['title']}' returned no usable data.")
            continue
        charts.append({"title": c["title"], "kind": c["kind"], "df": df, "sql": c["sql"]})

    return {"title": plan["title"], "kpis": kpis, "charts": charts, "problems": problems,
            "figure": compose_figure(plan["title"], kpis, charts)}


def generate_plan(schema):
    """Ask the AI for a dashboard plan (imported here so tests need no API key)."""
    from google.genai import types
    from src.llm_engine import _generate

    contents = [types.Content(role="user", parts=[types.Part(text="Create the dashboard plan for this table.")])]
    text = _generate(contents, f"{DASHBOARD_PROMPT}\nTABLE SCHEMA:\n{schema}", 0)
    return parse_plan(text)


def make_dashboard(schema, con, plan_fn=None, attempts=2):
    """Generate a plan and build it. Tries again if too few panels work."""
    best = None
    for _ in range(attempts):
        try:
            plan = (plan_fn or generate_plan)(schema)
        except ValueError:                      # the reply was not valid JSON: try again
            continue
        result = build_dashboard(plan, con)
        size = len(result["kpis"]) + len(result["charts"])
        if best is None or size > len(best["kpis"]) + len(best["charts"]):
            best = result
        if len(result["kpis"]) >= 3 and len(result["charts"]) >= 4:
            break
    if best is None or not (best["kpis"] or best["charts"]):
        raise RuntimeError("Could not build a dashboard for this data.")
    return best