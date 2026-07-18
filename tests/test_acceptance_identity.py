from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [
    str(ROOT / "normalize-acceptance-and-demo" / "scripts"),
    str(ROOT / "orchestrate-task-cycle" / "scripts"),
]
from normalize_acceptance_and_demo import acceptance_identity  # noqa: E402
from orchestrate_task_cycle.result_contract import api as result_contract  # noqa: E402


def final_packet() -> dict[str, Any]:
    return {
        "acceptance_status": "normalized",
        "acceptance_criteria": ["The deterministic contract tests pass."],
        "blockers": [],
        "evidence_paths": ["acceptance-source.json"],
    }


def test_identity_binds_exact_task_revision_and_changes_after_edit(tmp_path: Path) -> None:
    task = tmp_path / "task.md"
    task.write_text("# Task\n\nFirst revision.\n", encoding="utf-8")
    first = acceptance_identity.bind(tmp_path, "task-1", "task.md", final_packet(), True)
    task.write_text("# Task\n\nSecond revision.\n", encoding="utf-8")
    second = acceptance_identity.bind(tmp_path, "task-1", "task.md", final_packet(), True)

    assert first["acceptance_id"] != second["acceptance_id"]
    assert first["acceptance_provenance"]["source_task_fingerprint"] != second["acceptance_provenance"]["source_task_fingerprint"]
    assert second["acceptance_provenance"]["source_task_path"] == "task.md"


def test_identity_rejects_packet_for_another_task(tmp_path: Path) -> None:
    (tmp_path / "task.md").write_text("# Task\n", encoding="utf-8")
    packet = final_packet()
    packet["task_id"] = "task-other"

    with pytest.raises(acceptance_identity.AcceptanceIdentityError, match="does not match"):
        acceptance_identity.bind(tmp_path, "task-1", "task.md", packet, True)


def test_final_identity_requires_explicit_contract_fields(tmp_path: Path) -> None:
    (tmp_path / "task.md").write_text("# Task\n", encoding="utf-8")

    with pytest.raises(acceptance_identity.AcceptanceIdentityError, match="acceptance_status"):
        acceptance_identity.bind(tmp_path, "task-1", "task.md", {}, True)


def test_identity_rejects_task_path_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-task.md"
    outside.write_text("# Outside\n", encoding="utf-8")

    with pytest.raises(acceptance_identity.AcceptanceIdentityError, match="escapes"):
        acceptance_identity.bind(tmp_path, "task-1", str(outside), final_packet(), True)


@pytest.mark.parametrize("criterion", [None, {}, [], "   "])
def test_final_identity_rejects_semantically_empty_criteria(tmp_path: Path, criterion: Any) -> None:
    (tmp_path / "task.md").write_text("# Task\n", encoding="utf-8")
    packet = final_packet()
    packet["acceptance_criteria"] = [criterion]

    with pytest.raises(acceptance_identity.AcceptanceIdentityError, match="semantically empty"):
        acceptance_identity.bind(tmp_path, "task-1", "task.md", packet, True)


def test_acceptance_result_contract_rejects_semantically_empty_criterion() -> None:
    result = result_contract.validate(
        "acceptance",
        {
            "step": "acceptance",
            "acceptance_id": "acceptance-task-1",
            "task_id": "task-1",
            "acceptance_status": "normalized",
            "acceptance_provenance": {
                "source_task_id": "task-1",
                "source_task_path": "task.md",
                "source_task_fingerprint": "a" * 64,
            },
            "acceptance_criteria": [None],
            "blockers": [],
            "evidence_paths": ["task.md"],
        },
        "block",
    )

    assert result["status"] == "block"
    assert any(finding["code"] == "semantically_empty_acceptance_criteria" for finding in result["findings"])


def test_acceptance_result_contract_rejects_semantically_empty_blocker() -> None:
    result = result_contract.validate(
        "acceptance",
        {
            "step": "acceptance",
            "acceptance_id": "acceptance-task-1",
            "task_id": "task-1",
            "acceptance_status": "blocked",
            "acceptance_provenance": {
                "source_task_id": "task-1",
                "source_task_path": "task.md",
                "source_task_fingerprint": "a" * 64,
            },
            "acceptance_criteria": ["A concrete outcome is required."],
            "blockers": ["   "],
            "evidence_paths": ["task.md"],
        },
        "block",
    )

    assert result["status"] == "block"
    assert any(finding["code"] == "semantically_empty_acceptance_blocker" for finding in result["findings"])


def test_normalized_scenario_acceptance_requires_opaque_premise_contract() -> None:
    packet = {
        "step": "acceptance",
        "acceptance_id": "acceptance-task-1",
        "task_id": "task-1",
        "acceptance_status": "normalized",
        "acceptance_provenance": {
            "source_task_id": "task-1",
            "source_task_path": "task.md",
            "source_task_fingerprint": "a" * 64,
        },
        "acceptance_criteria": ["Exercise the conditional outcome."],
        "acceptance_scenarios": [
            {
                "scenario_id": "scenario_A",
                "expected_terminal_state": "blocked",
            }
        ],
        "blockers": [],
        "evidence_paths": ["task.md"],
    }

    result = result_contract.validate("acceptance", packet, "block")

    assert "acceptance_scenario_contract_malformed" in {
        finding["code"] for finding in result["findings"]
    }
    assert result["status"] == "block"


def test_not_applicable_scenario_declaration_does_not_block_normalization() -> None:
    packet = {
        "step": "acceptance",
        "acceptance_id": "acceptance-task-1",
        "task_id": "task-1",
        "acceptance_status": "normalized",
        "acceptance_provenance": {
            "source_task_id": "task-1",
            "source_task_path": "task.md",
            "source_task_fingerprint": "a" * 64,
        },
        "acceptance_criteria": ["Preserve the non-applicable scenario path."],
        "acceptance_scenarios": [{"applicability": "not_applicable"}],
        "blockers": [],
        "evidence_paths": ["task.md"],
    }

    result = result_contract.validate("acceptance", packet, "block")

    assert "acceptance_scenario_contract_malformed" not in {
        finding["code"] for finding in result["findings"]
    }


@pytest.mark.parametrize(
    ("status", "blockers", "message"),
    [
        ("normalized", ["still unresolved"], "cannot retain blockers"),
        ("blocked", [], "requires a concrete blocker"),
        ("blocked", ["   "], "semantically empty blocker"),
        ("needs_review", [], "requires a concrete blocker"),
    ],
)
def test_final_identity_enforces_status_blocker_consistency(
    tmp_path: Path,
    status: str,
    blockers: list[str],
    message: str,
) -> None:
    (tmp_path / "task.md").write_text("# Task\n", encoding="utf-8")
    packet = final_packet()
    packet["acceptance_status"] = status
    packet["blockers"] = blockers

    with pytest.raises(acceptance_identity.AcceptanceIdentityError, match=message):
        acceptance_identity.bind(tmp_path, "task-1", "task.md", packet, True)


def satisfiable_contract_fields() -> dict[str, Any]:
    criterion = {
        "criterion_id": "criterion_A",
        "predicate_id": "predicate_A",
        "required_output_classes": ["body"],
        "required_non_empty_output_classes": ["body"],
        "required_mutation_surfaces": ["producer"],
        "required_verifier_input_classes": ["body"],
        "required_freshness_class": "fresh_producer_execution",
        "requires_body_movement": True,
    }
    directive = {
        "producer_directive_id": "directive_A",
        "criterion_ids": ["criterion_A"],
        "permitted_output_classes": ["body"],
        "guaranteed_non_empty_output_classes": ["body"],
        "allowed_task_mutation_surfaces": ["producer"],
        "verifier_observable_output_classes": ["body"],
        "satisfying_execution_paths": ["bounded_execution"],
        "producer_execution_allowed": True,
        "body_mutation_allowed": True,
        "local_repair_routes": ["same_task_contract_repair"],
    }
    return {
        "validation_predicate_contract": {"criteria": [criterion]},
        "producer_directives": {"directives": [directive]},
    }


def test_normalizer_and_result_contract_share_satisfiability_happy_path(
    tmp_path: Path,
) -> None:
    (tmp_path / "task.md").write_text("# Task\n", encoding="utf-8")
    packet = {**final_packet(), **satisfiable_contract_fields()}

    normalized = acceptance_identity.bind(
        tmp_path, "task-1", "task.md", packet, True
    )
    result = result_contract.validate("acceptance", normalized, "block")

    assert result["status"] == "ok"
    assert normalized["validation_predicate_contract"]["satisfiability_rows"][0][
        "evaluation_status"
    ] == "pass"
    assert normalized["mutually_unsatisfiable_contract"] is False
    assert normalized["unverifiable_acceptance_contract"] is False


def test_satisfiability_identity_tokens_are_canonicalized_before_consumption(
    tmp_path: Path,
) -> None:
    (tmp_path / "task.md").write_text("# Task\n", encoding="utf-8")
    fields = satisfiable_contract_fields()
    criterion = fields["validation_predicate_contract"]["criteria"][0]
    directive = fields["producer_directives"]["directives"][0]
    criterion["criterion_id"] = " criterion_A "
    criterion["predicate_id"] = " predicate_A "
    criterion["required_freshness_class"] = " fresh_producer_execution "
    directive["criterion_ids"] = [" criterion_A "]
    packet = {**final_packet(), **fields}

    normalized = acceptance_identity.bind(
        tmp_path, "task-1", "task.md", packet, True
    )
    result = result_contract.validate("acceptance", normalized, "block")

    row = normalized["validation_predicate_contract"]["satisfiability_rows"][0]
    assert row["criterion_id"] == "criterion_A"
    assert row["predicate_id"] == "predicate_A"
    assert result["status"] == "ok"


def fake_satisfiability_pass_packet() -> dict[str, Any]:
    fields = satisfiable_contract_fields()
    directive = fields["producer_directives"]["directives"][0]
    directive.update(
        permitted_output_classes=[],
        guaranteed_non_empty_output_classes=[],
        allowed_task_mutation_surfaces=[],
        verifier_observable_output_classes=[],
        satisfying_execution_paths=[],
        producer_execution_allowed=False,
        body_mutation_allowed=False,
    )
    fields["validation_predicate_contract"]["satisfiability_rows"] = [
        {
            "criterion_id": "criterion_A",
            "predicate_id": "predicate_A",
            "producer_directive_id": "directive_A",
            "affected_output_classes": ["body"],
            "evaluation_status": "pass",
            "conflict_class": "none",
            "local_repair_possible": False,
            "evidence_refs": ["task.md"],
        }
    ]
    return {
        "step": "acceptance",
        "acceptance_id": "acceptance-task-1",
        "task_id": "task-1",
        "acceptance_status": "normalized",
        "acceptance_provenance": {
            "source_task_id": "task-1",
            "source_task_path": "task.md",
            "source_task_fingerprint": "a" * 64,
        },
        "acceptance_criteria": ["Produce a fresh non-empty body."],
        "blockers": [],
        "evidence_paths": ["task.md"],
        "mutually_unsatisfiable_contract": False,
        "unverifiable_acceptance_contract": False,
        **fields,
    }


def test_result_contract_recomputes_and_rejects_fake_satisfiability_pass() -> None:
    packet = fake_satisfiability_pass_packet()

    result = result_contract.validate("acceptance", packet, "block")
    codes = {finding["code"] for finding in result["findings"]}

    assert result["status"] == "block"
    assert "acceptance_satisfiability_claim_mismatch" in codes
    assert "normalized_acceptance_contract_not_satisfiable" in codes


@pytest.mark.parametrize("target", ["derive", "loopback_audit", "validate"])
def test_every_downstream_owner_rejects_fake_satisfiability_pass(
    target: str,
) -> None:
    result = result_contract.validate(
        target, fake_satisfiability_pass_packet(), "block"
    )

    assert "acceptance_satisfiability_claim_mismatch" in {
        finding["code"] for finding in result["findings"]
    }
