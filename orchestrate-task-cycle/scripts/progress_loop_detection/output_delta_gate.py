from __future__ import annotations

from pathlib import Path
from typing import Any

from .constants import *
from .values import *
from .io_utils import *
from .provider import *


def _quality_policy_items(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def normalize_quality_delta_policy(value: Any) -> dict[str, Any]:
    if isinstance(value, (list, tuple, set)):
        raw_keys = value
        raw_aliases: Any = {}
    elif isinstance(value, dict):
        raw_keys = (
            value.get("keys")
            or value.get("quality_delta_keys")
            or value.get("metric_keys")
            or value.get("axes")
            or []
        )
        raw_aliases = (
            value.get("aliases")
            or value.get("quality_metric_aliases")
            or value.get("metric_aliases")
            or {}
        )
    else:
        raw_keys = []
        raw_aliases = {}
    keys = list(dict.fromkeys(_quality_policy_items(raw_keys)))
    aliases: dict[str, list[str]] = {}
    for key in keys:
        supplied = _quality_policy_items(raw_aliases.get(key)) if isinstance(raw_aliases, dict) else []
        aliases[key] = list(dict.fromkeys([key, *supplied]))
    return {"keys": keys, "aliases": aliases, "supplied": bool(keys)}


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
    override_applied = observed_class in {"node_edge_delta", "metadata_only", "terminal_record"}
    if override_applied:
        declared_status = str(status) if status is not None else None
        observed_produced = observed_class == "node_edge_delta"
        produced_value = observed_produced and (not has_strict_delta_fields or (declared_changed and declared_semantic))
        metadata_value = observed_class != "node_edge_delta" or (observed_produced and not produced_value)
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
        return gate
    quality = first_mapping(value, ("quality_vector", "output_delta.quality_vector", "output_delta_gate.quality_vector"))
    previous = first_mapping(
        value,
        ("previous_quality_vector", "output_delta.previous_quality_vector", "output_delta_gate.previous_quality_vector"),
    )
    if not quality:
        return {}
    policy = quality_delta_policy_from_value(value)

    def metric(mapping: dict[str, Any], key: str) -> float:
        for candidate in policy["aliases"].get(key, [key]):
            if candidate in mapping:
                return float_number(mapping.get(candidate)) or 0.0
        return 0

    keys = policy["keys"]
    current = {key: metric(quality, key) for key in keys}
    previous_values = {key: metric(previous, key) for key in keys}
    improved = [key for key in keys if current[key] > previous_values[key]]
    return {
        "gate": "G-COV",
        "quality_delta_pass": bool(improved),
        "improved_fields": improved,
        "current_quality_vector": current,
        "previous_quality_vector": previous_values,
        "quality_delta_policy": policy,
        "quality_delta_policy_supplied": policy["supplied"],
        "evaluation_status": "evaluated" if keys else "not_evaluated",
        "status": "pass" if improved else ("block" if keys else "not_evaluated"),
    }
