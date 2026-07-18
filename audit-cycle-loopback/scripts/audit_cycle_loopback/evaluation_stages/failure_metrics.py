from __future__ import annotations

from ..runtime_dependencies import (
    bind_adapter_invocation_result,
    call_adapter,
    extract_check_ids,
    extract_frontier_observations,
    frontier_key,
    load_json_value,
    normalize_evidence_provenance,
    numeric_vector,
    rel_path,
    vector_delta_gate,
)

from ..evaluation_frame import _EvaluationFrame


def _evaluate_failure_metrics(frame: _EvaluationFrame) -> None:
    (
        args, current_root_key, domain_adapter, family_key, gate_inputs, latest,
        measurement_ids_value, output_delta, paths, quality, quality_delta_policy, root,
        runner_validation,
    ) = frame.require(
        'args', 'current_root_key', 'domain_adapter', 'family_key', 'gate_inputs', 'latest',
        'measurement_ids_value', 'output_delta', 'paths', 'quality',
        'quality_delta_policy', 'root', 'runner_validation',
    )
    current_check_ids = set(getattr(args, "measurement_check_id", []) or [])
    current_check_ids.update(extract_check_ids(measurement_ids_value, runner_validation, output_delta, quality, gate_inputs))
    current_frontiers = {frontier_key(item) for item in getattr(args, "measurement_frontier", []) or [] if item}
    current_frontiers.update(extract_frontier_observations(runner_validation, output_delta, quality, gate_inputs))
    substance_value = load_json_value(root, getattr(args, "substance_metrics_json", None))
    if substance_value is None:
        substance_value, substance_error = call_adapter(
            domain_adapter,
            "substance_metrics",
            root=root,
            artifact_paths=[rel_path(root, path) for path in paths],
            quality_vector=quality,
            output_delta=output_delta,
            runner_validation=runner_validation,
        )
        if substance_error:
            substance_value = {"substance_metrics_error": substance_error}
    if isinstance(substance_value, dict) and isinstance(substance_value.get("substance_metrics"), dict):
        current_substance = substance_value["substance_metrics"]
    elif isinstance(substance_value, dict) and isinstance(substance_value.get("current_substance_vector"), dict):
        current_substance = substance_value["current_substance_vector"]
    else:
        current_substance = substance_value if isinstance(substance_value, dict) else {}
    previous_substance = (
        (latest or {}).get("substance_metrics")
        or (latest or {}).get("current_substance_vector")
        or ((latest or {}).get("substance_delta_gate") or {}).get("current_substance_vector")
        or {}
    )
    substance_gate = vector_delta_gate(
        gate_name="G-SUBSTANCE",
        current=current_substance,
        previous=previous_substance,
        pass_field="substance_delta_pass",
        current_field="current_substance_vector",
        previous_field="previous_substance_vector",
        epsilon=args.epsilon,
    )
    evidence_provenance_value, evidence_provenance_error = call_adapter(
        domain_adapter,
        "evidence_provenance",
        root=root,
        artifact_paths=[rel_path(root, path) for path in paths],
        quality_vector=quality,
        substance_metrics=current_substance,
        output_delta=output_delta,
        runner_validation=runner_validation,
        family_key=family_key,
        root_key=current_root_key,
        candidate_metric_keys=[*quality_delta_policy["keys"], *sorted(numeric_vector(current_substance))],
    )
    evidence_provenance, evidence_provenance_provided = normalize_evidence_provenance(evidence_provenance_value)
    provenance_status = (
        str(
            evidence_provenance_value.get("evaluation_status")
            or evidence_provenance_value.get("status")
            or ""
        ).strip().lower()
        if isinstance(evidence_provenance_value, dict)
        else ""
    )
    provenance_contract_valid = isinstance(evidence_provenance_value, (dict, list))
    provenance_accepted = bool(
        provenance_contract_valid
        and evidence_provenance_provided
        and evidence_provenance
        and not evidence_provenance_error
        and provenance_status
        not in {"fail", "failed", "fail_quiet", "not_evaluated", "unavailable"}
    )
    bind_adapter_invocation_result(
        "evidence_provenance",
        return_contract_valid=provenance_contract_valid,
        semantic_accepted=provenance_accepted,
        value_consumed_by_decision=provenance_accepted,
    )
    frame.update({
        "current_check_ids": current_check_ids,
        "current_frontiers": current_frontiers,
        "current_substance": current_substance,
        "evidence_provenance": evidence_provenance,
        "evidence_provenance_error": evidence_provenance_error,
        "evidence_provenance_provided": evidence_provenance_provided,
        "evidence_provenance_value": evidence_provenance_value,
        "substance_gate": substance_gate,
    })
