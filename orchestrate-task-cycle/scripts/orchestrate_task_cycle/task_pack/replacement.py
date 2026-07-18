"""Replacement planning, durable evidence, and postcondition validation."""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

from . import replacement_engine as task_pack_replacement

from .creation import validate_retired_items_contract
from .ordering import sorted_items
from .packet_io import load_json, require_file_digest
from .storage import (
    _require_within,
    bounded_workspace_file,
    canonical_pack_sha256,
    creation_receipt_dir,
    creation_snapshot_dir,
    json_bytes,
    pack_dir,
    rel_path,
    resolve_pack_path,
    sha256_bytes,
)
from .store import active_pack_candidates
from .validation import validate_pack

def replacement_plan_fingerprint(plan: dict[str, Any]) -> str:
    return sha256_bytes(json_bytes(plan))


def replacement_plan_snapshot_path(root: Path, plan_fingerprint: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{64}", plan_fingerprint):
        raise SystemExit("Replacement plan fingerprint is invalid.")
    return _require_within(
        pack_dir(root) / "replacement_plan_snapshots" / f"{plan_fingerprint}.json",
        pack_dir(root),
        "Replacement plan snapshot path",
    )


def pack_planning_contract(pack: dict[str, Any]) -> dict[str, Any]:
    lifecycle_fields = {
        "status",
        "current_item_id",
        "mutation_log",
        "created_at",
        "updated_at",
        "terminal_blocker",
    }
    contract = {
        str(key): copy.deepcopy(value)
        for key, value in sorted(pack.items(), key=lambda pair: str(pair[0]))
        if key not in lifecycle_fields and key != "items"
    }
    contract["items"] = [
        {
            str(key): copy.deepcopy(value)
            for key, value in sorted(item.items(), key=lambda pair: str(pair[0]))
            if key not in {"status", "promotion", "completion", "result"}
        }
        for item in sorted_items(pack)
    ]
    return contract


def validate_durable_creation_evidence(
    root: Path,
    durable_creation: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(durable_creation, dict):
        raise SystemExit("Replacement creation evidence metadata is missing.")
    snapshot_path = bounded_workspace_file(
        root,
        durable_creation.get("creation_snapshot_ref"),
        "Replacement creation snapshot",
    )
    _require_within(snapshot_path, creation_snapshot_dir(root), "Replacement creation snapshot")
    require_file_digest(
        snapshot_path,
        durable_creation.get("creation_snapshot_file_sha256"),
        "Replacement creation snapshot",
    )
    try:
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit("Replacement creation snapshot is not valid JSON.") from exc
    if not isinstance(snapshot, dict):
        raise SystemExit("Replacement creation snapshot must be a JSON object.")
    if canonical_pack_sha256(snapshot) != durable_creation.get("creation_snapshot_canonical_sha256"):
        raise SystemExit("Replacement creation snapshot canonical digest is inconsistent.")

    receipt_path = bounded_workspace_file(
        root,
        durable_creation.get("creation_receipt_ref"),
        "Replacement creation receipt",
    )
    _require_within(receipt_path, creation_receipt_dir(root), "Replacement creation receipt")
    require_file_digest(
        receipt_path,
        durable_creation.get("creation_receipt_sha256"),
        "Replacement creation receipt",
    )
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit("Replacement creation receipt is not valid JSON.") from exc
    expected_receipt = {
        key: value
        for key, value in durable_creation.items()
        if key not in {"creation_receipt_ref", "creation_receipt_sha256"}
    }
    if receipt != expected_receipt:
        raise SystemExit("Replacement creation receipt does not exactly bind the creation snapshot.")
    return snapshot, receipt


def validate_successor_creation_transition(
    successor: dict[str, Any],
    creation_snapshot: dict[str, Any],
    *,
    initial_selection_applied: bool,
) -> None:
    if pack_planning_contract(successor) != pack_planning_contract(creation_snapshot):
        raise SystemExit("Replacement successor planning contract drifted from its creation snapshot.")
    if not initial_selection_applied:
        if canonical_pack_sha256(successor) != canonical_pack_sha256(creation_snapshot):
            raise SystemExit("Replacement successor state drifted from its unselected creation snapshot.")
        return
    before_items = sorted_items(creation_snapshot)
    after_items = sorted_items(successor)
    if not before_items or any(item.get("status") != "planned" for item in before_items):
        raise SystemExit("Replacement initial selection requires an all-planned creation snapshot.")
    if [item.get("item_id") for item in before_items] != [item.get("item_id") for item in after_items]:
        raise SystemExit("Replacement initial selection changed successor item identity or order.")
    if after_items[0].get("status") != "promoted" or any(
        item.get("status") != "planned" for item in after_items[1:]
    ):
        raise SystemExit("Replacement initial selection must promote only the first planned item.")
    expected_current = after_items[1].get("item_id") if len(after_items) > 1 else None
    if successor.get("current_item_id") != expected_current:
        raise SystemExit("Replacement initial selection current item is inconsistent.")
    before_log = creation_snapshot.get("mutation_log")
    after_log = successor.get("mutation_log")
    if (
        not isinstance(before_log, list)
        or not isinstance(after_log, list)
        or len(after_log) != len(before_log) + 1
        or after_log[:-1] != before_log
        or not isinstance(after_log[-1], dict)
        or after_log[-1].get("action") != "promote"
    ):
        raise SystemExit("Replacement initial selection mutation history is inconsistent.")


def replacement_postcondition(root: Path, prepare: dict[str, Any]) -> dict[str, Any]:
    metadata = prepare.get("metadata") if isinstance(prepare.get("metadata"), dict) else {}
    predecessor_ref = str(metadata.get("predecessor_pack_ref") or "")
    successor_ref = str(metadata.get("successor_pack_ref") or "")
    predecessor_path = resolve_pack_path(root, predecessor_ref)
    successor_path = resolve_pack_path(root, successor_ref)
    predecessor = load_json(predecessor_path)
    successor = load_json(successor_path)
    creation_snapshot, creation_receipt = validate_durable_creation_evidence(
        root,
        metadata.get("creation_snapshot") if isinstance(metadata.get("creation_snapshot"), dict) else {},
    )
    plan_path = bounded_workspace_file(root, metadata.get("plan_snapshot_ref"), "Replacement plan snapshot")
    try:
        bound_plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit("Replacement plan snapshot is not valid JSON.") from exc
    if not isinstance(bound_plan, dict) or replacement_plan_fingerprint(bound_plan) != metadata.get("plan_fingerprint"):
        raise SystemExit("Replacement plan snapshot fingerprint is inconsistent.")
    planned_successor = bound_plan.get("pack") if isinstance(bound_plan.get("pack"), dict) else {}
    if pack_planning_contract(planned_successor) != pack_planning_contract(creation_snapshot):
        raise SystemExit("Replacement creation snapshot is not bound to the exact input plan.")
    validate_successor_creation_transition(
        successor,
        creation_snapshot,
        initial_selection_applied=metadata.get("initial_selection_applied") is True,
    )
    replacement_contract = successor.get("replacement_contract")
    retired_findings, _retired_ids = validate_retired_items_contract(
        root,
        replacement_contract.get("retired_items", []) if isinstance(replacement_contract, dict) else None,
        predecessor_pack_sha256=(
            str(replacement_contract.get("predecessor_pack_canonical_sha256") or "")
            if isinstance(replacement_contract, dict)
            else None
        ),
    )
    if retired_findings:
        raise SystemExit("Replacement retired-item evidence no longer validates.")
    if predecessor.get("status") != "superseded":
        raise SystemExit("Replacement postcondition requires a superseded predecessor.")
    predecessor_blocks = [item for item in validate_pack(predecessor, predecessor_path) if item.get("severity") == "block"]
    successor_findings = validate_pack(successor, successor_path)
    if predecessor_blocks or successor_findings:
        raise SystemExit("Replacement postcondition pack validation failed.")
    if canonical_pack_sha256(predecessor) != metadata.get("predecessor_after_canonical_sha256"):
        raise SystemExit("Replacement predecessor canonical state differs from the prepared transaction.")
    if canonical_pack_sha256(successor) != metadata.get("successor_after_canonical_sha256"):
        raise SystemExit("Replacement successor canonical state differs from the prepared transaction.")
    active = active_pack_candidates(root)
    active_refs = [rel_path(root, path) for path, _data in active]
    if active_refs != [successor_ref]:
        raise SystemExit("Replacement postcondition requires exactly the successor pack to be active.")
    return {
        "active_pack_count": 1,
        "active_pack_refs": active_refs,
        "predecessor_status": predecessor.get("status"),
        "successor_status": successor.get("status"),
        "creation_snapshot_ref": metadata["creation_snapshot"]["creation_snapshot_ref"],
        "creation_snapshot_sha256": metadata["creation_snapshot"]["creation_snapshot_file_sha256"],
        "creation_receipt_ref": metadata["creation_snapshot"]["creation_receipt_ref"],
        "creation_receipt_sha256": metadata["creation_snapshot"]["creation_receipt_sha256"],
        "creation_receipt_kind": creation_receipt.get("receipt_kind"),
    }


def validate_replacement_receipt(
    root: Path,
    plan: dict[str, Any],
    receipt: dict[str, Any] | None,
    *,
    current_pack_path: str | None = None,
    current_render_path: str | None = None,
) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []

    def add(code: str, message: str, evidence: Any = None) -> None:
        finding: dict[str, Any] = {"severity": "block", "code": code, "message": message}
        if evidence is not None:
            finding["evidence"] = evidence
        findings.append(finding)

    if not isinstance(receipt, dict):
        add("replacement_receipt_missing", "replace_pack requires a committed replacement receipt.")
        return {"status": "block", "findings": findings}
    transaction_id = str(receipt.get("transaction_id") or "")
    try:
        verified = task_pack_replacement.validate_completed_transaction(root, transaction_id)
    except SystemExit as exc:
        add("replacement_receipt_invalid", str(exc))
        return {"status": "block", "findings": findings}
    if receipt != verified:
        add(
            "replacement_supplied_receipt_incomplete",
            "Supplied replacement receipt must exactly match the durable validated receipt, including its ref and digest.",
        )
    expected_fingerprint = replacement_plan_fingerprint(plan)
    if verified.get("plan_fingerprint") != expected_fingerprint:
        add(
            "replacement_plan_fingerprint_mismatch",
            "Replacement receipt is bound to a different plan.",
            {"expected": expected_fingerprint, "actual": verified.get("plan_fingerprint")},
        )
    try:
        prepare = task_pack_replacement.load_prepare(root, transaction_id)[0]
        metadata = prepare.get("metadata") if isinstance(prepare.get("metadata"), dict) else {}
        target_refs = {
            str(target.get("role")): str(target.get("target_ref"))
            for target in prepare.get("targets", [])
            if isinstance(target, dict)
        }
        if current_pack_path is not None and current_pack_path != metadata.get("successor_pack_ref"):
            add(
                "replacement_current_pack_path_mismatch",
                "Result task_pack_path does not identify the committed replacement successor.",
                {"expected": metadata.get("successor_pack_ref"), "actual": current_pack_path},
            )
        if current_render_path is not None and current_render_path != target_refs.get("successor_render"):
            add(
                "replacement_current_render_path_mismatch",
                "Result task_pack_render_path does not identify the committed successor render target.",
                {"expected": target_refs.get("successor_render"), "actual": current_render_path},
            )
        actual_postcondition = replacement_postcondition(root, prepare)
        if verified.get("postcondition") != actual_postcondition:
            add(
                "replacement_postcondition_receipt_mismatch",
                "Replacement receipt postcondition does not match the current verified state.",
                {"recorded": verified.get("postcondition"), "actual": actual_postcondition},
            )
    except SystemExit as exc:
        add("replacement_postcondition_invalid", str(exc))
    return {"status": "block" if findings else "ok", "findings": findings, "receipt": verified}
