# Tools/call_tree_mapper.py
import ast
import os
from collections import defaultdict, Counter
# Define directories that should always be skipped
EXCLUDE_DIRS = {
    ".git", "venv", ".venv", "site-packages", "__pycache__", "node_modules",
    ".mypy_cache", ".upm", ".pythonlibs", ".cache", "build", "dist", ".pytest_cache"
}
def is_project_file(path):
    parts = path.split(os.sep)
    return not any(part in EXCLUDE_DIRS for part in parts)
# AST visitor to analyze function calls
class CallAnalyzer(ast.NodeVisitor):
    def __init__(self, filename):
        self.filename = filename
        self.current_func = None
        self.call_map = defaultdict(set)
        self.call_counts = defaultdict(int)
        self.defined_funcs = set()
        self.func_file_map = {}
        self.flask_routes = {}  # key = route str, value = function name
    # Visit function definitions to track defined functions
    def visit_FunctionDef(self, node):
        self.current_func = node.name
        self.defined_funcs.add(node.name)
        self.func_file_map[node.name] = self.filename
        # Detect Flask @app.route(...) or @app.get(...) style decorators
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
                method = decorator.func.attr.lower()
                if method in {"route", "get", "post", "put", "delete", "patch"}:
                    try:
                        # Get route path safely
                        if decorator.args and isinstance(decorator.args[0], ast.Constant):
                            route_path = decorator.args[0].value
                        else:
                            route_path = "?"
                        # Get HTTP method from methods=["POST"] keyword if present
                        http_method = method.upper()
                        for kw in decorator.keywords:
                            if kw.arg == "methods" and isinstance(kw.value, ast.List):
                                for elt in kw.value.elts:
                                    if isinstance(elt, ast.Constant):
                                        http_method = elt.value.upper()
                                        break
                        route_str = f"{http_method} {route_path}"
                        self.flask_routes[route_str] = node.name
                    except Exception:
                        pass # Silently ignore malformed decorators
        self.generic_visit(node)
        self.current_func = None
    # Visit function calls to track call relationships
    def visit_Call(self, node):
        if self.current_func:
            func_name = self._get_call_name(node.func)
            if func_name:
                self.call_map[self.current_func].add(func_name)
                self.call_counts[func_name] += 1
        self.generic_visit(node)
    # Helper to get the name of a function call
    def _get_call_name(self, node):
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return node.attr
        return None
# Helper to determine if a directory should be excluded from analysis
def should_exclude_dir(path):
    parts = path.split(os.sep)
    return any(part in EXCLUDE_DIRS for part in parts)
# Analyze the project tree and generate a call map
def analyze_project_tree(base_dir="."):
    file_paths = []
    root_dir_counts = Counter()
    for root, dirs, files in os.walk(base_dir):
        if should_exclude_dir(root):
            continue
        for file in files:
            if file.endswith(".py"):
                full_path = os.path.join(root, file)
                file_paths.append(full_path)
                # Track first-level directory under root
                relative = os.path.relpath(full_path, base_dir)
                top_level = relative.split(os.sep)[0]
                root_dir_counts[top_level] += 1
    # Count and display top-level .py file distribution
    print("[call_tree_mapper] 📂 Top-level directory .py file distribution:")
    for dir_name, count in root_dir_counts.most_common():
        print(f"  - {dir_name}/: {count} files")
    # Announce total scan
    print(f"[call_tree_mapper] 🧠 Scanning {len(file_paths)} Python files for function mapping...")
    # Aggregate results across all files
    combined_analyzer = CallAnalyzer("<combined>")
    for i, path in enumerate(file_paths, 1):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                tree = ast.parse(f.read(), filename=path)
            analyzer = CallAnalyzer(path)  # ✅ One analyzer per file
            analyzer.visit(tree)
            # Merge results from this file into the global analyzer
            for func in analyzer.defined_funcs:
                combined_analyzer.defined_funcs.add(func)
                combined_analyzer.func_file_map[func] = analyzer.func_file_map[func]
                combined_analyzer.call_map[func].update(analyzer.call_map.get(func, set()))
                combined_analyzer.flask_routes.update(analyzer.flask_routes)
            for callee, count in analyzer.call_counts.items():
                combined_analyzer.call_counts[callee] += count
        except Exception as e:
            print(f"[call_tree_mapper] ⚠️ Skipped {os.path.basename(path)}: {e}")
        if i % 10 == 0 or i == len(file_paths):
            percent = round((i / len(file_paths)) * 100)
            print(f"[call_tree_mapper] ✅ Processed {i}/{len(file_paths)} files ({percent}%)")
    return combined_analyzer
# Print the call tree in a readable format
def print_call_tree(call_map, call_counts, defined_funcs, func_file_map, flask_routes):
    printed = set()
    # Recursively print function call branches
    def print_branch(func, indent=0):
        if func in printed or not is_project_file(func_file_map.get(func, "")):
            return
        printed.add(func)
        raw_callees = call_map.get(func, [])
        callees = [c for c in raw_callees if c in func_file_map and is_project_file(func_file_map[c])]
        line = f"{'  ' * indent}{func} (called {call_counts.get(func, 0)}x): {', '.join(sorted(callees)) or 'None'}"
        print(line[:150])
        for callee in callees:
            if callee in defined_funcs and is_project_file(func_file_map.get(callee, "")):
                print_branch(callee, indent + 1)
    # Print the call tree starting from root functions
    print("\n=== 🧭 Function Call Tree ===")
    roots = [
        f for f in defined_funcs
        if call_counts.get(f, 0) == 0
        and is_project_file(func_file_map.get(f, ""))
        and any(
            c in func_file_map and is_project_file(func_file_map[c])
            for c in call_map.get(f, [])
        )
    ]
    # Build reverse lookup for route annotations
    route_annotations = {
        func: route for route, func in flask_routes.items()
    }
    for root in sorted(roots):
        if root in route_annotations:
            print(f"ROUTE {route_annotations[root]} → {root}")
        print_branch(root)
    # Print single-use or orphaned functions
    print("\n=== 🧩 Single-use / Orphaned Functions ===")
    for func in sorted(defined_funcs):
        if not is_project_file(func_file_map.get(func, "")):
            continue
        if call_counts.get(func, 0) != 0:
            continue
        outbound = call_map.get(func, set())
        if not any(
            callee in func_file_map and is_project_file(func_file_map[callee])
            for callee in outbound
        ):
            print(f"{func} (called 0x)")
# Generate and print the call tree map
def generate_call_map():
    analyzer = analyze_project_tree(".")
    print_call_tree(analyzer.call_map, analyzer.call_counts, analyzer.defined_funcs, analyzer.func_file_map, analyzer.flask_routes)
    print("\n[call_tree_mapper] ✅ Call tree generation complete.")

# Auto-run when imported
generate_call_map()

