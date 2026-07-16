from __future__ import annotations

import math
from typing import Any

from .values import boolish, first_mapping, first_value
from ..output_delta_contract import normalize_quality_delta_policy

def quality_delta_policy_from_value(value: dict[str, Any]) -> dict[str, Any]:
    policy = first_mapping(
        value,
        (
            "quality_delta_policy",
            "output_delta.quality_delta_policy",
            "output_delta_gate.quality_delta_policy",
            "anti_loop_progress_gate.quality_delta_policy",
            "result.quality_delta_policy",
            "result.anti_loop_progress_gate.quality_delta_policy",
        ),
    )
    if policy:
        return normalize_quality_delta_policy(policy)
    keys = first_value(
        value,
        (
            "quality_delta_keys",
            "output_delta.quality_delta_keys",
            "anti_loop_progress_gate.quality_delta_keys",
            "result.quality_delta_keys",
        ),
    )
    aliases = first_mapping(
        value,
        (
            "quality_metric_aliases",
            "output_delta.quality_metric_aliases",
            "anti_loop_progress_gate.quality_metric_aliases",
            "result.quality_metric_aliases",
        ),
    )
    return normalize_quality_delta_policy({"keys": keys or [], "aliases": aliases})

def output_delta_gate(value: dict[str, Any], observed: dict[str, Any] | None = None) -> dict[str, Any]:
    produced = first_value(
        value,
        (
            "produced_domain_delta",
            "output_delta.produced_domain_delta",
            "output_delta_gate.produced_domain_delta",
            "quality_review.produced_domain_delta",
            "result.output_delta.produced_domain_delta",
        ),
    )
    metadata_only = first_value(
        value,
        (
            "metadata_only",
            "output_delta.metadata_only",
            "output_delta_gate.metadata_only",
            "quality_review.metadata_only",
            "result.output_delta.metadata_only",
        ),
    )
    status = first_value(
        value,
        (
            "output_delta_status",
            "output_delta.status",
            "output_delta_gate.output_delta_status",
            "quality_review.output_delta_status",
            "result.output_delta.output_delta_status",
        ),
    )
    effective = first_value(
        value,
        (
            "effective_progress_kind",
            "output_delta.effective_progress_kind",
            "output_delta_gate.effective_progress_kind",
            "result.output_delta.effective_progress_kind",
        ),
    )
    changed = first_value(
        value,
        (
            "changed_vs_previous",
            "output_delta.changed_vs_previous",
            "output_delta_gate.changed_vs_previous",
            "quality_review.changed_vs_previous",
            "result.output_delta.changed_vs_previous",
        ),
    )
    semantic = first_value(
        value,
        (
            "semantic_progress",
            "output_delta.semantic_progress",
            "output_delta_gate.semantic_progress",
            "quality_review.semantic_progress",
            "result.output_delta.semantic_progress",
        ),
    )
    declared_produced = boolish(produced)
    declared_metadata_only = boolish(metadata_only)
    declared_changed = boolish(changed)
    declared_semantic = boolish(semantic)
    has_strict_delta_fields = produced is not None and (changed is not None or semantic is not None)
    observed_class = (observed or {}).get("observed_output_class")
    override_applied = observed_class in {"material_delta", "metadata_only", "terminal_record"}
    if override_applied:
        declared_status = str(status) if status is not None else None
        observed_produced = observed_class == "material_delta"
        produced_value = observed_produced and (not has_strict_delta_fields or (declared_changed and declared_semantic))
        metadata_value = observed_class != "material_delta" or (observed_produced and not produced_value)
        effective_value = "goal_productive" if produced_value else "governance_only"
        status_value = declared_status or f"observed_{observed_class}"
    else:
        produced_value = declared_produced and (not has_strict_delta_fields or (declared_changed and declared_semantic))
        metadata_value = declared_metadata_only or (declared_produced and has_strict_delta_fields and not produced_value)
        effective_value = str(effective).lower() if isinstance(effective, str) else None
        status_value = str(status) if status is not None else None
    return {
        "output_delta_status": status_value,
        "produced_domain_delta": produced_value,
        "changed_vs_previous": declared_changed,
        "semantic_progress": declared_semantic,
        "metadata_only": metadata_value,
        "effective_progress_kind": effective_value,
        "declared_produced_domain_delta": declared_produced,
        "declared_changed_vs_previous": declared_changed,
        "declared_semantic_progress": declared_semantic,
        "declared_metadata_only": declared_metadata_only,
        "observed_output_class": observed_class,
        "observed_output_reason": (observed or {}).get("observed_output_reason"),
        "observed_override_applied": override_applied,
        "observed_output": observed or {},
        "has_output_delta_fields": produced is not None or metadata_only is not None or status is not None or effective is not None,
    }


def _numeric_metric(mapping: dict[str, Any], key: str, aliases: dict[str, Any]) -> tuple[bool, float | None]:
    for candidate in aliases.get(key, [key]):
        if candidate not in mapping:
            continue
        value = mapping.get(candidate)
        if isinstance(value, bool):
            return False, None
        if isinstance(value, (int, float)):
            try:
                numeric = float(value)
            except OverflowError:
                return False, None
            return (True, numeric) if math.isfinite(numeric) else (False, None)
        if isinstance(value, str):
            try:
                numeric = float(value.strip())
                return (True, numeric) if math.isfinite(numeric) else (False, None)
            except ValueError:
                return False, None
        return False, None
    return False, None


def _evaluate_quality_delta(
    quality: dict[str, Any],
    previous: dict[str, Any],
    policy_value: Any,
) -> dict[str, Any]:
    policy = normalize_quality_delta_policy(policy_value)
    keys = policy["keys"]
    current: dict[str, float] = {}
    previous_values: dict[str, float] = {}
    missing: list[str] = []
    previous_binding_count = sum(
        1
        for key in keys
        if any(candidate in previous for candidate in policy["aliases"].get(key, [key]))
    )
    baseline_absent = bool(keys) and previous_binding_count == 0
    for key in keys:
        current_present, current_value = _numeric_metric(quality, key, policy["aliases"])
        previous_present, previous_value = _numeric_metric(previous, key, policy["aliases"])
        if current_present and current_value is not None:
            current[key] = current_value
        if previous_present and previous_value is not None:
            previous_values[key] = previous_value
        elif baseline_absent:
            previous_values[key] = 0.0
        if not current_present or (not previous_present and not baseline_absent):
            missing.append(key)
    invalid = list(policy["invalid_contract_fields"])
    insufficient = sorted(set([*policy["insufficient_evidence_fields"], *missing]))
    evaluated = bool(keys) and not invalid and not insufficient
    improved = [key for key in keys if evaluated and current[key] > previous_values[key]]
    if policy.get("policy_contract_invalid") or invalid:
        evaluation_status = "invalid_contract"
    elif insufficient:
        evaluation_status = "insufficient_evidence"
    elif not policy["supplied"]:
        evaluation_status = "not_evaluated"
    elif not keys and policy["not_applicable_fields"]:
        evaluation_status = "not_applicable"
    else:
        evaluation_status = "evaluated"
    return {
        "gate": "G-COV",
        "quality_delta_pass": bool(improved),
        "improved_fields": improved,
        "current_quality_vector": current,
        "previous_quality_vector": previous_values,
        "quality_delta_policy": policy,
        "quality_delta_policy_supplied": policy["supplied"],
        "not_applicable_fields": policy["not_applicable_fields"],
        "insufficient_evidence_fields": insufficient,
        "invalid_contract_fields": invalid,
        "evaluation_status": evaluation_status,
        "status": "pass" if improved else ("block" if evaluation_status == "evaluated" else evaluation_status),
    }


def coverage_quality_delta_gate(value: dict[str, Any]) -> dict[str, Any]:
    gate = first_mapping(
        value,
        (
            "coverage_quality_delta_gate",
            "quality_delta_gate",
            "output_delta.coverage_quality_delta_gate",
            "output_delta_gate.coverage_quality_delta_gate",
            "anti_loop_progress_gate.coverage_quality_delta_gate",
            "result.coverage_quality_delta_gate",
        ),
    )
    if gate:
        policy_value = gate.get("quality_delta_policy") or quality_delta_policy_from_value(value)
        policy = normalize_quality_delta_policy(policy_value)
        if not policy["supplied"] and not policy.get("policy_contract_invalid"):
            return gate
        quality = first_mapping(gate, ("current_quality_vector", "quality_vector"))
        previous = first_mapping(gate, ("previous_high_water_vector", "previous_quality_vector", "high_water_mark"))
        return {**gate, **_evaluate_quality_delta(quality, previous, policy)}
    quality = first_mapping(value, ("quality_vector", "output_delta.quality_vector", "output_delta_gate.quality_vector"))
    previous = first_mapping(
        value,
        ("previous_quality_vector", "output_delta.previous_quality_vector", "output_delta_gate.previous_quality_vector"),
    )
    if not quality:
        return {}
    policy = quality_delta_policy_from_value(value)
    return _evaluate_quality_delta(quality, previous, policy)
