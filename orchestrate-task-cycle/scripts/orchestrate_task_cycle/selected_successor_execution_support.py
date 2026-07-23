"""Shared checkpoint and authority-settlement helpers for selected successors."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

from .selection_decision_store import normalize_binding, read_bound_bytes


ACTIONS = (
    "apply_task_state_plan_pending",
    "publish_selected_successor_topology",
    "settle_selected_successor_task_state",
)


def checkpoint_state(root: Path, binding_value: Any, action: str) -> str:
    binding = normalize_binding(binding_value, f"{action} expected result")
    current = root
    for part in PurePosixPath(binding["ref"]).parts:
        current /= part
        if current.is_symlink():
            raise ValueError(
                f"Selected-successor {action} checkpoint traverses a symlink"
            )
    if not current.exists():
        return "missing"
    try:
        read_bound_bytes(root, binding, f"{action} checkpoint")
    except ValueError as exc:
        raise ValueError(
            f"Selected-successor {action} checkpoint conflicts with its expected binding"
        ) from exc
    return "exact"


def execution_rows(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    rows = bundle.get("execution_order")
    if (
        not isinstance(rows, list)
        or len(rows) != 3
        or [row.get("step") if isinstance(row, dict) else None for row in rows]
        != [1, 2, 3]
        or [row.get("action") if isinstance(row, dict) else None for row in rows]
        != list(ACTIONS)
    ):
        raise ValueError("Selected-successor bundle execution order is invalid")
    return rows


def checkpoint_states(
    root: Path, bundle: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[str]]:
    rows = execution_rows(bundle)
    return rows, [
        checkpoint_state(root, row["expected_result"], row["action"]) for row in rows
    ]


def validate_pristine_source(
    root: Path, bundle: dict[str, Any], states: list[str]
) -> None:
    """Reopen provenance only while all canonical effects are still absent."""

    if states != ["missing", "missing", "missing"]:
        return
    from .selected_successor_provenance import (
        validate_selected_source_for_prepared_successor,
    )

    validate_selected_source_for_prepared_successor(
        root,
        bundle["source_decision"],
        bundle["task_source"],
        bundle["selection_prepare"],
    )
    from .executable_closure_snapshot import (
        validate_selected_successor_predecessor_snapshot,
    )

    validate_selected_successor_predecessor_snapshot(root, bundle)


def settle_authority(
    root: Path,
    rows: list[dict[str, Any]],
    proofs: dict[str, dict[str, Any]],
    *,
    settled_at: str,
    skills_root: Path | None,
) -> list[dict[str, Any]]:
    from manage_agent_authority.settlement import settle_owner_result

    owner_results = (
        rows[2]["expected_result"],
        rows[1]["expected_result"],
        rows[2]["expected_result"],
    )
    settlements: list[dict[str, Any]] = []
    for row, owner_result in zip(rows, owner_results):
        action = row["action"]
        proof = proofs[action]
        result = settle_owner_result(
            root,
            proof["reservation"]["ref"],
            proof["reservation"]["sha256"],
            owner_result,
            proof["pre_commit_verification"],
            settled_at=settled_at,
            expected_version=proof["expected_version"],
            idempotency_key=row["idempotency_key"],
            skills_root=skills_root,
        )
        if (
            result.get("status") != "consumed"
            or result.get("outcome") != "confirmed_effect"
        ):
            raise ValueError(f"Selected-successor {action} authority did not consume")
        settlement = result.get("settlement")
        if not isinstance(settlement, dict):
            raise ValueError(
                f"Selected-successor {action} settlement receipt is missing"
            )
        settlements.append(
            {
                "action": action,
                "status": "consumed",
                "owner_result": owner_result,
                "owner_validation": result["owner_validation"],
                "use_receipt": {
                    "ref": settlement["ref"],
                    "sha256": settlement["sha256"],
                },
            }
        )
    return settlements


__all__ = (
    "ACTIONS",
    "checkpoint_states",
    "execution_rows",
    "settle_authority",
    "validate_pristine_source",
)
