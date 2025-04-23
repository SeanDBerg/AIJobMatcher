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