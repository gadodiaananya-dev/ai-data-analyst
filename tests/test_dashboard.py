import duckdb
import pandas as pd
import pytest

from src.dashboard import (build_dashboard, compose_figure, format_kpi, make_dashboard,
                           parse_plan, validate_plan)


@pytest.fixture
def con():
    df = pd.DataFrame({
        "region": ["East", "West", "East", "South", None],
        "sales": [100.0, 250.0, 50.0, 75.0, 10.0],
        "order_date": pd.to_datetime(["2024-01-05", "2024-01-20", "2024-02-03", "2024-02-18", "2024-03-01"]),
    })
    connection = duckdb.connect(":memory:")
    connection.register("v", df)
    connection.execute("CREATE TABLE data AS SELECT * FROM v")
    return connection


GOOD_PLAN = {
    "title": "Sales overview",
    "kpis": [
        {"label": "Total sales", "sql": "SELECT SUM(sales) FROM data", "format": "money"},
        {"label": "Rows", "sql": "SELECT COUNT(*) FROM data", "format": "number"},
    ],
    "charts": [
        {"title": "Sales by region", "kind": "bar",
         "sql": "SELECT region, SUM(sales) FROM data WHERE region IS NOT NULL GROUP BY 1"},
        {"title": "Monthly sales", "kind": "line",
         "sql": "SELECT strftime(order_date, '%Y-%m') m, SUM(sales) FROM data GROUP BY 1 ORDER BY 1"},
        {"title": "Share by region", "kind": "pie",
         "sql": "SELECT region, SUM(sales) FROM data WHERE region IS NOT NULL GROUP BY 1"},
    ],
}


def test_parse_plan_handles_code_fences_and_extra_text():
    text = 'Here you go:\n```json\n{"title": "T", "kpis": [], "charts": []}\n```'
    assert parse_plan(text)["title"] == "T"


def test_parse_plan_rejects_text_without_json():
    with pytest.raises(ValueError):
        parse_plan("sorry, I cannot do that")


def test_validate_plan_drops_unsafe_and_malformed_panels():
    plan = {"title": "x",
            "kpis": [{"label": "Bad", "sql": "DROP TABLE data"}, {"label": "Ok", "sql": "SELECT 1"}, "junk"],
            "charts": [{"title": "Bad 2", "sql": "DELETE FROM data"}, {"title": "No sql"}]}
    clean, problems = validate_plan(plan)
    assert [k["label"] for k in clean["kpis"]] == ["Ok"]
    assert clean["charts"] == []
    assert len(problems) == 4


def test_validate_plan_limits_the_number_of_panels_and_fixes_unknown_types():
    plan = {"kpis": [{"label": f"k{i}", "sql": "SELECT 1", "format": "weird"} for i in range(10)],
            "charts": [{"title": f"c{i}", "sql": "SELECT 1, 2", "kind": "radar"} for i in range(10)]}
    clean, _ = validate_plan(plan)
    assert len(clean["kpis"]) == 4 and len(clean["charts"]) == 6
    assert clean["kpis"][0]["format"] == "number" and clean["charts"][0]["kind"] == "bar"


def test_build_dashboard_runs_real_queries(con):
    d = build_dashboard(GOOD_PLAN, con)
    assert [k["text"] for k in d["kpis"]] == ["$485", "5"]
    assert len(d["charts"]) == 3 and d["problems"] == []
    assert d["figure"] is not None


def test_a_failing_panel_is_skipped_not_fatal(con):
    plan = {"kpis": [{"label": "Good", "sql": "SELECT SUM(sales) FROM data", "format": "money"},
                     {"label": "Broken", "sql": "SELECT SUM(nonexistent) FROM data"},
                     {"label": "Many rows", "sql": "SELECT sales FROM data"}],
            "charts": [{"title": "One column", "sql": "SELECT region FROM data"}]}
    d = build_dashboard(plan, con)
    assert [k["label"] for k in d["kpis"]] == ["Good"]
    assert d["charts"] == []
    assert len(d["problems"]) == 3


@pytest.mark.parametrize("value, fmt, expected", [
    (1234567.8, "money", "$1,234,568"), (-50, "money", "-$50"), (12.345, "percent", "12.3%"),
    (3.14159, "decimal", "3.14"), (1500, "number", "1,500"),
])
def test_format_kpi(value, fmt, expected):
    assert format_kpi(value, fmt) == expected


def _chart(title, kind, n=4):
    return {"title": title, "kind": kind,
            "df": pd.DataFrame({"label": [f"item {i}" for i in range(n)], "value": [float(i + 1) for i in range(n)]})}


def _kpi(label, value=10.0, fmt="number"):
    return {"label": label, "value": value, "format": fmt, "text": str(value), "sql": "SELECT 1"}


def test_the_whole_dashboard_is_one_figure_with_the_right_trace_types():
    fig = compose_figure("T", [_kpi("A"), _kpi("B", fmt="money")],
                         [_chart("bars", "bar"), _chart("trend", "line"), _chart("share", "pie")])
    types = [tr.type for tr in fig.data]
    assert types == ["indicator", "indicator", "bar", "scatter", "pie"]
    assert fig.layout.height < 700                      # fits on one screen


def test_tables_become_bars_and_tiny_pies_become_bars():
    fig = compose_figure("T", [], [_chart("a", "table"), _chart("b", "pie", n=12), _chart("c", "line", n=1)])
    assert [tr.type for tr in fig.data] == ["bar", "bar", "bar"]


@pytest.mark.parametrize("n_kpis, n_charts", [(4, 6), (3, 4), (1, 1), (0, 6), (4, 0), (2, 5)])
def test_every_panel_count_builds_without_overlap(n_kpis, n_charts):
    kinds = ["bar", "line", "pie"]
    fig = compose_figure("T", [_kpi(f"k{i}") for i in range(n_kpis)],
                         [_chart(f"c{i}", kinds[i % 3]) for i in range(n_charts)])
    assert len(fig.data) == n_kpis + n_charts
    # panels must not overlap horizontally inside a row
    boxes = []
    for tr in fig.data:
        dom = tr.domain if tr.type in ("indicator", "pie") else fig.layout[tr.xaxis.replace("x", "xaxis")].domain
        y = tr.domain.y if tr.type in ("indicator", "pie") else fig.layout[tr.yaxis.replace("y", "yaxis")].domain
        boxes.append((tuple(dom.x if hasattr(dom, "x") else dom), tuple(y)))
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            (ax, ay), (bx, by) = boxes[i], boxes[j]
            same_row = abs(ay[0] - by[0]) < 1e-6
            if same_row:
                assert ax[1] <= bx[0] + 1e-9 or bx[1] <= ax[0] + 1e-9


def test_nothing_to_draw_returns_none():
    assert compose_figure("T", [], []) is None


def test_make_dashboard_retries_when_the_reply_is_not_json(con):
    replies = iter([ValueError("not json"), GOOD_PLAN])

    def fake_plan(schema):
        r = next(replies)
        if isinstance(r, Exception):
            raise r
        return r

    d = make_dashboard("schema", con, plan_fn=fake_plan)
    assert len(d["kpis"]) == 2 and len(d["charts"]) == 3


def test_make_dashboard_fails_clearly_when_nothing_works(con):
    with pytest.raises(RuntimeError):
        make_dashboard("schema", con, plan_fn=lambda s: {"kpis": [], "charts": []})