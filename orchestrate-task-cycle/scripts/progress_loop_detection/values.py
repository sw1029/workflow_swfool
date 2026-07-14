from __future__ import annotations

import datetime as dt
import hashlib
import re
from typing import Any

from .constants import *


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


def normalize_detector_policy(value: Any) -> dict[str, Any]:
    """Normalize adapter-owned detector policy without inventing defaults."""
    if value is None:
        return {
            "supplied": False,
            "evaluation_status": "not_evaluated",
            "findings": [],
            "budgets": {},
            "semantic_axis_patterns": [],
            "root_axis_patterns": [],
            "artifact_policy": {},
            "provider_retry_policy": {},
        }
    if not isinstance(value, dict):
        return {
            "supplied": True,
            "evaluation_status": "invalid_contract",
            "findings": [{"severity": "block", "code": "detector_policy_not_object"}],
            "budgets": {},
            "semantic_axis_patterns": [],
            "root_axis_patterns": [],
            "artifact_policy": {},
            "provider_retry_policy": {},
        }

    findings: list[dict[str, Any]] = []
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

def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def stable_digest(parts: list[str] | tuple[str, ...] | set[str]) -> str:
    digest = hashlib.sha256()
    for part in sorted(str(item) for item in parts if item is not None and str(item) != ""):
        digest.update(part.encode("utf-8", errors="replace"))
        digest.update(b"\0")
    return digest.hexdigest()


def scalar_values(value: Any) -> list[str]:
    if isinstance(value, (str, int, float, bool)):
        text = str(value).strip()
        return [text] if text else []
    if isinstance(value, list):
        items: list[str] = []
        for item in value:
            items.extend(scalar_values(item))
        return items
    if isinstance(value, dict):
        items: list[str] = []
        for item in value.values():
            items.extend(scalar_values(item))
        return items
    return []


def collect_by_key(value: Any, keys: set[str]) -> list[str]:
    collected: list[str] = []

    def collect_matching_keys(item: Any) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                if key.lower() in keys:
                    collected.extend(scalar_values(child))
                collect_matching_keys(child)
        elif isinstance(item, list):
            for child in item:
                collect_matching_keys(child)

    collect_matching_keys(value)
    return sorted(set(collected))


def list_values(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item is not None and str(item) != ""]
    if isinstance(value, str) and value:
        return [value]
    return []


def structured_progress(value: dict[str, Any]) -> str | None:
    for key in ("progress_verdict", "progress", "progress_status"):
        raw = value.get(key)
        if isinstance(raw, dict):
            raw = raw.get("verdict") or raw.get("progress_verdict")
        if isinstance(raw, str) and raw.lower() in {"advanced", "safety_only", "no_progress", "regressed"}:
            return raw.lower()
    return None


def structured_blockers(value: dict[str, Any]) -> list[str]:
    blockers = []
    for key in ("blockers", "remaining_blockers", "blocking_findings"):
        blockers.extend(list_values(value.get(key)))
    return blockers[:5]


def list_field(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item is not None and str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "required", "present", "added"}
    return False


def number_value(value: Any) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def float_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def value_at(value: dict[str, Any], path: str) -> Any:
    current: Any = value
    for key in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def first_value(value: dict[str, Any], paths: tuple[str, ...]) -> Any:
    for path in paths:
        current = value_at(value, path) if "." in path else value.get(path)
        if current is None:
            continue
        if isinstance(current, (list, dict)) and not current:
            continue
        if isinstance(current, str) and not current.strip():
            continue
        return current
    return None


def first_mapping(value: dict[str, Any], paths: tuple[str, ...]) -> dict[str, Any]:
    for path in paths:
        current = value_at(value, path) if "." in path else value.get(path)
        if isinstance(current, dict) and current:
            return current
    return {}


def list_field_paths(value: dict[str, Any], paths: tuple[str, ...]) -> list[str]:
    items: list[str] = []
    for path in paths:
        raw = value_at(value, path) if "." in path else value.get(path)
        items.extend(list_field(raw))
    return sorted(set(items))


def normalize_root_family_key(*values: Any) -> str:
    raw = "|".join(str(value or "") for value in values if value is not None and str(value).strip()).lower()
    if not raw:
        return "unknown"
    raw = VOLATILE_SIGNATURE_RE.sub("-", raw)
    raw = re.sub(r"\bv\d+\b|[-_]v\d+\b", "vnnn", raw)
    raw = SIGNATURE_TOKEN_RE.sub("-", raw).strip("-_.:/|")
    while raw:
        updated = FACET_SUFFIX_RE.sub("", raw).strip("-_.:/|")
        if updated == raw:
            break
        raw = updated
    return f"family:{stable_digest([raw])[:32]}" if raw else "unknown"


def explicit_result_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in PASS_STATUS_VALUES:
            return True
        if lowered in FAIL_STATUS_VALUES:
            return False
    return None


def mapping_result_bool(mapping: dict[str, Any]) -> bool | None:
    for key, value in mapping.items():
        if str(key).strip().lower() in VALIDATOR_RESULT_KEYS:
            result = explicit_result_bool(value)
            if result is not None:
                return result
    return None


def collect_result_bools(value: Any) -> list[bool]:
    results: list[bool] = []

    def collect_result_flags(item: Any) -> None:
        if isinstance(item, dict):
            result = mapping_result_bool(item)
            if result is not None:
                results.append(result)
            for child in item.values():
                collect_result_flags(child)
        elif isinstance(item, list):
            for child in item:
                collect_result_flags(child)

    collect_result_flags(value)
    return results


def first_count_by_key(mapping: dict[str, Any], keys: set[str]) -> int | None:
    for key, value in mapping.items():
        if str(key).strip().lower() not in keys:
            continue
        count = number_value(value)
        if count is not None:
            return count
    return None
