# Tools/js_tree_mapper.py - Updated to ensure API calls appear in tree and orphan list

import os
import re
import js2py
from collections import defaultdict, Counter

JS_DIR = "static/js"
COMMON_JS_GLOBALS = {
    'append', 'remove', 'html', 'val', 'empty', 'fadeIn', 'fadeOut', 'on', 'off',
    'addClass', 'removeClass', 'setTimeout', 'forEach', 'map', 'filter', 'reduce',
    'if', 'catch', 'then', 'log', 'alert', 'function', 'console', 'data', 'text', 'eq', 'find', 'join',
    'show', 'hide', 'click', 'confirm', 'json', 'reload', 'ajax', 'parse', 'String', 'each', 'replace',
    'closest', 'after', 'draw', 'info', 'error', 'accepted', 'is', 'entries', 'clear', 'destroy', 'DataTable', 'keys', 'stringify', 'setItem'
}

class JSCallAnalyzer:
    def __init__(self):
        self.call_map = defaultdict(set)
        self.call_counts = Counter()
        self.defined_funcs = set()
        self.func_file_map = {}
        self.api_calls = defaultdict(list)

    def analyze_file(self, filepath):
        JS_API_PATTERNS = {
            "fetch": r"fetch\s*\(\s*[`'\"](?P<url>[^`'\"]+)",
            "axios_shorthand": r"axios\.\w+\s*\(\s*[`'\"](?P<url>[^`'\"]+)",
            "axios_object": r"axios\s*\(\s*\{\s*[^}]*['\"]url['\"]\s*:\s*[`'\"](?P<url>[^`'\"]+)",
            "jquery": r"\$\.(post|get|ajax|getJSON)\s*\(\s*[`'\"](?P<url>[^`'\"]+)",
            "xhr": r"\.open\s*\(\s*[`'\"][A-Z]+[`'\"]\s*,\s*[`'\"](?P<url>[^`'\"]+)"
        }
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            current_func = None
            for i, line in enumerate(lines):
                stripped = line.strip()
                func_decl = re.match(r"function (\w+)\s*\(", stripped)
                if func_decl:
                    current_func = func_decl.group(1)
                    self.defined_funcs.add(current_func)
                    self.func_file_map[current_func] = filepath
                    continue
                assigned = re.match(r"const (\w+)\s*=\s*(?:function|\(.*\)\s*=>)", stripped)
                if assigned:
                    current_func = assigned.group(1)
                    self.defined_funcs.add(current_func)
                    self.func_file_map[current_func] = filepath
                    continue
                if current_func:
                    call_match = re.findall(r"(\w+)\s*\(", stripped)
                    for called in call_match:
                        if called not in self.defined_funcs:
                            continue
                        self.call_map[current_func].add(called)
                        self.call_counts[called] += 1
                    for label, pattern in JS_API_PATTERNS.items():
                        match = re.search(pattern, stripped)
                        if match:
                            url = match.group("url")
                            tag = f"API: {url}"
                            self.call_map[current_func].add(tag)
                            self.api_calls[current_func].append(tag)
                            self.call_counts[tag] += 1
        except Exception as e:
            print(f"[js_tree_mapper] ⚠️ Skipped {filepath}: {e}")

def print_js_call_tree(analyzer: JSCallAnalyzer):
    printed = set()
    def print_branch(func, indent=0):
        if func in printed:
            return
        printed.add(func)
        callees = [c for c in sorted(analyzer.call_map.get(func, [])) if c in analyzer.defined_funcs or c.startswith("API: ")]
        location = f" [{os.path.basename(analyzer.func_file_map.get(func, '?'))}]"
        line = f"{'  ' * indent}{func}{location} (called {analyzer.call_counts.get(func, 0)}x): {', '.join(callees) or 'None'}"
        print(line[:150])
        for callee in callees:
            print_branch(callee, indent + 1)

    print("=== 🌐 JavaScript Function Call Tree ===")
    roots = [f for f in analyzer.defined_funcs if analyzer.call_counts.get(f, 0) == 0]
    for root in sorted(roots):
        print_branch(root)

    print("\n=== 🧩 JavaScript Orphaned Functions ===")
    traced = set(analyzer.call_map.keys()) | {c for cs in analyzer.call_map.values() for c in cs}
    orphans = sorted(f for f in analyzer.defined_funcs if f not in traced)
    for orphan in orphans:
        print(f"{orphan} (called 0x)")

    api_all = set()
    for url_list in analyzer.api_calls.values():
        api_all.update(url_list)

    api_unattached = sorted([api for api in api_all if api not in traced])
    for api in api_unattached:
        print(f"{api} (called 0x)")

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