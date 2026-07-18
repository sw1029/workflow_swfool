from __future__ import annotations

from ..runtime_dependencies import (
    consumer_context_conformance_gate,
    consumer_receipt_binding_sha256,
    string_list,
)
from ..decision_identity_binding import (
    decision_identity_echo,
    explicit_identity,
    explicit_identity_mismatches,
)

from ..evaluation_frame import _EvaluationFrame


def _prepare_consumer_probe(frame: _EvaluationFrame) -> None:
    (
        adapter_load_gate, adapter_registered, adapter_revision_sha256, args,
        artifact_echo_valid, attempt_identity,
        consumer_conformance_gate, consumer_id, decision_artifact_ref, domain_adapter,
        input_state_fingerprint, invocation_completed, quality, quality_hook_receipt, rows,
        self_consumer_probe_pending, self_consumer_probe_row, self_consumer_required,
    ) = frame.require(
        'adapter_load_gate', 'adapter_registered', 'adapter_revision_sha256', 'args', 'artifact_echo_valid',
        'attempt_identity', 'consumer_conformance_gate', 'consumer_id',
        'decision_artifact_ref', 'domain_adapter', 'input_state_fingerprint',
        'invocation_completed', 'quality', 'quality_hook_receipt', 'rows',
        'self_consumer_probe_pending', 'self_consumer_probe_row', 'self_consumer_required',
    )
    if adapter_registered:
        quality_hook = getattr(domain_adapter, "quality_vector", None) if domain_adapter is not None else None
        required_ids = list(consumer_conformance_gate.get("required_consumer_ids") or [])
        self_consumer_required = consumer_id in required_ids
        self_consumer_probe_pending = self_consumer_required or bool(
            decision_artifact_ref.get("scope_verified") and callable(quality_hook)
        )
        expected_verification_ids = sorted(
            str(item) for item in string_list(decision_artifact_ref.get("verification_input_ids"))
        )
        observed_verification_ids = sorted(
            str(item) for item in string_list(quality.get("verification_input_ids"))
        )
        expected_explicit_identity = explicit_identity(decision_artifact_ref)
        observed_identity_echo = decision_identity_echo(quality)
        if expected_explicit_identity is not None:
            artifact_echo_valid = bool(
                decision_artifact_ref.get("scope_verified")
                and not explicit_identity_mismatches(quality, decision_artifact_ref)
            )
        else:
            artifact_echo_valid = bool(
                decision_artifact_ref.get("scope_verified")
                and str(quality.get("artifact_id") or "") == str(decision_artifact_ref.get("artifact_id") or "")
                and str(quality.get("artifact_sha256") or quality.get("output_sha256") or "").lower()
                == str(decision_artifact_ref.get("artifact_sha256") or "").lower()
                and str(quality.get("production_lane_identity") or "")
                == str(decision_artifact_ref.get("production_lane_identity") or "")
                and (
                    not decision_artifact_ref.get("body_projection_fingerprint")
                    or quality.get("body_projection_fingerprint")
                    == decision_artifact_ref.get("body_projection_fingerprint")
                )
                and (
                    decision_artifact_ref.get("verification_input_ids") is None
                    or observed_verification_ids == expected_verification_ids
                )
                and (
                    decision_artifact_ref.get("input_fingerprints") is None
                    or quality.get("input_fingerprints") == decision_artifact_ref.get("input_fingerprints")
                )
            )
        invocation_completed = bool(quality_hook_receipt.get("invocation_completed"))
        if self_consumer_probe_pending:
            probe_row = {
                "consumer_context_id": consumer_id,
                "hook_id": "quality_vector",
                "adapter_loaded": domain_adapter is not None,
                "hook_resolved": bool(quality_hook_receipt.get("hook_resolved")),
                "required_hook_callable": callable(quality_hook),
                "hook_signature_compatible": bool(quality_hook_receipt.get("hook_signature_compatible")),
                "invocation_completed": invocation_completed,
                "invocation_status": "completed" if invocation_completed else "not_evaluated",
                "return_contract_valid": bool(quality_hook_receipt.get("return_contract_valid")),
                "return_contract_status": "pass" if quality_hook_receipt.get("return_contract_valid") else "not_evaluated",
                "artifact_identity_echo_valid": artifact_echo_valid,
                "artifact_identity_echo_status": "pass" if artifact_echo_valid else "not_evaluated",
                "cycle_id": args.cycle_id,
                "task_id": args.task_id,
                "input_state_fingerprint": input_state_fingerprint,
                "attempt_identity": attempt_identity,
                "adapter_revision_sha256": adapter_revision_sha256,
                "artifact_id": quality.get("artifact_id"),
                "artifact_sha256": quality.get("artifact_sha256") or quality.get("output_sha256"),
                "production_lane_identity": quality.get("production_lane_identity"),
                "body_projection_fingerprint": quality.get("body_projection_fingerprint"),
                "verification_input_ids": observed_verification_ids,
                "input_fingerprints": quality.get("input_fingerprints"),
                "decision_identity_echo": observed_identity_echo,
                "evidence_provenance": "self_grounded",
                "value_consumed_by_decision": False,
                "decision_consumption_status": "not_evaluated",
                "probe_evidence_ref": f"packet:consumer_context_conformance/{consumer_id}",
                "status": "pending_decision_consumption",
            }
            probe_sha256 = consumer_receipt_binding_sha256(probe_row)
            probe_row["probe_evidence_id"] = "probe-" + probe_sha256[:16]
            probe_row["probe_evidence_sha256"] = probe_sha256
            self_consumer_probe_row = dict(probe_row)
            if consumer_id not in required_ids:
                if self_consumer_required:
                    required_ids.append(consumer_id)
            rows = [row for row in consumer_conformance_gate.get("rows") or [] if row.get("consumer_context_id") != consumer_id]
            rows.append(probe_row)
            consumer_conformance_gate = consumer_context_conformance_gate(
                {
                    "required_consumer_ids": required_ids,
                    "consumer_context_conformance": {"rows": rows},
                },
                expected_artifact_ref=decision_artifact_ref,
                expected_cycle_id=args.cycle_id,
                expected_input_state_fingerprint=input_state_fingerprint,
                expected_attempt_identity=attempt_identity,
                expected_task_id=args.task_id,
                expected_adapter_revision_sha256=adapter_revision_sha256,
            )
    adapter_load_gate["consumer_context_conformance"] = consumer_conformance_gate
    frame.update({
        "artifact_echo_valid": artifact_echo_valid,
        "consumer_conformance_gate": consumer_conformance_gate,
        "invocation_completed": invocation_completed,
        "rows": rows,
        "self_consumer_probe_pending": self_consumer_probe_pending,
        "self_consumer_probe_row": self_consumer_probe_row,
    })
