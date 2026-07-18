"""New-pack creation and carry-forward planning contracts."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from .contracts import OPEN_RESIDUAL_STATUSES, RETIREMENT_BASES, SHA256_PATTERN
from .ordering import item_order, refresh_current_item, sorted_items
from .packet_io import require_file_digest, verify_evidence_files, write_content_addressed_file
from .provenance import mutation_entry
from .receipts import validate_initial_selection_receipt
from .storage import (
    _require_within,
    bounded_workspace_file,
    bounded_workspace_path,
    canonical_pack_sha256,
    pack_dir,
    rel_path,
    sha256_bytes,
    sha256_file,
)
from .validation import publication_findings

def apply_initial_selection_to_new_pack(
    root: Path,
    path: Path,
    pack_data: dict[str, Any],
    initial_selection: dict[str, Any] | None,
    durable_creation: dict[str, Any],
    *,
    check_size: bool,
    dry_run: bool = False,
) -> tuple[bool, list[dict[str, Any]]]:
    if not isinstance(initial_selection, dict):
        return False, publication_findings(pack_data, path, check_size=check_size)
    pack_id = str(pack_data.get("pack_id") or "")
    item_id = str(initial_selection.get("item_id") or "").strip()
    task_id = str(initial_selection.get("task_id") or "").strip()
    task_path_value = str(initial_selection.get("task_path") or "task.md")
    origin = str(initial_selection.get("promotion_origin") or "bootstrap_initial_selection")
    if origin not in {"bootstrap_initial_selection", "authorized_initial_selection"}:
        raise SystemExit("Create/replace initial_selection requires an initial promotion origin.")
    target = next(
        (
            item
            for item in pack_data.get("items", [])
            if isinstance(item, dict) and str(item.get("item_id") or "") == item_id
        ),
        None,
    )
    ordered = sorted_items(pack_data)
    if target is None or not ordered or target is not ordered[0] or target.get("order") != 1:
        raise SystemExit("Create/replace initial_selection must target the first canonical pack item.")
    if target.get("status") != "planned":
        raise SystemExit("Create/replace initial_selection requires a planned first item.")
    task_path = bounded_workspace_path(root, task_path_value, "Create/replace initial task_path")
    prospective_ref = str(initial_selection.get("prospective_task_ref") or "").strip()
    prospective_digest = str(initial_selection.get("prospective_task_sha256") or "").strip()
    prospective_path: Path | None = None
    prospective_bytes: bytes | None = None
    if prospective_ref or prospective_digest:
        prospective_path = bounded_workspace_file(
            root,
            prospective_ref,
            "Create/replace prospective_task_ref",
        )
        require_file_digest(
            prospective_path,
            prospective_digest,
            "Create/replace prospective task",
        )
        prospective_bytes = prospective_path.read_bytes()
    if dry_run and prospective_bytes is not None:
        task_bytes = prospective_bytes
        task_digest = sha256_bytes(task_bytes)
    elif task_path.is_file():
        task_bytes = task_path.read_bytes()
        task_digest = sha256_bytes(task_bytes)
        if prospective_bytes is not None and task_bytes != prospective_bytes:
            raise SystemExit("Canonical task bytes differ from the preflight prospective task.")
    else:
        raise SystemExit(
            "Create/replace initial task_path is missing; dry-run requires a hash-bound prospective_task_ref."
        )
    snapshot_directory = _require_within(
        pack_dir(root) / "task_snapshots" / pack_id,
        pack_dir(root),
        "Create/replace initial task snapshot directory",
    )
    snapshot_name = f"{item_id[:48]}-{task_id[:48]}-{task_digest[:16]}.md"
    task_snapshot_path = _require_within(
        snapshot_directory / snapshot_name,
        pack_dir(root),
        "Create/replace initial task snapshot path",
    )
    write_content_addressed_file(task_snapshot_path, task_bytes, "Create/replace initial task snapshot")
    supplied_receipt = initial_selection.get("initial_selection_receipt")
    if not isinstance(supplied_receipt, dict):
        raise SystemExit("Create/replace initial_selection requires initial_selection_receipt.")
    if supplied_receipt.get("task_snapshot_ref") != rel_path(root, task_snapshot_path):
        raise SystemExit("Create/replace initial-selection receipt references a different task snapshot.")
    if supplied_receipt.get("pack_creation_snapshot_ref") != durable_creation.get("creation_snapshot_ref"):
        raise SystemExit("Create/replace initial-selection receipt references a different creation snapshot.")
    verified = validate_initial_selection_receipt(
        root,
        path,
        pack_data,
        supplied_receipt,
        task_id=task_id,
        task_digest=task_digest,
        operation="promote",
        require_mutation_binding=False,
    )
    inline_digest = sha256_bytes(
        json.dumps(verified, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    target["status"] = "promoted"
    target["promotion"] = {
        "task_id": task_id,
        "task_path": rel_path(root, task_path),
        "task_sha256": task_digest,
        "task_snapshot_path": rel_path(root, task_snapshot_path),
        "promoted_at": supplied_receipt.get("created_at"),
        "mutation_evidence_paths": verify_evidence_files(
            root,
            initial_selection.get("evidence_paths"),
            "Create/replace initial-selection evidence_paths",
        )
        if initial_selection.get("evidence_paths")
        else [],
        "promotion_origin": origin,
        "initial_selection_receipt": verified,
        "initial_selection_receipt_ref": f"inline:sha256:{inline_digest}",
        "predecessor_completion_receipt_ref": None,
    }
    promote_entry = mutation_entry("promote", initial_selection, item_order(pack_data), item_order(pack_data))
    promote_entry.update(
        {
            "timestamp": supplied_receipt.get("created_at"),
            "item_id": item_id,
            "task_id": task_id,
            "validated_task_id": None,
            "promotion_origin": origin,
            "before_pack_sha256": durable_creation.get("creation_snapshot_canonical_sha256"),
        }
    )
    pack_data.setdefault("mutation_log", []).append(promote_entry)
    refresh_current_item(pack_data)
    allowed_prospective = {task_digest} if dry_run and prospective_bytes is not None else None
    return True, publication_findings(
        pack_data,
        path,
        check_size=check_size,
        prospective_task_digests=allowed_prospective,
    )


def item_planning_contract(item: dict[str, Any]) -> dict[str, Any]:
    lifecycle_fields = {"order", "status", "promotion", "completion", "result"}
    return {
        str(key): copy.deepcopy(value)
        for key, value in sorted(item.items(), key=lambda pair: str(pair[0]))
        if key not in lifecycle_fields
    }


def item_planning_contract_sha256(item: dict[str, Any]) -> str:
    payload = json.dumps(item_planning_contract(item), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return sha256_bytes(payload.encode("utf-8"))


def validate_retired_items_contract(
    root: Path,
    retired_items: Any,
    *,
    predecessor_pack_sha256: str | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    findings: list[dict[str, Any]] = []
    if not isinstance(retired_items, list) or not all(isinstance(value, dict) for value in retired_items):
        return (
            [
                {
                    "severity": "block",
                    "code": "replacement_retired_items_invalid",
                    "message": "Replacement contract retired_items must be a list of disposition objects.",
                }
            ],
            [],
        )
    retired_ids: list[str] = []
    for retired in retired_items:
        item_id = str(retired.get("item_id") or "")
        reason = str(retired.get("reason") or "").strip()
        basis = str(retired.get("retirement_basis") or "")
        predecessor_digest = str(retired.get("predecessor_pack_sha256") or "").removeprefix("sha256:")
        evidence = retired.get("decision_evidence")
        if (
            not item_id
            or not reason
            or len(reason) > 500
            or basis not in RETIREMENT_BASES
            or not SHA256_PATTERN.fullmatch(predecessor_digest)
            or (predecessor_pack_sha256 is not None and predecessor_digest != predecessor_pack_sha256)
            or not isinstance(evidence, list)
            or not evidence
        ):
            findings.append(
                {
                    "severity": "block",
                    "code": "replacement_retired_item_incomplete",
                    "message": "Each retired item requires a typed basis, exact predecessor hash, bounded reason, and hash-bound decision evidence.",
                    "evidence": {
                        "item_id": item_id or None,
                        "retirement_basis": basis or None,
                        "predecessor_pack_sha256": predecessor_digest or None,
                    },
                }
            )
            continue
        for evidence_item in evidence:
            try:
                if not isinstance(evidence_item, dict):
                    raise SystemExit("Retirement evidence entry must be an object.")
                evidence_path = bounded_workspace_file(
                    root,
                    evidence_item.get("path"),
                    f"Replacement retired item {item_id} evidence",
                )
                try:
                    evidence_path.relative_to(pack_dir(root).resolve())
                except ValueError:
                    pass
                else:
                    raise SystemExit(
                        "Retirement evidence must remain outside the mutable task-pack transaction store."
                    )
                require_file_digest(
                    evidence_path,
                    evidence_item.get("sha256"),
                    f"Replacement retired item {item_id} evidence",
                )
            except SystemExit as exc:
                findings.append(
                    {
                        "severity": "block",
                        "code": "replacement_retired_item_evidence_invalid",
                        "message": str(exc),
                        "evidence": {"item_id": item_id},
                    }
                )
        retired_ids.append(item_id)
    return findings, retired_ids


def validate_carry_forward_contract(root: Path, predecessor_path: Path, predecessor: dict[str, Any], successor: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    findings: list[dict[str, Any]] = []
    bindings: list[dict[str, str]] = []

    def add(code: str, message: str, evidence: Any = None) -> None:
        finding: dict[str, Any] = {"severity": "block", "code": code, "message": message}
        if evidence is not None:
            finding["evidence"] = evidence
        findings.append(finding)

    contract = successor.get("replacement_contract")
    if not isinstance(contract, dict) or contract.get("schema_version") != 1:
        add("replacement_contract_missing", "Replacement successor requires replacement_contract schema version 1.")
        return findings, bindings
    expected_ref = rel_path(root, predecessor_path)
    if contract.get("predecessor_pack_ref") != expected_ref:
        add("replacement_predecessor_ref_mismatch", "Replacement contract names a different predecessor pack.")
    if contract.get("predecessor_pack_file_sha256") != sha256_file(predecessor_path):
        add("replacement_predecessor_file_sha_mismatch", "Replacement contract predecessor file digest is stale.")
    if contract.get("predecessor_pack_canonical_sha256") != canonical_pack_sha256(predecessor):
        add("replacement_predecessor_canonical_sha_mismatch", "Replacement contract predecessor canonical digest is stale.")
    new_ids = contract.get("new_item_ids")
    carried_ids = contract.get("carried_forward_item_ids")
    retired_items = contract.get("retired_items", [])
    if not isinstance(new_ids, list) or not all(isinstance(value, str) and value for value in new_ids):
        add("replacement_new_item_ids_invalid", "Replacement contract requires an explicit new_item_ids list.")
        new_ids = []
    if not isinstance(carried_ids, list) or not all(isinstance(value, str) and value for value in carried_ids):
        add("replacement_carried_item_ids_invalid", "Replacement contract requires an explicit carried_forward_item_ids list.")
        carried_ids = []
    new_ids = [str(value) for value in new_ids]
    carried_ids = [str(value) for value in carried_ids]
    retired_findings, retired_ids = validate_retired_items_contract(
        root,
        retired_items,
        predecessor_pack_sha256=canonical_pack_sha256(predecessor),
    )
    findings.extend(retired_findings)
    if len(set(new_ids)) != len(new_ids) or len(set(carried_ids)) != len(carried_ids) or set(new_ids) & set(carried_ids):
        add("replacement_item_partition_invalid", "New and carried-forward item IDs must be unique and disjoint.")
    if len(set(retired_ids)) != len(retired_ids) or set(retired_ids) & (set(new_ids) | set(carried_ids)):
        add("replacement_retired_partition_invalid", "Retired predecessor IDs must be unique and disjoint from successor items.")
    successor_ids = item_order(successor)
    if set(successor_ids) != set(new_ids) | set(carried_ids):
        add(
            "replacement_item_partition_incomplete",
            "Replacement new/carried item IDs must partition every successor item.",
            {"successor_item_ids": successor_ids, "new_item_ids": new_ids, "carried_forward_item_ids": carried_ids},
        )
    if len(new_ids) > 5:
        add("replacement_new_item_count_exceeded", "Replacement may introduce at most five newly derived items.")
    if len(successor_ids) > 5 and not carried_ids:
        add("replacement_large_pack_without_carry_forward", "A replacement over five total items requires exact carry-forward items.")

    predecessor_items = {
        str(item.get("item_id")): item
        for item in sorted_items(predecessor)
        if isinstance(item, dict) and item.get("item_id")
    }
    successor_items = {
        str(item.get("item_id")): item
        for item in sorted_items(successor)
        if isinstance(item, dict) and item.get("item_id")
    }
    predecessor_ids = set(predecessor_items)
    successor_id_set = set(successor_items)
    for successor_item_id, successor_item in successor_items.items():
        dependencies = successor_item.get("dependencies")
        if not isinstance(dependencies, list):
            continue
        for dependency in dependencies:
            dependency_id = str(dependency or "")
            if not dependency_id or dependency_id not in predecessor_items or dependency_id in successor_id_set:
                continue
            dependency_item = predecessor_items[dependency_id]
            completion = dependency_item.get("completion")
            if dependency_item.get("status") == "consumed" and isinstance(completion, dict):
                continue
            add(
                "replacement_dependency_target_removed",
                "Successor dependency names a predecessor item that is neither present nor completed with preserved evidence.",
                {"item_id": successor_item_id, "dependency_item_id": dependency_id},
            )
    if set(new_ids) & predecessor_ids:
        add(
            "replacement_predecessor_reclassified_as_new",
            "An existing predecessor item cannot be reclassified as newly derived; carry it exactly or retire it explicitly.",
            {"item_ids": sorted(set(new_ids) & predecessor_ids)},
        )
    unknown_retired = set(retired_ids) - predecessor_ids
    if unknown_retired:
        add(
            "replacement_retired_item_unknown",
            "retired_items may name only predecessor items.",
            {"item_ids": sorted(unknown_retired)},
        )
    live_predecessor_ids = {
        item_id
        for item_id, item in predecessor_items.items()
        if item.get("status") in OPEN_RESIDUAL_STATUSES
    }
    unaccounted_live = live_predecessor_ids - set(carried_ids) - set(retired_ids)
    if unaccounted_live:
        add(
            "replacement_live_predecessor_item_unaccounted",
            "Every nonterminal predecessor item must be carried forward exactly or retired with evidence.",
            {"item_ids": sorted(unaccounted_live)},
        )
    predecessor_relative = [item_id for item_id in item_order(predecessor) if item_id in set(carried_ids)]
    successor_relative = [item_id for item_id in successor_ids if item_id in set(carried_ids)]
    if predecessor_relative != carried_ids or successor_relative != carried_ids:
        add(
            "replacement_carried_order_changed",
            "Carried-forward items must retain predecessor-relative order.",
            {"declared": carried_ids, "predecessor": predecessor_relative, "successor": successor_relative},
        )
    for item_id in carried_ids:
        old_item = predecessor_items.get(item_id)
        new_item = successor_items.get(item_id)
        if old_item is None or new_item is None:
            add("replacement_carried_item_missing", "A declared carried-forward item is missing.", {"item_id": item_id})
            continue
        old_digest = item_planning_contract_sha256(old_item)
        new_digest = item_planning_contract_sha256(new_item)
        bindings.append(
            {
                "item_id": item_id,
                "predecessor_planning_sha256": old_digest,
                "successor_planning_sha256": new_digest,
            }
        )
        if old_digest != new_digest:
            add(
                "replacement_carried_planning_contract_changed",
                "Carried-forward planning fields changed; treat the item as newly derived or restore the exact contract.",
                {"item_id": item_id, "predecessor_sha256": old_digest, "successor_sha256": new_digest},
            )
    return findings, bindings
