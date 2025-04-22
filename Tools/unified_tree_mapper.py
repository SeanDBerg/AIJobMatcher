# unified_tree_mapper.py - Merges JS, Flask, and Python trees into a unified call graph

import os
from collections import defaultdict
from Tools.call_tree_mapper import analyze_project_tree
from Tools.js_tree_mapper import JSCallAnalyzer
from Tools.js_flask_bridge import extract_flask_routes_via_ast

def build_unified_tree():
    print("\n=== 🧠 UNIFIED CALL TREE ===")

    # === Analyze Python ===
    py_analyzer = analyze_project_tree(".")
    py_tree = py_analyzer.call_map
    py_defined = py_analyzer.defined_funcs
    flask_routes = extract_flask_routes_via_ast()
    route_targets = set(flask_routes.values())

    # === Analyze JavaScript ===
    js_analyzer = JSCallAnalyzer()
    for root, _, files in os.walk("static/js"):
        for file in files:
            if file.endswith(".js"):
                js_analyzer.analyze_file(os.path.join(root, file))
    js_tree = js_analyzer.call_map
    js_defined = js_analyzer.defined_funcs

    # === Bridge JS → Flask → Python ===
    unified_tree = defaultdict(set)
    for js_func, api_urls in js_analyzer.api_calls.items():
        if js_func not in js_defined:
            continue
        for callee in js_tree[js_func]:
            if callee in js_defined or callee.startswith("API: "):
                unified_tree[js_func].add(callee)
        for api_url in api_urls:
            norm_api = normalize_path(api_url)
            flask_handler = flask_routes.get(norm_api)
            if flask_handler:
                unified_tree[js_func].add(flask_handler)
                if flask_handler in py_tree:
                    for callee in py_tree[flask_handler]:
                        if callee in py_defined:
                            unified_tree[flask_handler].add(callee)

    for py_func in py_tree:
        if py_func not in unified_tree:
            unified_tree[py_func].update({c for c in py_tree[py_func] if c in py_defined})

    print_tree(unified_tree, py_defined, js_defined, flask_routes)
    print("\n=== 🧩 Unified Orphaned Functions ===")
    all_traced = set(unified_tree.keys()) | {c for callees in unified_tree.values() for c in callees}
    project_defined = py_defined | js_defined
    orphaned = sorted(f for f in project_defined if f not in all_traced and f not in route_targets)
    for orphan in orphaned:
        print(f"{orphan} (called 0x)")

def normalize_path(path):
    import re
    path = path.strip().strip("'\"` ")
    path = re.sub(r"<[^>]+>", ":var", path)
    path = re.sub(r"\$\{[^}]+\}", ":var", path)
    path = re.sub(r"\+[^+]+", "", path)
    path = re.sub(r"//+", "/", path)
    return path.rstrip("/") + "/"

def print_tree(tree, py_funcs, js_funcs, flask_routes):
    printed = set()

    def is_project(name):
        return name in py_funcs or name in js_funcs or name.startswith("API: ")

    def print_branch(func, depth=0):
        if func in printed:
            return
        printed.add(func)
        indent = "  " * depth
        line = f"{indent}{func}"
        if depth == 0 and func in flask_routes.values():
            route = [r for r, f in flask_routes.items() if f == func][0]
            print(f"ROUTE {route} → {func}")
        print(line)
        for callee in sorted(tree.get(func, [])):
            if is_project(callee):
                print_branch(callee, depth + 1)

    roots = [f for f in tree if f not in {c for callees in tree.values() for c in callees}]
    for root in sorted(roots):
        if is_project(root):
            print_branch(root)

# Auto-run when imported
build_unified_tree()
