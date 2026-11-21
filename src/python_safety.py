import ast

ALLOWED_IMPORTS = (
    "pandas", "numpy", "scipy", "sklearn",
    "plotly.express", "plotly.graph_objects", "plotly.subplots",
    "math", "statistics", "datetime", "itertools", "collections",
)

BLOCKED_NAMES = {
    "open", "exec", "eval", "compile", "__import__", "input", "globals", "locals",
    "vars", "getattr", "setattr", "delattr", "breakpoint", "exit", "quit", "help",
    "dir", "memoryview", "type",
}

BLOCKED_ATTRS = {
    # system / files / network
    "system", "popen", "spawn", "rmdir", "unlink", "rmtree", "mkdir",
    "makedirs", "chmod", "os", "sys", "subprocess", "shutil", "importlib",
    "builtins", "pickle", "socket", "urllib", "requests", "http", "ctypes",
    "io", "Path", "pathlib",
    # code execution
    "eval", "query",
    # reading / writing files
    "load", "loads", "save", "savez", "savetxt", "loadtxt", "genfromtxt", "fromfile",
    "tofile", "memmap", "to_csv", "to_excel", "to_pickle", "to_sql", "to_parquet",
    "to_json", "to_html", "to_feather", "to_hdf", "to_clipboard", "to_latex",
    "to_markdown", "to_xml", "to_stata", "to_gbq", "to_orc", "plot",
}


def _is_allowed_module(name):
    return any(name == m or name.startswith(m + ".") for m in ALLOWED_IMPORTS)


def check_python(code):
    """Return (is_safe, reason). A static check run BEFORE the code executes."""
    if not code or not code.strip():
        return False, "Empty code."
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"Syntax error: {e.msg} (line {e.lineno})"

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if not _is_allowed_module(alias.name):
                    return False, f"Import not allowed: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            if node.level or not node.module or not _is_allowed_module(node.module):
                return False, f"Import not allowed: {node.module}"
            for alias in node.names:
                if alias.name in BLOCKED_ATTRS or alias.name.startswith("__"):
                    return False, f"Blocked name: {alias.name}"
        elif isinstance(node, ast.Name):
            if node.id in BLOCKED_NAMES or (node.id.startswith("__") and node.id != "__name__"):
                return False, f"Blocked name: {node.id}"
        elif isinstance(node, ast.Attribute):
            a = node.attr
            if a.startswith("__") or a in BLOCKED_ATTRS or a.startswith(("read_", "write_")):
                return False, f"Blocked attribute: {a}"
    return True, "ok"