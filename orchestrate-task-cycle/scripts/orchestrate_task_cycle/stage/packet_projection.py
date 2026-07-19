"""Bounded compatibility inputs for legacy subskill packet builders."""

from __future__ import annotations

from typing import Any

from ..packet.context import authority_policy
from ..render_subskill_packet import packet_for
from .contracts import canonical_bytes, state_fingerprint
from .specs import TARGET_COMPILE_SPECS


MAX_MODEL_PACKET_BYTES = 384 * 1024
MAX_ROUTING_INPUT_BYTES = 64 * 1024
ROUTING_PROFILE_FIELDS = (
    "final_direction_ownership",
    "signals",
    "signal_evidence",
    "request_max",
    "max_escalation_reason",
    "prior_tier5_evidence",
    "agent_count",
)


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _routing_projection(value: Any) -> dict[str, Any]:
    routing = _mapping(value)
    bindings = _mapping(routing.get("model_bindings"))
    profiles = _mapping(routing.get("profiles"))
    projected = {
        "model_bindings": {
            str(model_ref): {
                key: binding.get(key)
                for key in ("model", "binding_id", "source")
                if key in binding
            }
            for model_ref, binding in bindings.items()
            if isinstance(binding, dict)
        },
        "profiles": {
            str(profile_id): {
                field: request.get(field)
                for field in ROUTING_PROFILE_FIELDS
                if field in request
            }
            for profile_id, request in profiles.items()
            if isinstance(request, dict)
        },
    }
    if len(canonical_bytes(projected)) > MAX_ROUTING_INPUT_BYTES:
        raise ValueError("model_packet_budget_exceeded: routing input is too large")
    return projected


def _count_context(full: dict[str, Any]) -> dict[str, Any]:
    state = _mapping(full.get("task_state"))
    return {
        "task_state": {
            "task_miss": {
                "active_count": _mapping(state.get("task_miss")).get("active_count")
            },
            "candidate_task": {
                "count": _mapping(state.get("candidate_task")).get("count")
            },
            "task_pack": {
                key: _mapping(state.get("task_pack")).get(key)
                for key in ("count", "active_count")
            },
            "validation_set": {
                "count": _mapping(state.get("validation_set")).get("count")
            },
        },
        "issue": {"active_count": _mapping(full.get("issue")).get("active_count")},
        "schema": {"count": _mapping(full.get("schema")).get("count")},
        "contract": {"count": _mapping(full.get("contract")).get("count")},
        "agent_log": {
            "markdown_count": _mapping(full.get("agent_log")).get("markdown_count")
        },
        "validation_assets": {
            "sets": {
                "count": _mapping(
                    _mapping(full.get("validation_assets")).get("sets")
                ).get("count")
            }
        },
    }


def _compact_context(full: dict[str, Any], model: dict[str, Any]) -> dict[str, Any]:
    task = _mapping(model.get("task"))
    task_binding = dict(_mapping(task.get("task_md")))
    full_task = _mapping(full.get("task_md"))
    if full_task.get("title") is not None:
        task_binding["title"] = full_task.get("title")
    goal = _mapping(model.get("goal_truth"))
    advice = _mapping(model.get("advice"))
    context = {
        "workspace": model.get("workspace"),
        "task_md": task_binding,
        "agent_goal": {
            "available_goal_truth": list(goal.get("available_goal_truth") or []),
            "used_goal_truth": list(goal.get("used_goal_truth") or []),
        },
        "external_advice": {
            "active_count": advice.get("active_count", 0),
            "normalized_packet": {"used_advice": list(advice.get("items") or [])},
        },
        "model_effort_routing": _routing_projection(full.get("model_effort_routing")),
        **_count_context(full),
    }
    return context


def _compact_stage(stage: dict[str, Any]) -> dict[str, Any]:
    return {
        "authority_policy": authority_policy(stage),
        "model_effort_routing": _routing_projection(stage.get("model_effort_routing")),
    }


def _generic_authority_packet(model: dict[str, Any]) -> dict[str, Any]:
    roles = TARGET_COMPILE_SPECS["authority"].dependency_roles
    return {
        "target": "authority",
        "authority_policy": "owner_artifact_only",
        "required_inputs": [
            "authority-owner decision artifact",
            "reservation and verification when mutation is allowed",
        ],
        "required_outputs": list(TARGET_COMPILE_SPECS["authority"].required_fields),
        "model_context_binding": {"state_fingerprint": state_fingerprint(model, roles)},
    }


def model_packet(
    target: str,
    full: dict[str, Any],
    model: dict[str, Any],
    workflow_mode: str,
) -> dict[str, Any]:
    if target == "authority":
        packet = _generic_authority_packet(model)
    else:
        stage = _mapping(_mapping(full.get("cycle_state")).get("current_stage"))
        packet = packet_for(
            target,
            _compact_context(full, model),
            _compact_stage(stage),
            workflow_mode,
        )
        packet["used_goal_truth"] = _mapping(model.get("goal_truth")).get(
            "used_goal_truth", []
        )
        packet["used_advice"] = _mapping(model.get("advice")).get("items", [])
        packet["model_context_binding"] = {
            "state_fingerprint": state_fingerprint(
                model, TARGET_COMPILE_SPECS[target].dependency_roles
            )
        }
        if "diagnostics" not in TARGET_COMPILE_SPECS[target].dependency_roles:
            packet.pop("context_counts", None)
        packet.pop("session_audit", None)
        packet.pop("task_pack_packet", None)
    size = len(canonical_bytes(packet))
    if size > MAX_MODEL_PACKET_BYTES:
        raise ValueError(
            f"model_packet_budget_exceeded: {size} > {MAX_MODEL_PACKET_BYTES} bytes"
        )
    return packet


__all__ = ["MAX_MODEL_PACKET_BYTES", "MAX_ROUTING_INPUT_BYTES", "model_packet"]
