from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


changed_surface = load_module(
    ROOT / "plan-validation-scope" / "scripts" / "changed_surface.py",
    "changed_surface_two_pass",
)
validation_scope = load_module(
    ROOT / "plan-validation-scope" / "scripts" / "validation_scope.py",
    "validation_scope_two_pass",
)


def build(
    tmp_path: Path,
    *,
    mode: str,
    values: list[str],
    known: bool = True,
    payload: dict[str, Any] | None = None,
    plan: dict[str, Any] | None = None,
    commands: list[str] | None = None,
) -> dict[str, Any]:
    return validation_scope.build_manifest(
        root=tmp_path,
        mode=mode,
        task_id="task-1",
        values=values,
        files_known=known,
        payload=payload or {},
        plan=plan,
        required_commands=commands or [],
        reused_prerequisites=[],
        escalation_reasons=[],
    )


def test_changed_surface_classifies_skill_contract_and_task_state() -> None:
    assert changed_surface.classify_path("some-skill/SKILL.md") == "contract"
    assert changed_surface.classify_path(".task/index.jsonl") == "task_state"
    assert changed_surface.classify_path("tests/test_flow.py") == "tests"


def test_changed_surface_does_not_normalize_parent_traversal_into_workspace(tmp_path: Path) -> None:
    classified = changed_surface.classify_files(tmp_path, ["../outside.py"])

    assert classified["changed_files"] == ["../outside.py"]
    assert classified["changed_surfaces"] == ["source"]


def test_plan_selects_affected_chain_for_source_change(tmp_path: Path) -> None:
    manifest = build(tmp_path, mode="plan", values=["src/app.py"])

    assert manifest["status"] == "ok"
    assert manifest["validation_profile"] == "affected_chain"
    assert manifest["planned_changed_files"] == ["src/app.py"]


def test_finalize_never_lowers_plan_and_escalates_explicit_shared_runtime(tmp_path: Path) -> None:
    plan = build(tmp_path, mode="plan", values=["docs/note.md"])
    manifest = build(
        tmp_path,
        mode="finalize",
        values=["pyproject.toml"],
        payload={"shared_runtime_change": True},
        plan=plan,
        commands=["python -m pytest -q"],
    )

    assert plan["validation_profile"] == "current_only"
    assert manifest["validation_profile"] == "full_chain"
    assert manifest["profile_changed"] is True
    assert manifest["finalized"] is True


def test_finalize_fails_closed_when_actual_surface_is_unknown(tmp_path: Path) -> None:
    plan = build(tmp_path, mode="plan", values=["src/app.py"])
    manifest = build(
        tmp_path,
        mode="finalize",
        values=[],
        known=False,
        plan=plan,
        commands=["python -m pytest -q"],
    )

    assert manifest["status"] == "block"
    assert manifest["finalized"] is False
    assert any(item["code"] == "changed_surface_unknown" for item in manifest["findings"])


def test_string_false_does_not_enable_full_chain(tmp_path: Path) -> None:
    manifest = build(
        tmp_path,
        mode="plan",
        values=["docs/note.md"],
        payload={"explicit_full_chain": "false"},
    )

    assert manifest["validation_profile"] == "current_only"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("step", "validation_scope_finalize", "validation_scope_plan"),
        ("mode", "finalize", "mode=plan"),
        ("finalized", True, "unfinalized"),
        ("task_id", "task-other", "does not match"),
        ("task_id", "unknown-task", "non-placeholder"),
    ],
)
def test_finalize_rejects_invalid_or_cross_task_plan_identity(
    tmp_path: Path,
    field: str,
    value: Any,
    message: str,
) -> None:
    plan = build(tmp_path, mode="plan", values=["src/app.py"], commands=["python -m pytest -q"])
    plan[field] = value

    with pytest.raises(ValueError, match=message):
        build(
            tmp_path,
            mode="finalize",
            values=["src/app.py"],
            plan=plan,
            commands=["python -m pytest -q"],
        )


def test_validation_scope_output_path_stays_inside_workspace_and_rejects_symlink_escape(tmp_path: Path) -> None:
    assert validation_scope.workspace_output_path(tmp_path, ".task/scope.json") == tmp_path / ".task" / "scope.json"

    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    with pytest.raises(ValueError, match="workspace root"):
        validation_scope.workspace_output_path(tmp_path, str(outside / "scope.json"))

    link = tmp_path / "linked-output"
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symlinks"):
        validation_scope.workspace_output_path(tmp_path, "linked-output/scope.json")


def test_finalize_rejects_placeholder_current_task_id(tmp_path: Path) -> None:
    plan = build(tmp_path, mode="plan", values=["src/app.py"], commands=["python -m pytest -q"])

    with pytest.raises(ValueError, match="non-placeholder task_id"):
        validation_scope.build_manifest(
            root=tmp_path,
            mode="finalize",
            task_id="unknown-task",
            values=["src/app.py"],
            files_known=True,
            payload={},
            plan=plan,
            required_commands=["python -m pytest -q"],
            reused_prerequisites=[],
            escalation_reasons=[],
        )
