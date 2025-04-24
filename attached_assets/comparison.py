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
def render_combined_call_trees(all_trees):
    printed = set()
    print("\n=== 🧭 Function Call Tree ===")

    def is_project_file(path):
        return not any(x in path for x in ["venv", "site-packages", "__pycache__", "node_modules"])

    def format_line(func, indent, tag, ext, func_file_map, func_line_map, call_counts):
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

    def print_branch(func, indent, tree):
        if func in printed:
            return
        printed.add(func)
        print(format_line(func, indent, tree["tag"], tree["ext"], tree["func_file_map"], tree["func_line_map"], tree["call_counts"]))
        for callee in sorted(tree["call_map"].get(func, [])):
            if callee in tree["defined_funcs"] and is_project_file(tree["func_file_map"].get(callee, "")):
                print_branch(callee, indent + 1, tree)
        if func in tree["api_map"] and isinstance(tree["api_map"][func], (list, set)):
            for api in sorted(tree["api_map"][func]):
                print("  " * (indent + 1) + f"→ [API] {api} [{tree['tag']}]")

    all_roots = []
    for tree in all_trees:
        roots = set()
        for func in tree["defined_funcs"]:
            has_caller = any(func in callees for callees in tree["call_map"].values())
            if not has_caller:
                roots.add(func)
        for func in tree["api_map"]:
            roots.add(func)
        if tree["flask_routes"]:
            route_annotations = {func: route for route, func in tree["flask_routes"].items()}
            for root in sorted(roots):
                if root in route_annotations:
                    file_name = os.path.basename(tree["func_file_map"].get(root, "?")).replace(tree["ext"], "")
                    print(f"[API] ROUTE {route_annotations[root]} [{file_name}] → {root} [FLASK]")
                print_branch(root, 0, tree)
        else:
            for root in sorted(roots):
                print_branch(root, 0, tree)

    print("\n=== \U0001f4a9 Single-use / Orphaned Functions ===")
    for tree in all_trees:
        for func in sorted(tree["defined_funcs"]):
            if tree["call_counts"].get(func, 0) != 0:
                continue
            if not is_project_file(tree["func_file_map"].get(func, "")):
                continue
            outbound = tree["call_map"].get(func, set())
            if not outbound and func not in tree["api_map"]:
                file = os.path.basename(tree["func_file_map"].get(func, "?")).replace(tree["ext"], "")
                print(f"[FUNC] {func} [{file}] (called 0x) [{tree['tag']}]")

# === Entry point for full diagnostics ===
def run_all_diagnostics(mode="js"):
    all_trees = []

    if mode in ("all", "py"):
        result = analyze_python_functions(".")
        flask_routes = extract_flask_routes(result["file_paths"])
        for route, func in flask_routes.items():
            result["call_counts"][func] = result["call_counts"].get(func, 0) + 1
        all_trees.append({
            "call_map": result["call_map"],
            "call_counts": result["call_counts"],
            "defined_funcs": result["defined_funcs"],
            "func_file_map": result["func_file_map"],
            "file_distribution": result["file_distribution"],
            "total_files": result["total_files"],
            "func_line_map": result.get("func_line_map", {}),
            "api_map": defaultdict(set),
            "tag": "PY",
            "ext": ".py",
            "flask_routes": flask_routes
        })

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
        all_trees.append({
            "call_map": analyzer.call_map,
            "call_counts": analyzer.call_counts,
            "defined_funcs": analyzer.defined_funcs,
            "func_file_map": analyzer.func_file_map,
            "file_distribution": analyzer.file_distribution,
            "total_files": analyzer.total_files,
            "func_line_map": {},
            "api_map": api_results["api_map"],
            "tag": "JS",
            "ext": ".js",
            "flask_routes": None
        })

    render_combined_call_trees(all_trees)

# Auto-run for JS + PY combined
run_all_diagnostics(mode="all")
