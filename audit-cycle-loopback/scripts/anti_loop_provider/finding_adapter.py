from __future__ import annotations

from .runtime_dependencies import (
    Any,
    bool_value,
)

from .evaluation_frame import _require_values


def _collect_adapter_findings(state: dict[str, Any]) -> None:
    (
        adapter_fingerprint_error, advice_gate, corrective_gate, current_terminal_outcome_key,
        facet_map_error, facet_root_map_missing, findings, latest_terminal_family,
        partial_progress_gate, previous_baseline_error, previous_baseline_source,
        raw_root_family_key, structure_error, structure_gate, terminal_family_key,
    ) = _require_values(
        state,
        (
            'adapter_fingerprint_error', 'advice_gate', 'corrective_gate',
            'current_terminal_outcome_key', 'facet_map_error', 'facet_root_map_missing',
            'findings', 'latest_terminal_family', 'partial_progress_gate',
            'previous_baseline_error', 'previous_baseline_source', 'raw_root_family_key',
            'structure_error', 'structure_gate', 'terminal_family_key',
        ),
    )
    if bool_value(corrective_gate.get("surface_corrective_noop")):
        findings.append(
            {
                "severity": "block",
                "code": "vacuous_corrective_noop",
                "message": "corrective/backfill rows attempted work without resolving any lane; exclude those rows from produced or semantic delta evidence.",
                "evidence": corrective_gate,
            }
        )
    if bool_value(advice_gate.get("advice_metrics_stale")):
        findings.append(
            {
                "severity": "warn",
                "code": "advice_metrics_stale",
                "message": "advice declares output fingerprint claims that do not match the current adapter/output fingerprint; refresh or reclassify the advice before relying on its headline metrics.",
                "evidence": advice_gate,
            }
        )
    if bool_value(advice_gate.get("gate_result_regression_stale")):
        findings.append(
            {
                "severity": "warn",
                "code": "gate_result_regression_stale",
                "message": "a gate verdict regressed from passed to blocked under a stable environment fingerprint; route through the existing advice-freshness/self-check path before trusting stale headline gate state.",
                "evidence": advice_gate,
            }
        )
    if str(partial_progress_gate.get("status")) == "warn":
        findings.append(
            {
                "severity": "warn",
                "code": "partial_progress_axes_flatlined",
                "message": "adapter-reported partial progress axes exist while quality/substance high-water remains flat; recommend decomposing all-or-nothing gates rather than adding another detector.",
                "evidence": partial_progress_gate,
            }
        )
    if adapter_fingerprint_error:
        findings.append(
            {
                "severity": "warn",
                "code": "domain_adapter_output_fingerprint_failed",
                "message": "domain adapter output_fingerprint() failed; advice freshness can only use the quality vector fingerprint.",
                "evidence": {"error": adapter_fingerprint_error},
            }
        )
    if previous_baseline_error:
        findings.append(
            {
                "severity": "warn",
                "code": "domain_adapter_previous_accepted_fp_failed",
                "message": "domain adapter previous_accepted_fp() failed or returned an unusable baseline; registry fallback was used where available.",
                "evidence": {"error": previous_baseline_error, "baseline_source": previous_baseline_source},
            }
        )
    if bool_value(structure_gate.get("structure_consolidation_recommended")):
        findings.append(
            {
                "severity": "warn",
                "code": "structure_consolidation_recommended",
                "message": "domain adapter structure metrics recommend Class C consolidation or module-boundary work.",
                "evidence": structure_gate,
            }
        )
    if structure_error:
        findings.append(
            {
                "severity": "warn",
                "code": "domain_adapter_structure_metrics_failed",
                "message": "domain adapter structure_metrics() failed; structure consolidation signal was skipped.",
                "evidence": {"error": structure_error},
            }
        )
    if facet_map_error:
        findings.append(
            {
                "severity": "warn",
                "code": "domain_adapter_facet_root_map_failed",
                "message": "domain adapter facet_root_map() failed; terminal-outcome fallback grouped this cycle by artifact family and terminal outcome.",
                "evidence": {
                    "error": facet_map_error,
                    "terminal_outcome_key": current_terminal_outcome_key,
                    "terminal_outcome_family_key": terminal_family_key,
                },
            }
        )
    elif facet_root_map_missing:
        findings.append(
            {
                "severity": "warn",
                "code": "facet_root_map_missing",
                "message": "facet_root_map is unavailable; terminal-outcome fallback grouped this cycle by artifact family and terminal outcome so proximate blocker mutations cannot reset same-family caps.",
                "evidence": {
                    "terminal_outcome_key": current_terminal_outcome_key,
                    "terminal_outcome_family_key": terminal_family_key,
                    "raw_root_family_key": raw_root_family_key,
                    "previous_cycle_id": (latest_terminal_family or {}).get("cycle_id"),
                },
            }
        )
