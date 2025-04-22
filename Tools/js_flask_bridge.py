# Tools/js_flask_bridge.py
import os
import re
from collections import defaultdict
from Tools.call_tree_mapper import analyze_project_tree
from Tools.js_tree_mapper import JSCallAnalyzer
# Constants
FLASK_ROUTE_REGEX = re.compile(r"@(?:app|\w+_bp)\.(route|get|post|put|delete|patch)\((.*?)\)")
JS_API_REGEX = re.compile(r"(?:fetch|axios\.(get|post|put|delete))\(([^\)]+)\)")
# === Collect Flask routes ===
def extract_flask_routes_via_ast():
    analyzer = analyze_project_tree(".")
    return {
        normalize_path(route.split(" ", 1)[1]): func  # remove METHOD
        for route, func in analyzer.flask_routes.items()
    }
# === Collect Flask routes via regex ===
def extract_js_calls_from_analyzer():
    analyzer = JSCallAnalyzer()
    for root, _, files in os.walk("static/js"):
        for file in files:
            if file.endswith(".js"):
                analyzer.analyze_file(os.path.join(root, file))
    # Normalize and flatten
    norm_map = defaultdict(list)
    for func, urls in analyzer.api_calls.items():
        for url in urls:
            norm = normalize_path(url)
            norm_map[norm].append((func, url))
    return norm_map
# === Utility: Normalize API path by removing parameters ===
def normalize_path(path):
    path = path.strip().strip("'\"` ")
    path = re.sub(r"<[^>]+>", ":var", path) # Replace Flask-style <param> with :param
    path = re.sub(r"\$\{[^}]+\}", ":var", path) # Replace JS-style ${param} with :param
    path = re.sub(r"\s*\+\s*\w+", "", path) # Remove + variable concat artifacts
    path = re.sub(r"//+", "/", path) # Normalize slashes
    return path.rstrip("/") + "/"
# === Match JS to Flask and report as groups ===
def map_js_to_flask():
    flask_routes = extract_flask_routes_via_ast()
    js_calls = extract_js_calls_from_analyzer()

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
