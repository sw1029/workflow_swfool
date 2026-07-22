"""Privacy-safe Python AST extraction for architecture facts."""

from __future__ import annotations

import ast
import copy
from typing import Any

from .contracts import object_sha256


class _NormalizedAst(ast.NodeTransformer):
    """Erase incidental names and literal values before behavioral hashing."""

    def visit_Name(self, node: ast.Name) -> ast.AST:  # noqa: N802
        return ast.copy_location(ast.Name(id="_name", ctx=node.ctx), node)

    def visit_arg(self, node: ast.arg) -> ast.AST:  # noqa: N802
        return ast.copy_location(ast.arg(arg="_arg", annotation=None), node)

    def visit_Constant(self, node: ast.Constant) -> ast.AST:  # noqa: N802
        marker = f"<{type(node.value).__name__}>"
        return ast.copy_location(ast.Constant(value=marker), node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:  # noqa: N802
        value = self.generic_visit(node)
        assert isinstance(value, ast.FunctionDef)
        value.name = "_function"
        value.decorator_list = []
        value.returns = None
        return value

    def visit_AsyncFunctionDef(  # noqa: N802
        self, node: ast.AsyncFunctionDef
    ) -> ast.AST:
        value = self.generic_visit(node)
        assert isinstance(value, ast.AsyncFunctionDef)
        value.name = "_function"
        value.decorator_list = []
        value.returns = None
        return value


def _qualified_expression(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _qualified_expression(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    if isinstance(node, ast.Subscript):
        return _qualified_expression(node.value)
    return None


def _function_signature(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> dict[str, Any]:
    args = node.args
    return {
        "positional_arg_count": len(args.posonlyargs) + len(args.args),
        "keyword_only_arg_count": len(args.kwonlyargs),
        "has_vararg": args.vararg is not None,
        "has_kwarg": args.kwarg is not None,
        "is_async": isinstance(node, ast.AsyncFunctionDef),
    }


def _normalized_digest(node: ast.AST) -> str:
    normalized = _NormalizedAst().visit(copy.deepcopy(node))
    ast.fix_missing_locations(normalized)
    return object_sha256(ast.dump(normalized, include_attributes=False))


class _SymbolCollector(ast.NodeVisitor):
    def __init__(self, module_id: str) -> None:
        self.module_id = module_id
        self.stack: list[str] = []
        self.symbols: list[dict[str, Any]] = []
        self.calls: list[dict[str, Any]] = []

    def _qualified(self, name: str) -> str:
        return ".".join((self.module_id, *self.stack, name))

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        qualified = self._qualified(node.name)
        bases = sorted(
            value
            for value in (_qualified_expression(base) for base in node.bases)
            if value
        )
        decorators = sorted(
            value
            for value in (_qualified_expression(item) for item in node.decorator_list)
            if value
        )
        methods = sorted(
            item.name
            for item in node.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        )
        self.symbols.append(
            {
                "qualified_name": qualified,
                "local_name": node.name,
                "kind": "class",
                "line_span": max(
                    1,
                    int(getattr(node, "end_lineno", node.lineno))
                    - node.lineno
                    + 1,
                ),
                "bases": bases,
                "decorators": decorators,
                "methods": methods,
                "is_protocol": any(value.endswith("Protocol") for value in bases),
                "is_abstract": any(
                    value.endswith(("ABC", "ABCMeta")) for value in bases
                )
                or "abstractmethod" in decorators,
                "normalized_ast_sha256": _normalized_digest(node),
            }
        )
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def _visit_function(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> None:
        qualified = self._qualified(node.name)
        self.symbols.append(
            {
                "qualified_name": qualified,
                "local_name": node.name,
                "kind": "async_function"
                if isinstance(node, ast.AsyncFunctionDef)
                else "function",
                "line_span": max(
                    1,
                    int(getattr(node, "end_lineno", node.lineno))
                    - node.lineno
                    + 1,
                ),
                "signature": _function_signature(node),
                "normalized_ast_sha256": _normalized_digest(node),
            }
        )
        self.stack.append(node.name)
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue
            target = _qualified_expression(child.func)
            if target:
                self.calls.append(
                    {
                        "caller": qualified,
                        "callee": target,
                        "dynamic": target
                        in {"__import__", "eval", "exec", "importlib.import_module"},
                    }
                )
        self.generic_visit(node)
        self.stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._visit_function(node)

    def visit_AsyncFunctionDef(  # noqa: N802
        self, node: ast.AsyncFunctionDef
    ) -> None:
        self._visit_function(node)


def _module_effects(tree: ast.Module) -> tuple[list[str], int]:
    effects: list[str] = []
    dynamic_import_count = 0
    declarations = (
        ast.Import,
        ast.ImportFrom,
        ast.FunctionDef,
        ast.AsyncFunctionDef,
        ast.ClassDef,
        ast.Pass,
    )
    for node in tree.body:
        if isinstance(node, declarations):
            continue
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            continue
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            value = getattr(node, "value", None)
            if not isinstance(value, (ast.Call, ast.Await, ast.Yield, ast.YieldFrom)):
                continue
            effects.append("assignment_runtime_expression")
        elif isinstance(node, ast.If) and isinstance(node.test, ast.Compare):
            effects.append("conditional_module_execution")
        else:
            effects.append(type(node).__name__.lower())
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _qualified_expression(node.func) in {
            "__import__",
            "importlib.import_module",
        }:
            dynamic_import_count += 1
    return sorted(set(effects)), dynamic_import_count


def analyze_python_source(
    source: str, *, filename: str, module_id: str
) -> dict[str, Any]:
    tree = ast.parse(source, filename=filename)
    collector = _SymbolCollector(module_id)
    collector.visit(tree)
    effects, dynamic_count = _module_effects(tree)
    return {
        "symbols": collector.symbols,
        "calls": collector.calls,
        "top_level_effect_kinds": effects,
        "dynamic_import_count": dynamic_count,
    }


__all__ = ("analyze_python_source",)
