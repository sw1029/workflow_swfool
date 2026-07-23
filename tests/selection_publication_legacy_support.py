"""Private fixture builder for immutable v1 selection recovery tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from orchestrate_task_cycle import selection_publication as publication
from orchestrate_task_cycle.selection_decision_store import (
    normalize_binding,
    read_bound_bytes,
    read_bound_json,
)
from orchestrate_task_cycle.selection_publication_intent_index import (
    write_commit_index,
)
from orchestrate_task_cycle.selection_publication_intent_service import (
    _committed_intent_replay,
)
from orchestrate_task_cycle.selection_publication_payload import (
    persist_blob,
    task_id,
)
from orchestrate_task_cycle.selection_publication_producer_capability import (
    _SELECTION_PUBLICATION_PRODUCER_CAPABILITY,
)
from orchestrate_task_cycle.selection_publication_prepare import (
    committed_replay,
    new_predecessor_transaction_id,
    pending_replay,
    prepare_response,
)
from orchestrate_task_cycle.selection_publication_status import (
    current_head_status,
)
from orchestrate_task_cycle.selection_publication_state import (
    STORAGE_SCHEMA_VERSION,
    head_receipts,
    record_committed,
    record_prepared,
)
from orchestrate_task_cycle.selection_publication_v2 import (
    INTENT_KEYS,
    _closed,
    _selected_source,
    _transition_assertion,
)
from orchestrate_task_cycle.selection_publication_external import (
    task_event_matches,
)


def prepare_legacy_publication(
    root: Path, plan: dict[str, Any]
) -> dict[str, Any]:
    root = root.expanduser().resolve(strict=True)
    normalized = publication._normalize_plan(root, plan)
    with publication._lock(
        root,
        producer_capability=_SELECTION_PUBLICATION_PRODUCER_CAPABILITY,
    ):
        state = publication._load_or_initialize_state(root)
        pending = publication._state_pending_ids(state)
        replay = pending_replay(
            root, normalized, pending, load_prepare=publication._load_prepare
        )
        if replay is not None:
            return {**replay, "storage_schema_version": STORAGE_SCHEMA_VERSION}
        receipts = head_receipts(state)
        replay = committed_replay(
            root, normalized, receipts, load_prepare=publication._load_prepare
        )
        if replay is not None:
            return {**replay, "storage_schema_version": STORAGE_SCHEMA_VERSION}
        predecessor = new_predecessor_transaction_id(
            normalized, receipts, publication._sha256_file(root / "task.md")
        )
        material = {**normalized, "predecessor_transaction_id": predecessor}
        transaction_id = "selection-" + publication._sha256_bytes(
            publication._canonical_json(material)
        )
        prepare = {**material, "transaction_id": transaction_id}
        path = publication._prepare_path(root, transaction_id)
        digest = publication._write_once(
            path,
            publication._display_json(prepare),
            "selection-publication prepare journal",
            producer_capability=(
                _SELECTION_PUBLICATION_PRODUCER_CAPABILITY
            ),
        )
        publication._load_prepare(root, transaction_id)
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
    }


def seal_historical_legacy_publication_fixture(
    root: Path, plan: dict[str, Any]
) -> dict[str, Any]:
    """Materialize pre-retirement bytes for read/recovery consumer tests only."""

    prepared = prepare_legacy_publication(root, plan)
    transaction_id = str(prepared["transaction_id"])
    with publication._lock(
        root,
        producer_capability=_SELECTION_PUBLICATION_PRODUCER_CAPABILITY,
    ):
        state = publication._load_or_initialize_state(root)
        prepare, prepare_path, prepare_sha = publication._load_prepare(
            root, transaction_id
        )
        for target in prepare["targets"]:
            publication._atomic_write(
                publication._target_path(
                    root, target["role"], target["target_ref"]
                ),
                publication._decode_payload(target),
                producer_capability=_SELECTION_PUBLICATION_PRODUCER_CAPABILITY,
            )
        receipt = publication.receipt_for_prepare(
            root, prepare, prepare_path, prepare_sha, pending_binding=None
        )
        receipt_path = publication._receipt_path(root, transaction_id)
        receipt_sha = publication._write_once(
            receipt_path,
            publication._display_json(receipt),
            "historical selection-publication fixture receipt",
            producer_capability=_SELECTION_PUBLICATION_PRODUCER_CAPABILITY,
        )
        record_committed(root, state, prepare, prepare_sha, receipt_sha)
    return {
        **publication.validate_receipt(
            root, transaction_id, require_current_targets=True
        ),
        "transaction_id": transaction_id,
        "receipt_sha256": receipt_sha,
    }


def publish_legacy_prepared_fixture(
    root: Path, transaction_id: str
) -> dict[str, Any]:
    """Run the retired publisher only to materialize historical test fixtures."""

    root = root.expanduser().resolve(strict=True)
    receipt_path = publication._receipt_path(root, transaction_id)
    if receipt_path.is_file():
        return publication.publish_prepared(root, transaction_id)
    with publication._lock(
        root,
        producer_capability=_SELECTION_PUBLICATION_PRODUCER_CAPABILITY,
    ):
        state = publication._recover_state_for_transaction(root, transaction_id)
        prepare, prepare_path, prepare_sha = publication._load_prepare(
            root, transaction_id
        )
        publication._reject_competing_pending(state, transaction_id)
        publication.validate_publish_predecessor(
            prepare,
            head_receipts(state),
            publication._sha256_file(root / "task.md"),
        )
        if prepare.get("schema_version") == 2:
            for assertion in prepare["owner_assertions"]:
                publication.validate_owner_assertion(root, assertion)
        targets = list(prepare["targets"])
        for target in targets:
            path = publication._target_path(
                root, target["role"], target["target_ref"]
            )
            current = publication._sha256_file(path)
            if current not in {
                target.get("before_sha256"),
                target["after_sha256"],
            }:
                raise ValueError(
                    "selection-publication target drifted outside prepared states: "
                    + target["target_ref"]
                )
        for target in targets:
            path = publication._target_path(
                root, target["role"], target["target_ref"]
            )
            if publication._sha256_file(path) == target["after_sha256"]:
                continue
            payload = (
                publication.payload_for_target(root, target)
                if prepare.get("schema_version") == 2
                else publication._decode_payload(target)
            )
            publication._atomic_write(
                path,
                payload,
                producer_capability=_SELECTION_PUBLICATION_PRODUCER_CAPABILITY,
            )
        receipt = publication.receipt_for_prepare(
            root, prepare, prepare_path, prepare_sha, pending_binding=None
        )
        receipt_sha = publication._write_once(
            receipt_path,
            publication._display_json(receipt),
            "historical selection-publication fixture receipt",
            producer_capability=_SELECTION_PUBLICATION_PRODUCER_CAPABILITY,
        )
        verified = publication.validate_receipt(
            root, transaction_id, require_current_targets=True
        )
        record_committed(root, state, prepare, prepare_sha, receipt_sha)
        intent_sha256 = prepare.get("intent_sha256")
        if isinstance(intent_sha256, str):
            write_commit_index(
                root,
                intent_sha256,
                transaction_id,
                prepare_path,
                prepare_sha,
                receipt_path,
                receipt_sha,
            )
    return {
        **verified,
        "receipt_sha256": receipt_sha,
        "storage_schema_version": STORAGE_SCHEMA_VERSION,
        "mutation_performed": True,
        "authoritative_selection_published": True,
        "current_selection_authority_claimed": True,
        "publication_authority_status": "historical_fixture",
        "recovery_required": False,
    }


def _compile_legacy_intent_fixture(
    root: Path, raw: dict[str, Any]
) -> tuple[dict[str, Any], bytes]:
    intent = _closed(raw, INTENT_KEYS, "selection publication intent")
    if (
        intent.get("schema_version") != 1
        or intent.get("kind") != "selection_publication_intent"
        or not isinstance(intent.get("owner_receipts"), list)
    ):
        raise ValueError("selection publication intent contract is invalid")
    source_binding = normalize_binding(
        intent.get("source_decision"), "selection publication source decision"
    )
    _, source = read_bound_json(
        root, source_binding, "selection publication source decision"
    )
    task_binding_value = intent.get("task_source")
    owner_values = intent["owner_receipts"]
    if source.get("artifact_kind") == "selection_decision_receipt":
        source_binding, selected = _selected_source(root, source_binding)
        if task_binding_value is None or len(owner_values) != 1:
            raise ValueError(
                "selected publication requires one task source and one owner receipt"
            )
        task_binding = normalize_binding(
            task_binding_value, "selection task source"
        )
        _, task_payload = read_bound_bytes(
            root, task_binding, "selection task source"
        )
        selection_id = task_id(task_payload)
        if selection_id != selected.get("selected_task_id"):
            raise ValueError("selected task source differs from the decision task ID")
        assertion, plan = _transition_assertion(root, owner_values[0])
        if not task_event_matches(plan, selection_id, task_binding["sha256"]):
            raise ValueError(
                "task-state transition does not bind the exact selected task bytes"
            )
        owner_assertions = [assertion]
        source_decision_id = str(selected["receipt_id"])
        publication_mode = "selected_successor"
    elif source.get("receipt_kind") == "task_state_transition_apply_receipt":
        if task_binding_value is not None or owner_values:
            raise ValueError(
                "task-transition reconciliation requires no task or owner receipt"
            )
        assertion, plan = _transition_assertion(root, source_binding)
        task_path = root / "task.md"
        task_payload = task_path.read_bytes()
        selection_id = task_id(task_payload)
        current_sha = publication._sha256_file(task_path)
        if not task_event_matches(plan, selection_id, current_sha):
            raise ValueError(
                "task-transition reconciliation source does not bind current task.md"
            )
        owner_assertions = [assertion]
        source_decision_id = str(source["plan_id"])
        publication_mode = "task_state_reconciliation"
    else:
        raise ValueError("selection publication source decision kind is unsupported")
    task_sha = publication._sha256_bytes(task_payload)
    target = {
        "role": "task_alias",
        "target_ref": "task.md",
        "before_sha256": publication._sha256_file(root / "task.md"),
        "after_sha256": task_sha,
        "payload_ref": f".task/selection_publication/blobs/sha256/{task_sha}",
        "payload_sha256": task_sha,
        "payload_size": len(task_payload),
    }
    return (
        {
            "schema_version": 2,
            "kind": "selection_publication_prepare",
            "selection_id": selection_id,
            "source_decision_id": source_decision_id,
            "source_decision_sha256": source_binding["sha256"],
            "source_decision": source_binding,
            "publication_mode": publication_mode,
            "owner_assertions": owner_assertions,
            "targets": [target],
            "compiler_metrics": {
                "inline_payload_bytes": 0,
                "model_authored_mechanical_bytes": 0,
                "task_payload_bytes": len(task_payload),
            },
        },
        task_payload,
    )


def prepare_legacy_intent_fixture(
    root: Path, intent: dict[str, Any]
) -> dict[str, Any]:
    """Journal a retired schema-v2 prepare for historical protocol tests."""

    root = root.expanduser().resolve(strict=True)
    with publication._lock(
        root,
        producer_capability=_SELECTION_PUBLICATION_PRODUCER_CAPABILITY,
    ):
        state = publication._load_or_initialize_state(root)
        normalized, task_payload = _compile_legacy_intent_fixture(root, intent)
        receipts = head_receipts(state)
        current_task_sha256 = publication._sha256_file(root / "task.md")
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
                    "task-state reconciliation requires one unique drifted head"
                )
            target = normalized["targets"][0]
            target["before_sha256"] = head["expected_task_sha256"]
            if target["after_sha256"] != current_task_sha256:
                raise ValueError(
                    "task-state reconciliation must bind exact current task.md"
                )
            predecessor = head["head_transaction_id"]
        else:
            predecessor = new_predecessor_transaction_id(
                normalized, receipts, current_task_sha256
            )
        material = {**normalized, "predecessor_transaction_id": predecessor}
        transaction_id = "selection-" + publication._sha256_bytes(
            publication._canonical_json(material)
        )
        prepare = {**material, "transaction_id": transaction_id}
        _blob, blob_sha256, blob_created = persist_blob(
            root,
            task_payload,
            producer_capability=_SELECTION_PUBLICATION_PRODUCER_CAPABILITY,
        )
        if blob_sha256 != normalized["targets"][0]["payload_sha256"]:
            raise ValueError("legacy fixture compiler produced another task blob")
        path = publication._prepare_path(root, transaction_id)
        digest = publication._write_once(
            path,
            publication._display_json(prepare),
            "historical selection-publication fixture prepare",
            producer_capability=_SELECTION_PUBLICATION_PRODUCER_CAPABILITY,
        )
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


def recover_legacy_publications_fixture(
    root: Path, transaction_id: str | None = None
) -> dict[str, Any]:
    identifiers = (
        [transaction_id]
        if transaction_id is not None
        else publication.pending_transaction_ids(root)
    )
    if transaction_id is None and len(identifiers) > 1:
        raise ValueError(
            "selection-publication has competing pending transactions; "
            "automatic recovery cannot choose an authoritative selection"
        )
    receipts = [
        publish_legacy_prepared_fixture(root, identifier)
        for identifier in identifiers
    ]
    return {
        "status": "recovered" if receipts else "no_op",
        "recovered_count": len(receipts),
        "receipts": receipts,
        "remaining_pending_transaction_ids": publication.pending_transaction_ids(
            root
        ),
        "mutation_performed": bool(receipts),
    }


__all__ = (
    "prepare_legacy_publication",
    "prepare_legacy_intent_fixture",
    "publish_legacy_prepared_fixture",
    "recover_legacy_publications_fixture",
    "seal_historical_legacy_publication_fixture",
)
