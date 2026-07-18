"""Render one deterministic selection-tick disposition packet."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .selection_tick_baseline import PreviousSelectionTick
from .selection_tick_contract import validate_selection_tick_v2
from .selection_tick_policy import selection_disposition


def _canonical(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def render_selection_tick_packet(
    *,
    previous: dict[str, Any] | None,
    previous_tick: PreviousSelectionTick | None,
    previous_sha: str,
    rows: list[dict[str, Any]],
    manifest_sha256: str,
    changed_entries: list[dict[str, Any]],
    active_predicates: list[str],
    active_classes: list[str],
    active_minimum: str,
    exact_premise_supplied: bool,
    fresh_exact_premise_detected: bool,
    carried_watch_ids: list[str],
    publication: dict[str, Any],
    acknowledge_selection_tick_id: str | None,
    premise_contract: str,
) -> dict[str, Any]:
    """Apply wake, acknowledgement, and publication gates then seal the packet."""

    changed_classes = sorted({str(row["evidence_class"]) for row in changed_entries})
    material_entries = [
        row for row in changed_entries if row["evidence_class"] in set(active_classes)
    ]
    pending_publications = publication["pending_transaction_ids"]
    publication_blocked = publication["status"] != "clear"
    status, reason, selection_required = selection_disposition(
        publication_blocked=publication_blocked,
        pending_publications=pending_publications,
        previous_sha=previous_sha,
        manifest_sha256=manifest_sha256,
        fresh_exact_premise_detected=fresh_exact_premise_detected,
        material_entries=material_entries,
    )
    acknowledging = bool(previous_tick and previous_tick.acknowledging_selection)
    baseline_rebased = False
    if acknowledging and not publication_blocked:
        if changed_entries:
            status = "selection_required"
            reason = "selection_inputs_changed_during_acknowledgement"
            selection_required = True
        else:
            status = "baseline_recorded"
            reason = "selection_required_tick_acknowledged_and_rebased"
            selection_required = False
            baseline_rebased = True
    acknowledgement_status = (
        "accepted"
        if baseline_rebased
        else "blocked_publication"
        if acknowledging and publication_blocked
        else "rejected_input_drift"
        if acknowledging
        else "not_requested"
    )
    acknowledgement_binding = (
        previous_tick.selection_acknowledgement_binding
        if acknowledging and previous is not None and previous_tick is not None
        else None
    )
    packet: dict[str, Any] = {
        "format_version": 2,
        "artifact_kind": "selection_tick",
        "status": status,
        "reason": reason,
        "observed_input_manifest_sha256": manifest_sha256,
        "previous_input_manifest_sha256": previous_sha or None,
        "watch_entries": rows,
        "changed_watch_entries": changed_entries,
        "changed_evidence_classes": changed_classes,
        "material_changed_watch_entries": material_entries,
        "wake_predicates": active_predicates,
        "wake_evaluation_rule": "explicit-premise-or-bound-class-change-v1",
        "wake_predicate_ids_are_policy_labels": True,
        "watched_evidence_classes": active_classes,
        "minimum_material_delta": active_minimum,
        "premise_input_contract": premise_contract,
        "satisfied_wake_predicates": active_predicates if selection_required else [],
        "exact_premise_supplied": exact_premise_supplied,
        "fresh_exact_premise_detected": fresh_exact_premise_detected,
        "carried_forward_watch_ids": carried_watch_ids,
        "acknowledgement_requested_for_packet_id": (
            acknowledge_selection_tick_id if acknowledging else None
        ),
        "selection_acknowledgement_binding": acknowledgement_binding,
        "selection_acknowledgement_status": acknowledgement_status,
        "acknowledged_selection_tick_id": (
            str(previous["packet_id"])
            if baseline_rebased and previous is not None
            else None
        ),
        "baseline_rebased": baseline_rebased,
        "authority_scope_ids": sorted(
            str(row["authority_scope_id"])
            for row in rows
            if row.get("kind") == "effective_authority"
        ),
        "selection_required": selection_required,
        "agent_fanout_allowed": selection_required,
        "full_cycle_allowed": False,
        "next_action": (
            "recover_selection_publication"
            if pending_publications
            else "repair_selection_publication_drift"
            if publication_blocked
            else "run_derive_selection"
            if selection_required
            else "preserve_terminal_wait"
        ),
        "pending_selection_publication_ids": pending_publications,
        "selection_publication_status": publication,
        "not_goal_truth": True,
        "not_authority": True,
        "mutation_performed": False,
    }
    packet["packet_id"] = (
        "selection-tick-" + hashlib.sha256(_canonical(packet)).hexdigest()[:32]
    )
    return validate_selection_tick_v2(packet)


__all__ = ("render_selection_tick_packet",)
