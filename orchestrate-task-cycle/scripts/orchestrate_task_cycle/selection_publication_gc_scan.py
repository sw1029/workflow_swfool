"""Bounded mark phase and immutable plan contract for selection GC."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any

from .selection_publication_gc_contract import (
    CAS_LAYOUTS,
    GC_SCHEMA_VERSION,
    MAX_CANDIDATE_BYTES,
    MAX_CANDIDATE_COUNT,
    MAX_SCAN_BYTES,
    MAX_SCAN_FILE_BYTES,
    MAX_SCAN_FILES,
    REFERENCE_PATTERN,
    plan_path,
)
from .selection_publication_gc_fs import (
    artifact_binding,
    MissingArtifactParent,
    read_relative,
    read_json_relative,
    write_once_relative,
)
from .selection_publication_gc_walk import (
    read_pinned_walk_file,
    walk_regular_files_fd,
)
from .selection_publication_reference_barrier import (
    MAX_REFERENCE_BARRIER_BYTES,
    REFERENCE_BARRIER_REF,
    reference_barrier_binding,
    validate_reference_barrier_payload,
)
from .selection_publication_state import STORAGE_SCHEMA_VERSION, load_state
from .selection_publication_producer_capability import (
    _SELECTION_PUBLICATION_PRODUCER_CAPABILITY,
)
from .selection_publication_store import (
    _canonical_json,
    _lock,
    _sha256_bytes,
)


def _cas_files(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for parts in CAS_LAYOUTS:
        relative = Path(".task", "selection_publication", *parts).as_posix()
        try:
            files = walk_regular_files_fd(root, start=relative, recursive=False)
            for value in files:
                payload = read_pinned_walk_file(
                    value,
                    "selection-publication CAS inventory leaf",
                    max_bytes=MAX_CANDIDATE_BYTES,
                )
                digest = _sha256_bytes(payload)
                if value.name != digest:
                    raise ValueError(
                        "selection-publication CAS leaf name differs from bytes"
                    )
                rows.append(
                    {
                        "ref": value.ref,
                        "sha256": digest,
                        "size_bytes": len(payload),
                    }
                )
        except MissingArtifactParent:
            continue
    unique = sorted(rows, key=lambda row: str(row["ref"]))
    if len({str(row["ref"]) for row in unique}) != len(unique):
        raise ValueError("selection-publication CAS inventory contains duplicates")
    if len(unique) > MAX_CANDIDATE_COUNT:
        raise ValueError("selection-publication CAS inventory exceeds gc bound")
    return unique


def _json_string_refs(value: Any, candidates: set[str]) -> set[str]:
    referenced: set[str] = set()
    stack = [value]
    visited = 0
    while stack:
        visited += 1
        if visited > MAX_SCAN_FILES:
            raise ValueError("retention JSON traversal exceeds node bound")
        current = stack.pop()
        if isinstance(current, str):
            referenced.update(ref for ref in candidates if ref in current)
        elif isinstance(current, list):
            stack.extend(current)
        elif isinstance(current, dict):
            stack.extend(current.keys())
            stack.extend(current.values())
    return referenced


def _decoded_json_refs(ref: str, payload: bytes, candidates: set[str]) -> set[str]:
    suffix = Path(ref).suffix.lower()
    if suffix not in {".json", ".jsonl"}:
        return set()
    try:
        text = payload.decode("utf-8")
        values = (
            [json.loads(text)]
            if suffix == ".json"
            else [json.loads(line) for line in text.splitlines() if line.strip()]
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError(f"retention JSON reference scan failed closed: {ref}") from exc
    result: set[str] = set()
    for value in values:
        result.update(_json_string_refs(value, candidates))
    return result


def referenced_paths(root: Path, candidates: set[str]) -> tuple[set[str], int]:
    if not candidates:
        return set(), 0
    referenced: set[str] = set()
    scanned = 0
    values = walk_regular_files_fd(
        root,
        skip_prefixes=(
            (".git",),
            (".task", "selection_publication", "gc"),
        ),
    )
    for files, value in enumerate(values, start=1):
        if files > MAX_SCAN_FILES:
            raise ValueError("retention reference scan exceeds file-count bound")
        size = value.metadata.st_size
        if size > MAX_SCAN_FILE_BYTES:
            raise ValueError(
                f"retention reference scan file exceeds bound: {value.ref}"
            )
        scanned += size
        if scanned > MAX_SCAN_BYTES:
            raise ValueError("retention reference scan exceeds byte bound")
        payload = read_pinned_walk_file(
            value,
            f"retention reference scan file {value.ref}",
            max_bytes=MAX_SCAN_FILE_BYTES,
        )
        for match in REFERENCE_PATTERN.finditer(payload):
            ref = match.group().decode("utf-8", errors="strict")
            if ref in candidates:
                referenced.add(ref)
        referenced.update(_decoded_json_refs(value.ref, payload, candidates))
        if referenced == candidates:
            break
    return referenced, scanned


def workspace_reference_epoch(root: Path) -> dict[str, Any]:
    """Fingerprint one bounded, fd-pinned workspace snapshot for adoption."""

    digest = hashlib.sha256()
    scanned = 0
    count = 0
    values = walk_regular_files_fd(
        root,
        skip_prefixes=(
            (".git",),
            (".task", "selection_publication", "gc"),
        ),
    )
    for count, value in enumerate(values, start=1):
        if count > MAX_SCAN_FILES:
            raise ValueError("reference barrier adoption exceeds file-count bound")
        size = value.metadata.st_size
        if size > MAX_SCAN_FILE_BYTES:
            raise ValueError(
                f"reference barrier adoption file exceeds bound: {value.ref}"
            )
        scanned += size
        if scanned > MAX_SCAN_BYTES:
            raise ValueError("reference barrier adoption exceeds workspace byte bound")
        payload = read_pinned_walk_file(
            value,
            f"reference barrier adoption file {value.ref}",
            max_bytes=MAX_SCAN_FILE_BYTES,
        )
        row = {
            "ref": value.ref,
            "sha256": _sha256_bytes(payload),
            "size_bytes": len(payload),
        }
        digest.update(_canonical_json(row))
    return {
        "workspace_epoch_sha256": digest.hexdigest(),
        "workspace_file_count": count,
        "workspace_bytes": scanned,
    }


def validate_quiescent_state(
    root: Path,
) -> tuple[dict[str, Any], dict[str, str]]:
    state = load_state(root)
    if state is None:
        raise ValueError(
            "selection publication storage v4 is required before retention gc"
        )
    if state.get("active_transaction") is not None:
        raise ValueError(
            "selection publication retention gc requires no active transaction"
        )
    state_ref = ".task/selection_publication/state.json"
    observed, payload = read_json_relative(
        root, state_ref, "selection publication compact state"
    )
    if observed != state or payload != _canonical_json(state):
        raise ValueError("selection publication compact state changed during gc")
    return state, artifact_binding(root, state_ref)


def _plan_body(
    state_binding: dict[str, str],
    reference_barrier: dict[str, str] | None,
    candidates: list[dict[str, Any]],
    *,
    scanned_bytes: int,
    cas_file_count: int,
    retained_ref_count: int,
) -> dict[str, Any]:
    return {
        "schema_version": GC_SCHEMA_VERSION,
        "storage_schema_version": STORAGE_SCHEMA_VERSION,
        "kind": "selection_publication_gc_plan",
        "state": state_binding,
        "reference_barrier": reference_barrier,
        "candidate_rule": "unreferenced_selection_publication_cas_only",
        "candidates": candidates,
        "scan_metrics": {
            "repository_bytes_scanned": scanned_bytes,
            "cas_file_count": cas_file_count,
            "retained_reference_count": retained_ref_count,
            "candidate_count": len(candidates),
            "candidate_bytes": sum(int(row["size_bytes"]) for row in candidates),
        },
        "restore_supported": True,
    }


def plan_gc(root: Path) -> dict[str, Any]:
    root = root.expanduser().resolve(strict=True)
    with _lock(
        root,
        producer_capability=_SELECTION_PUBLICATION_PRODUCER_CAPABILITY,
    ):
        _state, state_binding = validate_quiescent_state(root)
        barrier_binding = current_reference_barrier(root, required=True)
        paths = _cas_files(root)
        refs = {str(row["ref"]) for row in paths}
        referenced, scanned = referenced_paths(root, refs)
        candidates = _candidate_rows(root, paths, referenced)
        candidate_bytes = sum(int(row["size_bytes"]) for row in candidates)
        if candidate_bytes > MAX_CANDIDATE_BYTES:
            raise ValueError("selection-publication gc candidates exceed byte bound")
        body = _plan_body(
            state_binding,
            barrier_binding,
            candidates,
            scanned_bytes=scanned,
            cas_file_count=len(paths),
            retained_ref_count=len(referenced),
        )
        fingerprint = _sha256_bytes(_canonical_json(body))
        plan_id = f"spgc-{fingerprint}"
        plan = {
            **body,
            "plan_id": plan_id,
            "plan_content_sha256": fingerprint,
        }
        path = plan_path(root, plan_id)
        digest, created = write_once_relative(
            root,
            path.relative_to(root).as_posix(),
            _canonical_json(plan),
            "selection-publication gc plan",
            producer_capability=_SELECTION_PUBLICATION_PRODUCER_CAPABILITY,
        )
    return {
        "schema_version": GC_SCHEMA_VERSION,
        "result_kind": "selection_publication_gc_plan_result",
        "status": "no_candidates" if not candidates else "planned",
        "plan": {"ref": path.relative_to(root).as_posix(), "sha256": digest},
        "plan_id": plan_id,
        "candidate_count": len(candidates),
        "candidate_bytes": candidate_bytes,
        "idempotent_replay": not created,
        "mutation_performed": created,
        "model_authored_mechanical_bytes": 0,
    }


def current_reference_barrier(root: Path, *, required: bool) -> dict[str, str] | None:
    payload = read_relative(
        root,
        REFERENCE_BARRIER_REF,
        "selection-publication reference barrier",
        required=False,
        max_bytes=MAX_REFERENCE_BARRIER_BYTES,
    )
    if payload is None:
        if required:
            raise ValueError(
                "selection-publication gc cannot prove workspace-wide "
                "reference-producer participation"
            )
        return None
    validate_reference_barrier_payload(payload, root=root, require_current=True)
    return reference_barrier_binding(payload)


def validate_plan_reference_barrier(root: Path, plan: dict[str, Any]) -> dict[str, str]:
    expected = plan.get("reference_barrier")
    current = current_reference_barrier(root, required=True)
    if expected != current:
        raise ValueError(
            "selection-publication reference barrier changed after planning"
        )
    assert current is not None
    return current


def _candidate_rows(
    root: Path, paths: list[dict[str, Any]], referenced: set[str]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    _ = root
    for path in paths:
        ref = str(path["ref"])
        if ref in referenced:
            continue
        rows.append(
            {
                "ref": ref,
                "sha256": path["sha256"],
                "size_bytes": path["size_bytes"],
                "reason": "unreferenced_cas",
            }
        )
    return rows


def load_plan(root: Path, plan_id: str) -> tuple[dict[str, Any], Path, str]:
    path = plan_path(root, plan_id)
    relative = path.relative_to(root).as_posix()
    plan, payload = read_json_relative(root, relative, "selection-publication gc plan")
    _validate_plan_header(plan, plan_id, payload)
    _validate_candidate_rows(plan)
    return plan, path, _sha256_bytes(payload)


def _validate_plan_header(plan: dict[str, Any], plan_id: str, payload: bytes) -> None:
    required = {
        "schema_version",
        "storage_schema_version",
        "kind",
        "state",
        "reference_barrier",
        "candidate_rule",
        "candidates",
        "scan_metrics",
        "restore_supported",
        "plan_id",
        "plan_content_sha256",
    }
    if (
        set(plan) != required
        or plan.get("schema_version") != GC_SCHEMA_VERSION
        or plan.get("storage_schema_version") != STORAGE_SCHEMA_VERSION
        or plan.get("kind") != "selection_publication_gc_plan"
        or plan.get("plan_id") != plan_id
    ):
        raise ValueError("selection-publication gc plan contract is invalid")
    body = {
        key: value
        for key, value in plan.items()
        if key not in {"plan_id", "plan_content_sha256"}
    }
    fingerprint = _sha256_bytes(_canonical_json(body))
    if (
        plan.get("plan_content_sha256") != fingerprint
        or plan_id != f"spgc-{fingerprint}"
        or payload != _canonical_json(plan)
    ):
        raise ValueError("selection-publication gc plan integrity failed")


def _validate_candidate_rows(plan: dict[str, Any]) -> None:
    candidates = plan.get("candidates")
    if not isinstance(candidates, list) or len(candidates) > MAX_CANDIDATE_COUNT:
        raise ValueError("selection-publication gc candidates are invalid")
    seen: set[str] = set()
    total = 0
    for row in candidates:
        _validate_candidate_row(row, seen)
        seen.add(row["ref"])
        total += row["size_bytes"]
    if total > MAX_CANDIDATE_BYTES:
        raise ValueError("selection-publication gc plan exceeds byte bound")


def _validate_candidate_row(row: Any, seen: set[str]) -> None:
    if (
        not isinstance(row, dict)
        or set(row) != {"ref", "sha256", "size_bytes", "reason"}
        or row.get("reason") != "unreferenced_cas"
        or not isinstance(row.get("ref"), str)
        or not isinstance(row.get("size_bytes"), int)
        or row["size_bytes"] < 0
        or row["ref"] in seen
        or not re.fullmatch(r"[0-9a-f]{64}", str(row.get("sha256") or ""))
    ):
        raise ValueError("selection-publication gc candidate contract is invalid")
    relative = Path(row["ref"])
    expected = {
        Path(".task", "selection_publication", *parts, row["sha256"])
        for parts in CAS_LAYOUTS
    }
    if (
        relative.is_absolute()
        or relative.as_posix() != row["ref"]
        or ".." in relative.parts
        or relative not in expected
    ):
        raise ValueError("selection-publication gc candidate is not an exact CAS path")


__all__ = (
    "current_reference_barrier",
    "load_plan",
    "plan_gc",
    "referenced_paths",
    "validate_plan_reference_barrier",
    "validate_quiescent_state",
    "workspace_reference_epoch",
)
