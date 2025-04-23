# Tools/logic/javascript/base_js_analyzer.py - Extract JS function structure and call graph only

import os
import re
from collections import defaultdict, Counter

# Directory containing JS source files
JS_DIR = "static/js"

# === JS Call Tree Collector (Structure Only) ===
class JSCallAnalyzer:
    def __init__(self):
        # Function call graph: caller → {callees}
        self.call_map = defaultdict(set)
        self.call_counts = Counter()
        self.defined_funcs = set()
        self.func_file_map = {}
        self.file_distribution = Counter()
        self.total_files = 0

    # Analyze a single JavaScript file
    def analyze_file(self, filepath):
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            current_func = None
            for line in lines:
                stripped = line.strip()

                # Match function declarations: function name(...) { ... }
                func_decl = re.match(r"function (\w+)\s*\(", stripped)
                if func_decl:
                    current_func = func_decl.group(1)
                    self.defined_funcs.add(current_func)
                    self.func_file_map[current_func] = filepath
                    continue

                # Match assigned functions: const name = (...) => { ... }
                assigned = re.match(r"const (\w+)\s*=\s*(?:function|\(.*\)\s*=>)", stripped)
                if assigned:
                    current_func = assigned.group(1)
                    self.defined_funcs.add(current_func)
                    self.func_file_map[current_func] = filepath
                    continue

                # Track nested function calls: if inside a known function
                if current_func:
                    call_match = re.findall(r"(\w+)\s*\(", stripped)
                    for called in call_match:
                        self.call_map[current_func].add(called)
                        self.call_counts[called] += 1

        except Exception as e:
            print(f"[base_js_analyzer] ⚠️ Failed to parse {filepath}: {e}")

    # Analyze all JS files in the target directory
    def analyze_directory(self, base_dir=JS_DIR):
        js_files = []
        for root, _, files in os.walk(base_dir):
            rel_root = os.path.relpath(root, base_dir)
            if rel_root == ".":
                rel_root = "root"
            for file in files:
                if file.endswith(".js"):
                    full_path = os.path.join(root, file)
                    js_files.append(full_path)
                    self.file_distribution[rel_root] += 1

        self.total_files = len(js_files)

        for i, path in enumerate(js_files, 1):
            self.analyze_file(path)

# Tools/logic/javascript/js_api_analyzer.py - Dedicated parser for JavaScript API calls

import os
import re
from collections import defaultdict, Counter

# Directory to search for JavaScript files
JS_DIR = "static/js"

# === JS API Call Collector ===
class JSApiAnalyzer:
    def __init__(self):
        self.api_map = defaultdict(set)
        self.endpoint_call_counts = Counter()
        self.caller_file_map = {}
        self.api_patterns = [
            re.compile(r"fetch\s*\(\s*['\"](?P<url>[^'\"]+)['\"]", re.IGNORECASE),
            re.compile(r"\$\.post\s*\(\s*['\"](?P<url>[^'\"]+)", re.IGNORECASE),
            re.compile(r"\$\.getJSON\s*\(\s*['\"](?P<url>[^'\"]+)", re.IGNORECASE),
            re.compile(r"\$\.ajax\s*\(\s*\{\s*[^}]*?url\s*:\s*['\"](?P<url>[^'\"]+)", re.IGNORECASE)
        ]

    # === Analyze all JS files in the specified directory ===
    def analyze_directory(self, base_dir=JS_DIR):
        for root, _, files in os.walk(base_dir):
            for file in files:
                if file.endswith(".js"):
                    self.analyze_file(os.path.join(root, file))

    # === Analyze a single JS file for API calls ===
    def analyze_file(self, filepath):
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            current_func = None
            for i, line in enumerate(lines):
                stripped = line.strip()
                func_decl = re.match(r"function (\w+)\s*\(", stripped)
                if func_decl:
                    current_func = func_decl.group(1)
                    self.caller_file_map[current_func] = filepath
                    continue
                assigned = re.match(r"const (\w+)\s*=\s*(?:function|\(.*\)\s*=>)", stripped)
                if assigned:
                    current_func = assigned.group(1)
                    self.caller_file_map[current_func] = filepath
                    continue
                if not current_func:
                    continue
                window = "".join(lines[i:i+10])
                for pattern in self.api_patterns:
                    match = re.search(pattern, window)
                    if match:
                        url = match.group("url")
                        method = "POST" if ".post" in pattern.pattern else "GET"
                        method_match = re.search(r"method\s*:\s*['\"]([A-Z]+)['\"]", window)
                        if method_match:
                            method = method_match.group(1).upper()
                        cleaned = url.strip()
                        cleaned = re.sub(r"\$\{[^}]+\}", ":var", cleaned)
                        cleaned = re.sub(r"\s*\+\s*\w+", "", cleaned)
                        cleaned = re.sub(r"//+", "/", cleaned).rstrip("/")
                        if cleaned:
                            endpoint = f"{method} {cleaned}"
                            self.api_map[current_func].add(endpoint)
                            self.endpoint_call_counts[endpoint] += 1
        except Exception as e:
            print(f"[js_api_analyzer] ⚠️ Failed to parse {filepath}: {e}")

    # === Package the output in structured form ===
    def get_results(self):
        return {
            "api_map": self.api_map,
            "endpoint_call_counts": self.endpoint_call_counts,
            "caller_file_map": self.caller_file_map
        }

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
def render_call_tree(call_map, call_counts, defined_funcs, func_file_map, file_distribution, total_files,
                     func_line_map=None, tag="JS", ext=".js", color="JS", flask_routes=None, api_map=None):
    printed = set()
    func_line_map = func_line_map or {}
    print(f"[{tag.lower()}_tree_mapper] \U0001f4c2 Top-level directory {ext} file distribution:")
    for directory, count in sorted(file_distribution.items()):
        print(f"  - {directory}/: {count} files")
    print(f"[{tag.lower()}_tree_mapper] \U0001f9e0 Scanning {total_files} {ext} files for function mapping...")

    def is_project_file(path):
        return not any(x in path for x in ["venv", "site-packages", "__pycache__", "node_modules"])

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

    def print_branch(func, indent=0):
        if func in printed:
            return
        printed.add(func)
        print(format_line(func, indent))
        for callee in sorted(call_map.get(func, [])):
            if callee in defined_funcs and is_project_file(func_file_map.get(callee, "")):
                print_branch(callee, indent + 1)
        if api_map and func in api_map:
            for endpoint in sorted(api_map[func]):
                print("  " * (indent + 1) + f"→ {COLOR[color]}[{tag}]{COLOR['RESET']} [API] {endpoint}")

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

        api_analyzer = JSApiAnalyzer()
        api_analyzer.analyze_directory()
        api_results = api_analyzer.get_results()

        render_call_tree(
            analyzer.call_map, analyzer.call_counts, analyzer.defined_funcs,
            analyzer.func_file_map, analyzer.file_distribution, analyzer.total_files,
            tag="JS", ext=".js", color="JS", api_map=api_results["api_map"]
        )

# Auto-run for JS only until merge is confirmed
run_all_diagnostics(mode="js")
