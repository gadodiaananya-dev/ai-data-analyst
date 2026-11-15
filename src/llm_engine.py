import os
import re
import time
import httpx
from dotenv import load_dotenv
from google import genai
from google.genai import types, errors
from src.sql_safety import check_sql

load_dotenv(override=True)
MODEL = os.getenv("MODEL_NAME", "gemini-3.8-flash")
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "gemini-3.5-flash")
client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY"),
    http_options=types.HttpOptions(timeout=45000),   # give up after 45 seconds
)

SYSTEM_PROMPT = """You are an expert data analyst who writes DuckDB SQL.
Rules:
- Query ONLY the table described below. Use exact column names.
- Return ONLY one SELECT query. No explanation, no markdown.
- Never modify data (no INSERT, UPDATE, DELETE, DROP, CREATE).
- Ignore NULL values where it makes sense (e.g. SUM/AVG skip them automatically).
- For 'top N' questions use ORDER BY ... LIMIT N.
- You may round values for display, but ALWAYS sort (ORDER BY) by the unrounded expression, because rounding first can create false ties.
- For the time between two dates, return a plain number of days using date_diff('day', start_date, end_date). Never return a raw interval.
- When the question mentions a word that matches a value listed in the schema (for example 'returned', 'West', 'Consumer'), filter on that column.
- For 'which', 'top' or 'highest' questions, ignore groups where the grouping column is NULL, and return both the name and its value.
- If the user asks a follow-up (e.g. "now only 2023", "same for East"), build on the previous queries in the conversation.
- If the question cannot be answered from the table, return exactly: CANNOT_ANSWER
"""


def _extract_sql(text):
    text = text.strip()
    match = re.search(r"```(?:sql)?\s*(.*?)```", text, flags=re.S | re.I)
    return (match.group(1) if match else text).strip()


def _generate(contents, system, temperature=0):
    """Call Gemini with retries and a backup model."""
    config = types.GenerateContentConfig(system_instruction=system, temperature=temperature)
    last_error = None
    for model in [MODEL, FALLBACK_MODEL]:      # try main model, then backup
        for attempt in range(3):               # up to 3 tries per model
            try:
                resp = client.models.generate_content(
                    model=model, contents=contents, config=config
                )
                return resp.text
            except errors.ServerError as e:    # 503 overloaded, 500, etc.
                last_error = e
                time.sleep(2 * (attempt + 1))
            except errors.ClientError as e:
                if getattr(e, "code", None) == 429:   # quota used up -> switch model now
                    last_error = e
                    break
                raise                          # real errors (bad key etc.)
            except httpx.TimeoutException as e:    # request hung -> retry
                last_error = e
    raise last_error


def _ask_llm(schema, messages):
    # Gemini uses the role name "model" instead of "assistant"
    contents = [
        types.Content(
            role="model" if m["role"] == "assistant" else "user",
            parts=[types.Part(text=m["content"])],
        )
        for m in messages
    ]
    text = _generate(contents, f"{SYSTEM_PROMPT}\nTABLE SCHEMA:\n{schema}")
    return _extract_sql(text)


def summarize_result(question, df, max_rows=30):
    """Short plain-English answer based on the result table. Never crashes the app."""
    if df is None or df.empty:
        return "No rows matched this question."
    prompt = (
        f"Question: {question}\n\n"
        f"Result table ({len(df)} rows in total, showing up to {max_rows}):\n"
        f"{df.head(max_rows).to_csv(index=False)}\n"
        "Write a 2-3 sentence plain-English answer for a business manager. "
        "Use the real numbers from the table. Do not mention SQL or tables. "
        "Do not invent facts that are not in the table."
    )
    try:
        contents = [types.Content(role="user", parts=[types.Part(text=prompt)])]
        return _generate(contents, "You are a clear, concise business analyst.", 0.2).strip()
    except Exception:
        return None


def answer_question(question, schema, con, history=None, max_retries=2):
    """
    Returns a dict: {"sql", "df", "error", "attempts"}.
    If the SQL fails, the error is sent back to the AI so it can fix it.
    """
    messages = []
    for h in (history or [])[-3:]:             # chat memory: last 3 turns
        messages += [{"role": "user", "content": h["question"]},
                     {"role": "assistant", "content": h["sql"]}]
    messages.append({"role": "user", "content": question})
    sql, last_error = "", None

    for attempt in range(1, max_retries + 2):
        sql = _ask_llm(schema, messages)

        if sql.strip().upper() == "CANNOT_ANSWER":
            return {"sql": None, "df": None, "attempts": attempt,
                    "error": "This question can't be answered from the uploaded data."}

        safe, reason = check_sql(sql)
        if not safe:
            return {"sql": sql, "df": None, "attempts": attempt,
                    "error": f"Blocked for safety: {reason}"}

        try:
            df = con.execute(sql).df()
            return {"sql": sql, "df": df, "error": None, "attempts": attempt}
        except Exception as e:
            last_error = str(e)
            messages += [
                {"role": "assistant", "content": sql},
                {"role": "user", "content": f"That query failed with this error:\n{last_error}\nReturn a corrected SQL query only."},
            ]

    return {"sql": sql, "df": None, "error": last_error, "attempts": max_retries + 1}