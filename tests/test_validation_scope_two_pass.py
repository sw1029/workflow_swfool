from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "orchestrate-task-cycle" / "scripts"))
sys.path.insert(0, str(ROOT / "plan-validation-scope" / "scripts"))
from plan_validation_scope import changed_surface, validation_scope  # noqa: E402
from orchestrate_task_cycle.result_contract.acceptance_satisfiability import (  # noqa: E402
    assess_contract_satisfiability,
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


def satisfiability_payload(
    *,
    conflict: bool = False,
    unverifiable: bool = False,
) -> dict[str, Any]:
    criterion = {
        "criterion_id": "EVENT_REF",
        "predicate_id": "EVIDENCE_REF",
        "required_output_classes": ["BODY_REF"],
        "required_non_empty_output_classes": ["BODY_REF"],
        "required_mutation_surfaces": ["SUBJECT_REF"],
        "required_verifier_input_classes": ["SOURCE_UNIT_REF"],
        "required_freshness_class": "fresh_producer_execution",
        "requires_body_movement": True,
    }
    directive = {
        "producer_directive_id": "ENTITY_REF",
        "criterion_ids": ["EVENT_REF"],
        "permitted_output_classes": [] if conflict else ["BODY_REF"],
        "guaranteed_non_empty_output_classes": ["BODY_REF"],
        "allowed_task_mutation_surfaces": ["SUBJECT_REF"],
        "verifier_observable_output_classes": (
            [] if unverifiable else ["SOURCE_UNIT_REF"]
        ),
        "satisfying_execution_paths": [] if unverifiable else ["WORK_REF"],
        "producer_execution_allowed": True,
        "body_mutation_allowed": True,
        "local_repair_routes": ["WORK_REF"],
    }
    payload: dict[str, Any] = {
        "validation_predicate_contract": {"criteria": [criterion]},
        "producer_directives": [directive],
        "evidence_paths": ["EVIDENCE_REF"],
    }
    assessment = assess_contract_satisfiability(payload)
    payload["validation_predicate_contract"]["satisfiability_rows"] = list(
        assessment.expected_rows
    )
    payload["mutually_unsatisfiable_contract"] = (
        assessment.mutually_unsatisfiable
    )
    payload["unverifiable_acceptance_contract"] = assessment.unverifiable
    return payload


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


def test_stale_decision_subject_blocks_plan_and_cannot_be_rebound_at_finalize(
    tmp_path: Path,
) -> None:
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
    rebound = build(
        tmp_path,
        mode="finalize",
        values=["src/unit.py"],
        payload={"decision_artifact_ref": decision_ref()},
        plan=plan,
        commands=["python -m pytest -q"],
    )

    assert plan["status"] == "block"
    assert plan["validation_profile"] == "affected_chain"
    assert finalized["status"] == "block"
    assert finalized["finalized"] is False
    assert any(
        row["code"] == "decision_artifact_binding_not_evaluated"
        for row in finalized["findings"]
    )
    assert rebound["status"] == "block"
    assert any(
        row["code"] == "decision_artifact_binding_not_evaluated"
        for row in rebound["findings"]
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


def test_changed_revision_cannot_rebind_the_same_validation_attempt(
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

    assert finalized["status"] == "block"
    assert finalized["finalized"] is False
    assert any(
        row["code"] == "decision_artifact_subject_changed"
        for row in finalized["findings"]
    )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda ref: ref.update(subject_digest="c" * 64),
        lambda ref: ref["body_fingerprint"].update(value="d" * 64),
        lambda ref: ref["cohort"].update(value=["cohort_B"]),
    ],
)
def test_changed_digest_or_applicable_dimension_cannot_finalize(
    tmp_path: Path,
    mutate: Any,
) -> None:
    planned_ref = decision_ref()
    plan = build(
        tmp_path,
        mode="plan",
        values=["docs/unit.md"],
        payload={"decision_artifact_ref": planned_ref},
    )
    current_ref = json.loads(json.dumps(planned_ref))
    mutate(current_ref)

    finalized = build(
        tmp_path,
        mode="finalize",
        values=["docs/unit.md"],
        payload={"decision_artifact_ref": current_ref},
        plan=plan,
        commands=["python -m pytest -q"],
    )

    assert finalized["status"] == "block"
    assert any(
        row["code"] == "decision_artifact_subject_changed"
        for row in finalized["findings"]
    )


def test_exact_identity_and_not_applicable_dimensions_finalize_normally(
    tmp_path: Path,
) -> None:
    payload = {
        "decision_artifact_ref": decision_ref(),
        "verification_source_separation_gate": separation_gate(),
    }
    plan = build(tmp_path, mode="plan", values=["docs/unit.md"], payload=payload)
    finalized = build(
        tmp_path,
        mode="finalize",
        values=["docs/unit.md"],
        payload=payload,
        plan=plan,
        commands=["python -m pytest -q"],
    )

    assert finalized["status"] == "ok"
    assert finalized["finalized"] is True
    assert finalized["validation_profile"] == "current_only"


def test_satisfiable_predicate_contract_is_preserved_and_finalizes(
    tmp_path: Path,
) -> None:
    payload = satisfiability_payload()
    plan = build(tmp_path, mode="plan", values=["docs/unit.md"], payload=payload)
    finalized = build(
        tmp_path,
        mode="finalize",
        values=["docs/unit.md"],
        payload=payload,
        plan=plan,
        commands=["python -m pytest -q"],
    )

    assert plan["validation_predicate_contract"] == payload[
        "validation_predicate_contract"
    ]
    assert finalized["status"] == "ok"
    assert finalized["finalized"] is True


@pytest.mark.parametrize(
    ("payload", "expected_code"),
    [
        (satisfiability_payload(conflict=True), "acceptance_satisfiability_failed"),
        (
            satisfiability_payload(unverifiable=True),
            "acceptance_satisfiability_not_evaluated",
        ),
    ],
)
def test_failed_or_unevaluated_satisfiability_blocks_finalization(
    tmp_path: Path,
    payload: dict[str, Any],
    expected_code: str,
) -> None:
    plan = build(tmp_path, mode="plan", values=["docs/unit.md"], payload=payload)
    finalized = build(
        tmp_path,
        mode="finalize",
        values=["docs/unit.md"],
        payload=payload,
        plan=plan,
        commands=["python -m pytest -q"],
    )

    assert plan["status"] == "block"
    assert finalized["status"] == "block"
    assert any(row["code"] == expected_code for row in finalized["findings"])


def test_forged_satisfiability_pass_and_missing_finalize_contract_are_blocked(
    tmp_path: Path,
) -> None:
    payload = satisfiability_payload(conflict=True)
    payload["validation_predicate_contract"]["satisfiability_rows"][0][
        "evaluation_status"
    ] = "pass"
    plan = build(tmp_path, mode="plan", values=["docs/unit.md"], payload=payload)
    forged = build(
        tmp_path,
        mode="finalize",
        values=["docs/unit.md"],
        payload=payload,
        plan=plan,
        commands=["python -m pytest -q"],
    )
    missing = build(
        tmp_path,
        mode="finalize",
        values=["docs/unit.md"],
        plan=plan,
        commands=["python -m pytest -q"],
    )

    assert plan["status"] == "block"
    assert any(
        row["code"] == "acceptance_satisfiability_claim_mismatch"
        for row in forged["findings"]
    )
    assert any(
        row["code"] == "validation_predicate_contract_missing_at_finalize"
        for row in missing["findings"]
    )
