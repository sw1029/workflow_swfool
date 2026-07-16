from __future__ import annotations

import ast
from pathlib import Path

from orchestrate_task_cycle.transition.context import ValidationContext
from orchestrate_task_cycle.transition.pipeline import VALIDATION_STAGES


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "orchestrate-task-cycle" / "scripts" / "orchestrate_task_cycle"


def production_modules() -> list[Path]:
    return [
        PACKAGE / "validate_cycle_transition.py",
        *sorted((PACKAGE / "transition").glob("*.py")),
    ]


def test_transition_modules_keep_bounded_clean_code_surfaces() -> None:
    for path in production_modules():
        source = path.read_text(encoding="utf-8")
        assert len(source.splitlines()) <= 500, path
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                assert node.end_lineno is not None
                assert node.end_lineno - node.lineno + 1 <= 140, (path, node.name)


def test_transition_package_uses_explicit_static_composition() -> None:
    assert VALIDATION_STAGES
    assert len({stage.__name__ for stage in VALIDATION_STAGES}) == len(
        VALIDATION_STAGES
    )
    state = ValidationContext({}, {}, "pre_context")
    for stage in VALIDATION_STAGES:
        stage(state)
    assert state.result() == {
        "status": "ok",
        "transition": "pre_context",
        "workflow_mode": "normal",
        "findings": [],
    }


def test_transition_modules_avoid_dynamic_and_wildcard_loading() -> None:
    for path in production_modules():
        source = path.read_text(encoding="utf-8")
        assert "sys.path.insert" not in source, path
        assert "spec_from_file_location" not in source, path
        tree = ast.parse(source)
        assert not any(
            isinstance(node, ast.ImportFrom)
            and any(alias.name == "*" for alias in node.names)
            for node in ast.walk(tree)
        ), path
