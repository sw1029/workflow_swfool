"""Promotion and completion provenance validation."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contracts import (
    ISSUE_MUTATION_STATUSES,
    ISSUE_NOOP_STATUSES,
    PROMOTION_TERMINAL_EXECUTION_STATUSES,
    PROMOTION_VALIDATION_VERDICTS,
)
from .ordering import active_in_flight_items, evidence_paths_from, refresh_current_item, sorted_items
from .packet_io import (
    load_bound_packet,
    non_empty,
    packet_field,
    preserve_verdict_axes,
    verify_evidence_files,
)
from .receipts import validate_initial_selection_receipt
from .storage import bounded_workspace_file, now_iso, rel_path, sha256_bytes

def mutation_entry(action: str, plan: dict[str, Any], before_order: list[str], after_order: list[str]) -> dict[str, Any]:
    reason = str(plan.get("reason") or plan.get("mutation_reason") or "").strip()
    if not reason:
        raise SystemExit("Mutation plan requires `reason`.")
    return {
        "timestamp": now_iso(),
        "action": action,
        "reason": reason,
        "evidence_paths": evidence_paths_from(plan),
        "before_order": before_order,
        "after_order": after_order,
        "actor": str(plan.get("actor") or "$derive-improvement-task"),
    }
def _require_packet_task(packet: dict[str, Any], expected_task_id: str, label: str) -> None:
    observed = str(packet_field(packet, "task_id") or "").strip()
    if not observed or observed != expected_task_id:
        raise SystemExit(f"{label} must be bound to validated_task_id={expected_task_id}.")


def _require_packet_not_blocked(packet: dict[str, Any], label: str) -> None:
    if isinstance(packet.get("result"), dict):
        envelope_status = str(packet.get("status") or "").strip().lower()
        if envelope_status not in {"ok", "pass", "passed"}:
            raise SystemExit(f"{label} result-contract envelope must have status ok/pass.")
        envelope_findings = packet.get("findings")
        if not isinstance(envelope_findings, list):
            raise SystemExit(f"{label} result-contract envelope requires an explicit findings list.")
    else:
        raw_status = str(packet.get("status") or "").strip().lower()
        if raw_status in {"block", "blocked", "error", "failed", "invalid"}:
            raise SystemExit(f"{label} carries a blocking status.")
        envelope_findings = packet.get("findings", [])
        if not isinstance(envelope_findings, list):
            raise SystemExit(f"{label} findings must be a JSON list when present.")
    findings_sets = [envelope_findings]
    payload = packet.get("result")
    if isinstance(payload, dict) and "findings" in payload:
        payload_findings = payload.get("findings")
        if not isinstance(payload_findings, list):
            raise SystemExit(f"{label} nested findings must be a JSON list.")
        findings_sets.append(payload_findings)
    for findings in findings_sets:
        if any(
            isinstance(finding, dict)
            and str(finding.get("severity") or finding.get("status") or "").strip().lower()
            in {"block", "blocked", "error", "failed", "high", "critical"}
            for finding in findings
        ):
            raise SystemExit(f"{label} contains a blocking finding.")


def _require_empty_packet_blockers(packet: dict[str, Any], label: str) -> None:
    blockers = packet_field(packet, "blockers")
    if not isinstance(blockers, list) or blockers:
        raise SystemExit(f"{label} must contain an explicit empty blockers list.")


def _issue_identifier_present(packet: dict[str, Any]) -> bool:
    for key in ("issue_id", "issue_ids", "issue_path", "issue_paths", "issue_url", "issue_urls"):
        if non_empty(packet_field(packet, key)):
            return True
    return False


def validate_promotion_provenance(
    root: Path,
    plan: dict[str, Any],
    validated_task_id: str,
    declared_validation_verdict: str,
) -> dict[str, Any]:
    run_path, run_packet, run_digest = load_bound_packet(
        root,
        plan.get("run_report_path"),
        plan.get("run_report_sha256"),
        "Promotion run report",
    )
    if str(packet_field(run_packet, "step") or "").strip() != "run":
        raise SystemExit("Promotion run report must declare step=run.")
    _require_packet_not_blocked(run_packet, "Promotion run report")
    _require_packet_task(run_packet, validated_task_id, "Promotion run report")
    _require_empty_packet_blockers(run_packet, "Promotion run report")
    execution_status = str(packet_field(run_packet, "execution_status") or "").strip().lower()
    if execution_status not in PROMOTION_TERMINAL_EXECUTION_STATUSES:
        raise SystemExit("Promotion requires a terminal run report with no pending execution.")
    if packet_field(run_packet, "long_run_branch") is True:
        long_run_role = str(packet_field(run_packet, "long_run_role") or "").strip().lower()
        if long_run_role not in {"harvest", "finalize"}:
            raise SystemExit("Promotion cannot advance while a long-running execution remains at launch or monitor state.")
    run_evidence = verify_evidence_files(root, packet_field(run_packet, "evidence_paths"), "Run report evidence_paths")

    validation_path, validation_packet, validation_digest = load_bound_packet(
        root,
        plan.get("validation_report_path"),
        plan.get("validation_report_sha256"),
        "Promotion validation report",
    )
    if str(packet_field(validation_packet, "step") or "").strip() != "validate":
        raise SystemExit("Promotion validation report must declare step=validate.")
    _require_packet_not_blocked(validation_packet, "Promotion validation report")
    _require_packet_task(validation_packet, validated_task_id, "Promotion validation report")
    packet_verdict = str(packet_field(validation_packet, "validation_verdict") or "").strip().lower()
    if packet_verdict not in PROMOTION_VALIDATION_VERDICTS:
        raise SystemExit("Promotion validation report must carry a complete/pass verdict.")
    if declared_validation_verdict not in PROMOTION_VALIDATION_VERDICTS:
        raise SystemExit("Promotion validation_verdict must be complete, pass, or passed.")
    _require_empty_packet_blockers(validation_packet, "Promotion validation report")
    validation_packet_evidence = verify_evidence_files(
        root,
        packet_field(validation_packet, "evidence_paths"),
        "Validation report evidence_paths",
    )
    declared_validation_evidence = verify_evidence_files(
        root,
        plan.get("validation_evidence_paths"),
        "Promotion validation_evidence_paths",
    )
    validation_report_relative = rel_path(root, validation_path)
    if validation_report_relative not in declared_validation_evidence:
        raise SystemExit("Promotion validation_evidence_paths must include validation_report_path.")

    issue_path, issue_packet, issue_digest = load_bound_packet(
        root,
        plan.get("issue_packet_path"),
        plan.get("issue_packet_sha256"),
        "Promotion issue packet",
    )
    if str(packet_field(issue_packet, "step") or "").strip() != "issue":
        raise SystemExit("Promotion issue packet must declare step=issue.")
    _require_packet_not_blocked(issue_packet, "Promotion issue packet")
    _require_packet_task(issue_packet, validated_task_id, "Promotion issue packet")
    _require_empty_packet_blockers(issue_packet, "Promotion issue packet")
    issue_status = str(packet_field(issue_packet, "issue_status") or "").strip().lower()
    if issue_status not in ISSUE_NOOP_STATUSES | ISSUE_MUTATION_STATUSES:
        raise SystemExit("Promotion issue packet must record a completed issue reconciliation or an explicit no-op.")
    issue_provenance = packet_field(issue_packet, "issue_provenance")
    if not isinstance(issue_provenance, dict) or str(issue_provenance.get("source_task_id") or "").strip() != validated_task_id:
        raise SystemExit("Promotion issue packet provenance must identify the validated task.")
    provenance_report_value = str(issue_provenance.get("validation_report_path") or "").strip()
    provenance_report = bounded_workspace_file(root, provenance_report_value, "Issue validation_report_path")
    if provenance_report != validation_path:
        raise SystemExit("Promotion issue packet provenance must cite the exact bound validation report.")
    if issue_status in ISSUE_NOOP_STATUSES:
        if not non_empty(packet_field(issue_packet, "issue_skipped_reason")):
            raise SystemExit("Promotion issue no-op requires issue_skipped_reason.")
    elif not _issue_identifier_present(issue_packet):
        raise SystemExit("Promotion issue reconciliation must identify the durable issue record it handled.")
    issue_evidence = verify_evidence_files(root, packet_field(issue_packet, "evidence_paths"), "Issue packet evidence_paths")

    return {
        "execution_status": execution_status,
        "run_report_path": rel_path(root, run_path),
        "run_report_sha256": run_digest,
        "run_evidence_paths": run_evidence,
        "validation_report_path": validation_report_relative,
        "validation_report_sha256": validation_digest,
        "validation_packet_evidence_paths": validation_packet_evidence,
        "validation_evidence_paths": declared_validation_evidence,
        "issue_packet_path": rel_path(root, issue_path),
        "issue_packet_sha256": issue_digest,
        "issue_status": issue_status,
        "issue_evidence_paths": issue_evidence,
    }


def validate_initial_selection_provenance(
    root: Path,
    path: Path,
    data: dict[str, Any],
    plan: dict[str, Any],
    *,
    item_id: str,
    task_id: str,
    task_digest: str,
    promotion_origin: str,
) -> dict[str, Any]:
    """Validate first-item bootstrap/authority provenance in the promotion transaction."""

    if promotion_origin not in {"bootstrap_initial_selection", "authorized_initial_selection"}:
        raise SystemExit("Initial selection requires a bootstrap or authorized promotion origin.")
    ordered = sorted_items(data)
    if not ordered or str(ordered[0].get("item_id") or "") != item_id or ordered[0].get("order") != 1:
        raise SystemExit("Initial selection origin is valid only for the first canonical pack item.")
    if any(
        isinstance(item, dict) and item.get("status") in {"promoted", "in_progress", "consumed"}
        for item in data.get("items", [])
    ):
        raise SystemExit("Initial selection origin cannot be reused after any pack item was promoted or consumed.")
    prior_actions = {
        str(item.get("action") or "")
        for item in data.get("mutation_log", [])
        if isinstance(item, dict) and item.get("action")
    }
    if prior_actions - {"create"}:
        raise SystemExit("Initial selection must bind to the unmodified pack-creation snapshot.")

    receipt = plan.get("initial_selection_receipt")
    if not isinstance(receipt, dict):
        raise SystemExit("Initial selection requires `initial_selection_receipt` in the promotion transaction.")
    if str(receipt.get("initial_item_id") or "") != item_id:
        raise SystemExit("Initial selection receipt item identity differs from the selected first item.")
    verified = validate_initial_selection_receipt(
        root,
        path,
        data,
        receipt,
        task_id=task_id,
        task_digest=task_digest,
        operation="promote",
        require_mutation_binding=False,
    )
    receipt_digest = sha256_bytes(
        json.dumps(verified, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    return {
        "promotion_origin": promotion_origin,
        "initial_selection_receipt": verified,
        "initial_selection_receipt_ref": f"inline:sha256:{receipt_digest}",
        "predecessor_completion_receipt_ref": None,
    }


def consume_in_flight_for_atomic_promotion(
    root: Path,
    data: dict[str, Any],
    completion_plan: dict[str, Any],
    *,
    require_current_verdicts: bool,
) -> str:
    """Consume exactly one promoted item in memory before promoting its successor."""

    in_flight = active_in_flight_items(data)
    if len(in_flight) != 1:
        raise SystemExit("Atomic consume-and-promote requires exactly one in-flight pack item.")
    item = in_flight[0]
    promotion = item.get("promotion")
    if not isinstance(promotion, dict):
        raise SystemExit("Atomic consume-and-promote requires preserved promotion provenance.")
    completed_task_id = str(promotion.get("task_id") or "").strip()
    declared_task_id = str(completion_plan.get("task_id") or completion_plan.get("validated_task_id") or "").strip()
    if not completed_task_id or declared_task_id != completed_task_id:
        raise SystemExit("Atomic completion task identity must match the in-flight promotion.")
    validation_verdict = str(completion_plan.get("validation_verdict") or "").strip().lower()
    completion_provenance = validate_promotion_provenance(
        root,
        completion_plan,
        completed_task_id,
        validation_verdict,
    )
    item["completion"] = {
        "completed_task_id": completed_task_id,
        "completed_at": now_iso(),
        "validation_verdict": validation_verdict,
        "completion_evidence_paths": verify_evidence_files(
            root,
            completion_plan.get("evidence_paths"),
            "Atomic completion evidence_paths",
        ),
        **completion_provenance,
    }
    item["status"] = "consumed"
    result = item.setdefault("result", {})
    result["validation_verdict"] = validation_verdict
    for field in (
        "progress_verdict",
        "progress_kind",
        "semantic_signature",
        "blocker_signature",
    ):
        if completion_plan.get(field) is not None:
            result[field] = completion_plan.get(field)
    preserve_verdict_axes(result, completion_plan, require_current=require_current_verdicts)
    data.setdefault("mutation_log", []).append(
        {
            "timestamp": now_iso(),
            "action": "mark_consumed",
            "reason": completion_plan.get("reason") or "atomic predecessor completion",
            "item_id": item.get("item_id"),
            "actor": "$derive-improvement-task",
            "atomic_with_next_promotion": True,
        }
    )
    refresh_current_item(data)
    return completed_task_id

