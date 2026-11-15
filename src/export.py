from io import BytesIO
import pandas as pd


def to_excel_bytes(df, question="", sql=""):
    """Build an .xlsx file in memory: a Result sheet and a Query info sheet."""
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Result", index=False)
        info = pd.DataFrame({"Item": ["Question", "SQL used"], "Value": [question, sql or ""]})
        info.to_excel(writer, sheet_name="Query info", index=False)
        for ws in writer.book.worksheets:            # auto column width
            for col in ws.columns:
                longest = max(len(str(c.value)) if c.value is not None else 0 for c in col)
                ws.column_dimensions[col[0].column_letter].width = min(longest + 2, 60)
    return buffer.getvalue()