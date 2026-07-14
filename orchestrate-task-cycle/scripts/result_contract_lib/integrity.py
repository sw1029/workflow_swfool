from __future__ import annotations

import hashlib
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


def canonical_encoded(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
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


def bounded_scalar_text(value: Any, *, max_length: int = IDENTITY_SCALAR_MAX_LENGTH) -> str | None:
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
    for key in ("actual_artifact_truth", "projection_identity", "decision_input_identity", "decision_artifact_ref"):
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
    for key in ("actual_artifact_truth", "projection_identity", "decision_input_identity", "decision_artifact_ref"):
        child = value.get(key)
        if isinstance(child, dict):
            nested = projection_artifact_id(child)
            if nested:
                return nested
    return None


def projected_field_ids(data: dict[str, Any], roots: list[tuple[str, Any]]) -> list[str]:
    values: list[Any] = []
    for source in [data, *(root for _, root in roots)]:
        if not isinstance(source, dict):
            continue
        for key in ("recomputed_fields", "canonical_projection_fields", "projected_field_ids"):
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


def projected_field_contract_supplied(data: dict[str, Any], roots: list[tuple[str, Any]]) -> bool:
    for source in [data, *(root for _, root in roots)]:
        if not isinstance(source, dict):
            continue
        if any(key in source for key in ("recomputed_fields", "canonical_projection_fields", "projected_field_ids")):
            return True
        actual_truth = source.get("actual_artifact_truth")
        if isinstance(actual_truth, dict) and "recomputed_fields" in actual_truth:
            return True
    return False


def collect_actual_roots(value: Any, path: str = "$", key: str = "") -> list[tuple[str, dict[str, Any]]]:
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


def scoped_report_roots(data: dict[str, Any], roots: list[tuple[str, Any]]) -> list[tuple[str, Any]]:
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
            canonical_artifact_id and root_artifact_id and root_artifact_id != canonical_artifact_id
        )
        fingerprint_conflict = bool(
            canonical_fingerprint and root_fingerprint and root_fingerprint != canonical_fingerprint
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
        if not artifact_conflict and not fingerprint_conflict and (artifact_match or fingerprint_match):
            scoped.append((path, root))
    return scoped


def cross_report_projection_values(
    data: dict[str, Any],
    roots: list[tuple[str, Any]],
) -> tuple[str | None, list[str], dict[str, list[tuple[str, str, Any]]], list[dict[str, Any]]]:
    top_level_fingerprint = projection_fingerprint(data)
    top_level_artifact_id = projection_artifact_id(data)
    root_identities = [
        (path, root, projection_artifact_id(root), projection_fingerprint(root))
        for path, root in roots
    ]
    artifact_groups: dict[str, list[tuple[str, Any, str | None, str | None]]] = {}
    for identity in root_identities:
        if identity[2]:
            artifact_groups.setdefault(identity[2], []).append(identity)

    canonical_artifact_id = top_level_artifact_id
    canonical_fingerprint = top_level_fingerprint
    if not top_level_artifact_id and not top_level_fingerprint:
        shared_artifact_ids = [
            artifact_id
            for artifact_id, identities in artifact_groups.items()
            if len(identities) >= 2
        ]
        if len(shared_artifact_ids) == 1:
            canonical_artifact_id = shared_artifact_ids[0]
    top_artifact_matched_by_root = bool(
        top_level_artifact_id
        and any(root_artifact_id == top_level_artifact_id for _, _, root_artifact_id, _ in root_identities)
    )
    if not top_level_fingerprint and not top_artifact_matched_by_root:
        explicit_fingerprints = [
            fingerprint
            for _, _, _, fingerprint in root_identities
            if fingerprint
        ]
        if len(explicit_fingerprints) >= 2 and len(set(explicit_fingerprints)) == 1:
            canonical_fingerprint = explicit_fingerprints[0]

    identity_divergences: list[dict[str, Any]] = []
    if top_level_artifact_id or top_level_fingerprint:
        for path, _, root_artifact_id, fingerprint in root_identities:
            artifact_conflicts = bool(
                top_level_artifact_id
                and root_artifact_id
                and root_artifact_id != top_level_artifact_id
            )
            fingerprint_conflicts = bool(
                top_level_fingerprint
                and fingerprint
                and fingerprint != top_level_fingerprint
            )
            if artifact_conflicts:
                if report_integrity_required(data) or (
                    top_level_fingerprint and fingerprint == top_level_fingerprint
                ):
                    identity_divergences.append(
                        identity_divergence_evidence(
                            root_ref="$canonical_projection",
                            source_ref=path,
                            field_id="artifact_id",
                            canonical_value=top_level_artifact_id,
                            observed_value=root_artifact_id,
                        )
                    )
                continue
            if fingerprint_conflicts:
                identity_divergences.append(
                    identity_divergence_evidence(
                        root_ref="$canonical_projection",
                        source_ref=path,
                        field_id="body_projection_fingerprint",
                        canonical_value=top_level_fingerprint,
                        observed_value=fingerprint,
                    )
                )

    if not top_level_fingerprint:
        artifact_ids_to_check = (
            [top_level_artifact_id]
            if top_level_artifact_id
            else [
                artifact_id
                for artifact_id, identities in artifact_groups.items()
                if len(identities) >= 2
            ]
        )
        for artifact_id in artifact_ids_to_check:
            fingerprint_entries = [
                (path, json.dumps(fingerprint), fingerprint)
                for path, _, _, fingerprint in artifact_groups.get(artifact_id, [])
                if fingerprint
            ]
            if len({encoded for _, encoded, _ in fingerprint_entries}) <= 1:
                continue
            identity_divergences.append(
                opaque_binding_evidence(
                    root_ref="$shared_artifact_projection",
                    field_id="body_projection_fingerprint",
                    entries=fingerprint_entries,
                )
            )

    if not canonical_fingerprint and not canonical_artifact_id:
        return None, [], {}, identity_divergences

    scoped_roots: list[tuple[str, Any]] = []
    for path, root, root_artifact_id, root_fingerprint in root_identities:
        if not root_artifact_id and not root_fingerprint:
            continue
        artifact_matches = bool(
            canonical_artifact_id
            and root_artifact_id
            and root_artifact_id == canonical_artifact_id
        )
        fingerprint_matches = bool(
            canonical_fingerprint
            and root_fingerprint
            and root_fingerprint == canonical_fingerprint
        )
        artifact_conflicts = bool(
            canonical_artifact_id
            and root_artifact_id
            and root_artifact_id != canonical_artifact_id
        )
        fingerprint_conflicts = bool(
            canonical_fingerprint
            and root_fingerprint
            and root_fingerprint != canonical_fingerprint
        )
        if artifact_conflicts or fingerprint_conflicts:
            continue
        if artifact_matches or fingerprint_matches:
            scoped_roots.append((path, root))

    field_ids = projected_field_ids(data, scoped_roots)
    if not field_ids:
        return canonical_fingerprint, [], {}, identity_divergences
    aggregated: dict[str, list[tuple[str, str, Any]]] = {}
    for root_path, root in scoped_roots:
        terminal_values = collect_terminal_key_values(root, root_path)
        for field_id in field_ids:
            aggregated.setdefault(field_id, []).extend(terminal_values.get(field_id, []))
    return canonical_fingerprint, field_ids, aggregated, identity_divergences


def report_key_divergences(data: dict[str, Any]) -> list[dict[str, Any]]:
    roots = collect_report_roots(data)
    if report_integrity_required(data) and not roots:
        roots = [("$", data)]
    local_roots = scoped_report_roots(data, roots)
    divergences: list[dict[str, Any]] = []
    if report_integrity_required(data) and (projection_artifact_id(data) or projection_fingerprint(data)):
        canonical_artifact_id = projection_artifact_id(data)
        canonical_fingerprint = projection_fingerprint(data)
        for root_path, root in roots:
            root_artifact_id = projection_artifact_id(root)
            root_fingerprint = projection_fingerprint(root)
            comparable_identity = bool(
                (canonical_artifact_id and root_artifact_id)
                or (canonical_fingerprint and root_fingerprint)
            )
            if comparable_identity:
                continue
            divergences.append(
                opaque_binding_evidence(
                    root_ref="$required_report_identity",
                    field_id="projection_identity_binding",
                    entries=[
                        ("$canonical_projection", json.dumps("present"), "projection_identity_present"),
                        (root_path, json.dumps("unbound"), "projection_identity_not_comparable"),
                    ],
                )
            )
    for root_path, root in local_roots:
        terminal_values = collect_terminal_key_values(root, root_path)
        for key, entries in terminal_values.items():
            unique_values = {encoded for _, encoded, _ in entries}
            if len(entries) < 2 or len(unique_values) <= 1:
                continue
            divergences.append(opaque_binding_evidence(root_ref=root_path, field_id=key, entries=entries))
    projection_roots = [
        (path, root)
        for path, root in roots
        if is_report_context_key(_report_root_name(path))
    ]
    _, _, cross_root_values, identity_divergences = cross_report_projection_values(data, projection_roots)
    divergences.extend(identity_divergences)
    for key, entries in cross_root_values.items():
        unique_values = {encoded for _, encoded, _ in entries}
        root_paths = {
            root_path
            for root_path, _ in projection_roots
            if any(path == root_path or path.startswith(f"{root_path}.") or path.startswith(f"{root_path}[") for path, _, _ in entries)
        }
        if len(root_paths) < 2 or len(unique_values) <= 1:
            continue
        divergences.append(opaque_binding_evidence(root_ref="$canonical_projection", field_id=key, entries=entries))
    return divergences


def report_key_duplicate_matches(data: dict[str, Any]) -> list[dict[str, Any]]:
    roots = collect_report_roots(data)
    if report_integrity_required(data) and not roots:
        roots = [("$", data)]
    local_roots = scoped_report_roots(data, roots)
    duplicates: list[dict[str, Any]] = []
    for root_path, root in local_roots:
        terminal_values = collect_terminal_key_values(root, root_path)
        for key, entries in terminal_values.items():
            unique_values = {encoded for _, encoded, _ in entries}
            if len(entries) < 2 or len(unique_values) != 1:
                continue
            evidence = opaque_binding_evidence(root_ref=root_path, field_id=key, entries=entries)
            evidence["duplicate_count"] = len(entries)
            duplicates.append(evidence)
    projection_roots = [
        (path, root)
        for path, root in roots
        if is_report_context_key(_report_root_name(path))
    ]
    _, _, cross_root_values, _ = cross_report_projection_values(data, projection_roots)
    for key, entries in cross_root_values.items():
        unique_values = {encoded for _, encoded, _ in entries}
        root_paths = {
            root_path
            for root_path, _ in projection_roots
            if any(path == root_path or path.startswith(f"{root_path}.") or path.startswith(f"{root_path}[") for path, _, _ in entries)
        }
        if len(root_paths) < 2 or len(unique_values) != 1:
            continue
        evidence = opaque_binding_evidence(root_ref="$canonical_projection", field_id=key, entries=entries)
        evidence["duplicate_count"] = len(entries)
        duplicates.append(evidence)
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
    actual_roots = collect_actual_roots(data)
    report_roots = [
        (path, value)
        for path, value in collect_report_roots(data)
        if isinstance(value, dict)
        and is_report_context_key(_report_root_name(path))
    ]
    projection_roots = [*actual_roots, *report_roots]
    field_ids = projected_field_ids(data, projection_roots)
    field_contract_supplied = projected_field_contract_supplied(data, projection_roots)
    canonical_fingerprint = projection_fingerprint(data)
    canonical_artifact_id = projection_artifact_id(data)
    divergences: list[dict[str, Any]] = []
    canonical_actual_conflicts: set[str] = set()
    canonical_report_conflicts: set[str] = set()
    for actual_name, actual_value in actual_roots:
        actual_artifact_id = projection_artifact_id(actual_value)
        actual_fingerprint = projection_fingerprint(actual_value)
        if canonical_artifact_id and actual_artifact_id and actual_artifact_id != canonical_artifact_id:
            divergences.append(
                identity_divergence_evidence(
                    root_ref="$canonical_actual_projection",
                    source_ref=actual_name,
                    field_id="artifact_id",
                    canonical_value=canonical_artifact_id,
                    observed_value=actual_artifact_id,
                )
            )
            canonical_actual_conflicts.add(actual_name)
        if canonical_fingerprint and actual_fingerprint and actual_fingerprint != canonical_fingerprint:
            divergences.append(
                identity_divergence_evidence(
                    root_ref="$canonical_actual_projection",
                    source_ref=actual_name,
                    field_id="body_projection_fingerprint",
                    canonical_value=canonical_fingerprint,
                    observed_value=actual_fingerprint,
                )
            )
            canonical_actual_conflicts.add(actual_name)
    for report_name, report_value in report_roots:
        report_artifact_id = projection_artifact_id(report_value)
        report_fingerprint = projection_fingerprint(report_value)
        comparable_identity = bool(
            (canonical_artifact_id and report_artifact_id)
            or (canonical_fingerprint and report_fingerprint)
        )
        if (
            report_integrity_required(data)
            and (canonical_artifact_id or canonical_fingerprint)
            and not comparable_identity
        ):
            divergences.append(
                opaque_binding_evidence(
                    root_ref="$required_report_identity",
                    field_id="projection_identity_binding",
                    entries=[
                        ("$canonical_projection", json.dumps("present"), "projection_identity_present"),
                        (report_name, json.dumps("unbound"), "projection_identity_not_comparable"),
                    ],
                )
            )
            canonical_report_conflicts.add(report_name)
            continue
        artifact_conflicts = bool(
            canonical_artifact_id
            and report_artifact_id
            and report_artifact_id != canonical_artifact_id
        )
        fingerprint_conflicts = bool(
            canonical_fingerprint
            and report_fingerprint
            and report_fingerprint != canonical_fingerprint
        )
        if artifact_conflicts:
            if report_integrity_required(data) or (
                canonical_fingerprint and report_fingerprint == canonical_fingerprint
            ):
                divergences.append(
                    identity_divergence_evidence(
                        root_ref="$canonical_report_projection",
                        source_ref=report_name,
                        field_id="artifact_id",
                        canonical_value=canonical_artifact_id,
                        observed_value=report_artifact_id,
                    )
                )
                canonical_report_conflicts.add(report_name)
            continue
        if fingerprint_conflicts:
            divergences.append(
                identity_divergence_evidence(
                    root_ref="$canonical_report_projection",
                    source_ref=report_name,
                    field_id="body_projection_fingerprint",
                    canonical_value=canonical_fingerprint,
                    observed_value=report_fingerprint,
                )
            )
            canonical_report_conflicts.add(report_name)
    for actual_name, actual_value in actual_roots:
        actual_fields = scalar_leaves(actual_value)
        for report_name, report_value in report_roots:
            if actual_name in canonical_actual_conflicts or report_name in canonical_report_conflicts:
                continue
            explicit_actual_artifact_id = projection_artifact_id(actual_value)
            report_artifact_id = projection_artifact_id(report_value)
            explicit_actual_fingerprint = projection_fingerprint(actual_value)
            report_fingerprint = projection_fingerprint(report_value)
            artifact_conflicts = bool(
                (canonical_artifact_id and explicit_actual_artifact_id and explicit_actual_artifact_id != canonical_artifact_id)
                or (canonical_artifact_id and report_artifact_id and report_artifact_id != canonical_artifact_id)
                or (
                    explicit_actual_artifact_id
                    and report_artifact_id
                    and explicit_actual_artifact_id != report_artifact_id
                )
            )
            pair_identity_comparable = bool(
                (explicit_actual_artifact_id and report_artifact_id)
                or (explicit_actual_fingerprint and report_fingerprint)
            )
            if (
                report_integrity_required(data)
                and not canonical_artifact_id
                and not canonical_fingerprint
                and (explicit_actual_artifact_id or explicit_actual_fingerprint)
                and not pair_identity_comparable
            ):
                divergences.append(
                    opaque_binding_evidence(
                        root_ref="$required_actual_report_identity",
                        field_id="projection_identity_binding",
                        entries=[
                            (actual_name, json.dumps("present"), "actual_projection_identity_present"),
                            (report_name, json.dumps("unbound"), "report_projection_identity_not_comparable"),
                        ],
                    )
                )
                continue
            if artifact_conflicts:
                if report_integrity_required(data):
                    divergences.append(
                        identity_divergence_evidence(
                            root_ref=actual_name,
                            source_ref=report_name,
                            field_id="artifact_id",
                            canonical_value=explicit_actual_artifact_id or canonical_artifact_id or "present",
                            observed_value=report_artifact_id or "missing",
                        )
                    )
                continue
            shared_artifact = bool(
                explicit_actual_artifact_id
                and report_artifact_id
                and explicit_actual_artifact_id == report_artifact_id
            )
            top_artifact_scoped = bool(
                canonical_artifact_id
                and report_artifact_id == canonical_artifact_id
                and explicit_actual_artifact_id in {None, canonical_artifact_id}
            )
            shared_fingerprint = bool(
                explicit_actual_fingerprint
                and report_fingerprint
                and explicit_actual_fingerprint == report_fingerprint
            )
            top_fingerprint_scoped = bool(
                canonical_fingerprint
                and report_fingerprint
                and explicit_actual_fingerprint in {None, canonical_fingerprint}
            )
            if not (shared_artifact or top_artifact_scoped or shared_fingerprint or top_fingerprint_scoped):
                continue
            actual_fingerprint = explicit_actual_fingerprint or canonical_fingerprint
            if actual_fingerprint and report_fingerprint and actual_fingerprint != report_fingerprint:
                divergences.append(
                    opaque_binding_evidence(
                        root_ref="$actual_report_projection",
                        field_id="body_projection_fingerprint",
                        entries=[
                            (actual_name, json.dumps(actual_fingerprint), actual_fingerprint),
                            (report_name, json.dumps(report_fingerprint), report_fingerprint),
                        ],
                    )
                )
                continue
            report_fields = scalar_leaves(report_value)
            if not field_contract_supplied:
                for field in sorted(set(actual_fields) & set(report_fields)):
                    if "." not in field and any(key.endswith(f".{field}") for key in actual_fields):
                        continue
                    if actual_fields[field] != report_fields[field]:
                        divergences.append(
                            opaque_binding_evidence(
                                root_ref="$actual_report_projection",
                                field_id=field,
                                entries=[
                                    (actual_name, canonical_encoded(actual_fields[field]), actual_fields[field]),
                                    (report_name, canonical_encoded(report_fields[field]), report_fields[field]),
                                ],
                            )
                        )
            else:
                actual_terminal = collect_terminal_key_values(actual_value, actual_name)
                report_terminal = collect_terminal_key_values(report_value, report_name)
                for field_id in field_ids:
                    actual_entries = actual_terminal.get(field_id, [])
                    report_entries = report_terminal.get(field_id, [])
                    if not actual_entries and not report_entries:
                        divergences.append(
                            opaque_binding_evidence(
                                root_ref="$actual_report_projection",
                                field_id=field_id,
                                entries=[
                                    (actual_name, json.dumps("missing"), "actual_projection_field_missing"),
                                    (report_name, json.dumps("missing"), "report_projection_field_missing"),
                                ],
                            )
                        )
                        continue
                    if not actual_entries or not report_entries:
                        divergences.append(
                            opaque_binding_evidence(
                                root_ref="$actual_report_projection",
                                field_id=field_id,
                                entries=[
                                    (
                                        actual_name,
                                        json.dumps(bool(actual_entries)),
                                        "projection_field_present" if actual_entries else "projection_field_missing",
                                    ),
                                    (
                                        report_name,
                                        json.dumps(bool(report_entries)),
                                        "projection_field_present" if report_entries else "projection_field_missing",
                                    ),
                                ],
                            )
                        )
                        continue
                    actual_values = {encoded for _, encoded, _ in actual_entries}
                    report_values = {encoded for _, encoded, _ in report_entries}
                    if actual_values != report_values:
                        divergences.append(
                            opaque_binding_evidence(
                                root_ref="$actual_report_projection",
                                field_id=field_id,
                                entries=[*actual_entries, *report_entries],
                            )
                        )
    return divergences
