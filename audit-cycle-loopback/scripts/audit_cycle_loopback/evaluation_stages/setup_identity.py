from __future__ import annotations

from ..runtime_dependencies import (
    Any,
    consumer_context_conformance_gate,
    content_bound_attempt_identity,
    decision_input_state_fingerprint,
    normalize_root_family_key,
)

from ..evaluation_frame import _EvaluationFrame


def _adapter_consumer_declaration(
    adapter_scan_handoff: dict[str, Any],
    *,
    adapter_registered: bool,
    consumer_id: str,
    scan_supplied: bool,
) -> tuple[list[str], str]:
    status = str(adapter_scan_handoff.get("status") or "").strip().lower()
    raw_ids = adapter_scan_handoff.get("required_consumer_ids")
    if status == "ready" and isinstance(raw_ids, list):
        ids = [str(item).strip() for item in raw_ids if str(item).strip()]
        if len(ids) == len(raw_ids) and len(set(ids)) == len(ids) and consumer_id in ids:
            return ids, "manifest_v2"
        return [consumer_id], "scan_contract_invalid"
    if scan_supplied:
        return [consumer_id], "scan_unavailable"
    if adapter_registered:
        return [consumer_id], "legacy_explicit_adapter"
    return [], "not_applicable"


def _prepare_initial_identity(frame: _EvaluationFrame) -> None:
    (
        adapter_registered, adapter_revision_sha256, adapter_scan_handoff, args,
        decision_artifact_ref, gate_inputs, output_delta, quality, runner_validation,
    ) = frame.require(
        'adapter_registered', 'adapter_revision_sha256', 'adapter_scan_handoff',
        'args', 'decision_artifact_ref', 'gate_inputs', 'output_delta', 'quality',
        'runner_validation',
    )
    consumer_id = "audit-cycle-loopback"
    required_consumer_ids, adapter_consumer_contract_mode = (
        _adapter_consumer_declaration(
            adapter_scan_handoff,
            adapter_registered=adapter_registered,
            consumer_id=consumer_id,
            scan_supplied=bool(getattr(args, "adapter_scan_json", None)),
        )
    )
    input_state_fingerprint = decision_input_state_fingerprint(
        [
            runner_validation,
            output_delta,
            quality,
            *gate_inputs,
            {"adapter_revision_sha256": adapter_revision_sha256},
        ],
        decision_artifact_ref,
    )
    attempt_identity = content_bound_attempt_identity(
        args.cycle_id,
        normalize_root_family_key(args.artifact_family),
        "pending",
        input_state_fingerprint,
    )
    declared_consumer_context = consumer_context_conformance_gate(
        {"required_consumer_ids": required_consumer_ids},
        runner_validation,
        output_delta,
        *gate_inputs,
        expected_artifact_ref=decision_artifact_ref,
        expected_cycle_id=args.cycle_id,
        expected_input_state_fingerprint=input_state_fingerprint,
        expected_attempt_identity=attempt_identity,
        expected_task_id=args.task_id,
        expected_adapter_revision_sha256=adapter_revision_sha256,
    )
    consumer_conformance_gate = consumer_context_conformance_gate(
        {"required_consumer_ids": declared_consumer_context.get("required_consumer_ids") or []},
        runner_validation,
        expected_artifact_ref=decision_artifact_ref,
        expected_cycle_id=args.cycle_id,
        expected_input_state_fingerprint=input_state_fingerprint,
        expected_attempt_identity=attempt_identity,
        expected_task_id=args.task_id,
        expected_adapter_revision_sha256=adapter_revision_sha256,
    )
    self_consumer_probe_pending = False
    self_consumer_required = False
    self_consumer_probe_row: dict[str, Any] | None = None
    artifact_echo_valid = False
    invocation_completed = False
    rows: list[dict[str, Any]] = []
    frame.update({
        "adapter_consumer_contract_mode": adapter_consumer_contract_mode,
        "artifact_echo_valid": artifact_echo_valid,
        "attempt_identity": attempt_identity,
        "consumer_conformance_gate": consumer_conformance_gate,
        "consumer_id": consumer_id,
        "declared_consumer_context": declared_consumer_context,
        "input_state_fingerprint": input_state_fingerprint,
        "invocation_completed": invocation_completed,
        "rows": rows,
        "required_consumer_ids": required_consumer_ids,
        "self_consumer_probe_pending": self_consumer_probe_pending,
        "self_consumer_probe_row": self_consumer_probe_row,
        "self_consumer_required": self_consumer_required,
    })
