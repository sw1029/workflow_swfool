"""Semantic validators for exact normal-cycle selection trigger evidence.

The trigger seal binds bytes.  This module owns the separate question of whether
those bytes are the current, cycle-coherent owner artifacts that the trigger is
allowed to bind.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .ledger.finalization import verify_finalization_receipt
from .selection_decision_store import (
    canonical_sha256,
    closed_object,
    normalize_binding,
    read_bound_json,
)


BOOTSTRAP_KEYS = {
    "schema_version",
    "artifact_kind",
    "bootstrap_id",
    "cycle_id",
    "publication_status",
    "current_task",
    "task_index",
    "not_goal_truth",
    "not_authority",
    "not_validation_evidence",
    "mutation_performed",
    "bootstrap_sha256",
}
PASS_STATUSES = frozenset({"pass", "complete", "completed"})


def _cycle_ref(cycle_id: str, ref: str, label: str) -> None:
    prefix = f".task/cycle/{cycle_id}/"
    if not ref.startswith(prefix):
        raise ValueError(f"normal-cycle {label} must be scoped to the selected cycle")


def _canonical_owner_ref(binding: dict[str, str], expected: str, label: str) -> None:
    if binding["ref"] != expected:
        raise ValueError(f"normal-cycle {label} must use canonical ref {expected}")


def validate_cycle_finalization(
    root: Path, cycle_id: str, binding: dict[str, str]
) -> None:
    expected_ref = f".task/cycle/{cycle_id}/current_finalization.json"
    _canonical_owner_ref(binding, expected_ref, "cycle finalization")
    _, pointer = read_bound_json(root, binding, "cycle finalization pointer")
    if (
        pointer.get("kind") != "cycle_finalization_pointer"
        or pointer.get("cycle_id") != cycle_id
        or not isinstance(pointer.get("receipt"), dict)
    ):
        raise ValueError("normal-cycle finalization pointer is wrong-kind or wrong-cycle")
    # The finalization owner verifies the immutable snapshot, current pointer,
    # committed state, and receipt lineage.  A committed `authoritative_final`
    # of blocked is deliberately valid here: selection may be the remaining gap.
    verified = verify_finalization_receipt(root, cycle_id, pointer["receipt"])
    receipt = verified["receipt"]
    if receipt.get("state_commit_status") != "committed":
        raise ValueError("normal-cycle finalization is not committed")


def validate_schema_pre_derive(
    root: Path, cycle_id: str, binding: dict[str, str]
) -> None:
    _cycle_ref(cycle_id, binding["ref"], "schema-pre-derive result")
    _, result = read_bound_json(root, binding, "schema-pre-derive result")
    status = str(result.get("status") or "").strip().lower()
    schema_status = str(result.get("schema_status") or "").strip().lower()
    if (
        result.get("step") != "schema_pre_derive"
        or result.get("cycle_id") != cycle_id
        or status not in PASS_STATUSES
        or schema_status not in PASS_STATUSES
    ):
        raise ValueError(
            "normal-cycle schema-pre-derive result must be cycle-bound and pass/complete"
        )


def validate_derive_result(
    root: Path,
    cycle_id: str,
    binding: dict[str, str],
    input_evidence_manifest_sha256: str,
) -> None:
    _cycle_ref(cycle_id, binding["ref"], "derive result")
    _, result = read_bound_json(root, binding, "derive result")
    if result.get("step") != "derive" or result.get("cycle_id") != cycle_id:
        raise ValueError("normal-cycle derive result is wrong-kind or wrong-cycle")

    # Re-run the derive projection validator rather than trusting an arbitrary
    # JSON file that merely labels itself as a derive result.
    from .selection_synthesis import render_selection_synthesis

    synthesis = render_selection_synthesis(root, result)
    if synthesis["input_evidence_manifest_sha256"] != input_evidence_manifest_sha256:
        raise ValueError("normal-cycle derive evidence manifest binding differs")


def validate_current_owner_bindings(
    _root: Path,
    current_task: dict[str, str],
    task_index: dict[str, str],
) -> None:
    _canonical_owner_ref(current_task, "task.md", "current task")
    _canonical_owner_ref(task_index, ".task/index.jsonl", "task index")
    # Exact byte reads are performed by the trigger binder.  The index is JSONL,
    # so treating the whole owner artifact as one JSON value would be incorrect.


def _publication_status(root: Path) -> dict[str, Any]:
    # Lazy import keeps trigger validation out of the publication compiler's
    # module-import cycle.
    from .selection_publication import publication_status

    return publication_status(root, deep=True)


def _assert_uninitialized_publication(root: Path) -> None:
    status = _publication_status(root)
    head = status.get("current_head")
    if (
        status.get("status") != "clear"
        or status.get("pending_transaction_ids") != []
        or status.get("selection_journal_initialized") is not False
        or not isinstance(head, dict)
        or head.get("status") != "not_initialized"
        or head.get("head_count") != 0
    ):
        raise ValueError(
            "normal-cycle publication bootstrap requires a truly uninitialized journal"
        )


def render_publication_bootstrap(
    root: Path,
    *,
    cycle_id: str,
    current_task: dict[str, str],
    task_index: dict[str, str],
) -> dict[str, Any]:
    """Render the sole compiler-owned substitute for an uninitialized head."""

    root = root.expanduser().resolve(strict=True)
    task = normalize_binding(current_task, "current task")
    index = normalize_binding(task_index, "task index")
    validate_current_owner_bindings(root, task, index)
    _assert_uninitialized_publication(root)
    core = {
        "schema_version": 1,
        "artifact_kind": "normal_cycle_selection_publication_bootstrap",
        "cycle_id": cycle_id,
        "publication_status": "not_initialized",
        "current_task": task,
        "task_index": index,
        "not_goal_truth": True,
        "not_authority": True,
        "not_validation_evidence": True,
        "mutation_performed": False,
    }
    bootstrap_id = "selection-publication-bootstrap-" + canonical_sha256(core)[:24]
    body = {**core, "bootstrap_id": bootstrap_id}
    return {**body, "bootstrap_sha256": canonical_sha256(body)}


def validate_publication_bootstrap(
    root: Path,
    cycle_id: str,
    current_task: dict[str, str],
    task_index: dict[str, str],
    value: Any,
) -> dict[str, Any]:
    bootstrap = closed_object(
        value, BOOTSTRAP_KEYS, "normal-cycle publication bootstrap"
    )
    expected = render_publication_bootstrap(
        root,
        cycle_id=cycle_id,
        current_task=current_task,
        task_index=task_index,
    )
    if bootstrap != expected:
        raise ValueError("normal-cycle publication bootstrap integrity failed")
    return expected


def _validate_committed_publication_head(
    root: Path,
    binding: dict[str, str],
    current_task: dict[str, str],
    receipt: dict[str, Any],
) -> None:
    from .selection_publication import validate_receipt

    status = _publication_status(root)
    head = status.get("current_head")
    transaction_id = receipt.get("transaction_id")
    if (
        status.get("status") != "clear"
        or status.get("pending_transaction_ids") != []
        or not isinstance(head, dict)
        or head.get("status") != "current"
        or head.get("head_count") != 1
        or transaction_id != head.get("head_transaction_id")
        or head.get("current_task_sha256") != current_task["sha256"]
        or head.get("expected_task_sha256") != current_task["sha256"]
    ):
        raise ValueError(
            "normal-cycle publication head is not the unique current committed head"
        )
    expected_ref = f".task/selection_publication/receipts/{transaction_id}.json"
    _canonical_owner_ref(binding, expected_ref, "publication head")
    verified = validate_receipt(
        root, str(transaction_id), require_current_targets=True
    )
    if (
        verified.get("status") != "committed"
        or verified.get("receipt_ref") != binding["ref"]
        or verified.get("receipt_sha256") != binding["sha256"]
    ):
        raise ValueError("normal-cycle publication head receipt binding differs")


def validate_publication_head(
    root: Path,
    cycle_id: str,
    binding: dict[str, str],
    current_task: dict[str, str],
    task_index: dict[str, str],
) -> None:
    _, value = read_bound_json(root, binding, "normal-cycle publication head")
    if value.get("artifact_kind") == "normal_cycle_selection_publication_bootstrap":
        _cycle_ref(cycle_id, binding["ref"], "publication bootstrap")
        validate_publication_bootstrap(
            root, cycle_id, current_task, task_index, value
        )
        return
    if value.get("kind") == "selection_publication_receipt":
        _validate_committed_publication_head(root, binding, current_task, value)
        return
    raise ValueError(
        "normal-cycle publication head must be a committed receipt or compiler bootstrap"
    )


__all__ = (
    "render_publication_bootstrap",
    "validate_current_owner_bindings",
    "validate_cycle_finalization",
    "validate_derive_result",
    "validate_publication_head",
    "validate_schema_pre_derive",
)
