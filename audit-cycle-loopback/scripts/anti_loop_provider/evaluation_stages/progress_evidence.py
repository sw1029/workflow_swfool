from __future__ import annotations

from ..runtime_dependencies import (
    apply_gate_artifact_compatibility,
    bool_value,
    call_adapter,
    coverage_quality_delta_reconciliation_gate,
    evidence_provenance_gate,
    find_coverage_quality_delta_gate,
    load_json_value,
    provider_scale_dispatch_gate,
    rel_path,
    vacuous_corrective_gate,
)

from ..evaluation_frame import _EvaluationFrame


def _evaluate_progress_evidence(frame: _EvaluationFrame) -> None:
    (
        args, attested_coverage_fields, attested_substance_fields, bind_artifact_gate,
        coverage_gate, domain_adapter, evidence_provenance, evidence_provenance_error,
        evidence_provenance_provided, gate_inputs, independent_coverage_fields,
        independent_substance_fields, output_delta, paths, prev_high, provider_request_count,
        quality, root, runner_validation, self_grounded_fields, source_separation_gate,
        substance_gate,
    ) = frame.require(
        'args', 'attested_coverage_fields', 'attested_substance_fields', 'bind_artifact_gate',
        'coverage_gate', 'domain_adapter', 'evidence_provenance', 'evidence_provenance_error',
        'evidence_provenance_provided', 'gate_inputs', 'independent_coverage_fields',
        'independent_substance_fields', 'output_delta', 'paths', 'prev_high',
        'provider_request_count', 'quality', 'root', 'runner_validation',
        'self_grounded_fields', 'source_separation_gate', 'substance_gate',
    )
    evidence_gate = evidence_provenance_gate(
        hook_provided=evidence_provenance_provided,
        provenance=evidence_provenance,
        independent_fields=[*independent_coverage_fields, *independent_substance_fields],
        attested_fields=[*attested_coverage_fields, *attested_substance_fields],
        adapter_error=evidence_provenance_error,
        self_grounded_fields=sorted(self_grounded_fields),
        source_separation_gate=source_separation_gate,
    )
    output_delta_coverage_gate = find_coverage_quality_delta_gate(output_delta)
    coverage_reconciliation_gate = coverage_quality_delta_reconciliation_gate(coverage_gate, output_delta_coverage_gate, args.epsilon)
    if not bool_value(coverage_gate.get("artifact_decision_scope_allowed")):
        coverage_reconciliation_gate = apply_gate_artifact_compatibility(
            coverage_reconciliation_gate,
            coverage_gate.get("gate_compatibility") or {},
        )
    coverage_reconciliation_blocks = bool_value(coverage_reconciliation_gate.get("constrains_disposition"))
    if coverage_reconciliation_blocks:
        gate_inputs.append({"name": "coverage_quality_delta_reconciliation_gate", **coverage_reconciliation_gate})
    dispatch_gate = provider_scale_dispatch_gate(prev_high, coverage_gate, provider_request_count)
    if not bool_value(coverage_gate.get("artifact_decision_scope_allowed")):
        dispatch_gate = apply_gate_artifact_compatibility(
            dispatch_gate,
            coverage_gate.get("gate_compatibility") or {},
        )
    if bool_value(dispatch_gate.get("constrains_disposition")):
        gate_inputs.append({"name": "provider_scale_dispatch_gate", **dispatch_gate})
    if bool_value(substance_gate.get("constrains_disposition")):
        gate_inputs.append({"name": "substance_delta_gate", **substance_gate})
    corrective_value = load_json_value(root, getattr(args, "corrective_resolution_json", None))
    if corrective_value is None:
        corrective_value, corrective_error = call_adapter(
            domain_adapter,
            "corrective_resolution",
            root=root,
            artifact_paths=[rel_path(root, path) for path in paths],
            quality_vector=quality,
            output_delta=output_delta,
            runner_validation=runner_validation,
        )
        if corrective_error:
            corrective_value = {"corrective_resolution_error": corrective_error}
    corrective_gate = vacuous_corrective_gate(corrective_value)
    corrective_gate = bind_artifact_gate(
        "vacuous_corrective_gate",
        corrective_gate,
        pass_fields=("surface_corrective_noop",),
        computed_from_decision_artifact=True,
    )
    if bool_value(corrective_gate.get("constrains_disposition")):
        gate_inputs.append({"name": "vacuous_corrective_gate", **corrective_gate})
    frame.update({
        "corrective_gate": corrective_gate,
        "coverage_reconciliation_blocks": coverage_reconciliation_blocks,
        "coverage_reconciliation_gate": coverage_reconciliation_gate,
        "dispatch_gate": dispatch_gate,
        "evidence_gate": evidence_gate,
    })
