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
from .selection_publication_v2 import compile_intent, persist_blob


_LOGICAL_INTENT_KEYS = (
    "schema_version",
    "kind",
    "selection_id",
    "source_decision_id",
    "source_decision_sha256",
    "source_decision",
    "publication_mode",
    "owner_assertions",
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


def prepare_publication_intent(
    root: Path, intent: dict[str, Any]
) -> dict[str, Any]:
    """Compile and journal one compact v2 intent without inline payloads."""

    root = root.expanduser().resolve(strict=True)
    with _lock(root):
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
