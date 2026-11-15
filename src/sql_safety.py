import re

FORBIDDEN = [
    "insert", "update", "delete", "drop", "alter", "create", "truncate",
    "attach", "detach", "copy", "export", "import", "install", "load",
    "pragma", "call", "grant", "revoke",
]


def check_sql(sql):
    """Return (is_safe, reason). Only a single read-only SELECT is allowed."""
    cleaned = re.sub(r"--.*?$|/\*.*?\*/", " ", sql, flags=re.S | re.M).strip()
    cleaned = cleaned.rstrip(";").strip()
    if not cleaned:
        return False, "Empty query."
    if ";" in cleaned:
        return False, "Only one SQL statement is allowed."
    if not re.match(r"^(select|with)\b", cleaned, flags=re.I):
        return False, "Only SELECT queries are allowed."
    lowered = cleaned.lower()
    for word in FORBIDDEN:
        if re.search(rf"\b{word}\b", lowered):
            return False, f"Blocked keyword: {word.upper()}"
    return True, "ok"