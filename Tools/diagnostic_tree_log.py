# Tools/diagnostic_tree_log.py - Unified diagnostic tree logger for Python + JavaScript
from Tools.logic.python.base_python_analyzer import analyze_python_functions
from Tools.logic.python.flask_analyzer import extract_flask_routes
from Tools.logic.javascript.base_js_analyzer import JSCallAnalyzer
from Tools.logic.javascript.js_api_analyzer import JSApiAnalyzer
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
def render_call_tree(call_map, call_counts, defined_funcs, func_file_map, file_distribution, total_files,func_line_map=None, tag="JS", ext=".js", color="JS", flask_routes=None):
    printed = set()
    func_line_map = func_line_map or {}
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
        return f"{indent_str}{COLOR[color]}[{tag}]{COLOR['RESET']} {COLOR[color]}{label}{COLOR['RESET']} {func} {location} (called {count}x)"
    # Recursively print the call tree
    def print_branch(func, indent=0):
        if func in printed:
            return
        printed.add(func)
        print(format_line(func, indent))
        for callee in sorted(call_map.get(func, [])):
            if callee.startswith("API: "):
                clean_api = callee.replace("API: ", "")
                print("  " * (indent + 1) + f"→ {COLOR[color]}[{tag}]{COLOR['RESET']} [API] {clean_api}")
            elif callee in defined_funcs and is_project_file(func_file_map.get(callee, "")):
                print_branch(callee, indent + 1)
    roots = [f for f in defined_funcs if call_counts.get(f, 0) == 0 and is_project_file(func_file_map.get(f, ""))]
    if flask_routes:
        print("\n=== 🧭 Python Function Call Tree ===")
        route_annotations = {func: route for route, func in flask_routes.items()}
        for root in sorted(roots):
            if root in route_annotations:
                file_name = os.path.basename(func_file_map.get(root, "?")).replace(ext, "")
                route_tag = f"{COLOR['FLASK']}[FLASK]{COLOR['RESET']} {COLOR['FLASK']}[API]{COLOR['RESET']}"
                print(f"{route_tag} ROUTE {route_annotations[root]} [{file_name}] → {root}")
            print_branch(root)
    else:
        print("\n=== \U0001f310 JavaScript Function Call Tree ===")
        for root in sorted(roots):
            print_branch(root)
    # Orphans
    print("\n=== \U0001f4a9 Single-use / Orphaned Functions ===")
    traced = set(call_map.keys()) | {c for cs in call_map.values() for c in cs}
    for func in sorted(defined_funcs):
        if call_counts.get(func, 0) != 0:
            continue
        if not is_project_file(func_file_map.get(func, "")):
            continue
        outbound = call_map.get(func, set())
        if not any(callee in func_file_map and is_project_file(func_file_map[callee]) for callee in outbound):
            file = os.path.basename(func_file_map.get(func, "?")).replace(ext, "")
            print(f"{COLOR[color]}[{tag}]{COLOR['RESET']} [FUNC] {func} [{file}] (called 0x)")
    print(f"\n[{tag.lower()}_tree_mapper] ✅ Call tree generation complete.")
# === Entry point for full diagnostics ===
def run_all_diagnostics(mode="js"):
    if mode in ("all", "py"):
        result = analyze_python_functions(".")
        flask_routes = extract_flask_routes(result["file_paths"])
        for route, func in flask_routes.items():
            result["call_counts"][func] = result["call_counts"].get(func, 0) + 1
        render_call_tree(
            result["call_map"], result["call_counts"], result["defined_funcs"],
            result["func_file_map"], result["file_distribution"], result["total_files"],
            result.get("func_line_map", {}), tag="PY", ext=".py", color="PY", flask_routes=flask_routes
        )

    if mode in ("all", "js"):
        analyzer = JSCallAnalyzer()
        analyzer.analyze_directory()
        render_call_tree(
            analyzer.call_map, analyzer.call_counts, analyzer.defined_funcs,
            analyzer.func_file_map, analyzer.file_distribution, analyzer.total_files,
            tag="JS", ext=".js", color="JS"
        )

        api_analyzer = JSApiAnalyzer()
        api_analyzer.analyze_directory()
        api_results = api_analyzer.get_results()

        print("\n=== 📡 JavaScript API Calls by Function ===")
        for caller, apis in sorted(api_results["api_map"].items()):
            file_path = api_results["caller_file_map"].get(caller, "?")
            file_name = os.path.basename(file_path).replace(".js", "")
            print(f"{COLOR['JS']}[JS]{COLOR['RESET']} [FUNC] {caller} [{file_name}] (calls {len(apis)} APIs):")
            for api in sorted(apis):
                print(f"  → {api}")

        print("\n=== 🧩 JavaScript Unattached API Calls ===")
        called_apis = {api for apis in api_results["api_map"].values() for api in apis}
        for api, count in sorted(api_results["endpoint_call_counts"].items()):
            if count == 0 or api not in called_apis:
                print(f"{COLOR['JS']}[JS]{COLOR['RESET']} [API] {api} (called 0x)")

# Auto-run for JS only until merge is confirmed
run_all_diagnostics(mode="js")