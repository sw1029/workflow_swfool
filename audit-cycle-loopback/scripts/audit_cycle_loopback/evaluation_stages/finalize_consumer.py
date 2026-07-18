from __future__ import annotations

from ..runtime_dependencies import (
    Any,
    adapter_invocation_receipts,
    bool_value,
    consumer_context_conformance_gate,
    consumer_receipt_binding_sha256,
)
from ..consumer_receipt_contract import (
    CONSUMER_RECEIPT_CONTRACT_VERSION,
    CONSUMER_REVISION_SHA256,
    VALIDATOR_SIGNATURE_SHA256,
)

from ..evaluation_frame import _EvaluationFrame


def _decision_consumed_hook_ids(
    hook_io_receipts: list[dict[str, Any]],
) -> set[str]:
    return {
        str(item.get("hook_id"))
        for item in hook_io_receipts
        if item.get("status") == "completed"
        and item.get("return_contract_valid") is True
        and item.get("semantic_status") == "accepted"
        and item.get("value_consumed_by_decision") is True
        and item.get("hook_id")
    }


def _acceptance_required_hook_ids(
    hook_io_receipts: list[dict[str, Any]],
) -> set[str]:
    return {
        str(item.get("hook_id"))
        for item in hook_io_receipts
        if item.get("acceptance_required") is True and item.get("hook_id")
    }


def _self_consumer_wiring_conformant(
    row: dict[str, Any] | None,
    conformance_gate: dict[str, Any],
) -> bool:
    """Separate a sound consumer invocation from decision-identity failure."""

    if not isinstance(row, dict):
        return False
    consumer_id = str(row.get("consumer_context_id") or "").strip()
    normalized = next(
        (
            item
            for item in conformance_gate.get("rows") or []
            if isinstance(item, dict) and item.get("consumer_context_id") == consumer_id
        ),
        {},
    )
    required_flags = (
        "adapter_loaded",
        "hook_resolved",
        "required_hook_callable",
        "hook_signature_compatible",
        "invocation_completed",
        "return_contract_valid",
        "value_consumed_by_decision",
    )
    return bool(
        consumer_id
        and all(row.get(field) is True for field in required_flags)
        and row.get("result_contract_status") == "conformant"
        and normalized.get("coverage_status") == "conformant"
        and not normalized.get("coverage_mismatched_fields")
        and not normalized.get("excluded_required_gate_ids")
        and str(row.get("evidence_provenance") or "").strip().lower()
        in {"independently_verified", "self_grounded"}
        and row.get("probe_evidence_sha256") == consumer_receipt_binding_sha256(row)
    )


def _missing_context_is_wiring_defect(
    conformance_gate: dict[str, Any],
    self_consumer_row: dict[str, Any] | None,
) -> bool:
    missing = {
        str(item)
        for item in conformance_gate.get("missing_consumer_context_ids") or []
        if str(item).strip()
    }
    if not missing:
        return False
    self_id = str((self_consumer_row or {}).get("consumer_context_id") or "").strip()
    return not (
        missing == {self_id}
        and _self_consumer_wiring_conformant(
            self_consumer_row,
            conformance_gate,
        )
    )


def _bind_legacy_self_receipt(
    row: dict[str, Any],
    *,
    input_state_fingerprint: str,
    attempt_identity: str,
    hook_io_receipts: list[dict[str, Any]],
) -> dict[str, Any]:
    bound = dict(row)
    hook_id = str(bound.get("hook_id") or "quality_vector")
    consumed = hook_id in _decision_consumed_hook_ids(hook_io_receipts)
    bound.update(
        {
            "input_state_fingerprint": input_state_fingerprint,
            "attempt_identity": attempt_identity,
            "value_consumed_by_decision": consumed,
            "decision_consumption_status": (
                "consumed" if consumed else "not_evaluated"
            ),
        }
    )
    receipt_sha256 = consumer_receipt_binding_sha256(bound)
    bound["probe_evidence_id"] = "probe-" + receipt_sha256[:16]
    bound["probe_evidence_sha256"] = receipt_sha256
    return bound


def _bind_self_receipt_coverage(
    row: dict[str, Any],
    *,
    input_state_fingerprint: str,
    attempt_identity: str,
    adapter_scan_handoff: dict[str, Any],
    gate_compatibility_results: list[dict[str, Any]],
    hook_io_receipts: list[dict[str, Any]],
) -> dict[str, Any]:
    bound = dict(row)
    bound["input_state_fingerprint"] = input_state_fingerprint
    bound["attempt_identity"] = attempt_identity
    hook_id = str(bound.get("hook_id") or "quality_vector")
    manifest_hooks = adapter_scan_handoff.get("available_hook_ids")
    if not isinstance(manifest_hooks, list):
        manifest_hooks = adapter_scan_handoff.get("required_hook_ids")
    available_hook_ids = (
        {str(item) for item in manifest_hooks if str(item).strip()}
        if isinstance(manifest_hooks, list)
        else {hook_id}
    )
    required_gate_ids = sorted(
        str(item.get("gate_id"))
        for item in gate_compatibility_results
        if item.get("gate_id")
    )
    consumed_gate_ids = sorted(
        str(item.get("gate_id"))
        for item in gate_compatibility_results
        if item.get("gate_id") and item.get("gate_compatibility_status") == "compatible"
    )
    excluded_gate_ids = sorted(set(required_gate_ids) - set(consumed_gate_ids))
    decision_consumed_hooks = _decision_consumed_hook_ids(hook_io_receipts)
    acceptance_required_hooks = _acceptance_required_hook_ids(hook_io_receipts)
    active_required_hooks = decision_consumed_hooks | acceptance_required_hooks
    undeclared_active_hooks = active_required_hooks - available_hook_ids
    required_hook_ids = sorted(active_required_hooks & available_hook_ids)
    consumed_hook_ids = sorted(set(required_hook_ids) & decision_consumed_hooks)
    quality_consumed = hook_id in decision_consumed_hooks
    bound.update(
        {
            "consumer_contract_version": CONSUMER_RECEIPT_CONTRACT_VERSION,
            "consumer_revision_sha256": CONSUMER_REVISION_SHA256,
            "validator_signature_sha256": VALIDATOR_SIGNATURE_SHA256,
            "hook_io_receipts": hook_io_receipts,
            "required_hook_ids": required_hook_ids,
            "required_gate_ids": required_gate_ids,
            "consumed_hook_ids": consumed_hook_ids,
            "consumed_gate_ids": consumed_gate_ids,
            "excluded_gate_ids": excluded_gate_ids,
            "value_consumed_by_decision": quality_consumed,
            "decision_consumption_status": (
                "consumed" if quality_consumed else "not_evaluated"
            ),
            "result_contract_status": (
                "conformant"
                if set(consumed_hook_ids) == set(required_hook_ids)
                and not excluded_gate_ids
                and not undeclared_active_hooks
                else "not_evaluated"
            ),
        }
    )
    receipt_sha256 = consumer_receipt_binding_sha256(bound)
    bound["probe_evidence_id"] = "probe-" + receipt_sha256[:16]
    bound["probe_evidence_sha256"] = receipt_sha256
    return bound


def _finalize_consumer_conformance(frame: _EvaluationFrame) -> None:
    (
        adapter_load_gate,
        adapter_consumer_contract_mode,
        adapter_revision_sha256,
        adapter_scan_handoff,
        args,
        attempt_identity,
        decision_artifact_ref,
        declared_consumer_context,
        disposition,
        gate_compatibility_results,
        gate_inputs,
        hard_stop,
        identity_gate_inputs,
        input_state_fingerprint,
        output_delta,
        runner_validation,
        self_consumer_probe_row,
    ) = frame.require(
        "adapter_load_gate",
        "adapter_consumer_contract_mode",
        "adapter_revision_sha256",
        "adapter_scan_handoff",
        "args",
        "attempt_identity",
        "decision_artifact_ref",
        "declared_consumer_context",
        "disposition",
        "gate_compatibility_results",
        "gate_inputs",
        "hard_stop",
        "identity_gate_inputs",
        "input_state_fingerprint",
        "output_delta",
        "runner_validation",
        "self_consumer_probe_row",
    )
    hook_io_receipts = adapter_invocation_receipts()
    if (
        self_consumer_probe_row is not None
        and adapter_consumer_contract_mode == "manifest_v2"
    ):
        self_consumer_probe_row = _bind_self_receipt_coverage(
            self_consumer_probe_row,
            input_state_fingerprint=input_state_fingerprint,
            attempt_identity=attempt_identity,
            adapter_scan_handoff=adapter_scan_handoff,
            gate_compatibility_results=gate_compatibility_results,
            hook_io_receipts=hook_io_receipts,
        )
    elif (
        self_consumer_probe_row is not None
        and adapter_consumer_contract_mode == "legacy_explicit_adapter"
    ):
        self_consumer_probe_row = _bind_legacy_self_receipt(
            self_consumer_probe_row,
            input_state_fingerprint=input_state_fingerprint,
            attempt_identity=attempt_identity,
            hook_io_receipts=hook_io_receipts,
        )
    final_conformance_inputs: list[Any] = [
        {
            "required_consumer_ids": declared_consumer_context.get(
                "required_consumer_ids"
            )
            or [],
        },
        runner_validation,
        output_delta,
        *identity_gate_inputs,
    ]
    if (
        self_consumer_probe_row is not None
        and adapter_consumer_contract_mode == "manifest_v2"
    ):
        final_conformance_inputs.append(
            {
                "consumer_contract": {
                    "consumer_id": self_consumer_probe_row.get("consumer_context_id"),
                    "task_id": args.task_id,
                    "adapter_revision_sha256": adapter_revision_sha256,
                    "consumer_revision_sha256": CONSUMER_REVISION_SHA256,
                    "hook_id": self_consumer_probe_row.get("hook_id"),
                    "required_hook_ids": self_consumer_probe_row.get(
                        "required_hook_ids"
                    ),
                    "required_gate_ids": self_consumer_probe_row.get(
                        "required_gate_ids"
                    ),
                },
                "consumer_context_conformance": {
                    "rows": [self_consumer_probe_row],
                },
            }
        )
    elif self_consumer_probe_row is not None:
        final_conformance_inputs.append(
            {"consumer_context_conformance": {"rows": [self_consumer_probe_row]}}
        )
    consumer_conformance_gate = consumer_context_conformance_gate(
        *final_conformance_inputs,
        expected_artifact_ref=decision_artifact_ref,
        expected_cycle_id=args.cycle_id,
        expected_input_state_fingerprint=input_state_fingerprint,
        expected_attempt_identity=attempt_identity,
        expected_task_id=args.task_id,
        expected_adapter_revision_sha256=adapter_revision_sha256,
        expected_consumer_revision_sha256=CONSUMER_REVISION_SHA256,
    )
    adapter_load_gate["consumer_context_conformance"] = consumer_conformance_gate
    if (
        adapter_consumer_contract_mode == "manifest_v2"
        and _missing_context_is_wiring_defect(
            consumer_conformance_gate,
            self_consumer_probe_row,
        )
    ):
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
    frame.update(
        {
            "consumer_conformance_gate": consumer_conformance_gate,
            "disposition": disposition,
            "hard_stop": hard_stop,
            "self_consumer_probe_row": self_consumer_probe_row,
        }
    )
