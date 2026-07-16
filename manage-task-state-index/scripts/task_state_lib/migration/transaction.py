"""Crash-safe migration publication and forward recovery transaction."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Callable, ContextManager

from .contracts import (
    ANCHOR_KIND,
    MIGRATION_EVENT_FIELD,
    MigrationError,
)
from .graph import _find_anchor_lines, _matching_plan_anchor, _validate_journal_base
from .plan import _plan_manifest, _validate_plan_contract
from .storage import (
    _atomic_json,
    _atomic_write,
    _canonical_bytes,
    _event_bytes,
    _fsync_dir,
    _index_lock,
    _index_path,
    _now,
    _read_json,
    _safe_ref,
    _sha256,
    _sha_file,
    _validate_plan_anchors,
)
from .publication import (
    _anchor_event,
    _committed_journal_payload,
    _completion_marker_payload,
    _receipt_payload,
    _render_markdown,
)
from .validation import (
    _forward_complete_anchored,
    _normalized_events_from_plan,
    _validate_receipt_graph,
    load_sealed_events_if_present,
)

def _crash(point: str) -> None:
    if os.environ.get("TASK_STATE_MIGRATION_CRASH_AT") == point:
        raise RuntimeError(f"injected crash at {point}")


def _append_fsync(path: Path, payload: bytes) -> None:
    with path.open("ab", buffering=0) as handle:
        handle.write(payload)
        os.fsync(handle.fileno())
    _fsync_dir(path.parent)


def _stage_sidecars(
    root: Path, plan: dict[str, Any], plan_bytes: bytes, mapping_bytes: bytes,
    prefix: bytes, *, allow_existing_journal: bool,
) -> tuple[Path, dict[str, Any], str, dict[str, Any] | None]:
    tx_dir = _safe_ref(root, plan["transaction_directory_ref"], must_exist=False)
    if tx_dir.exists() and tx_dir.is_symlink():
        raise MigrationError("Unsafe migration transaction directory")
    tx_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "source": _safe_ref(root, plan["source_snapshot_ref"], must_exist=False),
        "plan": _safe_ref(root, plan["plan_snapshot_ref"], must_exist=False),
        "mapping": _safe_ref(root, plan["mapping_manifest"]["snapshot_ref"], must_exist=False),
        "manifest": _safe_ref(root, plan["resolution_manifest"]["ref"], must_exist=False),
        "correction": _safe_ref(root, plan["correction_suffix"]["ref"], must_exist=False),
        "prepare_journal": _safe_ref(root, plan["prepare_journal_ref"], must_exist=False),
        "journal": _safe_ref(root, plan["journal_ref"], must_exist=False),
    }
    manifest_bytes = _canonical_bytes(_plan_manifest(plan))
    joiner = b"\n" if prefix and not prefix.endswith(b"\n") else b""
    correction_bytes = joiner + _event_bytes(plan["correction_events"])
    for key, payload in (
        ("source", prefix), ("plan", plan_bytes), ("mapping", mapping_bytes),
        ("manifest", manifest_bytes), ("correction", correction_bytes),
    ):
        path = paths[key]
        if path.exists() and path.read_bytes() != payload:
            raise MigrationError(f"Conflicting existing migration sidecar: {path}")
        if not path.exists():
            _atomic_write(path, payload)
    prepare = {
        "schema_version": 1, "kind": "task_state_index_migration_journal_prepare",
        "transaction_id": plan["migration_id"], "state": "prepared",
        "prefix_sha256": plan["source_prefix"]["sha256"],
        "prefix_byte_length": plan["source_prefix"]["byte_length"],
        "expected_boundary_sha256": plan["expected_after_index_sha256"],
        "expected_boundary_byte_length": plan["expected_commit_boundary_byte_length"],
        "plan_ref": plan["plan_snapshot_ref"], "plan_sha256": _sha256(plan_bytes),
    }
    prepare_bytes = _canonical_bytes(prepare)
    if paths["prepare_journal"].exists() and paths["prepare_journal"].read_bytes() != prepare_bytes:
        raise MigrationError("Conflicting prepare journal")
    if not paths["prepare_journal"].exists():
        _atomic_write(paths["prepare_journal"], prepare_bytes)
    existing_journal: dict[str, Any] | None = None
    if paths["journal"].exists():
        if not allow_existing_journal:
            raise MigrationError("Existing migration journal requires explicit recover")
        existing_journal = _read_json(paths["journal"], "migration journal")
        _validate_journal_base(existing_journal, prepare)
    else:
        _atomic_json(paths["journal"], {**prepare, "journal_updated_at": _now()})
    return paths["journal"], prepare, _sha256(prepare_bytes), existing_journal


def _update_journal(path: Path, prepare: dict[str, Any], state: str, **fields: Any) -> None:
    _atomic_json(path, {**prepare, "state": state, "journal_updated_at": _now(), **fields})


def _validate_partial_tail_ownership(
    tail: bytes, boundary_tail: bytes, journal: dict[str, Any] | None,
) -> None:
    if journal is None or journal.get("state") != "partial_suffix":
        raise MigrationError("Unsealed tail lacks an existing partial-suffix journal")
    appended_length = journal.get("appended_byte_length")
    appended_sha = journal.get("appended_sha256")
    if appended_length != len(tail) or appended_sha != _sha256(tail):
        raise MigrationError("Partial-suffix journal does not bind the exact appended tail")
    if not tail or len(tail) >= len(boundary_tail) or not boundary_tail.startswith(tail):
        raise MigrationError("Unsealed tail is not an exact prefix of the journal-owned boundary payload")


def _committed_for_plan(root: Path, payload: bytes, plan: dict[str, Any]) -> dict[str, Any] | None:
    matching = _matching_plan_anchor(payload, plan)
    if matching is None:
        return None
    events, _results, receipt = _validate_receipt_graph(root, payload, *matching)
    return {"idempotent": True, "receipt": receipt, "event_count": len(events)}

def _preflight_locked_apply(
    root: Path,
    plan: dict[str, Any],
    recovery_status: str,
) -> tuple[Path, bytes, dict[str, Any] | None]:
    index = _index_path(root)
    current = index.read_bytes()
    try:
        committed = _committed_for_plan(root, current, plan)
    except MigrationError:
        if (
            recovery_status == "forward_completed"
            and _matching_plan_anchor(current, plan) is not None
        ):
            result = _forward_complete_anchored(root, plan, current)
            return index, b"", result
        raise
    if committed is not None:
        if recovery_status == "forward_completed":
            receipt = committed["receipt"]
            render_snapshot = _safe_ref(root, receipt["rendered_index_ref"])
            _atomic_write(root / ".task" / "index.md", render_snapshot.read_bytes())
            committed["recovery_status"] = "forward_completed"
        return index, b"", committed
    prefix_len = plan["source_prefix"]["byte_length"]
    prefix_sha = plan["source_prefix"]["sha256"]
    if len(current) < prefix_len or _sha256(current[:prefix_len]) != prefix_sha:
        raise MigrationError("Source prefix drift prevents migration or recovery")
    prefix = current[:prefix_len]
    if recovery_status != "forward_completed" and current != prefix:
        raise MigrationError("Initial apply requires the exact planned source prefix")
    if len(current) > prefix_len and not current.startswith(
        _safe_ref(root, plan["source_snapshot_ref"]).read_bytes()
    ):
        raise MigrationError("Index does not retain the planned source prefix")
    return index, prefix, None


def _publish_seal_boundary(
    root: Path,
    plan: dict[str, Any],
    plan_bytes: bytes,
    mapping_bytes: bytes,
    index: Path,
    prefix: bytes,
    recovery_status: str,
) -> tuple[Path, dict[str, Any], str]:
    journal_path, prepare, prepare_sha, existing_journal = _stage_sidecars(
        root,
        plan,
        plan_bytes,
        mapping_bytes,
        prefix,
        allow_existing_journal=recovery_status == "forward_completed",
    )
    _crash("after_prepare")
    correction = _safe_ref(root, plan["correction_suffix"]["ref"]).read_bytes()
    boundary_tail = correction + _canonical_bytes(plan["seal"]["event"])
    boundary = prefix + boundary_tail
    current = index.read_bytes()
    if current == prefix:
        if os.environ.get("TASK_STATE_MIGRATION_CRASH_AT") == "after_partial_suffix":
            partial = boundary_tail[: max(1, len(boundary_tail) // 2)]
            _append_fsync(index, partial)
            _update_journal(
                journal_path,
                prepare,
                "partial_suffix",
                appended_byte_length=len(partial),
                appended_sha256=_sha256(partial),
            )
            _crash("after_partial_suffix")
        _append_fsync(index, boundary_tail)
    elif current != boundary and current.startswith(prefix) and len(current) < len(boundary):
        if recovery_status != "forward_completed":
            raise MigrationError(
                "Initial apply refuses a non-prefix source tail; use explicit recover"
            )
        tail = current[len(prefix):]
        _validate_partial_tail_ownership(tail, boundary_tail, existing_journal)
        with index.open("r+b") as handle:
            handle.truncate(len(prefix))
            handle.flush()
            os.fsync(handle.fileno())
        _append_fsync(index, boundary_tail)
    elif current != boundary:
        raise MigrationError("Conflicting tail prevents migration recovery")
    if _sha256(index.read_bytes()[: len(boundary)]) != plan["expected_after_index_sha256"]:
        raise MigrationError("Published seal boundary digest mismatch")
    _update_journal(journal_path, prepare, "sealed")
    _crash("after_suffix")
    return journal_path, prepare, prepare_sha


def _publish_receipt_graph(
    root: Path,
    plan: dict[str, Any],
    plan_bytes: bytes,
    mapping_bytes: bytes,
    index: Path,
    journal_path: Path,
    prepare: dict[str, Any],
    prepare_sha: str,
    recovery_status: str,
) -> dict[str, Any]:
    events = _normalized_events_from_plan(root, plan, mapping_bytes)
    placeholder = _anchor_event(plan, "0" * 64)
    render = _render_markdown(
        events + plan["correction_events"] + [plan["seal"]["event"], placeholder],
        plan["effective_at"],
    )
    _atomic_write(_safe_ref(root, plan["render_snapshot_ref"], must_exist=False), render)
    committed_at = _now()
    journal = _committed_journal_payload(
        plan, prepare, committed_at, _sha256(render), recovery_status
    )
    journal_bytes = _canonical_bytes(journal)
    marker = _completion_marker_payload(
        plan,
        prepare_sha,
        _sha256(journal_bytes),
        _sha256(render),
        recovery_status,
        committed_at,
        _sha256(plan_bytes),
    )
    marker_bytes = _canonical_bytes(marker)
    receipt = _receipt_payload(
        plan,
        _sha256(plan_bytes),
        prepare_sha,
        _sha256(journal_bytes),
        _sha256(marker_bytes),
        _sha256(render),
        recovery_status,
        committed_at,
    )
    receipt_path = _safe_ref(root, plan["receipt_ref"], must_exist=False)
    receipt_bytes = _canonical_bytes(receipt)
    _atomic_write(receipt_path, receipt_bytes)
    receipt_sha = _sha256(receipt_bytes)
    _update_journal(journal_path, prepare, "receipt_written", receipt_sha256=receipt_sha)
    _crash("after_receipt")
    _crash("after_receipt_before_marker")
    anchor = _anchor_event(
        plan, receipt_sha, _sha256(journal_bytes), _sha256(marker_bytes)
    )
    anchor_present = any(
        isinstance(value, dict)
        and isinstance(value.get("fields"), dict)
        and value["fields"].get(MIGRATION_EVENT_FIELD) == ANCHOR_KIND
        and value["fields"].get("migration_id") == plan["migration_id"]
        and value["fields"].get("receipt_sha256") == receipt_sha
        for _offset, _raw, value in _find_anchor_lines(index.read_bytes())
    )
    if not anchor_present:
        _append_fsync(index, _canonical_bytes(anchor))
    _update_journal(journal_path, prepare, "receipt_anchored", receipt_sha256=receipt_sha)
    _crash("after_anchor")
    _atomic_write(journal_path, journal_bytes)
    completion_marker = _safe_ref(root, plan["completion_marker_ref"], must_exist=False)
    if completion_marker.exists() and completion_marker.read_bytes() != marker_bytes:
        raise MigrationError("Conflicting immutable migration completion marker")
    if not completion_marker.exists():
        _atomic_write(completion_marker, marker_bytes)
    _crash("after_completion_marker_before_render")
    _atomic_write(root / ".task" / "index.md", render)
    _crash("after_render")
    loaded = load_sealed_events_if_present(root)
    if loaded is None:
        raise MigrationError("Committed migration was not accepted by the strict sealed reader")
    return {
        "idempotent": False,
        "transaction_id": plan["migration_id"],
        "receipt_ref": plan["receipt_ref"],
        "receipt_sha256": receipt_sha,
        "commit_boundary_sha256": plan["expected_after_index_sha256"],
        "final_index_sha256": _sha_file(index),
        "event_count": len(loaded[0]),
        "recovery_status": recovery_status,
    }


def _apply_locked(
    root: Path,
    plan: dict[str, Any],
    plan_bytes: bytes,
    mapping_bytes: bytes,
    *,
    recovery_status: str,
) -> dict[str, Any]:
    index, prefix, terminal = _preflight_locked_apply(root, plan, recovery_status)
    if terminal is not None:
        return terminal
    journal_path, prepare, prepare_sha = _publish_seal_boundary(
        root, plan, plan_bytes, mapping_bytes, index, prefix, recovery_status
    )
    return _publish_receipt_graph(
        root,
        plan,
        plan_bytes,
        mapping_bytes,
        index,
        journal_path,
        prepare,
        prepare_sha,
        recovery_status,
    )

def apply_plan(
    root: Path, plan_path: Path, expected_plan_sha: str, expected_index_sha: str,
    *, dry_run: bool = False, recovery_status: str = "not_required",
    _index_lock_fn: Callable[[Path], ContextManager[None]] = _index_lock,
) -> dict[str, Any]:
    root = root.resolve()
    plan, plan_bytes, _mapping, mapping_bytes = _validate_plan_contract(
        root, plan_path.resolve(strict=True), expected_plan_sha, expected_index_sha,
    )
    if plan.get("unclassified_count") != 0:
        raise MigrationError("Migration apply requires unclassified_count=0")
    projection = plan.get("projection", {})
    required = {
        "active_task_count": 1, "active_pack_count": 1,
        "duplicate_active_alias_count": 0, "current_broken_link_count": 0,
        "current_surface_blocker_count": 0,
    }
    if any(projection.get(key) != value for key, value in required.items()) or projection.get("projection_completeness") != "complete":
        raise MigrationError("Migration plan does not reconcile the current projection")
    if dry_run:
        current = _index_path(root).read_bytes()
        if _sha256(current) != expected_index_sha:
            raise MigrationError("Source drift before dry-run")
        _validate_plan_anchors(root, plan)
        return {
            "dry_run": True, "mutation_performed": False,
            "transaction_id": plan["migration_id"], "plan_sha256": expected_plan_sha,
            "expected_commit_boundary_sha256": plan["expected_after_index_sha256"],
            "projection": projection,
        }
    _validate_plan_anchors(root, plan)
    with _index_lock_fn(root):
        _validate_plan_anchors(root, plan)
        return _apply_locked(root, plan, plan_bytes, mapping_bytes, recovery_status=recovery_status)


def recover_transaction(
    root: Path,
    transaction_id: str,
    *,
    _index_lock_fn: Callable[[Path], ContextManager[None]] = _index_lock,
) -> dict[str, Any]:
    root = root.resolve()
    if not re.fullmatch(r"tsm-[0-9a-f]{24}", transaction_id):
        raise MigrationError("Invalid transaction ID")
    plan_path = _safe_ref(root, f".task/migrations/{transaction_id}/plan.json")
    plan_bytes = plan_path.read_bytes()
    plan = _read_json(plan_path, "migration recovery plan")
    mapping_path = _safe_ref(root, plan["mapping_manifest"]["snapshot_ref"])
    mapping_bytes = mapping_path.read_bytes()
    if _sha256(mapping_bytes) != plan["mapping_manifest"]["sha256"]:
        raise MigrationError("Recovery mapping snapshot mismatch")
    with _index_lock_fn(root):
        _validate_plan_anchors(root, plan)
        return _apply_locked(root, plan, plan_bytes, mapping_bytes, recovery_status="forward_completed")
