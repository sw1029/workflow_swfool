from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .candidate_validation import (
    authoritative_final_from_axes,
    validate_durable_payload_privacy,
    validate_durable_state_candidate,
)
from .constants import (
    FINALIZATION_POINTER_KIND,
    FINALIZATION_RECEIPT_KIND,
    FINALIZATION_SCHEMA_VERSION,
    FINALIZATION_SNAPSHOT_KIND,
    SHA256_PATTERN,
    VERDICT_AXES,
    VERDICT_AXIS_STATUSES,
)
from .finalization_publication import (
    FinalizationVerification,
    ImmutableBytesWriter,
    publish_candidate,
)
from .no_change_contract import no_change_candidate_matches_authoritative_state
from .operation_contract import projected_target_state
from .repository import AtomicTextWriter
from .support import (
    atomic_write_text,
    canonical_json_bytes,
    canonical_sha256,
    current_finalization_path,
    finalization_snapshot_path,
    immutable_write_bytes,
    ledger_lock,
    rel_path,
    validate_cycle_id,
    validate_event_id,
)


def _load_current_finalization_unlocked(
    root: Path, cycle_id: str
) -> dict[str, Any] | None:
    path = current_finalization_path(root, cycle_id)
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed current finalization pointer: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError("current finalization pointer must be a JSON object")
    return value


def _validate_receipt_header(cycle_id: str, receipt: dict[str, Any]) -> tuple[str, str]:
    if not isinstance(receipt, dict):
        raise ValueError("finalization receipt must be a JSON object")
    receipt_schema_version = receipt.get("schema_version")
    if (
        isinstance(receipt_schema_version, bool)
        or receipt_schema_version != FINALIZATION_SCHEMA_VERSION
    ):
        raise ValueError("finalization receipt schema_version must be 1")
    if receipt.get("kind") != FINALIZATION_RECEIPT_KIND:
        raise ValueError(
            f"finalization receipt kind must be {FINALIZATION_RECEIPT_KIND}"
        )
    if str(receipt.get("cycle_id") or "") != cycle_id:
        raise ValueError("finalization receipt cycle_id mismatch")
    validate_event_id(receipt.get("attempt_id"))
    revision = receipt.get("attempt_revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise ValueError(
            "finalization receipt attempt_revision must be a positive integer"
        )
    expected_previous = receipt.get("expected_previous_revision")
    if expected_previous is not None and (
        isinstance(expected_previous, bool)
        or not isinstance(expected_previous, int)
        or expected_previous < 1
    ):
        raise ValueError("finalization receipt expected_previous_revision is invalid")
    expected_previous_attempt_id = receipt.get("expected_previous_attempt_id")
    if expected_previous_attempt_id is not None:
        validate_event_id(expected_previous_attempt_id)
    expected_previous_token = receipt.get("expected_previous_finalization_token")
    if expected_previous_token is not None and not SHA256_PATTERN.fullmatch(
        str(expected_previous_token)
    ):
        raise ValueError("finalization receipt expected previous token is invalid")
    supersedes_revision = receipt.get("supersedes_revision")
    supersedes_token = receipt.get("supersedes_finalization_token")
    if revision > 1:
        if (
            supersedes_revision != revision - 1
            or expected_previous != supersedes_revision
            or expected_previous_attempt_id != receipt.get("attempt_id")
            or expected_previous_token != supersedes_token
            or not SHA256_PATTERN.fullmatch(str(supersedes_token or ""))
        ):
            raise ValueError(
                "same-attempt finalization revision has invalid supersession lineage"
            )
    elif supersedes_revision is not None or supersedes_token is not None:
        raise ValueError(
            "first attempt revision must not claim same-attempt supersession"
        )
    elif expected_previous_attempt_id == receipt.get("attempt_id"):
        raise ValueError("same-attempt correction cannot reset attempt_revision to 1")
    receipt_hash = str(receipt.get("receipt_hash") or "").strip().lower()
    receipt_body = dict(receipt)
    receipt_body.pop("receipt_hash", None)
    if not SHA256_PATTERN.fullmatch(receipt_hash) or receipt_hash != canonical_sha256(
        receipt_body
    ):
        raise ValueError("finalization receipt hash mismatch")
    finalization_token = str(receipt.get("finalization_token") or "").strip().lower()
    if not SHA256_PATTERN.fullmatch(finalization_token):
        raise ValueError("finalization receipt token is invalid")
    if receipt.get("current_pointer_token") != finalization_token:
        raise ValueError("finalization receipt current pointer token mismatch")
    predecessor_token = receipt.get("predecessor_token")
    if predecessor_token != expected_previous_token:
        raise ValueError("finalization receipt predecessor token mismatch")
    if predecessor_token is not None and not SHA256_PATTERN.fullmatch(
        str(predecessor_token)
    ):
        raise ValueError("finalization receipt predecessor token is invalid")
    for digest_field in ("operation_set_digest", "post_write_projection_digest"):
        if not SHA256_PATTERN.fullmatch(str(receipt.get(digest_field) or "")):
            raise ValueError(f"finalization receipt {digest_field} is invalid")
    if receipt.get("attempt_memory_disposition") != "none":
        raise ValueError(
            "committed finalization receipt attempt memory disposition is invalid"
        )
    return receipt_hash, finalization_token


def _load_verified_snapshot(
    root: Path,
    cycle_id: str,
    receipt: dict[str, Any],
    finalization_token: str,
) -> dict[str, Any]:
    snapshot_path = finalization_snapshot_path(root, cycle_id, finalization_token)
    if str(receipt.get("snapshot_ref") or "") != rel_path(root, snapshot_path):
        raise ValueError("finalization receipt snapshot_ref mismatch")
    if not snapshot_path.is_file():
        raise ValueError("finalization receipt snapshot is missing")
    raw_snapshot = snapshot_path.read_bytes()
    snapshot_sha256 = hashlib.sha256(raw_snapshot).hexdigest()
    if (
        snapshot_sha256 != finalization_token
        or str(receipt.get("snapshot_sha256") or "") != snapshot_sha256
    ):
        raise ValueError("finalization snapshot content hash mismatch")
    try:
        snapshot = json.loads(raw_snapshot.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("finalization snapshot is malformed") from exc
    if not isinstance(snapshot, dict) or canonical_json_bytes(snapshot) != raw_snapshot:
        raise ValueError("finalization snapshot is not canonical JSON")
    schema_version = snapshot.get("schema_version")
    if (
        isinstance(schema_version, bool)
        or schema_version != FINALIZATION_SCHEMA_VERSION
        or snapshot.get("kind") != FINALIZATION_SNAPSHOT_KIND
    ):
        raise ValueError("finalization snapshot schema or kind mismatch")
    for field in (
        "cycle_id",
        "attempt_id",
        "attempt_revision",
        "supersedes_revision",
        "supersedes_finalization_token",
        "expected_previous_revision",
        "expected_previous_attempt_id",
        "expected_previous_finalization_token",
        "final_candidate_digest",
        "validation_axes_digest",
        "authoritative_projection_id",
        "authoritative_projection_digest",
        "predecessor_token",
        "operation_set_digest",
        "operation_ids",
        "expected_target_revision_ids",
        "target_revision_ids",
        "post_write_projection_digest",
    ):
        if snapshot.get(field) != receipt.get(field):
            raise ValueError(f"finalization receipt and snapshot disagree on {field}")
    return snapshot


def _validate_projection(
    receipt: dict[str, Any], snapshot: dict[str, Any]
) -> dict[str, Any]:
    projection = snapshot.get("authoritative_projection")
    if not isinstance(projection, dict):
        raise ValueError("finalization snapshot lacks authoritative_projection")
    expected_fields = {"verdict_contract_version", "authoritative_final", *VERDICT_AXES}
    projection_version = projection.get("verdict_contract_version")
    if (
        set(projection) != expected_fields
        or isinstance(projection_version, bool)
        or projection_version != 1
    ):
        raise ValueError(
            "authoritative projection fields or verdict contract version mismatch"
        )
    verified_axes: dict[str, dict[str, Any]] = {}
    for axis in VERDICT_AXES:
        value = projection.get(axis)
        if (
            not isinstance(value, dict)
            or str(value.get("status") or "") not in VERDICT_AXIS_STATUSES
        ):
            raise ValueError(f"authoritative projection verdict axis {axis} is invalid")
        evidence = value.get("evidence_ref") or value.get("evidence_refs")
        if value.get("status") != "not_applicable" and evidence in (None, "", []):
            raise ValueError(
                f"authoritative projection verdict axis {axis} lacks evidence"
            )
        if evidence not in (None, "", []):
            validate_durable_payload_privacy(
                evidence, f"authoritative_projection.{axis}.evidence"
            )
        verified_axes[axis] = value
    if projection.get("authoritative_final") != authoritative_final_from_axes(
        verified_axes
    ):
        raise ValueError(
            "authoritative final verdict does not match the six verdict axes"
        )
    projection_digest = canonical_sha256(projection)
    if projection_digest != snapshot.get("authoritative_projection_digest"):
        raise ValueError("authoritative projection digest mismatch")
    if snapshot.get("authoritative_projection_id") != f"sha256:{projection_digest}":
        raise ValueError("authoritative projection id mismatch")
    if projection.get("authoritative_final") != receipt.get("authoritative_final"):
        raise ValueError("authoritative final verdict mismatch")
    axes_material = {
        "verdict_contract_version": projection.get("verdict_contract_version")
    }
    for axis in VERDICT_AXES:
        axes_material[axis] = projection.get(axis)
    if canonical_sha256(axes_material) != snapshot.get("validation_axes_digest"):
        raise ValueError("validation axes digest mismatch")
    durable_state = snapshot.get("durable_state_candidate")
    validate_durable_state_candidate(
        durable_state,
        verified_axes["artifact_semantic_verdict"]["status"],
        verified_axes["goal_readiness_verdict"]["status"],
        str(snapshot.get("attempt_id") or ""),
    )
    if canonical_sha256(durable_state) != snapshot.get("durable_state_digest"):
        raise ValueError("durable state candidate digest mismatch")
    post_write_projection = snapshot.get("post_write_projection")
    if not isinstance(post_write_projection, dict):
        raise ValueError("finalization snapshot lacks post-write target projection")
    if canonical_sha256(post_write_projection) != snapshot.get(
        "post_write_projection_digest"
    ):
        raise ValueError("post-write target projection digest mismatch")
    revisions = {
        target: value.get("resulting_revision_id")
        for target, value in post_write_projection.items()
        if isinstance(value, dict)
    }
    if revisions != snapshot.get("target_revision_ids"):
        raise ValueError("post-write target revision projection mismatch")
    return projection


def _predecessor_projection(
    root: Path, cycle_id: str, predecessor_token: object
) -> dict[str, Any]:
    if predecessor_token is None:
        return {}
    token = str(predecessor_token)
    path = finalization_snapshot_path(root, cycle_id, token)
    if not path.is_file():
        raise ValueError("predecessor finalization snapshot is missing")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != token:
        raise ValueError("predecessor finalization snapshot hash mismatch")
    try:
        snapshot = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("predecessor finalization snapshot is malformed") from exc
    projection = (
        snapshot.get("post_write_projection") if isinstance(snapshot, dict) else None
    )
    if (
        not isinstance(snapshot, dict)
        or canonical_json_bytes(snapshot) != raw
        or snapshot.get("cycle_id") != cycle_id
        or not isinstance(projection, dict)
        or canonical_sha256(projection) != snapshot.get("post_write_projection_digest")
    ):
        raise ValueError("predecessor target projection is invalid")
    return projection


def _validate_post_write_lineage(
    root: Path, cycle_id: str, snapshot: dict[str, Any]
) -> None:
    durable_state = snapshot["durable_state_candidate"]
    operations = (
        durable_state["operations"]
        if durable_state.get("mode") == "typed_operations"
        else []
    )
    if canonical_sha256(operations) != snapshot.get("operation_set_digest"):
        raise ValueError("operation-set digest mismatch")
    predecessor = _predecessor_projection(
        root,
        cycle_id,
        snapshot.get("predecessor_token"),
    )
    if not no_change_candidate_matches_authoritative_state(
        durable_state,
        predecessor,
    ):
        raise ValueError(
            "no-change observations do not match predecessor owner projection"
        )
    expected = {
        **predecessor,
        **projected_target_state(durable_state),
    }
    if expected != snapshot.get("post_write_projection"):
        raise ValueError(
            "post-write target projection does not match predecessor lineage"
        )


def _validate_pointer(
    cycle_id: str,
    receipt: dict[str, Any],
    receipt_hash: str,
    finalization_token: str,
    pointer: dict[str, Any] | None,
) -> None:
    if not isinstance(pointer, dict):
        raise ValueError("current finalization pointer is missing")
    if (
        isinstance(pointer.get("schema_version"), bool)
        or pointer.get("schema_version") != FINALIZATION_SCHEMA_VERSION
        or pointer.get("kind") != FINALIZATION_POINTER_KIND
        or pointer.get("cycle_id") != cycle_id
    ):
        raise ValueError("current finalization pointer schema, kind, or cycle mismatch")
    if (
        pointer.get("receipt_hash") != receipt_hash
        or pointer.get("finalization_token") != finalization_token
        or pointer.get("current_pointer_token") != finalization_token
    ):
        raise ValueError(
            "finalization receipt is stale or does not match current pointer"
        )
    if pointer.get("receipt") != receipt:
        raise ValueError("current finalization pointer receipt body mismatch")


def _verify_finalization_receipt_unlocked(
    root: Path,
    cycle_id: str,
    receipt: dict[str, Any],
    current_pointer: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cycle_id = validate_cycle_id(cycle_id)
    receipt_hash, finalization_token = _validate_receipt_header(cycle_id, receipt)
    snapshot = _load_verified_snapshot(root, cycle_id, receipt, finalization_token)
    projection = _validate_projection(receipt, snapshot)
    _validate_post_write_lineage(root, cycle_id, snapshot)
    if receipt.get("state_commit_status") != "committed":
        raise ValueError("finalization receipt is not committed")
    pointer = (
        current_pointer
        if current_pointer is not None
        else _load_current_finalization_unlocked(root, cycle_id)
    )
    _validate_pointer(cycle_id, receipt, receipt_hash, finalization_token, pointer)
    return {
        "valid": True,
        "finalization_receipt": receipt,
        "receipt": receipt,
        "authoritative_projection": projection,
        "snapshot": snapshot,
        "current_pointer": pointer,
    }


def verify_finalization_receipt(
    root: Path, cycle_id: str, receipt: dict[str, Any]
) -> dict[str, Any]:
    cycle_id = validate_cycle_id(cycle_id)
    with ledger_lock(root, cycle_id, exclusive=False):
        return _verify_finalization_receipt_unlocked(root, cycle_id, receipt)


def load_current_finalized_state(root: Path, cycle_id: str) -> dict[str, Any]:
    """Load only the content-verified current state projection for downstream consumers."""
    cycle_id = validate_cycle_id(cycle_id)
    with ledger_lock(root, cycle_id, exclusive=False):
        pointer = _load_current_finalization_unlocked(root, cycle_id)
        if not isinstance(pointer, dict) or not isinstance(
            pointer.get("receipt"), dict
        ):
            raise ValueError("current finalized state is unavailable")
        verified = _verify_finalization_receipt_unlocked(
            root, cycle_id, pointer["receipt"], current_pointer=pointer
        )
        snapshot = verified["snapshot"]
        return {
            "valid": True,
            "cycle_id": cycle_id,
            "receipt": verified["receipt"],
            "durable_state_candidate": snapshot["durable_state_candidate"],
            "durable_state_digest": snapshot["durable_state_digest"],
            "operation_set_digest": snapshot["operation_set_digest"],
            "post_write_projection": snapshot["post_write_projection"],
            "post_write_projection_digest": snapshot["post_write_projection_digest"],
            "target_revision_ids": snapshot["target_revision_ids"],
            "authoritative_projection": snapshot["authoritative_projection"],
            "authoritative_projection_digest": snapshot[
                "authoritative_projection_digest"
            ],
        }


def finalize_candidate(
    root: Path,
    cycle_id: str,
    candidate: dict[str, Any],
    *,
    atomic_writer: AtomicTextWriter = atomic_write_text,
    immutable_writer: ImmutableBytesWriter = immutable_write_bytes,
) -> dict[str, Any]:
    """Prepare and publish a candidate through the verification-owned facade."""

    verification = FinalizationVerification(
        load_current=_load_current_finalization_unlocked,
        load_snapshot=_load_verified_snapshot,
        verify_receipt=_verify_finalization_receipt_unlocked,
    )
    return publish_candidate(
        root,
        cycle_id,
        candidate,
        verification=verification,
        atomic_writer=atomic_writer,
        immutable_writer=immutable_writer,
    )


__all__ = (
    "finalize_candidate",
    "load_current_finalized_state",
    "verify_finalization_receipt",
)
