"""
Phase 6: AST guard for proof script safety validation.
Validates proof scripts using Python AST to reject unsafe imports, functions, and dunder access.
"""

import ast

class ProofGuardVisitor(ast.NodeVisitor):
    def __init__(self):
        self.errors = []

    def visit_Import(self, node):
        allowed_modules = {"pandas", "decimal", "pathlib", "json"}
        for alias in node.names:
            if alias.name not in allowed_modules:
                self.errors.append(f"Forbidden module import: {alias.name}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        allowed_modules = {"pandas", "decimal", "pathlib", "json"}
        if node.module not in allowed_modules:
            self.errors.append(f"Forbidden module import from: {node.module}")
        self.generic_visit(node)

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name):
            forbidden_funcs = {"eval", "exec", "compile", "__import__", "open", "subprocess"}
            if node.func.id in forbidden_funcs:
                self.errors.append(f"Forbidden function call: {node.func.id}")
        self.generic_visit(node)

    def visit_Attribute(self, node):
        if node.attr.startswith("__") and node.attr.endswith("__"):
            self.errors.append(f"Forbidden dunder attribute access: {node.attr}")
        self.generic_visit(node)

def validate_proof_script_ast(script_content: str) -> bool:
    try:
        tree = ast.parse(script_content)
        visitor = ProofGuardVisitor()
        visitor.visit(tree)
        return len(visitor.errors) == 0
    except Exception:
        return False

