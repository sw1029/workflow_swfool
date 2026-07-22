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
    TRANSACTION_ID,
    _canonical_json,
    _display_json,
    _lock,
    _prepare_path,
    _sha256_bytes,
    _sha256_file,
    _transactions_root,
    _write_once,
)
from .selection_decision_store import read_bound_bytes
from .selection_publication_v2 import (
    compile_intent,
    external_intent_identity,
    persist_blob,
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
    root: Path, intent_value: dict[str, Any]
) -> dict[str, Any] | None:
    """Reopen one exact v3 journal without revalidating stale trigger dependencies."""

    if intent_value.get("schema_version") != 2:
        return None
    intent, intent_sha256 = external_intent_identity(intent_value)
    for field, label in (
        ("source_decision", "selection publication source decision"),
        ("task_source", "selection task source"),
        ("task_state_plan", "prospective task-state transition plan"),
    ):
        read_bound_bytes(root, intent[field], label)

    directory = _transactions_root(root)
    identifiers = (
        sorted(
            child.name
            for child in directory.iterdir()
            if child.is_dir()
            and not child.is_symlink()
            and TRANSACTION_ID.fullmatch(child.name)
            and (child / "prepare.json").is_file()
            and not (child / "prepare.json").is_symlink()
        )
        if directory.is_dir()
        else []
    )
    matches: list[tuple[str, Path, str]] = []
    for transaction_id in identifiers:
        prepare, path, digest = publication._load_prepare(root, transaction_id)
        targets = prepare.get("targets")
        target = targets[0] if isinstance(targets, list) and len(targets) == 1 else {}
        if prepare.get("schema_version") == 3 and prepare.get(
            "intent_sha256"
        ) == intent_sha256:
            if (
                prepare.get("source_decision") != intent["source_decision"]
                or prepare.get("task_state_plan") != intent["task_state_plan"]
                or target.get("payload_sha256") != intent["task_source"]["sha256"]
                or target.get("after_sha256") != intent["task_source"]["sha256"]
            ):
                raise ValueError(
                    "selection-publication prepared intent identity is inconsistent"
                )
            matches.append((transaction_id, path, digest))
    if len(matches) > 1:
        raise ValueError("selection-publication prepared intent replay is ambiguous")
    if not matches:
        return None

    pending = publication.pending_transaction_ids(root)
    transaction_id, path, digest = matches[0]
    if pending and pending != [transaction_id]:
        raise ValueError(
            "selection-publication has a competing pending transaction; exact intent replay cannot choose it"
        )
    committed = _sha256_file(
        root / f".task/selection_publication/receipts/{transaction_id}.json"
    )
    if not pending and committed is None:
        raise ValueError("selection-publication prepared intent lifecycle is incomplete")
    return prepare_response(
        root,
        transaction_id,
        path,
        digest,
        status="prepared" if pending else "already_committed",
        mutation_performed=False,
        recovery_required=bool(pending),
    )


def prepare_publication_intent(
    root: Path, intent: dict[str, Any]
) -> dict[str, Any]:
    """Compile and journal one compact v2 intent without inline payloads."""

    root = root.expanduser().resolve(strict=True)
    with _lock(root):
        replay = _prepared_external_intent_replay(root, intent)
        if replay is not None:
            if publication._repair_state_if_needed(root):
                replay = {
                    **replay,
                    "mutation_performed": True,
                    "compact_state_repaired": True,
                }
            return {**replay, "storage_schema_version": 3}
        normalized, task_payload = compile_intent(root, intent)
        receipts = publication._committed_receipts(root)
        current_task_sha256 = _sha256_file(root / "task.md")
        pending = publication.pending_transaction_ids(root)
        replay = pending_replay(
            root,
            normalized,
            pending,
            load_prepare=publication._load_prepare,
        )
        if replay is not None:
            if publication._repair_state_if_needed(root):
                replay = {
                    **replay,
                    "mutation_performed": True,
                    "compact_state_repaired": True,
                }
            return {**replay, "storage_schema_version": 2}
        replay = _committed_intent_replay(
            root, normalized, receipts, current_task_sha256
        )
        if replay is not None:
            if publication._repair_state_if_needed(root):
                replay = {
                    **replay,
                    "mutation_performed": True,
                    "compact_state_repaired": True,
                }
            return {**replay, "storage_schema_version": 2}

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
        _blob, blob_sha256, blob_created = persist_blob(root, task_payload)
        if blob_sha256 != normalized["targets"][0]["payload_sha256"]:
            raise ValueError("selection publication compiler produced another task blob")
        path = _prepare_path(root, transaction_id)
        digest = _write_once(
            path, _display_json(prepare), "selection-publication prepare journal"
        )
        publication._load_prepare(root, transaction_id)
        publication._refresh_state(root)
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
        "storage_schema_version": 2,
        "task_blob_created": blob_created,
        "task_payload_bytes": len(task_payload),
        "inline_payload_bytes": 0,
    }


__all__ = ("prepare_publication_intent",)
