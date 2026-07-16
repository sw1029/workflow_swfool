from __future__ import annotations

from ..runtime_dependencies import (
    ROOT_KEY_KEYS,
    bool_value,
    call_adapter,
    first_named_value,
    load_json_value,
    load_json_values,
    normalize_previous_accepted_baseline,
    normalize_repo_owned_source_roots,
    quality_high_water_for_policy,
    rel_path,
    validator_integrity_gate,
)

from ..evaluation_frame import _EvaluationFrame


def _evaluate_failure_baseline(frame: _EvaluationFrame) -> None:
    (
        args, domain_adapter, family_key, gate_inputs, latest, output_delta, paths,
        prev_fingerprint, prev_high, quality, quality_delta_policy, root, runner_validation,
    ) = frame.require(
        'args', 'domain_adapter', 'family_key', 'gate_inputs', 'latest', 'output_delta',
        'paths', 'prev_fingerprint', 'prev_high', 'quality', 'quality_delta_policy', 'root',
        'runner_validation',
    )
    failure_autopsies = load_json_values(root, getattr(args, "failure_autopsy_json", []) or [])
    validator_gate = validator_integrity_gate(runner_validation, output_delta, gate_inputs)
    if bool_value(validator_gate.get("constrains_disposition")):
        gate_inputs.append({"name": "validator_integrity_gate", **validator_gate})
    measurement_ids_value = load_json_value(root, getattr(args, "measurement_check_ids_json", None))
    current_root_key = (
        args.root_key
        or first_named_value([runner_validation, output_delta, quality, gate_inputs], ROOT_KEY_KEYS)
        or family_key
    )
    repo_owned_source_roots_value, repo_owned_source_roots_error = call_adapter(
        domain_adapter,
        "repo_owned_source_roots",
        root=root,
        artifact_paths=[rel_path(root, path) for path in paths],
        quality_vector=quality,
        output_delta=output_delta,
        runner_validation=runner_validation,
        family_key=family_key,
        root_key=current_root_key,
    )
    repo_owned_source_roots = normalize_repo_owned_source_roots(repo_owned_source_roots_value)
    repo_owned_source_roots_status = (
        "provided"
        if repo_owned_source_roots
        else ("error" if repo_owned_source_roots_error else "not_provided")
    )
    previous_baseline_source = "registry_latest"
    previous_baseline_error: str | None = None
    previous_baseline_value, previous_baseline_call_error = call_adapter(
        domain_adapter,
        "previous_accepted_fp",
        root=root,
        artifact_paths=[rel_path(root, path) for path in paths],
        quality_vector=quality,
        output_delta=output_delta,
        runner_validation=runner_validation,
        family_key=family_key,
        root_key=current_root_key,
        registry_latest=latest,
    )
    previous_adapter_fp, previous_adapter_high, previous_adapter_reason = normalize_previous_accepted_baseline(previous_baseline_value)
    if previous_baseline_call_error:
        previous_baseline_error = previous_baseline_call_error
    elif previous_adapter_reason:
        previous_baseline_error = previous_adapter_reason
    if previous_adapter_fp:
        prev_fingerprint = previous_adapter_fp
        previous_baseline_source = "domain_adapter.previous_accepted_fp"
    if previous_adapter_high:
        prev_high = {**prev_high, **previous_adapter_high}
        previous_baseline_source = "domain_adapter.previous_accepted_fp"
    prev_high = quality_high_water_for_policy(prev_high, quality_delta_policy)
    frame.update({
        "current_root_key": current_root_key,
        "failure_autopsies": failure_autopsies,
        "measurement_ids_value": measurement_ids_value,
        "prev_fingerprint": prev_fingerprint,
        "prev_high": prev_high,
        "previous_adapter_high": previous_adapter_high,
        "previous_baseline_error": previous_baseline_error,
        "previous_baseline_source": previous_baseline_source,
        "repo_owned_source_roots": repo_owned_source_roots,
        "repo_owned_source_roots_error": repo_owned_source_roots_error,
        "repo_owned_source_roots_status": repo_owned_source_roots_status,
        "validator_gate": validator_gate,
    })
