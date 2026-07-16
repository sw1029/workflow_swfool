"""Adapter-owned progress detector policy normalization."""

from __future__ import annotations

import re
from typing import Any

DETECTOR_BUDGET_KEYS = {
    "evidence_scope_limit",
    "recurrence",
    "goal_productive_stale",
    "root_axis_stall",
    "feature_symbol_stall",
    "terminal_quiescence",
    "terminal_escalation",
    "detection_only_streak",
    "consolidation_streak",
    "command_surface_count",
    "metadata_only_window",
}


def _string_set(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {str(item).strip() for item in value if isinstance(item, str) and item.strip()}


def _positive_policy_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str) and value.strip().isdigit() and int(value.strip()) > 0:
        return int(value.strip())
    return None


def _pattern_policy(value: Any, field: str, findings: list[dict[str, Any]]) -> list[tuple[str, str]]:
    if value is None:
        return []
    if not isinstance(value, list):
        findings.append({"severity": "block", "code": "policy_pattern_catalog_not_list", "field": field})
        return []
    normalized: list[tuple[str, str]] = []
    for index, item in enumerate(value):
        axis_id: Any = None
        pattern: Any = None
        if isinstance(item, dict):
            axis_id = item.get("axis_id") or item.get("id")
            pattern = item.get("pattern")
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            axis_id, pattern = item
        if not isinstance(axis_id, str) or not axis_id.strip() or not isinstance(pattern, str) or not pattern:
            findings.append(
                {
                    "severity": "block",
                    "code": "policy_pattern_entry_invalid",
                    "field": field,
                    "index": index,
                }
            )
            continue
        try:
            re.compile(pattern, re.IGNORECASE)
        except re.error as exc:
            findings.append(
                {
                    "severity": "block",
                    "code": "policy_pattern_invalid_regex",
                    "field": field,
                    "index": index,
                    "error": str(exc),
                }
            )
            continue
        normalized.append((axis_id.strip(), pattern))
    return normalized


def _base_detector_policy(
    *, supplied: bool, status: str, findings: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "supplied": supplied,
        "evaluation_status": status,
        "findings": findings,
        "budgets": {},
        "semantic_axis_patterns": [],
        "root_axis_patterns": [],
        "artifact_policy": {},
        "provider_retry_policy": {},
    }


def _normalize_budgets(
    value: dict[str, Any], findings: list[dict[str, Any]]
) -> dict[str, int]:
    raw_budgets = value.get("budgets")
    if raw_budgets is None:
        raw_budgets = {}
    if not isinstance(raw_budgets, dict):
        findings.append({"severity": "block", "code": "detector_policy_budgets_not_object"})
        raw_budgets = {}
    budgets: dict[str, int] = {}
    for key in sorted(DETECTOR_BUDGET_KEYS):
        if key not in raw_budgets:
            continue
        normalized = _positive_policy_int(raw_budgets.get(key))
        if normalized is None:
            findings.append({"severity": "block", "code": "detector_policy_budget_invalid", "budget": key})
        else:
            budgets[key] = normalized
    return budgets


def _normalize_artifact_policy(
    value: dict[str, Any], findings: list[dict[str, Any]]
) -> dict[str, Any]:
    artifact = value.get("artifact_policy")
    if artifact is None:
        artifact = {}
    if not isinstance(artifact, dict):
        findings.append({"severity": "block", "code": "artifact_policy_not_object"})
        artifact = {}
    normalized_artifact: dict[str, Any] = {
        "path_fields": sorted(_string_set(artifact.get("path_fields"))),
        "input_path_fields": sorted(_string_set(artifact.get("input_path_fields"))),
        "input_manifest_names": sorted(_string_set(artifact.get("input_manifest_names"))),
        "target_unit_keys": sorted(_string_set(artifact.get("target_unit_keys"))),
        "inline_input_fields": sorted(_string_set(artifact.get("inline_input_fields"))),
        "file_kinds": [],
        "count_fields": {},
    }
    raw_file_kinds = artifact.get("file_kinds")
    if raw_file_kinds is not None and not isinstance(raw_file_kinds, list):
        findings.append({"severity": "block", "code": "artifact_file_kinds_not_list"})
    elif isinstance(raw_file_kinds, list):
        for index, item in enumerate(raw_file_kinds):
            if not isinstance(item, dict):
                findings.append({"severity": "block", "code": "artifact_file_kind_invalid", "index": index})
                continue
            file_name = item.get("file_name")
            kind_id = item.get("kind_id")
            identity_fields = sorted(_string_set(item.get("identity_fields")))
            if (
                not isinstance(file_name, str)
                or not file_name.strip()
                or "/" in file_name
                or not isinstance(kind_id, str)
                or not kind_id.strip()
                or not identity_fields
            ):
                findings.append({"severity": "block", "code": "artifact_file_kind_invalid", "index": index})
                continue
            normalized_artifact["file_kinds"].append(
                {
                    "file_name": file_name.strip(),
                    "kind_id": kind_id.strip(),
                    "identity_fields": identity_fields,
                }
            )
    raw_counts = artifact.get("count_fields")
    if raw_counts is not None and not isinstance(raw_counts, dict):
        findings.append({"severity": "block", "code": "artifact_count_fields_not_object"})
    elif isinstance(raw_counts, dict):
        for metric_id, aliases in raw_counts.items():
            normalized_aliases = sorted(_string_set(aliases))
            if not isinstance(metric_id, str) or not metric_id.strip() or not normalized_aliases:
                findings.append({"severity": "block", "code": "artifact_count_field_invalid"})
                continue
            normalized_artifact["count_fields"][metric_id.strip()] = normalized_aliases
    return normalized_artifact


def _normalize_retry_policy(
    value: dict[str, Any], findings: list[dict[str, Any]]
) -> dict[str, Any]:
    retry_supplied = value.get("provider_retry_policy") is not None
    retry = value.get("provider_retry_policy")
    if retry is None:
        retry = {}
    if not isinstance(retry, dict):
        findings.append({"severity": "block", "code": "provider_retry_policy_not_object"})
        retry = {}
    mitigation_requirements: dict[str, set[str]] = {}
    raw_requirements = retry.get("mitigation_requirements")
    if raw_requirements is not None and not isinstance(raw_requirements, dict):
        findings.append({"severity": "block", "code": "mitigation_requirements_not_object"})
    elif isinstance(raw_requirements, dict):
        for failure_class, required in raw_requirements.items():
            names = _string_set(required)
            if isinstance(failure_class, str) and failure_class.strip() and names:
                mitigation_requirements[failure_class.strip()] = names
            else:
                findings.append({"severity": "block", "code": "mitigation_requirement_invalid"})
    normalized_retry = {
        "supplied": retry_supplied,
        "transient_failure_classes": _string_set(retry.get("transient_failure_classes")),
        "permanent_failure_classes": _string_set(retry.get("permanent_failure_classes")),
        "mitigation_requirements": mitigation_requirements,
        "retry_count_threshold": _positive_policy_int(retry.get("retry_count_threshold")),
    }
    if retry.get("retry_count_threshold") is not None and normalized_retry["retry_count_threshold"] is None:
        findings.append({"severity": "block", "code": "retry_count_threshold_invalid"})
    return normalized_retry


def _normalize_regex_fields(
    value: dict[str, Any], findings: list[dict[str, Any]]
) -> dict[str, str]:
    regex_fields: dict[str, str] = {}
    for field in ("command_surface_pattern", "detection_terms_pattern", "correction_terms_pattern"):
        raw = value.get(field)
        if raw is None:
            continue
        if not isinstance(raw, str) or not raw:
            findings.append({"severity": "block", "code": "detector_policy_regex_invalid", "field": field})
            continue
        try:
            re.compile(raw, re.IGNORECASE)
        except re.error as exc:
            findings.append(
                {
                    "severity": "block",
                    "code": "detector_policy_regex_invalid",
                    "field": field,
                    "error": str(exc),
                }
            )
            continue
        regex_fields[field] = raw
    return regex_fields


def normalize_detector_policy(value: Any) -> dict[str, Any]:
    """Normalize adapter-owned detector policy without inventing defaults."""
    if value is None:
        return _base_detector_policy(
            supplied=False,
            status="not_evaluated",
            findings=[],
        )
    if not isinstance(value, dict):
        return _base_detector_policy(
            supplied=True,
            status="invalid_contract",
            findings=[{"severity": "block", "code": "detector_policy_not_object"}],
        )

    findings: list[dict[str, Any]] = []
    budgets = _normalize_budgets(value, findings)
    normalized_artifact = _normalize_artifact_policy(value, findings)
    normalized_retry = _normalize_retry_policy(value, findings)
    regex_fields = _normalize_regex_fields(value, findings)
    semantic_patterns = _pattern_policy(
        value.get("semantic_axis_patterns"),
        "semantic_axis_patterns",
        findings,
    )
    root_patterns = _pattern_policy(
        value.get("root_axis_patterns"),
        "root_axis_patterns",
        findings,
    )
    return {
        "supplied": True,
        "evaluation_status": "invalid_contract" if findings else "evaluated",
        "findings": findings,
        "budgets": budgets,
        "semantic_axis_patterns": semantic_patterns,
        "root_axis_patterns": root_patterns,
        "artifact_policy": normalized_artifact,
        "provider_retry_policy": normalized_retry,
        **regex_fields,
    }
