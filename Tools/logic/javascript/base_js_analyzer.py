# Tools/logic/javascript/base_js_analyzer.py - Extract JS functions and function-to-function call graphs (no API logic)
import os
import re
from collections import defaultdict, Counter

JS_DIR = "static/js"

class JSCallAnalyzer:
    def __init__(self):
        self.call_map = defaultdict(set)
        self.call_counts = Counter()
        self.defined_funcs = set()
        self.func_file_map = {}
        self.file_distribution = Counter()
        self.total_files = 0

    def analyze_file(self, filepath):
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

                # Track function calls (pure call relationships only)
                if current_func:
                    call_match = re.findall(r"(\w+)\s*\(", stripped)
                    for called in call_match:
                        self.call_map[current_func].add(called)
                        self.call_counts[called] += 1

        except Exception as e:
            print(f"[js_analyzer] ⚠️ Failed to parse {filepath}: {e}")

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

        for path in js_files:
            self.analyze_file(path)
