from __future__ import annotations

from ..runtime_dependencies import (
    bool_value,
    consumer_context_conformance_gate,
    consumer_receipt_binding_sha256,
)

from ..evaluation_frame import _EvaluationFrame


def _evaluate_failure_consumer(frame: _EvaluationFrame) -> None:
    (
        adapter_load_gate, adapter_revision_sha256, args, artifact_echo_valid,
        attempt_identity, bind_artifact_gate,
        consumer_conformance_gate, consumer_id, coverage_gate, decision_artifact_ref,
        independent_coverage_fields, independent_substance_fields, input_state_fingerprint,
        invocation_completed, quality_hook_receipt, rows, self_consumer_probe_pending,
        self_consumer_probe_row, substance_gate,
    ) = frame.require(
        'adapter_load_gate', 'adapter_revision_sha256', 'args', 'artifact_echo_valid', 'attempt_identity',
        'bind_artifact_gate', 'consumer_conformance_gate', 'consumer_id', 'coverage_gate',
        'decision_artifact_ref', 'independent_coverage_fields', 'independent_substance_fields',
        'input_state_fingerprint', 'invocation_completed', 'quality_hook_receipt', 'rows',
        'self_consumer_probe_pending', 'self_consumer_probe_row', 'substance_gate',
    )
    substance_gate = bind_artifact_gate(
        "substance_delta_gate",
        substance_gate,
        pass_fields=("substance_delta_pass",),
        computed_from_decision_artifact=True,
    )
    if not bool_value(coverage_gate.get("decision_contribution_allowed")):
        coverage_gate["incompatible_or_unverified_observed_fields"] = list(independent_coverage_fields)
        independent_coverage_fields = []
    if not bool_value(substance_gate.get("decision_contribution_allowed")):
        substance_gate["incompatible_or_unverified_observed_fields"] = list(independent_substance_fields)
        independent_substance_fields = []
    if self_consumer_probe_pending:
        invocation_receipt_valid = bool(
            invocation_completed
            and quality_hook_receipt.get("return_contract_valid")
            and artifact_echo_valid
        )
        if not invocation_receipt_valid:
            coverage_gate["consumer_invocation_status"] = "not_evaluated"
            coverage_gate["decision_contribution_allowed"] = False
            coverage_gate["quality_delta_pass"] = False
            coverage_gate["evaluation_status"] = "not_evaluated"
            coverage_gate["constrains_disposition"] = False
            independent_coverage_fields = []
        decision_consumed = bool(
            invocation_receipt_valid
            and bool_value(coverage_gate.get("decision_contribution_allowed"))
        )
        rows = []
        for receipt in consumer_conformance_gate.get("rows") or []:
            if receipt.get("consumer_context_id") != consumer_id:
                rows.append(receipt)
                continue
            receipt = dict(receipt)
            receipt["value_consumed_by_decision"] = decision_consumed
            receipt["decision_consumption_status"] = "pass" if decision_consumed else "not_evaluated"
            receipt["status"] = "pass" if decision_consumed else "not_evaluated"
            receipt_sha256 = consumer_receipt_binding_sha256(receipt)
            receipt["probe_evidence_id"] = "probe-" + receipt_sha256[:16]
            receipt["probe_evidence_sha256"] = receipt_sha256
            rows.append(receipt)
        if self_consumer_probe_row is not None:
            self_consumer_probe_row = dict(self_consumer_probe_row)
            self_consumer_probe_row["value_consumed_by_decision"] = decision_consumed
            self_consumer_probe_row["decision_consumption_status"] = "pass" if decision_consumed else "not_evaluated"
            self_consumer_probe_row["status"] = "pass" if decision_consumed else "not_evaluated"
            receipt_sha256 = consumer_receipt_binding_sha256(self_consumer_probe_row)
            self_consumer_probe_row["probe_evidence_id"] = "probe-" + receipt_sha256[:16]
            self_consumer_probe_row["probe_evidence_sha256"] = receipt_sha256
        consumer_conformance_gate = consumer_context_conformance_gate(
            {
                "required_consumer_ids": consumer_conformance_gate.get("required_consumer_ids") or [],
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
        "independent_coverage_fields": independent_coverage_fields,
        "independent_substance_fields": independent_substance_fields,
        "self_consumer_probe_row": self_consumer_probe_row,
        "substance_gate": substance_gate,
    })
