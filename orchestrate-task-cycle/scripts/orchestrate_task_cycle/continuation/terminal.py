"""Fail-closed run intake used to continue only through closure stages."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .contracts import ContinuationContractError, binding, digest, opaque


TERMINAL_INTAKE_CONTRACT_ID = "run_terminal_intake@v1"
OWNER_INTAKE_CONTRACT_ID = "run_terminal_owner_intake@v1"


def _bindings(value: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ContinuationContractError(f"{label} must be a list")
    normalized = [
        binding(item, f"{label}[{index}]")
        for index, item in enumerate(value)
    ]
    identities = [(item["ref"], item["sha256"]) for item in normalized if item]
    if len(identities) != len(set(identities)):
        raise ContinuationContractError(f"{label} contains duplicate bindings")
    return [item for item in normalized if item is not None]


def build_run_terminal_intake(
    *,
    cycle_id: str,
    task_id: str,
    run_id: str,
    disposition: str,
    failure_reason: str | None,
    safe_surviving_artifacts: list[dict[str, str]],
    discarded_artifacts: list[dict[str, str]],
    autopsy_binding: dict[str, str] | None,
) -> dict[str, Any]:
    if disposition not in {"succeeded", "failed_closed"}:
        raise ContinuationContractError(
            "terminal intake disposition must be succeeded or failed_closed"
        )
    if disposition == "failed_closed" and failure_reason is None:
        raise ContinuationContractError("failed_closed intake requires a reason")
    surviving = _bindings(safe_surviving_artifacts, "safe_surviving_artifacts")
    discarded = _bindings(discarded_artifacts, "discarded_artifacts")
    if {
        (item["ref"], item["sha256"]) for item in surviving
    }.intersection((item["ref"], item["sha256"]) for item in discarded):
        raise ContinuationContractError(
            "surviving and discarded run artifacts must be disjoint"
        )
    intake: dict[str, Any] = {
        "contract_id": TERMINAL_INTAKE_CONTRACT_ID,
        "cycle_id": opaque(cycle_id, "cycle_id"),
        "task_id": opaque(task_id, "task_id"),
        "run_id": opaque(run_id, "run_id"),
        "disposition": disposition,
        "failure_reason": (
            opaque(failure_reason, "failure_reason", nullable=True)
        ),
        "safe_surviving_artifacts": surviving,
        "discarded_artifacts": discarded,
        "autopsy_binding": binding(
            autopsy_binding, "autopsy_binding", nullable=True
        ),
        "closure_only": disposition == "failed_closed",
        "automatic_retry": False,
        "next_stage": "qualitative_review",
    }
    intake["intake_id"] = f"run-intake-{digest(intake)[:32]}"
    return intake


def _verified_terminal(
    root: str | Path, cycle_id: str
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Reopen the one producer-owned terminal event for this cycle."""

    from ..cycle_ledger import read_events
    from ..stage.closure import reopen_run_terminal_event

    events = [
        event
        for event in read_events(Path(root).resolve(strict=True), cycle_id)
        if event.get("step") == "run"
        and event.get("observation_kind") == "run_terminal"
    ]
    if not events:
        return None
    if len(events) != 1:
        raise ContinuationContractError(
            "cycle contains ambiguous terminal run observations"
        )
    try:
        projection = reopen_run_terminal_event(root, cycle_id, events[0])
    except (OSError, TypeError, ValueError) as exc:
        raise ContinuationContractError(
            "terminal run evidence cannot be reopened"
        ) from exc
    return events[0], projection


def run_terminal_owner_intake(
    root: str | Path, cycle_id: str
) -> dict[str, Any] | None:
    """Expose verified closure evidence without exposing discarded bindings."""

    reopened = _verified_terminal(root, cycle_id)
    if reopened is None:
        return None
    event, projection = reopened
    task_id = event.get("task_id")
    if task_id is None:
        from ..ledger.support import read_initialization_metadata

        task_id = read_initialization_metadata(
            Path(root).resolve(strict=True), cycle_id
        ).get("task_id")
    failure = projection.get("failure")
    full = build_run_terminal_intake(
        cycle_id=cycle_id,
        task_id=str(task_id or ""),
        run_id=projection["run_id"],
        disposition=projection["status"],
        failure_reason=(
            failure.get("reason") if isinstance(failure, dict) else None
        ),
        safe_surviving_artifacts=[
            row["binding"] for row in projection["safe_surviving_artifacts"]
        ],
        discarded_artifacts=[
            row["binding"] for row in projection["discarded_artifacts"]
        ],
        autopsy_binding=(
            failure.get("evidence_binding")
            if isinstance(failure, dict)
            else None
        ),
    )
    owner = {
        "contract_id": OWNER_INTAKE_CONTRACT_ID,
        "intake_id": full["intake_id"],
        "cycle_id": full["cycle_id"],
        "task_id": full["task_id"],
        "run_id": full["run_id"],
        "disposition": full["disposition"],
        "failure_reason": full["failure_reason"],
        "safe_surviving_artifacts": full["safe_surviving_artifacts"],
        "autopsy_binding": full["autopsy_binding"],
        "discarded_artifact_count": len(full["discarded_artifacts"]),
        "closure_only": full["closure_only"],
        "automatic_retry": full["automatic_retry"],
        "next_stage": full["next_stage"],
    }
    owner["owner_intake_id"] = f"run-owner-intake-{digest(owner)[:32]}"
    return owner


def _claimed_refs(value: Any) -> set[str]:
    refs: set[str] = set()

    def visit(item: Any, field: str | None = None) -> None:
        if isinstance(item, dict):
            ref = item.get("ref")
            if isinstance(ref, str) and isinstance(item.get("sha256"), str):
                refs.add(ref)
            for key, nested in item.items():
                visit(nested, str(key))
        elif isinstance(item, list):
            for nested in item:
                visit(nested, field)
        elif isinstance(item, str) and field in {
            "artifact_refs",
            "artifacts",
            "evidence_paths",
            "path",
            "ref",
            "source_ref",
        }:
            refs.add(item)

    visit(value)
    return refs


def reject_discarded_terminal_inputs(
    root: str | Path, cycle_id: str, value: Any
) -> None:
    """Reject owner claims that consume a producer-discarded run artifact."""

    reopened = _verified_terminal(root, cycle_id)
    if reopened is None:
        return
    _event, projection = reopened
    discarded = {
        row["binding"]["ref"] for row in projection["discarded_artifacts"]
    }
    if discarded.intersection(_claimed_refs(value)):
        raise ContinuationContractError(
            "closure owner input references a discarded run artifact"
        )


__all__ = (
    "OWNER_INTAKE_CONTRACT_ID",
    "TERMINAL_INTAKE_CONTRACT_ID",
    "build_run_terminal_intake",
    "reject_discarded_terminal_inputs",
    "run_terminal_owner_intake",
)
