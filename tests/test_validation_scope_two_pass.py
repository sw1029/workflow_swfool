from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "orchestrate-task-cycle" / "scripts"))
sys.path.insert(0, str(ROOT / "plan-validation-scope" / "scripts"))
from plan_validation_scope import changed_surface, validation_scope  # noqa: E402


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


def decision_ref(*, freshness: str = "current", revision_id: str = "revision_A") -> dict[str, Any]:
    return {
        "decision_subject_id": "subject_A",
        "subject_class_id": "class_A",
        "revision_id": revision_id,
        "subject_digest": "a" * 64,
        "lineage_id": "lineage_A",
        "freshness_status": freshness,
        "body_fingerprint": {"applicability": "applicable", "value": "b" * 64},
        "production_lane": {"applicability": "not_applicable", "value": None},
        "cohort": {"applicability": "applicable", "value": ["cohort_A"]},
        "producer_run": {"applicability": "not_applicable", "value": None},
    }


def separation_gate(*, invariant_status: str = "pass") -> dict[str, Any]:
    independent = invariant_status == "pass"
    return {
        "independent_source_separation_status": "pass",
        "independent_invariant_separation_status": invariant_status,
        "verification_axes": [
            {
                "axis_id": "axis_A",
                "coupling_status": "disjoint",
                "producer_function_id": "producer_function_A",
                "verifier_function_id": "verifier_function_B",
                "producer_invariant_owner_id": "producer_owner_A",
                "verifier_invariant_owner_id": "verifier_owner_B",
                "invariant_separation_status": "independent" if independent else "coupled",
            }
        ],
    }


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


def test_stale_decision_subject_warns_in_plan_and_blocks_finalize(tmp_path: Path) -> None:
    payload = {"decision_artifact_ref": decision_ref(freshness="stale")}
    plan = build(tmp_path, mode="plan", values=["src/unit.py"], payload=payload)
    finalized = build(
        tmp_path,
        mode="finalize",
        values=["src/unit.py"],
        payload=payload,
        plan=plan,
        commands=["python -m pytest -q"],
    )

    assert plan["status"] == "warn"
    assert plan["validation_profile"] == "affected_chain"
    assert finalized["status"] == "block"
    assert finalized["finalized"] is False
    assert any(
        row["code"] == "decision_artifact_binding_not_evaluated"
        for row in finalized["findings"]
    )


def test_finalize_requires_current_identity_when_plan_declared_it(tmp_path: Path) -> None:
    plan = build(
        tmp_path,
        mode="plan",
        values=["docs/unit.md"],
        payload={"decision_artifact_ref": decision_ref()},
    )
    finalized = build(
        tmp_path,
        mode="finalize",
        values=["docs/unit.md"],
        plan=plan,
        commands=["python -m pytest -q"],
    )

    assert finalized["status"] == "block"
    assert any(
        row["code"] == "decision_artifact_ref_missing_at_finalize"
        for row in finalized["findings"]
    )


def test_source_disjoint_but_invariant_coupled_verification_cannot_finalize(
    tmp_path: Path,
) -> None:
    payload = {
        "decision_artifact_ref": decision_ref(),
        "verification_source_separation_gate": separation_gate(
            invariant_status="coupled"
        ),
    }
    plan = build(tmp_path, mode="plan", values=["src/unit.py"], payload=payload)
    finalized = build(
        tmp_path,
        mode="finalize",
        values=["src/unit.py"],
        payload=payload,
        plan=plan,
        commands=["python -m pytest -q"],
    )

    assert finalized["status"] == "block"
    assert any(
        row["code"] == "verification_separation_not_evaluated"
        for row in finalized["findings"]
    )


def test_current_subject_and_independent_verification_finalize_normally(
    tmp_path: Path,
) -> None:
    planned_payload = {
        "decision_artifact_ref": decision_ref(),
        "verification_source_separation_gate": separation_gate(),
    }
    plan = build(
        tmp_path,
        mode="plan",
        values=["docs/unit.md"],
        payload=planned_payload,
    )
    current_payload = {
        **planned_payload,
        "decision_artifact_ref": decision_ref(revision_id="revision_B"),
    }
    finalized = build(
        tmp_path,
        mode="finalize",
        values=["docs/unit.md"],
        payload=current_payload,
        plan=plan,
        commands=["python -m pytest -q"],
    )

    assert finalized["status"] == "ok"
    assert finalized["finalized"] is True
    assert finalized["decision_artifact_ref"]["revision_id"] == "revision_B"
    assert finalized["validation_profile"] == "current_only"
