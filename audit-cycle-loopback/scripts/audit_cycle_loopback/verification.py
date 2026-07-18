from __future__ import annotations

from typing import Any
from pathlib import Path
import fnmatch
from . import acceptance as _acceptance
from . import families as _families
from . import root_cause as _root_cause
from . import values as _values
from . import vectors as _vectors


def evidence_source_metadata(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    source = value.get("evidence_provenance_gate") if isinstance(value.get("evidence_provenance_gate"), dict) else value
    axis_kinds: dict[str, str] = {}
    axis_scopes: dict[str, str] = {}
    scalar_maps: dict[str, dict[str, str]] = {
        field: {}
        for field in (
            "producer_function_id",
            "verifier_function_id",
            "producer_input_fingerprint",
            "verifier_input_fingerprint",
            "producer_invariant_owner_id",
            "verifier_invariant_owner_id",
            "invariant_separation_status",
        )
    }
    provenance_rows = source.get("evidence_provenance") or source.get("metric_provenance")
    if isinstance(provenance_rows, dict):
        for axis_id, row in provenance_rows.items():
            if isinstance(row, dict):
                normalized_axis = normalize_gate_key(axis_id)
                axis_kind = row.get("axis_kind") or row.get("kind")
                if axis_kind:
                    axis_kinds[normalized_axis] = str(axis_kind).strip().lower()
                axis_scope = row.get("axis_scope") or row.get("scope")
                if axis_scope:
                    axis_scopes[normalized_axis] = str(axis_scope).strip().lower()
                for field, mapping in scalar_maps.items():
                    value = row.get(field)
                    if isinstance(value, str) and value.strip():
                        mapping[normalized_axis] = value.strip()
    if isinstance(source.get("axis_kinds"), dict):
        axis_kinds.update(
            {
                normalize_gate_key(axis_id): str(axis_kind).strip().lower()
                for axis_id, axis_kind in source["axis_kinds"].items()
                if str(axis_kind).strip()
            }
        )
    return {
        "verification_input_paths": _vectors.string_list(
            source.get("verification_input_paths")
            or source.get("verification_inputs")
            or source.get("input_paths")
            or source.get("read_paths")
        ),
        "verification_input_ids": _vectors.string_list(source.get("verification_input_ids")),
        "producer_input_ids": _vectors.string_list(source.get("producer_input_ids")),
        "verified_artifact_ids": _vectors.string_list(source.get("verified_artifact_ids")),
        "input_fingerprints": source.get("input_fingerprints") if isinstance(source.get("input_fingerprints"), dict) else {},
        "axis_kinds": axis_kinds,
        "axis_scopes": axis_scopes,
        **{
            field: {
                **mapping,
                **(
                    {"*": source[field].strip()}
                    if isinstance(source.get(field), str) and source[field].strip()
                    else {}
                ),
            }
            for field, mapping in scalar_maps.items()
        },
        "self_grounded_axes": {
            normalize_gate_key(item)
            for item in _vectors.string_list(
                source.get("self_grounded_axes")
                or source.get("self_grounded_fields")
                or source.get("self_grounded_metrics")
            )
        },
        "disagreement_count": source.get("disagreement_count"),
        "zero_disagreement_reported": (
            source.get("disagreement_count") == 0
            or _values.bool_value(source.get("zero_disagreement_reported"))
            or _values.bool_value(source.get("no_disagreements"))
        ),
    }

def _fingerprint_values(raw: Any) -> set[str]:
    if isinstance(raw, dict):
        return {
            str(child)
            for child in raw.values()
            if isinstance(child, (str, int, float)) and str(child)
        }
    return {str(child) for child in _values.list_values(raw) if str(child)}


def _source_comparison(
    metadata: dict[str, Any], input_paths: list[str], artifact_paths: list[str]
) -> tuple[list[str], list[str], list[str], list[bool]]:
    overlaps = [
        input_path
        for input_path in input_paths
        if any(
            input_path == artifact_path
            or path_matches_pattern(input_path, artifact_path)
            or path_matches_pattern(artifact_path, input_path)
            for artifact_path in artifact_paths
        )
    ]
    verification_ids = set(metadata.get("verification_input_ids") or [])
    target_ids = set(metadata.get("producer_input_ids") or []) | set(
        metadata.get("verified_artifact_ids") or []
    )
    fingerprint_map = metadata.get("input_fingerprints") or {}
    verification_fingerprints = _fingerprint_values(
        fingerprint_map.get("verification_inputs")
        or fingerprint_map.get("verification")
        or {key: fingerprint_map.get(key) for key in verification_ids if key in fingerprint_map}
    )
    producer_fingerprints = _fingerprint_values(
        fingerprint_map.get("producer_inputs")
        or fingerprint_map.get("producer")
        or fingerprint_map.get("verified_artifacts")
        or {key: fingerprint_map.get(key) for key in target_ids if key in fingerprint_map}
    )
    comparable = [
        bool(input_paths and artifact_paths),
        bool(verification_ids and target_ids),
        bool(verification_fingerprints and producer_fingerprints),
    ]
    return (
        overlaps,
        sorted(verification_ids & target_ids),
        sorted(verification_fingerprints & producer_fingerprints),
        comparable,
    )


def _axis_scalar(metadata: dict[str, Any], field_id: str, axis_id: str) -> str:
    values = metadata.get(field_id) or {}
    return str(values.get(axis_id) or values.get("*") or "")


def _verification_axis_row(
    field: str,
    metadata: dict[str, Any],
    self_grounded_fields: list[str],
    *,
    missing: bool,
    overlap: bool,
) -> tuple[dict[str, Any], str]:
    normalized = normalize_gate_key(field)
    axis_scope = (metadata.get("axis_scopes") or {}).get(normalized, "")
    axis_kind = (metadata.get("axis_kinds") or {}).get(normalized, "unspecified")
    producer_owner = _axis_scalar(metadata, "producer_invariant_owner_id", normalized)
    verifier_owner = _axis_scalar(metadata, "verifier_invariant_owner_id", normalized)
    declared_status = _axis_scalar(metadata, "invariant_separation_status", normalized).lower()
    if producer_owner and producer_owner == verifier_owner:
        invariant_status = "coupled"
    elif producer_owner and verifier_owner and declared_status == "independent":
        invariant_status = "independent"
    elif declared_status == "coupled":
        invariant_status = "coupled"
    else:
        invariant_status = "unknown"
    category = "downgraded"
    if field in self_grounded_fields:
        coupling_status = "same_artifact"
        valid = axis_scope == "root_local" and axis_kind not in {"semantic", "source_semantic"}
        evidence_provenance = "self_grounded" if valid else "not_evaluated"
        category = "self_grounded" if valid else category
    elif missing:
        coupling_status, evidence_provenance = "unknown", "not_evaluated"
    elif overlap:
        coupling_status, evidence_provenance = "overlapping", "producer_attested"
    else:
        coupling_status = "disjoint"
        evidence_provenance = "independently_verified" if invariant_status == "independent" else "producer_attested"
        category = "independent" if invariant_status == "independent" else invariant_status
    row = {
        "axis_id": field,
        "axis_kind": axis_kind,
        "axis_scope": axis_scope or "unknown",
        "semantic_axis": axis_kind in {"semantic", "source_semantic"},
        "verification_input_ids": metadata.get("verification_input_ids") or [],
        "verifier_input_ids": metadata.get("verification_input_ids") or [],
        "verified_artifact_ids": metadata.get("verified_artifact_ids") or [],
        "producer_input_ids": metadata.get("producer_input_ids") or [],
        "input_fingerprints": metadata.get("input_fingerprints") or {},
        "coupling_status": coupling_status,
        "producer_function_id": _axis_scalar(metadata, "producer_function_id", normalized),
        "verifier_function_id": _axis_scalar(metadata, "verifier_function_id", normalized),
        "producer_input_fingerprint": _axis_scalar(metadata, "producer_input_fingerprint", normalized),
        "verifier_input_fingerprint": _axis_scalar(metadata, "verifier_input_fingerprint", normalized),
        "producer_invariant_owner_id": producer_owner,
        "verifier_invariant_owner_id": verifier_owner,
        "invariant_separation_status": invariant_status,
        "evidence_provenance": evidence_provenance,
    }
    return row, category


def verification_source_separation_gate(
    *,
    provenance_value: Any,
    verified_artifact_paths: list[str],
    independently_verified_fields: list[str],
    self_grounded_fields: list[str] | None = None,
) -> dict[str, Any]:
    metadata = evidence_source_metadata(provenance_value)
    independent = sorted(set(independently_verified_fields) | set(self_grounded_fields or []))
    self_grounded = set(metadata.get("self_grounded_axes") or set()) | {
        normalize_gate_key(field) for field in self_grounded_fields or []
    }
    source_required = [field for field in independent if normalize_gate_key(field) not in self_grounded]
    grounded = [field for field in independent if normalize_gate_key(field) in self_grounded]
    input_paths = [path.replace("\\", "/").lstrip("./") for path in metadata.get("verification_input_paths") or []]
    artifact_paths = [path.replace("\\", "/").lstrip("./") for path in verified_artifact_paths]
    overlaps, identity_overlaps, fingerprint_overlaps, comparable = _source_comparison(
        metadata, input_paths, artifact_paths
    )
    missing = bool(source_required and not any(comparable))
    overlap = bool(source_required and (overlaps or identity_overlaps or fingerprint_overlaps))
    rows_with_categories = [
        _verification_axis_row(field, metadata, grounded, missing=missing, overlap=overlap)
        for field in independent
    ]
    axis_rows = [row for row, _ in rows_with_categories]
    independent_actual = [row["axis_id"] for row, category in rows_with_categories if category == "independent"]
    grounded_actual = [row["axis_id"] for row, category in rows_with_categories if category == "self_grounded"]
    coupled = [row["axis_id"] for row, category in rows_with_categories if category == "coupled"]
    invariant_missing = [row["axis_id"] for row, category in rows_with_categories if category == "unknown" and not missing and not overlap]
    pass_status = bool(independent_actual or grounded_actual)
    independent_source = bool(source_required) and not missing and not overlap
    return {
        "gate": "H4-VERIFICATION-SOURCE-SEPARATION",
        "verification_input_paths": input_paths,
        "verified_artifact_paths": artifact_paths,
        "verification_input_ids": metadata.get("verification_input_ids") or [],
        "producer_input_ids": metadata.get("producer_input_ids") or [],
        "verified_artifact_ids": metadata.get("verified_artifact_ids") or [],
        "input_fingerprints": metadata.get("input_fingerprints") or {},
        "self_grounded_axes": sorted(self_grounded),
        "self_grounded_fields": grounded,
        "verification_axes": axis_rows,
        "source_separation_required_fields": source_required,
        "verification_input_disjoint": bool(source_required and input_paths and not overlaps),
        "verification_input_overlap_paths": sorted(set(overlaps)),
        "verification_identity_overlap_ids": identity_overlaps,
        "verification_fingerprint_overlap": fingerprint_overlaps,
        "independent_source_separation_status": "missing" if missing else "overlap" if overlap else "pass" if independent_source else "self_grounded" if grounded else "not_evaluated",
        "independent_invariant_separation_status": "coupled" if coupled else "unknown" if invariant_missing else "pass" if independent_actual else "not_evaluated",
        "invariant_separation_missing_fields": invariant_missing,
        "invariant_separation_coupled_fields": coupled,
        "independently_verified_downgraded_fields": sorted(set(independent) - set(independent_actual)),
        "zero_disagreement_reported": _values.bool_value(metadata.get("zero_disagreement_reported")),
        "status": "pass" if pass_status else "not_evaluated" if not independent else "block",
        "constrains_disposition": False,
    }

def load_changed_files(root: Path, changed_files_json: str | None, changed_files: list[str]) -> list[str]:
    values: list[str] = list(changed_files or [])
    loaded = _values.load_json_value(root, changed_files_json)
    if isinstance(loaded, list):
        values.extend(str(item) for item in loaded if item is not None)
    elif isinstance(loaded, dict):
        for key in ("changed_files", "files", "paths", "changed_paths", "modified_files"):
            raw = loaded.get(key)
            if isinstance(raw, list):
                for item in raw:
                    if isinstance(item, dict) and item.get("path"):
                        values.append(str(item["path"]))
                    elif item is not None:
                        values.append(str(item))
    normalized: list[str] = []
    for value in values:
        text = _root_cause.clean_provenance_path_ref(str(value or ""))
        if not text:
            continue
        path = Path(text)
        if path.is_absolute():
            try:
                text = path.resolve().relative_to(root.resolve()).as_posix()
            except (OSError, ValueError):
                text = path.as_posix()
        else:
            text = text.replace("\\", "/").lstrip("./")
        if text and text not in normalized:
            normalized.append(text)
    return normalized

def path_matches_pattern(path: str, pattern: str) -> bool:
    candidate = path.replace("\\", "/").lstrip("./")
    raw = pattern.replace("\\", "/").strip().lstrip("./")
    if not candidate or not raw:
        return False
    if raw.endswith("/"):
        return candidate.startswith(raw)
    return (
        candidate == raw
        or candidate.startswith(raw.rstrip("/") + "/")
        or fnmatch.fnmatch(candidate, raw)
        or fnmatch.fnmatch(candidate, raw.rstrip("/") + "/**")
    )

def normalize_gate_key(value: Any) -> str:
    return _families.normalize_root_family_key(str(value or "unknown_gate"))

def normalize_verifier_source_paths(value: Any) -> tuple[dict[str, list[str]], bool]:
    if value is None:
        return {}, False
    source = value
    if isinstance(value, dict):
        for key in ("verifier_source_paths", "gate_verifier_source_paths", "gate_sources", "sources"):
            if key in value:
                source = value.get(key)
                break
    mapping: dict[str, list[str]] = {}

    def add(gate_id: Any, paths: Any) -> None:
        key = normalize_gate_key(gate_id or "*")
        values = _vectors.string_list(paths)
        if isinstance(paths, dict):
            for child_key in ("paths", "source_paths", "verifier_paths", "files"):
                values.extend(_vectors.string_list(paths.get(child_key)))
        if values:
            bucket = mapping.setdefault(key, [])
            for item in values:
                if item not in bucket:
                    bucket.append(item)

    if isinstance(source, dict):
        for gate_id, paths in source.items():
            if gate_id in {"paths", "source_paths", "verifier_paths", "files"}:
                add("*", paths)
            else:
                add(gate_id, paths)
    elif isinstance(source, list):
        for item in source:
            if isinstance(item, dict):
                gate_id = item.get("gate") or item.get("gate_id") or item.get("name") or item.get("id") or "*"
                paths = item.get("paths") or item.get("source_paths") or item.get("verifier_paths") or item.get("files")
                add(gate_id, paths)
            elif isinstance(item, str):
                add("*", item)
    elif isinstance(source, str):
        add("*", source)
    return mapping, True

def gate_evaluation_status(gate: dict[str, Any]) -> str | None:
    for key in ("evaluation_status", "status", "verdict", "result"):
        normalized = _acceptance.normalize_gate_evaluation_status(gate.get(key))
        if normalized:
            return normalized
    return None

def gate_is_passing(gate: dict[str, Any]) -> bool:
    status = gate_evaluation_status(gate)
    if status == "pass":
        return True
    if status in {"fail", "not_evaluated"}:
        return False
    return any(
        _values.bool_value(gate.get(key))
        for key in (
            "quality_delta_pass",
            "substance_delta_pass",
            "primary_metric_high_water_moved",
            "structure_high_water_moved",
        )
    )

def coupled_verifier_gate(
    *,
    changed_files: list[str],
    verifier_source_map: dict[str, list[str]],
    hook_provided: bool,
    gates: list[dict[str, Any]],
) -> dict[str, Any]:
    if not hook_provided:
        return {
            "gate": "F1-VERIFIER-COUPLING",
            "verifier_source_paths_status": "not_provided",
            "changed_files_status": "not_provided" if not changed_files else "provided",
            "pass_with_coupled_verifier": False,
            "status": "not_evaluated",
            "constrains_disposition": False,
        }
    affected: list[dict[str, Any]] = []
    changed_source_paths: list[str] = []
    for gate in gates:
        gate_id = normalize_gate_key(gate.get("gate") or gate.get("name") or gate.get("id"))
        patterns = list(verifier_source_map.get(gate_id) or []) + list(verifier_source_map.get("*") or [])
        if not patterns:
            continue
        matched = [
            changed
            for changed in changed_files
            if any(path_matches_pattern(changed, pattern) for pattern in patterns)
        ]
        if not matched:
            continue
        changed_source_paths.extend(matched)
        if gate_is_passing(gate):
            affected.append(
                {
                    "gate": gate.get("gate") or gate.get("name") or gate_id,
                    "evaluation_status": gate_evaluation_status(gate) or "pass",
                    "changed_source_paths": sorted(set(matched)),
                    "verifier_source_paths": sorted(set(patterns)),
                    "effective_result": "pass_with_coupled_verifier",
                }
            )
    coupled = bool(affected)
    return {
        "gate": "F1-VERIFIER-COUPLING",
        "verifier_source_paths_status": "provided",
        "changed_files_status": "provided" if changed_files else "not_provided",
        "changed_files": changed_files,
        "changed_verifier_source_paths": sorted(set(changed_source_paths)),
        "affected_passing_gates": affected,
        "pass_with_coupled_verifier": coupled,
        "status": "block" if coupled else "ok",
        "hard_stop_required": coupled,
        "constrains_disposition": coupled,
        "allowed_dispositions": ["goal_productive", "terminal_blocked", "user_escalation"],
        "allowed_task_kinds": ["verifier_revalidation", "independent_evidence_recalculation"],
    }
