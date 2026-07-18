"""Initial-selection provenance normalization mutation behavior."""

from __future__ import annotations

import copy
from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Any

from .ordering import item_order
from .provenance import mutation_entry
from .receipts import _required_sha256, validate_initial_selection_receipt
from .storage import now_iso, rel_path, sha256_bytes


_ACTION = "normalize_initial_selection_provenance"


@dataclass(frozen=True)
class _NormalizationTarget:
    receipt: dict[str, Any]
    item_id: str
    target: dict[str, Any]
    promotion: dict[str, Any]
    task_id: str
    task_digest: str


@dataclass(frozen=True)
class _ProtectedState:
    current_item_id: object
    item_order: list[str]
    item_states: list[dict[str, Any]]
    other_items: list[dict[str, Any]]
    promotion: dict[str, Any]


def _normalization_target(
    items: list[Any], plan: dict[str, Any]
) -> _NormalizationTarget:
    receipt = plan.get("initial_selection_receipt")
    if not isinstance(receipt, dict):
        raise SystemExit(
            "Initial-selection normalization requires `initial_selection_receipt`."
        )
    item_id = str(receipt.get("initial_item_id") or plan.get("item_id") or "").strip()
    target = next(
        (
            item
            for item in items
            if isinstance(item, dict) and str(item.get("item_id") or "") == item_id
        ),
        None,
    )
    if target is None:
        raise SystemExit(
            "Initial-selection normalization references an unknown pack item."
        )
    promotion = target.get("promotion")
    if not isinstance(promotion, dict):
        raise SystemExit(
            "Initial-selection normalization requires preserved promotion provenance."
        )
    if target.get("status") not in {"promoted", "in_progress", "consumed"}:
        raise SystemExit("Only an already-selected initial item can be normalized.")
    task_id = str(promotion.get("task_id") or "")
    task_digest = _required_sha256(
        promotion.get("task_sha256"), "Initial promotion task_sha256"
    )
    return _NormalizationTarget(
        receipt, item_id, target, promotion, task_id, task_digest
    )


def _existing_normalization_result(
    root: Path,
    path: Path,
    data: dict[str, Any],
    context: _NormalizationTarget,
) -> int | None:
    existing = context.promotion.get("provenance_normalization")
    if not isinstance(existing, dict):
        return None
    if context.promotion.get("initial_selection_receipt") != context.receipt:
        raise SystemExit(
            "Initial-selection provenance is already normalized with a conflicting receipt."
        )
    output = {
        "status": "already_normalized",
        "action": _ACTION,
        "pack_path": rel_path(root, path),
        "pack_id": data.get("pack_id"),
        "current_item_id": data.get("current_item_id"),
        "pack_transition_verdict": {
            "status": "pass",
            "evidence_ref": rel_path(root, path),
        },
        "historical_authority_verdict": existing.get("historical_authority_verdict"),
    }
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def _protected_state(
    data: dict[str, Any],
    items: list[Any],
    context: _NormalizationTarget,
) -> _ProtectedState:
    item_states = [
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
    return _ProtectedState(
        current_item_id=data.get("current_item_id"),
        item_order=item_order(data),
        item_states=item_states,
        other_items=[
            copy.deepcopy(item) for item in items if item is not context.target
        ],
        promotion=copy.deepcopy(context.promotion),
    )


def _update_promotion(
    root: Path,
    path: Path,
    data: dict[str, Any],
    plan: dict[str, Any],
    context: _NormalizationTarget,
) -> dict[str, Any]:
    verified = validate_initial_selection_receipt(
        root,
        path,
        data,
        context.receipt,
        task_id=context.task_id,
        task_digest=context.task_digest,
        operation=_ACTION,
        require_mutation_binding=False,
    )
    origin = str(plan.get("promotion_origin") or "bootstrap_initial_selection")
    if origin not in {
        "bootstrap_initial_selection",
        "authorized_initial_selection",
    }:
        raise SystemExit(
            "Normalized initial selection requires an initial promotion origin."
        )
    inline_digest = sha256_bytes(
        json.dumps(
            verified, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
    )
    context.promotion.update(
        {
            "promotion_origin": origin,
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
    return verified


def _record_normalization(
    data: dict[str, Any],
    plan: dict[str, Any],
    coherence: dict[str, Any],
    before_order: list[str],
    context: _NormalizationTarget,
    verified: dict[str, Any],
) -> None:
    entry = mutation_entry(_ACTION, plan, before_order, before_order)
    entry.update(
        {
            "item_id": context.item_id,
            "task_id": context.task_id,
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


def _assert_protected_state(
    data: dict[str, Any],
    items: list[Any],
    context: _NormalizationTarget,
    before: _ProtectedState,
) -> None:
    if (
        data.get("current_item_id") != before.current_item_id
        or item_order(data) != before.item_order
    ):
        raise SystemExit(
            "Initial-selection normalization changed current item or pack order."
        )
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
    if after_item_states != before.item_states:
        raise SystemExit(
            "Initial-selection normalization changed protected item lifecycle fields."
        )
    if [item for item in items if item is not context.target] != before.other_items:
        raise SystemExit("Initial-selection normalization changed another pack item.")
    for key, value in before.promotion.items():
        if context.promotion.get(key) != value:
            raise SystemExit(
                f"Initial-selection normalization rewrote existing promotion field: {key}"
            )


def apply_normalization(
    root: Path,
    path: Path,
    data: dict[str, Any],
    items: list[Any],
    plan: dict[str, Any],
    coherence: dict[str, Any],
    before_order: list[str],
) -> int | None:
    context = _normalization_target(items, plan)
    existing_result = _existing_normalization_result(root, path, data, context)
    if existing_result is not None:
        return existing_result
    before = _protected_state(data, items, context)
    verified = _update_promotion(root, path, data, plan, context)
    _record_normalization(data, plan, coherence, before_order, context, verified)
    _assert_protected_state(data, items, context, before)
    return None


__all__ = ("apply_normalization",)
