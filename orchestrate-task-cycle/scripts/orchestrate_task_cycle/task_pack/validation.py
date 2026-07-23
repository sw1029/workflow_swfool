"""Ordered pack and publication validation."""
from __future__ import annotations

from pathlib import Path
from collections.abc import Callable
from typing import Any

from .contracts import ITEM_STATUSES, OPEN_RESIDUAL_STATUSES, PACK_ID_PATTERN, PACK_STATUSES
from .validation_promotion import validate_item_promotion
from .validation_scope import validate_item_scope
from .validation_verdicts import validate_item_verdicts
from .state_machine import dependency_findings, lifecycle_findings
from .prerequisite_chain import validate_pack_chain_coherence


FindingAdder = Callable[..., None]


def _validate_items(
    data: dict[str, Any],
    items: list[Any],
    path: Path | None,
    prospective_task_digests: set[str] | None,
    prospective_creation_snapshots: dict[str, dict[str, Any]] | None,
    prospective_task_snapshots: dict[str, bytes] | None,
    add: FindingAdder,
) -> set[str]:
    seen_ids: set[str] = set()
    seen_orders: set[int] = set()
    item_by_id: dict[str, dict[str, Any]] = {}
    residual_links: list[tuple[str, str]] = []
    prerequisite_chains: list[tuple[str, dict[str, Any]]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            add("block", "invalid_item", "Task pack item must be an object.", {"index": index})
            continue
        for field in ("item_id", "order", "status", "title", "objective", "validation_profile", "progress_target"):
            if field not in item:
                add("block", "missing_item_field", f"Task pack item is missing `{field}`.", {"index": index})
        item_id = str(item.get("item_id") or "")
        if not item_id:
            add("block", "empty_item_id", "Task pack item has empty item_id.", {"index": index})
        elif not PACK_ID_PATTERN.fullmatch(item_id):
            add("block", "invalid_item_id", "Task pack item_id must be one path-safe token.", {"item_id": item_id})
        elif item_id in seen_ids:
            add("block", "duplicate_item_id", "Task pack item_id is duplicated.", {"item_id": item_id})
        seen_ids.add(item_id)
        if item_id:
            item_by_id[item_id] = item
        order = item.get("order")
        if not isinstance(order, int) or order <= 0:
            add("block", "invalid_item_order", "Task pack item order must be a positive integer.", {"item_id": item_id, "order": order})
        elif order in seen_orders:
            add("block", "duplicate_item_order", "Task pack item order is duplicated.", {"order": order})
        seen_orders.add(order) if isinstance(order, int) else None
        if item.get("status") not in ITEM_STATUSES:
            add("block", "invalid_item_status", "Invalid task pack item status.", {"item_id": item_id, "status": item.get("status")})
        validate_item_promotion(
            data,
            item,
            item_id,
            path,
            prospective_task_digests,
            prospective_creation_snapshots,
            prospective_task_snapshots,
            add,
        )
        result = validate_item_verdicts(item, item_id, add)
        validate_item_scope(item, item_id, result, residual_links, add)
        chain = item.get("bounded_prerequisite_chain")
        if not isinstance(chain, dict) and isinstance(result, dict):
            chain = result.get("bounded_prerequisite_chain")
        if isinstance(chain, dict):
            prerequisite_chains.append((item_id, chain))
    validate_pack_chain_coherence(prerequisite_chains, add)
    for item_id, residual_item_id in residual_links:
        residual = item_by_id.get(residual_item_id)
        if residual is None:
            add(
                "block", "scope_fidelity_residual_item_unknown",
                "`residual_item_id` must reference another pack item.",
                {"item_id": item_id, "residual_item_id": residual_item_id},
            )
        elif residual.get("status") not in OPEN_RESIDUAL_STATUSES:
            add(
                "block", "scope_fidelity_residual_item_not_open",
                "`residual_item_id` must remain open when the current item narrows a measurable directive.",
                {"item_id": item_id, "residual_item_id": residual_item_id, "residual_status": residual.get("status")},
            )
    in_flight = [
        str(item.get("item_id") or "")
        for item in items
        if isinstance(item, dict) and item.get("status") in {"promoted", "in_progress"}
    ]
    if len(in_flight) > 1:
        add(
            "block", "multiple_in_flight_pack_items",
            "A task pack may have at most one promoted/in-progress item at a time.",
            {"item_ids": in_flight},
        )
    return seen_ids


def _validate_terminal(data: dict[str, Any], add: FindingAdder) -> None:
    if data.get("status") == "terminal_blocked" and not data.get("terminal_blocker"):
        add("block", "terminal_blocker_missing", "`terminal_blocked` pack requires `terminal_blocker`.")
    terminal = data.get("terminal_blocker")
    if not isinstance(terminal, dict):
        return
    for field in ("semantic_signature", "blocker_signature", "required_handoff", "evidence_paths"):
        if not terminal.get(field):
            add("block", "terminal_blocker_field_missing", f"`terminal_blocker` requires `{field}`.", {"field": field})
    if terminal.get("provider_reattempt_required") is True:
        add(
            "block", "provider_terminal_seal_before_bounded_retry",
            "Task pack cannot terminal-block a provider family while bounded provider retry is still required.",
        )
    if terminal.get("authorized_alternative_path_exists") is True and not terminal.get("authorized_alternative_path_attempted"):
        add(
            "block", "seal_denied_authorized_alternative_unattempted",
            "Task pack cannot seal a family while an authority-permitted productive alternative remains unattempted.",
        )
    if terminal.get("untried_actionable_root_cause_exists") is True:
        add(
            "block", "seal_denied_untried_actionable_root_cause",
            "Task pack cannot terminal-block while an authority-allowed actionable root cause remains untried.",
        )
    if terminal.get("terminal_quiescence") is True and terminal.get("commit_skipped_reason") != "terminal_quiescence":
        add(
            "warn", "terminal_quiescence_missing_commit_skip_reason",
            "Terminal quiescence should record `commit_skipped_reason: terminal_quiescence`.",
        )


def validate_pack(
    data: dict[str, Any],
    path: Path | None = None,
    *,
    prospective_task_digests: set[str] | None = None,
    prospective_creation_snapshots: dict[str, dict[str, Any]] | None = None,
    prospective_task_snapshots: dict[str, bytes] | None = None,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    def add(severity: str, code: str, message: str, evidence: Any = None) -> None:
        item: dict[str, Any] = {"severity": severity, "code": code, "message": message}
        if evidence is not None:
            item["evidence"] = evidence
        findings.append(item)

    for field in ("schema_version", "pack_id", "status", "goal", "items", "mutation_log"):
        if field not in data:
            add("block", "missing_required_field", f"Task pack is missing `{field}`.", {"path": str(path) if path else None})
    if data.get("schema_version") != 1:
        add("block", "unsupported_schema_version", "`schema_version` must be 1.", {"value": data.get("schema_version")})
    pack_id = str(data.get("pack_id") or "").strip()
    if not PACK_ID_PATTERN.fullmatch(pack_id):
        add("block", "invalid_pack_id", "`pack_id` must be one path-safe token of at most 128 characters.", {"pack_id": pack_id})
    if path is not None and pack_id and path.stem != pack_id:
        add(
            "block",
            "pack_id_path_mismatch",
            "Task pack filename must match its `pack_id`.",
            {"pack_id": pack_id, "filename": path.name},
        )
    status = data.get("status")
    if status not in PACK_STATUSES:
        add("block", "invalid_pack_status", "Invalid task pack status.", {"status": status})

    items = data.get("items")
    if not isinstance(items, list) or not items:
        add("block", "items_missing", "`items` must be a non-empty list.")
        return findings

    seen_ids = _validate_items(
        data,
        items,
        path,
        prospective_task_digests,
        prospective_creation_snapshots,
        prospective_task_snapshots,
        add,
    )
    dependency_findings(data, add)
    lifecycle_findings(data, add)
    current = data.get("current_item_id")
    if current and current not in seen_ids:
        add("block", "current_item_missing", "`current_item_id` does not match any item.", {"current_item_id": current})
    _validate_terminal(data, add)
    if not isinstance(data.get("mutation_log", []), list):
        add("block", "mutation_log_invalid", "`mutation_log` must be a list.")
    return findings


def publication_findings(
    data: dict[str, Any],
    path: Path,
    *,
    check_size: bool,
    prospective_task_digests: set[str] | None = None,
    prospective_creation_snapshots: dict[str, dict[str, Any]] | None = None,
    prospective_task_snapshots: dict[str, bytes] | None = None,
) -> list[dict[str, Any]]:
    findings = validate_pack(
        data,
        path,
        prospective_task_digests=prospective_task_digests,
        prospective_creation_snapshots=prospective_creation_snapshots,
        prospective_task_snapshots=prospective_task_snapshots,
    )
    if check_size:
        items = data.get("items") if isinstance(data.get("items"), list) else []
        if not 2 <= len(items) <= 5:
            findings.append(
                {
                    "severity": "block",
                    "code": "new_pack_item_count_out_of_bounds",
                    "message": "A newly derived pack must contain 2-5 items; larger replacements require exact carry-forward binding.",
                    "evidence": {"item_count": len(items)},
                }
            )
    if findings and not any(item.get("code") == "publication_findings_not_clean" for item in findings):
        findings.append(
            {
                "severity": "block",
                "code": "publication_findings_not_clean",
                "message": "New task-pack publication requires findings=[].",
                "evidence": {"finding_codes": [str(item.get("code")) for item in findings]},
            }
        )
    return findings
