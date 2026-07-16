"""Artifact-to-gate compatibility policy."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .values import bool_value
from .vectors import string_list


AdapterCaller = Callable[..., tuple[Any, str | None]]


@dataclass(frozen=True)
class CompatibilityState:
    adapter: Any | None
    gate_id: str
    artifact_ref: dict[str, Any]
    gate: dict[str, Any]
    artifact_class: str
    base: dict[str, Any]
    hook_resolved: bool
    hook_signature_compatible: bool
    hook_value: Any
    hook_error: str | None


def _hook_signature_compatible(hook: Any, kwargs: dict[str, Any]) -> bool:
    if not callable(hook):
        return False
    try:
        signature = inspect.signature(hook)
        accepts_kwargs = any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values()
        )
        accepted = (
            kwargs
            if accepts_kwargs
            else {key: value for key, value in kwargs.items() if key in signature.parameters}
        )
        signature.bind(**accepted)
        return accepts_kwargs or "artifact_ref" in signature.parameters
    except (TypeError, ValueError):
        return False


def _build_state(
    adapter: Any | None,
    gate_id: str,
    artifact_ref: dict[str, Any],
    gate: dict[str, Any],
    context: dict[str, Any],
    call_adapter: AdapterCaller,
) -> CompatibilityState:
    artifact_class = str(artifact_ref.get("artifact_class") or "").strip()
    base = {
        "gate_id": gate_id,
        "artifact_id": artifact_ref.get("artifact_id"),
        "artifact_sha256": artifact_ref.get("artifact_sha256"),
    }
    hook = (
        getattr(adapter, "gate_artifact_compatibility", None)
        if adapter is not None
        else None
    )
    hook_resolved = callable(hook)
    hook_kwargs = {
        "artifact_class": artifact_class,
        "gate_id": gate_id,
        "artifact_ref": artifact_ref,
        "gate": gate,
        **context,
    }
    signature_compatible = _hook_signature_compatible(hook, hook_kwargs)
    hook_value, hook_error = (
        call_adapter(adapter, "gate_artifact_compatibility", **hook_kwargs)
        if signature_compatible
        else (
            None,
            "gate_artifact_compatibility_signature_incompatible"
            if hook_resolved
            else None,
        )
    )
    return CompatibilityState(
        adapter=adapter,
        gate_id=gate_id,
        artifact_ref=artifact_ref,
        gate=gate,
        artifact_class=artifact_class,
        base=base,
        hook_resolved=hook_resolved,
        hook_signature_compatible=signature_compatible,
        hook_value=hook_value,
        hook_error=hook_error,
    )


def _valid_hook_result(state: CompatibilityState) -> dict[str, Any]:
    hook_value = state.hook_value
    echoed_id = str(hook_value.get("artifact_id") or "")
    echoed_sha = str(hook_value.get("artifact_sha256") or "").lower()
    identity_echo_valid = bool(
        echoed_id
        and echoed_sha
        and echoed_id == str(state.artifact_ref.get("artifact_id") or "")
        and echoed_sha
        == str(state.artifact_ref.get("artifact_sha256") or "").lower()
    )
    receipt = {
        "consumer_context_id": f"gate_artifact_compatibility:{state.gate_id}",
        "adapter_loaded": state.adapter is not None,
        "hook_resolved": state.hook_resolved,
        "required_hook_callable": state.hook_resolved,
        "hook_signature_compatible": state.hook_signature_compatible,
        "invocation_completed": state.hook_signature_compatible
        and state.hook_error is None,
        "return_contract_valid": True,
        "artifact_identity_echo_valid": identity_echo_valid,
        "value_consumed_by_decision": identity_echo_valid,
        "status": "pass" if identity_echo_valid else "not_evaluated",
    }
    if not identity_echo_valid:
        return {
            **state.base,
            "gate_compatibility_status": "not_evaluated",
            "compatibility_basis": "adapter_hook_identity_echo_invalid",
            "compatibility_evidence_ref": hook_value.get("evidence_ref"),
            "consumer_invocation_receipt": receipt,
        }
    return {
        **state.base,
        "gate_compatibility_status": "compatible"
        if hook_value["compatible"]
        else "incompatible",
        "compatibility_basis": "adapter_hook",
        "compatibility_evidence_ref": hook_value.get("evidence_ref"),
        "unmet_precondition": hook_value.get("unmet_precondition"),
        "consumer_invocation_receipt": receipt,
    }


def _invalid_hook_result(state: CompatibilityState) -> dict[str, Any]:
    return {
        **state.base,
        "gate_compatibility_status": "not_evaluated",
        "compatibility_basis": "hook_error"
        if state.hook_error
        else "adapter_hook_return_contract_invalid",
        "compatibility_evidence_ref": None,
        "compatibility_error": state.hook_error,
        "consumer_invocation_receipt": {
            "consumer_context_id": f"gate_artifact_compatibility:{state.gate_id}",
            "hook_id": "gate_artifact_compatibility",
            "adapter_loaded": state.adapter is not None,
            "hook_resolved": True,
            "required_hook_callable": True,
            "hook_signature_compatible": state.hook_signature_compatible,
            "invocation_completed": state.hook_signature_compatible
            and state.hook_error is None,
            "return_contract_valid": False,
            "artifact_identity_echo_valid": False,
            "value_consumed_by_decision": False,
            "status": "not_evaluated",
        },
    }


def _static_or_unmapped_result(state: CompatibilityState) -> dict[str, Any]:
    supported = string_list(
        state.gate.get("supported_artifact_classes")
        or state.gate.get("artifact_classes")
    )
    required_class = str(
        state.gate.get("required_artifact_class")
        or state.gate.get("artifact_class")
        or ""
    ).strip()
    if supported or required_class:
        compatible = (
            state.artifact_class in supported
            if supported
            else state.artifact_class == required_class
        )
        return {
            **state.base,
            "gate_compatibility_status": "compatible" if compatible else "incompatible",
            "compatibility_basis": "gate_static_mapping",
            "compatibility_evidence_ref": state.gate.get(
                "compatibility_evidence_ref"
            ),
        }
    return {
        **state.base,
        "gate_compatibility_status": "not_evaluated",
        "compatibility_basis": "hook_error"
        if state.hook_error
        else "mapping_not_supplied",
        "compatibility_evidence_ref": None,
        "compatibility_error": state.hook_error,
        "consumer_invocation_receipt": {
            "consumer_context_id": f"gate_artifact_compatibility:{state.gate_id}",
            "adapter_loaded": state.adapter is not None,
            "hook_resolved": state.hook_resolved,
            "required_hook_callable": state.hook_resolved,
            "hook_signature_compatible": state.hook_signature_compatible,
            "invocation_completed": bool(
                state.hook_signature_compatible and state.hook_error is None
            ),
            "return_contract_valid": False,
            "artifact_identity_echo_valid": False,
            "value_consumed_by_decision": False,
            "status": "not_evaluated",
        },
    }


def gate_artifact_compatibility_result(
    adapter: Any | None,
    gate_id: str,
    artifact_ref: dict[str, Any],
    gate: dict[str, Any] | None,
    context: dict[str, Any],
    *,
    call_adapter: AdapterCaller,
) -> dict[str, Any]:
    gate = gate or {}
    base = {
        "gate_id": gate_id,
        "artifact_id": artifact_ref.get("artifact_id"),
        "artifact_sha256": artifact_ref.get("artifact_sha256"),
    }
    if not bool_value(artifact_ref.get("scope_verified")):
        return {
            **base,
            "gate_compatibility_status": "not_evaluated",
            "compatibility_basis": "artifact_identity_not_verified",
            "compatibility_evidence_ref": None,
        }
    state = _build_state(
        adapter, gate_id, artifact_ref, gate, context, call_adapter
    )
    if isinstance(state.hook_value, dict) and isinstance(
        state.hook_value.get("compatible"), bool
    ):
        return _valid_hook_result(state)
    if state.hook_resolved:
        return _invalid_hook_result(state)
    return _static_or_unmapped_result(state)


def apply_gate_artifact_compatibility(
    gate: dict[str, Any],
    compatibility: dict[str, Any],
    *,
    pass_fields: tuple[str, ...] = (),
) -> dict[str, Any]:
    updated = dict(gate)
    status = str(compatibility.get("gate_compatibility_status") or "not_evaluated")
    updated["gate_compatibility"] = compatibility
    updated["gate_compatibility_status"] = status
    updated["decision_contribution_allowed"] = status == "compatible"
    if status != "compatible":
        updated["observed_evaluation_status"] = updated.get(
            "evaluation_status"
        ) or updated.get("status")
        updated["evaluation_status"] = "not_evaluated"
        updated["constrains_disposition"] = False
        updated["hard_stop_required"] = False
        for field in pass_fields:
            if field in updated:
                updated[field] = False
    return updated
