"""Compile task-index prevalidation into one rederivable CAS owner result."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from .audit_snapshot import (
    audit_input_manifest,
    audit_with_snapshot,
    read_bounded_regular,
)
from .transition_plan_contract import (
    canonical_bytes,
    publish_immutable,
    sha256_bytes,
)
from .transition_publication import ensure_owned_transition_directory


COMPILER_ID = "task_index.prevalidate.owner.v3"
MAX_RESULT_BYTES = 256 * 1024
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
_FIELDS = {
    "schema_version",
    "artifact_kind",
    "compiler_id",
    "audited_at",
    "index_snapshot",
    "result",
    "result_sha256",
}
_BINDING_FIELDS = {"ref", "sha256", "size_bytes"}


def _timestamp(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("Task-index prevalidation requires an explicit timestamp")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            "Task-index prevalidation timestamp must be RFC3339"
        ) from exc
    if parsed.tzinfo is None:
        raise ValueError(
            "Task-index prevalidation timestamp must include a timezone"
        )
    return parsed.isoformat()


def _manifest_file_binding(
    manifest: dict[str, Any], ref: str
) -> dict[str, str] | None:
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        raise ValueError("Task-index audit input manifest entries are invalid")
    matching = [
        entry
        for entry in entries
        if isinstance(entry, dict) and entry.get("ref") == ref
    ]
    if len(matching) != 1:
        raise ValueError(f"Task-index audit manifest does not bind {ref}")
    entry = matching[0]
    if entry.get("kind") == "absent":
        return None
    if (
        set(entry) != {"ref", "kind", "size_bytes", "sha256"}
        or entry.get("kind") != "regular"
    ):
        raise ValueError(f"Task-index audit manifest entry is invalid: {ref}")
    return {"ref": ref, "sha256": str(entry["sha256"])}


def _projection(
    root: Path, audited_at: str
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], bytes]:
    manifest, audit = audit_with_snapshot(root, audited_at=audited_at)
    manifest_payload = canonical_bytes(manifest) + b"\n"
    if len(manifest_payload) > MAX_MANIFEST_BYTES:
        raise ValueError("Task-index audit input manifest exceeds its byte budget")
    manifest_digest = sha256_bytes(manifest_payload)
    manifest_binding = {
        "ref": (
            ".task/index_prevalidation/"
            f"input-manifest-{manifest_digest}.json"
        ),
        "sha256": manifest_digest,
        "size_bytes": len(manifest_payload),
    }
    blockers = [
        {
            key: item[key]
            for key in ("severity", "code", "message", "ids", "paths")
            if key in item
        }
        for item in audit["current_surface_blockers"]
    ]
    evaluated = (
        audit["audit_evidence_status"] == "evaluated"
        and audit["current_projection_status"] == "evaluated"
    )
    index_status = (
        "blocked"
        if blockers
        else "pass"
        if evaluated
        else "not_evaluated"
    )
    snapshot = {
        "schema_version": 1,
        "audit_input_manifest": manifest_binding,
        "audit_input_root_sha256": manifest["root_sha256"],
        "audit_input_entry_count": manifest["entry_count"],
        "audit_input_total_bytes": manifest["total_bytes"],
        "ledger": _manifest_file_binding(manifest, ".task/index.jsonl"),
        "projection": _manifest_file_binding(manifest, ".task/index.md"),
    }
    snapshot_id = "task-index-snapshot-" + sha256_bytes(
        canonical_bytes(snapshot)
    )[:24]
    evidence_paths = [
        ref
        for ref in (
            ".task/index.jsonl" if snapshot["ledger"] else None,
            ".task/index.md" if snapshot["projection"] else None,
            "task.md"
            if _manifest_file_binding(manifest, "task.md")
            else None,
            manifest_binding["ref"],
        )
        if ref is not None
    ]
    result = {
        "index_status": index_status,
        "index_snapshot_id": snapshot_id,
        "blockers": blockers,
        "evidence_paths": evidence_paths,
        "audit_observation_scope": "immutable_bounded_input_snapshot",
        "live_revalidation_required": True,
    }
    return snapshot, result, manifest, manifest_payload


def _compiled(
    root: Path, at: str
) -> tuple[dict[str, Any], dict[str, Any], bytes]:
    audited_at = _timestamp(at)
    snapshot, result, manifest, manifest_payload = _projection(root, audited_at)
    return {
        "schema_version": 2,
        "artifact_kind": "task_state_index_prevalidation_result",
        "compiler_id": COMPILER_ID,
        "audited_at": audited_at,
        "index_snapshot": snapshot,
        "result": result,
        "result_sha256": sha256_bytes(canonical_bytes(result)),
    }, manifest, manifest_payload


def _validate_compiled_snapshot(
    value: dict[str, Any],
    manifest: dict[str, Any],
    manifest_payload: bytes,
) -> None:
    snapshot = value.get("index_snapshot")
    result = value.get("result")
    if not isinstance(snapshot, dict) or not isinstance(result, dict):
        raise ValueError("Task-index compiled audit projection is malformed")
    manifest_digest = sha256_bytes(manifest_payload)
    expected_manifest_binding = {
        "ref": (
            ".task/index_prevalidation/"
            f"input-manifest-{manifest_digest}.json"
        ),
        "sha256": manifest_digest,
        "size_bytes": len(manifest_payload),
    }
    if (
        manifest_payload != canonical_bytes(manifest) + b"\n"
        or snapshot.get("audit_input_manifest")
        != expected_manifest_binding
        or snapshot.get("audit_input_root_sha256")
        != manifest.get("root_sha256")
        or snapshot.get("audit_input_entry_count")
        != manifest.get("entry_count")
        or snapshot.get("audit_input_total_bytes")
        != manifest.get("total_bytes")
        or snapshot.get("ledger")
        != _manifest_file_binding(manifest, ".task/index.jsonl")
        or snapshot.get("projection")
        != _manifest_file_binding(manifest, ".task/index.md")
        or result.get("index_snapshot_id")
        != "task-index-snapshot-"
        + sha256_bytes(canonical_bytes(snapshot))[:24]
        or value.get("result_sha256")
        != sha256_bytes(canonical_bytes(result))
    ):
        raise ValueError(
            "Task-index result differs from its captured audit manifest"
        )


def _publish_compiled(
    root: Path,
    value: dict[str, Any],
    manifest: dict[str, Any],
    manifest_payload: bytes,
    *,
    publish: bool,
) -> tuple[dict[str, Any], bool]:
    _validate_compiled_snapshot(value, manifest, manifest_payload)
    payload = canonical_bytes(value) + b"\n"
    if len(payload) > MAX_RESULT_BYTES:
        raise ValueError("Task-index prevalidation result exceeds its byte budget")
    digest = sha256_bytes(payload)
    binding = {
        "ref": f".task/index_prevalidation/{digest}.json",
        "sha256": digest,
        "size_bytes": len(payload),
    }
    if not publish:
        return binding, False
    if audit_input_manifest(root) != manifest:
        raise ValueError(
            "Task-index audit inputs changed before result publication"
        )
    ensure_owned_transition_directory(root, "index_prevalidation")
    manifest_ref = value["index_snapshot"]["audit_input_manifest"]["ref"]
    publish_immutable(root / manifest_ref, manifest_payload)
    created = publish_immutable(root / binding["ref"], payload)
    return binding, created


def audit_projection(
    root: Path, *, at: str, publish: bool = False
) -> dict[str, Any]:
    """Return one snapshot-bound post-audit projection and optional CAS binding."""

    root = root.resolve()
    value, manifest, manifest_payload = _compiled(root, at)
    binding, _created = _publish_compiled(
        root, value, manifest, manifest_payload, publish=publish
    )
    return {
        "index_snapshot": value["index_snapshot"],
        "result": value["result"],
        "owner_result_binding": binding,
    }


def compile_prevalidation(
    root: Path,
    *,
    at: str,
    publish: bool = True,
) -> dict[str, Any]:
    root = root.resolve()
    value, manifest, manifest_payload = _compiled(root, at)
    binding, created = _publish_compiled(
        root, value, manifest, manifest_payload, publish=publish
    )
    return {
        "schema_version": 1,
        "result_kind": "task_state_index_prevalidation_compile_result",
        "status": "published" if publish else "dry_run",
        "owner_result_binding": binding,
        "mutation_performed": created,
        "duplicate": publish and not created,
        "model_authored_mechanical_bytes": 0,
    }


def _validate_prevalidation_source(
    root: Path,
    value: Any,
    *,
    source_ref: str,
    source_payload: bytes,
) -> dict[str, Any]:
    root = root.resolve(strict=True)
    if (
        not isinstance(value, dict)
        or set(value) != _FIELDS
        or value.get("schema_version") != 2
        or value.get("artifact_kind")
        != "task_state_index_prevalidation_result"
        or value.get("compiler_id") != COMPILER_ID
    ):
        raise ValueError("Task-index prevalidation envelope is not closed")
    payload = canonical_bytes(value) + b"\n"
    digest = sha256_bytes(payload)
    if source_ref != f".task/index_prevalidation/{digest}.json":
        raise ValueError(
            "Task-index prevalidation ref is not its producer CAS path"
        )
    if source_payload != payload or sha256_bytes(source_payload) != digest:
        raise ValueError(
            "Task-index prevalidation source is not canonical producer CAS bytes"
        )
    snapshot = value.get("index_snapshot")
    manifest_binding = (
        snapshot.get("audit_input_manifest")
        if isinstance(snapshot, dict)
        else None
    )
    if (
        not isinstance(manifest_binding, dict)
        or set(manifest_binding) != {"ref", "sha256", "size_bytes"}
    ):
        raise ValueError("Task-index prevalidation lacks its audit input manifest")
    manifest_digest = manifest_binding.get("sha256")
    manifest_size = manifest_binding.get("size_bytes")
    if (
        not isinstance(manifest_digest, str)
        or len(manifest_digest) != 64
        or any(
            character not in "0123456789abcdef"
            for character in manifest_digest
        )
        or not isinstance(manifest_size, int)
        or isinstance(manifest_size, bool)
        or manifest_size < 1
        or manifest_size > MAX_MANIFEST_BYTES
        or manifest_binding.get("ref")
        != (
            ".task/index_prevalidation/"
            f"input-manifest-{manifest_digest}.json"
        )
    ):
        raise ValueError("Task-index audit input manifest binding is invalid")
    manifest_payload = read_bounded_regular(
        root,
        manifest_binding["ref"],
        max_bytes=MAX_MANIFEST_BYTES,
    )
    if (
        len(manifest_payload) != manifest_binding["size_bytes"]
        or sha256_bytes(manifest_payload) != manifest_binding["sha256"]
    ):
        raise ValueError("Task-index audit input manifest binding differs")
    expected, expected_manifest, expected_manifest_payload = _compiled(
        root, str(value.get("audited_at") or "")
    )
    if (
        manifest_payload != expected_manifest_payload
        or manifest_payload != canonical_bytes(expected_manifest) + b"\n"
    ):
        raise ValueError(
            "Task-index audit input manifest differs from current audit inputs"
        )
    if value != expected:
        raise ValueError(
            "Task-index prevalidation differs from current deterministic audit"
        )
    return expected


def validate_prevalidation(
    root: Path,
    value: Any,
    *,
    source_ref: str,
) -> dict[str, Any]:
    """Revalidate one already-decoded producer artifact against live inputs."""

    source_payload = read_bounded_regular(
        root.resolve(strict=True),
        source_ref,
        max_bytes=MAX_RESULT_BYTES,
    )
    return _validate_prevalidation_source(
        root,
        value,
        source_ref=source_ref,
        source_payload=source_payload,
    )


def validate_prevalidation_binding(
    root: Path,
    binding: Any,
) -> dict[str, Any]:
    """Boundedly reopen one exact producer binding and rederive its live audit."""

    if not isinstance(binding, dict) or set(binding) != _BINDING_FIELDS:
        raise ValueError(
            "Task-index prevalidation binding must contain exact "
            "ref, sha256, and size_bytes"
        )
    ref = binding.get("ref")
    digest = binding.get("sha256")
    size_bytes = binding.get("size_bytes")
    if (
        not isinstance(ref, str)
        or not ref
        or not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
        or not isinstance(size_bytes, int)
        or isinstance(size_bytes, bool)
        or size_bytes < 1
        or size_bytes > MAX_RESULT_BYTES
        or ref != f".task/index_prevalidation/{digest}.json"
    ):
        raise ValueError("Task-index prevalidation binding values are invalid")
    root = root.resolve(strict=True)
    source_payload = read_bounded_regular(
        root,
        ref,
        max_bytes=MAX_RESULT_BYTES,
    )
    if (
        len(source_payload) != size_bytes
        or sha256_bytes(source_payload) != digest
    ):
        raise ValueError("Task-index prevalidation binding differs from source")
    try:
        value = json.loads(source_payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            "Task-index prevalidation binding is not valid UTF-8 JSON"
        ) from exc
    if (
        not isinstance(value, dict)
        or source_payload != canonical_bytes(value) + b"\n"
    ):
        raise ValueError(
            "Task-index prevalidation binding is not canonical producer JSON"
        )
    verified = _validate_prevalidation_source(
        root,
        value,
        source_ref=ref,
        source_payload=source_payload,
    )
    return {
        "owner_result_binding": {
            "ref": ref,
            "sha256": digest,
            "size_bytes": size_bytes,
        },
        "artifact": verified,
        "index_snapshot": verified["index_snapshot"],
        "result": verified["result"],
    }


__all__ = (
    "COMPILER_ID",
    "audit_projection",
    "compile_prevalidation",
    "validate_prevalidation",
    "validate_prevalidation_binding",
)
