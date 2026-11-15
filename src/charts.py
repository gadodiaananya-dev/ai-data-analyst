import datetime as dt
import pandas as pd
import plotly.express as px

TIME_WORDS = ("date", "month", "year", "quarter", "week", "day")
TIME_SUFFIXES = ("year", "month", "quarter", "week")


def _is_time_col(df, col):
    s = df[col]
    name = col.lower()
    if pd.api.types.is_datetime64_any_dtype(s):
        return True
    if pd.api.types.is_numeric_dtype(s):
        return name.endswith(TIME_SUFFIXES)      # e.g. order_year (not avg_days)
    if any(w in name for w in TIME_WORDS):
        return True
    first = s.dropna()
    return len(first) > 0 and isinstance(first.iloc[0], (dt.date, dt.datetime))


def auto_chart(df):
    """Pick a sensible chart for a result table. Returns a Plotly figure or None."""
    if df is None or len(df) < 2 or len(df.columns) < 2:
        return None

    nums = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    times = [c for c in df.columns if _is_time_col(df, c)]
    cats = [c for c in df.columns if c not in nums and c not in times]

    fig = None
    # 1) trend over time -> line chart
    if times:
        x = times[0]
        ys = [c for c in nums if c != x]
        if ys:
            d = df.sort_values(x)
            color = cats[0] if cats and len(ys) == 1 else None
            fig = px.line(d, x=x, y=ys[0] if color else ys, color=color, markers=True)

    # 2) category vs number -> bar chart
    elif cats and nums and len(df) <= 30:
        cat, val = cats[0], nums[0]
        color = cats[1] if len(cats) > 1 else None
        d = df.sort_values(val, ascending=True)
        fig = px.bar(d, x=val, y=cat, orientation="h", color=color,
                     barmode="group" if color else "relative")

    # 3) two numbers -> scatter
    elif len(nums) >= 2 and len(df) <= 3000:
        fig = px.scatter(df, x=nums[0], y=nums[1])

    if fig is not None:
        fig.update_layout(height=420, margin=dict(l=10, r=10, t=30, b=10))
    return fig