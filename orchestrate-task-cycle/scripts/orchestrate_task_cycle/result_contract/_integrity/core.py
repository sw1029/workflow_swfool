from __future__ import annotations

import hashlib
import json
from typing import Any

from ..accessors import boolish, first_present


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

PROJECTION_FINGERPRINT_KEYS = {
    "body_projection_fingerprint",
    "canonical_body_projection_fingerprint",
    "projection_fingerprint",
}
ACTUAL_CONTEXT_KEYS = {
    "actual_artifact",
    "current_artifact",
    "artifact_body",
    "body_projection",
}
IDENTITY_SCALAR_MAX_LENGTH = 256


def report_integrity_required(data: dict[str, Any]) -> bool:
    return any(
        boolish(first_present(data, [path]))
        for path in (
            "report_key_integrity_required",
            "report_key_integrity_gate.required",
            "report_key_integrity_gate.scan_duplicate_terminal_keys",
            "result.report_key_integrity_gate.required",
        )
    )


def is_report_context_key(key: str) -> bool:
    normalized = key.strip().lower()
    return normalized in REPORT_CONTEXT_KEYS or normalized.endswith("_report")


def collect_report_roots(
    value: Any, path: str = "$", key: str = ""
) -> list[tuple[str, Any]]:
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


def collect_terminal_key_values(
    value: Any, path: str = "$"
) -> dict[str, list[tuple[str, str, Any]]]:
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


def canonical_encoded(value: Any) -> str:
    try:
        return json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )
    except TypeError:
        return repr(value)


def opaque_fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_encoded(value).encode("utf-8")).hexdigest()


def opaque_binding_evidence(
    *,
    root_ref: Any,
    field_id: Any,
    entries: list[tuple[str, str, Any]],
) -> dict[str, Any]:
    return {
        "root_ref_sha256": opaque_fingerprint(root_ref),
        "field_id_sha256": opaque_fingerprint(field_id),
        "source_ref_sha256": [opaque_fingerprint(path) for path, _, _ in entries],
        "value_sha256": sorted({opaque_fingerprint(value) for _, _, value in entries}),
        "binding_count": len(entries),
        "distinct_value_count": len({encoded for _, encoded, _ in entries}),
    }


def bounded_scalar_text(
    value: Any, *, max_length: int = IDENTITY_SCALAR_MAX_LENGTH
) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    normalized = str(value).strip()
    if not normalized or len(normalized) > max_length:
        return None
    return normalized


def identity_divergence_evidence(
    *,
    root_ref: str,
    source_ref: str,
    field_id: str,
    canonical_value: str,
    observed_value: str,
) -> dict[str, Any]:
    return opaque_binding_evidence(
        root_ref=root_ref,
        field_id=field_id,
        entries=[
            (root_ref, json.dumps(canonical_value), canonical_value),
            (source_ref, json.dumps(observed_value), observed_value),
        ],
    )


def _first_text(value: dict[str, Any], keys: set[str]) -> str | None:
    for key, child in value.items():
        if str(key).strip().lower() not in keys:
            continue
        normalized = bounded_scalar_text(child)
        if normalized:
            return normalized
    return None


def projection_fingerprint(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    direct = _first_text(value, PROJECTION_FINGERPRINT_KEYS)
    if direct:
        return direct
    for key in (
        "actual_artifact_truth",
        "projection_identity",
        "decision_input_identity",
        "decision_artifact_ref",
    ):
        child = value.get(key)
        if isinstance(child, dict):
            nested = _first_text(child, PROJECTION_FINGERPRINT_KEYS)
            if nested:
                return nested
    return None


def projection_artifact_id(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    for key in ("current_artifact_id", "artifact_id"):
        normalized = bounded_scalar_text(value.get(key))
        if normalized:
            return normalized
    for key in (
        "actual_artifact_truth",
        "projection_identity",
        "decision_input_identity",
        "decision_artifact_ref",
    ):
        child = value.get(key)
        if isinstance(child, dict):
            nested = projection_artifact_id(child)
            if nested:
                return nested
    return None


def projected_field_ids(
    data: dict[str, Any], roots: list[tuple[str, Any]]
) -> list[str]:
    values: list[Any] = []
    for source in [data, *(root for _, root in roots)]:
        if not isinstance(source, dict):
            continue
        for key in (
            "recomputed_fields",
            "canonical_projection_fields",
            "projected_field_ids",
        ):
            if key in source:
                values.append(source.get(key))
        actual_truth = source.get("actual_artifact_truth")
        if isinstance(actual_truth, dict):
            values.append(actual_truth.get("recomputed_fields"))
    fields: list[str] = []
    for value in values:
        if not isinstance(value, (list, tuple, set)):
            value = [value]
        if isinstance(value, (list, tuple, set)):
            for item in value:
                normalized = bounded_scalar_text(item)
                if normalized:
                    fields.append(normalized)
    return list(dict.fromkeys(fields))


def projected_field_contract_supplied(
    data: dict[str, Any], roots: list[tuple[str, Any]]
) -> bool:
    for source in [data, *(root for _, root in roots)]:
        if not isinstance(source, dict):
            continue
        if any(
            key in source
            for key in (
                "recomputed_fields",
                "canonical_projection_fields",
                "projected_field_ids",
            )
        ):
            return True
        actual_truth = source.get("actual_artifact_truth")
        if isinstance(actual_truth, dict) and "recomputed_fields" in actual_truth:
            return True
    return False


def collect_actual_roots(
    value: Any, path: str = "$", key: str = ""
) -> list[tuple[str, dict[str, Any]]]:
    roots: list[tuple[str, dict[str, Any]]] = []
    if isinstance(value, dict):
        if key and is_report_context_key(key):
            return roots
        for key, child in value.items():
            child_path = f"{path}.{key}"
            normalized = str(key).strip().lower()
            if normalized in ACTUAL_CONTEXT_KEYS and isinstance(child, dict):
                roots.append((child_path, child))
                continue
            roots.extend(collect_actual_roots(child, child_path, str(key)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            roots.extend(collect_actual_roots(child, f"{path}[{index}]", key))
    return roots


def _report_root_name(path: str) -> str:
    return path.rsplit(".", 1)[-1].split("[", 1)[0]


def scoped_report_roots(
    data: dict[str, Any], roots: list[tuple[str, Any]]
) -> list[tuple[str, Any]]:
    canonical_artifact_id = projection_artifact_id(data)
    canonical_fingerprint = projection_fingerprint(data)
    required = report_integrity_required(data)
    scoped: list[tuple[str, Any]] = []
    for path, root in roots:
        root_artifact_id = projection_artifact_id(root)
        root_fingerprint = projection_fingerprint(root)
        if not canonical_artifact_id and not canonical_fingerprint:
            if required or root_artifact_id or root_fingerprint:
                scoped.append((path, root))
            continue
        artifact_conflict = bool(
            canonical_artifact_id
            and root_artifact_id
            and root_artifact_id != canonical_artifact_id
        )
        fingerprint_conflict = bool(
            canonical_fingerprint
            and root_fingerprint
            and root_fingerprint != canonical_fingerprint
        )
        artifact_match = bool(
            canonical_artifact_id and root_artifact_id == canonical_artifact_id
        )
        fingerprint_match = bool(
            canonical_fingerprint and root_fingerprint == canonical_fingerprint
        )
        if required and not root_artifact_id and not root_fingerprint:
            scoped.append((path, root))
            continue
        if (
            not artifact_conflict
            and not fingerprint_conflict
            and (artifact_match or fingerprint_match)
        ):
            scoped.append((path, root))
    return scoped
