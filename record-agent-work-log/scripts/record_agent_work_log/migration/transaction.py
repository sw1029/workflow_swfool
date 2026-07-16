"""Locked migration application transaction."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import time
from typing import Any

from ..integrity import sha256_bytes, workspace_root
from ..write import log_lock
from .contracts import MigrationError
from .inventory import _inventory_document
from .planning import _canonical_records_from_plan, _load_plan, _manifest_for
from .publication import (
    _active_marker,
    _current_prefix_matches,
    _ensure_directory,
    _failpoint,
    _journal_payload,
    _marker_for,
    _publish_identical,
    _receipt_from_journal,
)
from .recovery import validate_receipt
from .storage import (
    _canonical_json_bytes,
    _index_path,
    _read_index,
    _resolve_ref,
    _root_identity,
    _safe_migration_path,
    _sha256_path,
    _strict_atomic_replace,
    _utc_now,
)


@dataclass(frozen=True)
class ApplyContext:
    root: Path
    plan: dict[str, Any]
    plan_payload: bytes
    plan_sha: str
    expected_index_sha: str
    expected_inventory_sha: str
    status_map_payload: bytes


@dataclass(frozen=True)
class Reconstruction:
    source_payload: bytes
    inventory: dict[str, Any]
    after_payload: bytes
    after_sha: str


@dataclass(frozen=True)
class TransactionPaths:
    source_snapshot: Path
    status_map_copy: Path
    plan_copy: Path
    manifest_path: Path
    staged_path: Path
    journal_path: Path
    receipt_path: Path
    marker_path: Path
    refs: dict[str, str]


def _validate_existing_idempotent(
    root: Path, plan_sha: str, plan: dict[str, Any]
) -> dict[str, Any] | None:
    active = _active_marker(root)
    if active is None:
        return None
    marker, _ = active
    if marker.get("plan_sha256") != plan_sha or marker.get(
        "migration_id"
    ) != plan.get("migration_id"):
        raise MigrationError("a different migration is already committed")
    index_payload = _read_index(root)
    if not _current_prefix_matches(
        index_payload,
        marker.get("after_index_sha256", ""),
        marker.get("after_index_size", -1),
    ):
        raise MigrationError(
            "committed migration prefix does not match the current index"
        )
    receipt_path = _safe_migration_path(root, marker.get("receipt_ref"))
    if _sha256_path(receipt_path) != marker.get("receipt_sha256"):
        raise MigrationError("committed migration receipt hash mismatch")
    validate_receipt(root, receipt_path, require_appendable=True)
    return {
        "status": "already_committed",
        "migration_id": plan["migration_id"],
        "receipt": str(receipt_path),
        "receipt_sha256": marker["receipt_sha256"],
        "after_index_sha256": marker["after_index_sha256"],
        "idempotent": True,
    }


def _load_apply_context(
    root_raw: str | Path,
    plan_raw: str | Path,
    expected_plan_sha256: str,
    expected_index_sha256: str,
    expected_inventory_sha256: str,
) -> tuple[Path, dict[str, Any], bytes, str]:
    root = workspace_root(root_raw)
    plan_path = _resolve_ref(root, str(plan_raw))
    plan, plan_payload = _load_plan(plan_path)
    plan_sha = sha256_bytes(plan_payload)
    if plan_sha != expected_plan_sha256:
        raise MigrationError(
            f"plan SHA-256 mismatch: expected {expected_plan_sha256}, "
            f"observed {plan_sha}"
        )
    if plan.get("unresolved_count") != 0:
        raise MigrationError(
            "migration apply is blocked while unresolved_count is nonzero"
        )
    if plan.get("source_index", {}).get("sha256") != expected_index_sha256:
        raise MigrationError("expected index SHA does not match the plan")
    if plan.get("source_inventory_sha256") != expected_inventory_sha256:
        raise MigrationError("expected inventory SHA does not match the plan")
    if plan.get("root_identity") != _root_identity(root):
        raise MigrationError("plan root identity does not match this workspace")
    return root, plan, plan_payload, plan_sha


def _bind_status_map(
    root: Path,
    plan: dict[str, Any],
    plan_payload: bytes,
    plan_sha: str,
    expected_index_sha256: str,
    expected_inventory_sha256: str,
) -> ApplyContext:
    status_map_path = _resolve_ref(root, plan["status_map"]["ref"])
    status_map_payload = status_map_path.read_bytes()
    if sha256_bytes(status_map_payload) != plan["status_map"]["sha256"]:
        raise MigrationError("status map drift detected before apply")
    return ApplyContext(
        root=root,
        plan=plan,
        plan_payload=plan_payload,
        plan_sha=plan_sha,
        expected_index_sha=expected_index_sha256,
        expected_inventory_sha=expected_inventory_sha256,
        status_map_payload=status_map_payload,
    )


def _reconstruct(
    context: ApplyContext,
    *,
    index_drift_message: str,
    inventory_drift_message: str,
) -> Reconstruction:
    source_payload = _read_index(context.root)
    if sha256_bytes(source_payload) != context.expected_index_sha:
        raise MigrationError(index_drift_message)
    inventory = _inventory_document(context.root, source_payload)
    if inventory["inventory_sha256"] != context.expected_inventory_sha:
        raise MigrationError(inventory_drift_message)
    _, after_payload = _canonical_records_from_plan(context.root, context.plan)
    after_sha = sha256_bytes(after_payload)
    if after_sha != context.plan.get("expected_after_index_sha256") or len(
        after_payload
    ) != context.plan.get("expected_after_index_size"):
        raise MigrationError("reconstructed after-index does not match the plan")
    return Reconstruction(source_payload, inventory, after_payload, after_sha)


def _dry_run(context: ApplyContext) -> dict[str, Any]:
    reconstruction = _reconstruct(
        context,
        index_drift_message="source index drift detected before dry-run",
        inventory_drift_message=(
            "source Markdown inventory drift detected before dry-run"
        ),
    )
    return {
        "status": "dry_run_pass",
        "migration_id": context.plan["migration_id"],
        "source_index_sha256": context.expected_index_sha,
        "source_inventory_sha256": context.expected_inventory_sha,
        "after_index_sha256": reconstruction.after_sha,
        "after_row_count": context.plan["expected_after_row_count"],
        "zero_canonical_mutation": True,
    }


def _transaction_paths(context: ApplyContext) -> TransactionPaths:
    migration_root = context.root / ".agent_log" / "migrations"
    transaction_root = migration_root / context.plan["migration_id"]
    _ensure_directory(migration_root)
    _ensure_directory(transaction_root)
    named_paths = {
        "source": transaction_root / "source-index.snapshot",
        "status_map": transaction_root / "status-map.json",
        "plan": transaction_root / "plan.json",
        "manifest": transaction_root / "resolution-manifest.json",
        "staged": transaction_root / "staged-index.snapshot",
        "journal": transaction_root / "journal.json",
        "receipt": transaction_root / "receipt.json",
    }
    refs = {
        name: path.relative_to(context.root).as_posix()
        for name, path in named_paths.items()
    }
    return TransactionPaths(
        source_snapshot=named_paths["source"],
        status_map_copy=named_paths["status_map"],
        plan_copy=named_paths["plan"],
        manifest_path=named_paths["manifest"],
        staged_path=named_paths["staged"],
        journal_path=named_paths["journal"],
        receipt_path=named_paths["receipt"],
        marker_path=migration_root / "active.json",
        refs=refs,
    )


def _publish_sidecars(
    context: ApplyContext,
    reconstruction: Reconstruction,
    paths: TransactionPaths,
) -> bytes:
    _publish_identical(paths.source_snapshot, reconstruction.source_payload)
    _failpoint("after_snapshot")
    _publish_identical(paths.status_map_copy, context.status_map_payload)
    _publish_identical(paths.plan_copy, context.plan_payload)
    manifest = _manifest_for(context.plan, reconstruction.inventory)
    manifest_payload = _canonical_json_bytes(manifest)
    _publish_identical(paths.manifest_path, manifest_payload)
    _publish_identical(paths.staged_path, reconstruction.after_payload)
    _failpoint("after_sidecars")
    return manifest_payload


def _prepare_journal(
    context: ApplyContext,
    reconstruction: Reconstruction,
    paths: TransactionPaths,
    manifest_payload: bytes,
) -> dict[str, Any]:
    journal = _journal_payload(
        plan=context.plan,
        plan_sha=context.plan_sha,
        source_inventory_sha=context.expected_inventory_sha,
        source_snapshot_ref=paths.refs["source"],
        source_snapshot_sha=sha256_bytes(reconstruction.source_payload),
        status_map_ref=paths.refs["status_map"],
        status_map_sha=sha256_bytes(context.status_map_payload),
        plan_ref=paths.refs["plan"],
        manifest_ref=paths.refs["manifest"],
        manifest_sha=sha256_bytes(manifest_payload),
        staged_ref=paths.refs["staged"],
        after_sha=reconstruction.after_sha,
        after_size=len(reconstruction.after_payload),
        after_rows=context.plan["expected_after_row_count"],
        phase="prepared",
        prepared_at=_utc_now(),
    )
    _strict_atomic_replace(paths.journal_path, _canonical_json_bytes(journal))
    _failpoint("after_prepare")
    hold = os.environ.get("AGENT_LOG_MIGRATION_LOCK_HOLD_SECONDS")
    if hold:
        time.sleep(min(max(float(hold), 0.0), 10.0))
    return journal


def _switch_index(
    context: ApplyContext,
    reconstruction: Reconstruction,
    paths: TransactionPaths,
    journal: dict[str, Any],
) -> None:
    _strict_atomic_replace(_index_path(context.root), reconstruction.after_payload)
    journal["phase"] = "switched"
    _strict_atomic_replace(paths.journal_path, _canonical_json_bytes(journal))
    _failpoint("after_switch")


def _publish_receipt(
    context: ApplyContext,
    paths: TransactionPaths,
    journal: dict[str, Any],
) -> bytes:
    _, receipt_payload = _receipt_from_journal(context.root, journal)
    _strict_atomic_replace(paths.receipt_path, receipt_payload)
    _failpoint("after_receipt")
    return receipt_payload


def _commit_journal_and_marker(
    paths: TransactionPaths,
    journal: dict[str, Any],
    receipt_payload: bytes,
) -> None:
    receipt_sha = sha256_bytes(receipt_payload)
    journal["phase"] = "committed"
    journal["committed_at"] = _utc_now()
    journal["receipt_ref"] = paths.refs["receipt"]
    journal["receipt_sha256"] = receipt_sha
    _strict_atomic_replace(paths.journal_path, _canonical_json_bytes(journal))
    _failpoint("after_journal_commit")
    marker = _marker_for(
        journal,
        paths.refs["receipt"],
        receipt_sha,
        paths.refs["journal"],
        _sha256_path(paths.journal_path),
    )
    _strict_atomic_replace(paths.marker_path, _canonical_json_bytes(marker))
    _failpoint("after_marker")


def _committed_result(
    context: ApplyContext,
    reconstruction: Reconstruction,
    paths: TransactionPaths,
    manifest_payload: bytes,
    receipt_payload: bytes,
) -> dict[str, Any]:
    validation = validate_receipt(
        context.root, paths.receipt_path, require_appendable=True
    )
    if validation["status"] != "valid":
        raise MigrationError("post-publication receipt validation failed")
    return {
        "status": "committed",
        "migration_id": context.plan["migration_id"],
        "receipt": str(paths.receipt_path),
        "receipt_sha256": sha256_bytes(receipt_payload),
        "manifest": str(paths.manifest_path),
        "manifest_sha256": sha256_bytes(manifest_payload),
        "source_snapshot": str(paths.source_snapshot),
        "source_snapshot_sha256": sha256_bytes(reconstruction.source_payload),
        "before_index_sha256": context.expected_index_sha,
        "after_index_sha256": reconstruction.after_sha,
        "after_row_count": context.plan["expected_after_row_count"],
        "idempotent": False,
    }


def _apply_locked(context: ApplyContext) -> dict[str, Any]:
    active = _validate_existing_idempotent(
        context.root, context.plan_sha, context.plan
    )
    if active is not None:
        return active
    reconstruction = _reconstruct(
        context,
        index_drift_message="source index drift detected inside migration lock",
        inventory_drift_message="source inventory drift detected inside migration lock",
    )
    paths = _transaction_paths(context)
    manifest_payload = _publish_sidecars(context, reconstruction, paths)
    journal = _prepare_journal(
        context, reconstruction, paths, manifest_payload
    )
    _switch_index(context, reconstruction, paths, journal)
    receipt_payload = _publish_receipt(context, paths, journal)
    _commit_journal_and_marker(paths, journal, receipt_payload)
    return _committed_result(
        context, reconstruction, paths, manifest_payload, receipt_payload
    )


def apply_plan(
    root_raw: str | Path,
    *,
    plan_raw: str | Path,
    expected_plan_sha256: str,
    expected_index_sha256: str,
    expected_inventory_sha256: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    root, plan, plan_payload, plan_sha = _load_apply_context(
        root_raw,
        plan_raw,
        expected_plan_sha256,
        expected_index_sha256,
        expected_inventory_sha256,
    )
    active = _validate_existing_idempotent(root, plan_sha, plan)
    if active is not None:
        return active
    context = _bind_status_map(
        root,
        plan,
        plan_payload,
        plan_sha,
        expected_index_sha256,
        expected_inventory_sha256,
    )
    if dry_run:
        return _dry_run(context)
    with log_lock(root):
        return _apply_locked(context)
