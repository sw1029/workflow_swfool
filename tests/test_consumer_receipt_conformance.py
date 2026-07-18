from __future__ import annotations

import copy
from pathlib import Path
import sys
import types
from typing import Any, Callable

import pytest


ROOT = Path(__file__).resolve().parents[1]
for package_root in (
    ROOT / "orchestrate-task-cycle" / "scripts",
    ROOT / "audit-cycle-loopback" / "scripts",
):
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))

from audit_cycle_loopback import adapters, consumer_context  # noqa: E402
from audit_cycle_loopback import consumer_receipt_contract as audit_receipts  # noqa: E402
from audit_cycle_loopback import evaluation_frame  # noqa: E402
from audit_cycle_loopback.evaluation_stages import finalize_consumer  # noqa: E402
from orchestrate_task_cycle.result_contract import api as result_contract  # noqa: E402
from orchestrate_task_cycle.result_contract.consumer_receipt_contract import (  # noqa: E402
    CONSUMER_RECEIPT_CONTRACT_VERSION,
    CONSUMER_REVISION_SHA256,
    VALIDATOR_SIGNATURE_SHA256,
    validate_consumer_receipt_binding,
)


TASK_ID = "task-current"
ADAPTER_REVISION = "d" * 64
CONSUMER_ID = "consumer-current"
HOOK_ID = "quality_vector"
REQUIRED_HOOKS = [HOOK_ID]
REQUIRED_GATES = ["gate-A", "gate-B"]
ARTIFACT_REF = {
    "artifact_id": "artifact-current",
    "artifact_sha256": "a" * 64,
    "production_lane_identity": "lane-current",
    "body_projection_fingerprint": "b" * 64,
    "verification_input_ids": ["input-current"],
}


def contract() -> dict[str, Any]:
    return {
        "consumer_id": CONSUMER_ID,
        "task_id": TASK_ID,
        "adapter_revision_sha256": ADAPTER_REVISION,
        "consumer_revision_sha256": CONSUMER_REVISION_SHA256,
        "hook_id": HOOK_ID,
        "required_hook_ids": REQUIRED_HOOKS,
        "required_gate_ids": REQUIRED_GATES,
    }


def receipt() -> dict[str, Any]:
    row = {
        "consumer_context_id": CONSUMER_ID,
        "hook_id": HOOK_ID,
        "cycle_id": "cycle-current",
        "task_id": TASK_ID,
        "attempt_identity": "attempt-current",
        "input_state_fingerprint": "c" * 64,
        "adapter_revision_sha256": ADAPTER_REVISION,
        "consumer_contract_version": CONSUMER_RECEIPT_CONTRACT_VERSION,
        "consumer_revision_sha256": CONSUMER_REVISION_SHA256,
        "validator_signature_sha256": VALIDATOR_SIGNATURE_SHA256,
        "hook_io_receipts": [
            {
                "acceptance_required": True,
                "invocation_index": 0,
                "hook_id": HOOK_ID,
                "input_sha256": "1" * 64,
                "output_sha256": "2" * 64,
                "return_contract_valid": True,
                "semantic_status": "accepted",
                "signature_sha256": "3" * 64,
                "status": "completed",
                "value_consumed_by_decision": True,
            }
        ],
        **ARTIFACT_REF,
        "required_hook_ids": REQUIRED_HOOKS,
        "required_gate_ids": REQUIRED_GATES,
        "consumed_hook_ids": REQUIRED_HOOKS,
        "consumed_gate_ids": REQUIRED_GATES,
        "excluded_gate_ids": [],
        "result_contract_status": "conformant",
        "adapter_loaded": True,
        "hook_resolved": True,
        "required_hook_callable": True,
        "hook_signature_compatible": True,
        "invocation_completed": True,
        "return_contract_valid": True,
        "artifact_identity_echo_valid": True,
        "value_consumed_by_decision": True,
        "evidence_provenance": "independently_verified",
        "probe_evidence_ref": "packet:consumer-current",
    }
    row["probe_evidence_sha256"] = consumer_context.consumer_receipt_binding_sha256(row)
    return row


def audit_verdict(row: dict[str, Any]) -> dict[str, Any]:
    return consumer_context.consumer_context_conformance_gate(
        {
            "required_consumer_ids": [CONSUMER_ID],
            "consumer_contract": contract(),
            "consumer_context_conformance": {"rows": [row]},
        },
        expected_artifact_ref=ARTIFACT_REF,
        expected_cycle_id="cycle-current",
        expected_input_state_fingerprint="c" * 64,
        expected_attempt_identity="attempt-current",
        expected_task_id=TASK_ID,
        expected_adapter_revision_sha256=ADAPTER_REVISION,
    )


def result_verdict(row: dict[str, Any]) -> dict[str, Any]:
    return result_contract.validate(
        "loopback_audit",
        {
            "step": "loopback_audit",
            "task_id": TASK_ID,
            "cycle_id": "cycle-current",
            "input_state_fingerprint": "c" * 64,
            "attempt_identity": "attempt-current",
            "decision_artifact_ref": ARTIFACT_REF,
            "domain_adapter": {
                "adapter_revision_sha256": ADAPTER_REVISION,
                "required_hook_ids": REQUIRED_HOOKS,
            },
            "required_gate_ids": REQUIRED_GATES,
            "required_consumer_ids": [CONSUMER_ID],
            "consumer_contracts": [contract()],
            "consumer_context_conformance": {"rows": [row]},
        },
        "block",
    )


def consumer_finding(result: dict[str, Any]) -> dict[str, Any] | None:
    return next(
        (
            row
            for row in result.get("findings", [])
            if row.get("code") == "required_consumer_context_not_evaluated"
        ),
        None,
    )


def test_cross_owner_explicit_receipt_happy_path_and_hash_are_identical() -> None:
    row = receipt()
    binding = validate_consumer_receipt_binding(
        row,
        expected_task_id=TASK_ID,
        expected_adapter_revision_sha256=ADAPTER_REVISION,
        expected_hook_id=HOOK_ID,
        expected_required_hook_ids=REQUIRED_HOOKS,
        expected_required_gate_ids=REQUIRED_GATES,
    )
    audit_binding = audit_receipts.validate_consumer_receipt_binding(
        row,
        expected_task_id=TASK_ID,
        expected_adapter_revision_sha256=ADAPTER_REVISION,
        expected_consumer_revision_sha256=CONSUMER_REVISION_SHA256,
        expected_hook_id=HOOK_ID,
        expected_required_hook_ids=REQUIRED_HOOKS,
        expected_required_gate_ids=REQUIRED_GATES,
    )

    assert row[
        "probe_evidence_sha256"
    ] == result_contract._consumer_receipt_binding_sha256(row)
    assert binding["status"] == "conformant"
    assert binding == audit_binding
    assert audit_receipts.VALIDATOR_SIGNATURE_SHA256 == VALIDATOR_SIGNATURE_SHA256
    assert binding["mismatched_fields"] == []
    assert audit_verdict(row)["status"] == "pass"
    assert consumer_finding(result_verdict(row)) is None


def other_task(row: dict[str, Any]) -> None:
    row["task_id"] = "task-replayed"


def other_adapter(row: dict[str, Any]) -> None:
    row["adapter_revision_sha256"] = "e" * 64


def missing_hook(row: dict[str, Any]) -> None:
    row["consumed_hook_ids"] = []
    row["result_contract_status"] = "not_evaluated"


def missing_gate(row: dict[str, Any]) -> None:
    row["consumed_gate_ids"] = ["gate-A"]
    row["result_contract_status"] = "not_evaluated"


def incompatible_required_gate(row: dict[str, Any]) -> None:
    row["consumed_gate_ids"] = ["gate-A"]
    row["excluded_gate_ids"] = ["gate-B"]
    row["result_contract_status"] = "not_evaluated"


@pytest.mark.parametrize(
    ("mutate", "expected_field"),
    (
        (other_task, "task_id"),
        (other_adapter, "adapter_revision_sha256"),
        (missing_hook, "consumed_hook_ids"),
        (missing_gate, "gate_coverage"),
        (incompatible_required_gate, "consumer_coverage_status"),
    ),
)
def test_cross_owner_rejects_replay_missing_and_incompatible_coverage(
    mutate: Callable[[dict[str, Any]], None], expected_field: str
) -> None:
    row = receipt()
    mutate(row)
    row["probe_evidence_sha256"] = consumer_context.consumer_receipt_binding_sha256(row)

    audit = audit_verdict(row)
    result = result_verdict(row)
    finding = consumer_finding(result)

    assert audit["status"] == "not_evaluated"
    assert audit["rows"][0]["status"] == "not_evaluated"
    assert finding is not None
    mismatches = (
        finding.get("evidence", {}).get("mismatched_fields", {}).get(CONSUMER_ID, [])
    )
    assert expected_field in mismatches


def test_cross_owner_rejects_tampered_coverage_without_rebinding_hash() -> None:
    row = receipt()
    original = copy.deepcopy(row)
    row["consumed_gate_ids"] = ["gate-A"]

    assert row["probe_evidence_sha256"] == original["probe_evidence_sha256"]
    assert row[
        "probe_evidence_sha256"
    ] != result_contract._consumer_receipt_binding_sha256(row)
    assert audit_verdict(row)["status"] == "not_evaluated"
    assert consumer_finding(result_verdict(row)) is not None


def test_rehashed_boolean_only_receipt_cannot_replace_hook_io_evidence() -> None:
    row = receipt()
    for field in (
        "consumer_contract_version",
        "consumer_revision_sha256",
        "validator_signature_sha256",
        "hook_io_receipts",
    ):
        row.pop(field)
    row["probe_evidence_sha256"] = consumer_context.consumer_receipt_binding_sha256(row)

    binding = validate_consumer_receipt_binding(
        row,
        expected_task_id=TASK_ID,
        expected_adapter_revision_sha256=ADAPTER_REVISION,
        expected_consumer_revision_sha256=CONSUMER_REVISION_SHA256,
        expected_hook_id=HOOK_ID,
        expected_required_hook_ids=REQUIRED_HOOKS,
        expected_required_gate_ids=REQUIRED_GATES,
    )

    assert binding["status"] == "not_evaluated"
    assert "hook_io_receipts" in binding["mismatched_fields"]
    assert audit_verdict(row)["status"] == "not_evaluated"


def finalize_frame(gate_statuses: dict[str, str]) -> evaluation_frame._EvaluationFrame:
    adapters.reset_adapter_invocation_receipts()
    adapters.call_adapter(
        types.SimpleNamespace(quality_vector=lambda **_kwargs: {}),
        HOOK_ID,
        artifact_id="artifact-current",
    )
    adapters.bind_adapter_invocation_result(
        HOOK_ID,
        return_contract_valid=True,
        semantic_accepted=True,
        value_consumed_by_decision=True,
    )
    row = receipt()
    row["consumer_context_id"] = "audit-cycle-loopback"
    row["hook_id"] = HOOK_ID
    for field in (
        "required_hook_ids",
        "required_gate_ids",
        "consumed_hook_ids",
        "consumed_gate_ids",
        "excluded_gate_ids",
        "result_contract_status",
        "probe_evidence_sha256",
    ):
        row.pop(field, None)
    return evaluation_frame._EvaluationFrame(
        {
            "adapter_load_gate": {},
            "adapter_consumer_contract_mode": "manifest_v2",
            "adapter_revision_sha256": ADAPTER_REVISION,
            "adapter_scan_handoff": {"required_hook_ids": REQUIRED_HOOKS},
            "args": types.SimpleNamespace(
                task_id=TASK_ID,
                cycle_id="cycle-current",
            ),
            "attempt_identity": "attempt-current",
            "decision_artifact_ref": ARTIFACT_REF,
            "declared_consumer_context": {
                "required_consumer_ids": ["audit-cycle-loopback"]
            },
            "disposition": "goal_productive",
            "gate_compatibility_results": [
                {"gate_id": gate_id, "gate_compatibility_status": status}
                for gate_id, status in gate_statuses.items()
            ],
            "gate_inputs": [],
            "hard_stop": False,
            "identity_gate_inputs": [],
            "input_state_fingerprint": "c" * 64,
            "output_delta": {},
            "runner_validation": {},
            "self_consumer_probe_row": row,
        }
    )


def test_loopback_finalizer_emits_exact_manifest_and_decision_coverage() -> None:
    frame = finalize_frame({"gate-A": "compatible", "gate-B": "compatible"})
    finalize_consumer._finalize_consumer_conformance(frame)
    state = frame.snapshot()
    gate = state["consumer_conformance_gate"]
    row = gate["rows"][0]

    assert gate["status"] == "pass"
    assert row["required_hook_ids"] == REQUIRED_HOOKS
    assert row["required_gate_ids"] == REQUIRED_GATES
    assert row["consumed_hook_ids"] == REQUIRED_HOOKS
    assert row["consumed_gate_ids"] == REQUIRED_GATES
    assert row["excluded_gate_ids"] == []
    assert row["result_contract_status"] == "conformant"
    assert row[
        "probe_evidence_sha256"
    ] == result_contract._consumer_receipt_binding_sha256(row)


def test_loopback_decision_used_reachability_hooks_enter_receipt_demand() -> None:
    frame = finalize_frame({"gate-A": "compatible", "gate-B": "compatible"})
    required_hooks = [HOOK_ID, "acceptance_scale", "throughput_evidence"]
    for hook_id in required_hooks[1:]:
        adapters.call_adapter(
            types.SimpleNamespace(**{hook_id: lambda **_kwargs: {"status": "pass"}}),
            hook_id,
            artifact_id="artifact-current",
        )
        adapters.bind_adapter_invocation_result(
            hook_id,
            return_contract_valid=True,
            semantic_accepted=True,
            value_consumed_by_decision=True,
        )
    frame.update({"adapter_scan_handoff": {"required_hook_ids": required_hooks}})

    finalize_consumer._finalize_consumer_conformance(frame)
    row = frame.snapshot()["consumer_conformance_gate"]["rows"][0]

    assert row["required_hook_ids"] == sorted(required_hooks)
    assert row["consumed_hook_ids"] == sorted(required_hooks)
    assert {item["hook_id"] for item in row["hook_io_receipts"]} >= set(required_hooks)


def test_fail_quiet_required_secondary_hook_is_not_consumed() -> None:
    frame = finalize_frame({"gate-A": "compatible", "gate-B": "compatible"})
    hook_id = "acceptance_scale"
    adapters.call_adapter(
        types.SimpleNamespace(
            acceptance_scale=lambda **_kwargs: {
                "status": "fail_quiet",
                "evaluation_status": "not_evaluated",
            }
        ),
        hook_id,
        artifact_id="artifact-current",
    )
    adapters.bind_adapter_invocation_result(
        hook_id,
        return_contract_valid=True,
        semantic_accepted=False,
        value_consumed_by_decision=False,
        acceptance_required=True,
    )
    frame.update({"adapter_scan_handoff": {"required_hook_ids": [HOOK_ID, hook_id]}})

    finalize_consumer._finalize_consumer_conformance(frame)
    state = frame.snapshot()
    row = state["consumer_conformance_gate"]["rows"][0]

    assert hook_id not in row["consumed_hook_ids"]
    assert row["result_contract_status"] == "not_evaluated"
    assert state["adapter_load_gate"]["adapter_wiring_defect"] is True


def test_optional_uninvoked_and_fail_quiet_hooks_do_not_create_wiring_defect() -> None:
    frame = finalize_frame({"gate-A": "compatible", "gate-B": "compatible"})
    fail_quiet_hook = "acceptance_scale"
    uninvoked_hook = "throughput_evidence"
    adapters.call_adapter(
        types.SimpleNamespace(
            acceptance_scale=lambda **_kwargs: {
                "status": "fail_quiet",
                "evaluation_status": "not_evaluated",
            }
        ),
        fail_quiet_hook,
        artifact_id="artifact-current",
    )
    adapters.bind_adapter_invocation_result(
        fail_quiet_hook,
        return_contract_valid=True,
        semantic_accepted=False,
        value_consumed_by_decision=False,
        acceptance_required=False,
    )
    available = [HOOK_ID, fail_quiet_hook, uninvoked_hook]
    frame.update({"adapter_scan_handoff": {"available_hook_ids": available}})

    finalize_consumer._finalize_consumer_conformance(frame)
    state = frame.snapshot()
    row = state["consumer_conformance_gate"]["rows"][0]

    assert row["required_hook_ids"] == [HOOK_ID]
    assert row["consumed_hook_ids"] == [HOOK_ID]
    assert state["consumer_conformance_gate"]["status"] == "pass"
    assert state["adapter_load_gate"].get("adapter_wiring_defect") is not True


def test_loopback_finalizer_keeps_incompatible_required_gate_not_evaluated() -> None:
    frame = finalize_frame({"gate-A": "compatible", "gate-B": "incompatible"})
    finalize_consumer._finalize_consumer_conformance(frame)
    state = frame.snapshot()
    gate = state["consumer_conformance_gate"]
    row = gate["rows"][0]

    assert gate["status"] == "not_evaluated"
    assert gate["missing_consumer_context_ids"] == ["audit-cycle-loopback"]
    assert row["excluded_gate_ids"] == ["gate-B"]
    assert row["result_contract_status"] == "not_evaluated"
    assert state["hard_stop"] is True
    assert state["disposition"] == "self_inflicted_gate_defect"
