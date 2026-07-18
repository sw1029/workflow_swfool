"""Closed intent and receipt contracts for canonical task transitions."""

from __future__ import annotations

from typing import Any

from .common import HEX64, expect_keys, require, sha256_json
from .task_transition_plan import validate_task_transition_plan
from .task_transition_store import owned_ref


SCHEMA_VERSION = 1
INTENT_KIND = "task_transition_intent"
RECEIPT_KIND = "task_transition_receipt"
NO_EFFECT_REASONS = {
    "canonical_prestate_stale",
    "interrupted_pre_intent_no_effect",
    "prospective_missing",
    "prospective_digest_mismatch",
}


def _binding(value: Any, label: str) -> dict[str, str]:
    require(isinstance(value, dict), "invalid_owner_result",
            f"{label} must be an object")
    expect_keys(value, {"ref", "sha256"}, set(), label, "invalid_owner_result")
    require(isinstance(value["ref"], str) and bool(value["ref"]),
            "invalid_owner_result", f"{label}.ref must be non-empty")
    require(isinstance(value["sha256"], str)
            and HEX64.fullmatch(value["sha256"]) is not None,
            "invalid_owner_result", f"{label}.sha256 must be lowercase SHA-256")
    return value


def expected_intent(
    plan: dict[str, Any], plan_binding: dict[str, str],
) -> dict[str, Any]:
    normalized = validate_task_transition_plan(plan)
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": INTENT_KIND,
        "transition_id": normalized["transition_id"],
        "transition_kind": normalized["transition_kind"],
        "plan_binding": dict(plan_binding),
        "plan_sha256": normalized["plan_sha256"],
        "before_task": dict(normalized["before_task"]),
        "after_task": dict(normalized["after_task"]),
        "archive_task": dict(normalized["archive_task"]),
    }


def validate_intent(
    plan: dict[str, Any], plan_binding: dict[str, str], value: Any,
) -> dict[str, Any]:
    require(isinstance(value, dict), "invalid_owner_result",
            "task transition intent must be an object")
    expected = expected_intent(plan, plan_binding)
    expect_keys(value, set(expected), set(), "task transition intent",
                "invalid_owner_result")
    require(value == expected, "invalid_owner_result",
            "task transition intent differs from the exact owner plan")
    return value


def _receipt_id(body: dict[str, Any]) -> str:
    return f"task-transition-receipt-{sha256_json(body)[:24]}"


def effect_receipt(
    plan: dict[str, Any], plan_binding: dict[str, str],
    intent_binding: dict[str, str], successor_binding: dict[str, str],
    archive_binding: dict[str, str] | None,
) -> dict[str, Any]:
    normalized = validate_task_transition_plan(plan)
    body = {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": RECEIPT_KIND,
        "transition_id": normalized["transition_id"],
        "transition_kind": normalized["transition_kind"],
        "plan_binding": dict(plan_binding),
        "plan_sha256": normalized["plan_sha256"],
        "effect_status": "confirmed_effect",
        "settlement_kind": "applied",
        "intent": dict(intent_binding),
        "successor_task": dict(successor_binding),
        "canonical_task": dict(normalized["after_task"]),
        "archive_task": (
            dict(archive_binding) if archive_binding is not None else None
        ),
    }
    return {**body, "receipt_id": _receipt_id(body)}


def no_effect_receipt(
    plan: dict[str, Any], plan_binding: dict[str, str],
    canonical_observation: dict[str, Any],
    prospective_observation: dict[str, Any], reason_codes: list[str],
    observation_binding: dict[str, str] | None,
) -> dict[str, Any]:
    normalized = validate_task_transition_plan(plan)
    body = {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": RECEIPT_KIND,
        "transition_id": normalized["transition_id"],
        "transition_kind": normalized["transition_kind"],
        "plan_binding": dict(plan_binding),
        "plan_sha256": normalized["plan_sha256"],
        "effect_status": "confirmed_no_effect",
        "settlement_kind": "pre_intent_no_effect",
        "intent_absent": True,
        "canonical_observation": canonical_observation,
        "prospective_observation": prospective_observation,
        "observation_task": (
            dict(observation_binding) if observation_binding is not None else None
        ),
        "archive_ref": owned_ref(
            normalized["transition_id"], "archives", "md"
        ),
        "archive_absent": True,
        "reason_codes": sorted(reason_codes),
    }
    return {**body, "receipt_id": _receipt_id(body)}


def _validate_observation(value: Any, label: str) -> dict[str, Any]:
    require(isinstance(value, dict), "invalid_owner_result",
            f"{label} must be an object")
    expect_keys(value, {"exists", "sha256"}, set(), label,
                "invalid_owner_result")
    require(isinstance(value["exists"], bool), "invalid_owner_result",
            f"{label}.exists must be boolean")
    digest = value["sha256"]
    require(
        (not value["exists"] and digest is None)
        or (
            value["exists"]
            and isinstance(digest, str)
            and HEX64.fullmatch(digest) is not None
        ),
        "invalid_owner_result",
        f"{label} existence and digest are inconsistent",
    )
    return value


def _validate_prospective_observation(value: Any) -> dict[str, Any]:
    require(isinstance(value, dict), "invalid_owner_result",
            "prospective_observation must be an object")
    expect_keys(value, {"state", "sha256"}, set(), "prospective_observation",
                "invalid_owner_result")
    require(value["state"] in {"missing", "exact", "digest_mismatch"},
            "invalid_owner_result", "prospective observation state is invalid")
    digest = value["sha256"]
    require(
        (value["state"] == "missing" and digest is None)
        or (
            value["state"] != "missing"
            and isinstance(digest, str)
            and HEX64.fullmatch(digest) is not None
        ),
        "invalid_owner_result",
        "prospective observation state and digest are inconsistent",
    )
    return value


def validate_receipt(
    plan: dict[str, Any], plan_binding: dict[str, str], value: Any,
) -> dict[str, Any]:
    normalized = validate_task_transition_plan(plan)
    require(isinstance(value, dict), "invalid_owner_result",
            "task transition receipt must be an object")
    common = {
        "schema_version", "artifact_kind", "receipt_id", "transition_id",
        "transition_kind", "plan_binding", "plan_sha256", "effect_status",
        "settlement_kind",
    }
    effect = {"intent", "successor_task", "canonical_task", "archive_task"}
    no_effect = {
        "intent_absent", "canonical_observation", "prospective_observation",
        "observation_task", "archive_ref", "archive_absent", "reason_codes",
    }
    expected_extra = effect if value.get("effect_status") == "confirmed_effect" else no_effect
    expect_keys(value, common | expected_extra, set(), "task transition receipt",
                "invalid_owner_result")
    require(value["schema_version"] == SCHEMA_VERSION
            and value["artifact_kind"] == RECEIPT_KIND,
            "invalid_owner_result", "task transition receipt type mismatch")
    require(value["transition_id"] == normalized["transition_id"]
            and value["transition_kind"] == normalized["transition_kind"]
            and value["plan_sha256"] == normalized["plan_sha256"]
            and value["plan_binding"] == plan_binding,
            "invalid_owner_result", "task transition receipt plan binding mismatch")
    body = {key: item for key, item in value.items() if key != "receipt_id"}
    require(value["receipt_id"] == _receipt_id(body), "invalid_owner_result",
            "task transition receipt identity mismatch")
    if value["effect_status"] == "confirmed_effect":
        return _validate_effect_receipt(normalized, value)
    require(value["effect_status"] == "confirmed_no_effect",
            "invalid_owner_result", "task transition receipt effect is invalid")
    return _validate_no_effect_receipt(normalized, value)


def _validate_effect_receipt(
    plan: dict[str, Any], value: dict[str, Any],
) -> dict[str, Any]:
    require(value["settlement_kind"] == "applied", "invalid_owner_result",
            "confirmed task effect requires an applied receipt")
    _binding(value["intent"], "intent")
    successor = _binding(value["successor_task"], "successor_task")
    require(successor["ref"] == owned_ref(
        plan["transition_id"], "successors", "md"
    ) and successor["sha256"] == plan["after_task"]["sha256"],
            "invalid_owner_result", "receipt binds a different successor snapshot")
    require(value["canonical_task"] == plan["after_task"],
            "invalid_owner_result", "receipt declares a different canonical task")
    archive = value["archive_task"]
    if plan["archive_task"]["required"]:
        _binding(archive, "archive_task")
        require(archive["ref"] == plan["archive_task"]["ref"]
                and archive["sha256"] == plan["archive_task"]["sha256"],
                "invalid_owner_result", "receipt binds a different predecessor archive")
    else:
        require(archive is None, "invalid_owner_result",
                "initial task receipt cannot bind a predecessor archive")
    return value


def _validate_no_effect_receipt(
    plan: dict[str, Any], value: dict[str, Any],
) -> dict[str, Any]:
    require(value["settlement_kind"] == "pre_intent_no_effect"
            and value["intent_absent"] is True
            and value["archive_absent"] is True,
            "invalid_owner_result", "no-effect receipt lacks pre-intent proof")
    _validate_observation(value["canonical_observation"], "canonical_observation")
    _validate_prospective_observation(value["prospective_observation"])
    observation = value["observation_task"]
    if value["canonical_observation"]["exists"]:
        observation = _binding(observation, "observation_task")
        require(observation["ref"] == owned_ref(
            plan["transition_id"], "observations", "md"
        ) and observation["sha256"] == value["canonical_observation"]["sha256"],
                "invalid_owner_result",
                "no-effect receipt binds a different canonical observation snapshot")
    else:
        require(observation is None, "invalid_owner_result",
                "an absent canonical observation cannot bind snapshot bytes")
    require(value["archive_ref"] == owned_ref(
        plan["transition_id"], "archives", "md"
    ), "invalid_owner_result", "no-effect receipt archive ref mismatch")
    reasons = value["reason_codes"]
    require(isinstance(reasons, list) and bool(reasons)
            and reasons == sorted(set(reasons))
            and set(reasons) <= NO_EFFECT_REASONS,
            "invalid_owner_result", "no-effect receipt reasons are invalid")
    return value


__all__ = [
    "effect_receipt",
    "expected_intent",
    "no_effect_receipt",
    "validate_intent",
    "validate_receipt",
]
