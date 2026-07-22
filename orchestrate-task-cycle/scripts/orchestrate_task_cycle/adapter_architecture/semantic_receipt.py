"""Closed, exact-bound semantic assessment receipt validation."""

from __future__ import annotations

from typing import Any

from .contracts import (
    SEMANTIC_SCHEMA_REVISION,
    contains_forbidden_semantic_key,
    object_sha256,
    require_closed_fields,
    require_sha256,
)


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def _string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ValueError(f"{label} must be a list of non-empty strings")
    if len(set(value)) != len(value):
        raise ValueError(f"{label} must not contain duplicates")
    return list(value)


def _module_node(value: Any, label: str, depth: int = 0) -> None:
    if depth > 24 or not isinstance(value, dict):
        raise ValueError(f"{label} must be a bounded module node")
    require_closed_fields(
        value,
        required={"module_id", "distilled_responsibility", "children"},
        optional={"source_component_ids"},
        label=label,
    )
    _string(value["module_id"], f"{label}.module_id")
    _string(value["distilled_responsibility"], f"{label}.distilled_responsibility")
    children = value["children"]
    if not isinstance(children, list):
        raise ValueError(f"{label}.children must be a list")
    if "source_component_ids" in value:
        _string_list(value["source_component_ids"], f"{label}.source_component_ids")
    for index, child in enumerate(children):
        _module_node(child, f"{label}.children[{index}]", depth + 1)


def _pressure_index(
    structural_pressures: list[dict[str, Any]],
) -> dict[str, tuple[str, frozenset[str]]]:
    if not isinstance(structural_pressures, list):
        raise ValueError("structural pressures must be a list")
    result: dict[str, tuple[str, frozenset[str]]] = {}
    for index, pressure in enumerate(structural_pressures):
        if not isinstance(pressure, dict):
            raise ValueError(f"structural_pressures[{index}] must be an object")
        fact_id = _string(
            pressure.get("fact_id"),
            f"structural_pressures[{index}].fact_id",
        )
        if fact_id in result:
            raise ValueError("structural pressure fact IDs must be unique")
        axis = _string(
            pressure.get("axis"),
            f"structural_pressures[{index}].axis",
        )
        has_subject = "subject" in pressure
        has_subjects = "subjects" in pressure
        if has_subject == has_subjects:
            raise ValueError(
                f"structural_pressures[{index}] must have exactly one subject field"
            )
        if has_subject:
            subjects = {
                _string(
                    pressure["subject"],
                    f"structural_pressures[{index}].subject",
                )
            }
        else:
            subjects = set(
                _string_list(
                    pressure["subjects"],
                    f"structural_pressures[{index}].subjects",
                )
            )
            if not subjects:
                raise ValueError(
                    f"structural_pressures[{index}].subjects must not be empty"
                )
        result[fact_id] = (axis, frozenset(subjects))
    return result


def _validate_assessment(
    value: Any,
    pressure_by_id: dict[str, tuple[str, frozenset[str]]],
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("semantic assessment must be an object")
    require_closed_fields(
        value,
        required={
            "responsibilities",
            "semantic_module_tree",
            "findings",
            "compatibility_risks",
            "design_observations",
        },
        label="semantic assessment",
    )
    if contains_forbidden_semantic_key(value):
        raise ValueError("semantic assessment contains a forbidden authority/body field")
    responsibilities = value["responsibilities"]
    if not isinstance(responsibilities, list):
        raise ValueError("semantic responsibilities must be a list")
    for index, item in enumerate(responsibilities):
        if not isinstance(item, dict):
            raise ValueError("semantic responsibility must be an object")
        require_closed_fields(
            item,
            required={"component_id", "distilled_responsibility"},
            optional={"cohesion_observations", "leakage_observations"},
            label=f"responsibilities[{index}]",
        )
        _string(item["component_id"], "responsibility.component_id")
        _string(item["distilled_responsibility"], "responsibility.distilled_responsibility")
        for key in ("cohesion_observations", "leakage_observations"):
            if key in item:
                _string_list(item[key], f"responsibility.{key}")
    tree = value["semantic_module_tree"]
    if not isinstance(tree, list):
        raise ValueError("semantic_module_tree must be a list")
    for index, node in enumerate(tree):
        _module_node(node, f"semantic_module_tree[{index}]")
    findings = value["findings"]
    if not isinstance(findings, list):
        raise ValueError("semantic findings must be a list")
    finding_ids: set[str] = set()
    for index, item in enumerate(findings):
        if not isinstance(item, dict):
            raise ValueError("semantic finding must be an object")
        require_closed_fields(
            item,
            required={
                "finding_id",
                "axis",
                "subjects",
                "evidence_fact_ids",
                "observation",
                "confidence",
            },
            optional={"recommendation", "pattern_assessment"},
            label=f"findings[{index}]",
        )
        finding_id = _string(item["finding_id"], "finding.finding_id")
        if finding_id in finding_ids:
            raise ValueError("semantic finding IDs must be unique")
        finding_ids.add(finding_id)
        axis = _string(item["axis"], "finding.axis")
        subjects = set(_string_list(item["subjects"], "finding.subjects"))
        evidence = set(
            _string_list(item["evidence_fact_ids"], "finding.evidence_fact_ids")
        )
        if not evidence <= set(pressure_by_id):
            raise ValueError("semantic finding cites an unknown deterministic fact")
        cited_subjects: set[str] = set()
        for fact_id in sorted(evidence):
            fact_axis, fact_subjects = pressure_by_id[fact_id]
            if axis != fact_axis:
                raise ValueError(
                    "semantic finding axis does not match cited deterministic fact"
                )
            cited_subjects.update(fact_subjects)
        if evidence and subjects != cited_subjects:
            raise ValueError(
                "semantic finding subjects do not match cited deterministic facts"
            )
        _string(item["observation"], "finding.observation")
        confidence = item["confidence"]
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
            raise ValueError("semantic finding confidence must be between zero and one")
        if "recommendation" in item:
            _string(item["recommendation"], "finding.recommendation")
        if "pattern_assessment" in item:
            pattern = item["pattern_assessment"]
            if not isinstance(pattern, dict):
                raise ValueError("pattern_assessment must be an object")
            require_closed_fields(
                pattern,
                required={"pattern", "problem_force", "benefit", "risk", "simpler_alternative"},
                label="pattern_assessment",
            )
            for key in pattern:
                _string(pattern[key], f"pattern_assessment.{key}")
    for collection_name in ("compatibility_risks", "design_observations"):
        collection = value[collection_name]
        if not isinstance(collection, list):
            raise ValueError(f"{collection_name} must be a list")
        for item in collection:
            _string(item, collection_name)
    return dict(value)


def validate_semantic_receipt(
    receipt: dict[str, Any],
    *,
    adapter_id: str,
    adapter_revision_sha256: str,
    convention_sha256: str,
    fact_packet_sha256: str,
    structural_pressures: list[dict[str, Any]],
) -> dict[str, Any]:
    if not isinstance(receipt, dict):
        raise ValueError("semantic receipt must be an object")
    require_closed_fields(
        receipt,
        required={
            "schema_version",
            "artifact_kind",
            "semantic_schema_revision",
            "adapter_id",
            "adapter_revision_sha256",
            "convention_sha256",
            "fact_packet_sha256",
            "assessment",
            "receipt_sha256",
        },
        label="semantic receipt",
    )
    if (
        receipt["schema_version"] != 1
        or receipt["artifact_kind"] != "adapter_architecture_semantic_receipt"
        or receipt["semantic_schema_revision"] != SEMANTIC_SCHEMA_REVISION
    ):
        raise ValueError("semantic receipt schema is unsupported")
    expected = {
        "adapter_id": adapter_id,
        "adapter_revision_sha256": adapter_revision_sha256,
        "convention_sha256": convention_sha256,
        "fact_packet_sha256": fact_packet_sha256,
    }
    for field, value in expected.items():
        if receipt.get(field) != value:
            raise ValueError(f"semantic receipt {field} binding mismatch")
    for field in ("adapter_revision_sha256", "convention_sha256", "fact_packet_sha256"):
        require_sha256(receipt[field], field)
    body = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    if require_sha256(receipt["receipt_sha256"], "receipt_sha256") != object_sha256(body):
        raise ValueError("semantic receipt integrity mismatch")
    assessment = _validate_assessment(
        receipt["assessment"], _pressure_index(structural_pressures)
    )
    return {**receipt, "assessment": assessment}


__all__ = ("validate_semantic_receipt",)
