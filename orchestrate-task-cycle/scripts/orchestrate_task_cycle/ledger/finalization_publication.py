from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from .candidate_validation import (
    authoritative_final_from_axes,
    final_candidate_commit_material,
    normalize_final_candidate,
)
from .constants import (
    FINALIZATION_POINTER_KIND,
    FINALIZATION_RECEIPT_KIND,
    FINALIZATION_SCHEMA_VERSION,
    FINALIZATION_SNAPSHOT_KIND,
    VERDICT_AXES,
)
from .no_change_contract import no_change_candidate_matches_authoritative_state
from .operation_contract import projected_target_state
from .pending_finalization import (
    FinalizationConflictError,
    merge_matching_pending_conflicts_unlocked,
    persist_pending_conflict_unlocked,
)
from .repository import AtomicTextWriter
from .support import (
    atomic_write_text,
    canonical_json_bytes,
    canonical_sha256,
    current_finalization_path,
    finalization_snapshot_path,
    immutable_write_bytes,
    ledger_lock,
    read_initialization_metadata,
    rel_path,
    validate_cycle_id,
)


ImmutableBytesWriter = Callable[[Path, bytes], None]


@dataclass(frozen=True)
class FinalizationVerification:
    """Unlocked read/verification services supplied by the facade owner."""

    load_current: Callable[[Path, str], dict[str, Any] | None]
    load_snapshot: Callable[[Path, str, dict[str, Any], str], dict[str, Any]]
    verify_receipt: Callable[..., dict[str, Any]]


def _prepared_candidate(cycle_id: str, candidate: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_final_candidate(cycle_id, candidate)
    final_candidate_digest = canonical_sha256(
        final_candidate_commit_material(normalized)
    )
    axes = {axis: normalized[axis] for axis in VERDICT_AXES}
    axes_material = {"verdict_contract_version": 1, **axes}
    authoritative_final = authoritative_final_from_axes(axes)
    projection = {**axes_material, "authoritative_final": authoritative_final}
    projection_digest = canonical_sha256(projection)
    durable_state = normalized["durable_state_candidate"]
    operations = (
        durable_state.get("operations")
        if durable_state.get("mode") == "typed_operations"
        else []
    )
    return {
        "normalized": normalized,
        "final_candidate_digest": final_candidate_digest,
        "validation_axes_digest": canonical_sha256(axes_material),
        "authoritative_final": authoritative_final,
        "projection": projection,
        "projection_digest": projection_digest,
        "projection_id": f"sha256:{projection_digest}",
        "durable_state_digest": canonical_sha256(durable_state),
        "operation_set_digest": (
            durable_state.get("operation_set_digest")
            if operations
            else canonical_sha256([])
        ),
        "operation_ids": [operation["operation_id"] for operation in operations],
        "expected_target_revision_ids": [
            operation["expected_revision_id"] for operation in operations
        ],
    }


def _current_receipt_or_replay(
    root: Path,
    cycle_id: str,
    prepared: dict[str, Any],
    verification: FinalizationVerification,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    current_pointer = verification.load_current(root, cycle_id)
    if current_pointer is None:
        return None, None
    embedded = current_pointer.get("receipt")
    if not isinstance(embedded, dict):
        raise ValueError("current finalization pointer lacks a receipt")
    verified = verification.verify_receipt(
        root, cycle_id, embedded, current_pointer=current_pointer
    )
    receipt = verified["receipt"]
    normalized = prepared["normalized"]
    if (
        receipt.get("attempt_id") == normalized["attempt_id"]
        and receipt.get("final_candidate_digest") == prepared["final_candidate_digest"]
    ):
        replay = {
            **verified,
            "idempotent": True,
            "snapshot_path": receipt["snapshot_ref"],
            "current_finalization_path": rel_path(
                root, current_finalization_path(root, cycle_id)
            ),
        }
        return receipt, replay
    return receipt, None


def _enforce_expected_previous(
    root: Path,
    cycle_id: str,
    prepared: dict[str, Any],
    current_receipt: dict[str, Any] | None,
    immutable_writer: ImmutableBytesWriter,
) -> tuple[int | None, str | None, str | None]:
    normalized = prepared["normalized"]
    actual = (
        current_receipt.get("attempt_revision") if current_receipt else None,
        current_receipt.get("attempt_id") if current_receipt else None,
        current_receipt.get("finalization_token") if current_receipt else None,
    )
    expected = (
        normalized["expected_previous_revision"],
        normalized["expected_previous_attempt_id"],
        normalized["expected_previous_finalization_token"],
    )
    if expected == actual:
        return actual
    pending_receipt = persist_pending_conflict_unlocked(
        root,
        cycle_id,
        normalized,
        final_candidate_digest=prepared["final_candidate_digest"],
        actual_previous_revision=actual[0],
        actual_previous_attempt_id=actual[1],
        actual_previous_token=actual[2],
        immutable_writer=immutable_writer,
    )
    raise FinalizationConflictError(
        "final candidate expected previous finalization does not match current pointer; "
        "valid attempt memory was preserved as pending_conflict",
        pending_receipt,
    )


def _prior_target_state(
    root: Path,
    cycle_id: str,
    current_receipt: dict[str, Any] | None,
    verification: FinalizationVerification,
) -> dict[str, Any]:
    if current_receipt is None:
        return {}
    token = str(current_receipt.get("finalization_token") or "")
    snapshot = verification.load_snapshot(root, cycle_id, current_receipt, token)
    value = snapshot.get("post_write_projection")
    if not isinstance(value, dict):
        raise ValueError("current finalization lacks a verified target projection")
    return value


def _target_preconditions_match(
    durable_state: dict[str, Any], prior_state: dict[str, Any]
) -> bool:
    if durable_state.get("mode") != "typed_operations":
        return no_change_candidate_matches_authoritative_state(
            durable_state,
            prior_state,
        )
    for operation in durable_state["operations"]:
        prior = prior_state.get(operation["target_ref"])
        if isinstance(prior, dict) and (
            prior.get("idempotency_key") == operation["idempotency_key"]
            and prior.get("payload_digest") == operation["payload_digest"]
        ):
            continue
        actual_revision = (
            prior.get("resulting_revision_id") if isinstance(prior, dict) else None
        )
        if operation["expected_revision_id"] != actual_revision:
            return False
    return True


def _enforce_target_preconditions(
    root: Path,
    cycle_id: str,
    prepared: dict[str, Any],
    current_receipt: dict[str, Any] | None,
    immutable_writer: ImmutableBytesWriter,
    verification: FinalizationVerification,
) -> dict[str, Any]:
    prior_state = _prior_target_state(root, cycle_id, current_receipt, verification)
    durable_state = prepared["normalized"]["durable_state_candidate"]
    if _target_preconditions_match(durable_state, prior_state):
        return prior_state
    pending_receipt = persist_pending_conflict_unlocked(
        root,
        cycle_id,
        prepared["normalized"],
        final_candidate_digest=prepared["final_candidate_digest"],
        actual_previous_revision=(
            current_receipt.get("attempt_revision") if current_receipt else None
        ),
        actual_previous_attempt_id=(
            current_receipt.get("attempt_id") if current_receipt else None
        ),
        actual_previous_token=(
            current_receipt.get("finalization_token") if current_receipt else None
        ),
        immutable_writer=immutable_writer,
    )
    raise FinalizationConflictError(
        "durable target expected target revision/no-change observation does not "
        "match current owner projection; "
        "valid attempt memory was preserved as pending_conflict",
        pending_receipt,
    )


def _publication_documents(
    root: Path,
    cycle_id: str,
    prepared: dict[str, Any],
    actual: tuple[int | None, str | None, str | None],
    prior_target_state: dict[str, Any],
) -> tuple[dict[str, Any], bytes, Path, dict[str, Any], dict[str, Any]]:
    normalized = prepared["normalized"]
    same_attempt = actual[1] == normalized["attempt_id"] and actual[1] is not None
    revision = int(actual[0]) + 1 if same_attempt else 1
    supersedes_revision = actual[0] if same_attempt else None
    supersedes_token = actual[2] if same_attempt else None
    current_target_state = {
        **prior_target_state,
        **projected_target_state(normalized["durable_state_candidate"]),
    }
    current_target_revisions = {
        target: value["resulting_revision_id"]
        for target, value in current_target_state.items()
    }
    post_write_projection_digest = canonical_sha256(current_target_state)
    shared = {
        "cycle_id": cycle_id,
        "attempt_id": normalized["attempt_id"],
        "attempt_revision": revision,
        "supersedes_revision": supersedes_revision,
        "supersedes_finalization_token": supersedes_token,
        "expected_previous_revision": normalized["expected_previous_revision"],
        "expected_previous_attempt_id": normalized["expected_previous_attempt_id"],
        "expected_previous_finalization_token": normalized[
            "expected_previous_finalization_token"
        ],
        "final_candidate_digest": prepared["final_candidate_digest"],
        "validation_axes_digest": prepared["validation_axes_digest"],
        "authoritative_projection_id": prepared["projection_id"],
        "authoritative_projection_digest": prepared["projection_digest"],
        "predecessor_token": actual[2],
        "operation_set_digest": prepared["operation_set_digest"],
        "operation_ids": prepared["operation_ids"],
        "expected_target_revision_ids": prepared["expected_target_revision_ids"],
        "target_revision_ids": current_target_revisions,
        "post_write_projection_digest": post_write_projection_digest,
    }
    snapshot = {
        "schema_version": FINALIZATION_SCHEMA_VERSION,
        "kind": FINALIZATION_SNAPSHOT_KIND,
        **shared,
        "authoritative_projection": prepared["projection"],
        "durable_state_candidate": normalized["durable_state_candidate"],
        "durable_state_digest": prepared["durable_state_digest"],
        "post_write_projection": current_target_state,
    }
    snapshot_bytes = canonical_json_bytes(snapshot)
    token = hashlib.sha256(snapshot_bytes).hexdigest()
    snapshot_path = finalization_snapshot_path(root, cycle_id, token)
    receipt_body = {
        "schema_version": FINALIZATION_SCHEMA_VERSION,
        "kind": FINALIZATION_RECEIPT_KIND,
        **shared,
        "finalization_token": token,
        "snapshot_ref": rel_path(root, snapshot_path),
        "snapshot_sha256": token,
        "state_commit_status": "committed",
        "authoritative_final": prepared["authoritative_final"],
        "attempt_memory_disposition": "none",
    }
    receipt_body["current_pointer_token"] = token
    receipt = {**receipt_body, "receipt_hash": canonical_sha256(receipt_body)}
    pointer = {
        "schema_version": FINALIZATION_SCHEMA_VERSION,
        "kind": FINALIZATION_POINTER_KIND,
        "cycle_id": cycle_id,
        "finalization_token": token,
        "receipt_hash": receipt["receipt_hash"],
        "receipt": receipt,
        "current_pointer_token": token,
    }
    return snapshot, snapshot_bytes, snapshot_path, receipt, pointer


def _verify_prepared_snapshot_write(path: Path, expected: bytes, token: str) -> None:
    if not path.is_file():
        raise ValueError("prepared finalization snapshot was not durably written")
    observed = path.read_bytes()
    if observed != expected or hashlib.sha256(observed).hexdigest() != token:
        raise ValueError("prepared finalization snapshot reload mismatch")
    try:
        value = json.loads(observed.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("prepared finalization snapshot is malformed") from exc
    if not isinstance(value, dict) or canonical_json_bytes(value) != observed:
        raise ValueError("prepared finalization snapshot is not canonical JSON")


def publish_candidate(
    root: Path,
    cycle_id: str,
    candidate: dict[str, Any],
    *,
    verification: FinalizationVerification,
    atomic_writer: AtomicTextWriter = atomic_write_text,
    immutable_writer: ImmutableBytesWriter = immutable_write_bytes,
) -> dict[str, Any]:
    cycle_id = validate_cycle_id(cycle_id)
    prepared = _prepared_candidate(cycle_id, candidate)
    normalized = prepared["normalized"]

    with ledger_lock(root, cycle_id, exclusive=True):
        read_initialization_metadata(root, cycle_id)
        current_receipt, replay = _current_receipt_or_replay(
            root, cycle_id, prepared, verification
        )
        if replay is not None:
            merged_pending_conflicts = merge_matching_pending_conflicts_unlocked(
                root,
                cycle_id,
                normalized,
                committed_finalization_token=replay["receipt"]["finalization_token"],
                immutable_writer=immutable_writer,
            )
            return {
                **replay,
                "merged_pending_conflicts": merged_pending_conflicts,
            }
        actual = _enforce_expected_previous(
            root, cycle_id, prepared, current_receipt, immutable_writer
        )
        prior_target_state = _enforce_target_preconditions(
            root,
            cycle_id,
            prepared,
            current_receipt,
            immutable_writer,
            verification,
        )
        _, snapshot_bytes, snapshot_path, receipt, pointer = _publication_documents(
            root, cycle_id, prepared, actual, prior_target_state
        )
        finalization_token = receipt["finalization_token"]
        immutable_writer(snapshot_path, snapshot_bytes)
        _verify_prepared_snapshot_write(
            snapshot_path, snapshot_bytes, finalization_token
        )
        atomic_writer(
            current_finalization_path(root, cycle_id),
            json.dumps(pointer, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        verified = verification.verify_receipt(
            root, cycle_id, receipt, current_pointer=pointer
        )
        merged_pending_conflicts = merge_matching_pending_conflicts_unlocked(
            root,
            cycle_id,
            normalized,
            committed_finalization_token=finalization_token,
            immutable_writer=immutable_writer,
        )
        return {
            **verified,
            "idempotent": False,
            "snapshot_path": rel_path(root, snapshot_path),
            "current_finalization_path": rel_path(
                root, current_finalization_path(root, cycle_id)
            ),
            "merged_pending_conflicts": merged_pending_conflicts,
        }


__all__ = (
    "FinalizationVerification",
    "ImmutableBytesWriter",
    "publish_candidate",
)
