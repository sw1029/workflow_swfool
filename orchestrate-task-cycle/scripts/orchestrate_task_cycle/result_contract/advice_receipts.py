"""Content bindings for advice-clause consumer and forward-test receipts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .advice_runtime_artifacts import verify_cycle_artifact, workspace_root
from .common import boolish, first_present, list_values
from .decision_identity_dimensions import (
    LEGACY_FIELDS,
    expected_dimension_echo,
    expected_subject_echo,
    parse_decision_identity,
)
from .derive_advice import derive_advice_consumer_binding
from .receipts import _full_sha256, _opaque_scalar


FORWARD_ARTIFACT_KEYS = {
    "contract_version",
    "producer_agent_id",
    "producer_receipt_id",
    "producer_role",
    "freshness_basis",
    "input_advice_clause_set_sha256",
    "input_synthesis_output_sha256",
    "input_decision_identity_echo",
    "scenario_id",
    "precondition_ids",
    "injected_fault_class",
    "output_ref",
    "output",
    "output_sha256",
}
FORWARD_OUTPUT_KEYS = {
    "clause_id",
    "observed_decision_state",
    "decision_path_consumed",
    "evidence_ids",
}
FORWARD_VERIFICATION_KEYS = {
    "contract_version",
    "verifier_agent_id",
    "verifier_receipt_id",
    "producer_agent_id",
    "producer_receipt_id",
    "producer_output_sha256",
    "invariant_owner_id",
    "expected_decision_state",
    "observed_decision_state",
    "invariant_ids",
    "verification_input_ids",
    "evidence_ids",
    "status",
    "receipt_sha256",
}
FORWARD_RECEIPT_KEYS = {
    "path_kind",
    "clause_id",
    "scenario_id",
    "precondition_ids",
    "injected_fault_class",
    "expected_decision_state",
    "observed_decision_state",
    "decision_identity_echo",
    "producer_artifact",
    "independent_verification_receipt",
    "receipt_ref",
    "receipt_sha256",
}


def expected_advice_decision_identity_echo(result: dict[str, Any]) -> dict[str, Any]:
    identity = first_present(
        result,
        [
            "decision_input_identity",
            "decision_artifact_ref",
            "selected_artifact_ref",
            "artifact_ref",
            "actual_artifact_ref",
            "result.decision_input_identity",
            "improvement_analysis_manifest.shared_evidence_manifest.decision_artifact_ref",
        ],
    )
    if not isinstance(identity, dict):
        manifest = first_present(
            result,
            ["improvement_analysis_manifest.shared_evidence_manifest"],
        )
        if isinstance(manifest, dict) and all(
            field in manifest for field in LEGACY_FIELDS
        ):
            identity = {field: manifest[field] for field in LEGACY_FIELDS}
    if not isinstance(identity, dict):
        return {}
    projection = parse_decision_identity(identity)
    if projection.explicit:
        return {
            **expected_subject_echo(identity),
            "dimension_values": expected_dimension_echo(identity),
        }
    return identity


def _digest(basis: dict[str, Any]) -> str:
    raw = json.dumps(basis, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def advice_consumer_receipt_binding_sha256(row: dict[str, Any]) -> str:
    basis = {
        "clause_id": str(row.get("clause_id") or row.get("advice_clause_id") or ""),
        "state": str(row.get("state") or "").strip().lower(),
        "consumer_context_id": str(
            row.get("consumer_context_id") or row.get("consumer_id") or ""
        ),
        "decision_identity_echo": row.get("decision_identity_echo"),
        "invocation_completed": boolish(row.get("invocation_completed")),
        "return_contract_valid": boolish(row.get("return_contract_valid")),
        "decision_path_consumed": boolish(row.get("decision_path_consumed")),
        "evidence_provenance": str(row.get("evidence_provenance") or "")
        .strip()
        .lower(),
        "consumer_receipt_ref": str(row.get("consumer_receipt_ref") or ""),
        "advice_packet_digest": str(
            row.get("advice_packet_digest") or row.get("packet_digest") or ""
        )
        .strip()
        .lower()
        .removeprefix("sha256:"),
        "advice_source_digest": str(
            row.get("advice_source_digest") or row.get("source_digest") or ""
        )
        .strip()
        .lower()
        .removeprefix("sha256:"),
        "documentation_only": boolish(row.get("documentation_only")),
        "hook_declared_only": boolish(row.get("hook_declared_only")),
        "consumer_contract_kind": str(row.get("consumer_contract_kind") or ""),
        "derive_consumer_binding": row.get("derive_consumer_binding"),
    }
    return _digest(basis)


def advice_consumer_receipt_valid(
    row: dict[str, Any],
    expected_identity_echo: dict[str, Any],
    result: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> bool:
    digest = str(row.get("consumer_receipt_sha256") or "").lower()
    clause_id = str(row.get("clause_id") or row.get("advice_clause_id") or "")
    expected_binding = derive_advice_consumer_binding(
        result, clause_id, context=context
    )
    return all(
        (
            bool(expected_identity_echo),
            row.get("decision_identity_echo") == expected_identity_echo,
            row.get("consumer_context_id") == "derive-improvement-task",
            boolish(row.get("invocation_completed")),
            boolish(row.get("return_contract_valid")),
            boolish(row.get("decision_path_consumed")),
            str(row.get("evidence_provenance") or "").strip().lower()
            == "durable_runtime_artifact_bound",
            row.get("consumer_contract_kind") == "derive_three_lens_synthesis",
            isinstance(expected_binding, dict),
            row.get("derive_consumer_binding") == expected_binding,
            row.get("consumer_receipt_ref")
            == (expected_binding or {}).get("synthesis_output_ref"),
            _full_sha256(digest),
            digest == advice_consumer_receipt_binding_sha256(row),
            not boolish(row.get("documentation_only")),
            not boolish(row.get("hook_declared_only")),
        )
    )


def advice_forward_path_receipt_binding_sha256(
    row: dict[str, Any],
    receipt: dict[str, Any],
) -> str:
    basis = {
        "path_kind": str(receipt.get("path_kind") or "").strip().lower(),
        "clause_id": str(receipt.get("clause_id") or ""),
        "scenario_id": str(receipt.get("scenario_id") or ""),
        "precondition_ids": sorted(
            str(item) for item in list_values(receipt.get("precondition_ids"))
        ),
        "injected_fault_class": receipt.get("injected_fault_class"),
        "expected_decision_state": receipt.get("expected_decision_state"),
        "observed_decision_state": receipt.get("observed_decision_state"),
        "decision_identity_echo": receipt.get("decision_identity_echo"),
        "producer_artifact": receipt.get("producer_artifact"),
        "independent_verification_receipt": receipt.get(
            "independent_verification_receipt"
        ),
        "receipt_ref": str(receipt.get("receipt_ref") or ""),
        "contract_test_status": str(row.get("contract_test_status") or "")
        .strip()
        .lower(),
        "consumer_test_status": str(row.get("consumer_test_status") or "")
        .strip()
        .lower(),
        "forward_scenario_status": str(row.get("forward_scenario_status") or "")
        .strip()
        .lower(),
        "regression_status": str(row.get("regression_status") or "").strip().lower(),
    }
    return _digest(basis)


def advice_forward_agent_output_sha256(output: dict[str, Any]) -> str:
    return _digest(output)


def advice_forward_verification_receipt_sha256(receipt: dict[str, Any]) -> str:
    return _digest(
        {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    )


def _opaque_list(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and len(value) == len(set(map(str, value)))
        and all(_opaque_scalar(item) for item in value)
    )


def _forward_agent_artifact_valid(
    row: dict[str, Any],
    receipt: dict[str, Any],
    *,
    path_kind: str,
    expected_identity_echo: dict[str, Any],
    expected_binding: dict[str, Any],
    root: Path,
) -> bool:
    artifact = receipt.get("producer_artifact")
    verification = receipt.get("independent_verification_receipt")
    if not isinstance(artifact, dict) or not isinstance(verification, dict):
        return False
    if (
        set(artifact) != FORWARD_ARTIFACT_KEYS
        or set(verification) != FORWARD_VERIFICATION_KEYS
    ):
        return False
    output = artifact.get("output")
    if not isinstance(output, dict) or set(output) != FORWARD_OUTPUT_KEYS:
        return False
    expected_fault = None if path_kind == "happy" else row.get("injected_fault_class")
    expected_state = (
        row.get("happy_expected_decision_state")
        if path_kind == "happy"
        else row.get("expected_decision_state")
    )
    output_sha = str(artifact.get("output_sha256") or "")
    producer_valid = all(
        (
            artifact.get("contract_version") == 1,
            _opaque_scalar(artifact.get("producer_agent_id")),
            _opaque_scalar(artifact.get("producer_receipt_id")),
            artifact.get("producer_role") == f"advice_forward_{path_kind}",
            artifact.get("freshness_basis") == "current_bound_inputs",
            artifact.get("input_advice_clause_set_sha256")
            == expected_binding.get("advice_clause_set_sha256"),
            artifact.get("input_synthesis_output_sha256")
            == expected_binding.get("synthesis_output_sha256"),
            artifact.get("input_decision_identity_echo") == expected_identity_echo,
            artifact.get("scenario_id") == row.get("scenario_id"),
            artifact.get("precondition_ids") == row.get("precondition_ids"),
            artifact.get("injected_fault_class") == expected_fault,
            _opaque_scalar(artifact.get("output_ref")),
            output.get("clause_id") == row.get("clause_id"),
            output.get("observed_decision_state") == expected_state,
            output.get("decision_path_consumed") is True,
            _opaque_list(output.get("evidence_ids")),
            _full_sha256(output_sha),
            output_sha == advice_forward_agent_output_sha256(output),
        )
    )
    verification_sha = str(verification.get("receipt_sha256") or "")
    producer_input_ids = set(map(str, artifact.get("precondition_ids") or []))
    producer_evidence_ids = set(map(str, output.get("evidence_ids") or []))
    verification_input_ids = set(
        map(str, verification.get("verification_input_ids") or [])
    )
    invariant_ids = set(map(str, verification.get("invariant_ids") or []))
    verification_valid = all(
        (
            verification.get("contract_version") == 1,
            _opaque_scalar(verification.get("verifier_agent_id")),
            verification.get("verifier_agent_id") != artifact.get("producer_agent_id"),
            _opaque_scalar(verification.get("verifier_receipt_id")),
            verification.get("producer_agent_id") == artifact.get("producer_agent_id"),
            verification.get("producer_receipt_id")
            == artifact.get("producer_receipt_id"),
            verification.get("producer_output_sha256") == output_sha,
            _opaque_scalar(verification.get("invariant_owner_id")),
            verification.get("invariant_owner_id") != artifact.get("producer_agent_id"),
            verification.get("expected_decision_state") == expected_state,
            verification.get("observed_decision_state")
            == output.get("observed_decision_state"),
            _opaque_list(verification.get("invariant_ids")),
            _opaque_list(verification.get("verification_input_ids")),
            verification_input_ids.isdisjoint(producer_input_ids),
            verification_input_ids.isdisjoint(producer_evidence_ids),
            invariant_ids.isdisjoint(producer_input_ids),
            _opaque_list(verification.get("evidence_ids")),
            verification.get("status") == "pass",
            _full_sha256(verification_sha),
            verification_sha
            == advice_forward_verification_receipt_sha256(verification),
        )
    )
    runtime_binding = expected_binding.get("runtime_artifact_binding")
    cycle_id = (
        runtime_binding.get("cycle_id") if isinstance(runtime_binding, dict) else None
    )
    producer_file = (
        verify_cycle_artifact(root, cycle_id, artifact.get("output_ref"), output)
        if isinstance(cycle_id, str)
        else None
    )
    return bool(
        producer_valid
        and verification_valid
        and producer_file
        and producer_file["artifact_sha256"] == output_sha
    )


def advice_forward_path_receipt_valid(
    row: dict[str, Any],
    receipt: Any,
    *,
    path_kind: str,
    expected_identity_echo: dict[str, Any],
    result: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> bool:
    if not isinstance(receipt, dict) or set(receipt) != FORWARD_RECEIPT_KEYS:
        return False
    clause_id = str(row.get("clause_id") or "")
    expected_binding = derive_advice_consumer_binding(
        result, clause_id, context=context
    )
    if not isinstance(expected_binding, dict):
        return False
    expected = (
        row.get("happy_expected_decision_state")
        if path_kind == "happy"
        else row.get("expected_decision_state")
    )
    observed = (
        row.get("happy_observed_decision_state")
        if path_kind == "happy"
        else row.get("observed_decision_state")
    )
    expected_fault = None if path_kind == "happy" else row.get("injected_fault_class")
    digest = str(receipt.get("receipt_sha256") or "").lower()
    receipt_preconditions = list_values(receipt.get("precondition_ids"))
    row_preconditions = list_values(row.get("precondition_ids"))
    preconditions_valid = bool(row_preconditions) and all(
        _opaque_scalar(item) for item in [*row_preconditions, *receipt_preconditions]
    )
    runtime_binding = expected_binding.get("runtime_artifact_binding")
    cycle_id = (
        runtime_binding.get("cycle_id") if isinstance(runtime_binding, dict) else None
    )
    root = workspace_root(result, context)
    receipt_file_valid = bool(
        isinstance(cycle_id, str)
        and verify_cycle_artifact(root, cycle_id, receipt.get("receipt_ref"), receipt)
    )
    return all(
        (
            receipt.get("path_kind") == path_kind,
            receipt.get("clause_id") == row.get("clause_id"),
            receipt.get("scenario_id") == row.get("scenario_id"),
            preconditions_valid,
            sorted(str(item) for item in receipt_preconditions)
            == sorted(str(item) for item in row_preconditions),
            receipt.get("injected_fault_class") == expected_fault,
            _opaque_scalar(expected),
            expected == observed,
            receipt.get("expected_decision_state") == expected,
            receipt.get("observed_decision_state") == observed,
            bool(expected_identity_echo),
            receipt.get("decision_identity_echo") == expected_identity_echo,
            _opaque_scalar(receipt.get("receipt_ref")),
            _forward_agent_artifact_valid(
                row,
                receipt,
                path_kind=path_kind,
                expected_identity_echo=expected_identity_echo,
                expected_binding=expected_binding,
                root=root,
            ),
            receipt_file_valid,
            _full_sha256(digest),
            digest == advice_forward_path_receipt_binding_sha256(row, receipt),
        )
    )


def build_derive_advice_consumption_rows(
    result: dict[str, Any],
    *,
    state: str = "wired",
    context: dict[str, Any] | None = None,
    workspace_root: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Build receipts only from a validated, applicable derive advice projection."""
    if state not in {"wired", "verified"}:
        raise ValueError("derive advice receipt state must be wired or verified")
    analysis = result.get("improvement_analysis_manifest")
    manifest = (
        analysis.get("shared_evidence_manifest") if isinstance(analysis, dict) else None
    )
    contract = (
        manifest.get("active_advice_clause_set") if isinstance(manifest, dict) else None
    )
    if not isinstance(contract, dict):
        return []
    identity_echo = expected_advice_decision_identity_echo(result)
    rows: list[dict[str, Any]] = []
    for clause_id in contract.get("actionable_clause_ids", []):
        binding = derive_advice_consumer_binding(
            result,
            str(clause_id),
            context=context,
            workspace_root=workspace_root,
        )
        if not isinstance(binding, dict) or not identity_echo:
            return []
        row: dict[str, Any] = {
            "clause_id": clause_id,
            "state": state,
            "consumer_context_id": "derive-improvement-task",
            "consumer_contract_kind": "derive_three_lens_synthesis",
            "derive_consumer_binding": binding,
            "invocation_completed": True,
            "return_contract_valid": True,
            "decision_path_consumed": True,
            "decision_identity_echo": identity_echo,
            "evidence_provenance": "durable_runtime_artifact_bound",
            "consumer_receipt_ref": binding["synthesis_output_ref"],
            "advice_packet_digest": contract["advice_packet_digest"],
            "advice_source_digest": contract["clause_source_digests"][clause_id],
        }
        row["consumer_receipt_sha256"] = advice_consumer_receipt_binding_sha256(row)
        rows.append(row)
    return rows


__all__ = (
    "advice_consumer_receipt_binding_sha256",
    "advice_consumer_receipt_valid",
    "advice_forward_agent_output_sha256",
    "advice_forward_path_receipt_binding_sha256",
    "advice_forward_path_receipt_valid",
    "advice_forward_verification_receipt_sha256",
    "build_derive_advice_consumption_rows",
    "expected_advice_decision_identity_echo",
)
