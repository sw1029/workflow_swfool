"""Pure artifact construction for legacy task-pack retirement."""

from __future__ import annotations

from typing import Any

from .legacy_retirement_contract import LEGACY_ELIGIBILITY_CONTRACT_VERSION
from .legacy_retirement_schema import NON_CLAIMS, snapshot_id, transaction_id
from .legacy_retirement_store import (
    artifact_ref,
    canonical_sha256,
    display_bytes,
    sha256_bytes,
)
from .state_machine import derived_operational_status


def overlay_body(
    plan: dict[str, Any],
    target: Any,
    tx_id: str,
    snapshot_binding: dict[str, str],
    packet: dict[str, Any],
    verification: dict[str, Any],
) -> dict[str, Any]:
    source = plan["source_pack"]
    core: dict[str, Any] = {
        "schema_version": 1,
        "artifact_kind": "legacy_task_pack_retirement_overlay",
        "disposition": "retired_legacy_closed",
        "source_pack": {
            "pack_id": source["pack_id"],
            "ref": source["ref"],
            "file_sha256": source["file_sha256"],
            "canonical_pack_sha256": source["canonical_pack_sha256"],
            "snapshot_ref": snapshot_binding["ref"],
            "snapshot_sha256": snapshot_binding["sha256"],
            "declared_status": target.pack.get("status"),
        },
        "eligibility": {
            "contract_version": LEGACY_ELIGIBILITY_CONTRACT_VERSION,
            "blocking_finding_codes": list(target.finding_codes),
            "blocking_finding_fingerprint": target.finding_fingerprint,
            "raw_contract_status": "block",
            "derived_operational_status": derived_operational_status(target.pack),
            "current_task_bound": False,
        },
        "non_claims": dict(NON_CLAIMS),
        "authority": {
            "packet": plan["authority_packet"],
            "packet_id": packet.get("packet_id"),
            "pre_commit": plan["pre_commit_verification"],
            "verification_id": verification.get("verification_id"),
            "consume_idempotency_key": plan["consume_idempotency_key"],
        },
        "transaction": {"transaction_id": tx_id},
    }
    retirement_id = "lgr-" + canonical_sha256(core)[:32]
    return {**core, "retirement_id": retirement_id}


def prepare_body(
    plan: dict[str, Any],
    tx_id: str,
    snapshot_binding: dict[str, str],
    overlay_binding: dict[str, str],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_kind": "legacy_task_pack_retirement_prepare",
        "transaction_id": tx_id,
        "plan": plan,
        "source_snapshot": snapshot_binding,
        "overlay": overlay_binding,
    }


def completion_body(
    plan: dict[str, Any],
    tx_id: str,
    prepare_binding: dict[str, str],
    snapshot_binding: dict[str, str],
    overlay_binding: dict[str, str],
) -> dict[str, Any]:
    source = plan["source_pack"]
    return {
        "schema_version": 1,
        "artifact_kind": "legacy_task_pack_retirement_completion",
        "transaction_id": tx_id,
        "status": "committed",
        "prepare": prepare_binding,
        "source_snapshot": snapshot_binding,
        "overlay": overlay_binding,
        "source_pack": {"ref": source["ref"], "sha256": source["file_sha256"]},
        "completed_at": plan["prepared_at"],
    }


def predict_artifacts(
    plan: dict[str, Any],
    target: Any,
    packet: dict[str, Any],
    verification: dict[str, Any],
) -> dict[str, Any]:
    tx_id = transaction_id(plan)
    snap_id = snapshot_id(plan["source_pack"]["file_sha256"])
    snapshot_binding = {
        "ref": artifact_ref("snapshots", snap_id),
        "sha256": sha256_bytes(target.pack_bytes),
    }
    overlay = overlay_body(plan, target, tx_id, snapshot_binding, packet, verification)
    overlay_binding = {
        "ref": artifact_ref("overlays", overlay["retirement_id"]),
        "sha256": sha256_bytes(display_bytes(overlay)),
    }
    prepare = prepare_body(plan, tx_id, snapshot_binding, overlay_binding)
    prepare_binding = {
        "ref": artifact_ref("prepares", tx_id),
        "sha256": sha256_bytes(display_bytes(prepare)),
    }
    completion = completion_body(
        plan, tx_id, prepare_binding, snapshot_binding, overlay_binding
    )
    return {
        "transaction_id": tx_id,
        "snapshot_id": snap_id,
        "snapshot_binding": snapshot_binding,
        "overlay": overlay,
        "overlay_binding": overlay_binding,
        "prepare": prepare,
        "prepare_binding": prepare_binding,
        "completion": completion,
        "completion_binding": {
            "ref": artifact_ref("completions", tx_id),
            "sha256": sha256_bytes(display_bytes(completion)),
        },
    }


def activation_body(
    overlay_binding: dict[str, str],
    completion_binding: dict[str, str],
    use_receipt_binding: dict[str, str],
    activated_at: str,
) -> dict[str, Any]:
    core = {
        "schema_version": 1,
        "artifact_kind": "legacy_task_pack_retirement_activation",
        "retirement": overlay_binding,
        "completion": completion_binding,
        "authority_use_receipt": use_receipt_binding,
        "activated_at": activated_at,
    }
    return {**core, "activation_id": "lgra-" + canonical_sha256(core)[:32]}


__all__ = (
    "activation_body",
    "completion_body",
    "overlay_body",
    "predict_artifacts",
    "prepare_body",
)
