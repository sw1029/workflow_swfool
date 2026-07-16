from __future__ import annotations

from dataclasses import dataclass

from typing import Any

from .common import add, boolish, first_present
from .receipts import (
    _declared_values,
    _finite_numeric,
    _metric_gate_signature,
    _opaque_scalar,
    _opaque_string_items,
)


@dataclass
class _MetricState:
    target: Any
    result: Any
    mode: Any
    findings: Any
    gate: Any
    gate_paths: Any
    gate_values: Any
    applicability_proof_present: Any = None
    claim_relevant: Any = None
    consumed: Any = None
    declared_ids: Any = None
    evaluation_status: Any = None
    evaluation_status_invalid: Any = None
    excluded: Any = None
    improved_items: Any = None
    improved_valid: Any = None
    policy: Any = None
    policy_by_status: Any = None
    policy_contract_invalid: Any = None
    positive_metric_claim: Any = None
    severity: Any = None
    summary_by_status: Any = None
    summary_contract_invalid: Any = None
    vector_ids: Any = None
    vector_contract_invalid: bool = False
    summary_divergence: bool = False


def _validate_metric_applicability_consumption_part_01(state: _MetricState) -> None:
    findings = state.findings
    gate = state.gate
    gate_values = state.gate_values
    mode = state.mode
    result = state.result
    target = state.target
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
    state.evaluation_status = evaluation_status
    state.evaluation_status_invalid = evaluation_status_invalid
    state.excluded = excluded
    state.policy = policy
    state.severity = severity
    state.summary_by_status = summary_by_status
    state.summary_contract_invalid = summary_contract_invalid


def _validate_metric_applicability_consumption_part_02(state: _MetricState) -> None:
    policy_by_status = {
        "applicable": set(),
        "not_applicable": set(),
        "insufficient_evidence": set(),
        "invalid_contract": set(),
    }
    policy_contract_invalid = False
    applicability_proof_present = False
    declared_ids: set[str] = set()
    state.applicability_proof_present = applicability_proof_present
    state.declared_ids = declared_ids
    state.policy_by_status = policy_by_status
    state.policy_contract_invalid = policy_contract_invalid


def _validate_metric_applicability_consumption_part_03(state: _MetricState) -> None:
    applicability_proof_present = state.applicability_proof_present
    declared_ids = state.declared_ids
    excluded = state.excluded
    gate = state.gate
    policy = state.policy
    policy_by_status = state.policy_by_status
    policy_contract_invalid = state.policy_contract_invalid
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
    state.applicability_proof_present = applicability_proof_present
    state.consumed = consumed
    state.declared_ids = declared_ids
    state.improved_items = improved_items
    state.improved_valid = improved_valid
    state.policy_contract_invalid = policy_contract_invalid
    state.vector_contract_invalid = vector_contract_invalid


def _validate_metric_applicability_consumption_part_04(state: _MetricState) -> None:
    consumed = state.consumed
    excluded = state.excluded
    findings = state.findings
    gate = state.gate
    improved_items = state.improved_items
    improved_valid = state.improved_valid
    result = state.result
    severity = state.severity
    vector_contract_invalid = state.vector_contract_invalid
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
    state.claim_relevant = claim_relevant
    state.positive_metric_claim = positive_metric_claim
    state.vector_contract_invalid = vector_contract_invalid
    state.vector_ids = vector_ids


def _validate_metric_applicability_consumption_part_05(state: _MetricState) -> None:
    applicability_proof_present = state.applicability_proof_present
    claim_relevant = state.claim_relevant
    declared_ids = state.declared_ids
    evaluation_status = state.evaluation_status
    evaluation_status_invalid = state.evaluation_status_invalid
    findings = state.findings
    gate = state.gate
    improved_items = state.improved_items
    policy_by_status = state.policy_by_status
    policy_contract_invalid = state.policy_contract_invalid
    positive_metric_claim = state.positive_metric_claim
    severity = state.severity
    summary_by_status = state.summary_by_status
    summary_contract_invalid = state.summary_contract_invalid
    vector_contract_invalid = state.vector_contract_invalid
    vector_ids = state.vector_ids
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
    state.summary_divergence = summary_divergence
    state.vector_contract_invalid = vector_contract_invalid


def _validate_metric_applicability_consumption_part_06(state: _MetricState) -> None:
    claim_relevant = state.claim_relevant
    consumed = state.consumed
    evaluation_status = state.evaluation_status
    excluded = state.excluded
    findings = state.findings
    gate = state.gate
    policy_by_status = state.policy_by_status
    severity = state.severity
    summary_divergence = state.summary_divergence
    summary_by_status = state.summary_by_status
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
    state = _MetricState(
        target=target,
        result=result,
        mode=mode,
        findings=findings,
        gate=gate,
        gate_paths=gate_paths,
        gate_values=gate_values,
    )
    _validate_metric_applicability_consumption_part_01(state)
    _validate_metric_applicability_consumption_part_02(state)
    _validate_metric_applicability_consumption_part_03(state)
    _validate_metric_applicability_consumption_part_04(state)
    _validate_metric_applicability_consumption_part_05(state)
    _validate_metric_applicability_consumption_part_06(state)

