from __future__ import annotations

from .runtime_dependencies import (
    Any,
    bool_value,
    first_field_value,
    re,
    string_list,
)

from .evaluation_frame import _require_values
from .packet_finalization_fields import _finalization_fields
from .packet_gate_fields import _gate_fields
from .packet_identity_fields import _identity_fields
from .packet_progress_fields import _progress_fields
from .packet_verification_fields import _verification_fields


_PACKET_SECTION_BUILDERS = (
    _identity_fields,
    _gate_fields,
    _progress_fields,
    _verification_fields,
    _finalization_fields,
)


def build_base_packet(ns: dict[str, Any]) -> dict[str, Any]:
    (
        adapter_gate,
        adapter_load_gate,
        coverage_gate,
        decision_artifact_ref,
        gate_inputs,
        hard_stop,
        output_delta,
        primary_metric_gate,
        quality,
        runner_validation,
        semantic_progress,
        source_separation_gate,
        validator_gate,
    ) = _require_values(
        ns,
        (
            "adapter_gate",
            "adapter_load_gate",
            "coverage_gate",
            "decision_artifact_ref",
            "gate_inputs",
            "hard_stop",
            "output_delta",
            "primary_metric_gate",
            "quality",
            "runner_validation",
            "semantic_progress",
            "source_separation_gate",
            "validator_gate",
        ),
    )
    integrity_values = [runner_validation, output_delta, quality, *gate_inputs]
    truth_required = bool_value(
        first_field_value(
            integrity_values,
            {"actual_body_truth_required", "acceptance_required_actual_body_truth"},
        )
    )
    truth_basis = str(
        first_field_value(integrity_values, {"truth_basis", "actual_body_truth_basis"}) or ""
    ).strip().lower()
    body_divergence = bool_value(
        first_field_value(integrity_values, {"report_body_divergence"})
    )
    key_divergence = bool_value(
        first_field_value(integrity_values, {"report_key_divergence"})
    )
    consumer_missing = bool_value(
        (adapter_load_gate.get("consumer_context_conformance") or {}).get(
            "missing_consumer_context_ids"
        )
    )
    body_fingerprint = str(
        decision_artifact_ref.get("body_projection_fingerprint") or ""
    ).strip().lower()
    exact_body_bound = bool(re.fullmatch(r"[0-9a-f]{64}", body_fingerprint))
    exact_cohort_bound = bool(
        string_list(decision_artifact_ref.get("verification_input_ids"))
    ) or bool(
        decision_artifact_ref.get("input_fingerprints")
        if isinstance(decision_artifact_ref.get("input_fingerprints"), dict)
        else None
    )
    authoritative_progress = bool(semantic_progress) and not any(
        (
            hard_stop,
            body_divergence,
            key_divergence,
            consumer_missing,
            not bool_value(decision_artifact_ref.get("scope_verified")),
            not exact_body_bound,
            not exact_cohort_bound,
            not bool_value(coverage_gate.get("decision_contribution_allowed")),
            not bool_value(primary_metric_gate.get("primary_metric_high_water_moved")),
            truth_required and truth_basis in {"", "not_evaluated", "missing", "unknown"},
            bool_value(validator_gate.get("constrains_disposition")),
            bool_value(
                source_separation_gate.get("independently_verified_downgraded_fields")
            ),
        )
    )
    state = dict(ns)
    state.update(
        {
            "authoritative_progress": authoritative_progress,
            "body_divergence": body_divergence,
            "truth_basis": truth_basis,
            "truth_required": truth_required,
        }
    )
    row: dict[str, Any] = {}
    for builder in _PACKET_SECTION_BUILDERS:
        row.update(builder(state))
    if isinstance(adapter_gate.get("adapter_hook_demand"), list):
        row["adapter_hook_demand"] = adapter_gate.get("adapter_hook_demand") or []
        row["hook_demand_threshold"] = adapter_gate.get("hook_demand_threshold")
        row["hook_supply_required"] = bool_value(adapter_gate.get("hook_supply_required"))
        row["demanded_hooks"] = adapter_gate.get("demanded_hooks") or []
    return row
