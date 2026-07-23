from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ..result_contract.session_audit import sanitize_collection_summary
from .context import (
    PacketBuildContext,
    active_advice,
    authority_policy,
    available_goal_truth,
    counts,
    deep_get,
    goal_truth,
    output_delta_contract_packet,
    task_summary,
)
from .registry import TARGET_BUILDERS


@dataclass
class PacketState:
    target: str
    workflow_mode: str
    build_context: PacketBuildContext
    _legacy_v1_permit: object = field(repr=False)
    packet: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_packet_state(self)


def _require_packet_state(state: object) -> PacketState:
    if not isinstance(state, PacketState):
        raise ValueError(
            "packet stages require an authorized PacketState"
        )
    from .protocol import _validate_legacy_packet_permit

    _validate_legacy_packet_permit(
        state._legacy_v1_permit,
        state.build_context.context,
        state.build_context.stage,
    )
    return state


class PacketStage(Protocol):
    def apply(self, state: PacketState) -> None: ...


class BasePacketStage:
    def apply(self, state: PacketState) -> None:
        state = _require_packet_state(state)
        ctx = state.build_context
        context = ctx.context
        policy = ctx.model_effort_policy
        state.packet.update(
            {
                "target": state.target,
                "workspace": context.get("workspace"),
                "task": task_summary(context),
                "authority_policy": authority_policy(ctx.stage),
                "available_goal_truth": available_goal_truth(context),
                "used_goal_truth": goal_truth(context),
                "used_advice": active_advice(context),
                "advice_not_goal_truth": True,
                "context_counts": counts(context),
                "routing_reference": str(ctx.routing_reference_path),
                "model_effort_policy": {
                    "policy_id": policy["policy_id"],
                    "policy_path": str(ctx.model_effort_profile_path),
                    "models": policy["models"],
                    "tiers": policy["tiers"],
                    "model_binding_contract": policy["model_binding_contract"],
                    "dynamic_routing_input": {
                        "path": "model_effort_routing.profiles.<profile_id>",
                        "fields": [
                            "final_direction_ownership",
                            "signals",
                            "signal_evidence",
                            "request_max",
                            "max_escalation_reason",
                            "prior_tier5_evidence",
                            "agent_count",
                        ],
                        "allowed_signals": policy["dynamic_signals"],
                    },
                    "routing_result_contract": {
                        "agent_routing_applicability": (
                            "delegated|deterministic_only|delegation_unavailable"
                        ),
                        "routing_enforcement": policy["result_enforcement_values"],
                        "required_when_delegated": [
                            "policy_id",
                            "profile_id",
                            "routing_tier",
                            "requested_model_ref",
                            "requested_model",
                            "model_configuration_status",
                            "requested_reasoning_effort",
                            "routing_reason_codes",
                            "routing_violations",
                            "routing_enforcement",
                        ],
                        "optional_runtime_evidence": [
                            "actual_model",
                            "actual_reasoning_effort",
                        ],
                        "limitation_field": "routing_limitation",
                    },
                },
            }
        )


class OptionalContextStage:
    def apply(self, state: PacketState) -> None:
        state = _require_packet_state(state)
        context = state.build_context.context
        output_delta_packet = output_delta_contract_packet(
            context,
            state.build_context.output_delta_contract_candidates,
        )
        if output_delta_packet:
            state.packet["output_delta_contract_packet"] = output_delta_packet
        session_audit = sanitize_collection_summary(
            context.get("session_audit"), max_packets=12
        )
        if session_audit:
            state.packet["session_audit"] = session_audit
        active_pack = deep_get(context, "task_state", "task_pack", "active_pack")
        if isinstance(active_pack, dict) and active_pack:
            state.packet["task_pack_packet"] = active_pack


class TargetSpecificationStage:
    def apply(self, state: PacketState) -> None:
        state = _require_packet_state(state)
        builder = TARGET_BUILDERS.get(state.target)
        if builder is not None:
            state.packet.update(builder(state.build_context))


class BootstrapDeriveStage:
    def apply(self, state: PacketState) -> None:
        state = _require_packet_state(state)
        if state.target != "derive" or state.workflow_mode != "bootstrap":
            return
        state.packet.update(
            {
                "mode": "initial_init",
                "workflow_mode": "bootstrap",
                "task": "task.md absent",
                "required_inputs": [
                    "task-absent context packet",
                    "authority_policy and used_goal_truth",
                    ".agent_goal goal architecture/theory/schema-contract evidence when present",
                    ".task/task_miss, candidate_task, and task_pack evidence when relevant",
                    "pre-derive schema reconciliation result or explicit skipped/not-applicable reason",
                ],
                "selection_rules": [
                    "derive exactly one initial task.md",
                    "write the required Execution Environment section",
                    "skip past_task archival because no prior task exists",
                    "do not emit acceptance, governance, run, validation, issue, promotion, commit, dashboard, or report evidence",
                    "finish schema-post-derive and index, then close the bootstrap transaction",
                    "start a fresh normal cycle from context and repo_skill_adapter_scan",
                ],
                "required_outputs": [
                    "step: derive",
                    "derive_mode: initial_init",
                    "next_task_id",
                    "selected_task_source: standalone",
                    "progress_kind",
                    "semantic_signature",
                    "evidence_paths",
                    "no fabricated completed_task_id",
                ],
            }
        )


_DEFAULT_PIPELINE: tuple[PacketStage, ...] = (
    BasePacketStage(),
    OptionalContextStage(),
    TargetSpecificationStage(),
    BootstrapDeriveStage(),
)


@dataclass(frozen=True)
class PacketBuilder:
    stages: tuple[PacketStage, ...] = _DEFAULT_PIPELINE

    def build(
        self,
        target: str,
        context: PacketBuildContext,
        workflow_mode: str,
        *,
        _legacy_v1_permit: object | None = None,
    ) -> dict[str, Any]:
        from .protocol import _validate_legacy_packet_permit

        _validate_legacy_packet_permit(
            _legacy_v1_permit,
            context.context,
            context.stage,
        )
        state = PacketState(
            target=target,
            workflow_mode=workflow_mode,
            build_context=context,
            _legacy_v1_permit=_legacy_v1_permit,
        )
        for stage in self.stages:
            stage.apply(state)
        return state.packet


__all__ = ["PacketBuilder"]
