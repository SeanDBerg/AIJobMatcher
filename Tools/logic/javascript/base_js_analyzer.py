# Tools/logic/javascript/base_js_analyzer.py - Extract JS functions and API calls
import os
import re
from collections import defaultdict, Counter

# Directory containing JS source files
JS_DIR = "static/js"

# === JS Call Tree Collector with Embedded API Mapping ===
class JSCallAnalyzer:
    def __init__(self):
        # Function call graph: caller -> {callees or API calls}
        self.call_map = defaultdict(set)
        self.call_counts = Counter()
        self.defined_funcs = set()
        self.func_file_map = {}
        self.api_calls = defaultdict(list)
        self.file_distribution = Counter()
        self.total_files = 0

        # Enhanced API detection
        self.api_patterns = [
            re.compile(r"fetch\s*\(\s*['\"](?P<url>[^'\"]+)['\"]", re.IGNORECASE),
            re.compile(r"\$\.post\s*\(\s*['\"](?P<url>[^'\"]+)", re.IGNORECASE),
            re.compile(r"\$\.getJSON\s*\(\s*['\"](?P<url>[^'\"]+)", re.IGNORECASE),
            re.compile(r"\$\.ajax\s*\(\s*\{\s*[^}]*?url\s*:\s*['\"](?P<url>[^'\"]+)", re.IGNORECASE)
        ]

    # Analyze a single JavaScript file
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

                # Track function calls
                if current_func:
                    call_match = re.findall(r"(\w+)\s*\(", stripped)
                    for called in call_match:
                        self.call_map[current_func].add(called)
                        self.call_counts[called] += 1
                    window = "".join(lines[i:i+10])
                    # Detect and normalize API calls
                    for pattern in self.api_patterns:
                        match = re.search(pattern, window)
                        if match:
                            url = match.group("url")
                            method = "POST" if ".post" in pattern.pattern else "GET"
                            method_match = re.search(r"method\s*:\s*['\"]([A-Z]+)['\"]", window)
                            if method_match:
                                method = method_match.group(1).upper()
                            # Normalize template vars
                            cleaned = url.strip()
                            cleaned = re.sub(r"\$\{[^}]+\}", ":var", cleaned)
                            cleaned = re.sub(r"\s*\+\s*\w+", "", cleaned)
                            cleaned = re.sub(r"//+", "/", cleaned).rstrip("/")
    
                            if cleaned:
                               tag = f"API: {method} {cleaned}"
                               self.api_calls[current_func].append(tag)
                               self.call_map[current_func].add(tag)
                               self.call_counts[tag] += 1
        except Exception as e:
            print(f"[js_analyzer] ⚠️ Failed to parse {filepath}: {e}")

    # Recursively walk through the JS directory and analyze all .js files
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
