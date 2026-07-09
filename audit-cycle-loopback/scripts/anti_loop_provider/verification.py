from __future__ import annotations

from .common import *

def evidence_source_metadata(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    source = value.get("evidence_provenance_gate") if isinstance(value.get("evidence_provenance_gate"), dict) else value
    return {
        "verification_input_paths": string_list(
            source.get("verification_input_paths")
            or source.get("verification_inputs")
            or source.get("input_paths")
            or source.get("read_paths")
        ),
        "verification_input_ids": string_list(source.get("verification_input_ids")),
        "producer_input_ids": string_list(source.get("producer_input_ids")),
        "verified_artifact_ids": string_list(source.get("verified_artifact_ids")),
        "input_fingerprints": source.get("input_fingerprints") if isinstance(source.get("input_fingerprints"), dict) else {},
        "self_grounded_axes": {
            normalize_gate_key(item)
            for item in string_list(
                source.get("self_grounded_axes")
                or source.get("self_grounded_fields")
                or source.get("self_grounded_metrics")
            )
        },
        "disagreement_count": source.get("disagreement_count"),
        "zero_disagreement_reported": (
            source.get("disagreement_count") == 0
            or bool_value(source.get("zero_disagreement_reported"))
            or bool_value(source.get("no_disagreements"))
        ),
    }

def verification_source_separation_gate(
    *,
    provenance_value: Any,
    verified_artifact_paths: list[str],
    independently_verified_fields: list[str],
) -> dict[str, Any]:
    metadata = evidence_source_metadata(provenance_value)
    independent = sorted(set(independently_verified_fields))
    self_grounded = set(metadata.get("self_grounded_axes") or set())
    source_required_fields = [field for field in independent if normalize_gate_key(field) not in self_grounded]
    input_paths = [path.replace("\\", "/").lstrip("./") for path in metadata.get("verification_input_paths") or []]
    artifact_paths = [path.replace("\\", "/").lstrip("./") for path in verified_artifact_paths]
    overlaps: list[str] = []
    for input_path in input_paths:
        for artifact_path in artifact_paths:
            if input_path == artifact_path or path_matches_pattern(input_path, artifact_path) or path_matches_pattern(artifact_path, input_path):
                overlaps.append(input_path)
                break
    missing = bool(source_required_fields and not input_paths)
    overlap = bool(source_required_fields and overlaps)
    pass_status = bool(independent) and not missing and not overlap
    downgraded = source_required_fields if (missing or overlap) else []
    status = "pass" if pass_status else ("not_evaluated" if not independent else "block")
    return {
        "gate": "H4-VERIFICATION-SOURCE-SEPARATION",
        "verification_input_paths": input_paths,
        "verified_artifact_paths": artifact_paths,
        "verification_input_ids": metadata.get("verification_input_ids") or [],
        "producer_input_ids": metadata.get("producer_input_ids") or [],
        "verified_artifact_ids": metadata.get("verified_artifact_ids") or [],
        "input_fingerprints": metadata.get("input_fingerprints") or {},
        "self_grounded_axes": sorted(self_grounded),
        "source_separation_required_fields": source_required_fields,
        "verification_input_disjoint": bool(source_required_fields and input_paths and not overlaps),
        "verification_input_overlap_paths": sorted(set(overlaps)),
        "independent_source_separation_status": "missing" if missing else ("overlap" if overlap else ("pass" if pass_status else "not_evaluated")),
        "independently_verified_downgraded_fields": downgraded,
        "zero_disagreement_reported": bool_value(metadata.get("zero_disagreement_reported")),
        "status": status,
        "constrains_disposition": False,
    }

def load_changed_files(root: Path, changed_files_json: str | None, changed_files: list[str]) -> list[str]:
    values: list[str] = list(changed_files or [])
    loaded = load_json_value(root, changed_files_json)
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
        text = clean_provenance_path_ref(str(value or ""))
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
    return normalize_root_family_key(str(value or "unknown_gate"))

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
        values = string_list(paths)
        if isinstance(paths, dict):
            for child_key in ("paths", "source_paths", "verifier_paths", "files"):
                values.extend(string_list(paths.get(child_key)))
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
        normalized = normalize_gate_evaluation_status(gate.get(key))
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
        bool_value(gate.get(key))
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
