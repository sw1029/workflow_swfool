"""Read-only historical and current-state verification for task transitions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .common import WorkflowError, canonical_bytes, require
from .task_transition_contract import (
    expected_intent,
    validate_intent,
    validate_receipt,
)
from .task_transition_store import (
    file_bytes,
    load_task_transition_plan,
    owned_ref,
)


def sha256_bytes(payload: bytes) -> str:
    import hashlib

    return hashlib.sha256(payload).hexdigest()


def binding(ref: str, digest: str) -> dict[str, str]:
    return {"ref": ref, "sha256": digest}


def canonical_observation(root: Path) -> dict[str, Any]:
    payload = file_bytes(root, "task.md", "canonical task")
    return {
        "exists": payload is not None,
        "sha256": sha256_bytes(payload) if payload is not None else None,
    }


def prospective_observation(
    root: Path, plan: dict[str, Any],
) -> tuple[dict[str, Any], bytes | None]:
    payload = file_bytes(root, plan["prospective_task"]["ref"], "prospective task")
    if payload is None:
        return {"state": "missing", "sha256": None}, None
    digest = sha256_bytes(payload)
    state = "exact" if digest == plan["prospective_task"]["sha256"] else "digest_mismatch"
    return {"state": state, "sha256": digest}, payload


def matches(observation: dict[str, Any], state: dict[str, Any]) -> bool:
    return observation["exists"] == state["exists"] and (
        not observation["exists"] or observation["sha256"] == state["sha256"]
    )


def artifact_state(
    root: Path, ref: str, expected: dict[str, Any] | None, label: str,
) -> tuple[str, dict[str, Any] | None, str | None]:
    payload = file_bytes(root, ref, label)
    if payload is None:
        return "missing", None, None
    digest = sha256_bytes(payload)
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "conflict", None, digest
    if not isinstance(value, dict):
        return "conflict", None, digest
    if expected is not None and payload != canonical_bytes(expected):
        return "conflict", value, digest
    return "current", value, digest


def archive_state(root: Path, plan: dict[str, Any]) -> tuple[str, str | None]:
    ref = owned_ref(plan["transition_id"], "archives", "md")
    payload = file_bytes(root, ref, "predecessor task archive")
    if payload is None:
        return "missing", None
    digest = sha256_bytes(payload)
    expected = plan["archive_task"]
    if not expected["required"] or expected["ref"] != ref or expected["sha256"] != digest:
        return "conflict", digest
    return "current", digest


def snapshot_state(
    root: Path, plan: dict[str, Any], kind: str, expected_sha256: str | None,
) -> tuple[str, str | None]:
    ref = owned_ref(plan["transition_id"], kind, "md")
    payload = file_bytes(root, ref, f"task transition {kind} snapshot")
    if payload is None:
        return "missing", None
    digest = sha256_bytes(payload)
    if expected_sha256 is None or digest == expected_sha256:
        return "current", digest
    return "conflict", digest


def receipt_state(
    root: Path, plan: dict[str, Any], plan_binding: dict[str, str],
) -> tuple[str, dict[str, Any] | None, str | None]:
    ref = owned_ref(plan["transition_id"], "receipts", "json")
    state, value, digest = artifact_state(
        root, ref, None, "task transition receipt"
    )
    if state != "current" or value is None:
        return state, value, digest
    try:
        validate_receipt(plan, plan_binding, value)
    except WorkflowError:
        return "conflict", value, digest
    if file_bytes(root, ref, "task transition receipt") != canonical_bytes(value):
        return "conflict", value, digest
    return "current", value, digest


def intent_state(
    root: Path, plan: dict[str, Any], plan_binding: dict[str, str],
) -> tuple[str, dict[str, Any] | None, str | None]:
    ref = owned_ref(plan["transition_id"], "intents", "json")
    expected = expected_intent(plan, plan_binding)
    state, value, digest = artifact_state(
        root, ref, expected, "task transition intent"
    )
    if state == "current" and value is not None:
        validate_intent(plan, plan_binding, value)
    return state, value, digest


def _receipt_verification(
    root: Path, plan: dict[str, Any], plan_binding: dict[str, str],
    receipt: dict[str, Any], receipt_digest: str, phase: str,
) -> dict[str, Any]:
    canonical = canonical_observation(root)
    intent, _value, intent_digest = intent_state(root, plan, plan_binding)
    archive, archive_digest = archive_state(root, plan)
    successor, successor_digest = snapshot_state(
        root, plan, "successors", plan["after_task"]["sha256"]
    )
    observation_sha = (
        receipt.get("canonical_observation", {}).get("sha256")
        if receipt["effect_status"] == "confirmed_no_effect" else None
    )
    observation, observation_digest = snapshot_state(
        root, plan, "observations", observation_sha
    )
    effect = receipt["effect_status"]
    if effect == "confirmed_effect":
        valid = _effect_receipt_current(
            plan, receipt, intent, intent_digest, archive, archive_digest,
            successor, successor_digest, observation,
        )
        status = "already_applied" if valid else "recovery_required"
    else:
        valid = _no_effect_receipt_current(
            plan, receipt, intent, archive, successor, observation,
            observation_digest,
        )
        status = "settled_no_effect" if valid else "conflict"
    canonical_after = matches(canonical, {"exists": True, **plan["after_task"]})
    return {
        "status": status,
        "phase": phase,
        "effect_status": effect,
        "prestate_current": matches(canonical, plan["before_task"]),
        "effect_observed": effect == "confirmed_effect" and valid,
        "canonical_matches_after": canonical_after,
        "current_projection_healthy": (
            canonical_after if effect == "confirmed_effect"
            else canonical == receipt["canonical_observation"]
        ),
        "intent_observed": intent != "missing",
        "receipt_observed": True,
        "no_effect_verified": effect == "confirmed_no_effect" and valid,
        "receipt_ref": owned_ref(plan["transition_id"], "receipts", "json"),
        "receipt_file_sha256": receipt_digest,
    }


def _effect_receipt_current(
    plan: dict[str, Any], receipt: dict[str, Any], intent: str,
    intent_digest: str | None, archive: str, archive_digest: str | None,
    successor: str, successor_digest: str | None, observation: str,
) -> bool:
    return (
        intent == "current"
        and receipt["intent"] == binding(
            owned_ref(plan["transition_id"], "intents", "json"), str(intent_digest)
        )
        and successor == "current"
        and receipt["successor_task"] == binding(
            owned_ref(plan["transition_id"], "successors", "md"),
            str(successor_digest),
        )
        and observation == "missing"
        and (
            (not plan["archive_task"]["required"] and archive == "missing")
            or (
                plan["archive_task"]["required"]
                and archive == "current"
                and receipt["archive_task"] == binding(
                    str(plan["archive_task"]["ref"]), str(archive_digest)
                )
            )
        )
    )


def _no_effect_receipt_current(
    plan: dict[str, Any], receipt: dict[str, Any], intent: str, archive: str,
    successor: str, observation: str, observation_digest: str | None,
) -> bool:
    observation_current = (
        receipt["canonical_observation"]["exists"]
        and observation == "current"
        and receipt["observation_task"] == binding(
            owned_ref(plan["transition_id"], "observations", "md"),
            str(observation_digest),
        )
    ) or (
        not receipt["canonical_observation"]["exists"]
        and observation == "missing"
    )
    return (
        intent == "missing" and archive == "missing"
        and successor == "missing" and observation_current
    )


def unsettled_verification(
    root: Path, plan: dict[str, Any], plan_binding: dict[str, str], phase: str,
) -> dict[str, Any]:
    canonical = canonical_observation(root)
    prospective, _payload = prospective_observation(root, plan)
    intent, _value, _digest = intent_state(root, plan, plan_binding)
    archive, _archive_digest = archive_state(root, plan)
    successor, _successor_digest = snapshot_state(
        root, plan, "successors", plan["after_task"]["sha256"]
    )
    observation, _observation_digest = snapshot_state(
        root, plan, "observations", None
    )
    prestate = matches(canonical, plan["before_task"])
    canonical_after = matches(canonical, {"exists": True, **plan["after_task"]})
    effect = intent == "current" and canonical_after
    if intent == "conflict" or archive == "conflict" or successor == "conflict":
        status = "conflict"
    elif any(value == "current" for value in (
        intent, archive, successor, observation
    )):
        status = "recovery_required"
    elif canonical_after:
        status = "conflict"
    elif prestate and prospective["state"] == "exact":
        status = "ready" if phase == "planning" else "not_applied"
    else:
        status = "stale"
    return {
        "status": status,
        "phase": phase,
        "effect_status": None,
        "prestate_current": prestate,
        "effect_observed": effect,
        "canonical_matches_after": canonical_after,
        "current_projection_healthy": prestate,
        "intent_observed": intent != "missing",
        "receipt_observed": False,
        "no_effect_verified": False,
        "prospective_observation": prospective,
        "receipt_ref": None,
        "receipt_file_sha256": None,
    }


def inspect_transition(
    root: Path, plan: dict[str, Any], plan_binding: dict[str, str], phase: str,
) -> dict[str, Any]:
    state, receipt, receipt_digest = receipt_state(root, plan, plan_binding)
    if state == "conflict":
        return {
            "status": "conflict", "phase": phase, "effect_status": None,
            "prestate_current": False, "effect_observed": False,
            "canonical_matches_after": False, "current_projection_healthy": False,
            "intent_observed": False, "receipt_observed": True,
            "no_effect_verified": False, "receipt_ref": None,
            "receipt_file_sha256": receipt_digest,
        }
    if state == "current" and receipt is not None and receipt_digest is not None:
        return _receipt_verification(
            root, plan, plan_binding, receipt, receipt_digest, phase
        )
    return unsettled_verification(root, plan, plan_binding, phase)


def verify_task_transition_execution(
    root: Path, path_value: str | Path, *, phase: str = "planning",
) -> dict[str, Any]:
    """Read-only verification of historical settlement and current projection."""

    require(phase in {"planning", "apply"}, "invalid_owner_plan",
            "task transition verification phase must be planning or apply")
    _path, plan, plan_file_sha256, plan_ref = load_task_transition_plan(
        root, path_value
    )
    result = inspect_transition(
        root.resolve(), plan, binding(plan_ref, plan_file_sha256), phase
    )
    return {
        "result_kind": "task_transition_verification_result",
        "schema_version": 1,
        "plan_ref": plan_ref,
        "plan_file_sha256": plan_file_sha256,
        "plan_sha256": plan["plan_sha256"],
        "transition_id": plan["transition_id"],
        "historical_transaction_complete": result["status"] in {
            "already_applied", "settled_no_effect",
        },
        "mutation_performed": False,
        **result,
    }


__all__ = [
    "archive_state", "binding", "canonical_observation", "inspect_transition",
    "intent_state", "matches", "prospective_observation", "sha256_bytes",
    "snapshot_state", "verify_task_transition_execution",
]
