"""Locked orchestration for compact selection-publication intents."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import selection_publication as publication
from .selection_publication_prepare import (
    new_predecessor_transaction_id,
    pending_replay,
    prepare_response,
)
from .selection_publication_status import current_head_status
from .selection_publication_store import (
    _canonical_json,
    _display_json,
    _lock,
    _prepare_path,
    _sha256_bytes,
    _sha256_file,
    _write_once,
)
from .selection_publication_intent_index import (
    load_intent_index,
    write_commit_index,
    write_prepare_index,
)
from .selection_publication_state import (
    STORAGE_SCHEMA_VERSION,
    head_receipts,
    record_committed,
    record_prepared,
)
from .selection_publication_payload import persist_blob
from .selection_publication_producer_capability import (
    _SELECTION_PUBLICATION_PRODUCER_CAPABILITY,
)
from .selection_publication_v2 import (
    compile_intent,
    external_intent_identity,
)


_LOGICAL_INTENT_KEYS = (
    "schema_version",
    "kind",
    "selection_id",
    "source_decision_id",
    "source_decision_sha256",
    "source_decision",
    "publication_mode",
    "owner_assertions",
    "task_state_plan",
    "intent_sha256",
    "compiler_metrics",
)
_LOGICAL_TARGET_KEYS = (
    "role",
    "target_ref",
    "after_sha256",
    "payload_ref",
    "payload_sha256",
    "payload_size",
)


def _logical_intent_material(value: dict[str, Any]) -> dict[str, Any]:
    targets = value.get("targets")
    if not isinstance(targets, list):
        return {}
    return {
        **{key: value.get(key) for key in _LOGICAL_INTENT_KEYS},
        "targets": [
            {key: target.get(key) for key in _LOGICAL_TARGET_KEYS}
            for target in targets
            if isinstance(target, dict)
        ],
    }


def _committed_intent_replay(
    root: Path,
    normalized: dict[str, Any],
    receipts: list[dict[str, Any]],
    current_task_sha256: str | None,
) -> dict[str, Any] | None:
    """Reuse a logical v2 publication after its compiler-owned before state changed."""

    expected = _logical_intent_material(normalized)
    matches: list[tuple[str, Path, str]] = []
    for receipt in receipts:
        transaction_id = str(receipt["transaction_id"])
        prepare, path, digest = publication._load_prepare(root, transaction_id)
        if prepare.get("schema_version") == 2 and (
            _logical_intent_material(prepare) == expected
        ):
            matches.append((transaction_id, path, digest))
    if len(matches) > 1:
        head = current_head_status(receipts, current_task_sha256)
        head_matches = [
            match
            for match in matches
            if match[0] == head.get("head_transaction_id")
        ]
        if len(head_matches) != 1:
            raise ValueError(
                "selection-publication logical committed replay is ambiguous"
            )
        matches = head_matches
    if not matches:
        return None
    transaction_id, path, digest = matches[0]
    return prepare_response(
        root,
        transaction_id,
        path,
        digest,
        status="already_committed",
        mutation_performed=False,
        recovery_required=False,
    )


def _prepared_external_intent_replay(
    root: Path, intent_value: dict[str, Any], state: dict[str, Any]
) -> dict[str, Any] | None:
    """Reopen one exact v3 journal through its immutable O(1) indexes."""

    if intent_value.get("schema_version") != 2:
        return None
    intent, intent_sha256 = external_intent_identity(intent_value)
    indexed = load_intent_index(root, intent_sha256, committed=False)
    repaired = False
    active = state.get("active_transaction")
    head = state.get("head")
    state_record = next(
        (
            record
            for record in (active, head)
            if isinstance(record, dict)
            and record.get("intent_sha256") == intent_sha256
        ),
        None,
    )
    if indexed is None and isinstance(state_record, dict):
        transaction_id = str(state_record["transaction_id"])
        prepare, path, digest = publication._load_prepare(root, transaction_id)
        write_prepare_index(root, intent_sha256, transaction_id, path, digest)
        indexed = load_intent_index(root, intent_sha256, committed=False)
        repaired = True
    if indexed is None:
        return None
    transaction_id = str(indexed["transaction_id"])
    prepare, path, digest = publication._load_prepare(root, transaction_id)
    targets = prepare.get("targets")
    target = targets[0] if isinstance(targets, list) and len(targets) == 1 else {}
    if (
        indexed.get("prepare")
        != {"ref": path.relative_to(root).as_posix(), "sha256": digest}
        or prepare.get("schema_version") != 3
        or prepare.get("intent_sha256") != intent_sha256
        or prepare.get("source_decision") != intent["source_decision"]
        or prepare.get("task_state_plan") != intent["task_state_plan"]
        or target.get("payload_sha256") != intent["task_source"]["sha256"]
        or target.get("after_sha256") != intent["task_source"]["sha256"]
    ):
        raise ValueError("selection-publication prepared intent identity is inconsistent")
    committed = load_intent_index(root, intent_sha256, committed=True)
    receipt_path = publication._receipt_path(root, transaction_id)
    if committed is None and receipt_path.is_file():
        verified = publication.validate_receipt(
            root, transaction_id, require_current_targets=False
        )
        receipt_sha256 = str(verified["receipt_sha256"])
        active = state.get("active_transaction")
        current_head = state.get("head")
        if isinstance(active, dict) and active.get("transaction_id") == transaction_id:
            state = record_committed(
                root, state, prepare, digest, receipt_sha256
            )
            repaired = True
        elif (
            isinstance(current_head, dict)
            and current_head.get("transaction_id") == transaction_id
            and current_head.get("receipt")
            != {
                "ref": receipt_path.relative_to(root).as_posix(),
                "sha256": receipt_sha256,
            }
        ):
            raise ValueError("selection-publication compact head receipt differs")
        elif current_head is None:
            raise ValueError(
                "selection-publication committed intent is absent from compact state"
            )
        write_commit_index(
            root,
            intent_sha256,
            transaction_id,
            path,
            digest,
            receipt_path,
            receipt_sha256,
        )
        committed = load_intent_index(root, intent_sha256, committed=True)
        repaired = True
    active = state.get("active_transaction")
    head = state.get("head")
    if committed is not None:
        if (
            committed.get("transaction_id") != transaction_id
            or committed.get("prepare") != indexed.get("prepare")
        ):
            raise ValueError("selection-publication intent commit index differs")
        receipt_binding = committed.get("receipt")
        if not isinstance(receipt_binding, dict):
            raise ValueError("selection-publication intent commit receipt is invalid")
        if isinstance(active, dict) and active.get("transaction_id") == transaction_id:
            state = record_committed(
                root, state, prepare, digest, receipt_binding["sha256"]
            )
            repaired = True
        elif (
            isinstance(head, dict)
            and head.get("transaction_id") == transaction_id
            and head.get("receipt") != receipt_binding
        ):
            raise ValueError("selection-publication compact head receipt differs")
        elif head is None:
            raise ValueError(
                "selection-publication committed intent is absent from compact state"
            )
    elif not isinstance(active, dict) or active.get("transaction_id") != transaction_id:
        if active is not None:
            raise ValueError(
                "selection-publication prepared intent differs from bounded active transaction"
            )
        state = record_prepared(root, state, prepare, digest)
        repaired = True
    return prepare_response(
        root,
        transaction_id,
        path,
        digest,
        status="already_committed" if committed is not None else "prepared",
        mutation_performed=repaired,
        recovery_required=committed is None,
    )


def prepare_publication_intent(
    root: Path, intent: dict[str, Any]
) -> dict[str, Any]:
    """Compile and journal one compact v2 intent without inline payloads."""

    root = root.expanduser().resolve(strict=True)
    if intent.get("schema_version") != 2:
        raise ValueError(
            "Legacy schema-v1 selection publication intents are recovery-only "
            "and cannot compile new prepares"
        )
    with _lock(
        root,
        producer_capability=_SELECTION_PUBLICATION_PRODUCER_CAPABILITY,
    ):
        state = publication._load_or_initialize_state(root)
        replay = _prepared_external_intent_replay(root, intent, state)
        if replay is not None:
            return {**replay, "storage_schema_version": STORAGE_SCHEMA_VERSION}
        normalized, task_payload = compile_intent(root, intent)
        receipts = head_receipts(state)
        current_task_sha256 = _sha256_file(root / "task.md")
        pending = publication._state_pending_ids(state)
        replay = pending_replay(
            root,
            normalized,
            pending,
            load_prepare=publication._load_prepare,
        )
        if replay is not None:
            return {**replay, "storage_schema_version": STORAGE_SCHEMA_VERSION}
        replay = _committed_intent_replay(
            root, normalized, receipts, current_task_sha256
        )
        if replay is not None:
            return {**replay, "storage_schema_version": STORAGE_SCHEMA_VERSION}

        if normalized["publication_mode"] == "task_state_reconciliation":
            head = current_head_status(receipts, current_task_sha256)
            if head.get("status") != "drifted" or head.get("head_count") != 1:
                raise ValueError(
                    "task-state reconciliation requires one unique drifted selection head"
                )
            target = normalized["targets"][0]
            target["before_sha256"] = head["expected_task_sha256"]
            if target["after_sha256"] != current_task_sha256:
                raise ValueError(
                    "task-state reconciliation must bind exact current task.md bytes"
                )
            predecessor = head["head_transaction_id"]
        else:
            predecessor = new_predecessor_transaction_id(
                normalized, receipts, current_task_sha256
            )

        transaction_material = {
            **normalized,
            "predecessor_transaction_id": predecessor,
        }
        transaction_id = "selection-" + _sha256_bytes(
            _canonical_json(transaction_material)
        )
        prepare = {**transaction_material, "transaction_id": transaction_id}
        _blob, blob_sha256, blob_created = persist_blob(
            root,
            task_payload,
            producer_capability=_SELECTION_PUBLICATION_PRODUCER_CAPABILITY,
        )
        if blob_sha256 != normalized["targets"][0]["payload_sha256"]:
            raise ValueError("selection publication compiler produced another task blob")
        path = _prepare_path(root, transaction_id)
        digest = _write_once(
            path,
            _display_json(prepare),
            "selection-publication prepare journal",
            producer_capability=_SELECTION_PUBLICATION_PRODUCER_CAPABILITY,
        )
        publication._load_prepare(root, transaction_id)
        intent_sha256 = prepare.get("intent_sha256")
        if isinstance(intent_sha256, str):
            write_prepare_index(root, intent_sha256, transaction_id, path, digest)
        record_prepared(root, state, prepare, digest)
    return {
        **prepare_response(
            root,
            transaction_id,
            path,
            digest,
            status="prepared",
            mutation_performed=True,
            recovery_required=True,
        ),
        "storage_schema_version": STORAGE_SCHEMA_VERSION,
        "task_blob_created": blob_created,
        "task_payload_bytes": len(task_payload),
        "inline_payload_bytes": 0,
    }


__all__ = ("prepare_publication_intent",)
