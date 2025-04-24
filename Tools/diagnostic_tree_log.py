# Tools/diagnostic_tree_log.py - Unified diagnostic tree logger for Python + JavaScript
from Tools.logic.python.base_python_analyzer import analyze_python_functions
from Tools.logic.python.flask_analyzer import extract_flask_routes
from Tools.logic.javascript.base_js_analyzer import JSCallAnalyzer
from Tools.logic.javascript.js_api_analyzer import JSApiAnalyzer
from collections import defaultdict
import os

# === Color Scheme for Tags ===
COLOR = {
    "PY": "\033[38;5:110m",
    "FLASK": "\033[38;5:117m",
    "JS": "\033[38;5:203m",
    "HTML": "\033[38;5:229m",
    "RESET": "\033[0m"
}

# === Universal Function Tree Renderer ===
def render_call_tree(call_map, call_counts, defined_funcs, func_file_map, file_distribution, total_files, api_map=None, func_line_map=None, tag="JS", ext=".js", color="JS", flask_routes=None):
    printed = set()
    func_line_map = func_line_map or {}
    api_map = api_map if isinstance(api_map, dict) else defaultdict(set)

    print(f"[{tag.lower()}_tree_mapper] \U0001f4c2 Top-level directory {ext} file distribution:")
    for directory, count in sorted(file_distribution.items()):
        print(f"  - {directory}/: {count} files")

    print(f"[{tag.lower()}_tree_mapper] \U0001f9e0 Scanning {total_files} {ext} files for function mapping...")

    # Filter out non-project files
    def is_project_file(path):
        return not any(x in path for x in ["venv", "site-packages", "__pycache__", "node_modules"])

    # Format a function line with indentation and call details
    def format_line(func, indent=0):
        file_path = func_file_map.get(func, "?")
        file_name = os.path.basename(file_path).replace(ext, "")
        location = f"[{file_name}]"
        line = func_line_map.get(func)
        if line:
            location = f"[{file_name}{ext}:{line}]"
        count = call_counts.get(func, 0)
        indent_str = "  " * indent
        is_api = func.startswith("API: ")
        label = "[API]" if is_api else "[FUNC]"
        return f"{indent_str}{label} {func} {location} (called {count}x) [{tag}]"

    # Recursively print the call tree
    def print_branch(func, indent=0):
        if func in printed:
            return
        printed.add(func)
        print(format_line(func, indent))
        for callee in sorted(call_map.get(func, [])):
            if callee in defined_funcs and is_project_file(func_file_map.get(callee, "")):
                print_branch(callee, indent + 1)
        # Append API calls from api_map if present
        if func in api_map and isinstance(api_map[func], (list, set)):
            for api in sorted(api_map[func]):
                print("  " * (indent + 1) + f"→ [API] {api} [{tag}]")

    # Modified logic: Include all API-using functions as roots even if they are not called
    roots = set()
    for func in defined_funcs:
        has_caller = any(func in callees for callees in call_map.values())
        if not has_caller:
            roots.add(func)
    for func in api_map:
        roots.add(func)

    if tag == "PY":
        route_annotations = {func: route for route, func in flask_routes.items()} if flask_routes else {}

    for root in sorted(roots):
        if tag == "PY" and flask_routes and root in route_annotations:
            file_name = os.path.basename(func_file_map.get(root, "?")).replace(ext, "")
            print(f"[API] ROUTE {route_annotations[root]} [{file_name}] → {root} [FLASK]")
        print_branch(root)

    # Orphans
    print("\n=== \U0001f4a9 Single-use / Orphaned Functions ===")
    for func in sorted(defined_funcs):
        if call_counts.get(func, 0) != 0:
            continue
        if not is_project_file(func_file_map.get(func, "")):
            continue
        outbound = call_map.get(func, set())
        if not outbound and func not in api_map:
            file = os.path.basename(func_file_map.get(func, "?")).replace(ext, "")
            print(f"[FUNC] {func} [{file}] (called 0x) [{tag}]")

    print(f"\n[{tag.lower()}_tree_mapper] ✅ Call tree generation complete.")

# === Entry point for full diagnostics ===
def run_all_diagnostics(mode="js"):
    combined_results = []

    if mode in ("all", "py"):
        result = analyze_python_functions(".")
        flask_routes = extract_flask_routes(result["file_paths"])
        for route, func in flask_routes.items():
            result["call_counts"][func] = result["call_counts"].get(func, 0) + 1
        combined_results.append((
            result["call_map"], result["call_counts"], result["defined_funcs"],
            result["func_file_map"], result["file_distribution"], result["total_files"],
            result.get("func_line_map", {}), None, "PY", ".py", "PY", flask_routes
        ))

    if mode in ("all", "js"):
        analyzer = JSCallAnalyzer()
        analyzer.analyze_directory()
        api_analyzer = JSApiAnalyzer()
        api_analyzer.analyze_directory()
        api_results = api_analyzer.get_results()
        for caller, apis in api_results["api_map"].items():
            if caller not in analyzer.defined_funcs:
                analyzer.defined_funcs.add(caller)
            if caller not in analyzer.call_counts:
                analyzer.call_counts[caller] = 0
            if caller not in analyzer.func_file_map:
                analyzer.func_file_map[caller] = api_results["caller_file_map"].get(caller, "unknown")
            if caller not in analyzer.call_map:
                analyzer.call_map[caller] = set()
        combined_results.append((
            analyzer.call_map, analyzer.call_counts, analyzer.defined_funcs,
            analyzer.func_file_map, analyzer.file_distribution, analyzer.total_files,
            None, api_results["api_map"], "JS", ".js", "JS", None
        ))

    print("\n=== 🧭 Function Call Tree ===")
    for args in combined_results:
        render_call_tree(*args)

# Auto-run for JS + PY combined
run_all_diagnostics(mode="all")
