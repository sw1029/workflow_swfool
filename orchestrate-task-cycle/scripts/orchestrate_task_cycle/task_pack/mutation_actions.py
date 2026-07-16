"""Action-specific in-memory task-pack transformations."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

from .contracts import PACK_COHERENCE_VERSION, PACK_ID_PATTERN, PROMOTION_ORIGINS
from .ordering import active_in_flight_items, evidence_paths_from, item_order, next_item, renumber_items, sorted_items
from .packet_io import truthy, verify_evidence_files, write_content_addressed_file
from .provenance import consume_in_flight_for_atomic_promotion, mutation_entry, validate_initial_selection_provenance, validate_promotion_provenance
from .receipts import _required_sha256, validate_initial_selection_receipt
from .storage import _require_within, bounded_workspace_file, now_iso, pack_dir, rel_path, sha256_bytes, sha256_file


def apply_promote(root: Path, path: Path, data: dict[str, Any], items: list[Any], plan: dict[str, Any], coherence: dict[str, Any], before_order: list[str]) -> None:
    item_id = str(plan.get("item_id") or data.get("current_item_id") or "").strip()
    task_id = str(plan.get("task_id") or "").strip()
    task_path_value = str(plan.get("task_path") or "task.md").strip()
    validated_task_id = str(plan.get("validated_task_id") or "").strip()
    validation_verdict = str(plan.get("validation_verdict") or "").strip().lower()
    promotion_origin = str(plan.get("promotion_origin") or "predecessor_completion").strip().lower()
    if promotion_origin not in PROMOTION_ORIGINS:
        raise SystemExit("Promotion origin must be predecessor_completion, bootstrap_initial_selection, or authorized_initial_selection.")
    if not item_id or not task_id:
        raise SystemExit("Promotion requires `item_id` and `task_id`.")
    if promotion_origin == "predecessor_completion" and not validated_task_id:
        raise SystemExit("Predecessor promotion requires `validated_task_id`.")
    if not PACK_ID_PATTERN.fullmatch(task_id) or (
        validated_task_id and not PACK_ID_PATTERN.fullmatch(validated_task_id)
    ):
        raise SystemExit("Promotion task identifiers must be path-safe tokens of at most 128 characters.")
    in_flight = [str(item.get("item_id") or "") for item in active_in_flight_items(data)]
    atomic_completion = plan.get("consume_current_item")
    if in_flight and isinstance(atomic_completion, dict):
        completed_task_id = consume_in_flight_for_atomic_promotion(
            root,
            data,
            atomic_completion,
            require_current_verdicts=coherence.get("contract_version") == PACK_COHERENCE_VERSION,
        )
        if promotion_origin != "predecessor_completion" or validated_task_id != completed_task_id:
            raise SystemExit("Atomic successor promotion must use the consumed task as predecessor provenance.")
        in_flight = [str(item.get("item_id") or "") for item in active_in_flight_items(data)]
    if in_flight:
        raise SystemExit(f"Promotion requires the existing in-flight item to be consumed or closed first: {', '.join(in_flight)}")
    if promotion_origin == "predecessor_completion":
        mutation_evidence = verify_evidence_files(root, plan.get("evidence_paths"), "Promotion mutation evidence_paths")
    else:
        mutation_evidence = (
            verify_evidence_files(root, plan.get("evidence_paths"), "Promotion mutation evidence_paths")
            if plan.get("evidence_paths")
            else []
        )
    task_path = bounded_workspace_file(root, task_path_value, "Promotion task_path")
    task_digest = sha256_file(task_path)
    target = next((item for item in items if isinstance(item, dict) and str(item.get("item_id")) == item_id), None)
    if target is None:
        raise SystemExit(f"Unknown task pack item: {item_id}")
    expected = next_item(data)
    if expected is None or str(expected.get("item_id")) != item_id:
        raise SystemExit("promote_next_item may promote only the queue's current next item.")
    if target.get("status") not in {"planned", "inserted", "reordered", "blocked"}:
        raise SystemExit(f"Task pack item is not promotable from status {target.get('status')}: {item_id}")
    if truthy(target.get("acceptance_diluted")) or truthy(
        target.get("result", {}).get("acceptance_diluted") if isinstance(target.get("result"), dict) else False
    ):
        raise SystemExit("A task pack item with acceptance_diluted=true cannot be promoted.")
    snapshot_directory = _require_within(
        pack_dir(root) / "task_snapshots" / str(data.get("pack_id")),
        pack_dir(root),
        "Promotion task snapshot directory",
    )
    snapshot_name = f"{item_id[:48]}-{task_id[:48]}-{task_digest[:16]}.md"
    task_snapshot_path = _require_within(snapshot_directory / snapshot_name, pack_dir(root), "Promotion task snapshot path")
    write_content_addressed_file(task_snapshot_path, task_path.read_bytes(), "Promotion task snapshot")
    if promotion_origin != "predecessor_completion":
        supplied_receipt = plan.get("initial_selection_receipt")
        if not isinstance(supplied_receipt, dict):
            raise SystemExit("Initial selection requires `initial_selection_receipt`.")
        if supplied_receipt.get("task_snapshot_ref") != rel_path(root, task_snapshot_path):
            raise SystemExit("Initial selection receipt must reference the deterministic task snapshot.")
    if promotion_origin == "predecessor_completion":
        provenance_plan = {**(atomic_completion if isinstance(atomic_completion, dict) else {}), **plan}
        provenance = {
            "promotion_origin": promotion_origin,
            "initial_selection_receipt": None,
            "initial_selection_receipt_ref": None,
            **validate_promotion_provenance(root, provenance_plan, validated_task_id, validation_verdict),
        }
        provenance["predecessor_completion_receipt_ref"] = provenance.get("validation_report_path")
    else:
        provenance = validate_initial_selection_provenance(
            root,
            path,
            data,
            plan,
            item_id=item_id,
            task_id=task_id,
            task_digest=task_digest,
            promotion_origin=promotion_origin,
        )
    target["status"] = "promoted"
    target["promotion"] = {
        "task_id": task_id,
        "task_path": rel_path(root, task_path),
        "task_sha256": task_digest,
        "task_snapshot_path": rel_path(root, task_snapshot_path),
        "promoted_at": now_iso(),
        "mutation_evidence_paths": mutation_evidence,
        **provenance,
    }
    if promotion_origin == "predecessor_completion":
        target["promotion"].update(
            {
                "validated_task_id": validated_task_id,
                "validation_verdict": validation_verdict,
            }
        )
    entry = mutation_entry("promote", plan, before_order, item_order(data))
    entry.update(
        {
            "item_id": item_id,
            "task_id": task_id,
            "validated_task_id": validated_task_id or None,
            "promotion_origin": promotion_origin,
            "before_pack_sha256": coherence.get("before_pack_sha256"),
        }
    )
    data.setdefault("mutation_log", []).append(entry)


def apply_normalization(root: Path, path: Path, data: dict[str, Any], items: list[Any], plan: dict[str, Any], coherence: dict[str, Any], before_order: list[str]) -> int | None:
    action = "normalize_initial_selection_provenance"
    receipt = plan.get("initial_selection_receipt")
    if not isinstance(receipt, dict):
        raise SystemExit("Initial-selection normalization requires `initial_selection_receipt`.")
    item_id = str(receipt.get("initial_item_id") or plan.get("item_id") or "").strip()
    target = next(
        (item for item in items if isinstance(item, dict) and str(item.get("item_id") or "") == item_id),
        None,
    )
    if target is None:
        raise SystemExit("Initial-selection normalization references an unknown pack item.")
    promotion = target.get("promotion")
    if not isinstance(promotion, dict):
        raise SystemExit("Initial-selection normalization requires preserved promotion provenance.")
    if target.get("status") not in {"promoted", "in_progress", "consumed"}:
        raise SystemExit("Only an already-selected initial item can be normalized.")
    task_id = str(promotion.get("task_id") or "")
    task_digest = _required_sha256(promotion.get("task_sha256"), "Initial promotion task_sha256")
    existing_normalization = promotion.get("provenance_normalization")
    if isinstance(existing_normalization, dict):
        existing_receipt = promotion.get("initial_selection_receipt")
        if existing_receipt == receipt:
            output = {
                "status": "already_normalized",
                "action": action,
                "pack_path": rel_path(root, path),
                "pack_id": data.get("pack_id"),
                "current_item_id": data.get("current_item_id"),
                "pack_transition_verdict": {"status": "pass", "evidence_ref": rel_path(root, path)},
                "historical_authority_verdict": existing_normalization.get("historical_authority_verdict"),
            }
            json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
            sys.stdout.write("\n")
            return 0
        raise SystemExit("Initial-selection provenance is already normalized with a conflicting receipt.")

    before_current = data.get("current_item_id")
    before_item_order = item_order(data)
    before_item_states = [
        {
            "item_id": item.get("item_id"),
            "order": item.get("order"),
            "status": item.get("status"),
            "acceptance": copy.deepcopy(item.get("acceptance")),
            "result": copy.deepcopy(item.get("result")),
            "completion": copy.deepcopy(item.get("completion")),
        }
        for item in items
        if isinstance(item, dict)
    ]
    before_other_items = [copy.deepcopy(item) for item in items if item is not target]
    before_promotion = copy.deepcopy(promotion)
    verified = validate_initial_selection_receipt(
        root,
        path,
        data,
        receipt,
        task_id=task_id,
        task_digest=task_digest,
        operation=action,
        require_mutation_binding=False,
    )
    promotion_origin = str(plan.get("promotion_origin") or "bootstrap_initial_selection")
    if promotion_origin not in {"bootstrap_initial_selection", "authorized_initial_selection"}:
        raise SystemExit("Normalized initial selection requires an initial promotion origin.")
    inline_digest = sha256_bytes(
        json.dumps(verified, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    promotion.update(
        {
            "promotion_origin": promotion_origin,
            "initial_selection_receipt": verified,
            "initial_selection_receipt_ref": f"inline:sha256:{inline_digest}",
            "predecessor_completion_receipt_ref": None,
            "provenance_normalization": {
                "schema_version": 1,
                "mode": "legacy_initial_selection",
                "normalized_at": now_iso(),
                "authority_mode": verified.get("authority_mode"),
                "historical_selection_authority_status": verified.get(
                    "historical_selection_authority_status"
                ),
                "historical_authority_verdict": "partial"
                if verified.get("authority_mode") == "current_ratification"
                else "pass",
                "normalization_authority_status": "allowed_now",
                "retroactive_claim_allowed": False,
            },
        }
    )
    entry = mutation_entry(action, plan, before_order, before_order)
    entry.update(
        {
            "item_id": item_id,
            "task_id": task_id,
            "before_pack_sha256": coherence.get("before_pack_sha256"),
            "creation_snapshot_sha256": verified.get("pack_creation_snapshot_sha256"),
            "authority_receipt_ref": verified.get("authority_receipt_ref"),
            "authority_receipt_sha256": verified.get("authority_receipt_sha256"),
            "authority_mode": verified.get("authority_mode"),
            "historical_selection_authority_status": verified.get(
                "historical_selection_authority_status"
            ),
        }
    )
    data.setdefault("mutation_log", []).append(entry)

    if data.get("current_item_id") != before_current or item_order(data) != before_item_order:
        raise SystemExit("Initial-selection normalization changed current item or pack order.")
    after_item_states = [
        {
            "item_id": item.get("item_id"),
            "order": item.get("order"),
            "status": item.get("status"),
            "acceptance": item.get("acceptance"),
            "result": item.get("result"),
            "completion": item.get("completion"),
        }
        for item in items
        if isinstance(item, dict)
    ]
    if after_item_states != before_item_states:
        raise SystemExit("Initial-selection normalization changed protected item lifecycle fields.")
    if [item for item in items if item is not target] != before_other_items:
        raise SystemExit("Initial-selection normalization changed another pack item.")
    for key, value in before_promotion.items():
        if promotion.get(key) != value:
            raise SystemExit(f"Initial-selection normalization rewrote existing promotion field: {key}")


def apply_insert(data: dict[str, Any], items: list[Any], plan: dict[str, Any], before_order: list[str]) -> None:
    new_items = plan.get("items") or plan.get("insert_items")
    if not isinstance(new_items, list) or not new_items:
        raise SystemExit("Insert mutation requires non-empty `items`.")
    existing_ids = {str(item.get("item_id")) for item in items if isinstance(item, dict)}
    for item in new_items:
        if not isinstance(item, dict):
            raise SystemExit("Inserted items must be JSON objects.")
        item_id = str(item.get("item_id") or "").strip()
        if not item_id or item_id in existing_ids:
            raise SystemExit(f"Inserted item_id is empty or duplicated: {item_id}")
        item.setdefault("status", "inserted")
        item.setdefault("dependencies", [])
        item.setdefault("source_evidence", evidence_paths_from(plan))
        item.setdefault("promotion", {"task_id": None, "task_path": None, "promoted_at": None})
        item.setdefault("result", {"validation_verdict": None, "progress_verdict": None, "progress_kind": None, "semantic_signature": None, "blocker_signature": None})
        existing_ids.add(item_id)
    insert_before = plan.get("insert_before_item_id") or data.get("current_item_id")
    rebuilt: list[dict[str, Any]] = []
    inserted = False
    for item in sorted_items(data):
        if insert_before and item.get("item_id") == insert_before:
            rebuilt.extend(new_items)
            inserted = True
        rebuilt.append(item)
    if not inserted:
        rebuilt.extend(new_items)
    data["items"] = rebuilt
    renumber_items(data)
    data.setdefault("mutation_log", []).append(mutation_entry("insert", plan, before_order, item_order(data)))


def apply_reorder(data: dict[str, Any], items: list[Any], plan: dict[str, Any], before_order: list[str]) -> None:
    requested = plan.get("item_order") or plan.get("order")
    if not isinstance(requested, list) or not requested:
        raise SystemExit("Reorder mutation requires full `item_order` list.")
    requested_ids = [str(item) for item in requested]
    current_ids = item_order(data)
    if set(requested_ids) != set(current_ids) or len(requested_ids) != len(current_ids):
        raise SystemExit("Reorder mutation must name every existing item exactly once.")
    if requested_ids == current_ids:
        raise SystemExit("Reorder mutation is a no-op; canonical item order is unchanged.")
    by_id = {str(item.get("item_id")): item for item in items if isinstance(item, dict)}
    data["items"] = [by_id[item_id] for item_id in requested_ids]
    for item in data["items"]:
        if item.get("status") == "planned":
            item["status"] = "reordered"
    renumber_items(data)
    data.setdefault("mutation_log", []).append(mutation_entry("reorder", plan, before_order, item_order(data)))


def apply_skip(data: dict[str, Any], items: list[Any], plan: dict[str, Any], before_order: list[str]) -> None:
    item_ids = plan.get("item_ids") or plan.get("skip_item_ids") or plan.get("exclude_item_ids")
    if not isinstance(item_ids, list) or not item_ids:
        raise SystemExit("Skip mutation requires non-empty `item_ids`.")
    targets = {str(item_id) for item_id in item_ids}
    found: set[str] = set()
    for item in items:
        if isinstance(item, dict) and str(item.get("item_id")) in targets:
            item["status"] = "skipped"
            result = item.setdefault("result", {})
            result["skip_reason"] = plan.get("reason")
            result["evidence_paths"] = evidence_paths_from(plan)
            found.add(str(item.get("item_id")))
    missing = sorted(targets - found)
    if missing:
        raise SystemExit(f"Unknown task pack item(s): {', '.join(missing)}")
    data.setdefault("mutation_log", []).append(mutation_entry("skip", plan, before_order, item_order(data)))


def apply_supersede(data: dict[str, Any], items: list[Any], plan: dict[str, Any], before_order: list[str]) -> None:
    data["status"] = "superseded"
    for item in items:
        if isinstance(item, dict) and item.get("status") in {"planned", "inserted", "reordered", "blocked"}:
            item["status"] = "superseded"
    data.setdefault("mutation_log", []).append(mutation_entry("supersede", plan, before_order, item_order(data)))


def apply_terminal_block(data: dict[str, Any], items: list[Any], plan: dict[str, Any], before_order: list[str]) -> None:
    terminal = plan.get("terminal_blocker")
    if not isinstance(terminal, dict):
        raise SystemExit("terminal_block mutation requires `terminal_blocker` object.")
    data["status"] = "terminal_blocked"
    data["terminal_blocker"] = terminal
    current = data.get("current_item_id")
    for item in items:
        if isinstance(item, dict) and (not current or item.get("item_id") == current) and item.get("status") in {"planned", "inserted", "reordered", "blocked"}:
            item["status"] = "terminal_blocked"
            break
    data.setdefault("mutation_log", []).append(mutation_entry("terminal_block", plan, before_order, item_order(data)))
