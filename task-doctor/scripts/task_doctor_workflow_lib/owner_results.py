"""Closed result adapters for mutating owner operations supported by task-doctor."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable

from .common import WorkflowError, require
from .task_transition_transaction import verify_task_transition_receipt


SKILLS_ROOT = Path(__file__).resolve().parents[3]


def _public(label: str, action: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        result = action()
    except (SystemExit, KeyError, TypeError, ValueError) as error:
        message = str(error) or error.__class__.__name__
        raise WorkflowError(
            "invalid_owner_result", f"{label} verification failed: {message}"
        ) from error
    require(isinstance(result, dict), "invalid_owner_result",
            f"{label} verifier returned no typed result")
    return result


def _verify_apply_receipt(
    item: dict[str, Any], owner_artifact: dict[str, str],
    effect_status: str, verification: dict[str, Any], label: str,
) -> None:
    require(
        verification.get("plan_ref") == item["plan_binding"]["ref"]
        and verification.get("plan_file_sha256") == item["plan_binding"]["sha256"]
        and verification.get("plan_sha256") == item["plan"].get("plan_sha256"),
        "invalid_owner_result", f"{label} verifier binds a different owner plan",
    )
    if effect_status == "confirmed_effect":
        require(verification.get("status") == "already_applied",
                "invalid_owner_result",
                f"{label} confirmed effect is not present in the live projection")
        expected = {
            "ref": verification.get("receipt_ref"),
            "sha256": verification.get("receipt_file_sha256"),
        }
        require(owner_artifact == expected, "invalid_owner_result",
                f"{label} owner artifact must be its exact public apply receipt")
        return
    require(effect_status == "confirmed_no_effect", "invalid_owner_result",
            f"{label} owner effect status is unsupported")
    require(verification.get("status") == "settled_no_effect"
            and verification.get("no_effect_verified") is True,
            "invalid_owner_result",
            f"{label} no-effect result lacks a durable plan-bound receipt")
    expected = {
        "ref": verification.get(
            "no_effect_receipt_ref", verification.get("receipt_ref")
        ),
        "sha256": verification.get(
            "no_effect_receipt_file_sha256",
            verification.get("receipt_file_sha256"),
        ),
    }
    require(owner_artifact == expected, "invalid_owner_result",
            f"{label} owner artifact must be its exact no-effect receipt")


def _verify_advice(
    root: Path, item: dict[str, Any], owner_artifact: dict[str, str],
    effect_status: str,
) -> None:
    scripts = SKILLS_ROOT / "manage-external-advice" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from manage_external_advice.intake_plan import verify_intake_plan

    verification = _public(
        "external advice intake",
        lambda: verify_intake_plan(root, item["plan_binding"]["ref"]),
    )
    _verify_apply_receipt(
        item, owner_artifact, effect_status, verification, "external advice intake"
    )


def _verify_index(
    root: Path, item: dict[str, Any], owner_artifact: dict[str, str],
    effect_status: str,
) -> None:
    scripts = SKILLS_ROOT / "manage-task-state-index" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from manage_task_state_index.state.transition_plan import verify_transition_plan

    verification = _public(
        "task state index transition",
        lambda: verify_transition_plan(
            root, item["plan_binding"]["ref"], phase="apply"
        ),
    )
    _verify_apply_receipt(
        item, owner_artifact, effect_status, verification,
        "task state index transition",
    )


def verify_owner_result(
    root: Path, item: dict[str, Any], owner_artifact: dict[str, str],
    effect_status: str,
) -> None:
    """Dispatch one supported owner result to its public read-only verifier."""

    role = item["workflow_role"]
    if role == "task_scope_transition":
        verify_task_transition_receipt(
            root, item["plan_binding"]["ref"], owner_artifact, effect_status
        )
    elif role == "external_advice_intake":
        _verify_advice(root, item, owner_artifact, effect_status)
    elif role == "task_index_transition":
        _verify_index(root, item, owner_artifact, effect_status)
    else:
        raise WorkflowError(
            "invalid_owner_result",
            f"{item['owner_skill']} {role} has no registered closed result validator",
        )


__all__ = ["verify_owner_result"]
