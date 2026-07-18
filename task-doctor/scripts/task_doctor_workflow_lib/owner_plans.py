from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable

from .common import WorkflowError
from .task_transition_plan import (
    validate_task_transition_plan,
)
from .task_transition_transaction import verify_task_transition_execution


SKILLS_ROOT = Path(__file__).resolve().parents[3]


def _load_validator(owner_skill: str, workflow_role: str) -> Callable[[dict[str, Any]], None] | None:
    if owner_skill == "manage-external-advice" and workflow_role == "external_advice_intake":
        scripts = SKILLS_ROOT / "manage-external-advice" / "scripts"
        if str(scripts) not in sys.path:
            sys.path.insert(0, str(scripts))
        from manage_external_advice.intake_plan_contract import validate_intake_plan

        return validate_intake_plan
    if owner_skill == "manage-task-state-index" and workflow_role == "task_index_transition":
        scripts = SKILLS_ROOT / "manage-task-state-index" / "scripts"
        if str(scripts) not in sys.path:
            sys.path.insert(0, str(scripts))
        from manage_task_state_index.state.transition_plan_contract import (
            validate_transition_plan,
        )

        return validate_transition_plan
    return None


def validate_owner_plan(
    owner_skill: str, workflow_role: str, plan: dict[str, Any],
) -> None:
    if workflow_role == "task_pack_transition":
        raise WorkflowError(
            "invalid_owner_plan",
            "task_pack_transition has no registered closed public plan/result validator",
        )
    if workflow_role == "task_scope_transition":
        if owner_skill != "task-doctor" or plan.get("plan_kind") != "task_transition_plan":
            raise WorkflowError(
                "invalid_owner_plan",
                "task scope transitions require the registered task_transition_plan validator",
            )
        validate_task_transition_plan(plan)
        return
    validator = _load_validator(owner_skill, workflow_role)
    if validator is None:
        raise WorkflowError(
            "invalid_owner_plan",
            f"{owner_skill} {workflow_role} has no registered closed plan validator",
        )
    try:
        validator(plan)
    except (SystemExit, ValueError, KeyError, TypeError) as error:
        message = str(error) or error.__class__.__name__
        raise WorkflowError(
            "invalid_owner_plan",
            f"{owner_skill} {workflow_role} plan is invalid: {message}",
        ) from error


def verify_owner_plan(
    root: Path, owner_skill: str, workflow_role: str, plan: dict[str, Any],
    *, plan_ref: str | None = None, phase: str = "pre_dispatch",
    effect_status: str | None = None, dependencies: list[str] | None = None,
    dependencies_ready: bool = False,
) -> dict[str, Any]:
    validate_owner_plan(owner_skill, workflow_role, plan)
    if owner_skill == "task-doctor" and workflow_role == "task_scope_transition":
        if phase == "structural":
            return {"status": "structural"}
        if not isinstance(plan_ref, str) or not plan_ref:
            raise WorkflowError(
                "invalid_owner_plan", "task transition plan binding ref is unavailable"
            )
        verification_phase = "planning" if phase in {"planning", "pre_dispatch"} else "apply"
        if phase in {"planning", "pre_dispatch"}:
            result = verify_task_transition_execution(
                root, plan_ref, phase=verification_phase
            )
            if result.get("status") not in {
                "ready", "already_applied", "settled_no_effect",
                "recovery_required", "stale", "conflict",
            }:
                raise WorkflowError(
                    "invalid_owner_plan",
                    f"task transition returned an unknown state: {result.get('status')}",
                )
            return result
        if phase == "terminal" and effect_status is not None:
            result = verify_task_transition_execution(root, plan_ref, phase="apply")
            expected = (
                "already_applied" if effect_status == "confirmed_effect"
                else "settled_no_effect"
            )
            if result["status"] != expected:
                raise WorkflowError(
                    "stale_owner_result",
                    f"task transition terminal state is {result['status']}",
                )
            return result
        raise WorkflowError(
            "invalid_owner_plan",
            "task transition verification requires a known pre-dispatch or terminal phase",
        )
    if phase in {"structural", "terminal"}:
        return {"status": "structural"}
    if phase not in {"planning", "pre_dispatch"}:
        raise WorkflowError("invalid_owner_plan", "unsupported owner-plan phase")
    try:
        if not isinstance(plan_ref, str) or not plan_ref:
            raise ValueError("owner plan binding ref is unavailable")
        if owner_skill == "manage-external-advice" and workflow_role == (
            "external_advice_intake"
        ):
            from manage_external_advice.intake_plan import verify_intake_plan

            result = verify_intake_plan(root, plan_ref)
        elif owner_skill == "manage-task-state-index" and workflow_role == (
            "task_index_transition"
        ):
            from manage_task_state_index.state.transition_plan import verify_transition_plan

            result = verify_transition_plan(
                root, plan_ref,
                phase="apply" if dependencies_ready else "planning",
            )
        else:
            return {"status": "structural"}
    except (SystemExit, KeyError, TypeError, ValueError) as error:
        message = str(error) or error.__class__.__name__
        raise WorkflowError(
            "stale_owner_plan", f"owner pre-dispatch verification failed: {message}"
        ) from error
    if result.get("status") not in {
        "ready", "materializing", "already_applied", "settled_no_effect",
        "recovery_required", "stale", "conflict",
    }:
        raise WorkflowError(
            "invalid_owner_plan",
            f"owner plan returned an unknown lifecycle state: {result.get('status')}",
        )
    return result
