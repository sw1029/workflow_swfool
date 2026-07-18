from __future__ import annotations

from ..runtime_dependencies import (
    apply_quality_policy_compatibility,
    bind_adapter_invocation_result,
    bool_value,
    call_adapter,
    compute_quality,
    load_json_value,
    normalize_quality_delta_policy,
    rel_path,
)

from ..evaluation_frame import _EvaluationFrame


def _prepare_quality_state(frame: _EvaluationFrame) -> None:
    (
        args, decision_artifact_ref, domain_adapter, domain_adapter_error,
        gate_compatibility_results, paths, root,
    ) = frame.require(
        'args', 'decision_artifact_ref', 'domain_adapter', 'domain_adapter_error',
        'gate_compatibility_results', 'paths', 'root',
    )
    runner_validation = load_json_value(root, getattr(args, "runner_validation_json", None))
    output_delta = load_json_value(root, getattr(args, "output_delta_json", None))
    quality_delta_policy_value, quality_delta_policy_error = call_adapter(
        domain_adapter,
        "quality_delta_policy",
        root=root,
        artifact_paths=[rel_path(root, path) for path in paths],
        decision_artifact_ref=decision_artifact_ref,
        quality_vector={},
        output_delta=output_delta,
        runner_validation=runner_validation,
        applicability_preflight=True,
    )
    quality_delta_policy = normalize_quality_delta_policy(quality_delta_policy_value)
    preflight_policy_accepted = bool(
        isinstance(quality_delta_policy_value, (dict, list, tuple, set))
        and quality_delta_policy.get("supplied")
        and quality_delta_policy.get("applicability_supplied")
        and not quality_delta_policy_error
    )
    bind_adapter_invocation_result(
        "quality_delta_policy",
        return_contract_valid=isinstance(
            quality_delta_policy_value, (dict, list, tuple, set)
        ),
        semantic_accepted=preflight_policy_accepted,
        value_consumed_by_decision=preflight_policy_accepted,
    )

    quality, evidence_paths, insufficient_reason, quality_hook_receipt = (
        (
            {},
            [],
            domain_adapter_error,
            {
                "hook_resolved": False,
                "hook_signature_compatible": False,
                "invocation_completed": False,
                "return_contract_valid": False,
            },
        )
        if domain_adapter_error
        else compute_quality(root, paths, domain_adapter, decision_artifact_ref)
    )
    if not quality_delta_policy.get("applicability_supplied"):
        legacy_policy_value, legacy_policy_error = call_adapter(
            domain_adapter,
            "quality_delta_policy",
            root=root,
            artifact_paths=[rel_path(root, path) for path in paths],
            decision_artifact_ref=decision_artifact_ref,
            quality_vector=quality,
            output_delta=output_delta,
            runner_validation=runner_validation,
            applicability_preflight=False,
        )
        legacy_policy = normalize_quality_delta_policy(legacy_policy_value)
        legacy_policy_accepted = bool(
            isinstance(legacy_policy_value, (dict, list, tuple, set))
            and legacy_policy.get("supplied")
            and not legacy_policy_error
        )
        bind_adapter_invocation_result(
            "quality_delta_policy",
            return_contract_valid=isinstance(
                legacy_policy_value, (dict, list, tuple, set)
            ),
            semantic_accepted=legacy_policy_accepted,
            value_consumed_by_decision=legacy_policy_accepted,
        )
        if legacy_policy.get("supplied"):
            quality_delta_policy = legacy_policy
            quality_delta_policy_error = legacy_policy_error
    quality_contract_valid = bool(quality_hook_receipt.get("return_contract_valid"))
    quality_accepted = bool(quality_contract_valid and not insufficient_reason)
    bind_adapter_invocation_result(
        "quality_vector",
        return_contract_valid=quality_contract_valid,
        semantic_accepted=quality_accepted,
        value_consumed_by_decision=quality_accepted,
        acceptance_required=True,
    )
    coverage_compatibility = {
        "gate_id": "coverage_quality_delta_gate",
        "artifact_id": decision_artifact_ref.get("artifact_id"),
        "artifact_sha256": decision_artifact_ref.get("artifact_sha256"),
        "gate_compatibility_status": (
            "compatible"
            if bool_value(decision_artifact_ref.get("scope_verified"))
            and quality_delta_policy.get("supplied")
            and not quality_delta_policy_error
            else "not_evaluated"
        ),
        "compatibility_basis": (
            "artifact_identity_not_verified"
            if not bool_value(decision_artifact_ref.get("scope_verified"))
            else "quality_delta_policy_error"
            if quality_delta_policy_error
            else "quality_delta_policy"
            if quality_delta_policy.get("supplied")
            else "mapping_not_supplied"
        ),
        "compatibility_evidence_ref": None,
    }
    gate_compatibility_results.append(coverage_compatibility)
    quality_delta_policy = apply_quality_policy_compatibility(
        quality_delta_policy,
        coverage_compatibility,
        policy_error=quality_delta_policy_error,
    )
    provider_request_count = max(0, int(args.provider_request_count or 0))
    frame.update({
        "coverage_compatibility": coverage_compatibility,
        "evidence_paths": evidence_paths,
        "insufficient_reason": insufficient_reason,
        "output_delta": output_delta,
        "provider_request_count": provider_request_count,
        "quality": quality,
        "quality_delta_policy": quality_delta_policy,
        "quality_delta_policy_error": quality_delta_policy_error,
        "quality_hook_receipt": quality_hook_receipt,
        "runner_validation": runner_validation,
    })
