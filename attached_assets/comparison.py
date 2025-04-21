import os
import ast
import re
from Tools.call_tree_mapper import analyze_project_tree
from Tools.js_tree_mapper import extract_js_api_calls

# Normalize path: strip trailing slashes and parameter markers
def normalize_path(path):
    return re.sub(r"\$\{[^}]+\}", "", path.rstrip("/"))

# Bridge analyzer for JS → Flask route mapping
def bridge_js_to_flask():
    print("\n=== 🔗 JavaScript ↔ Flask Route Connections ===")

    analyzer = analyze_project_tree(".")
    flask_routes = {
        normalize_path(route): func for route, func in analyzer.flask_routes.items()
    }

    js_api_calls = extract_js_api_calls("static/js")
    normalized_calls = [(caller, normalize_path(api)) for caller, api in js_api_calls]

    matched = []
    unmatched = []

    for caller, api in normalized_calls:
        if api in flask_routes:
            matched.append((caller, api, flask_routes[api]))
        else:
            unmatched.append((caller, api))

    if matched:
        for caller, api, flask_func in matched:
            print(f"  JS {caller} → API `{api}` → Flask: ✅ {flask_func}()")
    else:
        print("  ❌ No matches found")

    if unmatched:
        print("\n=== 🧩 JS API Calls (Unmatched) ===")
        for caller, api in unmatched:
            print(f"  JS {caller} → API `{api}` → Flask: ❌ No match")

    uncalled_flask = {
        route: func for route, func in flask_routes.items()
        if route not in [api for _, api in normalized_calls]
    }

    if uncalled_flask:
        print("\n=== 🧩 Flask Routes (Uncalled) ===")
        for route, func in sorted(uncalled_flask.items()):
            print(f"  Flask route {route}/ → {func}() ← ❌ Not triggered by JS")

# Auto-run on import
bridge_js_to_flask()
