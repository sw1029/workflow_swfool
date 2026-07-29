"""Proof-bound, idempotent initialization of a selected successor cycle."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import Any

from ..cycle_ledger import init_cycle
from ..ledger.constants import (
    COMPILER_FIRST_WORKFLOW_CONTRACT_PROFILE,
    STAGE_COMPILER_PROTOCOL_VERSION,
    STAGE_PREPARATION_SCHEMA_VERSION,
)
from ..ledger.support import ledger_lock, read_initialization_metadata
from ..selection_publication_store import _canonical_json
from .successor_adapter import (
    _selected_result,
    _settled_successor_proof,
    _successor_cycles,
)


_CYCLE_PREFIX = "cycle-successor-"
_REASON_PREFIX = "proof-bound selected successor "


def _identity(
    source_cycle_id: str, proof: dict[str, Any]
) -> tuple[str, str]:
    lease = proof["lease"]
    core = {
        "schema_version": 1,
        "source_cycle_id": source_cycle_id,
        "task_id": proof["task_id"],
        "goal_id": lease["goal_id"],
        "task_family": lease["task_family"],
        "session_lease_sha256": proof["lease_sha256"],
        "selection": proof["selection"],
        "bundle": proof["bundle"],
        "execution_leases": list(proof["execution_leases"]),
        "use_receipts": list(proof["use_receipts"]),
        "settlement_barrier": proof["barrier"].isoformat(),
    }
    digest = hashlib.sha256(_canonical_json(core)).hexdigest()
    return f"{_CYCLE_PREFIX}{digest[:32]}", f"{_REASON_PREFIX}{digest}"


def _is_exact_automatic_cycle(
    root: Path,
    cycle_id: str,
    *,
    task_id: str,
    reason: str,
) -> bool:
    metadata = read_initialization_metadata(root, cycle_id)
    return (
        metadata.get("task_id") == task_id
        and metadata.get("reason") == reason
        and metadata.get("stage_compiler_protocol_version")
        == STAGE_COMPILER_PROTOCOL_VERSION
        and metadata.get("stage_preparation_schema_version")
        == STAGE_PREPARATION_SCHEMA_VERSION
        and metadata.get("workflow_contract_profile")
        == COMPILER_FIRST_WORKFLOW_CONTRACT_PROFILE
    )


def _reuse_existing(
    root: Path,
    proof: dict[str, Any],
    successors: list[tuple[datetime, str]],
    *,
    expected_cycle_id: str,
    expected_reason: str,
) -> dict[str, Any] | None:
    if len(successors) != 1:
        return None
    _initialized_at, cycle_id = successors[0]
    metadata = read_initialization_metadata(root, cycle_id)
    if cycle_id == expected_cycle_id:
        if not _is_exact_automatic_cycle(
            root,
            cycle_id,
            task_id=proof["task_id"],
            reason=expected_reason,
        ):
            return None
    elif str(metadata.get("reason") or "").startswith(_REASON_PREFIX):
        # Never reinterpret an automatic cycle bound to a different proof as
        # a compatible manually initialized successor.
        return None
    return _selected_result(proof, cycle_id)


def _resolve(
    root: Path,
    source_cycle_id: str,
    *,
    session_id: str,
    goal_id: str | None,
    task_family: str | None,
    skills_root: Path | None,
) -> dict[str, Any]:
    return _settled_successor_proof(
        root,
        source_cycle_id,
        session_id=session_id,
        goal_id=goal_id,
        task_family=task_family,
        skills_root=skills_root,
    )


def ensure_selected_successor_cycle(
    root: Path,
    source_cycle_id: str,
    *,
    session_id: str | None = None,
    goal_id: str | None = None,
    task_family: str | None = None,
    skills_root: Path | None = None,
) -> dict[str, Any] | None:
    """Return or initialize one successor after two exact proof replays."""

    if not session_id:
        return None
    try:
        workspace = root.expanduser().resolve(strict=True)
        read_initialization_metadata(workspace, source_cycle_id)
        with ledger_lock(workspace, source_cycle_id, exclusive=True):
            proof = _resolve(
                workspace,
                source_cycle_id,
                session_id=session_id,
                goal_id=goal_id,
                task_family=task_family,
                skills_root=skills_root,
            )
            cycle_id, reason = _identity(source_cycle_id, proof)
            successors = _successor_cycles(
                workspace,
                source_cycle_id,
                proof["task_id"],
                after=proof["barrier"],
            )
            replayed = _resolve(
                workspace,
                source_cycle_id,
                session_id=session_id,
                goal_id=goal_id,
                task_family=task_family,
                skills_root=skills_root,
            )
            replayed_successors = _successor_cycles(
                workspace,
                source_cycle_id,
                proof["task_id"],
                after=proof["barrier"],
            )
            if replayed != proof or replayed_successors != successors:
                return None
            if successors:
                return _reuse_existing(
                    workspace,
                    proof,
                    successors,
                    expected_cycle_id=cycle_id,
                    expected_reason=reason,
                )
            if datetime.now(timezone.utc) <= proof["barrier"]:
                return None
            init_cycle(
                workspace,
                cycle_id,
                proof["task_id"],
                reason,
                stage_compiler_protocol_version=(
                    STAGE_COMPILER_PROTOCOL_VERSION
                ),
                stage_preparation_schema_version=(
                    STAGE_PREPARATION_SCHEMA_VERSION
                ),
                workflow_contract_profile=(
                    COMPILER_FIRST_WORKFLOW_CONTRACT_PROFILE
                ),
            )
            final_proof = _resolve(
                workspace,
                source_cycle_id,
                session_id=session_id,
                goal_id=goal_id,
                task_family=task_family,
                skills_root=skills_root,
            )
            final_successors = _successor_cycles(
                workspace,
                source_cycle_id,
                proof["task_id"],
                after=proof["barrier"],
            )
            if final_proof != proof:
                return None
            return _reuse_existing(
                workspace,
                proof,
                final_successors,
                expected_cycle_id=cycle_id,
                expected_reason=reason,
            )
    except (OSError, ValueError, SystemExit):
        return None


__all__ = ("ensure_selected_successor_cycle",)
