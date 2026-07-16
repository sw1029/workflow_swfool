from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "manage-task-state-index" / "scripts"
PACKAGE_DIR = SCRIPT_DIR / "manage_task_state_index"
STATE_DIR = PACKAGE_DIR / "state"
MIGRATION_DIR = PACKAGE_DIR / "migration"


def _python_files() -> list[Path]:
    return sorted((*STATE_DIR.rglob("*.py"), *MIGRATION_DIR.rglob("*.py")))


def test_task_state_facades_and_modules_stay_below_hard_size_budgets() -> None:
    paths = [
        PACKAGE_DIR / "index.py",
        *_python_files(),
    ]
    oversized_files: dict[str, int] = {}
    oversized_symbols: dict[str, int] = {}
    for path in paths:
        source = path.read_text(encoding="utf-8")
        line_count = len(source.splitlines())
        if line_count >= 500:
            oversized_files[path.relative_to(ROOT).as_posix()] = line_count
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            symbol_size = (node.end_lineno or node.lineno) - node.lineno + 1
            if symbol_size >= 140:
                key = f"{path.relative_to(ROOT).as_posix()}::{node.name}"
                oversized_symbols[key] = symbol_size
    assert oversized_files == {}
    assert oversized_symbols == {}


def test_task_state_producer_keeps_verifier_and_agent_log_migration_boundaries() -> None:
    forbidden = ("task_state_migration_verifier", "agent_log_migration")
    violations: list[str] = []
    for path in _python_files():
        source = path.read_text(encoding="utf-8")
        if any(name in source for name in forbidden):
            violations.append(path.relative_to(ROOT).as_posix())
    assert violations == []


def test_task_state_package_imports_without_facade_bootstrap() -> None:
    code = (
        "import sys; "
        f"sys.path.insert(0, {str(SCRIPT_DIR)!r}); "
        f"sys.path.insert(0, {str(ROOT / 'record-agent-work-log' / 'scripts')!r}); "
        "import manage_task_state_index.state.artifacts, manage_task_state_index.state.scan_service"
    )
    completed = subprocess.run(
        [sys.executable, "-I", "-c", code],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
