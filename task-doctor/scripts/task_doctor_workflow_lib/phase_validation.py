"""Phase-aware plan validation for nonterminal task-doctor operations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .authority import verify_operation_plan
from .common import read_json, workspace_file
from .journal import dependencies_complete


def validate_nonterminal_operations(
    root: Path, journal: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Validate immutable bindings and retain each public owner lifecycle result."""

    operations = {
        item["operation_id"]: item for item in journal["plan"]["operations"]
    }
    lifecycle: dict[str, dict[str, Any]] = {}
    for operation_id, state in journal["operation_state"].items():
        if state["status"] in {"complete", "skipped"}:
            continue
        item = operations[operation_id]
        dependencies_ready = dependencies_complete(journal, item)
        dependency_effect_in_flight = any(
            journal["operation_state"][dependency]["status"]
            not in {"pending", "blocked", "complete", "skipped"}
            for dependency in item["dependencies"]
        )
        phase = (
            "planning"
            if state["status"] == "pending" and not dependency_effect_in_flight
            else "structural"
        )
        lifecycle[operation_id] = verify_operation_plan(
            root, item, phase=phase, dependencies_ready=dependencies_ready,
        )
        evidence = state.get("result_evidence")
        if state.get("resolution") == "plan_changed" and isinstance(evidence, dict):
            path = workspace_file(
                root, evidence.get("ref", ""), evidence.get("sha256", ""),
                "plan-changed evidence",
            )
            if read_json(path, "invalid_owner_result").get("artifact_kind") == (
                "task_doctor_dependency_cancellation_receipt"
            ):
                from .dependency_cancellation import (
                    validate_dependency_cancellation,
                )

                validate_dependency_cancellation(
                    root, journal, operation_id, evidence,
                )
    return lifecycle


def project_nonterminal_status(
    root: Path, journal: dict[str, Any], *,
    allow_unbound_initial_approval: bool = False,
) -> dict[str, Any]:
    """Project workflow UX from public owner state and dependency-gated authority."""

    from .authority_overlay import live_authority_overlay
    from .projection import project_status

    lifecycle = validate_nonterminal_operations(root, journal)
    live = live_authority_overlay(
        root, journal, owner_lifecycle=lifecycle,
    )
    return project_status(
        journal, live, owner_lifecycle=lifecycle,
        allow_unbound_initial_approval=allow_unbound_initial_approval,
    )


__all__ = ["project_nonterminal_status", "validate_nonterminal_operations"]
