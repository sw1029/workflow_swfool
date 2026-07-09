from __future__ import annotations

import json
from typing import Any

from .accessors import boolish, first_present


REPORT_CONTEXT_KEYS = {
    "report",
    "quality_report",
    "validation_report",
    "result_report",
    "report_payload",
    "report_artifact",
    "artifact_report",
    "summary_report",
}

REPORT_DUPLICATE_KEY_EXCLUSIONS = {
    "id",
    "path",
    "status",
    "step",
    "target",
    "mode",
    "severity",
    "code",
    "message",
    "reason",
    "created_at",
    "updated_at",
    "timestamp",
    "evidence_path",
    "evidence_paths",
}


def report_integrity_required(data: dict[str, Any]) -> bool:
    return boolish(
        first_present(
            data,
            [
                "report_key_integrity_required",
                "report_key_integrity_gate.required",
                "report_key_integrity_gate.scan_duplicate_terminal_keys",
                "result.report_key_integrity_gate.required",
            ],
        )
    )


def is_report_context_key(key: str) -> bool:
    normalized = key.strip().lower()
    return normalized in REPORT_CONTEXT_KEYS or normalized.endswith("_report")


def collect_report_roots(value: Any, path: str = "$", key: str = "") -> list[tuple[str, Any]]:
    roots: list[tuple[str, Any]] = []
    if isinstance(value, dict):
        if key and is_report_context_key(key):
            roots.append((path, value))
            return roots
        for child_key, child in value.items():
            child_path = f"{path}.{child_key}"
            roots.extend(collect_report_roots(child, child_path, str(child_key)))
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            roots.extend(collect_report_roots(child, f"{path}[{idx}]", key))
    return roots


def collect_terminal_key_values(value: Any, path: str = "$") -> dict[str, list[tuple[str, str, Any]]]:
    values: dict[str, list[tuple[str, str, Any]]] = {}
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if isinstance(child, (dict, list)):
                child_values = collect_terminal_key_values(child, child_path)
                for child_key, child_entries in child_values.items():
                    values.setdefault(child_key, []).extend(child_entries)
                continue
            key_text = str(key)
            if key_text.lower() in REPORT_DUPLICATE_KEY_EXCLUSIONS:
                continue
            try:
                encoded = json.dumps(child, sort_keys=True, ensure_ascii=False)
            except TypeError:
                encoded = repr(child)
            values.setdefault(key_text, []).append((child_path, encoded, child))
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            child_values = collect_terminal_key_values(child, f"{path}[{idx}]")
            for child_key, child_entries in child_values.items():
                values.setdefault(child_key, []).extend(child_entries)
    return values


def report_key_divergences(data: dict[str, Any]) -> list[dict[str, Any]]:
    roots = collect_report_roots(data)
    if report_integrity_required(data) and not roots:
        roots = [("$", data)]
    divergences: list[dict[str, Any]] = []
    for root_path, root in roots:
        terminal_values = collect_terminal_key_values(root, root_path)
        for key, entries in terminal_values.items():
            unique_values = {encoded for _, encoded, _ in entries}
            if len(entries) < 2 or len(unique_values) <= 1:
                continue
            divergences.append(
                {
                    "root_path": root_path,
                    "terminal_key": key,
                    "paths": [path for path, _, _ in entries],
                    "values": [value for _, _, value in entries],
                }
            )
    return divergences


def report_key_duplicate_matches(data: dict[str, Any]) -> list[dict[str, Any]]:
    roots = collect_report_roots(data)
    if report_integrity_required(data) and not roots:
        roots = [("$", data)]
    duplicates: list[dict[str, Any]] = []
    for root_path, root in roots:
        terminal_values = collect_terminal_key_values(root, root_path)
        for key, entries in terminal_values.items():
            unique_values = {encoded for _, encoded, _ in entries}
            if len(entries) < 2 or len(unique_values) != 1:
                continue
            duplicates.append(
                {
                    "root_path": root_path,
                    "terminal_key": key,
                    "paths": [path for path, _, _ in entries],
                    "value": entries[0][2],
                    "duplicate_count": len(entries),
                }
            )
    return duplicates


def scalar_leaves(value: Any, prefix: str = "") -> dict[str, Any]:
    leaves: dict[str, Any] = {}
    if isinstance(value, dict):
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            leaves.update(scalar_leaves(child, child_prefix))
    elif not isinstance(value, list) and prefix:
        leaves[prefix] = value
        leaves.setdefault(prefix.rsplit(".", 1)[-1], value)
    return leaves


def actual_report_body_divergences(data: dict[str, Any]) -> list[dict[str, Any]]:
    actual_roots: list[tuple[str, dict[str, Any]]] = []
    report_roots: list[tuple[str, dict[str, Any]]] = []
    for key, value in data.items():
        if not isinstance(value, dict):
            continue
        normalized = str(key).strip().lower()
        if normalized in {"actual_artifact", "current_artifact", "artifact_body", "body_projection"}:
            actual_roots.append((str(key), value))
        elif normalized.endswith("report") or normalized.endswith("manifest") or normalized in {"validation_report", "result_report"}:
            report_roots.append((str(key), value))
    divergences: list[dict[str, Any]] = []
    for actual_name, actual_value in actual_roots:
        actual_fields = scalar_leaves(actual_value)
        for report_name, report_value in report_roots:
            report_fields = scalar_leaves(report_value)
            for field in sorted(set(actual_fields) & set(report_fields)):
                if "." not in field and any(key.endswith(f".{field}") for key in actual_fields):
                    continue
                if actual_fields[field] != report_fields[field]:
                    divergences.append(
                        {
                            "field": field,
                            "actual_source": actual_name,
                            "report_source": report_name,
                            "actual_value": actual_fields[field],
                            "report_value": report_fields[field],
                        }
                    )
    return divergences

