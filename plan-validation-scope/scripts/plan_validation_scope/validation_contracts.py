"""Decision-identity and verifier-separation checks for validation scope."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


DECISION_ARTIFACT_REF = "decision_artifact_ref"
VERIFICATION_SEPARATION_GATE = "verification_source_separation_gate"


@dataclass(frozen=True)
class ValidationContractEvaluation:
    findings: tuple[dict[str, str], ...]
    rationale: tuple[str, ...]
    requires_affected_chain: bool
    manifest_fields: dict[str, dict[str, Any]]


def decision_artifact_ref_issues(value: Any) -> tuple[list[str], Any | None]:
    if not isinstance(value, dict):
        return ["decision_artifact_ref_not_object"], None
    try:
        from orchestrate_task_cycle.result_contract.decision_identity_dimensions import (  # noqa: PLC0415
            parse_decision_identity,
        )
    except ImportError:
        return ["canonical_decision_identity_contract_unavailable"], None
    projection = parse_decision_identity(value)
    issues = list(projection.issues)
    if not projection.explicit:
        issues.append("explicit_decision_identity_missing")
    if projection.subject_values.get("freshness_status") != "current":
        issues.append("decision_subject_not_current")
    return sorted(set(issues)), projection


def verification_separation_issues(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["verification_separation_gate_not_object"]
    issues: list[str] = []
    if value.get("independent_source_separation_status") != "pass":
        issues.append("verification_source_not_independent")
    if value.get("independent_invariant_separation_status") != "pass":
        issues.append("verification_invariant_not_independent")
    axes = value.get("verification_axes")
    if not isinstance(axes, list) or not axes:
        return sorted({*issues, "verification_axes_missing"})
    for index, row in enumerate(axes):
        if not isinstance(row, dict):
            issues.append(f"verification_axes[{index}].not_object")
            continue
        if row.get("coupling_status") != "disjoint":
            issues.append(f"verification_axes[{index}].source_coupled")
        if row.get("invariant_separation_status") != "independent":
            issues.append(f"verification_axes[{index}].invariant_coupled")
        producer_owner = str(row.get("producer_invariant_owner_id") or "")
        verifier_owner = str(row.get("verifier_invariant_owner_id") or "")
        if not producer_owner or not verifier_owner or producer_owner == verifier_owner:
            issues.append(f"verification_axes[{index}].invariant_owner_not_separated")
        producer_function = str(row.get("producer_function_id") or "")
        verifier_function = str(row.get("verifier_function_id") or "")
        if (
            not producer_function
            or not verifier_function
            or producer_function == verifier_function
        ):
            issues.append(
                f"verification_axes[{index}].invariant_implementation_not_separated"
            )
    return sorted(set(issues))


def _finding(*, mode: str, code: str, message: str) -> dict[str, str]:
    return {
        "severity": "block" if mode == "finalize" else "warn",
        "code": code,
        "message": message,
    }


def _finding_codes(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {
        str(row.get("code") or "")
        for row in value
        if isinstance(row, dict) and row.get("code")
    }


def _planned_contracts(plan: dict[str, Any] | None) -> tuple[bool, bool]:
    if not isinstance(plan, dict):
        return False, False
    codes = _finding_codes(plan.get("findings"))
    decision_declared = DECISION_ARTIFACT_REF in plan or any(
        code.startswith("decision_artifact_")
        or code
        in {
            "explicit_decision_identity_missing",
            "canonical_decision_identity_contract_unavailable",
        }
        for code in codes
    )
    separation_declared = VERIFICATION_SEPARATION_GATE in plan or bool(
        codes
        & {
            "verification_separation_not_evaluated",
            "verification_separation_gate_missing_at_finalize",
        }
    )
    return decision_declared, separation_declared


def _decision_findings(
    *,
    mode: str,
    payload: dict[str, Any],
    plan: dict[str, Any] | None,
) -> tuple[list[dict[str, str]], list[str], bool]:
    declared = DECISION_ARTIFACT_REF in payload
    planned_decision, _ = _planned_contracts(plan)
    findings: list[dict[str, str]] = []
    if mode == "finalize" and planned_decision and not declared:
        findings.append(
            _finding(
                mode=mode,
                code="decision_artifact_ref_missing_at_finalize",
                message="Current decision-artifact identity was not supplied for finalization.",
            )
        )
    if not declared:
        return findings, [], False

    issues, current = decision_artifact_ref_issues(payload.get(DECISION_ARTIFACT_REF))
    if issues:
        findings.append(
            _finding(
                mode=mode,
                code="decision_artifact_binding_not_evaluated",
                message="Exact current decision-artifact binding is unavailable: "
                + ",".join(issues),
            )
        )
        return findings, ["decision_artifact_recompute_required"], True
    if mode != "finalize" or not isinstance(plan, dict):
        return findings, [], False

    planned_ref = plan.get(DECISION_ARTIFACT_REF)
    planned_issues, planned = decision_artifact_ref_issues(planned_ref)
    if planned_issues or planned is None or current is None:
        return findings, [], False
    stable_fields = ("decision_subject_id", "subject_class_id", "lineage_id")
    if any(
        planned.subject_values.get(field) != current.subject_values.get(field)
        for field in stable_fields
    ):
        findings.append(
            _finding(
                mode=mode,
                code="decision_artifact_subject_changed",
                message="Finalization supplied a different decision subject or lineage.",
            )
        )
        return findings, ["decision_artifact_subject_changed"], True
    return findings, [], False


def _separation_findings(
    *,
    mode: str,
    payload: dict[str, Any],
    plan: dict[str, Any] | None,
) -> tuple[list[dict[str, str]], list[str], bool]:
    declared = VERIFICATION_SEPARATION_GATE in payload
    _, planned_separation = _planned_contracts(plan)
    findings: list[dict[str, str]] = []
    if mode == "finalize" and planned_separation and not declared:
        findings.append(
            _finding(
                mode=mode,
                code="verification_separation_gate_missing_at_finalize",
                message="Current verification-separation gate was not supplied for finalization.",
            )
        )
    if not declared:
        return findings, [], False
    issues = verification_separation_issues(payload.get(VERIFICATION_SEPARATION_GATE))
    if not issues:
        return findings, [], False
    findings.append(
        _finding(
            mode=mode,
            code="verification_separation_not_evaluated",
            message="Independent verification is not source-and-invariant separated: "
            + ",".join(issues),
        )
    )
    return findings, ["independent_verification_recompute_required"], True


def evaluate_validation_contracts(
    *,
    mode: str,
    payload: dict[str, Any],
    plan: dict[str, Any] | None,
) -> ValidationContractEvaluation:
    decision = _decision_findings(mode=mode, payload=payload, plan=plan)
    separation = _separation_findings(mode=mode, payload=payload, plan=plan)
    manifest_fields = {
        key: payload[key]
        for key in (DECISION_ARTIFACT_REF, VERIFICATION_SEPARATION_GATE)
        if isinstance(payload.get(key), dict)
    }
    return ValidationContractEvaluation(
        findings=tuple([*decision[0], *separation[0]]),
        rationale=tuple([*decision[1], *separation[1]]),
        requires_affected_chain=decision[2] or separation[2],
        manifest_fields=manifest_fields,
    )
