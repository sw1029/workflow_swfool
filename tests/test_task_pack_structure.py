from __future__ import annotations

import ast
from pathlib import Path

from orchestrate_task_cycle.task_pack import api
from orchestrate_task_cycle.task_pack import consumption, mutation_apply, storage, validation


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = ROOT / "orchestrate-task-cycle" / "scripts" / "orchestrate_task_cycle" / "task_pack"


def test_task_pack_facade_reexports_established_entrypoints() -> None:
    assert api.command_apply_mutation is mutation_apply.command_apply_mutation
    assert api._command_apply_mutation_locked is mutation_apply._command_apply_mutation_locked
    assert api.command_mark_consumed is consumption.command_mark_consumed
    assert api.validate_pack is validation.validate_pack
    assert api.ContentAddressedWriteTransaction is storage.ContentAddressedWriteTransaction
    assert api.task_pack_replacement.__name__.endswith("replacement_engine")


def test_task_pack_modules_stay_bounded_and_do_not_import_the_facade() -> None:
    paths = sorted(PACKAGE_DIR.glob("*.py"))
    for path in paths:
        source = path.read_text(encoding="utf-8")
        assert len(source.splitlines()) < 500, path
        tree = ast.parse(source)
        oversized_symbols = [
            (node.name, node.end_lineno - node.lineno + 1)
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and node.end_lineno - node.lineno + 1 >= 140
        ]
        assert not oversized_symbols, (path, oversized_symbols)
        assert not any(
            isinstance(node, ast.Import) and any(alias.name == "task_pack_queue" for alias in node.names)
            or isinstance(node, ast.ImportFrom) and node.module == "task_pack_queue"
            for node in ast.walk(tree)
        ), path
        assert not any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "globals"
            for node in ast.walk(tree)
        ), path
