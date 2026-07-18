from __future__ import annotations

from .runtime_dependencies import (
    Any,
    bool_value,
)

from .evaluation_frame import _require_values


def _verification_fields(state: dict[str, Any]) -> dict[str, Any]:
    (
        adapter_expected_path,
        adapter_consumer_contract_mode,
        adapter_registered,
        adapter_revision_sha256,
        adapter_scan_handoff,
        diagnostics_gate,
        domain_adapter,
        domain_adapter_error,
        domain_adapter_path,
        effective_count_key,
        envelope_thaw_streak,
        failure_surface_gate,
        input_contract_gate,
        prev_fingerprint,
        previous_adapter_high,
        previous_baseline_error,
        previous_baseline_source,
        quality,
        reachability_gate,
        root_dominant_parameter_key,
        source_separation_gate,
        verifier_coupling_gate,
    ) = _require_values(
        state,
        (
            "adapter_expected_path",
            "adapter_consumer_contract_mode",
            "adapter_registered",
            "adapter_revision_sha256",
            "adapter_scan_handoff",
            "diagnostics_gate",
            "domain_adapter",
            "domain_adapter_error",
            "domain_adapter_path",
            "effective_count_key",
            "envelope_thaw_streak",
            "failure_surface_gate",
            "input_contract_gate",
            "prev_fingerprint",
            "previous_adapter_high",
            "previous_baseline_error",
            "previous_baseline_source",
            "quality",
            "reachability_gate",
            "root_dominant_parameter_key",
            "source_separation_gate",
            "verifier_coupling_gate",
        ),
    )
    return {
        "failure_surface_stage_gate": failure_surface_gate,
        "execution_stage_ladder_status": failure_surface_gate.get(
            "execution_stage_ladder_status"
        ),
        "last_successful_stage": failure_surface_gate.get("last_successful_stage"),
        "failure_surface_stage": failure_surface_gate.get("failure_surface_stage"),
        "failure_surface_count_key": failure_surface_gate.get(
            "failure_surface_count_key"
        ),
        "terminal_classification_stage_contradiction": bool_value(
            failure_surface_gate.get("terminal_classification_stage_contradiction")
        ),
        "terminal_classification_invalid_for_counting": bool_value(
            failure_surface_gate.get("terminal_classification_invalid_for_counting")
        ),
        "same_input_contract_gate": input_contract_gate,
        "same_input_contract_violation": bool_value(
            input_contract_gate.get("same_input_contract_violation")
        ),
        "diagnostics_unavailable_gate": diagnostics_gate,
        "diagnostics_unavailable": bool_value(
            diagnostics_gate.get("diagnostics_unavailable")
        ),
        "diagnostics_unavailable_streak": diagnostics_gate.get(
            "diagnostics_unavailable_streak"
        ),
        "instrumentation_supply_required": bool_value(
            diagnostics_gate.get("instrumentation_supply_required")
        ),
        "verification_source_separation_gate": source_separation_gate,
        "verification_input_ids": source_separation_gate.get("verification_input_ids")
        or [],
        "producer_input_ids": source_separation_gate.get("producer_input_ids") or [],
        "verified_artifact_ids": source_separation_gate.get("verified_artifact_ids")
        or [],
        "input_fingerprints": source_separation_gate.get("input_fingerprints") or {},
        "independent_source_separation_status": source_separation_gate.get(
            "independent_source_separation_status"
        ),
        "independently_verified_downgraded_fields": source_separation_gate.get(
            "independently_verified_downgraded_fields"
        )
        or [],
        "root_dominant_parameter_key": root_dominant_parameter_key,
        "effective_count_key": effective_count_key,
        "envelope_thaw_item_required": bool_value(
            reachability_gate.get("envelope_thaw_item_required")
        ),
        "envelope_thaw_item": reachability_gate.get("envelope_thaw_item"),
        "envelope_thaw_streak": envelope_thaw_streak,
        "coupled_verifier_gate": verifier_coupling_gate,
        "pass_with_coupled_verifier": bool_value(
            verifier_coupling_gate.get("pass_with_coupled_verifier")
        ),
        "changed_verifier_source_paths": verifier_coupling_gate.get(
            "changed_verifier_source_paths"
        )
        or [],
        "previous_output_fingerprint": prev_fingerprint,
        "current_output_fingerprint": quality.get("current_output_fingerprint"),
        "previous_accepted_baseline": {
            "source": previous_baseline_source,
            "error": previous_baseline_error,
            "fingerprint": prev_fingerprint,
            "quality_vector_override_applied": bool(previous_adapter_high),
        },
        "domain_adapter": {
            "path": domain_adapter_path or adapter_expected_path,
            "expected_path": adapter_expected_path,
            "registered": adapter_registered,
            "loaded": domain_adapter is not None,
            "status": (
                "loaded"
                if domain_adapter is not None
                else ("wiring_defect" if adapter_registered else "not_registered")
            ),
            "error": domain_adapter_error,
            "adapter_revision_sha256": adapter_revision_sha256,
            "consumer_contract_mode": adapter_consumer_contract_mode,
            "scan_handoff_status": adapter_scan_handoff.get("status"),
            "required_consumer_ids": adapter_scan_handoff.get(
                "required_consumer_ids"
            ),
            "required_hook_ids": adapter_scan_handoff.get("required_hook_ids"),
            "available_hook_ids": adapter_scan_handoff.get("available_hook_ids"),
        },
    }
