from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "orchestrate-task-cycle" / "scripts"
PACKAGE_DIR = SCRIPT_DIR / "task_pack_lib"


def load_facade():
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    spec = importlib.util.spec_from_file_location("task_pack_structure_facade", SCRIPT_DIR / "task_pack_queue.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_task_pack_facade_reexports_established_entrypoints() -> None:
    facade = load_facade()

    from task_pack_lib import consumption, mutation_apply, storage, validation

    assert facade.command_apply_mutation is mutation_apply.command_apply_mutation
    assert facade._command_apply_mutation_locked is mutation_apply._command_apply_mutation_locked
    assert facade.command_mark_consumed is consumption.command_mark_consumed
    assert facade.validate_pack is validation.validate_pack
    assert facade.ContentAddressedWriteTransaction is storage.ContentAddressedWriteTransaction
    assert facade.task_pack_replacement.__name__ == "task_pack_replacement"


def test_task_pack_modules_stay_bounded_and_do_not_import_the_facade() -> None:
    paths = [SCRIPT_DIR / "task_pack_queue.py", *sorted(PACKAGE_DIR.glob("*.py"))]
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
