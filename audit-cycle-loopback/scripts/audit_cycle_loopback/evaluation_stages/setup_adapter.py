from __future__ import annotations

from ..runtime_dependencies import (
    Any,
    adapter_wiring_gate,
    apply_gate_artifact_compatibility,
    gate_artifact_compatibility_result,
    rel_path,
)

from ..evaluation_frame import _EvaluationFrame


def _prepare_adapter_state(frame: _EvaluationFrame) -> None:
    (
        adapter_expected_path, adapter_registered, decision_artifact_ref, domain_adapter,
        domain_adapter_error, domain_adapter_path, paths, root,
    ) = frame.require(
        'adapter_expected_path', 'adapter_registered', 'decision_artifact_ref',
        'domain_adapter', 'domain_adapter_error', 'domain_adapter_path', 'paths', 'root',
    )
    adapter_load_gate = adapter_wiring_gate(
        registered=adapter_registered,
        loaded=domain_adapter is not None,
        expected_path=adapter_expected_path,
        loaded_path=domain_adapter_path,
        load_error=domain_adapter_error,
    )
    hook_demand_events: list[dict[str, Any]] = []
    gate_compatibility_results: list[dict[str, Any]] = []

    def bind_artifact_gate(
        gate_id: str,
        gate: dict[str, Any],
        *,
        pass_fields: tuple[str, ...] = (),
        computed_from_decision_artifact: bool = False,
    ) -> dict[str, Any]:
        if computed_from_decision_artifact and decision_artifact_ref.get("artifact_class"):
            gate = dict(gate)
            gate.setdefault("required_artifact_class", decision_artifact_ref["artifact_class"])
        compatibility = gate_artifact_compatibility_result(
            domain_adapter,
            gate_id,
            decision_artifact_ref,
            gate,
            root=root,
            artifact_paths=[rel_path(root, path) for path in paths],
        )
        gate_compatibility_results.append(compatibility)
        return apply_gate_artifact_compatibility(gate, compatibility, pass_fields=pass_fields)

    def record_adapter_hook_demand(hook_id: str, affected_gate_id: str, *, decision_relevant_skip: bool) -> None:
        if domain_adapter is None or hasattr(domain_adapter, hook_id):
            return
        hook_demand_events.append(
            {
                "hook_id": hook_id,
                "affected_gate_id": affected_gate_id,
                "decision_relevant_skip": bool(decision_relevant_skip),
            }
        )

    def adapter_hook_value_supplied(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, (dict, list, tuple, set, str)):
            return bool(value)
        return True
    frame.update({
        "adapter_hook_value_supplied": adapter_hook_value_supplied,
        "adapter_load_gate": adapter_load_gate,
        "bind_artifact_gate": bind_artifact_gate,
        "gate_compatibility_results": gate_compatibility_results,
        "hook_demand_events": hook_demand_events,
        "record_adapter_hook_demand": record_adapter_hook_demand,
    })
