# Tools/js_tree_mapper.py
import os
import re
from collections import defaultdict, Counter
JS_DIR = "static/js"
# === JS Call Tree Collector ===
class JSCallAnalyzer:
    def __init__(self):
        self.call_map = defaultdict(set)
        self.call_counts = Counter()
        self.defined_funcs = set()
        self.func_file_map = {}
        self.api_calls = defaultdict(list)
    # Analyze a single JavaScript file
    def analyze_file(self, filepath):
        JS_API_REGEX = re.compile(r"(?:fetch|axios\.(?:get|post|put|delete))\s*\(\s*(?P<url>[`\"']?[^,`\"']+[`\"']?)")
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            current_func = None
            for i, line in enumerate(lines):
                stripped = line.strip()

                # Match function declarations
                func_decl = re.match(r"function (\w+)\s*\(", stripped)
                if func_decl:
                    current_func = func_decl.group(1)
                    self.defined_funcs.add(current_func)
                    self.func_file_map[current_func] = filepath
                    continue

                # Match arrow or assigned functions
                assigned = re.match(r"const (\w+)\s*=\s*(?:function|\(.*\)\s*=>)", stripped)
                if assigned:
                    current_func = assigned.group(1)
                    self.defined_funcs.add(current_func)
                    self.func_file_map[current_func] = filepath
                    continue

                # Track function calls
                if current_func:
                    call_match = re.findall(r"(\w+)\s*\(", stripped)
                    for called in call_match:
                        self.call_map[current_func].add(called)
                        self.call_counts[called] += 1

                    # Match API calls using safe capture group
                    for match in re.finditer(JS_API_REGEX, stripped):
                        raw_url = match.group("url")
                        cleaned = raw_url.strip().strip('`"\'')

                        cleaned = re.sub(r"\$\{[^}]+\}", ":var", cleaned)  # normalize template vars
                        cleaned = re.sub(r"\s*\+\s*\w+", "", cleaned)      # remove + id
                        cleaned = re.sub(r"//+", "/", cleaned).rstrip("/")  # normalize slashes

                        if not cleaned:
                            continue

                        self.api_calls[current_func].append(cleaned)
                        self.call_map[current_func].add(f"API: {cleaned}")
                        self.call_counts[f"API: {cleaned}"] += 1
        except Exception as e:
            print(f"[js_tree_mapper] ⚠️ Skipped {filepath}: {e}")

# === JS Tree Printer with inline API call formatting ===
def print_js_call_tree(analyzer: JSCallAnalyzer):
    print("=== 🌐 JavaScript Call Tree ===")
    printed = set()

    def print_branch(func, indent=0):
        if func in printed:
            return
        printed.add(func)

        indent_str = "  " * indent
        count = analyzer.call_counts.get(func, 0)

        callees = sorted([
            c for c in analyzer.call_map.get(func, [])
            if c in analyzer.defined_funcs or c.startswith("API:")
        ])

        api_lines = []
        if func in analyzer.api_calls:
            for api in analyzer.api_calls[func]:
                print(f"{indent_str}CALL {api} → {func}")
                api_lines.append(f"{indent_str}→ calls API: {api}")

        callee_names = [c.replace("API: ", "") if c.startswith("API:") else c for c in callees]
        joined = ", ".join(callee_names) if callee_names else "None"
        print(f"{indent_str}{func} (called {count}x): {joined}")

        for line in api_lines:
            print(line)

        for callee in callees:
            print_branch(callee, indent + 1)

    roots = [f for f in analyzer.defined_funcs if analyzer.call_counts.get(f, 0) == 0]
    for root in sorted(roots):
        print_branch(root)

    print("\n=== 🧩 JavaScript Orphaned Functions ===")
    traced = set(analyzer.call_map.keys()) | {c for cs in analyzer.call_map.values() for c in cs}
    orphans = sorted(f for f in analyzer.defined_funcs if f not in traced)
    for orphan in orphans:
        file = os.path.basename(analyzer.func_file_map.get(orphan, "?"))
        print(f"[JS] {orphan} [{file}] (called 0x)")

    api_all = {f"API: {api}" for apis in analyzer.api_calls.values() for api in apis}
    api_unattached = sorted([api for api in api_all if api not in traced])
    for api in api_unattached:
        print(f"[API] {api} (called 0x)")

# === Entry Point ===
def generate_js_call_map():
    analyzer = JSCallAnalyzer()
    directory_summary = Counter()
    js_files = []

    for root, _, files in os.walk(JS_DIR):
        rel_root = os.path.relpath(root, JS_DIR)
        if rel_root == ".":
            rel_root = "root"
        for file in files:
            if file.endswith(".js"):
                path = os.path.join(root, file)
                js_files.append(path)
                directory_summary[rel_root] += 1

    print("[js_tree_mapper] 📂 Top-level directory .js file distribution:")
    for directory, count in sorted(directory_summary.items()):
        print(f"  - {directory}/: {count} files")

    print(f"[js_tree_mapper] 🧠 Scanning {len(js_files)} JavaScript files for function mapping...")

    for i, path in enumerate(js_files, 1):
        analyzer.analyze_file(path)
        if i % 10 == 0 or i == len(js_files):
            percent = round((i / len(js_files)) * 100)
            print(f"[js_tree_mapper] ✅ Processed {i}/{len(js_files)} files ({percent}%)")

    print_js_call_tree(analyzer)
    print("\n[js_tree_mapper] ✅ JavaScript call tree generation complete.")

# Auto-run when imported
generate_js_call_map()
