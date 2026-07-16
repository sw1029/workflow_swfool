#!/usr/bin/env python3
from __future__ import annotations

import ast
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import result_contract  # noqa: E402
from result_contract_lib.base import RuleContext, RuleRegistry, TargetContractRule  # noqa: E402
from result_contract_lib.registry import default_rule_registry  # noqa: E402
from result_contract_lib.rules.completion_checks import ORDERED_CHECKS as COMPLETION_CHECKS  # noqa: E402
from result_contract_lib.rules.derive_checks import ORDERED_CHECKS as DERIVE_CHECKS  # noqa: E402


def _logical_lines(path: Path) -> int:
    return sum(
        1
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


def _largest_function(path: Path) -> int:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return max(
        (
            node.end_lineno - node.lineno + 1
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ),
        default=0,
    )


def empty_context(target: str) -> RuleContext:
    return RuleContext(
        target=target,
        result={},
        mode="block",
        findings=[],
        missing=[],
        require_context_field=lambda _field, _code, _message: None,
    )


def test_default_registry_has_one_owner_per_target() -> None:
    owners: dict[str, list[str]] = {}
    for rule in default_rule_registry().rules:
        assert isinstance(rule, TargetContractRule)
        for target in rule.targets:
            owners.setdefault(target, []).append(type(rule).__name__)

    assert owners
    assert all(len(rule_names) == 1 for rule_names in owners.values())
    assert owners["derive"] == ["DeriveRule"]
    assert owners["loopback_audit"] == ["LoopbackAuditRule"]
    assert owners["validate"] == ["CompletionValidationRule"]


def test_large_target_rules_use_bounded_ordered_check_modules() -> None:
    assert [check.__name__ for check in DERIVE_CHECKS] == [
        "check_anti_loop",
        "check_task_pack",
        "check_execution_scope",
        "check_routing_contracts",
        "check_routing_safety",
        "check_routing_outcomes",
        "check_progress_evidence",
        "check_progress_policy",
        "check_provider_setup",
        "check_provider_outcomes",
    ]
    assert [check.__name__ for check in COMPLETION_CHECKS] == [
        "check_preflight",
        "check_acceptance_facts",
        "check_artifact_facts",
        "check_operation_facts",
        "check_evaluate",
        "check_scenarios",
        "check_change_evidence",
        "check_closure",
    ]

    bounded_roots = (
        SCRIPT_DIR / "result_contract_lib" / "rules" / "derive_checks",
        SCRIPT_DIR / "result_contract_lib" / "rules" / "completion_checks",
        SCRIPT_DIR / "result_contract_lib" / "validation_pipeline",
    )
    bounded_files = [path for root in bounded_roots for path in root.glob("*.py")]
    bounded_files.extend(
        (
            SCRIPT_DIR / "result_contract.py",
            SCRIPT_DIR / "result_contract_lib" / "advice.py",
            SCRIPT_DIR / "result_contract_lib" / "decision.py",
            SCRIPT_DIR / "result_contract_lib" / "decision_verification.py",
            SCRIPT_DIR / "result_contract_lib" / "engine.py",
            SCRIPT_DIR / "result_contract_lib" / "expectations.py",
            SCRIPT_DIR / "result_contract_lib" / "metric_consumption.py",
            SCRIPT_DIR / "result_contract_lib" / "policy.py",
            SCRIPT_DIR / "result_contract_lib" / "receipts.py",
            SCRIPT_DIR / "result_contract_lib" / "verdicts.py",
            SCRIPT_DIR / "result_contract_lib" / "rules" / "derive.py",
            SCRIPT_DIR / "result_contract_lib" / "rules" / "completion.py",
        )
    )

    assert all(_logical_lines(path) < 500 for path in bounded_files)
    assert all(_largest_function(path) <= 140 for path in bounded_files)
    assert all("import *" not in path.read_text(encoding="utf-8") for path in bounded_files)
    assert all("globals()" not in path.read_text(encoding="utf-8") for path in bounded_files)


def test_rule_registry_supports_focused_extension() -> None:
    visited: list[str] = []

    class FocusedRule(TargetContractRule):
        targets = frozenset({"focused"})

        def check(self, context: RuleContext) -> None:
            visited.append(context.target)

    registry = RuleRegistry([FocusedRule()])
    registry.validate(empty_context("other"))
    registry.validate(empty_context("focused"))

    assert visited == ["focused"]


def test_validator_accepts_an_injected_registry() -> None:
    class EmptyRule(TargetContractRule):
        targets = frozenset({"run"})

        def check(self, context: RuleContext) -> None:
            context.findings.append({"severity": "warn", "code": "injected", "message": "injected"})

    validator = result_contract.ResultContractValidator(RuleRegistry([EmptyRule()]))
    output = validator.validate(
        "run",
        {"step": "run", "task_id": "task-1", "execution_status": "success", "evidence_paths": ["run.json"]},
    )

    assert any(item.get("code") == "injected" for item in output["findings"])


def test_report_rule_preserves_optional_task_pack_contract() -> None:
    packet = {
        "step": "report",
        "used_goal_truth": [],
        "used_advice": [],
        "model_effort_routing": {},
        "task_id": "task-1",
        "changed_files": [],
        "commands": [],
        "validation_verdict": "partial",
        "progress_verdict": "no_progress",
        "blockers": [],
        "progress_axes": {},
        "next_task_id": None,
        "completion_status": "partial",
    }

    result = result_contract.validate("report", packet, "block")
    codes = {finding.get("code") for finding in result["findings"]}

    assert "report_task_pack_status_missing" not in codes
    assert "report_task_pack_path_missing" not in codes
    assert "report_task_pack_item_id_missing" not in codes


def test_positive_review_blocks_conflicting_projection_alias_and_body_report_divergence() -> None:
    axes = {
        axis: {"status": "pass", "evidence_ref": f"evidence_{axis}"}
        for axis in result_contract.VERDICT_AXES
    }
    projection = {
        "verdict_contract_version": 1,
        **axes,
        "authoritative_final": "success",
    }
    projection["artifact_semantic_verdict"] = {
        "status": "fail",
        "evidence_ref": "evidence_semantic_fail",
    }
    packet = {
        "step": "qualitative_review",
        "task_id": "task_T",
        "cycle_id": "cycle_C",
        "review_status": "complete",
        "quality_verdict": "acceptable",
        "verdict_contract_version": 1,
        **axes,
        "authoritative_projection": projection,
        "report_body_divergence": True,
    }

    output = result_contract.validate("qualitative_review", packet, "warn")
    codes = {finding.get("code") for finding in output["findings"]}

    assert output["status"] == "block"
    assert "verdict_axis_conflicted" in codes
    assert "report_body_divergence" in codes


def test_duplicate_consumer_receipts_fail_closed_in_either_order() -> None:
    artifact_ref = {
        "artifact_id": "artifact_A",
        "artifact_sha256": "a" * 64,
        "production_lane_identity": "lane_L",
        "body_projection_fingerprint": "c" * 64,
        "verification_input_ids": ["source_cohort_C"],
    }
    valid = {
        "consumer_context_id": "consumer_C",
        "cycle_id": "cycle_C",
        "input_state_fingerprint": "b" * 64,
        "attempt_identity": "attempt_A",
        **artifact_ref,
        "adapter_loaded": True,
        "hook_resolved": True,
        "required_hook_callable": True,
        "hook_signature_compatible": True,
        "invocation_completed": True,
        "return_contract_valid": True,
        "artifact_identity_echo_valid": True,
        "value_consumed_by_decision": True,
        "evidence_provenance": "independently_verified",
        "probe_evidence_ref": "packet_P",
    }
    valid["probe_evidence_sha256"] = result_contract._consumer_receipt_binding_sha256(valid)
    invalid = {**valid, "value_consumed_by_decision": False}
    invalid["probe_evidence_sha256"] = result_contract._consumer_receipt_binding_sha256(invalid)

    for rows in ([valid, invalid], [invalid, valid]):
        packet = {
            "step": "loopback_audit",
            "task_id": "task_T",
            "cycle_id": "cycle_C",
            "input_state_fingerprint": "b" * 64,
            "attempt_identity": "attempt_A",
            "decision_artifact_ref": artifact_ref,
            "required_consumer_ids": ["consumer_C"],
            "consumer_context_conformance": {"rows": rows},
        }
        output = result_contract.validate("loopback_audit", packet, "block")
        assert any(
            finding.get("code") == "required_consumer_context_not_evaluated"
            for finding in output["findings"]
        )

    aliased_packet = {
        "step": "loopback_audit",
        "task_id": "task_T",
        "cycle_id": "cycle_C",
        "input_state_fingerprint": "b" * 64,
        "attempt_identity": "attempt_A",
        "decision_artifact_ref": artifact_ref,
        "required_consumer_ids": ["consumer_C"],
        "consumer_context_conformance": {"rows": [valid]},
        "adapter_consumer_conformance": {"rows": [invalid]},
    }
    aliased_output = result_contract.validate("loopback_audit", aliased_packet, "block")
    assert any(
        finding.get("code") == "required_consumer_context_not_evaluated"
        for finding in aliased_output["findings"]
    )

    malformed_alias_output = result_contract.validate(
        "loopback_audit",
        {
            **aliased_packet,
            "adapter_consumer_conformance": {"rows": "invalid"},
        },
        "block",
    )
    assert any(
        finding.get("code") == "consumer_context_conformance_alias_malformed"
        for finding in malformed_alias_output["findings"]
    )


def test_finalization_consumption_rejects_projection_alias_conflict() -> None:
    axes = {
        axis: {"status": "blocked", "evidence_ref": f"evidence_{axis}"}
        for axis in result_contract.VERDICT_AXES
    }
    negative = {
        "verdict_contract_version": 1,
        **axes,
        "authoritative_final": "blocked",
    }
    positive = {
        "verdict_contract_version": 1,
        **{
            axis: {"status": "pass", "evidence_ref": f"positive_{axis}"}
            for axis in result_contract.VERDICT_AXES
        },
        "authoritative_final": "success",
    }
    output = result_contract.validate(
        "loopback_audit",
        {
            "step": "loopback_audit",
            "task_id": "task_T",
            "finalization_receipt": {},
            "authoritative_projection": negative,
            "result": {"authoritative_projection": positive},
        },
        "block",
    )

    assert any(
        finding.get("code") == "authoritative_projection_alias_conflict"
        for finding in output["findings"]
    )


def test_finalization_consumption_rejects_receipt_alias_conflict() -> None:
    first = {
        "schema_version": 1,
        "kind": "cycle_finalization_receipt",
        "cycle_id": "cycle_C",
        "attempt_id": "attempt_A",
        "receipt_hash": "a" * 64,
    }
    second = {**first, "receipt_hash": "b" * 64}
    output = result_contract.validate(
        "loopback_audit",
        {
            "step": "loopback_audit",
            "task_id": "task_T",
            "finalization_receipt": first,
            "validation_finalization_receipt": second,
        },
        "block",
    )

    assert any(
        finding.get("code") == "finalization_receipt_alias_conflict"
        for finding in output["findings"]
    )


def main() -> int:
    test_default_registry_has_one_owner_per_target()
    test_rule_registry_supports_focused_extension()
    test_validator_accepts_an_injected_registry()
    test_report_rule_preserves_optional_task_pack_contract()
    test_positive_review_blocks_conflicting_projection_alias_and_body_report_divergence()
    test_duplicate_consumer_receipts_fail_closed_in_either_order()
    test_finalization_consumption_rejects_projection_alias_conflict()
    test_finalization_consumption_rejects_receipt_alias_conflict()
    print("result contract architecture tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
