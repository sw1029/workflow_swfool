from __future__ import annotations

from typing import Any
from pathlib import Path
import hashlib
import re
from .common import (
    CORRECTION_TERMS_RE,
    DETECTION_TERMS_RE,
    FAIL_STATUS_VALUES,
    INSPECTED_COUNT_KEYS,
    PASS_STATUS_VALUES,
    POPULATION_COUNT_KEYS,
    VALIDATOR_CHILD_KEYS,
    VALIDATOR_RESULT_KEYS,
)
from . import domain as _domain
from . import families as _families
from . import measurement as _measurement
from . import values as _values


def normalize_ladder_rung(value: Any) -> str | None:
    text = str(value or "").strip().lower().replace("-", "_")
    if not text:
        return None
    return re.sub(r"[^a-z0-9_.:]+", "_", text).strip("_")[:160] or None

def infer_ladder_rung(*values: Any) -> str | None:
    # Generic workflow code cannot infer a domain ladder from free text.
    return None

def first_named_value(values: list[Any], keys: set[str]) -> str | None:
    for value in values:
        collected = _domain.collect_values_by_key(value, keys)
        if collected:
            return collected[0][:240]
    return None

def blocker_mutation_kind(
    curr_signature: str,
    curr_rung: str | None,
    curr_root_family: str,
    prev: dict[str, Any] | None,
) -> str:
    if not prev:
        return "initial"
    prev_signature = str(prev.get("blocker_signature") or prev.get("semantic_signature") or "").strip()
    prev_root = _measurement.row_root_family(prev)
    curr_root = curr_root_family or _families.normalize_root_family_key(curr_signature)
    if curr_root and prev_root and curr_root == prev_root:
        if curr_signature and prev_signature and curr_signature == prev_signature:
            return "repeat"
        return "facet_rename"
    if curr_root and prev_root and curr_root != prev_root:
        return "forward_mutation"
    if curr_signature and prev_signature and curr_signature == prev_signature:
        return "repeat"
    return "lateral"

def forward_mutation_streak(rows: list[dict[str, Any]], family_key: str) -> int:
    streak = 0
    for row in reversed(_domain.recent_family_rows(rows, family_key)):
        if row.get("blocker_mutation_kind") == "forward_mutation":
            streak += 1
            continue
        break
    return streak

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
        normalized = str(key).strip().lower()
        if normalized in VALIDATOR_RESULT_KEYS:
            result = explicit_result_bool(value)
            if result is not None:
                return result
    return None

def collect_result_bools(value: Any) -> list[bool]:
    results: list[bool] = []

    def walk(item: Any) -> None:
        if isinstance(item, dict):
            result = mapping_result_bool(item)
            if result is not None:
                results.append(result)
            for child in item.values():
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    walk(value)
    return results

def first_int_by_key(mapping: dict[str, Any], keys: set[str]) -> int | None:
    for key, value in mapping.items():
        if str(key).strip().lower() not in keys:
            continue
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
    return None

def validator_integrity_gate(*values: Any) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []

    def inspect(item: Any, path: str = "$") -> None:
        if isinstance(item, dict):
            top_result = mapping_result_bool(item)
            child_results: list[bool] = []
            for key in VALIDATOR_CHILD_KEYS:
                child = item.get(key)
                if isinstance(child, (dict, list)):
                    child_results.extend(collect_result_bools(child))
            if top_result is True and any(result is False for result in child_results):
                findings.append(
                    {
                        "kind": "integrity_mismatch",
                        "path": path,
                        "top_level_result": True,
                        "embedded_result_count": len(child_results),
                        "embedded_failed_count": sum(1 for result in child_results if result is False),
                    }
                )
            declared = first_int_by_key(item, POPULATION_COUNT_KEYS)
            inspected = first_int_by_key(item, INSPECTED_COUNT_KEYS)
            if declared is not None and inspected is not None and declared > 0 and inspected < declared:
                findings.append(
                    {
                        "kind": "under_detection",
                        "path": path,
                        "declared_population_count": declared,
                        "inspected_count": inspected,
                    }
                )
            for key, child in item.items():
                inspect(child, f"{path}.{key}")
        elif isinstance(item, list):
            for index, child in enumerate(item):
                inspect(child, f"{path}[{index}]")

    for value in values:
        inspect(value)
    mismatch = any(item["kind"] == "integrity_mismatch" for item in findings)
    under_detection = any(item["kind"] == "under_detection" for item in findings)
    blocked = mismatch or under_detection
    return {
        "gate": "G-INTEGRITY",
        "validator_integrity": "mismatch" if mismatch else "ok",
        "validator_coverage": "under_detection" if under_detection else "ok",
        "status": "block" if blocked else "ok",
        "hard_stop_required": blocked,
        "constrains_disposition": blocked,
        "allowed_dispositions": ["goal_productive", "terminal_blocked", "user_escalation"],
        "findings": findings[:20],
    }

def classify_task_correction(
    *,
    current_check_ids: set[str],
    current_frontiers: set[str],
    provider_request_count: int,
    changed_vs_previous: bool,
    semantic_progress: bool,
    values: list[Any],
) -> str:
    text = " ".join(_domain.scalar_strings(values)).lower()
    detection = bool(current_check_ids or current_frontiers or DETECTION_TERMS_RE.search(text))
    correction = bool(
        provider_request_count > 0
        or changed_vs_previous
        or semantic_progress
        or CORRECTION_TERMS_RE.search(text)
    )
    if detection and correction:
        return "mixed"
    if detection:
        return "detection"
    if correction:
        return "correction"
    return "unknown"

def detection_only_streak(rows: list[dict[str, Any]], root_family_key: str, current_detection_only: bool) -> int:
    streak = 1 if current_detection_only else 0
    if not current_detection_only:
        return 0
    for row in reversed(rows):
        if _measurement.row_root_family(row) != root_family_key:
            continue
        if _values.bool_value(row.get("detection_only")) and not _values.bool_value(row.get("semantic_progress")):
            streak += 1
            continue
        break
    return streak

def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None
