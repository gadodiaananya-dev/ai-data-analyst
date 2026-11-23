from pathlib import Path

import streamlit as st
from src.data_loader import load_file, create_connection
from src.profiler import dataset_summary, profile_columns
from src.schema import build_schema
from src.llm_engine import answer_question, summarize_result
from src.python_engine import answer_with_python
from src.router import choose_mode
from src.charts import auto_chart
from src.export import to_excel_bytes
from src.dashboard import make_dashboard

DEMO_PATH = Path("data/demo_sales.csv")

st.set_page_config(page_title="AI Data Analyst", page_icon="📊", layout="wide")
st.title("📊 AI Data Analyst Assistant")
st.caption("Upload a dataset and ask questions in plain English.  ·  ⚠️ This demo uses a free AI API, so please do not upload private data.")

uploaded = st.file_uploader("Upload CSV or Excel", type=["csv", "xlsx", "xls"])

# no upload yet: offer a built-in synthetic dataset so anyone can try the app
if uploaded is None and DEMO_PATH.exists():
    if st.button("▶️ Try it with the demo dataset (synthetic, messy sales data)"):
        st.session_state["use_demo"] = True
if uploaded is not None:
    st.session_state["use_demo"] = False
use_demo = uploaded is None and DEMO_PATH.exists() and st.session_state.get("use_demo", False)


def render_turn(turn, idx):
    """Show one answer: summary, method, chart, table, download, code."""
    is_python = turn.get("mode") == "python"
    st.caption("🐍 Python analysis" if is_python else "🗄️ SQL query")

    if turn.get("error"):
        st.error(turn["error"])
    else:
        if turn.get("summary"):
            st.markdown(turn["summary"])
        if turn.get("notes"):
            st.caption(f"Method: {turn['notes']}")
        if turn.get("fig") is not None:
            st.plotly_chart(turn["fig"], width="stretch", key=f"chart_{idx}")
        if turn["df"] is None or turn["df"].empty:
            st.info("No rows to list: nothing matched. For an outlier or filter question, "
                    "this means none were found.")
        else:
            st.dataframe(turn["df"], width="stretch")
            st.download_button(
                "⬇️ Download as Excel",
                data=to_excel_bytes(turn["df"], turn["question"], turn.get("sql") or turn.get("code")),
                file_name=f"result_{idx + 1}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"download_{idx}",
            )

    code = turn.get("code") if is_python else turn.get("sql")
    if code:
        with st.expander("View generated Python code" if is_python else "View generated SQL"):
            st.code(code, language="python" if is_python else "sql")
            if turn.get("attempts", 1) > 1:
                st.caption(f"Fixed automatically after {turn['attempts']} attempts.")


def render_dashboard(d):
    """Show the dashboard as one picture (KPI tiles on top, charts below)."""
    st.plotly_chart(
        d["figure"], width="stretch", key="dashboard_figure",
        config={"displaylogo": False,
                "toImageButtonOptions": {"format": "png", "filename": "dashboard", "scale": 2}},
    )
    st.caption("Tip: hover over the dashboard and click the camera icon to save it as an image, "
               "or the expand icon to view it full screen.")
    if d["problems"]:
        st.caption(f"{len(d['problems'])} panel(s) could not be built and were skipped.")


def read_source():
    """Return (df, clean_log, name, size) from the upload or from the demo file."""
    if uploaded is not None:
        df, log = load_file(uploaded)
        return df, log, uploaded.name, uploaded.size
    with open(DEMO_PATH, "rb") as f:
        df, log = load_file(f)
    return df, log, DEMO_PATH.name, DEMO_PATH.stat().st_size


if uploaded is not None or use_demo:
    try:
        df, clean_log, source_name, source_size = read_source()
    except Exception as e:
        st.error(f"Could not read file: {e}")
        st.stop()

    if use_demo:
        st.info("Using the built-in demo dataset. Upload your own file above to switch.")

    con = create_connection(df)
    schema = build_schema(df)

    # start a fresh chat when a different file is used
    file_key = f"{source_name}-{source_size}"
    if st.session_state.get("file_key") != file_key:
        st.session_state["file_key"] = file_key
        st.session_state["chat"] = []
        st.session_state["dashboard"] = None

    with st.sidebar:
        st.header("Dashboard")
        if st.button("📊 Generate dashboard", width="stretch"):
            with st.spinner("Building your dashboard..."):
                try:
                    st.session_state["dashboard"] = make_dashboard(schema, con)
                except Exception:
                    st.session_state["dashboard"] = None
                    st.error("Could not build a dashboard right now. Please try again in a minute.")
        if st.session_state.get("dashboard") and st.button("Hide dashboard", width="stretch"):
            st.session_state["dashboard"] = None
            st.rerun()
        st.divider()
        st.header("Settings")
        st.radio("Analysis mode", ["Auto", "SQL only", "Python only"], key="mode_pref")
        st.caption("Auto: forecasts, correlations, outliers and clustering use Python. Everything else uses SQL.")
        if st.button("🗑️ Clear chat"):
            st.session_state["chat"] = []
            st.rerun()
        st.divider()
        st.caption("SQL examples: 'Total sales by region', then 'now only for 2023'.")
        st.caption("Python examples: 'Forecast the next 3 months of sales', 'Is discount correlated with profit?'")

    if st.session_state.get("dashboard"):
        render_dashboard(st.session_state["dashboard"])
        st.divider()

    with st.expander("🧹 Cleaning report"):
        for item in clean_log:
            st.write("•", item)

    with st.expander("📋 Dataset overview and column profile"):
        summary = dataset_summary(df)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Rows", f"{summary['rows']:,}")
        c2.metric("Columns", summary["columns"])
        c3.metric("Duplicate rows", summary["duplicate_rows"])
        c4.metric("Missing cells", summary["missing_cells"])
        st.dataframe(df.head(20), width="stretch")
        st.dataframe(profile_columns(df), width="stretch")

    st.subheader("💬 Ask your data")

    # show the conversation so far
    for i, turn in enumerate(st.session_state["chat"]):
        with st.chat_message("user"):
            st.write(turn["question"])
        with st.chat_message("assistant"):
            render_turn(turn, i)

    question = st.chat_input("Ask a question about your data...")

    if question:
        with st.chat_message("user"):
            st.write(question)

        mode = choose_mode(question, st.session_state.get("mode_pref", "Auto"))
        history = [t for t in st.session_state["chat"] if t.get("sql") and not t.get("error")]

        with st.chat_message("assistant"):
            with st.spinner("Analysing with Python..." if mode == "python" else "Thinking..."):
                try:
                    if mode == "python":
                        result = answer_with_python(question, schema, df)
                        result["sql"] = None
                        fig = result.get("fig")
                        if fig is None and not result["error"]:
                            fig = auto_chart(result["df"])
                    else:
                        result = answer_question(question, schema, con, history=history)
                        fig = None if result["error"] else auto_chart(result["df"])
                except Exception:
                    st.error("The AI service is busy right now. Please try again in a minute.")
                    st.stop()
                text = None if result["error"] else summarize_result(question, result["df"])

        result["mode"] = mode
        st.session_state["chat"].append(
            {"question": question, **result, "fig": fig, "summary": text}
        )
        st.rerun()
else:
    st.info("Upload a file to get started, or try the demo dataset.")