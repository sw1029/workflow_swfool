from __future__ import annotations

from typing import Any

from ..result_contract.finalization import (
    extract_finalization_receipt,
    projection_from_result,
    verified_projection,
)
from .access import completed, first_value, status_for_step, step_event
from .bootstrap import bootstrap_binding_findings, explicit_task_absent
from .constants import (
    BOOTSTRAP_ORDER,
    BOOTSTRAP_TRANSITION_REQUIREMENTS,
    ORDER,
    ROUTING_REQUIRED_TARGETS,
    TRANSITION_REQUIREMENTS,
)
from .context import ValidationContext


def validate_workflow_and_required_order(state: ValidationContext) -> None:
    if state.workflow_mode not in {"normal", "bootstrap"}:
        raise ValueError(f"unsupported workflow mode: {state.workflow_mode}")
    requirements = _requirements(state)
    if (
        state.workflow_mode == "normal"
        and state.target_step in ROUTING_REQUIRED_TARGETS
        and not state.routing_source
    ):
        state.add(
            "block",
            "current_target_routing_packet_missing",
            "Agent-bearing normal-cycle transitions require an explicit current-target routing packet; accumulated stage routing is never reused.",
            {"target": state.target_step},
        )
    if state.transition not in requirements:
        state.add(
            "block",
            "transition_not_allowed_for_workflow_mode",
            f"`{state.transition}` is not allowed in `{state.workflow_mode}` workflow mode.",
            {"allowed_transitions": sorted(requirements)},
        )
    for step in requirements.get(state.transition, []):
        if not completed(state.stage, step):
            state.add(
                "block",
                "ordering_required_step_missing",
                f"{state.transition} requires completed step `{step}`.",
                {"step_status": status_for_step(state.stage, step)},
            )


def validate_finalization_receipt(state: ValidationContext) -> None:
    if state.workflow_mode != "normal" or state.transition not in {
        "pre_derive",
        "pre_dashboard",
        "pre_report",
        "pre_closeout_commit",
    }:
        return
    validate_event = step_event(state.stage, "validate")
    applicability = (
        str(validate_event.get("finalization_applicability") or "required")
        .strip()
        .lower()
    )
    if applicability == "not_applicable":
        transition_kind = (
            str(validate_event.get("transition_kind") or "").strip().lower()
        )
        reason = validate_event.get("finalization_not_applicable_reason")
        prior_final_attempt = validate_event.get("prior_final_attempt_exists")
        if (
            transition_kind
            not in {
                "standalone_repair",
                "unrelated_state_repair",
                "no_predecessor_attempt",
            }
            or not reason
            or prior_final_attempt is not False
        ):
            state.add(
                "block",
                "finalization_not_applicable_invalid",
                "Only a reasoned standalone/unrelated repair with no predecessor final attempt may bypass receipt consumption.",
            )
        return
    if applicability != "required":
        state.add(
            "block",
            "finalization_applicability_invalid",
            "Finalization applicability must be required or reasoned not_applicable.",
        )
        return
    if extract_finalization_receipt(validate_event) is None:
        state.add(
            "block",
            f"{state.transition}_finalization_receipt_missing",
            "Consumer transition requires the current content-bound finalization receipt from completion validation.",
        )
        return
    projection, _receipt, errors = verified_projection(validate_event, state.context)
    for item in errors:
        state.add(
            "block",
            str(item["code"]),
            str(item["message"]),
            item.get("evidence"),
        )
    declared = projection_from_result(validate_event)
    if projection is not None and declared is not None and declared != projection:
        state.add(
            "block",
            f"{state.transition}_authoritative_projection_mismatch",
            "Transition input disagrees with the current finalization snapshot projection.",
        )


def validate_anti_loop_handoff(state: ValidationContext) -> None:
    if state.workflow_mode != "normal" or state.transition != "pre_derive":
        return
    event = step_event(state.stage, "loopback_audit")
    handoff = event.get("anti_loop_handoff") or event.get("anti_loop_progress_handoff")
    gate = event.get("anti_loop_progress_gate")
    if (
        not isinstance(handoff, dict)
        and isinstance(gate, dict)
        and gate.get("applicability")
    ):
        handoff = gate
    version = _handoff_version(event, handoff, gate)
    if not isinstance(handoff, dict):
        explicit_legacy = str(version).strip() == "0"
        state.add(
            "warn" if explicit_legacy else "block",
            "pre_derive_anti_loop_handoff_legacy_unbound"
            if explicit_legacy
            else "pre_derive_anti_loop_handoff_missing",
            "Explicit legacy handoff version is unbound; current governed loopback events must emit a hash-bound required handoff before derive."
            if explicit_legacy
            else "Current governed loopback event is missing the required hash-bound handoff.",
        )
        return
    applicability = str(handoff.get("applicability") or "").strip().lower()
    if str(version).strip() not in {"0", "1"}:
        state.add(
            "block",
            "pre_derive_anti_loop_handoff_version_missing_or_invalid",
            "Current handoffs require version 1; legacy handoffs require explicit version 0.",
        )
    if str(version).strip() == "0":
        state.add(
            "warn",
            "pre_derive_anti_loop_handoff_explicit_legacy",
            "Explicit legacy handoff is unbound; emit a current hash-bound handoff on the next governed transition.",
        )
    elif applicability == "not_applicable":
        _validate_not_applicable_handoff(state, handoff)
    elif applicability != "required":
        state.add(
            "block",
            "pre_derive_anti_loop_handoff_not_required",
            "A normal governed post-loopback transition requires applicability=required.",
            {"applicability": applicability or None},
        )
    if str(version).strip() == "1" and applicability == "required":
        _validate_required_handoff(state, handoff)


def _handoff_version(event: dict[str, Any], handoff: Any, gate: Any) -> Any:
    if isinstance(handoff, dict):
        return handoff.get("handoff_contract_version")
    if isinstance(gate, dict):
        return gate.get("handoff_contract_version")
    return event.get("handoff_contract_version")


def _validate_not_applicable_handoff(
    state: ValidationContext,
    handoff: dict[str, Any],
) -> None:
    reason = handoff.get("not_applicable_reason") or handoff.get("applicability_reason")
    derive_mode = (
        str(
            handoff.get("derive_mode")
            or first_value(
                state.stage,
                "derive_mode",
                "transition_context.derive_mode",
                "packet.derive_mode",
            )
            or ""
        )
        .strip()
        .lower()
    )
    selected_source = (
        str(
            handoff.get("selected_task_source")
            or first_value(
                state.stage,
                "selected_task_source",
                "transition_context.selected_task_source",
                "packet.selected_task_source",
            )
            or ""
        )
        .strip()
        .lower()
    )
    prior_packet = bool(
        handoff.get("prior_packet_exists")
        or handoff.get("prior_packet_ref")
        or first_value(state.stage, "prior_loopback_packet_ref", "loopback_packet_ref")
    )
    if (
        (derive_mode != "initial_init" and selected_source != "standalone")
        or not reason
        or prior_packet
    ):
        state.add(
            "block",
            "pre_derive_anti_loop_handoff_not_applicable_invalid",
            "not_applicable requires a reasoned initial/standalone transition with no prior required loopback packet.",
        )


def _validate_required_handoff(
    state: ValidationContext,
    handoff: dict[str, Any],
) -> None:
    fields = (
        "packet_ref",
        "packet_sha256",
        "artifact_id",
        "artifact_sha256",
        "artifact_family",
        "blocker_signature",
        "progress_verdict",
        "allowed_next_action_classes",
    )
    missing = [field for field in fields if handoff.get(field) in (None, "", [])]
    if missing:
        state.add(
            "block",
            "pre_derive_anti_loop_handoff_incomplete",
            "Normal pre-derive handoff is missing decision identity/action fields.",
            {"missing_fields": missing},
        )


def validate_ordering_gaps_and_bootstrap(state: ValidationContext) -> None:
    active_order = BOOTSTRAP_ORDER if state.workflow_mode == "bootstrap" else ORDER
    required = _requirements(state).get(state.transition, [])
    completed_steps = [step for step in active_order if completed(state.stage, step)]
    if completed_steps:
        latest_idx = max(active_order.index(step) for step in completed_steps)
        for earlier in active_order[:latest_idx]:
            if earlier in {"schema_pre_derive", "schema_post_derive"}:
                continue
            if not completed(state.stage, earlier) and earlier in required:
                state.add(
                    "block",
                    "ordering_gap",
                    f"Later step completed before required `{earlier}` was complete.",
                    {"completed_steps": completed_steps},
                )
    if state.workflow_mode == "bootstrap" and state.transition == "bootstrap_complete":
        if not explicit_task_absent(state.context):
            state.add(
                "block",
                "bootstrap_task_absent_premise_missing",
                "Bootstrap completion requires explicit context evidence that task.md was absent when the transaction began.",
            )
        state.findings.extend(bootstrap_binding_findings(state.stage))


def _requirements(state: ValidationContext) -> dict[str, list[str]]:
    if state.workflow_mode == "bootstrap":
        return BOOTSTRAP_TRANSITION_REQUIREMENTS
    return TRANSITION_REQUIREMENTS
