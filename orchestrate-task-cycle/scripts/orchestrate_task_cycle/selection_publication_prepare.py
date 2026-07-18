"""Prepare replay and explicit predecessor decisions for selection publication."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Sequence

from .selection_publication_status import current_head_status


PrepareLoader = Callable[[Path, str], tuple[dict[str, Any], Path, str]]


def base_plan_matches(normalized: dict[str, Any], prepare: dict[str, Any]) -> bool:
    return all(prepare.get(key) == value for key, value in normalized.items())


def prepare_response(
    root: Path,
    transaction_id: str,
    path: Path,
    digest: str,
    *,
    status: str,
    mutation_performed: bool,
    recovery_required: bool,
) -> dict[str, Any]:
    return {
        "status": status,
        "transaction_id": transaction_id,
        "prepare_ref": path.relative_to(root).as_posix(),
        "prepare_sha256": digest,
        "mutation_performed": mutation_performed,
        "authoritative_selection_published": False,
        "recovery_required": recovery_required,
    }


def pending_replay(
    root: Path,
    normalized: dict[str, Any],
    pending: list[str],
    *,
    load_prepare: PrepareLoader,
) -> dict[str, Any] | None:
    if not pending:
        return None
    if len(pending) != 1:
        raise ValueError(
            "selection-publication has competing pending transactions; "
            "no prepare replay can choose an authoritative selection"
        )
    prepare, path, digest = load_prepare(root, pending[0])
    if not base_plan_matches(normalized, prepare):
        raise ValueError(
            "selection-publication has a different pending transaction; "
            "recover it before preparing or publishing new selection work"
        )
    return prepare_response(
        root,
        pending[0],
        path,
        digest,
        status="prepared",
        mutation_performed=False,
        recovery_required=True,
    )


def committed_replay(
    root: Path,
    normalized: dict[str, Any],
    receipts: Sequence[dict[str, Any]],
    *,
    load_prepare: PrepareLoader,
) -> dict[str, Any] | None:
    matches: list[tuple[str, Path, str]] = []
    for receipt in receipts:
        transaction_id = str(receipt["transaction_id"])
        prepare, path, digest = load_prepare(root, transaction_id)
        if base_plan_matches(normalized, prepare):
            matches.append((transaction_id, path, digest))
    if len(matches) > 1:
        raise ValueError("selection-publication exact committed replay is ambiguous")
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


def _task_alias_before(normalized: dict[str, Any]) -> str | None:
    target = next(
        target for target in normalized["targets"] if target["role"] == "task_alias"
    )
    value = target.get("before_sha256")
    return str(value) if value is not None else None


def new_predecessor_transaction_id(
    normalized: dict[str, Any],
    receipts: Sequence[dict[str, Any]],
    current_task_sha256: str | None,
) -> str | None:
    head = current_head_status(receipts, current_task_sha256)
    if head["status"] not in {"not_initialized", "current"}:
        raise ValueError(
            "selection-publication committed head is drifted or ambiguous; "
            "repair it before preparing new selection work"
        )
    if _task_alias_before(normalized) != current_task_sha256:
        raise ValueError(
            "new selection-publication task_alias before_sha256 must match the current committed head and task.md digest"
        )
    return str(head["head_transaction_id"]) if head["status"] == "current" else None


def validate_publish_predecessor(
    prepare: dict[str, Any],
    receipts: Sequence[dict[str, Any]],
    current_task_sha256: str | None,
) -> None:
    if "predecessor_transaction_id" not in prepare:
        if receipts:
            raise ValueError(
                "legacy selection-publication prepare cannot extend an initialized journal without explicit lineage"
            )
        return
    predecessor = prepare.get("predecessor_transaction_id")
    if predecessor is None:
        if receipts:
            raise ValueError(
                "selection-publication root prepare conflicts with committed history"
            )
        return
    head = current_head_status(receipts, current_task_sha256)
    if head.get("head_transaction_id") != predecessor or head.get("status") in {
        "not_initialized",
        "ambiguous",
    }:
        raise ValueError(
            "selection-publication prepared predecessor is no longer the unique committed head"
        )


__all__ = (
    "committed_replay",
    "new_predecessor_transaction_id",
    "pending_replay",
    "prepare_response",
    "validate_publish_predecessor",
)
