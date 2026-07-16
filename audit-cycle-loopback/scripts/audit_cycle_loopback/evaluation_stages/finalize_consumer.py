from __future__ import annotations

from ..runtime_dependencies import (
    Any,
    bool_value,
    consumer_context_conformance_gate,
    consumer_receipt_binding_sha256,
)

from ..evaluation_frame import _EvaluationFrame


def _finalize_consumer_conformance(frame: _EvaluationFrame) -> None:
    (
        adapter_load_gate, args, attempt_identity, decision_artifact_ref,
        declared_consumer_context, disposition, gate_inputs, hard_stop,
        identity_gate_inputs, input_state_fingerprint, output_delta, runner_validation,
        self_consumer_probe_row,
    ) = frame.require(
        "adapter_load_gate", "args", "attempt_identity", "decision_artifact_ref",
        "declared_consumer_context", "disposition", "gate_inputs", "hard_stop",
        "identity_gate_inputs", "input_state_fingerprint", "output_delta",
        "runner_validation", "self_consumer_probe_row",
    )
    if self_consumer_probe_row is not None:
        self_consumer_probe_row = dict(self_consumer_probe_row)
        self_consumer_probe_row["input_state_fingerprint"] = input_state_fingerprint
        self_consumer_probe_row["attempt_identity"] = attempt_identity
        receipt_sha256 = consumer_receipt_binding_sha256(self_consumer_probe_row)
        self_consumer_probe_row["probe_evidence_id"] = "probe-" + receipt_sha256[:16]
        self_consumer_probe_row["probe_evidence_sha256"] = receipt_sha256
    final_conformance_inputs: list[Any] = [
        {
            "required_consumer_ids": declared_consumer_context.get("required_consumer_ids") or [],
        },
        runner_validation,
        output_delta,
        *identity_gate_inputs,
    ]
    if self_consumer_probe_row is not None:
        final_conformance_inputs.append(
            {
                "consumer_context_conformance": {
                    "rows": [self_consumer_probe_row],
                }
            }
        )
    consumer_conformance_gate = consumer_context_conformance_gate(
        *final_conformance_inputs,
        expected_artifact_ref=decision_artifact_ref,
        expected_cycle_id=args.cycle_id,
        expected_input_state_fingerprint=input_state_fingerprint,
        expected_attempt_identity=attempt_identity,
    )
    adapter_load_gate["consumer_context_conformance"] = consumer_conformance_gate
    if bool_value(consumer_conformance_gate.get("missing_consumer_context_ids")):
        adapter_load_gate["status"] = "block"
        adapter_load_gate["constrains_disposition"] = True
        adapter_load_gate["adapter_wiring_defect"] = True
    matching_adapter_gate = next(
        (item for item in gate_inputs if item.get("name") == "adapter_wiring_gate"),
        None,
    )
    if matching_adapter_gate is not None:
        matching_adapter_gate.update(adapter_load_gate)
    elif bool_value(adapter_load_gate.get("adapter_wiring_defect")):
        gate_inputs.append({"name": "adapter_wiring_gate", **adapter_load_gate})
    if bool_value(adapter_load_gate.get("adapter_wiring_defect")):
        hard_stop = True
        disposition = "self_inflicted_gate_defect"
    frame.update({
        "consumer_conformance_gate": consumer_conformance_gate,
        "disposition": disposition,
        "hard_stop": hard_stop,
        "self_consumer_probe_row": self_consumer_probe_row,
    })
