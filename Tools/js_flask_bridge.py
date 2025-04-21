# Tools/js_flask_bridge.py
import ast
import os
import re
from collections import defaultdict

FLASK_ROUTE_REGEX = re.compile(r"@(?:app|\w+_bp)\.(route|get|post|put|delete|patch)\((.*?)\)")
JS_API_REGEX = re.compile(r"(?:fetch|axios\.(get|post|put|delete))\(([^\)]+)\)")

# === Utility: Normalize API path by removing parameters ===
def normalize_path(path):
    path = path.strip().strip("'\"` ")
    path = re.sub(r"<[^>]+>", "", path)          # Remove Flask dynamic <params>
    path = re.sub(r"\\$\{[^}]+\}", "", path)    # Remove JS ${params}
    path = re.sub(r"\+[^+]+", "", path)           # Remove JS string concat pieces
    return re.sub(r"//+", "/", path.rstrip("/ ")) + "/"

# === Collect Flask route paths ===
def extract_flask_routes(py_dir="."):
    route_map = {}  # route_path → handler name
    for root, _, files in os.walk(py_dir):
        if any(excluded in root for excluded in ["venv", "__pycache__", ".mypy_cache", ".pythonlibs"]):
            continue
        for file in files:
            if not file.endswith(".py"):
                continue
            path = os.path.join(root, file)
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                for i, line in enumerate(lines):
                    match = FLASK_ROUTE_REGEX.search(line)
                    if match:
                        route_str = match.group(2).split(",")[0]
                        route = normalize_path(route_str)
                        # Look forward to grab def line
                        for j in range(i+1, min(i+5, len(lines))):
                            if lines[j].strip().startswith("def "):
                                fn_name = lines[j].split("def ")[1].split("(")[0].strip()
                                route_map[route] = fn_name
                                break
            except Exception as e:
                print(f"[js_flask_bridge] ⚠️ Error in {file}: {e}")
    return route_map

# === Collect JS API fetch calls ===
def extract_js_calls(js_dir="./static/js"):
    call_map = defaultdict(list)  # normalized route → list of (js_func_name, original_path)
    for root, _, files in os.walk(js_dir):
        for file in files:
            if not file.endswith(".js"):
                continue
            path = os.path.join(root, file)
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                current_func = None
                for line in lines:
                    line = line.strip()
                    # Detect JS function header
                    if line.startswith("function "):
                        current_func = line.split("function ")[1].split("(")[0]
                    # Detect fetch/axios call
                    match = JS_API_REGEX.search(line)
                    if match:
                        raw = match.group(2)
                        norm = normalize_path(raw)
                        if current_func:
                            call_map[norm].append((current_func, raw))
            except Exception as e:
                print(f"[js_flask_bridge] ⚠️ Error in {file}: {e}")
    return call_map

# === Match JS to Flask and report as groups ===
def map_js_to_flask():
    flask_routes = extract_flask_routes()
    js_calls = extract_js_calls()

    matches = []
    js_orphans = []
    flask_orphans = set(flask_routes.keys())

    for route, callers in js_calls.items():
        if route in flask_routes:
            flask_orphans.discard(route)
            for func_name, original in callers:
                matches.append((func_name, original.strip(), flask_routes[route]))
        else:
            for func_name, original in callers:
                js_orphans.append((func_name, original.strip()))

    print("\n=== 🔗 JavaScript ↔ Flask Route Connections ===")
    for func, js_api, handler in matches:
        print(f"  JS {func} → API {js_api} → Flask: {handler}()")

    print("\n=== 🧩 JS API Calls (Unmatched) ===")
    for func, js_api in js_orphans:
        print(f"  JS {func} → API {js_api} → Flask: ❌ No match")

    print("\n=== 🧩 Flask Routes (Uncalled) ===")
    for route in sorted(flask_orphans):
        print(f"  Flask route {route} → {flask_routes[route]}() ← ❌ Not triggered by JS")

# Auto-run when imported
map_js_to_flask()
