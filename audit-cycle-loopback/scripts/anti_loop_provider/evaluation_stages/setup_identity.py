from __future__ import annotations

from ..runtime_dependencies import (
    Any,
    consumer_context_conformance_gate,
    content_bound_attempt_identity,
    decision_input_state_fingerprint,
    normalize_root_family_key,
)

from ..evaluation_frame import _EvaluationFrame


def _prepare_initial_identity(frame: _EvaluationFrame) -> None:
    (
        args, decision_artifact_ref, gate_inputs, output_delta, quality, runner_validation,
    ) = frame.require(
        'args', 'decision_artifact_ref', 'gate_inputs', 'output_delta', 'quality',
        'runner_validation',
    )
    input_state_fingerprint = decision_input_state_fingerprint(
        [runner_validation, output_delta, quality, *gate_inputs],
        decision_artifact_ref,
    )
    attempt_identity = content_bound_attempt_identity(
        args.cycle_id,
        normalize_root_family_key(args.artifact_family),
        "pending",
        input_state_fingerprint,
    )
    declared_consumer_context = consumer_context_conformance_gate(
        runner_validation,
        output_delta,
        *gate_inputs,
        expected_artifact_ref=decision_artifact_ref,
        expected_cycle_id=args.cycle_id,
        expected_input_state_fingerprint=input_state_fingerprint,
        expected_attempt_identity=attempt_identity,
    )
    consumer_conformance_gate = consumer_context_conformance_gate(
        {"required_consumer_ids": declared_consumer_context.get("required_consumer_ids") or []},
        runner_validation,
        expected_artifact_ref=decision_artifact_ref,
        expected_cycle_id=args.cycle_id,
        expected_input_state_fingerprint=input_state_fingerprint,
        expected_attempt_identity=attempt_identity,
    )
    self_consumer_probe_pending = False
    self_consumer_required = False
    self_consumer_probe_row: dict[str, Any] | None = None
    artifact_echo_valid = False
    invocation_completed = False
    rows: list[dict[str, Any]] = []
    consumer_id = "audit-cycle-loopback"
    frame.update({
        "artifact_echo_valid": artifact_echo_valid,
        "attempt_identity": attempt_identity,
        "consumer_conformance_gate": consumer_conformance_gate,
        "consumer_id": consumer_id,
        "declared_consumer_context": declared_consumer_context,
        "input_state_fingerprint": input_state_fingerprint,
        "invocation_completed": invocation_completed,
        "rows": rows,
        "self_consumer_probe_pending": self_consumer_probe_pending,
        "self_consumer_probe_row": self_consumer_probe_row,
        "self_consumer_required": self_consumer_required,
    })
