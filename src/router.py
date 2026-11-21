import re

# Questions that need statistics or modelling, which plain SQL cannot do well.
PYTHON_PATTERNS = [
    r"forecast", r"predict", r"projection", r"next \d+ (day|week|month|quarter|year)",
    r"next (week|month|quarter|year)", r"correlat", r"relationship between",
    r"outlier", r"anomal", r"unusual", r"cluster", r"segment .* into \d", r"regression",
    r"standard deviation", r"histogram", r"distribution", r"moving average",
    r"rolling", r"seasonal", r"statistically", r"significan",
]


def choose_mode(question, preference="Auto"):
    """Return 'sql' or 'python'."""
    if preference == "SQL only":
        return "sql"
    if preference == "Python only":
        return "python"
    q = question.lower()
    return "python" if any(re.search(p, q) for p in PYTHON_PATTERNS) else "sql"