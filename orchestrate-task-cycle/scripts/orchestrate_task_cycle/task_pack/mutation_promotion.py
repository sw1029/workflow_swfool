"""Promotion-specific task-pack mutation behavior."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contracts import PACK_COHERENCE_VERSION, PACK_ID_PATTERN, PROMOTION_ORIGINS
from .ordering import active_in_flight_items, item_order, next_item
from .packet_io import (
    require_file_digest,
    truthy,
    verify_evidence_files,
    write_content_addressed_file,
)
from .provenance import (
    consume_in_flight_for_atomic_promotion,
    mutation_entry,
    validate_initial_selection_provenance,
    validate_promotion_provenance,
)
from .storage import (
    _require_within,
    bounded_workspace_file,
    now_iso,
    pack_dir,
    rel_path,
    sha256_file,
)
from .state_machine import dependencies_satisfied, item_index


@dataclass(frozen=True)
class _PromotionRequest:
    item_id: str
    task_id: str
    task_path_value: str
    validated_task_id: str
    validation_verdict: str
    origin: str


def _promotion_request(data: dict[str, Any], plan: dict[str, Any]) -> _PromotionRequest:
    request = _PromotionRequest(
        item_id=str(plan.get("item_id") or data.get("current_item_id") or "").strip(),
        task_id=str(plan.get("task_id") or "").strip(),
        task_path_value=str(plan.get("task_path") or "task.md").strip(),
        validated_task_id=str(plan.get("validated_task_id") or "").strip(),
        validation_verdict=str(plan.get("validation_verdict") or "").strip().lower(),
        origin=str(plan.get("promotion_origin") or "predecessor_completion")
        .strip()
        .lower(),
    )
    if request.origin not in PROMOTION_ORIGINS:
        raise SystemExit(
            "Promotion origin must be predecessor_completion, bootstrap_initial_selection, or authorized_initial_selection."
        )
    if not request.item_id or not request.task_id:
        raise SystemExit("Promotion requires `item_id` and `task_id`.")
    if request.origin == "predecessor_completion" and not request.validated_task_id:
        raise SystemExit("Predecessor promotion requires `validated_task_id`.")
    if not PACK_ID_PATTERN.fullmatch(request.task_id) or (
        request.validated_task_id
        and not PACK_ID_PATTERN.fullmatch(request.validated_task_id)
    ):
        raise SystemExit(
            "Promotion task identifiers must be path-safe tokens of at most 128 characters."
        )
    return request


def _consume_in_flight(
    root: Path,
    data: dict[str, Any],
    plan: dict[str, Any],
    coherence: dict[str, Any],
    request: _PromotionRequest,
) -> object:
    in_flight = [
        str(item.get("item_id") or "") for item in active_in_flight_items(data)
    ]
    atomic_completion = plan.get("consume_current_item")
    if in_flight and isinstance(atomic_completion, dict):
        completed_task_id = consume_in_flight_for_atomic_promotion(
            root,
            data,
            atomic_completion,
            require_current_verdicts=coherence.get("contract_version")
            == PACK_COHERENCE_VERSION,
        )
        if (
            request.origin != "predecessor_completion"
            or request.validated_task_id != completed_task_id
        ):
            raise SystemExit(
                "Atomic successor promotion must use the consumed task as predecessor provenance."
            )
        in_flight = [
            str(item.get("item_id") or "") for item in active_in_flight_items(data)
        ]
    if in_flight:
        raise SystemExit(
            f"Promotion requires the existing in-flight item to be consumed or closed first: {', '.join(in_flight)}"
        )
    return atomic_completion


def _validate_unblock_receipt(
    root: Path,
    target: dict[str, Any],
    plan: dict[str, Any],
    coherence: dict[str, Any],
) -> dict[str, Any]:
    receipt = plan.get("unblock_receipt")
    if not isinstance(receipt, dict) or receipt.get("schema_version") != 1:
        raise SystemExit(
            "Blocked item promotion requires unblock_receipt schema_version=1."
        )
    item_id = str(target.get("item_id") or "")
    if receipt.get("item_id") != item_id or receipt.get("decision") != "unblocked":
        raise SystemExit(
            "Unblock receipt must identify the blocked item and decision=unblocked."
        )
    expected_before = str(coherence.get("before_pack_sha256") or "").removeprefix(
        "sha256:"
    )
    supplied_before = str(receipt.get("before_pack_sha256") or "").removeprefix(
        "sha256:"
    )
    if not expected_before or supplied_before != expected_before:
        raise SystemExit("Unblock receipt must bind the exact predecessor pack hash.")
    blocker_signature = str(
        target.get("blocker_signature")
        or (target.get("result") or {}).get("blocker_signature")
        or ""
    )
    supplied_signature = str(receipt.get("blocker_signature") or "")
    if not supplied_signature or (
        blocker_signature and supplied_signature != blocker_signature
    ):
        raise SystemExit(
            "Unblock receipt blocker signature is missing or does not match the blocked item."
        )
    evidence = receipt.get("decision_evidence")
    if not isinstance(evidence, list) or not evidence:
        raise SystemExit(
            "Unblock receipt requires non-empty hash-bound decision_evidence."
        )
    for entry in evidence:
        if not isinstance(entry, dict):
            raise SystemExit(
                "Unblock receipt decision_evidence entries must be objects."
            )
        evidence_path = bounded_workspace_file(
            root, entry.get("path"), "Unblock decision evidence"
        )
        require_file_digest(
            evidence_path, entry.get("sha256"), "Unblock decision evidence"
        )
    return copy.deepcopy(receipt)


def _promotion_target(
    root: Path,
    data: dict[str, Any],
    items: list[Any],
    plan: dict[str, Any],
    coherence: dict[str, Any],
    request: _PromotionRequest,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    target = next(
        (
            item
            for item in items
            if isinstance(item, dict) and str(item.get("item_id")) == request.item_id
        ),
        None,
    )
    if target is None:
        raise SystemExit(f"Unknown task pack item: {request.item_id}")
    unblock_receipt = None
    expected = next_item(data)
    if target.get("status") == "blocked":
        unblock_receipt = _validate_unblock_receipt(root, target, plan, coherence)
        if not dependencies_satisfied(target, item_index(data)):
            raise SystemExit(
                "Blocked item cannot be unblocked before every dependency is consumed."
            )
        if expected is not None and int(expected.get("order") or 0) < int(
            target.get("order") or 0
        ):
            raise SystemExit(
                "promote_next_item may not bypass an earlier dependency-ready item."
            )
    elif expected is None or str(expected.get("item_id")) != request.item_id:
        raise SystemExit(
            "promote_next_item may promote only the current next item (the earliest dependency-ready item)."
        )
    if target.get("status") not in {"planned", "inserted", "reordered", "blocked"}:
        raise SystemExit(
            f"Task pack item is not promotable from status {target.get('status')}: {request.item_id}"
        )
    result = target.get("result")
    acceptance_diluted = (
        result.get("acceptance_diluted") if isinstance(result, dict) else False
    )
    if truthy(target.get("acceptance_diluted")) or truthy(acceptance_diluted):
        raise SystemExit(
            "A task pack item with acceptance_diluted=true cannot be promoted."
        )
    return target, unblock_receipt


def _task_snapshot(
    root: Path,
    data: dict[str, Any],
    request: _PromotionRequest,
    task_path: Path,
    task_digest: str,
) -> Path:
    snapshot_directory = _require_within(
        pack_dir(root) / "task_snapshots" / str(data.get("pack_id")),
        pack_dir(root),
        "Promotion task snapshot directory",
    )
    snapshot_name = (
        f"{request.item_id[:48]}-{request.task_id[:48]}-{task_digest[:16]}.md"
    )
    task_snapshot_path = _require_within(
        snapshot_directory / snapshot_name,
        pack_dir(root),
        "Promotion task snapshot path",
    )
    write_content_addressed_file(
        task_snapshot_path, task_path.read_bytes(), "Promotion task snapshot"
    )
    return task_snapshot_path


def _promotion_provenance(
    root: Path,
    path: Path,
    data: dict[str, Any],
    plan: dict[str, Any],
    request: _PromotionRequest,
    task_digest: str,
    task_snapshot_path: Path,
    atomic_completion: object,
) -> dict[str, Any]:
    if request.origin != "predecessor_completion":
        supplied_receipt = plan.get("initial_selection_receipt")
        if not isinstance(supplied_receipt, dict):
            raise SystemExit("Initial selection requires `initial_selection_receipt`.")
        if supplied_receipt.get("task_snapshot_ref") != rel_path(
            root, task_snapshot_path
        ):
            raise SystemExit(
                "Initial selection receipt must reference the deterministic task snapshot."
            )
        return validate_initial_selection_provenance(
            root,
            path,
            data,
            plan,
            item_id=request.item_id,
            task_id=request.task_id,
            task_digest=task_digest,
            promotion_origin=request.origin,
        )
    provenance_plan = {
        **(atomic_completion if isinstance(atomic_completion, dict) else {}),
        **plan,
    }
    provenance = {
        "promotion_origin": request.origin,
        "initial_selection_receipt": None,
        "initial_selection_receipt_ref": None,
        **validate_promotion_provenance(
            root,
            provenance_plan,
            request.validated_task_id,
            request.validation_verdict,
        ),
    }
    provenance["predecessor_completion_receipt_ref"] = provenance.get(
        "validation_report_path"
    )
    return provenance


def _record_promotion(
    root: Path,
    data: dict[str, Any],
    target: dict[str, Any],
    plan: dict[str, Any],
    coherence: dict[str, Any],
    before_order: list[str],
    request: _PromotionRequest,
    task_path: Path,
    task_digest: str,
    task_snapshot_path: Path,
    mutation_evidence: list[str],
    provenance: dict[str, Any],
    unblock_receipt: dict[str, Any] | None,
) -> None:
    target["status"] = "promoted"
    target["promotion"] = {
        "task_id": request.task_id,
        "task_path": rel_path(root, task_path),
        "task_sha256": task_digest,
        "task_snapshot_path": rel_path(root, task_snapshot_path),
        "promoted_at": now_iso(),
        "mutation_evidence_paths": mutation_evidence,
        **provenance,
    }
    if unblock_receipt is not None:
        target["promotion"]["unblock_receipt"] = unblock_receipt
    if request.origin == "predecessor_completion":
        target["promotion"].update(
            {
                "validated_task_id": request.validated_task_id,
                "validation_verdict": request.validation_verdict,
            }
        )
    entry = mutation_entry("promote", plan, before_order, item_order(data))
    entry.update(
        {
            "item_id": request.item_id,
            "task_id": request.task_id,
            "validated_task_id": request.validated_task_id or None,
            "promotion_origin": request.origin,
            "before_pack_sha256": coherence.get("before_pack_sha256"),
        }
    )
    data.setdefault("mutation_log", []).append(entry)


def apply_promote(
    root: Path,
    path: Path,
    data: dict[str, Any],
    items: list[Any],
    plan: dict[str, Any],
    coherence: dict[str, Any],
    before_order: list[str],
) -> None:
    request = _promotion_request(data, plan)
    atomic_completion = _consume_in_flight(root, data, plan, coherence, request)
    mutation_evidence = (
        verify_evidence_files(
            root, plan.get("evidence_paths"), "Promotion mutation evidence_paths"
        )
        if request.origin == "predecessor_completion" or plan.get("evidence_paths")
        else []
    )
    task_path = bounded_workspace_file(
        root, request.task_path_value, "Promotion task_path"
    )
    task_digest = sha256_file(task_path)
    target, unblock_receipt = _promotion_target(
        root, data, items, plan, coherence, request
    )
    task_snapshot_path = _task_snapshot(root, data, request, task_path, task_digest)
    provenance = _promotion_provenance(
        root,
        path,
        data,
        plan,
        request,
        task_digest,
        task_snapshot_path,
        atomic_completion,
    )
    _record_promotion(
        root,
        data,
        target,
        plan,
        coherence,
        before_order,
        request,
        task_path,
        task_digest,
        task_snapshot_path,
        mutation_evidence,
        provenance,
        unblock_receipt,
    )


__all__ = ("apply_promote",)
