# Tools/js_tree_mapper.py
import os
import re
import js2py
from collections import defaultdict, Counter

JS_DIR = "static/js"
COMMON_JS_GLOBALS = {
    'append', 'remove', 'html', 'val', 'empty', 'fadeIn', 'fadeOut', 'on', 'off',
    'addClass', 'removeClass', 'setTimeout', 'forEach', 'map', 'filter', 'reduce',
    'if', 'catch', 'then', 'log', 'alert', 'function', 'console', 'data', 'text', 'eq', 'find', 'join'
}

# === JS Call Tree Collector ===
class JSCallAnalyzer:
    def __init__(self):
        self.call_map = defaultdict(set)
        self.call_counts = Counter()
        self.defined_funcs = set()
        self.func_file_map = {}
        self.api_calls = defaultdict(list)

    def analyze_file(self, filepath):
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            current_func = None
            for i, line in enumerate(lines):
                # Match function declarations
                func_decl = re.match(r"function (\w+)\s*\(", line)
                if func_decl:
                    current_func = func_decl.group(1)
                    self.defined_funcs.add(current_func)
                    self.func_file_map[current_func] = filepath
                    continue

                # Match arrow or assigned functions
                assigned = re.match(r"const (\w+)\s*=\s*(?:function|\(.*\)\s*=>)", line)
                if assigned:
                    current_func = assigned.group(1)
                    self.defined_funcs.add(current_func)
                    self.func_file_map[current_func] = filepath
                    continue

                # Match function calls inside current function
                if current_func:
                    call_match = re.findall(r"(\w+)\s*\(", line)
                    for called in call_match:
                        if called in COMMON_JS_GLOBALS:
                            continue
                        self.call_map[current_func].add(called)
                        self.call_counts[called] += 1

                    # Match fetch/axios/$ API calls with literal or template strings
                    api_match = re.search(r"(?P<caller>fetch|axios\.\w+|\$\.\w+)\s*\(\s*[`'\"](?P<url>[^`'\"]+)", line)
                    if api_match:
                        url = api_match.group("url")
                        self.call_map[current_func].add(f"API: {url}")
                        self.api_calls[current_func].append(url)
        except Exception as e:
            print(f"[js_tree_mapper] ⚠️ Skipped {filepath}: {e}")

# === JS Tree Printer ===
def print_js_call_tree(analyzer: JSCallAnalyzer):
    printed = set()

    def print_branch(func, indent=0):
        if func in printed:
            return
        printed.add(func)
        callees = sorted(analyzer.call_map.get(func, []))
        location = f" [{os.path.basename(analyzer.func_file_map.get(func, '?'))}]"
        line = f"{'  ' * indent}{func}{location} (called {analyzer.call_counts.get(func, 0)}x): {', '.join(callees) or 'None'}"
        print(line[:150])
        for callee in callees:
            if callee in analyzer.defined_funcs or callee.startswith("API: "):
                print_branch(callee, indent + 1)

    print("=== 🌐 JavaScript Function Call Tree ===")
    roots = [f for f in analyzer.defined_funcs if analyzer.call_counts.get(f, 0) == 0]
    for root in sorted(roots):
        print_branch(root)

# === Entry Point ===
def generate_js_call_map():
    analyzer = JSCallAnalyzer()
    js_files = []
    for root, _, files in os.walk(JS_DIR):
        for file in files:
            if file.endswith(".js"):
                js_files.append(os.path.join(root, file))

    print(f"[js_tree_mapper] 🔍 Scanning {len(js_files)} JavaScript files in {JS_DIR}...")
    for i, path in enumerate(js_files, 1):
        analyzer.analyze_file(path)
        if i % 10 == 0 or i == len(js_files):
            percent = round((i / len(js_files)) * 100)
            print(f"[js_tree_mapper] ✅ Processed {i}/{len(js_files)} files ({percent}%)")

    print_js_call_tree(analyzer)
    print("\n[js_tree_mapper] ✅ JavaScript call tree generation complete.")

# Auto-run when imported
generate_js_call_map()
