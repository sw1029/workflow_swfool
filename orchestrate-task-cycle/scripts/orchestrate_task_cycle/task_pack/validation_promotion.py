"""Hash-bound promotion and completion checks for one pack item."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from .contracts import PROMOTION_ORIGINS
from .packet_io import non_empty, require_file_digest
from .provenance import validate_promotion_provenance
from .receipts import validate_initial_selection_receipt
from .storage import _require_within, bounded_workspace_file, bounded_workspace_path, pack_dir

FindingAdder = Callable[..., None]
_COMMON_PROMOTION_FIELDS = ("task_id", "task_path", "task_sha256", "task_snapshot_path", "promoted_at")
_PREDECESSOR_PROMOTION_FIELDS = (
    "validated_task_id",
    "validation_verdict",
    "execution_status",
    "run_report_path",
    "run_report_sha256",
    "validation_report_path",
    "validation_report_sha256",
    "validation_evidence_paths",
    "issue_packet_path",
    "issue_packet_sha256",
    "issue_status",
    "mutation_evidence_paths",
)
_COMPLETION_FIELDS = (
    "completed_task_id",
    "completed_at",
    "validation_verdict",
    "execution_status",
    "run_report_path",
    "run_report_sha256",
    "validation_report_path",
    "validation_report_sha256",
    "validation_evidence_paths",
    "issue_packet_path",
    "issue_packet_sha256",
    "issue_status",
    "completion_evidence_paths",
)


def _validate_bound_promotion(
    data: dict[str, Any],
    item: dict[str, Any],
    item_id: str,
    promotion: dict[str, Any],
    promotion_origin: str,
    path: Path | None,
    prospective_task_digests: set[str] | None,
    add: FindingAdder,
) -> None:
    if path is None:
        return
    root = path.resolve().parents[2]
    audit_plan = {**promotion, "evidence_paths": promotion.get("mutation_evidence_paths")}
    try:
        if promotion_origin == "predecessor_completion":
            validate_promotion_provenance(
                root,
                audit_plan,
                str(promotion.get("validated_task_id") or "").strip(),
                str(promotion.get("validation_verdict") or "").strip().lower(),
            )
        else:
            receipt = promotion.get("initial_selection_receipt")
            if not isinstance(receipt, dict):
                raise SystemExit("Initial promotion receipt is missing.")
            if receipt.get("task_snapshot_ref") != promotion.get("task_snapshot_path"):
                raise SystemExit("Initial receipt and promotion task snapshot refs differ.")
            operation = (
                "normalize_initial_selection_provenance"
                if isinstance(promotion.get("provenance_normalization"), dict)
                else "promote"
            )
            validate_initial_selection_receipt(
                root,
                path,
                data,
                receipt,
                task_id=str(promotion.get("task_id") or ""),
                task_digest=str(promotion.get("task_sha256") or ""),
                operation=operation,
            )
        snapshot_path = bounded_workspace_file(root, promotion.get("task_snapshot_path"), "Promotion task_snapshot_path")
        _require_within(snapshot_path, pack_dir(root), "Promotion task_snapshot_path")
        require_file_digest(snapshot_path, promotion.get("task_sha256"), "Promotion task snapshot")
        if data.get("status") == "active" and item.get("status") in {"promoted", "in_progress"}:
            prospective_digest = str(promotion.get("task_sha256") or "")
            raw_task_path = str(promotion.get("task_path") or "")
            bounded_workspace_path(root, raw_task_path, "Promotion task_path")
            if not prospective_task_digests or prospective_digest not in prospective_task_digests:
                task_path = bounded_workspace_file(root, raw_task_path, "Promotion task_path")
                require_file_digest(task_path, prospective_digest, "Promotion task_path")
    except SystemExit as exc:
        add(
            "block",
            "promotion_provenance_invalid",
            "Promoted/in-progress item provenance no longer verifies against durable artifacts.",
            {"item_id": item_id, "error": str(exc)},
        )


def _validate_completion(
    item: dict[str, Any],
    item_id: str,
    promotion: dict[str, Any],
    path: Path | None,
    add: FindingAdder,
) -> None:
    completion = item.get("completion")
    if not isinstance(completion, dict):
        add(
            "block",
            "completion_provenance_missing",
            "Consumed items require hash-bound completion run, validation, issue, and mutation provenance.",
            {"item_id": item_id},
        )
        return
    missing = [field for field in _COMPLETION_FIELDS if not non_empty(completion.get(field))]
    promoted_task_id = str(promotion.get("task_id") or "").strip()
    if missing:
        add(
            "block",
            "completion_provenance_incomplete",
            "Consumed item completion provenance is incomplete.",
            {"item_id": item_id, "missing_fields": missing},
        )
    elif str(completion.get("completed_task_id") or "").strip() != promoted_task_id:
        add(
            "block",
            "completion_task_identity_mismatch",
            "Consumed item completion provenance must validate the task created by promotion.",
            {"item_id": item_id, "promoted_task_id": promoted_task_id},
        )
    elif path is not None:
        completion_plan = {**completion, "evidence_paths": completion.get("completion_evidence_paths")}
        try:
            validate_promotion_provenance(
                path.resolve().parents[2],
                completion_plan,
                promoted_task_id,
                str(completion.get("validation_verdict") or "").strip().lower(),
            )
        except SystemExit as exc:
            add(
                "block",
                "completion_provenance_invalid",
                "Consumed item completion provenance no longer verifies against durable artifacts.",
                {"item_id": item_id, "error": str(exc)},
            )


def validate_item_promotion(
    data: dict[str, Any],
    item: dict[str, Any],
    item_id: str,
    path: Path | None,
    prospective_task_digests: set[str] | None,
    add: FindingAdder,
) -> None:
    if item.get("status") not in {"promoted", "in_progress", "consumed"}:
        return
    promotion = item.get("promotion")
    if not isinstance(promotion, dict):
        add(
            "block",
            "promotion_provenance_missing",
            "Promoted/in-progress/consumed items require hash-bound task, run, validation, issue, and mutation provenance.",
            {"item_id": item_id},
        )
        return
    promotion_origin = str(promotion.get("promotion_origin") or "predecessor_completion").strip().lower()
    if promotion_origin not in PROMOTION_ORIGINS:
        add(
            "block",
            "promotion_origin_invalid",
            "Promotion origin is not recognized.",
            {"item_id": item_id, "promotion_origin": promotion_origin},
        )
    required_fields = _COMMON_PROMOTION_FIELDS + (
        _PREDECESSOR_PROMOTION_FIELDS if promotion_origin == "predecessor_completion" else ("initial_selection_receipt",)
    )
    missing = [field for field in required_fields if not non_empty(promotion.get(field))]
    if missing:
        add(
            "block",
            "promotion_provenance_incomplete",
            "Promoted/in-progress item provenance is incomplete.",
            {"item_id": item_id, "missing_fields": missing},
        )
    else:
        _validate_bound_promotion(data, item, item_id, promotion, promotion_origin, path, prospective_task_digests, add)
    if item.get("status") == "consumed":
        _validate_completion(item, item_id, promotion, path, add)

