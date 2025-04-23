# Tools/logic/python/flask_analyzer.py - Extracts Flask route decorators from Python files

import ast

# AST Visitor to extract Flask route decorators like @app.route("/path")
class FlaskRouteExtractor(ast.NodeVisitor):
    def __init__(self):
        self.route_map = {}

    def visit_FunctionDef(self, node):
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
                method = decorator.func.attr.lower()
                if method in {"route", "get", "post", "put", "delete", "patch"}:
                    try:
                        if decorator.args and isinstance(decorator.args[0], ast.Constant):
                            route_path = decorator.args[0].value
                        else:
                            route_path = "?"
                        http_method = method.upper()
                        for kw in decorator.keywords:
                            if kw.arg == "methods" and isinstance(kw.value, ast.List):
                                for elt in kw.value.elts:
                                    if isinstance(elt, ast.Constant):
                                        http_method = elt.value.upper()
                                        break
                        route_str = f"{http_method} {route_path}"
                        self.route_map[route_str] = node.name
                    except Exception:
                        pass
        self.generic_visit(node)

# Analyze a list of files and return all Flask route mappings
def extract_flask_routes(file_paths):
    routes = {}
    for path in file_paths:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                tree = ast.parse(f.read(), filename=path)
            extractor = FlaskRouteExtractor()
            extractor.visit(tree)
            routes.update(extractor.route_map)
        except Exception:
            continue
    return routes
