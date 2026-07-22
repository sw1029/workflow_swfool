"""Authority-gated execution and recovery for one selected-successor bundle."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .selection_decision_store import normalize_binding, read_bound_bytes
from .selection_publication import publish_prepared, validate_receipt
from .selection_publication_store import (
    _canonical_json,
    _sha256_bytes,
    _successor_gate_path,
    _write_once,
)
from .selected_successor import load_selected_successor_bundle
from .selected_successor_execution_support import (
    ACTIONS,
    checkpoint_states,
    settle_authority,
    validate_pristine_source,
)


def _proofs(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict) or set(value) != set(ACTIONS):
        raise ValueError("Selected-successor execution requires all three authority proofs")
    result: dict[str, dict[str, Any]] = {}
    for action in ACTIONS:
        proof = value[action]
        if not isinstance(proof, dict) or set(proof) != {
            "reservation",
            "pre_commit_verification",
            "expected_version",
        }:
            raise ValueError(f"Selected-successor {action} authority proof is not closed")
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


def _authority_gate(
    root: Path,
    bundle_binding: dict[str, str],
    rows: list[dict[str, Any]],
    proofs: dict[str, dict[str, Any]],
    *,
    publish: bool,
) -> tuple[dict[str, str], bool]:
    body = {
        "schema_version": 1,
        "artifact_kind": "selected_successor_authority_gate",
        "gate_status": "all_pre_commits_current_before_first_effect",
        "bundle": normalize_binding(bundle_binding, "selected-successor bundle"),
        "checked_operations": [
            {
                "action": row["action"],
                "operation": row["operation"],
                "subject": row["subject"],
                "idempotency_key": row["idempotency_key"],
                "reservation": proofs[row["action"]]["reservation"],
                "pre_commit_verification": proofs[row["action"]][
                    "pre_commit_verification"
                ],
                "expected_version": proofs[row["action"]]["expected_version"],
            }
            for row in rows
        ],
    }
    content_sha256 = _sha256_bytes(_canonical_json(body))
    gate = {**body, "gate_content_sha256": content_sha256}
    payload = _canonical_json(gate)
    path = _successor_gate_path(root, content_sha256)
    created = not path.exists() and not path.is_symlink()
    if publish:
        digest = _write_once(
            path, payload, "selected-successor pre-effect authority gate"
        )
    else:
        binding = {
            "ref": path.relative_to(root).as_posix(),
            "sha256": _sha256_bytes(payload),
        }
        read_bound_bytes(root, binding, "selected-successor pre-effect authority gate")
        digest = binding["sha256"]
    return {"ref": path.relative_to(root).as_posix(), "sha256": digest}, (
        publish and created
    )


def _authority_preflight(
    root: Path,
    rows: list[dict[str, Any]],
    proofs: dict[str, dict[str, Any]],
    *,
    require_current: bool,
    owner_results: tuple[dict[str, str], ...] | None = None,
    settled_at: str | None = None,
    skills_root: Path | None = None,
) -> list[dict[str, Any]]:
    from manage_agent_authority.execution_results import (
        validate_pre_commit_verification,
    )
    from manage_agent_authority.historical_proof_chain import (
        validate_historical_proof_chains,
    )

    checked: list[dict[str, Any]] = []
    chains = validate_historical_proof_chains(
        root,
        [
            (
                proofs[action]["reservation"],
                proofs[action]["pre_commit_verification"],
                proofs[action]["expected_version"],
            )
            for action in ACTIONS
        ],
        skills_root=skills_root,
    )
    for row, chain in zip(rows, chains):
        action = row["action"]
        proof = proofs[action]
        reservation_binding = proof["reservation"]
        reservation = chain["reservation"]
        state = chain["current_state"]
        if chain["reservation_binding"] != reservation_binding:
            raise ValueError(f"Selected-successor {action} reservation path differs")
        decision = chain["decision"]
        request = decision.get("request")
        operation = row.get("operation")
        if not isinstance(request, dict) or not isinstance(operation, dict):
            raise ValueError(f"Selected-successor {action} authority request is invalid")
        expected_operation = {
            key: operation.get(key)
            for key in (
                "skill_id",
                "skill_version",
                "operation_id",
                "operation_version",
            )
        }
        if (
            any(request.get(key) != value for key, value in expected_operation.items())
            or request.get("subject") != row.get("subject")
            or request.get("idempotency_key") != row.get("idempotency_key")
            or reservation.get("idempotency_key") != row.get("idempotency_key")
        ):
            raise ValueError(
                f"Selected-successor {action} reservation authorizes another operation"
            )
        expected_version = proof["expected_version"]
        replayed = False
        if require_current:
            if state.get("status") != "reserved" or state.get("version") != expected_version:
                raise ValueError(
                    f"Selected-successor {action} reservation is not current before effect"
                )
        else:
            if state.get("status") == "reserved" and state.get("version") == expected_version:
                pass
            elif (
                state.get("status") == "consumed"
                and state.get("version") == expected_version + 1
            ):
                if owner_results is None or settled_at is None:
                    raise ValueError("Consumed authority replay inputs are missing")
                from manage_agent_authority.settlement import settle_owner_result

                replay = settle_owner_result(
                    root,
                    reservation_binding["ref"],
                    reservation_binding["sha256"],
                    owner_results[len(checked)],
                    proof["pre_commit_verification"],
                    settled_at=settled_at,
                    expected_version=expected_version,
                    idempotency_key=row["idempotency_key"],
                    skills_root=skills_root,
                )
                if (
                    replay.get("status") != "consumed"
                    or replay.get("outcome") != "confirmed_effect"
                ):
                    raise ValueError(
                        f"Selected-successor {action} consumed replay is invalid"
                    )
                replayed = True
            else:
                raise ValueError(
                    f"Selected-successor {action} reservation is not replayable"
                )
        if chain["verification_binding"] != proof["pre_commit_verification"]:
            raise ValueError(
                f"Selected-successor {action} pre-commit verification path differs"
            )
        if state.get("status") == "reserved":
            validate_pre_commit_verification(
                root,
                reservation,
                reservation_binding,
                proof["pre_commit_verification"],
                expected_version=expected_version,
                require_current_state=True,
            )
        checked.append(
            {
                "action": action,
                "reservation": reservation_binding,
                "pre_commit_verification": proof["pre_commit_verification"],
                "expected_version": expected_version,
                "state_status": state.get("status"),
                "exact_v3_settlement_replayed": replayed,
            }
        )
    return checked


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
            raise ValueError("Selected-successor publication checkpoint is inconsistent")
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
    bundle: dict[str, Any],
    rows: list[dict[str, Any]],
    states: list[str],
) -> list[dict[str, Any]]:
    from manage_task_state_index.state.transition_plan import (
        apply_transition_plan,
        settle_transition_external,
    )
    from manage_task_state_index.state.selected_successor_guard import (
        _SELECTED_SUCCESSOR_EXECUTION_TOKEN,
    )

    effects: list[dict[str, Any]] = []
    if states[0] == "missing":
        result = apply_transition_plan(
            root,
            bundle["task_state_plan"]["ref"],
            external_prepare=bundle["selection_prepare"],
            _selected_successor_execution_token=_SELECTED_SUCCESSOR_EXECUTION_TOKEN,
        )
        if result.get("execution_result_binding") != rows[0]["expected_result"]:
            raise ValueError("Selected-successor pending effect returned another checkpoint")
        effects.append({"action": ACTIONS[0], "result": result})
        states[0] = "exact"
    if states[1] == "missing":
        result = publish_prepared(
            root,
            bundle["transaction_id"],
            _selected_successor_execution_token=_SELECTED_SUCCESSOR_EXECUTION_TOKEN,
        )
        binding = {"ref": result.get("receipt_ref"), "sha256": result.get("receipt_sha256")}
        if binding != rows[1]["expected_result"]:
            raise ValueError("Selected-successor publication returned another checkpoint")
        effects.append({"action": ACTIONS[1], "result": result})
        states[1] = "exact"
    else:
        # A receipt is the step checkpoint, but a crash may have happened after
        # its immutable write and before compact-state or intent-index repair.
        result = publish_prepared(
            root,
            bundle["transaction_id"],
            _selected_successor_execution_token=_SELECTED_SUCCESSOR_EXECUTION_TOKEN,
        )
        binding = {
            "ref": result.get("receipt_ref"),
            "sha256": result.get("receipt_sha256"),
        }
        if binding != rows[1]["expected_result"]:
            raise ValueError("Selected-successor publication replay returned another checkpoint")
        if result.get("mutation_performed"):
            effects.append({"action": ACTIONS[1], "result": result})
    if states[2] == "missing":
        result = settle_transition_external(
            root,
            bundle["task_state_plan"]["ref"],
            rows[1]["expected_result"],
            _selected_successor_execution_token=_SELECTED_SUCCESSOR_EXECUTION_TOKEN,
        )
        if result.get("execution_result_binding") != rows[2]["expected_result"]:
            raise ValueError("Selected-successor settlement returned another checkpoint")
        effects.append({"action": ACTIONS[2], "result": result})
        states[2] = "exact"
    return effects


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
    if states != ["missing", "missing", "missing"]:
        gate, gate_created = _authority_gate(
            root, bundle_binding, rows, proofs, publish=False
        )
    authority = _authority_preflight(
        root,
        rows,
        proofs,
        require_current=effects_required,
        owner_results=owner_results,
        settled_at=settled_at,
        skills_root=skills_root.resolve() if skills_root is not None else None,
    )
    if states == ["missing", "missing", "missing"]:
        gate, gate_created = _authority_gate(
            root, bundle_binding, rows, proofs, publish=True
        )
    _validate_existing_checkpoints(root, bundle, rows, states)
    initial_states = list(states)
    effects = _apply_effects(root, bundle, rows, states)
    _validate_existing_checkpoints(root, bundle, rows, states)
    settlements = settle_authority(
        root,
        rows,
        proofs,
        settled_at=settled_at,
        skills_root=skills_root.resolve() if skills_root is not None else None,
    )
    authority_mutation = any(
        row["state_status"] == "reserved" for row in authority
    )
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
        "final_checkpoints": {
            row["action"]: row["expected_result"] for row in rows
        },
        "authority_preflight": authority,
        "authority_gate": gate,
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
