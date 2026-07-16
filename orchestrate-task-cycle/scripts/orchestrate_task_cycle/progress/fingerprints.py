from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .io_utils import file_digest, resolve_existing_paths
from .provider import provider_failure_class
from .values import (
    boolish,
    collect_by_key,
    first_mapping,
    first_value,
    number_value,
    stable_digest,
)


def _artifact_policy(policy: dict[str, Any] | None) -> dict[str, Any]:
    value = (policy or {}).get("artifact_policy")
    return value if isinstance(value, dict) else {}


def input_fingerprint(
    root: Path,
    value: dict[str, Any],
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    explicit = first_value(
        value,
        (
            "consumed_input_fp",
            "feature_symbol.consumed_input_fp",
            "workflow_feature_symbol.consumed_input_fp",
        ),
    )
    if isinstance(explicit, str) and explicit.strip():
        return {"consumed_input_fp": explicit.strip(), "input_manifest_count": None}

    artifact = _artifact_policy(policy)
    raw_paths = collect_by_key(value, set(artifact.get("input_path_fields") or []))
    existing = resolve_existing_paths(root, raw_paths)
    allowed_names = set(artifact.get("input_manifest_names") or [])
    digest_parts: list[str] = []
    source_count = 0
    for path in existing:
        candidates = [path]
        if path.is_dir():
            candidates = [path / name for name in sorted(allowed_names)]
        for candidate in candidates:
            if not candidate.is_file() or candidate.name not in allowed_names:
                continue
            digest = file_digest(candidate)
            if digest:
                source_count += 1
                digest_parts.append(digest)
    for key in artifact.get("inline_input_fields") or []:
        raw = value.get(key)
        if isinstance(raw, (dict, list)):
            try:
                digest_parts.append(json.dumps(raw, ensure_ascii=False, sort_keys=True))
            except TypeError:
                continue
    return {
        "consumed_input_fp": stable_digest(digest_parts)[:32] if digest_parts else "none",
        "input_manifest_count": source_count,
    }


def target_unit_fingerprint(
    value: dict[str, Any],
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    explicit = first_value(
        value,
        (
            "target_unit_fp",
            "feature_symbol.target_unit_fp",
            "workflow_feature_symbol.target_unit_fp",
        ),
    )
    if isinstance(explicit, str) and explicit.strip():
        count = number_value(
            first_value(value, ("target_unit_count", "feature_symbol.target_unit_count"))
        )
        return {"target_unit_fp": explicit.strip(), "target_unit_count": count}
    keys = set(_artifact_policy(policy).get("target_unit_keys") or [])
    values = collect_by_key(value, keys) if keys else []
    return {
        "target_unit_fp": stable_digest(values)[:32] if values else "none",
        "target_unit_count": len(values),
    }


def workflow_feature_symbol(
    root: Path,
    value: dict[str, Any],
    blockers: list[str],
    axis: str | None,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    explicit = first_mapping(value, ("workflow_feature_symbol", "feature_symbol"))
    if isinstance(explicit.get("symbol"), str) and explicit["symbol"].strip():
        return {
            "symbol": explicit["symbol"].strip(),
            "scope": str(explicit.get("scope") or "workflow_loop"),
            "consumed_input_fp": explicit.get("consumed_input_fp") or "none",
            "input_manifest_count": number_value(explicit.get("input_manifest_count")),
            "target_unit_fp": explicit.get("target_unit_fp") or "none",
            "target_unit_count": number_value(explicit.get("target_unit_count")),
            "blocker_root_axis": explicit.get("blocker_root_axis") or axis or "unknown",
            "blocker_count": len(blockers),
        }
    input_part = input_fingerprint(root, value, policy)
    target_part = target_unit_fingerprint(value, policy)
    blocker_root_axis = axis or "unknown"
    symbol = stable_digest(
        [input_part["consumed_input_fp"], target_part["target_unit_fp"], blocker_root_axis]
    )[:24]
    return {
        "symbol": f"wf:{symbol}",
        "scope": "workflow_loop",
        "consumed_input_fp": input_part["consumed_input_fp"],
        "input_manifest_count": input_part["input_manifest_count"],
        "target_unit_fp": target_part["target_unit_fp"],
        "target_unit_count": target_part["target_unit_count"],
        "blocker_root_axis": blocker_root_axis,
        "blocker_count": len(blockers),
    }


def output_candidate_paths(
    root: Path,
    value: dict[str, Any],
    policy: dict[str, Any] | None = None,
) -> list[Path]:
    keys = set(_artifact_policy(policy).get("path_fields") or [])
    raw_paths = collect_by_key(value, keys) if keys else []
    return resolve_existing_paths(root, raw_paths)


def _record_identity(record: Any, fields: list[str]) -> str | None:
    if not isinstance(record, dict):
        return None
    values = [str(record[field]).strip() for field in fields if field in record and str(record[field]).strip()]
    return "|".join(values) if values else None


def _jsonl_summary(path: Path, identity_fields: list[str]) -> dict[str, Any]:
    count = 0
    identities: list[str] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if not line.strip():
                    continue
                count += 1
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                identity = _record_identity(record, identity_fields)
                if identity:
                    identities.append(identity)
    except OSError:
        return {"count": 0, "identity_digest": None}
    return {
        "count": count,
        "identity_digest": stable_digest(identities)[:32] if identities else None,
    }


def _configured_artifact_summary(
    paths: list[Path],
    policy: dict[str, Any] | None,
) -> dict[str, Any]:
    file_kinds = _artifact_policy(policy).get("file_kinds") or []
    configs = {item["file_name"]: item for item in file_kinds if isinstance(item, dict)}
    candidates: dict[str, tuple[Path, dict[str, Any]]] = {}
    for path in paths:
        if path.is_file() and path.name in configs:
            candidates[path.resolve().as_posix()] = (path, configs[path.name])
        elif path.is_dir():
            for file_name, config in configs.items():
                candidate = path / file_name
                if candidate.is_file():
                    candidates[candidate.resolve().as_posix()] = (candidate, config)

    record_count = 0
    fingerprint_parts: list[str] = []
    observed_kind_ids: list[str] = []
    for _, (path, config) in sorted(candidates.items()):
        summary = _jsonl_summary(path, list(config.get("identity_fields") or []))
        record_count += int(summary["count"])
        observed_kind_ids.append(str(config["kind_id"]))
        fingerprint_parts.append(
            f"{config['kind_id']}:{summary['count']}:{summary.get('identity_digest') or file_digest(path) or 'none'}"
        )
    return {
        "artifact_fingerprint": stable_digest(fingerprint_parts)[:32] if fingerprint_parts else None,
        "artifact_record_count": record_count,
        "observed_kind_ids": sorted(set(observed_kind_ids)),
    }


def _configured_counts(value: dict[str, Any], policy: dict[str, Any] | None) -> dict[str, int]:
    aliases = _artifact_policy(policy).get("count_fields") or {}
    counts_mapping = first_mapping(
        value,
        ("output_delta.counts", "counts", "validation_summary", "implementation_summary.output_counts"),
    )
    counts: dict[str, int] = {}
    for metric_id, candidates in aliases.items():
        for candidate in candidates:
            count = number_value(counts_mapping.get(candidate))
            if count is not None:
                counts[str(metric_id)] = count
                break
    return counts


def terminal_record_like(value: dict[str, Any]) -> bool:
    if boolish(value.get("legitimate_terminal_blocker")) or boolish(value.get("terminal_blocker")):
        return True
    status = first_value(
        value,
        ("output_delta_status", "output_delta.status", "validation_verdict", "completion_status", "result_status"),
    )
    if isinstance(status, str) and any(
        token in status.lower() for token in ("terminal", "fail_closed", "fail-closed", "blocked")
    ):
        return True
    failure = provider_failure_class(value)
    request_count = number_value(
        first_value(value, ("provider_request_count", "failure_autopsy.provider_request_count", "result.provider_request_count"))
    )
    return bool(failure and request_count)


def _explicit_observation(value: dict[str, Any]) -> dict[str, Any]:
    observed = first_mapping(
        value,
        (
            "observed_output",
            "output_observation",
            "output_delta.observed_output",
            "output_delta_gate.observed_output",
        ),
    )
    raw_class = str(observed.get("observed_output_class") or "").strip().lower()
    if not raw_class:
        return {}
    compatibility_classes = {
        "semantic_delta": "material_delta",
        "changed_semantic_output": "material_delta",
        "primary_output_delta": "material_delta",
    }
    output_class = compatibility_classes.get(raw_class, raw_class)
    if output_class not in {"material_delta", "metadata_only", "terminal_record", "not_evaluated"}:
        output_class = "not_evaluated"
    return {
        "observed_output_class": output_class,
        "observed_output_reason": str(observed.get("observed_output_reason") or "explicit_observation"),
        "artifact_fingerprint": observed.get("artifact_fingerprint"),
        "artifact_count_fingerprint": observed.get("artifact_count_fingerprint"),
        "artifact_record_count": number_value(observed.get("artifact_record_count")) or 0,
        "record_counts": observed.get("record_counts") if isinstance(observed.get("record_counts"), dict) else {},
        "evaluation_status": "not_evaluated" if output_class == "not_evaluated" else "evaluated",
    }


def observed_output_class(
    root: Path,
    value: dict[str, Any],
    previous: dict[str, Any] | None = None,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    explicit = _explicit_observation(value)
    if explicit:
        return explicit
    artifact = _artifact_policy(policy)
    if not artifact.get("path_fields") or not artifact.get("file_kinds"):
        return {
            "observed_output_class": "not_evaluated",
            "observed_output_reason": "artifact_policy_not_supplied",
            "artifact_fingerprint": None,
            "artifact_count_fingerprint": None,
            "artifact_record_count": 0,
            "record_counts": {},
            "evaluation_status": "not_evaluated",
        }

    paths = output_candidate_paths(root, value, policy)
    summary = _configured_artifact_summary(paths, policy)
    counts = _configured_counts(value, policy)
    count_fingerprint = stable_digest([f"{key}:{counts[key]}" for key in sorted(counts)])[:32] if counts else None
    previous_fingerprint = (previous or {}).get("artifact_fingerprint")
    previous_count_fingerprint = (previous or {}).get("artifact_count_fingerprint")
    material_count = summary["artifact_record_count"] or sum(counts.values())
    output_class = "not_evaluated"
    reason = "no_observable_output_artifact"
    if material_count > 0:
        unchanged = bool(
            (summary["artifact_fingerprint"] and previous_fingerprint == summary["artifact_fingerprint"])
            or (count_fingerprint and previous_count_fingerprint == count_fingerprint)
        )
        output_class = "metadata_only" if unchanged else "material_delta"
        reason = "artifact_observation_unchanged" if unchanged else "artifact_observation_changed"
    elif paths:
        output_class = "terminal_record" if terminal_record_like(value) else "metadata_only"
        reason = "configured_artifacts_without_material_records"
    elif terminal_record_like(value):
        output_class = "terminal_record"
        reason = "terminal_record_observed"
    return {
        "observed_output_class": output_class,
        "observed_output_reason": reason,
        "artifact_fingerprint": summary["artifact_fingerprint"],
        "artifact_count_fingerprint": count_fingerprint,
        "artifact_record_count": material_count,
        "record_counts": counts,
        "observed_kind_ids": summary["observed_kind_ids"],
        "evaluation_status": "not_evaluated" if output_class == "not_evaluated" else "evaluated",
    }
