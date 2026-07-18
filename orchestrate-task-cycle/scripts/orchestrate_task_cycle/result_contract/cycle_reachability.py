"""Cycle-reachability transport, binding, and harvest receipt checks."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
from typing import Any


PENDING_REACHABILITY_STATUSES = {
    "launching",
    "running",
    "completed_pending_validation",
    "stale",
    "not_running",
}


def canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _deep_get(value: object, path: str) -> object:
    current = value
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def first_declared(value: dict[str, Any], paths: tuple[str, ...]) -> object:
    for path in paths:
        item = _deep_get(value, path)
        if item is not None:
            return item
    return None


def _opaque(value: object) -> str | None:
    text = str(value or "").strip()
    if not text or len(text) > 255 or any(ord(char) < 32 for char in text):
        return None
    return text


def _positive(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and parsed > 0 else None


def _full_sha(value: object) -> str | None:
    text = str(value or "").strip().lower()
    return (
        text
        if len(text) == 64 and all(char in "0123456789abcdef" for char in text)
        else None
    )


def _string_set(value: object) -> set[str] | None:
    if not isinstance(value, list) or not value:
        return None
    items = [_opaque(item) for item in value]
    if any(item is None for item in items) or len(items) != len(set(items)):
        return None
    return {str(item) for item in items}


def cycle_gate_from_result(result: dict[str, Any]) -> dict[str, Any] | None:
    value = first_declared(
        result,
        (
            "cycle_reachability_gate",
            "anti_loop_progress_gate.cycle_reachability_gate",
            "run.cycle_reachability_gate",
            "selected_task.cycle_reachability_gate",
            "monitor_result.cycle_reachability_gate",
            "result.cycle_reachability_gate",
        ),
    )
    return value if isinstance(value, dict) else None


def unreachable_declared(result: dict[str, Any]) -> bool:
    paths = (
        "unreachable_within_cycle",
        "cycle_reachability_gate.unreachable_within_cycle",
        "anti_loop_progress_gate.unreachable_within_cycle",
        "anti_loop_progress_gate.cycle_reachability_gate.unreachable_within_cycle",
        "run.cycle_reachability_gate.unreachable_within_cycle",
        "monitor_result.cycle_reachability_gate.unreachable_within_cycle",
        "result.cycle_reachability_gate.unreachable_within_cycle",
    )
    return any(
        value is True or str(value or "").strip().lower() in {"true", "1", "yes"}
        for value in (_deep_get(result, path) for path in paths)
    )


def verify_gate_digest(gate: object) -> bool:
    if not isinstance(gate, dict):
        return False
    digest = _full_sha(gate.get("cycle_reachability_sha256"))
    body = {
        key: item for key, item in gate.items() if key != "cycle_reachability_sha256"
    }
    return digest == canonical_sha256(body)


def _gate_ids(gate: dict[str, Any]) -> tuple[str | None, str | None]:
    scale = gate.get("acceptance_scale")
    throughput = gate.get("throughput_evidence")
    return (
        _opaque(scale.get("acceptance_scale_id")) if isinstance(scale, dict) else None,
        _opaque(throughput.get("throughput_evidence_id"))
        if isinstance(throughput, dict)
        else None,
    )


def _throughput_fingerprint(gate: dict[str, Any]) -> str | None:
    throughput = gate.get("throughput_evidence")
    if not isinstance(throughput, dict):
        return None
    return _full_sha(throughput.get("throughput_evidence_sha256"))


def validate_unreachable_gate(gate: object) -> list[str]:
    if not isinstance(gate, dict):
        return ["cycle_reachability_gate_missing"]
    issues: list[str] = []
    if gate.get("contract_version") != 1:
        issues.append("cycle_reachability_contract_version_invalid")
    if gate.get("applicability") != "applicable":
        issues.append("cycle_reachability_not_applicable")
    if gate.get("evaluation_status") != "fail":
        issues.append("cycle_reachability_failure_status_missing")
    if (
        gate.get("reachability_verdict") != "unreachable"
        or gate.get("unreachable_within_cycle") is not True
    ):
        issues.append("cycle_reachability_unreachable_verdict_mismatch")
    if not verify_gate_digest(gate):
        issues.append("cycle_reachability_digest_mismatch")
    scale_id, throughput_id = _gate_ids(gate)
    if scale_id is None:
        issues.append("acceptance_scale_id_missing")
    if throughput_id is None:
        issues.append("throughput_evidence_id_missing")
    if _positive(gate.get("cycle_execution_cap")) is None:
        issues.append("cycle_execution_cap_missing_or_invalid")
    return issues


@dataclass(slots=True)
class LaunchContractAssessment:
    applicable: bool
    gate: dict[str, Any] | None = None
    residual: dict[str, Any] | None = None
    plan: dict[str, Any] | None = None
    run_id: str | None = None
    issues: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return self.applicable and not self.issues


def assess_launch_contract(result: dict[str, Any]) -> LaunchContractAssessment:
    if not unreachable_declared(result):
        return LaunchContractAssessment(applicable=False)
    gate = cycle_gate_from_result(result)
    assessment = LaunchContractAssessment(applicable=True, gate=gate)
    assessment.issues.extend(validate_unreachable_gate(gate))
    residual = first_declared(
        result,
        (
            "residual_acceptance",
            "run.residual_acceptance",
            "selected_task.residual_acceptance",
            "monitor_result.residual_acceptance",
        ),
    )
    plan = first_declared(
        result,
        (
            "harvest_validation_plan",
            "run.harvest_validation_plan",
            "selected_task.harvest_validation_plan",
            "monitor_result.harvest_validation_plan",
        ),
    )
    assessment.residual = residual if isinstance(residual, dict) else None
    assessment.plan = plan if isinstance(plan, dict) else None
    assessment.run_id = _opaque(
        first_declared(
            result,
            ("run_id", "run.run_id", "selected_task.run_id", "monitor_result.run_id"),
        )
    )
    if assessment.residual is None:
        assessment.issues.append("residual_acceptance_missing")
    if assessment.plan is None:
        assessment.issues.append("harvest_validation_plan_missing")
    if gate is None or assessment.residual is None or assessment.plan is None:
        return assessment
    scale = (
        gate.get("acceptance_scale")
        if isinstance(gate.get("acceptance_scale"), dict)
        else {}
    )
    scale_id, throughput_id = _gate_ids(gate)
    residual_id = _opaque(assessment.residual.get("residual_acceptance_id"))
    if (
        residual_id is None
        or _opaque(assessment.residual.get("original_acceptance_id")) is None
    ):
        assessment.issues.append("residual_acceptance_identity_missing")
    if assessment.residual.get("status") not in {"open", "pending"}:
        assessment.issues.append("residual_acceptance_not_open")
    if assessment.residual.get("acceptance_scale_id") != scale_id:
        assessment.issues.append("residual_acceptance_scale_binding_mismatch")
    if _positive(assessment.residual.get("required_scale")) != _positive(
        scale.get("required_scale")
    ):
        assessment.issues.append("residual_required_scale_mismatch")
    if _opaque(assessment.residual.get("scale_unit")) != _opaque(
        scale.get("scale_unit")
    ):
        assessment.issues.append("residual_scale_unit_mismatch")
    expected_gate_digest = gate.get("cycle_reachability_sha256")
    plan_bindings = {
        "run_id": assessment.run_id,
        "cycle_reachability_sha256": expected_gate_digest,
        "acceptance_scale_id": scale_id,
        "throughput_evidence_id": throughput_id,
        "residual_acceptance_id": residual_id,
    }
    if _opaque(assessment.plan.get("harvest_plan_id")) is None:
        assessment.issues.append("harvest_plan_id_missing")
    for field_name, expected in plan_bindings.items():
        if expected is None or assessment.plan.get(field_name) != expected:
            assessment.issues.append(f"harvest_plan_{field_name}_binding_mismatch")
    if _string_set(assessment.plan.get("validation_predicate_ids")) is None:
        assessment.issues.append("harvest_validation_predicate_ids_missing_or_invalid")
    return assessment


def _receipt_matches(
    assessment: LaunchContractAssessment, receipt: object
) -> tuple[bool, list[str]]:
    if not isinstance(receipt, dict):
        return False, ["harvest_validation_receipt_missing"]
    issues: list[str] = []
    gate = assessment.gate or {}
    plan = assessment.plan or {}
    residual = assessment.residual or {}
    scale = (
        gate.get("acceptance_scale")
        if isinstance(gate.get("acceptance_scale"), dict)
        else {}
    )
    expected = {
        "run_id": assessment.run_id,
        "harvest_plan_id": plan.get("harvest_plan_id"),
        "acceptance_scale_id": scale.get("acceptance_scale_id"),
        "residual_acceptance_id": residual.get("residual_acceptance_id"),
        "cycle_reachability_sha256": gate.get("cycle_reachability_sha256"),
    }
    if receipt.get("receipt_version") != 1 or receipt.get("status") != "pass":
        issues.append("harvest_validation_receipt_status_invalid")
    for field_name, expected_value in expected.items():
        if expected_value is None or receipt.get(field_name) != expected_value:
            issues.append(f"harvest_receipt_{field_name}_binding_mismatch")
    observed = _positive(receipt.get("observed_scale"))
    required = _positive(scale.get("required_scale"))
    if observed is None or required is None or observed < required:
        issues.append("harvest_observed_scale_below_acceptance")
    if _opaque(receipt.get("scale_unit")) != _opaque(scale.get("scale_unit")):
        issues.append("harvest_receipt_scale_unit_mismatch")
    required_predicates = _string_set(plan.get("validation_predicate_ids"))
    observed_predicates = _string_set(receipt.get("validation_predicate_ids"))
    if (
        required_predicates is None
        or observed_predicates is None
        or not required_predicates.issubset(observed_predicates)
    ):
        issues.append("harvest_receipt_predicate_coverage_mismatch")
    if _full_sha(receipt.get("output_fingerprint")) is None:
        issues.append("harvest_receipt_output_fingerprint_missing")
    digest = _full_sha(receipt.get("receipt_sha256"))
    body = {key: item for key, item in receipt.items() if key != "receipt_sha256"}
    if digest != canonical_sha256(body):
        issues.append("harvest_validation_receipt_digest_mismatch")
    return not issues, issues


def _recomputed_matches(
    assessment: LaunchContractAssessment, recomputed: object
) -> tuple[bool, list[str]]:
    if not isinstance(recomputed, dict):
        return False, ["recomputed_cycle_reachability_missing"]
    issues: list[str] = []
    original = assessment.gate or {}
    original_scale_id, original_throughput_id = _gate_ids(original)
    scale_id, throughput_id = _gate_ids(recomputed)
    original_throughput_sha = _throughput_fingerprint(original)
    throughput_sha = _throughput_fingerprint(recomputed)
    if not verify_gate_digest(recomputed):
        issues.append("recomputed_cycle_reachability_digest_mismatch")
    if (
        recomputed.get("contract_version") != 1
        or recomputed.get("applicability") != "applicable"
    ):
        issues.append("recomputed_cycle_reachability_contract_invalid")
    if (
        recomputed.get("evaluation_status") != "pass"
        or recomputed.get("reachability_verdict") != "reachable"
        or recomputed.get("unreachable_within_cycle") is not False
    ):
        issues.append("recomputed_cycle_reachability_not_reachable")
    if scale_id != original_scale_id:
        issues.append("recomputed_acceptance_scale_binding_mismatch")
    if throughput_id is None or throughput_id == original_throughput_id:
        issues.append("recomputed_throughput_evidence_not_fresh")
    if throughput_sha is None or throughput_sha == original_throughput_sha:
        issues.append("recomputed_throughput_measurement_not_fresh")
    return not issues, issues


@dataclass(slots=True)
class HarvestCompletionAssessment:
    applicable: bool
    complete: bool
    launch: LaunchContractAssessment
    issues: list[str] = field(default_factory=list)


def assess_harvest_completion(result: dict[str, Any]) -> HarvestCompletionAssessment:
    launch = assess_launch_contract(result)
    if not launch.applicable:
        return HarvestCompletionAssessment(
            applicable=False, complete=False, launch=launch
        )
    issues = list(launch.issues)
    receipt = first_declared(
        result,
        (
            "harvest_validation_receipt",
            "run.harvest_validation_receipt",
            "monitor_result.harvest_validation_receipt",
            "result.harvest_validation_receipt",
        ),
    )
    recomputed = first_declared(
        result,
        (
            "recomputed_cycle_reachability_gate",
            "run.recomputed_cycle_reachability_gate",
            "monitor_result.recomputed_cycle_reachability_gate",
            "result.recomputed_cycle_reachability_gate",
        ),
    )
    receipt_valid, receipt_issues = _receipt_matches(launch, receipt)
    recomputed_valid, recomputed_issues = _recomputed_matches(launch, recomputed)
    if not receipt_valid and not recomputed_valid:
        issues.extend(receipt_issues)
        issues.extend(recomputed_issues)
    legacy_claim = first_declared(
        result,
        (
            "long_run_harvest_validated",
            "harvest_validation_complete",
            "cycle_reachability_gate.harvest_validation_complete",
            "throughput_improved",
            "cycle_reachability_gate.throughput_improved",
        ),
    )
    if legacy_claim is not None and not (receipt_valid or recomputed_valid):
        issues.append("unstructured_harvest_or_throughput_claim")
    return HarvestCompletionAssessment(
        applicable=True,
        complete=not launch.issues and (receipt_valid or recomputed_valid),
        launch=launch,
        issues=list(dict.fromkeys(issues)),
    )


__all__ = [
    "HarvestCompletionAssessment",
    "LaunchContractAssessment",
    "PENDING_REACHABILITY_STATUSES",
    "assess_harvest_completion",
    "assess_launch_contract",
    "canonical_sha256",
    "cycle_gate_from_result",
    "first_declared",
    "unreachable_declared",
    "validate_unreachable_gate",
    "verify_gate_digest",
]
