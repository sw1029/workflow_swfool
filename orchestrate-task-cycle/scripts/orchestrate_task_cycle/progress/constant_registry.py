from __future__ import annotations

import json
import re
from importlib.resources import files
from typing import Any

from .constants import (
    BLOCKER_RE,
    COMMAND_SURFACE_RE,
    CONSOLIDATION_STREAK_CAP,
    CORRECTION_TERMS_RE,
    DETECTION_ONLY_STREAK_CAP,
    DETECTION_TERMS_RE,
    DISPOSITION_UNIVERSE,
    FACET_SUFFIX_RE,
    FAILURE_CLASS_RE,
    FAIL_STATUS_VALUES,
    INPUT_KIND_RE,
    INPUT_MANIFEST_NAMES,
    INPUT_PATH_FIELD_NAMES,
    INSPECTED_COUNT_KEYS,
    ISSUE_RE,
    MITIGATION_REQUIREMENTS,
    PASS_STATUS_VALUES,
    PATH_FIELD_NAMES,
    PERMANENT_PROVIDER_FAILURE_CLASSES,
    POPULATION_COUNT_KEYS,
    PROGRESS_RE,
    PROVIDER_REQUEST_COUNT_RE,
    QUALITY_DELTA_KEYS,
    REGISTRY_REL_PATH,
    ROOT_AXIS_PATTERNS,
    SAFETY_VALVES,
    SEMANTIC_AXIS_PATTERNS,
    SIGNATURE_TOKEN_RE,
    TARGET_UNIT_KEYS,
    TERMINAL_ESCALATION_STREAK_DEFAULT,
    TERMINAL_QUIESCENCE_STREAK_DEFAULT,
    TRANSIENT_PROVIDER_FAILURE_CLASSES,
    VALIDATOR_CHILD_KEYS,
    VALIDATOR_RESULT_KEYS,
    VOLATILE_SIGNATURE_RE,
)


REGISTRY_RESOURCE = "constant_registry.json"
REGEX_FLAG_NAMES = ("ASCII", "IGNORECASE", "LOCALE", "MULTILINE", "DOTALL", "VERBOSE")
REGEX_FLAGS = {
    "ASCII": re.ASCII,
    "IGNORECASE": re.IGNORECASE,
    "LOCALE": re.LOCALE,
    "MULTILINE": re.MULTILINE,
    "DOTALL": re.DOTALL,
    "VERBOSE": re.VERBOSE,
}
CONSTANTS_BY_NAME = {
    "BLOCKER_RE": BLOCKER_RE,
    "COMMAND_SURFACE_RE": COMMAND_SURFACE_RE,
    "CONSOLIDATION_STREAK_CAP": CONSOLIDATION_STREAK_CAP,
    "CORRECTION_TERMS_RE": CORRECTION_TERMS_RE,
    "DETECTION_ONLY_STREAK_CAP": DETECTION_ONLY_STREAK_CAP,
    "DETECTION_TERMS_RE": DETECTION_TERMS_RE,
    "DISPOSITION_UNIVERSE": DISPOSITION_UNIVERSE,
    "FACET_SUFFIX_RE": FACET_SUFFIX_RE,
    "FAILURE_CLASS_RE": FAILURE_CLASS_RE,
    "FAIL_STATUS_VALUES": FAIL_STATUS_VALUES,
    "INPUT_KIND_RE": INPUT_KIND_RE,
    "INPUT_MANIFEST_NAMES": INPUT_MANIFEST_NAMES,
    "INPUT_PATH_FIELD_NAMES": INPUT_PATH_FIELD_NAMES,
    "INSPECTED_COUNT_KEYS": INSPECTED_COUNT_KEYS,
    "ISSUE_RE": ISSUE_RE,
    "MITIGATION_REQUIREMENTS": MITIGATION_REQUIREMENTS,
    "PASS_STATUS_VALUES": PASS_STATUS_VALUES,
    "PATH_FIELD_NAMES": PATH_FIELD_NAMES,
    "PERMANENT_PROVIDER_FAILURE_CLASSES": PERMANENT_PROVIDER_FAILURE_CLASSES,
    "POPULATION_COUNT_KEYS": POPULATION_COUNT_KEYS,
    "PROGRESS_RE": PROGRESS_RE,
    "PROVIDER_REQUEST_COUNT_RE": PROVIDER_REQUEST_COUNT_RE,
    "QUALITY_DELTA_KEYS": QUALITY_DELTA_KEYS,
    "REGISTRY_REL_PATH": REGISTRY_REL_PATH,
    "ROOT_AXIS_PATTERNS": ROOT_AXIS_PATTERNS,
    "SAFETY_VALVES": SAFETY_VALVES,
    "SEMANTIC_AXIS_PATTERNS": SEMANTIC_AXIS_PATTERNS,
    "SIGNATURE_TOKEN_RE": SIGNATURE_TOKEN_RE,
    "TARGET_UNIT_KEYS": TARGET_UNIT_KEYS,
    "TERMINAL_ESCALATION_STREAK_DEFAULT": TERMINAL_ESCALATION_STREAK_DEFAULT,
    "TERMINAL_QUIESCENCE_STREAK_DEFAULT": TERMINAL_QUIESCENCE_STREAK_DEFAULT,
    "TRANSIENT_PROVIDER_FAILURE_CLASSES": TRANSIENT_PROVIDER_FAILURE_CLASSES,
    "VALIDATOR_CHILD_KEYS": VALIDATOR_CHILD_KEYS,
    "VALIDATOR_RESULT_KEYS": VALIDATOR_RESULT_KEYS,
    "VOLATILE_SIGNATURE_RE": VOLATILE_SIGNATURE_RE,
}


def load_constant_registry() -> dict[str, Any]:
    registry_path = files(__package__).joinpath(REGISTRY_RESOURCE)
    return json.loads(registry_path.read_text(encoding="utf-8"))


def public_constant_names() -> list[str]:
    return sorted(CONSTANTS_BY_NAME)


def constant_snapshot(value: Any) -> Any:
    if isinstance(value, re.Pattern):
        return {
            "kind": "regex",
            "pattern": value.pattern,
            "flags": regex_flag_names(value.flags),
        }
    if isinstance(value, set):
        return {
            "kind": "set",
            "items": sorted(constant_snapshot(item) for item in value),
        }
    if isinstance(value, tuple):
        return {
            "kind": "tuple",
            "items": [constant_snapshot(item) for item in value],
        }
    if isinstance(value, list):
        return {
            "kind": "list",
            "items": [constant_snapshot(item) for item in value],
        }
    if isinstance(value, dict):
        return {
            "kind": "dict",
            "items": {str(key): constant_snapshot(value[key]) for key in sorted(value)},
        }
    return value


def regex_flag_names(flags: int) -> list[str]:
    names: list[str] = []
    for name in REGEX_FLAG_NAMES:
        flag = REGEX_FLAGS[name]
        if flags & flag:
            names.append(name)
    return names


def validate_constant_registry(registry: dict[str, Any] | None = None) -> dict[str, Any]:
    registry = registry or load_constant_registry()
    findings: list[dict[str, Any]] = []
    entries = registry.get("entries")
    if not isinstance(entries, list):
        return {
            "status": "block",
            "registry_resource": REGISTRY_RESOURCE,
            "findings": [{"severity": "block", "code": "registry_entries_not_list"}],
        }

    entry_by_name = {str(entry.get("name")): entry for entry in entries if isinstance(entry, dict) and entry.get("name")}
    runtime_names = set(public_constant_names())
    registry_names = set(entry_by_name)
    if registry.get("coverage") == "all_public_uppercase_constants":
        for name in sorted(runtime_names - registry_names):
            findings.append({"severity": "block", "code": "constant_missing_from_registry", "name": name})
        for name in sorted(registry_names - runtime_names):
            findings.append({"severity": "block", "code": "registry_entry_without_runtime_constant", "name": name})

    for name, entry in sorted(entry_by_name.items()):
        if name not in CONSTANTS_BY_NAME:
            continue
        expected = entry.get("expected")
        actual = constant_snapshot(CONSTANTS_BY_NAME[name])
        if actual != expected:
            findings.append(
                {
                    "severity": "block",
                    "code": "constant_registry_value_mismatch",
                    "name": name,
                    "expected": expected,
                    "actual": actual,
                }
            )
        if isinstance(expected, dict) and expected.get("kind") == "regex":
            try:
                re.compile(str(expected.get("pattern") or ""))
            except re.error as exc:
                findings.append(
                    {
                        "severity": "block",
                        "code": "constant_registry_regex_invalid",
                        "name": name,
                        "error": str(exc),
                    }
                )

    return {
        "status": "block" if any(item.get("severity") == "block" for item in findings) else "ok",
        "schema_version": registry.get("schema_version"),
        "registry_kind": registry.get("registry_kind"),
        "registry_resource": REGISTRY_RESOURCE,
        "coverage": registry.get("coverage"),
        "runtime_constant_count": len(runtime_names),
        "registry_entry_count": len(registry_names),
        "findings": findings,
    }
