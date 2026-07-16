#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from result_contract_lib.base import RuleContext, RuleRegistry  # noqa: E402
from result_contract_lib.common import (  # noqa: E402
    ADVICE_REQUIRED_TARGETS,
    AGENT_ROUTING_TARGETS,
    CANONICAL_LEDGER_STEPS,
    COMMON_FIELDS,
    MODEL_EFFORT_POLICY,
    MODEL_EFFORT_ROUTER,
    ROUTING_ENFORCEMENT_VALUES,
    SUPPORTED_AGENT_EFFORTS,
    SUPPORTED_AGENT_MODELS,
    TARGETS,
    active_advice_present,
    actual_report_body_divergences,
    add,
    advice_handling_rationale_present,
    boolish,
    first_present,
    has_value,
    list_values,
    load_json,
    non_empty,
    report_key_divergences,
    report_key_duplicate_matches,
    value_for,
)
from result_contract_lib.registry import default_rule_registry  # noqa: E402
from result_contract_lib.finalization import validate_finalization_contract  # noqa: E402
from result_contract_lib.lifecycle import validate_lifecycle_extensions  # noqa: E402
from result_contract_lib.rules.session_audit import SessionAuditRule  # noqa: E402


PENDING_LONG_RUN_STATUSES = {"launching", "running", "completed_pending_validation", "stale", "not_running"}
SESSION_AUDIT_RULE = SessionAuditRule()
DECISION_TARGETS = {"qualitative_review", "loopback_audit", "derive", "validate", "report"}
VERDICT_AXES = (
    "task_acceptance_verdict",
    "artifact_truth_verdict",
    "artifact_semantic_verdict",
    "pack_transition_verdict",
    "historical_index_verdict",
    "goal_readiness_verdict",
)
VERDICT_AXIS_STATUSES = {
    "pass",
    "fail",
    "partial",
    "blocked",
    "not_evaluated",
    "not_applicable",
    "conflicted",
}
COUPLING_STATUSES = {"disjoint", "overlapping", "same_artifact", "unknown"}
EVIDENCE_PROVENANCE_STATUSES = {
    "independently_verified",
    "self_grounded",
    "producer_attested",
    "not_evaluated",
}


def _positive_decision_claim(target: str, result: dict[str, Any]) -> bool:
    validation_verdict = str(value_for(result, "validation_verdict") or "").strip().lower()
    review_status = str(value_for(result, "review_status") or "").strip().lower()
    quality_verdict = str(value_for(result, "quality_verdict") or "").strip().lower()
    progress_verdict = str(value_for(result, "progress_verdict") or "").strip().lower()
    progress_kind = str(value_for(result, "progress_kind") or "").strip().lower()
    completion_status = str(first_present(result, ["completion_status", "report.completion_status", "result.completion_status"]) or "").strip().lower()
    pack_transition_status = str(
        first_present(result, ["pack_transition_verdict.status", "pack_transition_status", "result.pack_transition_verdict.status"])
        or ""
    ).strip().lower()
    return bool(
        (target == "validate" and validation_verdict in {"complete", "pass", "passed", "success"})
        or (target == "qualitative_review" and review_status == "complete" and quality_verdict == "acceptable")
        or completion_status in {"complete", "complete_verified", "closed", "promoted"}
        or pack_transition_status in {"pass", "passed", "promoted", "complete"}
        or boolish(first_present(result, ["pack_transition_applied", "successor_auto_promoted", "promotion_applied"]))
        or progress_verdict == "advanced"
        or progress_kind == "goal_productive"
        or boolish(first_present(result, ["semantic_progress", "authoritative_semantic_progress"]))
        or boolish(first_present(result, ["hard_stop_required", "hard_stop"]))
    )


def _full_sha256(value: Any) -> bool:
    normalized = str(value or "").strip().lower().removeprefix("sha256:")
    return len(normalized) == 64 and all(character in "0123456789abcdef" for character in normalized)


def _opaque_scalar(value: Any, *, max_length: int = 256) -> bool:
    return bool(
        isinstance(value, str)
        and 0 < len(value.strip()) <= max_length
        and not any(ord(character) < 32 or ord(character) == 127 for character in value.strip())
    )


def _opaque_string_items(value: Any) -> tuple[list[str], bool]:
    if value is None:
        return [], True
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        return [], False
    items = [item.strip() for item in value if _opaque_scalar(item)]
    return items, len(items) == len(value)


def _finite_numeric(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(float(value))
    except (OverflowError, TypeError, ValueError):
        return False


def _declared_values(data: dict[str, Any], paths: tuple[str, ...]) -> list[Any]:
    values: list[Any] = []
    for path in paths:
        current: Any = data
        declared = True
        for part in path.split("."):
            if not isinstance(current, dict) or part not in current:
                declared = False
                break
            current = current[part]
        if declared:
            values.append(current)
    return values


def _normalized_verdict_status(value: Any) -> str:
    if isinstance(value, dict):
        raw = value.get("status") if value.get("status") is not None else value.get("verdict")
    else:
        raw = value
    status = str(raw or "").strip().lower()
    if status in {"", "missing", "unknown", "unobserved"}:
        return "not_evaluated"
    return status


def _consumer_receipt_pass(
    row: dict[str, Any],
    bool_field: str,
    status_field: str,
) -> bool:
    if bool_field in row:
        return boolish(row.get(bool_field))
    return str(row.get(status_field) or "").strip().lower() in {
        "pass",
        "passed",
        "complete",
        "completed",
        "consumed",
        "success",
    }


def _consumer_receipt_binding_sha256(row: dict[str, Any]) -> str:
    basis = {
        "consumer_context_id": str(row.get("consumer_context_id") or ""),
        "cycle_id": str(row.get("cycle_id") or ""),
        "input_state_fingerprint": str(row.get("input_state_fingerprint") or ""),
        "attempt_identity": str(row.get("attempt_identity") or ""),
        "artifact_id": row.get("artifact_id"),
        "artifact_sha256": row.get("artifact_sha256"),
        "production_lane_identity": row.get("production_lane_identity"),
        "body_projection_fingerprint": row.get("body_projection_fingerprint"),
        "verification_input_ids": sorted(
            str(item) for item in list_values(row.get("verification_input_ids"))
        ),
        "input_fingerprints": (
            row.get("input_fingerprints")
            if isinstance(row.get("input_fingerprints"), dict)
            else None
        ),
        "evidence_provenance": str(row.get("evidence_provenance") or "").strip().lower(),
        "adapter_loaded": boolish(row.get("adapter_loaded")),
        "hook_resolved": boolish(
            row.get("hook_resolved")
            if "hook_resolved" in row
            else row.get("required_hook_callable")
        ),
        "required_hook_callable": boolish(row.get("required_hook_callable")),
        "hook_signature_compatible": boolish(row.get("hook_signature_compatible")),
        "invocation_completed": _consumer_receipt_pass(
            row,
            "invocation_completed",
            "invocation_status",
        ),
        "return_contract_valid": boolish(row.get("return_contract_valid")),
        "artifact_identity_echo_valid": _consumer_receipt_pass(
            row,
            "artifact_identity_echo_valid",
            "artifact_identity_echo_status",
        ),
        "value_consumed_by_decision": _consumer_receipt_pass(
            row,
            "value_consumed_by_decision",
            "decision_consumption_status",
        ),
        "probe_evidence_ref": str(row.get("probe_evidence_ref") or ""),
    }
    raw = json.dumps(basis, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _metric_gate_signature(gate: Any) -> tuple[Any, ...]:
    if not isinstance(gate, dict):
        return ("invalid_gate",)
    raw_status = gate.get("evaluation_status") if gate.get("evaluation_status") is not None else gate.get("status")
    status = raw_status.strip().lower() if isinstance(raw_status, str) else "invalid_contract"
    improved, improved_valid = _opaque_string_items(gate.get("improved_fields"))
    summaries: list[tuple[str, tuple[str, ...], bool]] = []
    for field in ("not_applicable_fields", "insufficient_evidence_fields", "invalid_contract_fields"):
        items, valid = _opaque_string_items(gate.get(field))
        summaries.append((field, tuple(sorted(set(items))), valid))
    policy = gate.get("quality_delta_policy")
    policy_signature: tuple[Any, ...] = ("missing",)
    if isinstance(policy, dict):
        declared_value = policy.get("declared_keys") if policy.get("declared_keys") is not None else policy.get("keys")
        declared, declared_valid = _opaque_string_items(declared_value)
        mapping = policy.get("applicability")
        rows: list[tuple[str, str]] = []
        mapping_valid = mapping is None or isinstance(mapping, dict)
        if isinstance(mapping, dict):
            for metric_id, row in mapping.items():
                if not _opaque_scalar(metric_id) or not isinstance(row, dict):
                    mapping_valid = False
                    continue
                raw_row_status = row.get("evaluation_status")
                row_status = raw_row_status.strip().lower() if isinstance(raw_row_status, str) else "invalid_contract"
                rows.append((metric_id.strip(), row_status))
        elif mapping is None:
            rows = [(metric_id, "applicable") for metric_id in declared]
        policy_signature = (
            tuple(sorted(set(declared))),
            declared_valid,
            tuple(sorted(rows)),
            mapping_valid,
            boolish(policy.get("policy_contract_invalid")),
        )
    vectors: list[tuple[str, tuple[tuple[str, str], ...], bool]] = []
    for field in ("current_quality_vector", "previous_high_water_vector", "previous_quality_vector"):
        value = gate.get(field)
        if value is None:
            vectors.append((field, (), True))
            continue
        if not isinstance(value, dict):
            vectors.append((field, (), False))
            continue
        safe: list[tuple[str, str]] = []
        valid = True
        for metric_id, observation in value.items():
            if not _opaque_scalar(metric_id) or not _finite_numeric(observation):
                valid = False
                continue
            safe.append((metric_id.strip(), repr(float(observation))))
        vectors.append((field, tuple(sorted(safe)), valid))
    return (
        status,
        boolish(gate.get("quality_delta_pass")),
        tuple(sorted(set(improved))),
        improved_valid,
        tuple(summaries),
        policy_signature,
        tuple(vectors),
    )


def validate_decision_identity_and_compatibility(
    target: str,
    result: dict[str, Any],
    mode: str,
    findings: list[dict[str, Any]],
) -> None:
    if target not in DECISION_TARGETS:
        return
    raw_contract_version = first_present(
        result,
        [
            "decision_contract_version",
            "result.decision_contract_version",
            "anti_loop_progress_gate.decision_contract_version",
            "handoff_contract_version",
        ],
    )
    try:
        contract_version = int(raw_contract_version) if raw_contract_version is not None else None
    except (TypeError, ValueError):
        contract_version = None
    positive_claim = _positive_decision_claim(target, result)
    severity = (
        "block"
        if mode == "block"
        or target in {"validate", "report"}
        or positive_claim
        else "warn"
    )
    contract_required = positive_claim
    if contract_required and raw_contract_version is None:
        add(
            findings,
            severity,
            "decision_contract_version_missing",
            "Current decision claims require decision_contract_version=1; legacy consumption requires explicit version 0.",
        )
        return
    if raw_contract_version is not None and contract_version not in {0, 1}:
        add(findings, severity, "decision_contract_version_invalid", "Decision contract version must be 1 or explicit legacy version 0.")
        return
    if contract_version == 0:
        return
    identity = first_present(
        result,
        [
            "decision_input_identity",
            "decision_artifact_ref",
            "selected_artifact_ref",
            "artifact_ref",
            "actual_artifact_ref",
            "result.decision_input_identity",
        ],
    )
    if contract_version == 1 and not isinstance(identity, dict):
        add(
            findings,
            severity,
            "decision_artifact_identity_missing",
            "Current decision contract requires an exact decision artifact identity.",
        )
    if isinstance(identity, dict):
        required = (
            "artifact_id",
            "artifact_class",
            "artifact_sha256",
            "production_lane_identity",
            "discovery_basis",
        )
        missing = [field for field in required if not non_empty(identity.get(field))]
        scope_verified = boolish(identity.get("scope_verified"))
        advisory = boolish(identity.get("advisory_discovery")) or not scope_verified or bool(missing)
        if identity.get("artifact_sha256") and not _full_sha256(identity.get("artifact_sha256")):
            missing.append("artifact_sha256(valid_sha256)")
            advisory = True
        if missing:
            add(
                findings,
                severity,
                "decision_artifact_identity_incomplete",
                "Decision-controlling artifact identity is incomplete and must remain advisory.",
                {"missing_fields": sorted(set(missing))},
            )
        if positive_claim and advisory:
            add(
                findings,
                severity,
                "advisory_artifact_controls_decision",
                "An advisory or scope-unverified artifact cannot control completion, progress, hard stop, terminal state, or pack consumption.",
            )

        direct_read_scope = {
            str(item).strip().lower()
            for item in list_values(
                first_present(
                    result,
                    [
                        "direct_read_scope",
                        "quality_review.direct_read_scope",
                        "qualitative_review.direct_read_scope",
                        "result.direct_read_scope",
                    ],
                )
            )
            if str(item).strip()
        }
        semantic_axis_values = [
            *_declared_values(
                result,
                (
                    "artifact_semantic_verdict",
                    "verdict_axes.artifact_semantic_verdict",
                    "result.artifact_semantic_verdict",
                    "result.verdict_axes.artifact_semantic_verdict",
                ),
            ),
            *_declared_values(
                result,
                (
                    "goal_readiness_verdict",
                    "verdict_axes.goal_readiness_verdict",
                    "result.goal_readiness_verdict",
                    "result.verdict_axes.goal_readiness_verdict",
                ),
            ),
        ]
        semantic_claim = bool(
            "artifact_body" in direct_read_scope
            or any(_normalized_verdict_status(value) == "pass" for value in semantic_axis_values)
            or boolish(first_present(result, ["semantic_progress", "authoritative_semantic_progress"]))
            or str(first_present(result, ["progress_kind", "effective_progress_kind"]) or "").strip().lower()
            == "goal_productive"
        )
        body_values = []
        if "body_projection_fingerprint" in identity:
            body_values.append(identity.get("body_projection_fingerprint"))
        body_values.extend(
            _declared_values(
                result,
                (
                    "body_projection_fingerprint",
                    "actual_artifact_truth.body_projection_fingerprint",
                    "quality_review.body_projection_fingerprint",
                    "result.body_projection_fingerprint",
                ),
            )
        )
        body_fingerprint = next((value for value in body_values if non_empty(value)), None)
        cohort_values = []
        for field in ("verification_input_ids", "input_fingerprints"):
            if field in identity:
                cohort_values.append(identity.get(field))
        cohort_values.extend(
            _declared_values(
                result,
                (
                    "verification_input_ids",
                    "verification_source_separation_gate.verification_input_ids",
                    "input_fingerprints",
                    "verification_source_separation_gate.input_fingerprints",
                    "result.verification_input_ids",
                    "result.input_fingerprints",
                ),
            )
        )
        cohort_declared = any(non_empty(value) for value in cohort_values)
        semantic_binding_missing: list[str] = []
        if semantic_claim and not _full_sha256(body_fingerprint):
            semantic_binding_missing.append("body_projection_fingerprint")
        if semantic_claim and not cohort_declared:
            semantic_binding_missing.append("source_cohort")
        if semantic_binding_missing:
            add(
                findings,
                severity,
                "decision_semantic_binding_incomplete",
                "Artifact-body, semantic, or goal claims require a current body fingerprint and an explicitly declared source cohort; missing bindings remain not evaluated.",
                {"missing_fields": semantic_binding_missing},
            )

    explicit_identity = first_present(result, ["explicit_artifact_ref", "caller_artifact_ref"])
    default_identity = first_present(result, ["default_artifact_ref", "discovered_default_artifact_ref"])
    if isinstance(explicit_identity, dict) and isinstance(default_identity, dict):
        conflict = any(
            explicit_identity.get(field)
            and default_identity.get(field)
            and explicit_identity.get(field) != default_identity.get(field)
            for field in ("artifact_id", "artifact_sha256", "production_lane_identity")
        )
        if conflict:
            selected_id = identity.get("artifact_id") if isinstance(identity, dict) else None
            if selected_id != explicit_identity.get("artifact_id") or not _full_sha256(explicit_identity.get("artifact_sha256")):
                add(
                    findings,
                    severity,
                    "explicit_artifact_conflict_not_resolved",
                    "Exact caller artifact must win over a conflicting default discovery, and its hash must verify.",
                )

    rows = first_present(
        result,
        [
            "gate_compatibility_results",
            "gate_compatibility.rows",
            "decision_gate_compatibility",
            "result.gate_compatibility_results",
        ],
    )
    if isinstance(rows, dict):
        compatibility_rows = rows.get("rows") if isinstance(rows.get("rows"), list) else []
    else:
        compatibility_rows = rows if isinstance(rows, list) else []
    compatibility_declared = any(
        key in result
        for key in ("gate_compatibility_results", "decision_gate_compatibility")
    ) or isinstance(result.get("gate_compatibility"), dict)
    required_gate_scope_declared = "required_gate_ids" in result or isinstance(result.get("gate_compatibility"), dict) and "required_gate_ids" in result["gate_compatibility"]
    consumed_gate_scope_declared = any(
        key in result
        for key in ("decision_consumed_gate_ids", "consumed_gate_ids", "decision_gate_ids")
    )
    if contract_version == 1 and positive_claim:
        missing_surfaces = []
        if not compatibility_declared:
            missing_surfaces.append("gate_compatibility_results")
        if not required_gate_scope_declared:
            missing_surfaces.append("required_gate_ids")
        if not consumed_gate_scope_declared:
            missing_surfaces.append("decision_consumed_gate_ids")
        if missing_surfaces:
            add(
                findings,
                severity,
                "decision_gate_compatibility_scope_missing",
                "Current decision contract requires explicit applicable, required, and consumed gate scopes, including explicit empty lists.",
                {"missing_fields": missing_surfaces},
            )
    required_gate_ids = {
        str(item)
        for item in list_values(first_present(result, ["required_gate_ids", "gate_compatibility.required_gate_ids"]))
    }
    consumed_gate_ids: set[str] = set()
    for field in ("decision_consumed_gate_ids", "consumed_gate_ids", "decision_gate_ids", "residual_gate_ids", "hard_stop_gate_ids"):
        consumed_gate_ids.update(str(item) for item in list_values(first_present(result, [field, f"decision.{field}"])))
    by_id: dict[str, dict[str, Any]] = {}
    for row in compatibility_rows:
        if not isinstance(row, dict) or not non_empty(row.get("gate_id")):
            add(findings, severity, "gate_compatibility_row_invalid", "Gate compatibility rows require a gate_id.")
            continue
        gate_id = str(row.get("gate_id"))
        by_id[gate_id] = row
        status = str(row.get("gate_compatibility_status") or "").strip().lower()
        if status not in {"compatible", "incompatible", "not_evaluated"}:
            add(findings, severity, "gate_compatibility_status_invalid", "Gate compatibility status is invalid.", {"gate_id": gate_id})
        if status != "compatible" and gate_id in consumed_gate_ids:
            add(
                findings,
                severity,
                "noncompatible_gate_consumed",
                "An incompatible or unevaluated gate cannot contribute to the decision set.",
                {"gate_id": gate_id, "status": status},
            )
        if isinstance(identity, dict):
            for field in ("artifact_id", "artifact_sha256"):
                if row.get(field) and row.get(field) != identity.get(field):
                    add(
                        findings,
                        severity,
                        "gate_compatibility_artifact_identity_mismatch",
                        "Gate compatibility evidence is bound to a different artifact identity.",
                        {"gate_id": gate_id, "field": field},
                    )
    missing_required = sorted(
        gate_id
        for gate_id in required_gate_ids
        if gate_id not in by_id
        or str(by_id[gate_id].get("gate_compatibility_status") or "").strip().lower() != "compatible"
    )
    if missing_required and positive_claim:
        add(
            findings,
            severity,
            "required_gate_compatibility_not_evaluated",
            "A required decision gate is not proven compatible with the exact artifact.",
            {"gate_ids": missing_required},
        )


def validate_verification_axes(
    target: str,
    result: dict[str, Any],
    mode: str,
    findings: list[dict[str, Any]],
) -> None:
    axes_value = first_present(
        result,
        ["verification_axes", "evidence_provenance_gate.verification_axes", "verification_source_separation_gate.verification_axes"],
    )
    axes = axes_value if isinstance(axes_value, list) else []
    severity = "block" if mode == "block" or target in {"validate", "report"} else "warn"
    required_values = first_present(result, ["required_verification_axis_ids", "verification_axis_contract.required_axis_ids"])
    required_items, required_ids_valid = _opaque_string_items(required_values)
    required_ids = set(required_items)
    positive_claim = _positive_decision_claim(target, result)
    required_contract_consumed = boolish(
        first_present(
            result,
            [
                "verification_axis_contract.required_for_acceptance",
                "verification_axis_contract.decision_contribution_allowed",
                "verification_axes_required",
            ],
        )
    )
    if not required_ids_valid:
        add(
            findings,
            severity if positive_claim or required_contract_consumed else "warn",
            "verification_axis_required_ids_invalid",
            "Required verification-axis IDs must be bounded opaque strings.",
        )
    if required_contract_consumed and (not required_ids or not axes):
        add(
            findings,
            severity if positive_claim else "warn",
            "verification_axis_contract_missing",
            "A required verification-axis contract needs bounded required IDs and axis rows before decision consumption.",
        )
    if not axes:
        if required_ids and positive_claim:
            add(
                findings,
                severity,
                "required_verification_axis_not_evaluated",
                "A required verification axis is not evaluated and cannot be consumed as pass.",
                {"axis_ids": sorted(required_ids)},
            )
        return
    observed: dict[str, dict[str, Any]] = {}
    observed_provenance: dict[str, str] = {}
    for axis in axes:
        if not isinstance(axis, dict) or not _opaque_scalar(axis.get("axis_id")):
            add(findings, severity, "verification_axis_identity_missing", "Verification axis rows require axis_id.")
            continue
        axis_id = axis["axis_id"].strip()
        observed[axis_id] = axis
        coupling_value = axis.get("coupling_status")
        provenance_value = axis.get("evidence_provenance")
        coupling = coupling_value.strip().lower() if isinstance(coupling_value, str) else "unknown"
        provenance = provenance_value.strip().lower() if isinstance(provenance_value, str) else "not_evaluated"
        observed_provenance[axis_id] = provenance if provenance in EVIDENCE_PROVENANCE_STATUSES else "not_evaluated"
        if coupling not in COUPLING_STATUSES:
            add(findings, severity, "verification_axis_coupling_invalid", "Verification coupling status is invalid.", {"axis_id": axis_id})
        if provenance not in EVIDENCE_PROVENANCE_STATUSES:
            add(findings, severity, "verification_axis_provenance_invalid", "Verification evidence provenance is invalid.", {"axis_id": axis_id})
        if provenance == "independently_verified" and coupling != "disjoint":
            add(
                findings,
                severity,
                "verification_axis_independent_without_disjoint_inputs",
                "Independently verified evidence requires disjoint verification inputs.",
                {"axis_id": axis_id, "coupling_status": coupling},
            )
        lineage_scalar_fields = (
            "producer_function_id",
            "verifier_function_id",
            "producer_input_fingerprint",
            "verifier_input_fingerprint",
        )
        lineage_scalars: dict[str, str] = {}
        lineage_valid = True
        for field in lineage_scalar_fields:
            value = axis.get(field)
            if value is None:
                lineage_scalars[field] = ""
            elif _opaque_scalar(value):
                lineage_scalars[field] = value.strip()
            else:
                lineage_scalars[field] = ""
                lineage_valid = False
        producer_items, producer_ids_valid = _opaque_string_items(axis.get("producer_input_ids"))
        verifier_items, verifier_ids_valid = _opaque_string_items(axis.get("verifier_input_ids"))
        lineage_valid = lineage_valid and producer_ids_valid and verifier_ids_valid
        if not lineage_valid:
            add(
                findings,
                severity if provenance == "independently_verified" else "warn",
                "verification_axis_lineage_invalid",
                "Verification lineage requires bounded opaque function, fingerprint, and input IDs.",
                {"axis_id": axis_id},
            )
        producer_function_id = lineage_scalars["producer_function_id"]
        verifier_function_id = lineage_scalars["verifier_function_id"]
        producer_input_fingerprint = lineage_scalars["producer_input_fingerprint"]
        verifier_input_fingerprint = lineage_scalars["verifier_input_fingerprint"]
        producer_input_ids = set(producer_items)
        verifier_input_ids = set(verifier_items)
        comparable_lineage_basis = bool(
            producer_function_id
            and verifier_function_id
            and (
                (producer_input_fingerprint and verifier_input_fingerprint)
                or (producer_input_ids and verifier_input_ids)
            )
        )
        declared_disjoint_but_coupled = bool(
            (producer_function_id and producer_function_id == verifier_function_id)
            or (producer_input_fingerprint and producer_input_fingerprint == verifier_input_fingerprint)
            or (producer_input_ids and verifier_input_ids and producer_input_ids & verifier_input_ids)
        )
        if provenance == "independently_verified" and (declared_disjoint_but_coupled or not lineage_valid):
            add(
                findings,
                severity,
                "verification_axis_independent_with_coupled_lineage",
                "Independent evidence cannot reuse the producer function or its decision inputs, even when coupling_status is declared disjoint.",
                {"axis_id": axis_id},
            )
        if provenance == "independently_verified" and not comparable_lineage_basis:
            add(
                findings,
                severity,
                "verification_axis_independent_without_lineage_basis",
                "Independent evidence requires at least one comparable producer/verifier lineage pair.",
                {"axis_id": axis_id},
            )
        semantic_axis = boolish(axis.get("semantic_axis")) or str(axis.get("axis_kind") or "").lower() in {
            "semantic",
            "source_semantic",
        }
        if semantic_axis and provenance == "self_grounded":
            add(
                findings,
                severity,
                "self_grounded_semantic_axis_overclaim",
                "Same-artifact structural verification cannot establish a source-independent semantic axis.",
                {"axis_id": axis_id},
            )
    not_evaluated = sorted(
        axis_id
        for axis_id in required_ids
        if axis_id not in observed
        or observed_provenance.get(axis_id, "not_evaluated") == "not_evaluated"
    )
    if not_evaluated and positive_claim:
        add(
            findings,
            severity,
            "required_verification_axis_not_evaluated",
            "A required verification axis is not evaluated and cannot be consumed as pass.",
            {"axis_ids": not_evaluated},
        )


def validate_metric_applicability_consumption(
    target: str,
    result: dict[str, Any],
    mode: str,
    findings: list[dict[str, Any]],
) -> None:
    gate_paths = (
        "coverage_quality_delta_gate",
        "quality_delta_gate",
        "anti_loop_progress_gate.coverage_quality_delta_gate",
        "output_delta.coverage_quality_delta_gate",
        "result.coverage_quality_delta_gate",
    )
    gate_values = _declared_values(result, gate_paths)
    gate = next((value for value in gate_values if isinstance(value, dict)), None)
    if not isinstance(gate, dict):
        return
    severity = "block" if mode == "block" or target in {"validate", "report"} else "warn"
    gate_signatures = {_metric_gate_signature(value) for value in gate_values}
    duplicate_gate_claim = any(
        isinstance(value, dict)
        and (
            boolish(value.get("quality_delta_pass"))
            or bool(value.get("improved_fields"))
            or boolish(value.get("decision_contribution_allowed"))
        )
        for value in gate_values
    ) or any(
        boolish(first_present(result, [path]))
        for path in (
            "coverage_quality_delta_required",
            "metric_applicability_required",
            "result.coverage_quality_delta_required",
            "result.metric_applicability_required",
        )
    )
    if len(gate_signatures) > 1:
        add(
            findings,
            severity if duplicate_gate_claim else "warn",
            "metric_applicability_gate_conflict",
            "Duplicate metric-applicability gate surfaces must converge before any metric decision is consumed.",
        )
    raw_evaluation_status = gate.get("evaluation_status")
    if raw_evaluation_status is None:
        raw_evaluation_status = gate.get("status")
    evaluation_status = raw_evaluation_status.strip().lower() if isinstance(raw_evaluation_status, str) else ""
    evaluation_status_invalid = evaluation_status not in {
        "evaluated",
        "not_applicable",
        "insufficient_evidence",
        "invalid_contract",
        "not_evaluated",
    }
    summary_by_status: dict[str, set[str]] = {}
    summary_contract_invalid = False
    for status, field in (
        ("not_applicable", "not_applicable_fields"),
        ("insufficient_evidence", "insufficient_evidence_fields"),
        ("invalid_contract", "invalid_contract_fields"),
    ):
        items, valid = _opaque_string_items(gate.get(field))
        summary_by_status[status] = set(items)
        if not valid:
            summary_contract_invalid = True
            add(findings, "warn", "metric_applicability_summary_invalid", "Metric-applicability summaries require bounded opaque metric IDs.")
    excluded = set().union(*summary_by_status.values())
    policy = gate.get("quality_delta_policy")
    policy_by_status = {
        "applicable": set(),
        "not_applicable": set(),
        "insufficient_evidence": set(),
        "invalid_contract": set(),
    }
    policy_contract_invalid = False
    applicability_proof_present = False
    declared_ids: set[str] = set()
    if isinstance(policy, dict):
        policy_contract_invalid = boolish(policy.get("policy_contract_invalid"))
        for field in ("not_applicable_fields", "insufficient_evidence_fields", "invalid_contract_fields"):
            items, valid = _opaque_string_items(policy.get(field))
            excluded.update(items)
            policy_contract_invalid = policy_contract_invalid or not valid
        applicability = policy.get("applicability")
        declared_values = policy.get("declared_keys") if policy.get("declared_keys") is not None else policy.get("keys")
        declared_items, declared_valid = _opaque_string_items(declared_values)
        policy_contract_invalid = policy_contract_invalid or not declared_valid or len(set(declared_items)) != len(declared_items)
        declared_ids = set(declared_items)
        if applicability is not None:
            if not isinstance(applicability, dict):
                policy_contract_invalid = True
            else:
                allowed = {"applicable", "not_applicable", "insufficient_evidence", "invalid_contract"}
                mapping_ids = {
                    key.strip()
                    for key in applicability
                    if _opaque_scalar(key)
                }
                if mapping_ids != declared_ids or len(mapping_ids) != len(applicability):
                    policy_contract_invalid = True
                for metric_id in declared_items:
                    row = applicability.get(metric_id)
                    if not isinstance(row, dict):
                        policy_contract_invalid = True
                        policy_by_status["invalid_contract"].add(metric_id)
                        continue
                    row_status = row.get("evaluation_status")
                    if not isinstance(row_status, str) or row_status.strip().lower() not in allowed:
                        policy_contract_invalid = True
                        policy_by_status["invalid_contract"].add(metric_id)
                        continue
                    normalized_status = row_status.strip().lower()
                    policy_by_status[normalized_status].add(metric_id)
                applicability_proof_present = bool(declared_ids) and not policy_contract_invalid
        elif declared_ids:
            policy_by_status["applicable"].update(declared_ids)
            applicability_proof_present = not policy_contract_invalid
        elif boolish(policy.get("supplied")):
            policy_contract_invalid = True
        excluded.update(
            policy_by_status["not_applicable"],
            policy_by_status["insufficient_evidence"],
            policy_by_status["invalid_contract"],
        )
    elif policy is not None:
        policy_contract_invalid = True
    improved_items, improved_valid = _opaque_string_items(gate.get("improved_fields"))
    consumed = set(improved_items)
    vector_contract_invalid = False
    vector_ids: dict[str, set[str]] = {}
    for vector_name in ("current_quality_vector", "previous_high_water_vector", "previous_quality_vector"):
        vector = gate.get(vector_name)
        if vector is None:
            vector_ids[vector_name] = set()
            continue
        if not isinstance(vector, dict):
            vector_ids[vector_name] = set()
            vector_contract_invalid = True
            continue
        safe_ids = {key.strip() for key in vector if _opaque_scalar(key)}
        vector_ids[vector_name] = safe_ids
        if len(safe_ids) != len(vector) or any(not _finite_numeric(value) for value in vector.values()):
            vector_contract_invalid = True
        consumed.update(safe_ids & excluded)
    gate_id = gate.get("gate") if _opaque_scalar(gate.get("gate")) else "G-COV"
    required_gate_items: list[str] = []
    for path in ("required_gate_ids", "decision.required_gate_ids", "required_decision_gate_ids", "result.required_gate_ids"):
        items, _ = _opaque_string_items(first_present(result, [path]))
        required_gate_items.extend(items)
    consumed_gate_items: list[str] = []
    for field in ("decision_consumed_gate_ids", "consumed_gate_ids", "decision_gate_ids", "residual_gate_ids", "hard_stop_gate_ids"):
        items, _ = _opaque_string_items(first_present(result, [field, f"decision.{field}"]))
        consumed_gate_items.extend(items)
    gate_required = any(
        boolish(first_present(result, [path]))
        for path in (
            "coverage_quality_delta_required",
            "metric_applicability_required",
            "result.coverage_quality_delta_required",
            "result.metric_applicability_required",
        )
    ) or gate_id in required_gate_items
    gate_consumed = bool(
        boolish(gate.get("quality_delta_pass"))
        or improved_items
        or bool(excluded & consumed)
        or boolish(gate.get("decision_contribution_allowed"))
        or boolish(first_present(result, ["coverage_quality_delta_consumed", "metric_applicability_consumed"]))
        or gate_id in consumed_gate_items
    )
    claim_relevant = gate_required or gate_consumed
    positive_metric_claim = boolish(gate.get("quality_delta_pass")) or bool(improved_items)
    if not improved_valid:
        add(
            findings,
            severity if claim_relevant else "warn",
            "metric_applicability_consumed_ids_invalid",
            "Consumed metric IDs must be bounded opaque strings.",
        )
    if claim_relevant and not applicability_proof_present:
        add(
            findings,
            severity,
            "metric_applicability_proof_missing",
            "A metric-dependent decision requires artifact-metric applicability evidence; absence is insufficient_evidence.",
        )
    if positive_metric_claim and evaluation_status == "evaluated":
        current_ids = vector_ids["current_quality_vector"]
        previous_ids = vector_ids["previous_high_water_vector"] | vector_ids["previous_quality_vector"]
        if not current_ids or not previous_ids or not set(improved_items) <= current_ids or not set(improved_items) <= previous_ids:
            vector_contract_invalid = True
    if vector_contract_invalid:
        add(
            findings,
            severity if claim_relevant else "warn",
            "metric_vector_contract_invalid",
            "Consumed metric vectors require bounded metric IDs and finite numeric observations.",
        )
    vector_metric_ids = set().union(*vector_ids.values())
    applicable_ids = policy_by_status["applicable"]
    pass_claim = boolish(gate.get("quality_delta_pass"))
    metric_claim_inconsistent = bool(
        (pass_claim and not improved_items)
        or (not pass_claim and improved_items)
        or (improved_items and not set(improved_items) <= applicable_ids)
        or (vector_metric_ids and not vector_metric_ids <= declared_ids)
    )
    if metric_claim_inconsistent:
        add(
            findings,
            severity if claim_relevant else "warn",
            "metric_delta_claim_inconsistent",
            "Metric pass, improved IDs, applicability rows, and consumed vectors must describe the same metric set.",
        )
    summary_divergence = policy_contract_invalid or summary_contract_invalid or evaluation_status_invalid
    for status in ("not_applicable", "invalid_contract"):
        expected = policy_by_status[status]
        if not expected <= summary_by_status[status]:
            summary_divergence = True
    expected_insufficient = policy_by_status["insufficient_evidence"]
    if not expected_insufficient <= summary_by_status["insufficient_evidence"]:
        summary_divergence = True
    for metric_id in summary_by_status["not_applicable"]:
        if metric_id not in policy_by_status["not_applicable"]:
            summary_divergence = True
    for metric_id in summary_by_status["invalid_contract"]:
        if metric_id not in policy_by_status["invalid_contract"]:
            summary_divergence = True
    for metric_id in summary_by_status["insufficient_evidence"]:
        if metric_id not in policy_by_status["insufficient_evidence"] and not (
            metric_id in policy_by_status["applicable"] and evaluation_status == "insufficient_evidence"
        ):
            summary_divergence = True
    if evaluation_status == "evaluated" and (
        policy_by_status["insufficient_evidence"]
        or policy_by_status["invalid_contract"]
        or not policy_by_status["applicable"]
    ):
        summary_divergence = True
    if evaluation_status == "not_applicable" and (
        policy_by_status["applicable"]
        or policy_by_status["insufficient_evidence"]
        or policy_by_status["invalid_contract"]
        or not policy_by_status["not_applicable"]
    ):
        summary_divergence = True
    if evaluation_status == "insufficient_evidence" and policy_by_status["invalid_contract"]:
        summary_divergence = True
    if summary_divergence:
        add(
            findings,
            severity if claim_relevant else "warn",
            "metric_applicability_summary_divergence",
            "Metric-applicability rows and derived summaries must converge before decision consumption.",
        )
    if excluded & consumed or evaluation_status in {"not_applicable", "insufficient_evidence", "invalid_contract", "not_evaluated"} and (
        boolish(gate.get("quality_delta_pass")) or bool(gate.get("improved_fields"))
    ):
        add(
            findings,
            severity if claim_relevant else "warn",
            "nonapplicable_metric_consumed",
            "Non-applicable, insufficient, or invalid metrics cannot enter decision vectors, high-water movement, or stall accounting.",
            {"metric_ids": sorted(excluded & consumed), "evaluation_status": evaluation_status},
        )
    if evaluation_status == "invalid_contract":
        add(findings, severity if claim_relevant else "warn", "metric_applicability_invalid_contract", "A malformed or conflicting metric-applicability contract cannot support a metric-dependent decision.")
    elif evaluation_status == "insufficient_evidence":
        add(findings, severity if claim_relevant else "warn", "metric_applicability_insufficient_evidence", "Missing metric/body evidence is insufficient_evidence, not pass or fail.")
    elif evaluation_status == "not_evaluated" and claim_relevant:
        add(
            findings,
            severity,
            "metric_applicability_insufficient_evidence",
            "A required or consumed metric gate cannot remain not_evaluated.",
        )


def validate_task_pack_expectation_comparison(
    target: str,
    result: dict[str, Any],
    mode: str,
    findings: list[dict[str, Any]],
) -> None:
    severity = "block" if mode == "block" or target in {"validate", "derive", "report"} else "warn"
    expectation_fields = (
        "progress_target",
        "progress_kind_expected",
        "semantic_signature_expected",
        "blocker_signature_expected",
        "required_output_classes",
    )
    expectation_declared = any(
        first_present(result, [field, f"task_pack_item.{field}"]) is not None
        for field in expectation_fields
    ) or first_present(result, ["adoption_axis_contract.required_output_classes", "task_pack_item.adoption_axis_contract.required_output_classes"]) is not None
    transition_claimed = any(
        boolish(first_present(result, [path]))
        for path in (
            "task_pack_auto_consume",
            "successor_auto_promoted",
            "pack_transition_applied",
            "result.pack_transition_applied",
            "task_pack_item.result.pack_transition_applied",
            "task_pack_result.pack_transition_applied",
            "result.task_pack_item.result.pack_transition_applied",
            "result.task_pack_result.pack_transition_applied",
        )
    )
    comparison_paths = (
        "expectation_comparison",
        "task_pack_item.result.expectation_comparison",
        "task_pack_result.expectation_comparison",
        "result.expectation_comparison",
        "result.task_pack_item.result.expectation_comparison",
        "result.task_pack_result.expectation_comparison",
    )
    comparison_values = _declared_values(result, comparison_paths)
    comparison = next((value for value in comparison_values if isinstance(value, dict)), None)
    comparison_signatures: set[tuple[Any, ...]] = set()
    for value in comparison_values:
        if not isinstance(value, dict):
            comparison_signatures.add(("invalid_contract",))
            continue
        raw_comparison_status = value.get("status")
        raw_comparison_review = value.get("remaining_pack_review")
        mismatch_items, mismatch_valid = _opaque_string_items(value.get("mismatched_axes"))
        comparison_signatures.add(
            (
                raw_comparison_status.strip().lower() if isinstance(raw_comparison_status, str) else "invalid_contract",
                raw_comparison_review.strip().lower() if isinstance(raw_comparison_review, str) else "invalid_contract",
                tuple(sorted(set(mismatch_items))),
                mismatch_valid,
            )
        )
    duplicate_field_paths = {
        "progress_target_expected": (
            "progress_target",
            "task_pack_item.progress_target",
        ),
        "progress_verdict_actual": (
            "progress_verdict",
            "task_pack_item.result.progress_verdict",
            "task_pack_result.progress_verdict",
            "result.progress_verdict",
        ),
        "progress_kind_expected": (
            "progress_kind_expected",
            "task_pack_item.progress_kind_expected",
        ),
        "progress_kind_actual": (
            "progress_kind",
            "task_pack_item.result.progress_kind",
            "task_pack_result.progress_kind",
            "result.progress_kind",
            "result.task_pack_item.result.progress_kind",
        ),
        "semantic_signature_expected": (
            "semantic_signature_expected",
            "task_pack_item.semantic_signature_expected",
        ),
        "semantic_signature_actual": (
            "semantic_signature",
            "task_pack_item.result.semantic_signature",
            "task_pack_result.semantic_signature",
            "result.semantic_signature",
        ),
        "blocker_signature_expected": (
            "blocker_signature_expected",
            "task_pack_item.blocker_signature_expected",
        ),
        "blocker_signature_actual": (
            "blocker_signature",
            "task_pack_item.result.blocker_signature",
            "task_pack_result.blocker_signature",
            "result.blocker_signature",
        ),
    }
    duplicate_result_conflict = False
    for paths in duplicate_field_paths.values():
        values = _declared_values(result, paths)
        normalized = [value.strip() for value in values if _opaque_scalar(value)]
        if len(normalized) != len(values) or len(set(normalized)) > 1:
            duplicate_result_conflict = True
    for paths in (
        (
            "required_output_classes",
            "adoption_axis_contract.required_output_classes",
            "task_pack_item.adoption_axis_contract.required_output_classes",
        ),
        (
            "observed_output_classes",
            "result.observed_output_classes",
            "task_pack_item.result.observed_output_classes",
            "task_pack_result.observed_output_classes",
        ),
    ):
        values = _declared_values(result, paths)
        normalized_sets: set[tuple[str, ...]] = set()
        for value in values:
            items, valid = _opaque_string_items(value)
            if not valid:
                duplicate_result_conflict = True
            else:
                normalized_sets.add(tuple(sorted(set(items))))
        if len(normalized_sets) > 1:
            duplicate_result_conflict = True
    if len(comparison_signatures) > 1 or duplicate_result_conflict:
        add(
            findings,
            severity,
            "task_pack_expectation_surface_conflict",
            "Duplicate task-pack expectation/result surfaces must converge before the remaining pack can transition.",
        )
    if not isinstance(comparison, dict):
        if expectation_declared or transition_claimed:
            add(
                findings,
                severity,
                "task_pack_expectation_comparison_missing",
                "Declared task-pack expectations or a pack transition require an expectation comparison before the remaining pack is consumed.",
            )
        return
    raw_status = comparison.get("status")
    status = raw_status.strip().lower() if isinstance(raw_status, str) else ""
    allowed_statuses = {"match", "miss", "not_evaluated", "not_applicable"}
    allowed_reviews = {"continue", "reorder", "replace", "split", "pause", "terminal_candidate"}
    raw_review = comparison.get("remaining_pack_review")
    review = raw_review.strip().lower() if isinstance(raw_review, str) else ""
    if status not in allowed_statuses:
        add(findings, severity, "task_pack_expectation_status_invalid", "Task-pack expectation comparison status is invalid.")
        return
    expected_actual_pairs = (
        ("progress_target", "progress_verdict"),
        ("progress_kind_expected", "progress_kind"),
        ("semantic_signature_expected", "semantic_signature"),
        ("blocker_signature_expected", "blocker_signature"),
    )
    detected_mismatches: list[str] = []
    actual_evidence_missing = False
    expectation_contract_invalid = False
    for expected_field, actual_field in expected_actual_pairs:
        expected = first_present(result, [expected_field, f"task_pack_item.{expected_field}"])
        actual = first_present(result, [actual_field, f"task_pack_item.result.{actual_field}", f"result.{actual_field}"])
        if expected is not None:
            if not _opaque_scalar(expected):
                expectation_contract_invalid = True
            if actual is None:
                actual_evidence_missing = True
                detected_mismatches.append(f"{expected_field}:actual_missing")
            elif not _opaque_scalar(actual):
                expectation_contract_invalid = True
            elif _opaque_scalar(expected) and expected.strip() != actual.strip():
                detected_mismatches.append(f"{expected_field}:{actual_field}")
    required_output_value = first_present(result, ["required_output_classes", "adoption_axis_contract.required_output_classes", "task_pack_item.adoption_axis_contract.required_output_classes"])
    observed_output_value = first_present(result, ["observed_output_classes", "result.observed_output_classes", "task_pack_item.result.observed_output_classes"])
    required_output_items, required_outputs_valid = _opaque_string_items(required_output_value)
    observed_output_items, observed_outputs_valid = _opaque_string_items(observed_output_value)
    required_outputs = set(required_output_items)
    observed_outputs = set(observed_output_items)
    expectation_contract_invalid = expectation_contract_invalid or not required_outputs_valid or not observed_outputs_valid
    if required_outputs and not observed_outputs:
        actual_evidence_missing = True
    if required_outputs and not required_outputs <= observed_outputs:
        detected_mismatches.append("required_output_classes:observed_output_classes")
    declared_mismatches, mismatched_axes_valid = _opaque_string_items(comparison.get("mismatched_axes"))
    expectation_contract_invalid = expectation_contract_invalid or not mismatched_axes_valid
    if expectation_contract_invalid:
        add(
            findings,
            severity,
            "task_pack_expectation_contract_invalid",
            "Task-pack expectation comparison requires bounded opaque expected, actual, output-class, and mismatch-axis IDs.",
        )
    if status == "match" and (detected_mismatches or declared_mismatches):
        add(
            findings,
            severity,
            "task_pack_expectation_false_match",
            "Task-pack expectation comparison cannot report match when expected and actual fields diverge.",
            {"detected_mismatches": detected_mismatches, "declared_mismatches": declared_mismatches},
        )
    actual_value_mismatch = bool(detected_mismatches) and not actual_evidence_missing
    if expectation_declared and status == "not_applicable" or actual_value_mismatch and status != "miss":
        add(
            findings,
            severity,
            "task_pack_expectation_status_mismatch",
            "Declared and observable task-pack expectations cannot be bypassed with a non-miss comparison status.",
            {"detected_mismatch_fields": detected_mismatches},
        )
    if actual_evidence_missing and status != "not_evaluated":
        add(
            findings,
            severity,
            "task_pack_expectation_actual_missing_status",
            "Missing actual evidence requires expectation status not_evaluated before the remaining pack is reviewed.",
            {"detected_mismatches": detected_mismatches},
        )
    if status == "miss" and review not in allowed_reviews:
        add(findings, severity, "task_pack_expectation_miss_unreviewed", "Expectation miss requires an explicit review of the remaining pack.")
    if (
        status in {"miss", "not_evaluated"}
        or bool(detected_mismatches)
        or expectation_contract_invalid
    ) and transition_claimed:
        add(findings, severity, "task_pack_expectation_unresolved_transition", "An expectation miss or unevaluated comparison cannot auto-consume the remaining pack.")
    miss_streak = first_present(result, ["expectation_miss_streak", "task_pack_item.result.expectation_miss_streak"])
    miss_streak_cap = first_present(
        result,
        ["expectation_miss_streak_cap", "task_pack_item.expectation_miss_streak_cap"],
    )
    try:
        threshold_reached = (
            miss_streak is not None
            and miss_streak_cap is not None
            and int(miss_streak) >= max(1, int(miss_streak_cap))
        )
    except (TypeError, ValueError):
        threshold_reached = False
    repeated_miss = boolish(
        first_present(
            result,
            ["repeated_expectation_miss", "task_pack_item.result.repeated_expectation_miss"],
        )
    ) or threshold_reached
    producer_expected_value = first_present(result, ["progress_kind_expected", "task_pack_item.progress_kind_expected"])
    producer_expected = isinstance(producer_expected_value, str) and producer_expected_value.strip().lower() == "goal_productive"
    progress_kind_value = first_present(result, ["progress_kind", "result.progress_kind"])
    metadata_actual = boolish(first_present(result, ["metadata_only", "result.metadata_only"])) or (
        isinstance(progress_kind_value, str) and progress_kind_value.strip().lower() == "governance_only"
    )
    if status == "miss" and review == "continue" and producer_expected and metadata_actual and repeated_miss:
        add(
            findings,
            severity,
            "task_pack_repeated_metadata_miss_auto_continue",
            "Repeated metadata-only results against an expected producer output require pack reordering, replacement, split, pause, or terminal review before continue.",
        )


def validate_state_projection(
    target: str,
    result: dict[str, Any],
    mode: str,
    findings: list[dict[str, Any]],
) -> None:
    severity = "block" if mode == "block" or target in {"validate", "derive", "report"} else "warn"
    projection_required = boolish(
        first_present(
            result,
            [
                "state_projection_required",
                "lifecycle_transition_result.state_projection_required",
                "result.state_projection_required",
            ],
        )
    )
    transition_trigger_fields = (
        "lifecycle_transition_applied",
        "authority_projection_applied",
        "task_projection_applied",
        "task_index_projection_applied",
        "state_projection_consumed",
        "successor_auto_promoted",
        "promotion_applied",
        "pack_transition_applied",
    )
    dependent_transition = projection_required or any(
        boolish(first_present(result, [field, f"lifecycle_transition_result.{field}", f"result.{field}"]))
        for field in transition_trigger_fields
    )
    projection = first_present(
        result,
        ["state_projection", "lifecycle_transition_result.state_projection", "result.state_projection"],
    )
    if not isinstance(projection, dict):
        if dependent_transition:
            add(
                findings,
                severity,
                "state_projection_missing",
                "A declared authority/task/index transition requires its state projection receipt.",
            )
        return
    status = str(projection.get("projection_status") or "").strip().lower()
    allowed = {"current", "stale_projection", "not_evaluated", "conflict"}
    if status not in allowed:
        add(findings, severity if dependent_transition else "warn", "state_projection_status_invalid", "State projection status is invalid.")
        return
    epoch_value = projection.get("projection_epoch")
    source_decision_value = projection.get("source_decision_id")
    epoch = epoch_value.strip() if _opaque_scalar(epoch_value) else ""
    source_decision_id = source_decision_value.strip() if _opaque_scalar(source_decision_value) else ""
    surface_epochs = projection.get("surface_epochs") if isinstance(projection.get("surface_epochs"), dict) else {}
    missing_current: list[str] = []
    if status == "current":
        if not epoch:
            missing_current.append("projection_epoch")
        if not source_decision_id:
            missing_current.append("source_decision_id")
        for surface in ("authority", "task", "index"):
            surface_epoch = surface_epochs.get(surface)
            if not _opaque_scalar(surface_epoch) or surface_epoch.strip() != epoch:
                missing_current.append(f"surface_epochs.{surface}")
        for digest_field in ("authority_digest", "task_digest", "index_digest"):
            if not _full_sha256(projection.get(digest_field)):
                missing_current.append(digest_field)
        if missing_current:
            add(
                findings,
                severity if dependent_transition else "warn",
                "state_projection_false_current",
                "A current state projection requires one source decision, one shared epoch, and valid authority/task/index digests.",
                {"invalid_fields": missing_current},
            )
    projection_not_current = status in {"stale_projection", "not_evaluated", "conflict"} or bool(missing_current)
    if projection_not_current and dependent_transition:
        add(
            findings,
            severity,
            "state_projection_not_current",
            "A stale, unevaluated, or conflicting authority/task/index projection cannot support transition, execution, close, or promotion.",
            {"projection_status": "false_current" if missing_current else status, "repair_first": bool(source_decision_id)},
        )
    if projection_not_current and dependent_transition and source_decision_id and boolish(result.get("user_input_required")):
        add(
            findings,
            severity,
            "state_projection_repair_precedes_user_reask",
            "The source decision is known; repair stale task/index projections before asking the user to repeat it.",
        )


def _forward_test_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    raw = first_present(result, ["skill_forward_test", "skill_forward_tests", "validation.skill_forward_test", "result.skill_forward_test"])
    if isinstance(raw, dict):
        rows = raw.get("rows") if isinstance(raw.get("rows"), list) else [raw]
    else:
        rows = raw if isinstance(raw, list) else []
    return [row for row in rows if isinstance(row, dict)]


def validate_advice_consumption_and_forward_tests(
    target: str,
    result: dict[str, Any],
    mode: str,
    findings: list[dict[str, Any]],
) -> None:
    severity = "block" if mode == "block" or target in {"validate", "report"} else "warn"
    raw_states = first_present(result, ["advice_consumption_states", "advice_consumption_state", "consumption_state", "result.advice_consumption_states"])
    malformed_state_rows: list[Any] = []
    if isinstance(raw_states, dict):
        if "rows" in raw_states:
            if isinstance(raw_states.get("rows"), list):
                candidate_rows = raw_states["rows"]
            else:
                candidate_rows = []
                malformed_state_rows.append(raw_states.get("rows"))
        else:
            candidate_rows = [raw_states]
    elif isinstance(raw_states, list):
        candidate_rows = raw_states
    elif raw_states is None:
        candidate_rows = []
    else:
        candidate_rows = []
        malformed_state_rows.append(raw_states)
    state_rows = [row for row in candidate_rows if isinstance(row, dict)]
    malformed_state_rows.extend(row for row in candidate_rows if not isinstance(row, dict))
    if malformed_state_rows:
        positive_malformed = any(
            isinstance(row, str) and row.strip().lower() in {"wired", "verified"}
            for row in malformed_state_rows
        )
        add(
            findings,
            severity if positive_malformed else "warn",
            "advice_consumption_state_unverified",
            "Malformed advice-consumption state cannot establish clause wiring or verification.",
        )
    forward_rows = _forward_test_rows(result)
    forward_by_clause = {
        row["clause_id"].strip(): row
        for row in forward_rows
        if _opaque_scalar(row.get("clause_id"))
    }
    verified_clause_ids: set[str] = set()
    positive_clause_ids: set[str] = set()
    for row in state_rows:
        clause_value = row.get("clause_id") if row.get("clause_id") is not None else row.get("advice_clause_id")
        clause_id = clause_value.strip() if _opaque_scalar(clause_value) else ""
        state = str(row.get("state") or "").strip().lower()
        if state not in {"pending", "wired", "verified"}:
            positive_like_state = isinstance(row.get("state"), str) and row["state"].strip().lower().startswith(("wire", "verif", "complete"))
            add(
                findings,
                severity if positive_like_state else "warn",
                "advice_consumption_state_invalid",
                "Advice clause consumption state is invalid.",
                {"clause_id": clause_id or None},
            )
            continue
        if state in {"wired", "verified"}:
            if clause_id:
                positive_clause_ids.add(clause_id)
            wired = bool(
                clause_id
                and _opaque_scalar(row.get("consumer_context_id") or row.get("consumer_id"))
                and boolish(row.get("invocation_completed"))
                and boolish(row.get("return_contract_valid"))
                and boolish(
                    row.get("consumer_identity_echo_valid")
                    or row.get("identity_echo_valid")
                    or row.get("artifact_identity_echo_valid")
                )
                and boolish(row.get("decision_path_consumed"))
                and _opaque_scalar(row.get("consumer_receipt_ref"))
                and _full_sha256(row.get("consumer_receipt_sha256"))
                and not boolish(row.get("documentation_only"))
                and not boolish(row.get("hook_declared_only"))
            )
            if not wired:
                add(
                    findings,
                    severity,
                    "advice_clause_wired_without_consumer_receipt",
                    "Copied text, task creation, hook declaration, or self-attestation cannot establish wired advice consumption.",
                    {"clause_id": clause_id or None},
                )
        if state == "verified":
            verified_clause_ids.add(clause_id)
            if clause_id not in forward_by_clause:
                add(findings, severity, "advice_clause_verified_without_forward_test", "Verified advice consumption requires a clause-bound forward-test receipt.", {"clause_id": clause_id or None})

    allowed_layer_statuses = {"pass", "passed", "fail", "failed", "not_evaluated", "deferred"}
    for row in forward_rows:
        clause_value = row.get("clause_id")
        scenario_value = row.get("scenario_id")
        clause_id = clause_value.strip() if _opaque_scalar(clause_value) else ""
        scenario_id = scenario_value.strip() if _opaque_scalar(scenario_value) else ""
        positive_claim = clause_id in positive_clause_ids or str(row.get("verification_claim") or "").lower() in {"wired", "verified", "complete"}
        precondition_ids = row.get("precondition_ids")
        preconditions_valid = isinstance(precondition_ids, list) and bool(precondition_ids) and all(
            _opaque_scalar(item) for item in precondition_ids
        )
        injected_fault_valid = _opaque_scalar(row.get("injected_fault_class"))
        expected = row.get("expected_decision_state")
        observed = row.get("observed_decision_state")
        decisions_present = _opaque_scalar(expected) and _opaque_scalar(observed)
        layer_values = {
            key: str(row.get(key) or "").strip().lower()
            for key in ("contract_test_status", "consumer_test_status", "forward_scenario_status", "regression_status")
        }
        invalid_layers = [key for key, value in layer_values.items() if value not in allowed_layer_statuses]
        if not clause_id or not scenario_id or invalid_layers or not preconditions_valid or not injected_fault_valid or not decisions_present:
            add(
                findings,
                severity if positive_claim else "warn",
                "skill_forward_test_malformed",
                "Forward-test rows require clause/scenario IDs, opaque preconditions, an injected fault class, expected/observed decisions, and all four bounded layer statuses.",
                {
                    "clause_id": clause_id or None,
                    "invalid_layers": invalid_layers,
                    "preconditions_valid": preconditions_valid,
                    "injected_fault_valid": injected_fault_valid,
                    "decisions_present": decisions_present,
                },
            )
            continue
        all_pass = all(value in {"pass", "passed"} for value in layer_values.values())
        receipt_valid = _opaque_scalar(row.get("consumer_receipt_ref")) and _full_sha256(row.get("consumer_receipt_sha256"))
        runtime_deferred = str(row.get("runtime_forward_verification") or result.get("runtime_forward_verification") or "").strip() == "deferred_by_explicit_single_skill_constraint"
        positive_claim = clause_id in verified_clause_ids or str(row.get("verification_claim") or "").lower() in {"verified", "complete"}
        if positive_claim and (not all_pass or expected != observed or not receipt_valid or runtime_deferred):
            add(
                findings,
                severity,
                "skill_forward_test_verified_without_full_receipt",
                "A verified claim requires contract, external consumer, negative forward-decision, and happy-path regression evidence bound to the same clause/scenario.",
                {"clause_id": clause_id, "runtime_forward_verification_deferred": runtime_deferred},
            )


def validate_verdict_axes(
    target: str,
    result: dict[str, Any],
    mode: str,
    findings: list[dict[str, Any]],
) -> None:
    declared = {
        axis: _declared_values(
            result,
            (
                axis,
                f"verdict_axes.{axis}",
                f"result.{axis}",
                f"result.verdict_axes.{axis}",
                f"authoritative_projection.{axis}",
                f"finalization.authoritative_projection.{axis}",
                f"result.authoritative_projection.{axis}",
            ),
        )
        for axis in VERDICT_AXES
    }
    raw_version = first_present(
        result,
        ["verdict_contract_version", "verdict_axes.schema_version", "result.verdict_contract_version"],
    )
    try:
        contract_version = int(raw_version) if raw_version is not None else None
    except (TypeError, ValueError):
        contract_version = None
    any_axes = any(values for values in declared.values())
    current_required = target in {"validate", "derive", "report"} and _positive_decision_claim(target, result)
    severity = (
        "block"
        if mode == "block"
        or target in {"validate", "report"}
        or _positive_decision_claim(target, result)
        else "warn"
    )
    if raw_version is None and (any_axes or current_required):
        add(
            findings,
            severity,
            "verdict_contract_version_missing",
            "Lifecycle verdicts require version 1; legacy packets require explicit version 0.",
        )
        return
    if raw_version is not None and contract_version not in {0, 1}:
        add(findings, severity, "verdict_contract_version_invalid", "Verdict contract version must be 1 or explicit legacy version 0.")
        return
    if contract_version == 0:
        return
    if contract_version != 1 and not any_axes:
        return
    statuses: dict[str, str] = {}
    for axis, values in declared.items():
        if not values:
            add(findings, severity, "verdict_axis_missing", "Current verdict-axis packets must preserve every lifecycle verdict axis.", {"axis": axis})
            continue
        observed_statuses = {_normalized_verdict_status(value) for value in values}
        if len(observed_statuses) > 1:
            status = "conflicted"
            add(
                findings,
                severity,
                "verdict_axis_conflicted",
                "Duplicate current surfaces disagree on one verdict axis; preserve the axis as conflicted instead of selecting a favorable value.",
                {"axis": axis, "observed_statuses": sorted(observed_statuses)},
            )
        else:
            status = next(iter(observed_statuses))
        statuses[axis] = status
        if status not in VERDICT_AXIS_STATUSES:
            add(findings, severity, "verdict_axis_status_invalid", "Verdict axis status is invalid.", {"axis": axis, "status": status})
        for value in values:
            value_status = _normalized_verdict_status(value)
            evidence = value.get("evidence_ref") or value.get("evidence_refs") if isinstance(value, dict) else None
            if value_status != "not_applicable" and not non_empty(evidence):
                add(findings, severity, "verdict_axis_evidence_missing", "Verdict axes require a bounded evidence reference.", {"axis": axis})
                break
    goal_status = statuses.get("goal_readiness_verdict")
    implementation_blocking = {
        axis
        for axis in ("task_acceptance_verdict", "artifact_truth_verdict", "artifact_semantic_verdict")
        if statuses.get(axis) in {"fail", "blocked", "partial", "not_evaluated", "conflicted"}
    }
    readiness_blocking = {
        axis
        for axis in VERDICT_AXES[:-1]
        if statuses.get(axis) in {"fail", "blocked", "partial", "not_evaluated", "conflicted"}
    }
    if implementation_blocking and str(value_for(result, "progress_verdict") or "").lower() == "advanced":
        add(
            findings,
            severity,
            "implementation_axis_failure_counted_as_progress",
            "Task acceptance, artifact truth, or artifact semantic failure cannot be upgraded to advanced progress.",
            {"blocking_axes": sorted(implementation_blocking)},
        )
    if readiness_blocking and goal_status == "pass":
        add(
            findings,
            severity,
            "failed_axis_counted_as_goal_ready",
            "Goal readiness cannot pass while a required lifecycle axis is failed, blocked, partial, not evaluated, or conflicted.",
            {"blocking_axes": sorted(readiness_blocking)},
        )
    failed_axes = {
        axis
        for axis, status in statuses.items()
        if status in {"fail", "blocked", "partial", "not_evaluated", "conflicted"}
    }
    retry_axis = str(first_present(result, ["retry_axis", "selected_remediation_axis", "derive.retry_axis"]) or "").strip()
    if target == "derive" and failed_axes and retry_axis and retry_axis not in failed_axes:
        add(
            findings,
            severity,
            "derive_retry_axis_mismatch",
            "Derive retry routing must target an actually failed verdict axis.",
            {"retry_axis": retry_axis, "failed_axes": sorted(failed_axes)},
        )


def has_explicit_empty(result: dict[str, Any], field: str, expected_type: type[list[Any]] | type[dict[str, Any]]) -> bool:
    containers = [result]
    for key in ("result", "packet"):
        nested = result.get(key)
        if isinstance(nested, dict):
            containers.append(nested)
    return any(field in container and isinstance(container.get(field), expected_type) and not container[field] for container in containers)


def reasoned_na_allows_explicit_empty(target: str, field: str, result: dict[str, Any]) -> bool:
    if target == "qualitative_review":
        status = str(value_for(result, "review_status") or value_for(result, "status") or "").strip().lower()
        reason = first_present(
            result,
            ["reason", "review_skipped_reason", "qualitative_review_pending_reason", "reviewer_delegation_unavailable_reason", "blockers"],
        )
        if status in {"not_applicable", "blocked"} and non_empty(reason):
            if field == "reviewer_routing":
                return has_explicit_empty(result, field, dict)
            if field == "evidence_paths":
                return has_explicit_empty(result, field, list)
    if target == "validation_set_build":
        status = str(value_for(result, "validation_set_status") or value_for(result, "status") or "").strip().lower()
        reason = first_present(
            result,
            ["validation_set_not_applicable_reason", "validation_set_skipped_reason", "validation_set_blocked_reason", "reason", "blockers"],
        )
        return status == "not_applicable" and non_empty(reason) and field == "evidence_paths" and has_explicit_empty(result, field, list)
    if target == "schema_post_derive":
        status = str(value_for(result, "schema_status") or value_for(result, "status") or "").strip().lower()
        reason = first_present(
            result,
            ["schema_skipped_reason", "schema_terminal_reason", "schema_blocked_reason", "reason", "blockers"],
        )
        terminal = {"terminal", "terminal_blocked", "skipped", "not_applicable", "blocked", "deferred"}
        return status in terminal and non_empty(reason) and field == "evidence_paths" and has_explicit_empty(result, field, list)
    return False


def long_run_state_checked(contract_context: dict[str, Any] | None, result: dict[str, Any]) -> bool:
    markers: list[Any] = [result.get("long_run_state_checked")]
    if isinstance(contract_context, dict):
        markers.append(contract_context.get("long_run_state_checked"))
        cycle_state = contract_context.get("cycle_state")
        if isinstance(cycle_state, dict):
            markers.append(cycle_state.get("long_run_state_checked"))
        long_run_state = contract_context.get("long_run_state")
        if isinstance(long_run_state, dict):
            markers.append(long_run_state.get("checked"))
    return any(value is True for value in markers)


def pending_long_run_context(contract_context: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Extract scalar pending-run evidence from a caller-supplied cycle context."""

    if not isinstance(contract_context, dict):
        return []
    candidates: list[dict[str, Any]] = []
    seen_objects: set[int] = set()

    def append(value: Any) -> None:
        if isinstance(value, dict) and id(value) not in seen_objects:
            candidates.append(value)
            seen_objects.add(id(value))

    append(contract_context)
    for key in ("latest_event", "run", "monitor_result"):
        append(contract_context.get(key))
    steps = contract_context.get("steps")
    if isinstance(steps, dict):
        for value in steps.values():
            append(value)
    events = contract_context.get("events")
    if isinstance(events, list):
        for value in events:
            append(value)
    latest_events = contract_context.get("latest_events")
    if isinstance(latest_events, list):
        for value in latest_events:
            append(value)
    cycle_state = contract_context.get("cycle_state")
    if isinstance(cycle_state, dict):
        append(cycle_state)
        append(cycle_state.get("latest_event"))
        nested_latest_events = cycle_state.get("latest_events")
        if isinstance(nested_latest_events, list):
            for value in nested_latest_events:
                append(value)
        nested_events = cycle_state.get("events")
        if isinstance(nested_events, list):
            for value in nested_events:
                append(value)

    pending: list[dict[str, Any]] = []
    seen_runs: set[tuple[str, str, str]] = set()
    for candidate in candidates:
        status = str(
            candidate.get("execution_status")
            or candidate.get("source_status")
            or candidate.get("status")
            or ""
        ).strip().lower()
        event_kind = str(candidate.get("event_kind") or "").strip().lower()
        role = str(candidate.get("long_run_role") or "").strip().lower()
        run_id = str(candidate.get("run_id") or "").strip()
        is_long_run = bool(candidate.get("long_run_branch")) or event_kind.startswith("long_run_") or role in {
            "launch",
            "monitor",
            "harvest",
            "finalize",
        }
        if status not in PENDING_LONG_RUN_STATUSES or not (is_long_run or run_id):
            continue
        task_id = str(candidate.get("owner_task_id") or candidate.get("task_id") or "").strip()
        identity = (run_id, task_id, status)
        if identity in seen_runs:
            continue
        seen_runs.add(identity)
        pending.append(
            {
                "run_id": run_id or None,
                "task_id": task_id or None,
                "execution_status": status,
                "event_kind": event_kind or None,
                "remaining_validation": candidate.get("remaining_validation"),
            }
        )
    return pending


def _validate(
    target: str,
    result: dict[str, Any],
    mode: str,
    rule_registry: RuleRegistry,
    contract_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    derive_mode = str(first_present(result, ["derive_mode", "mode", "derive.mode", "result.derive_mode"]) or "").strip().lower()
    if target == "derive" and derive_mode == "initial_init":
        required_fields = [
            "next_task_id",
            "selected_task_source",
            "progress_kind",
            "semantic_signature",
            "evidence_paths",
        ]
    else:
        required_fields = COMMON_FIELDS[target]
    missing = [
        field
        for field in required_fields
        if not has_value(result, field) and not reasoned_na_allows_explicit_empty(target, field, result)
    ]
    severity = "block" if mode == "block" or target == "report" else "warn"
    for field in missing:
        add(findings, severity, "missing_required_field", f"`{target}` result is missing `{field}`.", {"field": field})

    validate_decision_identity_and_compatibility(target, result, mode, findings)
    validate_metric_applicability_consumption(target, result, mode, findings)
    validate_verification_axes(target, result, mode, findings)
    validate_task_pack_expectation_comparison(target, result, mode, findings)
    validate_state_projection(target, result, mode, findings)
    validate_advice_consumption_and_forward_tests(target, result, mode, findings)
    validate_verdict_axes(target, result, mode, findings)
    for item in validate_finalization_contract(target, result, contract_context):
        add(
            findings,
            "block",
            str(item["code"]),
            str(item["message"]),
            item.get("evidence"),
        )
    for item in validate_lifecycle_extensions(target, result):
        add(
            findings,
            str(item.get("severity") or "block"),
            str(item["code"]),
            str(item["message"]),
            item.get("evidence"),
        )

    if target in AGENT_ROUTING_TARGETS:
        applicability = str(value_for(result, "agent_routing_applicability") or "").lower()
        if applicability not in {"delegated", "deterministic_only", "delegation_unavailable"}:
            add(
                findings,
                severity,
                "agent_routing_applicability_missing",
                "Agent-bearing phase must declare whether work was delegated, deterministic-only, or unavailable.",
            )
        elif applicability == "delegated":
            for field in ("policy_id", "profile_id", "routing_tier", "requested_model", "requested_reasoning_effort", "routing_reason_codes", "routing_enforcement"):
                if not has_value(result, field):
                    add(findings, severity, "delegated_routing_evidence_missing", f"Delegated result is missing `{field}`.", {"field": field})
            if value_for(result, "routing_violations") is None:
                add(findings, severity, "delegated_routing_evidence_missing", "Delegated result is missing `routing_violations`.", {"field": "routing_violations"})
            requested_model = str(value_for(result, "requested_model") or "")
            requested_model_ref = str(value_for(result, "requested_model_ref") or "")
            model_configuration_status = str(value_for(result, "model_configuration_status") or "")
            model_binding_receipt = value_for(result, "model_binding_receipt")
            requested_effort = str(value_for(result, "requested_reasoning_effort") or "")
            enforcement = str(value_for(result, "routing_enforcement") or "")
            claim = {
                "policy_id": value_for(result, "policy_id"),
                "profile_id": value_for(result, "profile_id"),
                "routing_tier": value_for(result, "routing_tier"),
                "requested_model_ref": requested_model_ref,
                "requested_model": requested_model,
                "model_configuration_status": model_configuration_status,
                "model_binding_receipt": model_binding_receipt,
                "requested_reasoning_effort": requested_effort,
                "routing_reason_codes": value_for(result, "routing_reason_codes"),
                "routing_signals": value_for(result, "routing_signals") or {},
                "routing_signal_evidence": value_for(result, "routing_signal_evidence") or {},
                "routing_violations": value_for(result, "routing_violations") or [],
                "final_direction_ownership": value_for(result, "final_direction_ownership"),
                "routing_enforcement": enforcement,
                "max_escalation_reason": value_for(result, "max_escalation_reason"),
                "prior_tier5_unresolved": value_for(result, "prior_tier5_unresolved"),
                "prior_tier5_evidence": value_for(result, "prior_tier5_evidence"),
                "agent_count": value_for(result, "agent_count"),
            }
            for routing_finding in MODEL_EFFORT_ROUTER.validate_claim(claim, MODEL_EFFORT_POLICY, target):
                code = str(routing_finding.get("code") or "model_effort_routing_invalid")
                add(
                    findings,
                    "block",
                    code,
                    "Delegated model/effort claim violates the tier routing policy.",
                    routing_finding,
                )
            if (
                requested_model
                and (model_configuration_status or "reference_only") == "reference_only"
                and requested_model not in SUPPORTED_AGENT_MODELS
            ):
                add(findings, "block", "unsupported_requested_model", "Requested model is outside the tier routing policy.", {"requested_model": requested_model})
            if requested_effort and requested_effort not in SUPPORTED_AGENT_EFFORTS:
                add(findings, "block", "unsupported_requested_effort", "Requested effort is outside the tier routing policy.", {"requested_reasoning_effort": requested_effort})
            if enforcement and enforcement not in ROUTING_ENFORCEMENT_VALUES:
                add(findings, "block", "invalid_routing_enforcement", "Delegated result has invalid routing enforcement.", {"routing_enforcement": enforcement})
            if enforcement == "enforced" and (not has_value(result, "actual_model") or not has_value(result, "actual_reasoning_effort")):
                add(findings, "block", "enforced_routing_actual_evidence_missing", "Enforced routing requires actual model and effort evidence.")
            if enforcement in {"prompt_only", "inherited_unverified"} and not has_value(result, "routing_limitation"):
                add(findings, severity, "routing_limitation_missing", "Non-enforced routing requires a concrete limitation note.")
            actual_model = str(value_for(result, "actual_model") or "")
            actual_effort = str(value_for(result, "actual_reasoning_effort") or "")
            if actual_effort and actual_effort not in SUPPORTED_AGENT_EFFORTS:
                add(findings, "block", "unsupported_actual_effort", "Actual effort is outside the tier routing policy.", {"actual_reasoning_effort": actual_effort})
            if model_configuration_status == "resolved" and actual_model and requested_model and actual_model != requested_model:
                add(findings, "block", "actual_model_route_mismatch", "Actual model does not match the validated requested route.", {"requested_model": requested_model, "actual_model": actual_model})
            if actual_effort and requested_effort and actual_effort != requested_effort:
                add(findings, "block", "actual_effort_route_mismatch", "Actual effort does not match the validated requested route.", {"requested_reasoning_effort": requested_effort, "actual_reasoning_effort": actual_effort})
        elif applicability == "delegation_unavailable" and not has_value(result, "routing_limitation"):
            add(findings, severity, "routing_limitation_missing", "Unavailable delegation requires a concrete routing limitation.")

    def require_context_field(field: str, code: str, message: str) -> None:
        if has_value(result, field):
            return
        if field not in missing:
            missing.append(field)
        add(findings, "block" if mode == "block" or target == "report" else "warn", code, message, {"field": field})

    raw_step = result.get("step")
    step = str(raw_step).strip() if raw_step is not None else ""
    if not step:
        if "step" not in missing:
            missing.append("step")
        add(
            findings,
            "block" if mode == "block" else "warn",
            "ledger_step_missing",
            f"`{target}` result lacks top-level canonical `step`; direct ledger append must pass `--step {target}` or use an event envelope.",
            {"expected_step": target},
        )
    elif step not in CANONICAL_LEDGER_STEPS:
        add(
            findings,
            "block" if mode == "block" else "warn",
            "ledger_step_noncanonical",
            f"`{target}` result has noncanonical ledger `step`.",
            {"step": step, "expected_step": target},
        )
    elif step != target:
        add(
            findings,
            "block" if mode == "block" else "warn",
            "ledger_step_mismatch",
            f"`{target}` result has `step: {step}`; expected `step: {target}` for direct ledger append.",
            {"step": step, "expected_step": target},
        )

    if target in ADVICE_REQUIRED_TARGETS and active_advice_present(result) and not has_value(result, "used_advice"):
        if not advice_handling_rationale_present(result):
            add(
                findings,
                "block",
                "active_advice_unhandled",
                f"`{target}` result has active external advice in scope but lacks `used_advice` or an explicit advice defer/reject/not-applicable rationale.",
                {"required": ["used_advice", "advice_deferred_reason|advice_rejected_reason|advice_not_applicable_reason|advice_handling_rationale"]},
            )

    explicit_report_key_divergence = boolish(
        first_present(
            result,
            [
                "report_key_divergence",
                "report_key_integrity_gate.report_key_divergence",
                "validation.report_key_integrity_gate.report_key_divergence",
                "result.report_key_integrity_gate.report_key_divergence",
            ],
        )
    )
    auto_report_key_divergences = report_key_divergences(result)
    auto_report_key_duplicate_matches = report_key_duplicate_matches(result)
    if explicit_report_key_divergence or auto_report_key_divergences:
        report_key_severity = "block" if mode == "block" or target in {"validate", "report"} else "warn"
        add(
            findings,
            report_key_severity,
            "report_key_divergence",
            "`report_key_divergence` means one canonical projection has divergent duplicate terminal keys across one or more report surfaces; pass/close/adoption/baseline/comparison consumption is invalid until the reports converge.",
            {"auto_detected": auto_report_key_divergences[:20], "explicit_report_key_divergence": explicit_report_key_divergence},
        )
    if auto_report_key_duplicate_matches:
        add(
            findings,
            "warn",
            "report_key_duplicate_schema_debt",
            "Matching duplicate terminal report keys are schema debt; consumption may continue, but the report should be normalized to one authoritative copy.",
            {"auto_detected": auto_report_key_duplicate_matches[:20]},
        )

    auto_report_body_divergences = actual_report_body_divergences(result)
    report_body_divergence = boolish(
        first_present(
            result,
            [
                "report_body_divergence",
                "actual_artifact_truth.report_body_divergence",
                "validation.actual_artifact_truth.report_body_divergence",
                "result.report_body_divergence",
            ],
        )
    ) or bool(auto_report_body_divergences)
    actual_truth_required = boolish(
        first_present(
            result,
            [
                "actual_body_truth_required",
                "acceptance_required_actual_body_truth",
                "target_metric_delta.actual_body_truth_required",
                "acceptance.actual_body_truth_required",
            ],
        )
    )
    truth_basis = str(
        first_present(
            result,
            [
                "truth_basis",
                "actual_body_truth_basis",
                "actual_artifact_truth.truth_basis",
                "target_metric_delta.truth_basis",
            ],
        )
        or ""
    ).strip().lower()
    if report_body_divergence:
        add(
            findings,
            (
                "block"
                if mode == "block"
                or target in {"validate", "report"}
                or _positive_decision_claim(target, result)
                else "warn"
            ),
            "report_body_divergence",
            "The canonical actual-artifact body projection disagrees with the consumed report; this is distinct from duplicate report-key divergence.",
            {"auto_detected": auto_report_body_divergences[:20]},
        )
    if actual_truth_required and truth_basis in {"", "not_evaluated", "missing", "unknown"}:
        add(
            findings,
            "block" if mode == "block" or target == "validate" else "warn",
            "actual_body_truth_not_evaluated",
            "Acceptance-required actual-artifact body truth was not independently evaluated.",
        )

    required_consumer_ids: list[Any] = []
    for declared_ids in _declared_values(
        result,
        (
            "required_consumer_ids",
            "adapter_contract.required_consumer_ids",
            "consumer_context_conformance.required_consumer_ids",
            "adapter_consumer_conformance.required_consumer_ids",
            "result.required_consumer_ids",
            "result.consumer_context_conformance.required_consumer_ids",
            "result.adapter_consumer_conformance.required_consumer_ids",
        ),
    ):
        for consumer_id in list_values(declared_ids):
            if consumer_id not in required_consumer_ids:
                required_consumer_ids.append(consumer_id)
    conformance_rows: list[Any] = []
    malformed_conformance_aliases: list[str] = []
    for conformance_path in (
        "consumer_context_conformance",
        "adapter_consumer_conformance",
        "result.consumer_context_conformance",
        "result.adapter_consumer_conformance",
    ):
        declared_surfaces = _declared_values(result, (conformance_path,))
        if not declared_surfaces:
            continue
        conformance_surface = declared_surfaces[0]
        rows_value = (
            conformance_surface.get("rows")
            if isinstance(conformance_surface, dict)
            else conformance_surface
        )
        if isinstance(rows_value, list):
            conformance_rows.extend(rows_value)
        elif not (isinstance(conformance_surface, dict) and "rows" not in conformance_surface):
            malformed_conformance_aliases.append(conformance_path)
    if malformed_conformance_aliases:
        add(
            findings,
            (
                "block"
                if mode == "block"
                or target == "validate"
                or _positive_decision_claim(target, result)
                else "warn"
            ),
            "consumer_context_conformance_alias_malformed",
            "Every declared consumer-conformance alias must contain a row list; malformed duplicates cannot be ignored in favor of a valid surface.",
            {"aliases": malformed_conformance_aliases},
        )
    conformance_by_id: dict[str, list[dict[str, Any]]] = {}
    for row in conformance_rows:
        if isinstance(row, dict) and row.get("consumer_context_id"):
            conformance_by_id.setdefault(str(row["consumer_context_id"]), []).append(row)
    decision_identity = first_present(
        result,
        [
            "decision_input_identity",
            "decision_artifact_ref",
            "selected_artifact_ref",
            "artifact_ref",
            "actual_artifact_ref",
            "result.decision_input_identity",
        ],
    )
    decision_identity = decision_identity if isinstance(decision_identity, dict) else {}
    body_fingerprint_values = []
    if "body_projection_fingerprint" in decision_identity:
        body_fingerprint_values.append(decision_identity.get("body_projection_fingerprint"))
    body_fingerprint_values.extend(
        _declared_values(
            result,
            (
                "body_projection_fingerprint",
                "actual_artifact_truth.body_projection_fingerprint",
                "quality_review.body_projection_fingerprint",
                "result.body_projection_fingerprint",
            ),
        )
    )
    expected_body_fingerprint = next(
        (value for value in body_fingerprint_values if non_empty(value)),
        None,
    )
    verification_input_values = []
    if "verification_input_ids" in decision_identity:
        verification_input_values.append(decision_identity.get("verification_input_ids"))
    verification_input_values.extend(
        _declared_values(
            result,
            (
                "verification_input_ids",
                "verification_source_separation_gate.verification_input_ids",
                "result.verification_input_ids",
            ),
        )
    )
    expected_verification_input_ids = verification_input_values[0] if verification_input_values else None
    input_fingerprint_values = []
    if "input_fingerprints" in decision_identity:
        input_fingerprint_values.append(decision_identity.get("input_fingerprints"))
    input_fingerprint_values.extend(
        _declared_values(
            result,
            (
                "input_fingerprints",
                "verification_source_separation_gate.input_fingerprints",
                "result.input_fingerprints",
            ),
        )
    )
    expected_input_fingerprints = input_fingerprint_values[0] if input_fingerprint_values else None
    expected_cycle_id = str(first_present(result, ["cycle_id", "result.cycle_id"]) or "").strip()
    expected_input_state_fingerprint = str(
        first_present(result, ["input_state_fingerprint", "result.input_state_fingerprint"])
        or ""
    ).strip()
    expected_attempt_identity = str(
        first_present(result, ["attempt_identity", "result.attempt_identity"]) or ""
    ).strip()
    expected_cohort_present = bool(list_values(expected_verification_input_ids)) or bool(
        expected_input_fingerprints
        if isinstance(expected_input_fingerprints, dict)
        else None
    )
    invalid_consumers: list[str] = []
    consumer_mismatches: dict[str, list[str]] = {}
    for consumer_id in required_consumer_ids:
        candidate_rows = conformance_by_id.get(str(consumer_id)) or []
        mismatched_fields: set[str] = set()

        def row_valid(row: dict[str, Any]) -> bool:
            row_mismatches: list[str] = []
            if not expected_cycle_id or row.get("cycle_id") != expected_cycle_id:
                row_mismatches.append("cycle_id")
            if (
                not _full_sha256(expected_input_state_fingerprint)
                or row.get("input_state_fingerprint") != expected_input_state_fingerprint
            ):
                row_mismatches.append("input_state_fingerprint")
            if not expected_attempt_identity or row.get("attempt_identity") != expected_attempt_identity:
                row_mismatches.append("attempt_identity")
            for field in ("artifact_id", "artifact_sha256", "production_lane_identity"):
                expected = decision_identity.get(field)
                if not non_empty(expected) or row.get(field) != expected:
                    row_mismatches.append(field)
            if not _full_sha256(expected_body_fingerprint):
                row_mismatches.append("body_projection_fingerprint")
            elif row.get("body_projection_fingerprint") != expected_body_fingerprint:
                row_mismatches.append("body_projection_fingerprint")
            if not expected_cohort_present:
                row_mismatches.append("source_cohort")
            if expected_verification_input_ids is not None:
                expected_ids = sorted(str(item) for item in list_values(expected_verification_input_ids))
                observed_ids = sorted(str(item) for item in list_values(row.get("verification_input_ids")))
                if observed_ids != expected_ids:
                    row_mismatches.append("verification_input_ids")
            if expected_input_fingerprints is not None and row.get("input_fingerprints") != expected_input_fingerprints:
                row_mismatches.append("input_fingerprints")
            mismatched_fields.update(row_mismatches)
            invocation_status = str(row.get("invocation_status") or "").strip().lower()
            return_status = str(row.get("return_contract_status") or "").strip().lower()
            echo_status = str(row.get("artifact_identity_echo_status") or "").strip().lower()
            consumption_status = str(row.get("decision_consumption_status") or "").strip().lower()
            return not row_mismatches and all(
                (
                    boolish(row.get("adapter_loaded")),
                    boolish(row.get("hook_resolved")),
                    boolish(row.get("hook_callable") or row.get("required_hook_callable")),
                    boolish(row.get("signature_bind_passed") or row.get("hook_signature_compatible")),
                    boolish(row.get("invocation_completed")) or invocation_status in {"complete", "completed", "pass", "passed", "success"},
                    boolish(row.get("return_contract_valid")) or return_status in {"valid", "pass", "passed"},
                    boolish(row.get("artifact_identity_echo_valid")) or echo_status in {"valid", "pass", "passed", "matched"},
                    boolish(row.get("value_consumed_by_decision")) or consumption_status in {"consumed", "pass", "passed"},
                    str(row.get("evidence_provenance") or "").strip().lower()
                    in {"independently_verified", "self_grounded"},
                    non_empty(row.get("probe_evidence_ref")),
                    _full_sha256(row.get("probe_evidence_sha256")),
                    str(row.get("probe_evidence_sha256") or "").lower()
                    == _consumer_receipt_binding_sha256(row),
                )
            )

        valid = bool(candidate_rows) and all(row_valid(row) for row in candidate_rows)
        if not valid:
            invalid_consumers.append(str(consumer_id))
            if mismatched_fields:
                consumer_mismatches[str(consumer_id)] = sorted(mismatched_fields)
    if invalid_consumers:
        add(
            findings,
            "block" if mode == "block" or target == "validate" else "warn",
            "required_consumer_context_not_evaluated",
            "Required adapter consumer contexts lack a full external invocation receipt; import, hook-name presence, or adapter self-attestation is insufficient.",
            {
                "consumer_context_ids": invalid_consumers,
                "mismatched_fields": consumer_mismatches or None,
            },
        )

    if target == "validate":
        validation_verdict_early = str(value_for(result, "validation_verdict") or "").strip().lower()
        required_artifact_class_early = str(first_present(result, ["required_artifact_class", "acceptance.required_artifact_class"]) or "").strip()
        observed_artifact_class_early = str(first_present(result, ["observed_artifact_class", "artifact_class", "target_metric_delta.artifact_class"]) or "").strip()
        if (
            validation_verdict_early in {"complete", "passed", "pass", "success"}
            and required_artifact_class_early
            and observed_artifact_class_early
            and required_artifact_class_early != observed_artifact_class_early
        ):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_complete_required_artifact_class_mismatch",
                "Completion is invalid when the observed artifact class differs from the acceptance-required artifact class, regardless of progress verdict.",
                {"required_artifact_class": required_artifact_class_early, "observed_artifact_class": observed_artifact_class_early},
            )
    execution_status = str(value_for(result, "execution_status") or "").lower()
    pending_long_runs = pending_long_run_context(contract_context)
    checked_long_run_state = long_run_state_checked(contract_context, result)
    context = RuleContext(
        target=target,
        result=result,
        mode=mode,
        findings=findings,
        missing=missing,
        require_context_field=require_context_field,
        metadata={
            "contract_context": contract_context,
            "execution_status": execution_status,
            "explicit_report_key_divergence": explicit_report_key_divergence,
            "auto_report_key_divergences": auto_report_key_divergences,
            "pending_long_runs": pending_long_runs,
            "long_run_state_checked": checked_long_run_state,
        },
    )
    SESSION_AUDIT_RULE.validate(context)
    rule_registry.validate(context)

    status = "ok"
    if any(item["severity"] == "block" for item in findings):
        status = "block"
    elif findings:
        status = "warn"
    return {"status": status, "target": target, "mode": mode, "findings": findings, "missing_fields": missing}


class ResultContractValidator:
    """Reusable validator with an injectable target-rule registry."""

    def __init__(self, rule_registry: RuleRegistry | None = None) -> None:
        self.rule_registry = rule_registry or default_rule_registry()

    def validate(
        self,
        target: str,
        result: dict[str, Any],
        mode: str = "warn",
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if target not in TARGETS:
            raise ValueError(f"unsupported result-contract target: {target}")
        if mode not in {"warn", "block"}:
            raise ValueError(f"unsupported result-contract mode: {mode}")
        return _validate(target, result, mode, self.rule_registry, context)


DEFAULT_VALIDATOR = ResultContractValidator()


def validate(
    target: str,
    result: dict[str, Any],
    mode: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Backward-compatible functional facade."""

    return DEFAULT_VALIDATOR.validate(target, result, mode, context)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a subskill result contract for orchestrate-task-cycle.")
    parser.add_argument("--target", required=True, choices=sorted(TARGETS))
    parser.add_argument("--result", default="-", help="Result JSON path, JSON string, or '-' for stdin.")
    parser.add_argument("--context", help="Optional cycle/long-run context JSON path or JSON string.")
    parser.add_argument("--mode", choices=("warn", "block"), default="warn")
    args = parser.parse_args(argv)

    contract_context = load_json(args.context) if args.context else None
    output = validate(args.target, load_json(args.result), args.mode, contract_context)
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if output["status"] != "block" else 2


if __name__ == "__main__":
    raise SystemExit(main())
