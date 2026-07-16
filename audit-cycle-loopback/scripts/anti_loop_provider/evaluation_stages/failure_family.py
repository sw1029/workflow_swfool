from __future__ import annotations

from ..runtime_dependencies import (
    call_adapter,
    collapse_root_family,
    coverage_quality_delta_gate,
    latest_root_family_row,
    load_json_value,
    normalize_facet_root_map,
    rel_path,
    terminal_outcome_key,
    terminal_outcome_root_family,
)

from ..evaluation_frame import _EvaluationFrame


def _evaluate_failure_family(frame: _EvaluationFrame) -> None:
    (
        args, coverage_compatibility, current_root_key, decision_artifact_ref, domain_adapter,
        existing_cycle, family_key, insufficient_reason, latest, output_delta, paths,
        prev_count, prev_fingerprint, prev_high, provider_request_count, quality,
        quality_delta_policy, quality_delta_policy_error, registry_rows, root,
    ) = frame.require(
        'args', 'coverage_compatibility', 'current_root_key', 'decision_artifact_ref',
        'domain_adapter', 'existing_cycle', 'family_key', 'insufficient_reason', 'latest',
        'output_delta', 'paths', 'prev_count', 'prev_fingerprint', 'prev_high',
        'provider_request_count', 'quality', 'quality_delta_policy',
        'quality_delta_policy_error', 'registry_rows', 'root',
    )
    coverage_gate = coverage_quality_delta_gate(
        quality,
        prev_high,
        provider_request_count,
        args.epsilon,
        quality_delta_policy,
    )
    if quality_delta_policy_error:
        coverage_gate["quality_delta_policy_error"] = quality_delta_policy_error
    metric_evaluation_status = str(coverage_gate.get("evaluation_status") or "not_evaluated")
    compatibility_status = str(
        coverage_compatibility.get("gate_compatibility_status") or "not_evaluated"
    ).strip().lower()
    compatibility_basis = str(
        coverage_compatibility.get("compatibility_basis") or ""
    ).strip().lower()
    compatibility_invalid = compatibility_basis in {
        "adapter_hook_return_contract_invalid",
        "adapter_hook_identity_echo_invalid",
        "gate_artifact_compatibility_signature_incompatible",
        "hook_error",
    }
    artifact_decision_scope_allowed = bool(
        decision_artifact_ref.get("scope_verified")
        and compatibility_status != "incompatible"
        and not compatibility_invalid
    )
    coverage_gate["gate_compatibility"] = coverage_compatibility
    coverage_gate["gate_compatibility_status"] = compatibility_status
    coverage_gate["artifact_decision_scope_allowed"] = artifact_decision_scope_allowed
    coverage_gate["metric_evaluation_status"] = metric_evaluation_status
    if metric_evaluation_status in {"not_applicable", "insufficient_evidence", "invalid_contract"}:
        coverage_gate["evaluation_status"] = metric_evaluation_status
    coverage_gate["decision_contribution_allowed"] = bool(
        artifact_decision_scope_allowed
        and metric_evaluation_status == "evaluated"
    )
    changed_vs_previous = bool(prev_fingerprint and quality.get("current_output_fingerprint") != prev_fingerprint)
    facet_map_error: str | None = None
    facet_map_value = load_json_value(root, getattr(args, "facet_root_map_json", None))
    if facet_map_value is None:
        facet_map_value, facet_map_error = call_adapter(
            domain_adapter,
            "facet_root_map",
            root=root,
            artifact_paths=[rel_path(root, path) for path in paths],
            quality_vector=quality,
        )
        if facet_map_error:
            facet_map_value = None
    facet_root_map = normalize_facet_root_map(facet_map_value)
    preliminary_changed = bool(prev_fingerprint and quality.get("current_output_fingerprint") != prev_fingerprint)
    preliminary_semantic = bool(
        not insufficient_reason
        and coverage_gate.get("decision_contribution_allowed")
        and coverage_gate.get("quality_delta_pass")
    )
    current_terminal_outcome_key = terminal_outcome_key(output_delta, preliminary_changed, preliminary_semantic)
    raw_root_family_key = collapse_root_family(facet_root_map, current_root_key, args.semantic_signature, args.artifact_family)
    terminal_family_key, terminal_family_source, terminal_family_fallback = terminal_outcome_root_family(
        facet_root_map,
        artifact_family=args.artifact_family,
        outcome_key=current_terminal_outcome_key,
        root_key=current_root_key,
        semantic_signature=args.semantic_signature,
    )
    facet_root_map_missing = not bool(facet_root_map)
    current_root_family_key = terminal_family_key if facet_root_map_missing else raw_root_family_key
    latest_terminal_family = latest_root_family_row(registry_rows, current_root_family_key)
    if facet_root_map_missing:
        family_key = terminal_family_key
        existing_cycle = existing_cycle or next(
            (row for row in reversed(registry_rows) if row.get("family_key") == family_key and row.get("cycle_id") == args.cycle_id),
            None,
        )
        latest = latest_terminal_family or latest
        prev_count = max(prev_count, int((latest or {}).get("micro_hardening_count") or 0))
    frame.update({
        "changed_vs_previous": changed_vs_previous,
        "coverage_gate": coverage_gate,
        "current_root_family_key": current_root_family_key,
        "current_terminal_outcome_key": current_terminal_outcome_key,
        "existing_cycle": existing_cycle,
        "facet_map_error": facet_map_error,
        "facet_root_map": facet_root_map,
        "facet_root_map_missing": facet_root_map_missing,
        "family_key": family_key,
        "latest": latest,
        "latest_terminal_family": latest_terminal_family,
        "raw_root_family_key": raw_root_family_key,
        "terminal_family_fallback": terminal_family_fallback,
        "terminal_family_key": terminal_family_key,
        "terminal_family_source": terminal_family_source,
    })
