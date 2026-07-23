"""Authority-gated execution and recovery for one selected-successor bundle."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .selection_decision_store import normalize_binding
from .selection_publication import publish_prepared, validate_receipt
from .selected_successor_execution_lease import (
    authority_gate as _authority_gate,
    publish_execution_lease,
)
from .selected_successor_execution_authority import authority_preflight
from .selected_successor import load_selected_successor_bundle
from .selected_successor_execution_support import (
    ACTIONS,
    checkpoint_states,
    settle_authority,
    validate_pristine_source,
)
from .selected_successor_predecessor_snapshot import (
    validate_plan_owned_predecessor_snapshot,
)


def _execution_effect_hook(
    stage: str,
    root: Path,
    bundle: dict[str, Any],
    states: list[str],
) -> None:
    """Test seam for deterministic drift between selected-successor effects."""

    _ = stage, root, bundle, states


def _proofs(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict) or set(value) != set(ACTIONS):
        raise ValueError(
            "Selected-successor execution requires all three authority proofs"
        )
    result: dict[str, dict[str, Any]] = {}
    for action in ACTIONS:
        proof = value[action]
        if not isinstance(proof, dict) or set(proof) != {
            "reservation",
            "pre_commit_verification",
            "expected_version",
        }:
            raise ValueError(
                f"Selected-successor {action} authority proof is not closed"
            )
        version = proof["expected_version"]
        if type(version) is not int or version < 0:
            raise ValueError(f"Selected-successor {action} expected_version is invalid")
        result[action] = {
            "reservation": normalize_binding(
                proof["reservation"], f"{action} authority reservation"
            ),
            "pre_commit_verification": normalize_binding(
                proof["pre_commit_verification"],
                f"{action} authority pre-commit verification",
            ),
            "expected_version": version,
        }
    return result


def _validate_existing_checkpoints(
    root: Path,
    bundle: dict[str, Any],
    rows: list[dict[str, Any]],
    states: list[str],
) -> None:
    from manage_task_state_index.state.owner_validation import (
        validate_external_transition_receipt,
    )
    from manage_task_state_index.state.transition_external import load_pending_receipt
    from manage_task_state_index.state.transition_plan_contract import (
        load_transition_plan,
    )

    plan_binding = normalize_binding(bundle["task_state_plan"], "task-state plan")
    plan_path, plan, plan_sha256 = load_transition_plan(root, plan_binding["ref"])
    if (
        plan_sha256 != plan_binding["sha256"]
        or plan_path.relative_to(root).as_posix() != plan_binding["ref"]
    ):
        raise ValueError("Selected-successor task-state plan binding differs")
    if states[0] == "exact":
        pending, pending_binding = load_pending_receipt(
            root, plan, plan_binding["ref"], plan_binding["sha256"]
        )
        if (
            pending_binding != rows[0]["expected_result"]
            or pending.get("external_prepare") != bundle["selection_prepare"]
        ):
            raise ValueError("Selected-successor pending checkpoint is inconsistent")
    if states[1] == "exact":
        committed = validate_receipt(
            root, bundle["transaction_id"], require_current_targets=True
        )
        if {
            "ref": committed["receipt_ref"],
            "sha256": committed["receipt_sha256"],
        } != rows[1]["expected_result"]:
            raise ValueError(
                "Selected-successor publication checkpoint is inconsistent"
            )
    if states[2] == "exact":
        settled = validate_external_transition_receipt(
            root, rows[2]["expected_result"], phase="current"
        )
        if (
            settled.get("status") != "valid"
            or settled.get("plan_binding") != plan_binding
            or settled.get("selection_consumption_allowed") is not True
        ):
            raise ValueError("Selected-successor settlement checkpoint is inconsistent")


def _apply_effects(
    root: Path,
    bundle_binding: dict[str, str],
    bundle: dict[str, Any],
    rows: list[dict[str, Any]],
    states: list[str],
    proofs: dict[str, dict[str, Any]],
    *,
    skills_root: Path | None,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, str] | None,
    bool,
]:
    from manage_task_state_index.state.transition_plan import (
        apply_transition_plan,
        settle_transition_external,
    )

    effects: list[dict[str, Any]] = []
    leases: list[dict[str, Any]] = []
    gate: dict[str, str] | None = None
    gate_created = False

    def lease_for(action: str) -> dict[str, str]:
        nonlocal gate, gate_created
        lease, current_gate, created = publish_execution_lease(
            root,
            bundle_binding,
            rows,
            proofs,
            action=action,
            skills_root=skills_root,
        )
        gate = current_gate
        gate_created = gate_created or created
        leases.append({"action": action, "lease": lease})
        return lease

    if states[0] == "missing":
        lease = lease_for(ACTIONS[0])
        validate_pristine_source(root, bundle, states)
        result = apply_transition_plan(
            root,
            bundle["task_state_plan"]["ref"],
            external_prepare=bundle["selection_prepare"],
            execution_lease=lease,
        )
        if result.get("execution_result_binding") != rows[0]["expected_result"]:
            raise ValueError(
                "Selected-successor pending effect returned another checkpoint"
            )
        effects.append({"action": ACTIONS[0], "result": result})
        states[0] = "exact"
    if states[1] == "missing":
        _execution_effect_hook("before_step2_snapshot_validation", root, bundle, states)
        validate_plan_owned_predecessor_snapshot(root, bundle)
        lease = lease_for(ACTIONS[1])
        validate_plan_owned_predecessor_snapshot(root, bundle)
        result = publish_prepared(
            root,
            bundle["transaction_id"],
            execution_lease=lease,
        )
        binding = {
            "ref": result.get("receipt_ref"),
            "sha256": result.get("receipt_sha256"),
        }
        if binding != rows[1]["expected_result"]:
            raise ValueError(
                "Selected-successor publication returned another checkpoint"
            )
        effects.append({"action": ACTIONS[1], "result": result})
        states[1] = "exact"
    else:
        # A receipt is the step checkpoint, but a crash may have happened after
        # its immutable write and before compact-state or intent-index repair.
        result = publish_prepared(
            root,
            bundle["transaction_id"],
        )
        binding = {
            "ref": result.get("receipt_ref"),
            "sha256": result.get("receipt_sha256"),
        }
        if binding != rows[1]["expected_result"]:
            raise ValueError(
                "Selected-successor publication replay returned another checkpoint"
            )
        if result.get("mutation_performed"):
            effects.append({"action": ACTIONS[1], "result": result})
    if states[2] == "missing":
        lease = lease_for(ACTIONS[2])
        result = settle_transition_external(
            root,
            bundle["task_state_plan"]["ref"],
            rows[1]["expected_result"],
            execution_lease=lease,
        )
        if result.get("execution_result_binding") != rows[2]["expected_result"]:
            raise ValueError(
                "Selected-successor settlement returned another checkpoint"
            )
        effects.append({"action": ACTIONS[2], "result": result})
        states[2] = "exact"
    return effects, leases, gate, gate_created


def execute_selected_successor_bundle(
    root: Path,
    *,
    bundle_binding: dict[str, str],
    authority_proofs: dict[str, dict[str, Any]],
    settled_at: str,
    skills_root: Path | None = None,
) -> dict[str, Any]:
    """Execute or resume one bundle without treating partial state as no-effect."""

    root = root.expanduser().resolve(strict=True)
    bundle = load_selected_successor_bundle(root, bundle_binding)
    rows, states = checkpoint_states(root, bundle)
    proofs = _proofs(authority_proofs)
    if states not in (
        ["missing", "missing", "missing"],
        ["exact", "missing", "missing"],
        ["exact", "exact", "missing"],
        ["exact", "exact", "exact"],
    ):
        raise ValueError("Selected-successor checkpoints are not a legal prefix")
    validate_pristine_source(root, bundle, states)
    effects_required = "missing" in states
    owner_results = (
        rows[2]["expected_result"],
        rows[1]["expected_result"],
        rows[2]["expected_result"],
    )
    authority = authority_preflight(
        root,
        rows,
        proofs,
        require_current=effects_required,
        owner_results=owner_results,
        settled_at=settled_at,
        skills_root=skills_root.resolve() if skills_root is not None else None,
    )
    _validate_existing_checkpoints(root, bundle, rows, states)
    initial_states = list(states)
    effects, leases, gate, gate_created = _apply_effects(
        root,
        normalize_binding(bundle_binding, "selected-successor bundle"),
        bundle,
        rows,
        states,
        proofs,
        skills_root=(skills_root.resolve() if skills_root is not None else None),
    )
    if gate is None:
        gate, gate_created = _authority_gate(
            root, bundle_binding, rows, proofs, publish=False
        )
    _validate_existing_checkpoints(root, bundle, rows, states)
    settlements = settle_authority(
        root,
        rows,
        proofs,
        settled_at=settled_at,
        skills_root=skills_root.resolve() if skills_root is not None else None,
    )
    authority_mutation = any(row["state_status"] == "reserved" for row in authority)
    effect_mutation = any(
        bool(effect["result"].get("mutation_performed")) for effect in effects
    )
    return {
        "result_kind": "selected_successor_execution_result",
        "schema_version": 1,
        "status": "complete",
        "selected_task_id": bundle["selected_task_id"],
        "bundle": normalize_binding(bundle_binding, "selected-successor bundle"),
        "initial_checkpoints": dict(zip(ACTIONS, initial_states)),
        "final_checkpoints": {row["action"]: row["expected_result"] for row in rows},
        "authority_preflight": authority,
        "authority_gate": gate,
        "execution_leases": leases,
        "authority_settlements": settlements,
        "effect_actions": [effect["action"] for effect in effects],
        "idempotent_replay": not (
            gate_created or authority_mutation or effect_mutation
        ),
        "authority_mutation_performed": authority_mutation,
        "mutation_performed": gate_created or authority_mutation or effect_mutation,
        "recovery_required": False,
    }


__all__ = ("ACTIONS", "execute_selected_successor_bundle")
