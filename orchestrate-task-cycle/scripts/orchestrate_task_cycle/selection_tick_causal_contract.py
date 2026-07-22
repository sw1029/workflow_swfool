"""Causal wake and publication invariants for a structurally valid selection tick."""

from __future__ import annotations

from typing import Any

from .selection_tick_policy import selection_disposition
from .selection_tick_premise import VERIFIED_PREMISE_CONTRACT
from .selection_tick_publication_contract import validate_selection_publication


def validate_tick_causality(
    packet: dict[str, Any],
    *,
    watches: list[dict[str, Any]],
    changes: list[dict[str, str]],
    material: list[dict[str, str]],
    previous_manifest: str | None,
    observed_manifest: str,
    pending_publications: list[str],
    premise_contract: str,
) -> None:
    """Recompute exact-premise freshness and the canonical disposition."""

    has_exact_row = any(row.get("kind") == "exact_premise" for row in watches)
    exact_delta = any(
        row["evidence_class"] == "exact_subject"
        and row["change_kind"] in {"added", "content_changed"}
        for row in changes
    )
    exact_supplied = packet["exact_premise_supplied"]
    expected_fresh = bool(exact_supplied and (previous_manifest is None or exact_delta))
    if (
        packet["fresh_exact_premise_detected"] is not expected_fresh
        or (exact_supplied and not has_exact_row)
        or (exact_delta and not exact_supplied)
    ):
        raise ValueError("selection tick fresh exact-premise state is inconsistent")
    if premise_contract != VERIFIED_PREMISE_CONTRACT and (
        exact_supplied or exact_delta
    ):
        raise ValueError("raw exact-premise evidence cannot open selection re-entry")

    publication_status = validate_selection_publication(
        packet["selection_publication_status"], pending_publications
    )
    status = packet["status"]
    blocker_status = (
        publication_status
        if publication_status in {"recovery_required", "drift_blocked"}
        else None
    )
    if (blocker_status is not None and status != blocker_status) or (
        blocker_status is None and status in {"recovery_required", "drift_blocked"}
    ):
        raise ValueError("selection tick status disagrees with publication blocker")

    expected_status, expected_reason, expected_required = selection_disposition(
        publication_blocked=publication_status != "clear",
        pending_publications=pending_publications,
        previous_sha=previous_manifest or "",
        manifest_sha256=observed_manifest,
        fresh_exact_premise_detected=expected_fresh,
        material_entries=material,
    )
    if (
        packet["selection_acknowledgement_status"] != "not_requested"
        and publication_status == "clear"
    ):
        if expected_fresh or material:
            expected_status = "selection_required"
            expected_reason = "selection_inputs_changed_during_acknowledgement"
            expected_required = True
        else:
            expected_status = "baseline_recorded"
            expected_reason = "selection_required_tick_acknowledged_and_rebased"
            expected_required = False
    if (status, packet["reason"], packet["selection_required"]) != (
        expected_status,
        expected_reason,
        expected_required,
    ):
        raise ValueError("selection tick disposition is not causally derived")


__all__ = ("validate_tick_causality",)
