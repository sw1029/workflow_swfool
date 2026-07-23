"""Hydrate compact compiled-stage ledger rows from their exact CAS result."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .constants import COMPILED_STAGE_RESULT_EVENT_KIND, MIN_FIELDS
from .support import canonical_json_bytes, normalize_list


COMPACT_RESULT_EVENT_KIND = COMPILED_STAGE_RESULT_EVENT_KIND
SHA256 = re.compile(r"^[0-9a-f]{64}$")
MAX_RESULT_BYTES = 16 * 1024 * 1024
COMPACT_COMPILER_METRIC_FIELDS = {
    "context_section_count",
    "target_context_bytes",
    "files_opened_count",
    "files_written_count",
    "executor_kind",
    "model_call_required",
    "semantic_field_count",
    "owner_field_count",
    "context_bytes",
    "work_order_bytes",
    "machine_input_bytes",
    "preparation_bytes",
    "owner_result_bytes",
    "semantic_bytes",
    "raw_bytes_read",
    "result_bytes",
    "compact_payload_bytes",
    "cas_newly_written_bytes",
    "cas_reused_bytes",
    "model_visible_bytes",
    "model_call_count",
    "model_authored_mechanical_bytes",
    "model_authored_mechanical_bytes_origin",
    "inline_payload_bytes",
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "provider_id",
    "runtime_id",
    "model_id",
    "request_id",
    "usage_aggregate_eligible",
    "usage_provenance_status",
    "usage_receipt_ref",
    "usage_receipt_sha256",
    "usage_receipt_schema_version",
    "precondition_validation_status",
    "post_effect_changed_selector_count",
    "post_effect_changed_selectors_sha256",
}
_RESULT_SCALARS = {
    "task_id",
    "completed_task_id",
    "next_task_id",
    "validation_verdict",
    "progress_verdict",
    "review_status",
    "quality_verdict",
    "selection_outcome",
    "index_status",
    "audit_observation_scope",
    "live_revalidation_required",
    "commit_status",
    "completion_status",
}
_COMPACT_FIELDS = set(MIN_FIELDS) | _RESULT_SCALARS | {
    "event_kind",
    "preparation_id",
    "preparation_binding_sha256",
    "input_bindings_sha256",
    "deterministic_commit_binding",
    "result_artifact_ref",
    "result_artifact_sha256",
    "result_artifact_raw_sha256",
    "result_artifact_binding",
    "result_projection",
    "compiler_metrics",
    "producer_kind",
    "request_fingerprint",
    "ledger_sequence",
    "source_status",
}
_LEDGER_OWNED_FIELDS = {
    "format_version",
    "cycle_id",
    "event_id",
    "step",
    "status",
    "reason",
    "created_at",
    "ledger_sequence",
    "source_status",
    "event_kind",
    "preparation_id",
    "preparation_binding_sha256",
    "input_bindings_sha256",
    "deterministic_commit_binding",
    "result_artifact_ref",
    "result_artifact_sha256",
    "result_artifact_raw_sha256",
    "result_artifact_binding",
    "result_projection",
    "compiler_metrics",
    "producer_kind",
    "request_fingerprint",
}


def is_compact_result_event(event: dict[str, Any]) -> bool:
    return event.get("format_version") == 2 and event.get(
        "event_kind"
    ) == COMPACT_RESULT_EVENT_KIND


def _bounded_scalar(value: Any, maximum: int = 512) -> bool:
    return (
        value is None
        or isinstance(value, (bool, int, float))
        or isinstance(value, str)
        and len(value.encode("utf-8")) <= maximum
    )


def project_result_scalars(result: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in result.items()
        if key in _RESULT_SCALARS and _bounded_scalar(value, 256)
    }


def validate_compact_result_envelope(
    event: dict[str, Any], cycle_id: str | None = None
) -> dict[str, Any]:
    if event.get("format_version") != 2:
        if event.get("event_kind") == COMPACT_RESULT_EVENT_KIND:
            raise ValueError("compact stage result requires ledger format_version 2")
        return event
    if event.get("event_kind") != COMPACT_RESULT_EVENT_KIND:
        raise ValueError("ledger format_version 2 is reserved for compact stage results")
    if set(event) - _COMPACT_FIELDS:
        raise ValueError("compact stage result has unsupported fields")
    binding = event.get("result_artifact_binding")
    if not isinstance(binding, dict) or set(binding) != {
        "ref",
        "sha256",
        "size_bytes",
        "body_sha256",
    }:
        raise ValueError("compact stage result binding is invalid")
    ref, raw_sha256 = binding.get("ref"), binding.get("sha256")
    body_sha256, size_bytes = binding.get("body_sha256"), binding.get("size_bytes")
    relative = Path(str(ref or ""))
    expected_prefix = (".task", "cycle", str(cycle_id or event.get("cycle_id") or ""), "packets")
    if (
        not isinstance(ref, str)
        or "\\" in ref
        or "\x00" in ref
        or relative.as_posix() != ref
        or relative.is_absolute()
        or ".." in relative.parts
        or tuple(relative.parts)
        != (
            *expected_prefix,
            f"result-{event.get('step')}-{body_sha256}.json",
        )
        or not SHA256.fullmatch(str(raw_sha256 or ""))
        or not SHA256.fullmatch(str(body_sha256 or ""))
        or isinstance(size_bytes, bool)
        or not isinstance(size_bytes, int)
        or size_bytes < 1
        or size_bytes > MAX_RESULT_BYTES
    ):
        raise ValueError("compact stage result binding fields are invalid")
    if (
        event.get("result_artifact_ref") != ref
        or event.get("result_artifact_sha256") != body_sha256
        or event.get("result_artifact_raw_sha256") != raw_sha256
        or event.get("artifacts") != [ref]
        or not SHA256.fullmatch(str(event.get("preparation_binding_sha256") or ""))
        or not SHA256.fullmatch(str(event.get("input_bindings_sha256") or ""))
        or not isinstance(event.get("preparation_id"), str)
    ):
        raise ValueError("compact stage result compatibility binding mismatch")
    commit = event.get("deterministic_commit_binding")
    if commit is not None:
        commit_ref = commit.get("ref") if isinstance(commit, dict) else None
        commit_sha = (
            commit.get("sha256") if isinstance(commit, dict) else None
        )
        commit_size = (
            commit.get("size_bytes") if isinstance(commit, dict) else None
        )
        expected_commit = (
            Path(".task")
            / "cycle"
            / str(cycle_id or event.get("cycle_id") or "")
            / "compiler"
            / "deterministic_commit_receipt"
            / "sha256"
            / f"{commit_sha}.json"
        ).as_posix()
        if (
            not isinstance(commit, dict)
            or set(commit) != {"ref", "sha256", "size_bytes"}
            or commit_ref != expected_commit
            or not SHA256.fullmatch(str(commit_sha or ""))
            or isinstance(commit_size, bool)
            or not isinstance(commit_size, int)
            or commit_size < 1
            or commit_size > 64 * 1024
        ):
            raise ValueError(
                "compact deterministic commit binding is invalid"
            )
    projection = event.get("result_projection")
    metrics = event.get("compiler_metrics")
    if (
        not isinstance(projection, dict)
        or set(projection) - _RESULT_SCALARS
        or any(not _bounded_scalar(item, 256) for item in projection.values())
        or not isinstance(metrics, dict)
        or set(metrics) - COMPACT_COMPILER_METRIC_FIELDS
        or any(not _bounded_scalar(item) for item in metrics.values())
    ):
        raise ValueError("compact stage result projection or metrics are invalid")
    return event


def _safe_result_path(root: Path, cycle_id: str, ref: str) -> Path:
    root = root.expanduser().resolve(strict=True)
    relative = Path(ref)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise ValueError("compact stage result ref must be workspace-relative")
    candidate = root
    for part in relative.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise ValueError("compact stage result ref must not traverse symlinks")
    try:
        path = candidate.resolve(strict=True)
        path.relative_to(root)
    except (FileNotFoundError, ValueError) as exc:
        raise ValueError("compact stage result ref is missing or escapes workspace") from exc
    expected_parent = (root / ".task" / "cycle" / cycle_id / "packets").resolve(
        strict=True
    )
    if path.parent != expected_parent or not path.is_file():
        raise ValueError("compact stage result ref is outside the cycle packet CAS")
    return path


def hydrate_result_event(
    root: Path, cycle_id: str, event: dict[str, Any]
) -> dict[str, Any]:
    if not is_compact_result_event(event):
        return event
    validate_compact_result_envelope(event, cycle_id)
    binding = event["result_artifact_binding"]
    ref = binding.get("ref")
    raw_sha256 = binding.get("sha256")
    body_sha256 = binding.get("body_sha256")
    size_bytes = binding.get("size_bytes")
    path = _safe_result_path(root, cycle_id, ref)
    if path.stat().st_size != size_bytes:
        raise ValueError("compact stage result size binding mismatch")
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != raw_sha256:
        raise ValueError("compact stage result raw digest mismatch")
    try:
        result = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("compact stage result is not valid UTF-8 JSON") from exc
    if not isinstance(result, dict) or payload != canonical_json_bytes(result) + b"\n":
        raise ValueError("compact stage result is not canonical JSON")
    if hashlib.sha256(canonical_json_bytes(result)).hexdigest() != body_sha256:
        raise ValueError("compact stage result body digest mismatch")
    expected_projection = project_result_scalars(result)
    if event.get("result_projection") != expected_projection:
        raise ValueError("compact stage result scalar projection mismatch")
    if any(event.get(key) != value for key, value in expected_projection.items()):
        raise ValueError("compact stage result promoted scalar mismatch")
    if any(
        key not in expected_projection and event.get(key) is not None
        for key in _RESULT_SCALARS
    ):
        raise ValueError("compact stage result has an unbound promoted scalar")
    if "step" in result and result.get("step") != event.get("step"):
        raise ValueError("compact stage result body step does not match envelope")
    if "cycle_id" in result and result.get("cycle_id") != cycle_id:
        raise ValueError("compact stage result body cycle_id does not match envelope")
    hydrated = dict(event)
    hydrated.update(result)
    for key in _LEDGER_OWNED_FIELDS:
        if key in event:
            hydrated[key] = event[key]
    hydrated["artifacts"] = normalize_list(result.get("artifacts"), ref)
    hydrated["hydrated_from_compact_result"] = True
    return hydrated


__all__ = [
    "COMPACT_COMPILER_METRIC_FIELDS",
    "COMPACT_RESULT_EVENT_KIND",
    "hydrate_result_event",
    "is_compact_result_event",
    "project_result_scalars",
    "validate_compact_result_envelope",
]
