from __future__ import annotations

from pathlib import Path
from typing import Any

from .canonical import parse_time, utc_now
from .workflow_interaction import interaction_projection
from .workflow_inventory import load_status_inventory
from .workflow_selection import select_workflow
from .workflow_waits import classify_authority_candidates


def _summary(
    inventory: dict[str, Any],
    candidates: dict[str, Any],
    selected: dict[str, Any],
) -> dict[str, int]:
    exhausted = [
        *candidates["source_exhausted_waits"],
        *candidates["recovery_replans"],
    ]
    return {
        "grant_count": len(inventory["grants"]),
        "reservation_count": len(inventory["reservations"]),
        "resumable_count": len(selected["resumable"]),
        "blocked_reservation_count": len(selected["blocked_reserved"]),
        "released_count": len(selected["released"]),
        "quarantine_count": len(selected["quarantines"]),
        "current_allowed_count": len(candidates["current_allowed"]),
        "source_ready_wait_count": len(candidates["source_ready_waits"]),
        "source_defect_wait_count": len(candidates["source_defect_waits"]),
        "source_exhausted_wait_count": len(exhausted),
        "source_refresh_wait_count": len(exhausted),
        "recovery_wait_count": len(candidates["recovery_waits"]),
        "recovery_replan_count": len(candidates["recovery_replans"]),
        "pending_wait_count": len(candidates["recovery_waits"])
        + len(candidates["waits"]),
        "historical_wait_count": len(candidates["historical_waits"]),
    }


def _response(
    inventory: dict[str, Any],
    candidates: dict[str, Any],
    selected: dict[str, Any],
    *,
    evaluated_at: str,
    request_sha256: str | None,
) -> dict[str, Any]:
    state = selected["workflow_state"]
    interaction = interaction_projection(
        state, selected["should_prompt"], selected["next_action"]
    )
    exhausted = [
        *candidates["source_exhausted_waits"],
        *candidates["recovery_replans"],
    ]
    return {
        "schema_version": 2,
        "status": "ok",
        "evaluated_at": evaluated_at,
        "request_sha256_filter": request_sha256,
        **interaction,
        "approval_projection": selected.get("approval_projection"),
        "post_approval_handoff": selected.get("post_approval_handoff"),
        "wait_identity": selected.get("wait_identity"),
        "recovery_identity": selected["recovery_identity"],
        "workflow_basis": selected["basis"],
        "grants": inventory["grants"],
        "reservations": inventory["reservations"],
        "quarantines": selected["quarantines"],
        "resumable_reservations": selected["resumable"],
        "blocked_reservations": selected["blocked_reserved"],
        "released_reservations": selected["released"],
        "current_allowed_decisions": candidates["current_allowed"],
        "stale_allowed_decisions": candidates["stale_allowed"],
        "source_ready_waits": candidates["source_ready_waits"],
        "source_defect_waits": candidates["source_defect_waits"],
        "source_exhausted_waits": exhausted,
        "source_refresh_waits": exhausted,
        "recovery_waits": candidates["recovery_waits"],
        "recovery_replans": candidates["recovery_replans"],
        "covering_source_approvals": candidates["covering_sources"],
        "pending_waits": [*candidates["recovery_waits"], *candidates["waits"]],
        "historical_waits": candidates["historical_waits"],
        "verifications": inventory["verifications"],
        "execution_results": inventory["execution_results"],
        "use_receipts": inventory["use_receipts"],
        "release_receipts": inventory["release_receipts"],
        "reconciliation_receipts": inventory["reconciliation_receipts"],
        "summary": _summary(inventory, candidates, selected),
    }


def status_snapshot(
    root: Path,
    *,
    grant_id: str | None = None,
    request_sha256: str | None = None,
    evaluated_at: str | None = None,
    skills_root: Path | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    at = parse_time(evaluated_at or utc_now(), "status.at")
    inventory = load_status_inventory(
        root,
        grant_id=grant_id,
        request_sha256=request_sha256,
        at=at,
        skills_root=skills_root,
    )
    candidates = classify_authority_candidates(root, inventory, at, skills_root)
    selected = select_workflow(inventory, candidates)
    return _response(
        inventory,
        candidates,
        selected,
        evaluated_at=at.isoformat(),
        request_sha256=request_sha256,
    )


def resolve_operation(
    root: Path,
    request: dict[str, Any],
    context: dict[str, Any],
    *,
    evaluated_at: str,
    skills_root: Path | None,
) -> dict[str, Any]:
    from .workflow_resolver import resolve_operation as resolve

    return resolve(
        root,
        request,
        context,
        evaluated_at=evaluated_at,
        skills_root=skills_root,
    )


__all__ = ["resolve_operation", "status_snapshot"]
