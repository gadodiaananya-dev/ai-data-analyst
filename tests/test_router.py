import json
from pathlib import Path

import pytest

from src.router import choose_mode


@pytest.mark.parametrize("question", [
    "Forecast the next 3 months of sales",
    "Is discount correlated with profit?",
    "Find unusual orders (outliers)",
    "Cluster customers into 3 groups",
    "Predict next year's profit",
])
def test_statistical_questions_go_to_python(question):
    assert choose_mode(question) == "python"


@pytest.mark.parametrize("question", [
    "Total sales by region",
    "Monthly sales trend",
    "Top 5 products by profit",
])
def test_normal_questions_go_to_sql(question):
    assert choose_mode(question) == "sql"


def test_user_preference_overrides_auto():
    assert choose_mode("Total sales by region", "Python only") == "python"
    assert choose_mode("Forecast sales", "SQL only") == "sql"


def test_every_benchmark_question_still_uses_sql():
    """Protects the SQL accuracy results: the router must never steal these questions."""
    folder = Path(__file__).parent
    for name in ("eval_questions.json", "eval_unseen.json"):
        for q in json.loads((folder / name).read_text(encoding="utf-8")):
            assert choose_mode(q["question"]) == "sql", q["question"]