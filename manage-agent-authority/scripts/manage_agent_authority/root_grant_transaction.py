"""Recoverable publication transaction for plan-bound root grants."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .artifact_store import grant_path, state_path
from .canonical import (
    authority_lock,
    object_sha256,
    resolve_workspace_path,
    write_json_atomic,
)
from .root_grant_derivation import (
    MAX_ROOT_STATE_BYTES,
    MAX_ROOT_TRANSACTION_BYTES,
    closed_binding as _closed_binding,
    derive_root_grant_materialization,
    json_bytes,
    read_exact as _read_exact,
    source_snapshot_binding,
)
from .stable_store import publish_immutable


def payload_binding(root: Path, path: Path, payload: bytes) -> dict[str, str]:
    return {
        "ref": path.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _initial_state(
    grant: dict[str, Any], digest: str, status: str
) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "artifact_kind": "authority_grant_state",
        "grant_id": grant["grant_id"],
        "grant_sha256": digest,
        "status": status,
        "remaining_uses": grant["max_uses"],
        "reserved_uses": 0,
        "consumed_uses": 0,
        "version": 0,
        "last_event_id": None,
    }


def _materialization_hook(stage: str, path: Path) -> None:
    """Test seam for crash/recovery regression coverage."""

    _ = stage, path


def _build_assets(
    root: Path,
    materialization_root: Path,
    plan_binding: dict[str, str],
    decision_binding: dict[str, str],
    decided_at: str,
    source: dict[str, Any],
    grants: list[dict[str, Any]],
) -> dict[str, Any]:
    source_path = materialization_root / "source_approval.json"
    source_payload = json_bytes(source)
    source_binding = source_snapshot_binding(root, source)
    snapshot_path = root / source_binding["ref"]
    metadata_path = snapshot_path.with_suffix(snapshot_path.suffix + ".json")
    metadata_payload = json_bytes(
        {
            "schema_version": 2,
            "artifact_kind": "source_approval_snapshot",
            "source_ref": source_path.relative_to(root).as_posix(),
            "source_sha256": source_binding["sha256"],
            "snapshot_ref": source_binding["ref"],
            "snapshot_sha256": source_binding["sha256"],
        }
    )
    grant_assets: list[dict[str, Any]] = []
    registered: list[dict[str, str]] = []
    for grant in grants:
        artifact_path = grant_path(root, grant["grant_id"])
        artifact_payload = json_bytes(grant)
        digest = hashlib.sha256(artifact_payload).hexdigest()
        projection_path = state_path(root, grant["grant_id"])
        grant_assets.append(
            {
                "grant": grant,
                "grant_sha256": digest,
                "artifact_path": artifact_path,
                "artifact_payload": artifact_payload,
                "state_path": projection_path,
                "draft_payload": json_bytes(
                    _initial_state(grant, digest, "draft")
                ),
                "active_payload": json_bytes(
                    _initial_state(grant, digest, "active")
                ),
            }
        )
        registered.append(
            {
                "ref": artifact_path.relative_to(root).as_posix(),
                "sha256": digest,
                "request_sha256": grant["request_sha256"],
            }
        )
    prepare_core = {
        "schema_version": 1,
        "artifact_kind": "authority_root_grant_materialization_prepare",
        "root_approval_plan": plan_binding,
        "root_approval_decision_seed": decision_binding,
        "source_approval": source_binding,
        "grants": registered,
        "activation_rule": "all_grants_draft_then_all_active_then_receipt",
    }
    prepare = {
        "transaction_id": f"authrgtx-{object_sha256(prepare_core)[:24]}",
        **prepare_core,
    }
    prepare_path = materialization_root / "prepare.json"
    prepare_payload = json_bytes(prepare)
    receipt_core = {
        "schema_version": 1,
        "artifact_kind": "authority_root_grant_materialization_receipt",
        "transaction_prepare": payload_binding(
            root, prepare_path, prepare_payload
        ),
        "root_approval_plan": plan_binding,
        "root_approval_decision_seed": decision_binding,
        "decision_trust_class": source["decision_trust_class"],
        "source_approval": source_binding,
        "grants": registered,
        "materialized_at": decided_at,
    }
    receipt = {
        "receipt_id": f"authrgm-{object_sha256(receipt_core)[:24]}",
        **receipt_core,
    }
    receipt_path = materialization_root / "receipt.json"
    return {
        "source_path": source_path,
        "source_payload": source_payload,
        "source_binding": source_binding,
        "snapshot_path": snapshot_path,
        "metadata_path": metadata_path,
        "metadata_payload": metadata_payload,
        "grant_assets": grant_assets,
        "prepare_path": prepare_path,
        "prepare_payload": prepare_payload,
        "receipt": receipt,
        "receipt_path": receipt_path,
        "receipt_payload": json_bytes(receipt),
    }


def _derive_root_grant_assets(
    root: Path,
    plan_binding: dict[str, str],
    decision_binding: dict[str, str],
    *,
    skills_root: Path | None = None,
) -> dict[str, Any]:
    derived = derive_root_grant_materialization(
        root,
        plan_binding,
        decision_binding,
        skills_root=skills_root,
    )
    assets = _build_assets(
        root.resolve(),
        derived["materialization_root"],
        derived["plan_binding"],
        derived["decision_binding"],
        derived["decided_at"],
        derived["source"],
        derived["grants"],
    )
    if (
        assets["receipt_path"].relative_to(root.resolve()).as_posix()
        != derived["receipt_ref"]
        or assets["source_binding"] != derived["source_binding"]
    ):
        raise SystemExit(
            "Root grant transaction materialization identity drifted."
        )
    return assets


def _absent_or_exact(path: Path, payload: bytes, label: str) -> bool:
    existing = _read_exact(path, required=False, label=label)
    if existing is not None and existing != payload:
        raise SystemExit(f"Conflicting {label} exists: {path}")
    return existing is not None


def _preflight(assets: dict[str, Any]) -> bool:
    recovering = _absent_or_exact(
        assets["prepare_path"],
        assets["prepare_payload"],
        "root grant materialization prepare",
    )
    for path_key, payload_key, label in (
        ("source_path", "source_payload", "root source approval"),
        ("snapshot_path", "source_payload", "root source approval snapshot"),
        (
            "metadata_path",
            "metadata_payload",
            "root source approval snapshot metadata",
        ),
    ):
        _absent_or_exact(assets[path_key], assets[payload_key], label)
    for grant in assets["grant_assets"]:
        _absent_or_exact(
            grant["artifact_path"],
            grant["artifact_payload"],
            "root grant artifact",
        )
        state = _read_exact(
            grant["state_path"],
            required=False,
            label="root grant state",
            max_bytes=MAX_ROOT_STATE_BYTES,
        )
        if state not in {
            None,
            grant["draft_payload"],
            grant["active_payload"],
        }:
            raise SystemExit(
                "Root grant materialization found a conflicting or advanced state."
            )
    return recovering


def _verify_published_assets(assets: dict[str, Any]) -> None:
    for path_key, payload_key, label in (
        ("prepare_path", "prepare_payload", "transaction prepare"),
        ("source_path", "source_payload", "source approval"),
        ("snapshot_path", "source_payload", "source approval snapshot"),
        (
            "metadata_path",
            "metadata_payload",
            "source approval snapshot metadata",
        ),
    ):
        if _read_exact(
            assets[path_key], label=f"completed root {label}"
        ) != assets[payload_key]:
            raise SystemExit(
                f"Completed root materialization {label} drifted."
            )
    for grant in assets["grant_assets"]:
        if _read_exact(
            grant["artifact_path"], label="root grant artifact"
        ) != grant["artifact_payload"]:
            raise SystemExit(
                "Completed root materialization grant artifact drifted."
            )


def _verify_completed(assets: dict[str, Any]) -> None:
    _verify_published_assets(assets)
    for grant in assets["grant_assets"]:
        if _read_exact(
            grant["state_path"],
            label="root grant state",
            max_bytes=MAX_ROOT_STATE_BYTES,
        ) != grant["active_payload"]:
            raise SystemExit(
                "Completed root materialization grant state is not active."
            )


def _apply(assets: dict[str, Any]) -> None:
    publish_immutable(assets["prepare_path"], assets["prepare_payload"])
    _materialization_hook("after_prepare", assets["prepare_path"])
    publish_immutable(assets["source_path"], assets["source_payload"])
    publish_immutable(assets["snapshot_path"], assets["source_payload"])
    publish_immutable(assets["metadata_path"], assets["metadata_payload"])
    for grant in assets["grant_assets"]:
        publish_immutable(grant["artifact_path"], grant["artifact_payload"])
        if _read_exact(
            grant["state_path"],
            required=False,
            label="root grant state",
            max_bytes=MAX_ROOT_STATE_BYTES,
        ) is None:
            write_json_atomic(
                grant["state_path"],
                json.loads(grant["draft_payload"].decode("utf-8")),
            )
    _materialization_hook("after_drafts", assets["prepare_path"])
    _verify_published_assets(assets)
    for grant in assets["grant_assets"]:
        state = _read_exact(
            grant["state_path"],
            label="root grant state",
            max_bytes=MAX_ROOT_STATE_BYTES,
        )
        if state == grant["draft_payload"]:
            write_json_atomic(
                grant["state_path"],
                json.loads(grant["active_payload"].decode("utf-8")),
            )
        elif state != grant["active_payload"]:
            raise SystemExit(
                "Root grant state changed during materialization recovery."
            )
        _materialization_hook(
            "after_grant_activation", grant["state_path"]
        )
    _verify_published_assets(assets)
    publish_immutable(assets["receipt_path"], assets["receipt_payload"])
    _materialization_hook("after_receipt", assets["receipt_path"])


def _result(
    root: Path, assets: dict[str, Any], *, recovered: bool
) -> dict[str, Any]:
    return {
        "status": "recovered" if recovered else "materialized",
        "authority_status": "active",
        "decision_trust_class": assets["receipt"]["decision_trust_class"],
        "root_grant_materialization": payload_binding(
            root, assets["receipt_path"], assets["receipt_payload"]
        ),
        "source_approval": assets["source_binding"],
        "grants": assets["receipt"]["grants"],
    }


def validate_root_grant_receipt_chain(
    root: Path,
    receipt_ref: str,
    *,
    skills_root: Path | None = None,
) -> dict[str, Any]:
    """Boundedly reopen a receipt and reproduce its complete signed chain."""

    root = root.resolve()
    receipt_path = resolve_workspace_path(
        root,
        receipt_ref,
        "root grant materialization receipt",
    )
    receipt_payload = _read_exact(
        receipt_path,
        label="root grant materialization receipt",
    )
    assert receipt_payload is not None
    try:
        receipt = json.loads(receipt_payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(
            "Root grant materialization receipt is not readable JSON."
        ) from exc
    if not isinstance(receipt, dict):
        raise SystemExit(
            "Root grant materialization receipt must be a JSON object."
        )
    assets = _derive_root_grant_assets(
        root,
        receipt.get("root_approval_plan"),
        receipt.get("root_approval_decision_seed"),
        skills_root=skills_root,
    )
    if (
        receipt_path != assets["receipt_path"]
        or receipt_payload != assets["receipt_payload"]
    ):
        raise SystemExit(
            "Root grant materialization receipt differs from the exact "
            "signed-plan rendering."
        )
    _verify_published_assets(assets)
    return assets


def commit_root_grant_transaction(
    root: Path,
    plan_binding: dict[str, str],
    decision_binding: dict[str, str],
    *legacy_mechanical_inputs: Any,
    skills_root: Path | None = None,
) -> dict[str, Any]:
    """Commit only effects rederived from two producer-owned CAS bindings."""

    if legacy_mechanical_inputs:
        raise SystemExit(
            "Raw root-grant transaction inputs are sealed; provide only the "
            "exact plan and signed decision-seed bindings."
        )
    requested_plan_binding = _closed_binding(
        plan_binding,
        "root approval plan binding",
    )
    requested_decision_binding = _closed_binding(
        decision_binding,
        "root approval decision seed binding",
    )
    root = root.resolve()
    with authority_lock(root):
        assets = _derive_root_grant_assets(
            root,
            requested_plan_binding,
            requested_decision_binding,
            skills_root=skills_root,
        )
        receipt = _read_exact(
            assets["receipt_path"],
            required=False,
            label="root grant materialization receipt",
        )
        if receipt is not None:
            if receipt != assets["receipt_payload"]:
                raise SystemExit(
                    "Conflicting root grant materialization receipt exists."
                )
            _verify_completed(assets)
            return _result(root, assets, recovered=True)
        recovering = _preflight(assets)
        _apply(assets)
        return _result(root, assets, recovered=recovering)


__all__ = (
    "MAX_ROOT_TRANSACTION_BYTES",
    "commit_root_grant_transaction",
    "source_snapshot_binding",
    "validate_root_grant_receipt_chain",
)
