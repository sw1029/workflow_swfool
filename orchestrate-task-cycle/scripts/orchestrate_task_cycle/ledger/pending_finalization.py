from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from .candidate_validation import final_candidate_commit_material
from .constants import SHA256_PATTERN, VERDICT_AXES
from .support import (
    canonical_json_bytes,
    canonical_sha256,
    cycle_dir,
    immutable_write_bytes,
    ledger_lock,
    rel_path,
    validate_cycle_id,
    validate_event_id,
)


ImmutableBytesWriter = Callable[[Path, bytes], None]
PENDING_CONFLICT_KIND = "cycle_finalization_pending_conflict"
PENDING_RESOLUTION_KIND = "cycle_finalization_pending_resolution"
PENDING_DISPOSITIONS = {"merged", "retired"}


class FinalizationConflictError(ValueError):
    """CAS conflict that preserved an immutable anti-loop attempt record."""

    def __init__(self, message: str, pending_receipt: dict[str, Any]) -> None:
        super().__init__(message)
        self.pending_receipt = pending_receipt


def pending_finalizations_dir(root: Path, cycle_id: str) -> Path:
    return cycle_dir(root, validate_cycle_id(cycle_id)) / "pending_finalizations"


def pending_resolutions_dir(root: Path, cycle_id: str) -> Path:
    return pending_finalizations_dir(root, cycle_id) / "resolutions"


def _attempt_memory_material(
    cycle_id: str, candidate: dict[str, Any]
) -> dict[str, Any]:
    return {
        "cycle_id": cycle_id,
        "attempt_id": candidate["attempt_id"],
        "verdict_contract_version": candidate["verdict_contract_version"],
        **{axis: candidate[axis] for axis in VERDICT_AXES},
        "durable_state_candidate": candidate["durable_state_candidate"],
    }


def persist_pending_conflict_unlocked(
    root: Path,
    cycle_id: str,
    candidate: dict[str, Any],
    *,
    final_candidate_digest: str,
    actual_previous_revision: int | None,
    actual_previous_attempt_id: str | None,
    actual_previous_token: str | None,
    immutable_writer: ImmutableBytesWriter = immutable_write_bytes,
) -> dict[str, Any]:
    memory_material = _attempt_memory_material(cycle_id, candidate)
    candidate_material = final_candidate_commit_material(candidate)
    record = {
        "schema_version": 1,
        "kind": PENDING_CONFLICT_KIND,
        "cycle_id": cycle_id,
        "attempt_id": candidate["attempt_id"],
        "state_commit_status": "recovery_required",
        "attempt_memory_disposition": "pending_conflict",
        "attempt_memory_digest": canonical_sha256(memory_material),
        "final_candidate_digest": final_candidate_digest,
        "candidate_material": candidate_material,
        "expected_previous_revision": candidate.get("expected_previous_revision"),
        "expected_previous_attempt_id": candidate.get("expected_previous_attempt_id"),
        "expected_previous_finalization_token": candidate.get(
            "expected_previous_finalization_token"
        ),
        "actual_previous_revision": actual_previous_revision,
        "actual_previous_attempt_id": actual_previous_attempt_id,
        "actual_previous_finalization_token": actual_previous_token,
    }
    record_bytes = canonical_json_bytes(record)
    record_sha256 = hashlib.sha256(record_bytes).hexdigest()
    record_path = pending_finalizations_dir(root, cycle_id) / f"{record_sha256}.json"
    immutable_writer(record_path, record_bytes)
    return {
        "schema_version": 1,
        "kind": PENDING_CONFLICT_KIND,
        "cycle_id": cycle_id,
        "attempt_id": candidate["attempt_id"],
        "state_commit_status": "recovery_required",
        "attempt_memory_disposition": "pending_conflict",
        "pending_conflict_id": record_sha256,
        "record_ref": rel_path(root, record_path),
        "record_sha256": record_sha256,
        "attempt_memory_digest": record["attempt_memory_digest"],
    }


def _load_canonical_record(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if path.stem != digest:
        raise ValueError(f"pending finalization object filename/hash mismatch: {path}")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"pending finalization object is malformed: {path}") from exc
    if not isinstance(value, dict) or canonical_json_bytes(value) != raw:
        raise ValueError(f"pending finalization object is not canonical JSON: {path}")
    return value


def _resolution_path(root: Path, cycle_id: str, pending_conflict_id: str) -> Path:
    validate_event_id(pending_conflict_id)
    return pending_resolutions_dir(root, cycle_id) / f"{pending_conflict_id}.json"


def resolve_pending_conflict_unlocked(
    root: Path,
    cycle_id: str,
    pending_conflict_id: str,
    *,
    disposition: str,
    resolution_evidence_id: str,
    resolution_evidence_digest: str,
    resolution_evidence_ref: str,
    resolution_rationale_id: str,
    committed_finalization_token: str | None = None,
    immutable_writer: ImmutableBytesWriter = immutable_write_bytes,
) -> dict[str, Any]:
    if disposition not in PENDING_DISPOSITIONS:
        raise ValueError("pending finalization disposition must be merged or retired")
    validate_event_id(resolution_evidence_id)
    validate_event_id(resolution_evidence_ref)
    validate_event_id(resolution_rationale_id)
    evidence_digest = str(resolution_evidence_digest or "").strip().lower()
    if not SHA256_PATTERN.fullmatch(evidence_digest):
        raise ValueError("pending resolution evidence requires a full SHA-256 digest")
    if disposition == "merged" and (
        not SHA256_PATTERN.fullmatch(str(committed_finalization_token or ""))
        or evidence_digest != committed_finalization_token
    ):
        raise ValueError(
            "merged pending resolution must bind the committed finalization token"
        )
    if disposition == "retired" and committed_finalization_token is not None:
        raise ValueError(
            "retired pending resolution cannot claim a committed finalization token"
        )
    record_path = (
        pending_finalizations_dir(root, cycle_id) / f"{pending_conflict_id}.json"
    )
    if not record_path.is_file():
        raise ValueError("pending finalization conflict does not exist")
    pending = _load_canonical_record(record_path)
    if (
        pending.get("kind") != PENDING_CONFLICT_KIND
        or pending.get("cycle_id") != cycle_id
    ):
        raise ValueError("pending finalization conflict binding is invalid")
    resolution = {
        "schema_version": 1,
        "kind": PENDING_RESOLUTION_KIND,
        "cycle_id": cycle_id,
        "pending_conflict_id": pending_conflict_id,
        "pending_record_sha256": pending_conflict_id,
        "attempt_id": pending.get("attempt_id"),
        "attempt_memory_digest": pending.get("attempt_memory_digest"),
        "attempt_memory_disposition": disposition,
        "state_commit_status": "committed",
        "resolution_evidence_id": resolution_evidence_id,
        "resolution_evidence_digest": evidence_digest,
        "resolution_evidence_ref": resolution_evidence_ref,
        "resolution_rationale_id": resolution_rationale_id,
        "committed_finalization_token": committed_finalization_token,
    }
    resolution["resolution_record_digest"] = canonical_sha256(resolution)
    resolution_bytes = canonical_json_bytes(resolution)
    resolution_path = _resolution_path(root, cycle_id, pending_conflict_id)
    immutable_writer(resolution_path, resolution_bytes)
    return {
        **resolution,
        "resolution_ref": rel_path(root, resolution_path),
        "resolution_sha256": hashlib.sha256(resolution_bytes).hexdigest(),
    }


def resolve_pending_finalization_conflict(
    root: Path,
    cycle_id: str,
    pending_conflict_id: str,
    *,
    disposition: str,
    resolution_evidence_id: str,
    resolution_evidence_digest: str,
    resolution_evidence_ref: str,
    resolution_rationale_id: str,
    committed_finalization_token: str | None = None,
) -> dict[str, Any]:
    cycle_id = validate_cycle_id(cycle_id)
    with ledger_lock(root, cycle_id, exclusive=True):
        return resolve_pending_conflict_unlocked(
            root,
            cycle_id,
            pending_conflict_id,
            disposition=disposition,
            resolution_evidence_id=resolution_evidence_id,
            resolution_evidence_digest=resolution_evidence_digest,
            resolution_evidence_ref=resolution_evidence_ref,
            resolution_rationale_id=resolution_rationale_id,
            committed_finalization_token=committed_finalization_token,
        )


def load_pending_finalization_conflicts(
    root: Path, cycle_id: str
) -> list[dict[str, Any]]:
    cycle_id = validate_cycle_id(cycle_id)
    with ledger_lock(root, cycle_id, exclusive=False):
        directory = pending_finalizations_dir(root, cycle_id)
        if not directory.is_dir():
            return []
        active: list[dict[str, Any]] = []
        for path in sorted(directory.glob("*.json")):
            record = _load_canonical_record(path)
            if (
                record.get("schema_version") != 1
                or record.get("kind") != PENDING_CONFLICT_KIND
                or record.get("cycle_id") != cycle_id
                or record.get("attempt_memory_disposition") != "pending_conflict"
            ):
                raise ValueError(
                    f"pending finalization conflict schema is invalid: {path}"
                )
            resolution_path = _resolution_path(root, cycle_id, path.stem)
            if resolution_path.is_file():
                raw_resolution = resolution_path.read_bytes()
                try:
                    resolution = json.loads(raw_resolution.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise ValueError(
                        f"pending finalization resolution is malformed: {resolution_path}"
                    ) from exc
                if (
                    not isinstance(resolution, dict)
                    or canonical_json_bytes(resolution) != raw_resolution
                    or resolution.get("schema_version") != 1
                    or resolution.get("kind") != PENDING_RESOLUTION_KIND
                    or resolution.get("cycle_id") != cycle_id
                    or resolution.get("pending_conflict_id") != path.stem
                    or resolution.get("pending_record_sha256") != path.stem
                    or resolution.get("attempt_id") != record.get("attempt_id")
                    or resolution.get("attempt_memory_digest")
                    != record.get("attempt_memory_digest")
                    or resolution.get("attempt_memory_disposition")
                    not in PENDING_DISPOSITIONS
                    or resolution.get("state_commit_status") != "committed"
                    or not SHA256_PATTERN.fullmatch(
                        str(resolution.get("resolution_evidence_digest") or "")
                    )
                    or not isinstance(resolution.get("resolution_evidence_id"), str)
                    or not isinstance(resolution.get("resolution_evidence_ref"), str)
                    or not isinstance(resolution.get("resolution_rationale_id"), str)
                    or resolution.get("resolution_record_digest")
                    != canonical_sha256(
                        {
                            key: value
                            for key, value in resolution.items()
                            if key != "resolution_record_digest"
                        }
                    )
                    or (
                        resolution.get("attempt_memory_disposition") == "merged"
                        and (
                            not SHA256_PATTERN.fullmatch(
                                str(
                                    resolution.get("committed_finalization_token") or ""
                                )
                            )
                            or resolution.get("resolution_evidence_digest")
                            != resolution.get("committed_finalization_token")
                        )
                    )
                    or (
                        resolution.get("attempt_memory_disposition") == "retired"
                        and resolution.get("committed_finalization_token") is not None
                    )
                ):
                    raise ValueError(
                        f"pending finalization resolution binding is invalid: {resolution_path}"
                    )
                continue
            active.append(
                {
                    "pending_conflict_id": path.stem,
                    "record_ref": rel_path(root, path),
                    "record_sha256": path.stem,
                    **record,
                }
            )
        return active


def merge_matching_pending_conflicts_unlocked(
    root: Path,
    cycle_id: str,
    candidate: dict[str, Any],
    *,
    committed_finalization_token: str,
    immutable_writer: ImmutableBytesWriter = immutable_write_bytes,
) -> list[dict[str, Any]]:
    directory = pending_finalizations_dir(root, cycle_id)
    if not directory.is_dir():
        return []
    memory_digest = canonical_sha256(_attempt_memory_material(cycle_id, candidate))
    resolutions: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        pending = _load_canonical_record(path)
        if pending.get("attempt_memory_digest") != memory_digest:
            continue
        if _resolution_path(root, cycle_id, path.stem).is_file():
            continue
        resolutions.append(
            resolve_pending_conflict_unlocked(
                root,
                cycle_id,
                path.stem,
                disposition="merged",
                resolution_evidence_id=f"finalization-{committed_finalization_token}",
                resolution_evidence_digest=committed_finalization_token,
                resolution_evidence_ref=f"finalization-{committed_finalization_token}",
                resolution_rationale_id="matching-attempt-memory-merged",
                committed_finalization_token=committed_finalization_token,
                immutable_writer=immutable_writer,
            )
        )
    return resolutions
