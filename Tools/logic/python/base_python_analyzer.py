# Tools/logic/python/base_python_analyzer.py - Pure Python function call analyzer

import ast
import os
from collections import defaultdict, Counter

# Define directories that should always be skipped
EXCLUDE_DIRS = {
    ".git", "venv", ".venv", "site-packages", "__pycache__", "node_modules",
    ".mypy_cache", ".upm", ".pythonlibs", ".cache", "build", "dist", ".pytest_cache"
}

# Determine if a path is part of the user’s project
def is_project_file(path):
    parts = path.split(os.sep)
    return not any(part in EXCLUDE_DIRS for part in parts)

# === AST Visitor: Analyze Python function calls ===
class BaseCallAnalyzer(ast.NodeVisitor):
    def __init__(self, filename):
        self.filename = filename
        self.current_func = None
        self.call_map = defaultdict(set)
        self.call_counts = defaultdict(int)
        self.defined_funcs = set()
        self.func_file_map = {}
        self.func_line_map = {}

    # Visit function definitions to track declared functions
    def visit_FunctionDef(self, node):
        self.current_func = node.name
        self.defined_funcs.add(node.name)
        self.func_file_map[node.name] = self.filename
        self.func_line_map[node.name] = node.lineno
        self.generic_visit(node)
        self.current_func = None

    # Visit calls inside function bodies to track usage
    def visit_Call(self, node):
        if self.current_func:
            func_name = self._get_call_name(node.func)
            if func_name:
                self.call_map[self.current_func].add(func_name)
                self.call_counts[func_name] += 1
        self.generic_visit(node)

    # Helper: Extract call target name
    def _get_call_name(self, node):
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return node.attr
        return None

# Check if a directory should be excluded from analysis
def should_exclude_dir(path):
    parts = path.split(os.sep)
    return any(part in EXCLUDE_DIRS for part in parts)

# Analyze the full project and return call tree data
def analyze_python_functions(base_dir="."):
    file_paths = []
    root_dir_counts = Counter()

    for root, dirs, files in os.walk(base_dir):
        if should_exclude_dir(root):
            continue
        for file in files:
            if file.endswith(".py"):
                full_path = os.path.join(root, file)
                file_paths.append(full_path)
                relative = os.path.relpath(full_path, base_dir)
                top_level = relative.split(os.sep)[0]
                root_dir_counts[top_level] += 1

    combined = BaseCallAnalyzer("<combined>")
    for path in file_paths:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                tree = ast.parse(f.read(), filename=path)
            analyzer = BaseCallAnalyzer(path)
            analyzer.visit(tree)

            for func in analyzer.defined_funcs:
                combined.defined_funcs.add(func)
                combined.func_file_map[func] = analyzer.func_file_map[func]
                combined.call_map[func].update(analyzer.call_map.get(func, set()))
                combined.func_line_map[func] = analyzer.func_line_map.get(func)

            for callee, count in analyzer.call_counts.items():
                combined.call_counts[callee] += count
        except Exception:
            continue

    return {
        "call_map": combined.call_map,
        "call_counts": combined.call_counts,
        "defined_funcs": combined.defined_funcs,
        "func_file_map": combined.func_file_map,
        "func_line_map": combined.func_line_map,
        "file_distribution": root_dir_counts,
        "total_files": len(file_paths),
        "file_paths": file_paths
    }
