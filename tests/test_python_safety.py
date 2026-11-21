import pytest

from src.python_safety import check_python


def test_normal_analysis_code_is_allowed():
    code = (
        "from sklearn.linear_model import LinearRegression\n"
        "d = df.dropna(subset=['sales']).rename(columns={'sales': 's'})\n"
        "result = d.head()\n"
    )
    assert check_python(code)[0] is True


@pytest.mark.parametrize("code", [
    "import os\nresult = 1",
    "import subprocess\nresult = 1",
    "from os import path\nresult = 1",
    "result = open('secrets.txt').read()",
    "result = eval('1 + 1')",
    "exec('x = 1')\nresult = 1",
    "result = ().__class__.__bases__",
    "df.to_csv('out.csv')\nresult = df",
    "result = pd.read_csv('a.csv')",
    "pd.io.common.os.system('echo hi')\nresult = df",
    "result = np.load('x.npy')",
    "import plotly.io as pio\nresult = df",
    "result = getattr(df, 'head')()",
    "result = df.query('sales > 1')",
    "",
])
def test_dangerous_code_is_blocked(code):
    assert check_python(code)[0] is False


def test_syntax_errors_are_reported_not_crashed():
    ok, reason = check_python("result = (")
    assert ok is False and "Syntax" in reason