from __future__ import annotations

from .common import *

def _evaluate_impl(args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]], bool]:
    root = Path(args.root).resolve()
    registry_path = Path(args.registry_path)
    if not registry_path.is_absolute():
        registry_path = root / registry_path
    legacy_family_key = normalize_family_key(args.artifact_family, args.semantic_signature)
    family_key = legacy_family_key
    registry_rows = load_registry(registry_path)
    existing_cycle = next(
        (row for row in reversed(registry_rows) if row.get("family_key") == family_key and row.get("cycle_id") == args.cycle_id),
        None,
    )
    latest = next((row for row in reversed(registry_rows) if row.get("family_key") == family_key), None)
    prev_high = dict((latest or {}).get("high_water_mark") or default_high_water())
    prev_count = int((latest or {}).get("micro_hardening_count") or 0)
    prev_fingerprint = (latest or {}).get("current_output_fingerprint")

    paths = load_artifact_paths(root, args.artifact_paths_json, args.artifact_path)
    changed_files = load_changed_files(
        root,
        getattr(args, "changed_files_json", None),
        getattr(args, "changed_file", []) or [],
    )
    adapter_candidates = domain_adapter_candidate_paths(root, getattr(args, "domain_adapter", None))
    adapter_registered = bool(adapter_candidates)
    adapter_expected_path = adapter_candidates[0].expanduser().resolve().as_posix() if adapter_candidates else None
    domain_adapter, domain_adapter_path, domain_adapter_error = load_domain_adapter(root, getattr(args, "domain_adapter", None))
    adapter_load_gate = adapter_wiring_gate(
        registered=adapter_registered,
        loaded=domain_adapter is not None,
        expected_path=adapter_expected_path,
        loaded_path=domain_adapter_path,
        load_error=domain_adapter_error,
    )
    quality, evidence_paths, insufficient_reason = (
        ({}, [], domain_adapter_error)
        if domain_adapter_error
        else compute_quality(root, paths, domain_adapter)
    )
    provider_request_count = max(0, int(args.provider_request_count or 0))
    gate_inputs: list[dict[str, Any]] = []
    if bool_value(adapter_load_gate.get("constrains_disposition")):
        gate_inputs.append({"name": "adapter_wiring_gate", **adapter_load_gate})
    for raw_gate in getattr(args, "gate_state_json", []) or []:
        gate_inputs.extend(extract_disposition_gates(load_json_value(root, raw_gate)))
    runner_validation = load_json_value(root, getattr(args, "runner_validation_json", None))
    output_delta = load_json_value(root, getattr(args, "output_delta_json", None))
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
    preliminary_semantic = False if insufficient_reason else semantic_progress_from_high_water(quality, prev_high, provider_request_count, args.epsilon)
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
    failure_contexts = [runner_validation, output_delta, quality, gate_inputs, *failure_autopsies]
    root_dominant_parameter_key = (
        first_named_value(failure_contexts, {"root_dominant_parameter_key", "dominant_parameter_key", "deficit_axis"})
        or current_root_key
    )
    execution_stage_ladder_value, execution_stage_ladder_error = call_adapter(
        domain_adapter,
        "execution_stage_ladder",
        root=root,
        artifact_paths=[rel_path(root, path) for path in paths],
        quality_vector=quality,
        output_delta=output_delta,
        runner_validation=runner_validation,
        failure_autopsies=failure_autopsies,
        family_key=family_key,
        root_key=current_root_key,
        root_family_key=current_root_family_key,
    )
    if execution_stage_ladder_value is None:
        execution_stage_ladder_value = first_field_value(failure_contexts, {"execution_stage_ladder", "stage_ladder"})
    terminal_stage_map_value, terminal_stage_map_error = call_adapter(
        domain_adapter,
        "terminal_classification_stage_map",
        root=root,
        artifact_paths=[rel_path(root, path) for path in paths],
        quality_vector=quality,
        output_delta=output_delta,
        runner_validation=runner_validation,
        failure_autopsies=failure_autopsies,
        family_key=family_key,
        root_key=current_root_key,
        root_family_key=current_root_family_key,
    )
    failure_surface_gate = terminal_stage_resolution_gate(
        ladder_value=execution_stage_ladder_value,
        classification_map_value=terminal_stage_map_value,
        contexts=failure_contexts,
        root_family_key=current_root_family_key,
        dominant_parameter=str(root_dominant_parameter_key),
    )
    if execution_stage_ladder_error:
        failure_surface_gate["execution_stage_ladder_error"] = execution_stage_ladder_error
    if terminal_stage_map_error:
        failure_surface_gate["terminal_classification_stage_map_error"] = terminal_stage_map_error
    effective_count_key = str(failure_surface_gate.get("failure_surface_count_key") or current_root_family_key)
    if bool_value(failure_surface_gate.get("constrains_disposition")):
        gate_inputs.append({"name": "failure_surface_stage_gate", **failure_surface_gate})
    input_contract_gate = same_input_contract_gate(failure_contexts)
    if bool_value(input_contract_gate.get("constrains_disposition")):
        gate_inputs.append({"name": "same_input_contract_gate", **input_contract_gate})
    instrumentation_threshold_value, instrumentation_threshold_error = call_adapter(
        domain_adapter,
        "instrumentation_trigger_threshold",
        root=root,
        artifact_paths=[rel_path(root, path) for path in paths],
        quality_vector=quality,
        output_delta=output_delta,
        runner_validation=runner_validation,
        failure_autopsies=failure_autopsies,
        family_key=family_key,
        root_key=current_root_key,
        root_family_key=current_root_family_key,
    )
    instrumentation_threshold = (
        int(float_value(instrumentation_threshold_value))
        or int(getattr(args, "instrumentation_trigger_threshold", INSTRUMENTATION_TRIGGER_THRESHOLD_DEFAULT))
        or INSTRUMENTATION_TRIGGER_THRESHOLD_DEFAULT
    )
    diagnostics_gate = diagnostics_unavailable_gate(
        registry_rows=registry_rows,
        failure_surface_count_key=failure_surface_gate.get("failure_surface_count_key"),
        contexts=failure_contexts,
        threshold=instrumentation_threshold,
    )
    if instrumentation_threshold_error:
        diagnostics_gate["adapter_error"] = instrumentation_threshold_error
    if bool_value(diagnostics_gate.get("constrains_disposition")):
        gate_inputs.append({"name": "diagnostics_unavailable_gate", **diagnostics_gate})
    current_check_ids = set(getattr(args, "measurement_check_id", []) or [])
    current_check_ids.update(extract_check_ids(measurement_ids_value, runner_validation, output_delta, quality, gate_inputs))
    current_frontiers = {frontier_key(item) for item in getattr(args, "measurement_frontier", []) or [] if item}
    current_frontiers.update(extract_frontier_observations(runner_validation, output_delta, quality, gate_inputs))
    coverage_gate = coverage_quality_delta_gate(quality, prev_high, provider_request_count, args.epsilon)
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
        candidate_metric_keys=[*QUALITY_DELTA_KEYS, *sorted(numeric_vector(current_substance))],
    )
    evidence_provenance, evidence_provenance_provided = normalize_evidence_provenance(evidence_provenance_value)
    coverage_gate, independent_coverage_fields, attested_coverage_fields = apply_evidence_provenance_filter(
        coverage_gate,
        improved_key="improved_fields",
        pass_key="quality_delta_pass",
        provenance=evidence_provenance,
        hook_provided=evidence_provenance_provided,
    )
    substance_gate, independent_substance_fields, attested_substance_fields = apply_evidence_provenance_filter(
        substance_gate,
        improved_key="improved_axes",
        pass_key="substance_delta_pass",
        provenance=evidence_provenance,
        hook_provided=evidence_provenance_provided,
    )
    source_separation_gate = verification_source_separation_gate(
        provenance_value=evidence_provenance_value,
        verified_artifact_paths=[rel_path(root, path) for path in paths],
        independently_verified_fields=[*independent_coverage_fields, *independent_substance_fields],
    )
    downgraded_fields = set(source_separation_gate.get("independently_verified_downgraded_fields") or [])
    if downgraded_fields:
        coverage_downgraded = [field for field in independent_coverage_fields if field in downgraded_fields]
        substance_downgraded = [field for field in independent_substance_fields if field in downgraded_fields]
        independent_coverage_fields = [field for field in independent_coverage_fields if field not in downgraded_fields]
        independent_substance_fields = [field for field in independent_substance_fields if field not in downgraded_fields]
        attested_coverage_fields = sorted(set(attested_coverage_fields + coverage_downgraded))
        attested_substance_fields = sorted(set(attested_substance_fields + substance_downgraded))
        if coverage_downgraded:
            coverage_gate["improved_fields"] = independent_coverage_fields
            coverage_gate["quality_delta_pass"] = bool(independent_coverage_fields)
            coverage_gate["status"] = "pass" if independent_coverage_fields else "block"
            coverage_gate["independently_verified_fields"] = independent_coverage_fields
            coverage_gate["producer_attested_fields"] = attested_coverage_fields
            coverage_gate["attested_only_movement"] = bool(attested_coverage_fields and not independent_coverage_fields)
        if substance_downgraded:
            substance_gate["improved_axes"] = independent_substance_fields
            substance_gate["substance_delta_pass"] = bool(independent_substance_fields)
            substance_gate["status"] = "pass" if independent_substance_fields else "block"
            substance_gate["independently_verified_fields"] = independent_substance_fields
            substance_gate["producer_attested_fields"] = attested_substance_fields
            substance_gate["attested_only_movement"] = bool(attested_substance_fields and not independent_substance_fields)
    evidence_gate = evidence_provenance_gate(
        hook_provided=evidence_provenance_provided,
        provenance=evidence_provenance,
        independent_fields=[*independent_coverage_fields, *independent_substance_fields],
        attested_fields=[*attested_coverage_fields, *attested_substance_fields],
        adapter_error=evidence_provenance_error,
        source_separation_gate=source_separation_gate,
    )
    output_delta_coverage_gate = find_coverage_quality_delta_gate(output_delta)
    coverage_reconciliation_gate = coverage_quality_delta_reconciliation_gate(coverage_gate, output_delta_coverage_gate, args.epsilon)
    coverage_reconciliation_blocks = bool_value(coverage_reconciliation_gate.get("constrains_disposition"))
    if coverage_reconciliation_blocks:
        gate_inputs.append({"name": "coverage_quality_delta_reconciliation_gate", **coverage_reconciliation_gate})
    dispatch_gate = provider_scale_dispatch_gate(prev_high, coverage_gate, provider_request_count)
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
    if bool_value(corrective_gate.get("constrains_disposition")):
        gate_inputs.append({"name": "vacuous_corrective_gate", **corrective_gate})
    acceptance_value = load_json_value(root, getattr(args, "acceptance_reachability_json", None))
    acceptance_error: str | None = None
    if acceptance_value is None:
        acceptance_value, acceptance_error = call_adapter(
            domain_adapter,
            "acceptance_reachability",
            root=root,
            artifact_paths=[rel_path(root, path) for path in paths],
            quality_vector=quality,
            output_delta=output_delta,
            runner_validation=runner_validation,
            family_key=family_key,
            root_key=current_root_key,
        )
    target_required_verifier_error: str | None = None
    target_required_verifier_value, target_required_verifier_error = call_adapter(
        domain_adapter,
        "target_required_verifier",
        root=root,
        target=acceptance_target_from_value(acceptance_value),
        acceptance=acceptance_value,
        acceptance_reachability=acceptance_value,
        artifact_paths=[rel_path(root, path) for path in paths],
        quality_vector=quality,
        output_delta=output_delta,
        runner_validation=runner_validation,
        family_key=family_key,
        root_key=current_root_key,
    )
    if target_required_verifier_value is not None:
        acceptance_value = merge_acceptance_verifier_contract(acceptance_value, target_required_verifier_value)
    reachability_gate = acceptance_reachability_gate(acceptance_value)
    if bool_value(reachability_gate.get("constrains_disposition")):
        gate_inputs.append({"name": "acceptance_reachability_gate", **reachability_gate})
    metric_validity_value = load_json_value(root, getattr(args, "metric_validity_json", None))
    metric_validity_error: str | None = None
    if metric_validity_value is None:
        metric_validity_value, metric_validity_error = call_adapter(
            domain_adapter,
            "metric_validity_self_check",
            root=root,
            artifact_paths=[rel_path(root, path) for path in paths],
            quality_vector=quality,
            output_delta=output_delta,
            runner_validation=runner_validation,
            family_key=family_key,
            root_key=current_root_key,
        )
    metric_validity_gate = oracle_metric_validity_gate(metric_validity_value)
    if bool_value(metric_validity_gate.get("constrains_disposition")):
        gate_inputs.append({"name": "oracle_metric_validity_gate", **metric_validity_gate})
    adapter_fingerprint_value, adapter_fingerprint_error = call_adapter(
        domain_adapter,
        "output_fingerprint",
        root=root,
        artifact_paths=[rel_path(root, path) for path in paths],
        quality_vector=quality,
    )
    if adapter_fingerprint_value and not quality.get("current_output_fingerprint"):
        quality["current_output_fingerprint"] = str(adapter_fingerprint_value)
    advice_gate = advice_freshness_gate(root, quality.get("current_output_fingerprint"), [gate_inputs, runner_validation, output_delta])
    structure_value, structure_error = call_adapter(
        domain_adapter,
        "structure_metrics",
        root=root,
        artifact_paths=[rel_path(root, path) for path in paths],
        quality_vector=quality,
        output_delta=output_delta,
        runner_validation=runner_validation,
        family_key=family_key,
        root_key=current_root_key,
    )
    if structure_error:
        structure_value = {"structure_metrics_error": structure_error}
    structure_gate = structure_metrics_gate(structure_value)
    measurement_details = measurement_progress_details(
        registry_rows,
        family_key,
        current_root_key,
        current_root_family_key,
        current_check_ids,
        current_frontiers,
    )
    measurement_progress = bool_value(measurement_details["measurement_progress"])
    measurement_streak_value = int(measurement_details["measurement_streak"])
    measurement_progress_allowed = (
        measurement_progress
        and measurement_streak_value <= args.measurement_streak_cap
        and bool_value(coverage_gate.get("quality_delta_pass"))
        and bool_value(substance_gate.get("substance_delta_pass"))
        and not coverage_reconciliation_blocks
    )
    if bool_value(metric_validity_gate.get("metric_goal_productive_excluded")):
        measurement_progress_allowed = False
    blocker_sources: list[Any] = [runner_validation, output_delta, quality, gate_inputs, args.semantic_signature, args.artifact_family]
    current_blocker_signature = (
        args.blocker_signature
        or first_named_value(blocker_sources, BLOCKER_SIGNATURE_KEYS)
        or args.semantic_signature
        or "unknown"
    )
    blocker_root_family = current_root_family_key if facet_root_map_missing else collapse_root_family(facet_root_map, current_root_key, current_blocker_signature)
    latest_blocker = next((row for row in reversed(registry_rows) if row_root_family(row) == blocker_root_family), latest_terminal_family or latest)
    current_rung = normalize_ladder_rung(args.blocker_rung) or infer_ladder_rung(*blocker_sources)
    mutation_kind = blocker_mutation_kind(current_blocker_signature, current_rung, blocker_root_family, latest_blocker)
    previous_forward_count = forward_mutation_streak(registry_rows, family_key)
    current_forward_count = previous_forward_count + (1 if mutation_kind == "forward_mutation" else 0)
    forward_budget_remaining = max(0, args.max_forward_mutations - current_forward_count)
    force_implementation_cycle = mutation_kind == "forward_mutation" and forward_budget_remaining == 0
    disagreement = validator_disagreement_finding(runner_validation, output_delta)
    substance_delta_pass = bool_value(substance_gate.get("substance_delta_pass"))

    if insufficient_reason:
        semantic_progress = False
        evidence_class = "insufficient_evidence"
        high_water = prev_high
        count = previous_micro_hardening_count_for_count_key(registry_rows, effective_count_key) + 1
        disposition = "conservative_hold"
        hard_stop = True
    else:
        semantic_progress = bool_value(coverage_gate.get("quality_delta_pass"))
        evidence_class = "computed"
        allowed_high_water_keys = set(coverage_gate.get("improved_fields") or []) if evidence_provenance_provided else None
        high_water = (
            updated_high_water(quality, prev_high, provider_request_count, allowed_high_water_keys)
            if semantic_progress
            else prev_high
        )
        previous_family_count = previous_micro_hardening_count_for_count_key(registry_rows, effective_count_key)
        count = 0 if semantic_progress else previous_family_count + 1
        if semantic_progress:
            disposition = "open"
            hard_stop = False
        elif count >= args.threshold:
            disposition = "provider_or_semantic_transition_or_terminal"
            hard_stop = True
        else:
            disposition = "prefer_provider_or_semantic"
            hard_stop = False

    outcome_changed = terminal_outcome_changed(output_delta, changed_vs_previous, semantic_progress)
    delta_class = observed_delta_class(output_delta, changed_vs_previous, semantic_progress)
    forward_mutation_vacuous = mutation_kind == "forward_mutation" and not outcome_changed
    if forward_mutation_vacuous:
        hard_stop = True
    if mutation_kind == "forward_mutation" and outcome_changed and not disagreement and not coverage_reconciliation_blocks:
        changed_vs_previous = True
        count = 0
        hard_stop = False
        if disposition in {"conservative_hold", "provider_or_semantic_transition_or_terminal"}:
            disposition = "forward_mutation_goal_productive_candidate"
    if measurement_progress_allowed:
        hard_stop = False
        if disposition in {"conservative_hold", "provider_or_semantic_transition_or_terminal"}:
            disposition = "measurement_progress_goal_productive_candidate"
    if coverage_reconciliation_blocks:
        hard_stop = True
    if disagreement:
        hard_stop = True
    if bool_value(validator_gate.get("hard_stop_required")):
        hard_stop = True

    task_correction_class = classify_task_correction(
        current_check_ids=current_check_ids,
        current_frontiers=current_frontiers,
        provider_request_count=provider_request_count,
        changed_vs_previous=changed_vs_previous,
        semantic_progress=semantic_progress,
        values=[runner_validation, output_delta, quality, gate_inputs, args.semantic_signature, args.artifact_family],
    )
    detection_only = task_correction_class == "detection" and not semantic_progress
    detection_streak = detection_only_streak(registry_rows, blocker_root_family, detection_only)
    requires_correction_or_terminal = detection_streak >= args.detection_only_streak_cap and not semantic_progress
    if requires_correction_or_terminal:
        hard_stop = True
    current_no_goal_distance_delta = not (
        bool_value(coverage_gate.get("quality_delta_pass"))
        or bool_value(substance_gate.get("substance_delta_pass"))
    )
    partial_progress_value, partial_progress_error = call_adapter(
        domain_adapter,
        "partial_progress_axes",
        root=root,
        artifact_paths=[rel_path(root, path) for path in paths],
        quality_vector=quality,
        output_delta=output_delta,
        runner_validation=runner_validation,
        family_key=family_key,
        root_key=current_root_key,
        current_no_goal_distance_delta=current_no_goal_distance_delta,
    )
    partial_progress_gate = partial_progress_axes_gate(partial_progress_value, current_no_goal_distance_delta)
    partial_progress_gate["adapter_error"] = partial_progress_error
    adapter_contract_unmet = adapter_contract_unmet_fields(
        facet_root_map_missing=facet_root_map_missing,
        substance_gate=substance_gate,
        quality=quality,
    )
    adapter_gate = adapter_mandate_gate(
        registry_rows,
        artifact_family=args.artifact_family,
        contract_unmet=adapter_contract_unmet,
        current_no_delta=current_no_goal_distance_delta,
        cap=getattr(args, "adapter_mandate_streak_cap", ADAPTER_MANDATE_STREAK_CAP_DEFAULT),
    )
    if bool_value(adapter_load_gate.get("adapter_wiring_defect")):
        adapter_gate["adapter_mandate_required"] = False
        adapter_gate["status"] = "ok"
        adapter_gate["adapter_wiring_defect_supersedes_adapter_mandate"] = True
    if bool_value(adapter_load_gate.get("adapter_wiring_defect")):
        hard_stop = True
        disposition = "self_inflicted_gate_defect"
    elif bool_value(adapter_gate.get("adapter_mandate_required")):
        hard_stop = True
        disposition = "adapter_mandate_required"
        gate_inputs.append({"name": "adapter_mandate_gate", **adapter_gate})
    chain_gate = cumulative_goal_distance_gate(
        registry_rows,
        artifact_family=args.artifact_family,
        root_family_key=current_root_family_key,
        facet_root_map_missing=facet_root_map_missing,
        current_no_delta=current_no_goal_distance_delta,
        high_water=high_water,
        current_cycle_id=args.cycle_id,
        cap=getattr(args, "cumulative_chain_streak_cap", CUMULATIVE_CHAIN_STREAK_CAP_DEFAULT),
    )
    primary_metric_value, primary_metric_error = call_adapter(
        domain_adapter,
        "primary_metric",
        root=root,
        artifact_paths=[rel_path(root, path) for path in paths],
        quality_vector=quality,
        substance_metrics=current_substance,
        output_delta=output_delta,
        runner_validation=runner_validation,
        family_key=family_key,
        root_key=current_root_key,
        root_family_key=current_root_family_key,
        previous_primary_metric=previous_primary_metric_value(latest),
        evidence_provenance=evidence_provenance,
    )
    primary_metric_gate = normalize_primary_metric_gate(
        primary_metric_value,
        previous_value=previous_primary_metric_value(latest),
        rows=registry_rows,
        scope_key=str(chain_gate.get("cumulative_goal_distance_scope_key") or family_key),
        cap=getattr(args, "cumulative_chain_streak_cap", CUMULATIVE_CHAIN_STREAK_CAP_DEFAULT),
        epsilon=args.epsilon,
        provenance=evidence_provenance,
        provenance_hook_provided=evidence_provenance_provided,
    )
    if primary_metric_error:
        primary_metric_gate["adapter_error"] = primary_metric_error
    capability_ladder_value, capability_ladder_error = call_adapter(
        domain_adapter,
        "capability_ladder",
        root=root,
        artifact_paths=[rel_path(root, path) for path in paths],
        quality_vector=quality,
        output_delta=output_delta,
        runner_validation=runner_validation,
        family_key=family_key,
        root_key=current_root_key,
        root_family_key=current_root_family_key,
        high_water=high_water,
    )
    capability_ladder_option = first_actionable_capability_ladder_option(capability_ladder_value)
    forced_retarget_gate = chain_stall_forced_retarget_gate(
        chain_gate,
        blocker_mutation=mutation_kind,
        adapter_gate=adapter_load_gate,
        capability_ladder_option=capability_ladder_option,
    )
    if capability_ladder_error:
        forced_retarget_gate["capability_ladder_error"] = capability_ladder_error
    if bool_value(forced_retarget_gate.get("constrains_disposition")):
        chain_gate["allowed_dispositions"] = ["goal_productive", "terminal_blocked", "user_escalation"]
        chain_gate["allowed_task_kinds"] = forced_retarget_gate.get("allowed_task_kinds") or []
        gate_inputs.append({"name": "chain_stall_forced_retarget_gate", **forced_retarget_gate})
    c4_user_escalation_backstop_required = False
    if bool_value(primary_metric_gate.get("primary_metric_stalled")):
        forced_task_kinds = normalize_task_kinds(forced_retarget_gate.get("allowed_task_kinds") or [])
        if forced_task_kinds:
            primary_metric_gate["allowed_task_kinds"] = sorted(forced_task_kinds)
        else:
            c4_user_escalation_backstop_required = True
            primary_metric_gate["c4_user_escalation_backstop_required"] = True
            primary_metric_gate["allowed_dispositions"] = ["user_escalation"]
        gate_inputs.append({"name": "primary_metric_gate", **primary_metric_gate})
    if (
        bool_value(chain_gate.get("cumulative_goal_distance_stalled"))
        and not bool_value(adapter_gate.get("adapter_mandate_required"))
        and not bool_value(adapter_load_gate.get("adapter_wiring_defect"))
    ):
        hard_stop = True
        disposition = "goal_productive" if bool_value(forced_retarget_gate.get("constrains_disposition")) else "terminal_blocked"
        gate_inputs.append({"name": "cumulative_goal_distance_gate", **chain_gate})
    if bool_value(reachability_gate.get("acceptance_unreachable_under_frozen_config")):
        hard_stop = True
        if not bool_value(adapter_gate.get("adapter_mandate_required")) and not bool_value(
            chain_gate.get("cumulative_goal_distance_stalled")
        ):
            disposition = "relaxation_or_escalation_required"
    if bool_value(reachability_gate.get("unverifiable_acceptance_contract")):
        hard_stop = True
        if disposition in {"open", "prefer_provider_or_semantic", "measurement_progress_goal_productive_candidate"}:
            disposition = "verifier_contract_required"
    if bool_value(metric_validity_gate.get("metric_goal_productive_excluded")):
        hard_stop = True
        if disposition in {"open", "prefer_provider_or_semantic", "measurement_progress_goal_productive_candidate"}:
            disposition = "metric_definition_correction_required"
    if bool_value(primary_metric_gate.get("primary_metric_stalled")):
        hard_stop = True
        if c4_user_escalation_backstop_required:
            disposition = "user_escalation"
        elif disposition in {"open", "prefer_provider_or_semantic", "measurement_progress_goal_productive_candidate"}:
            disposition = "primary_metric_forced_retarget_required"
    if bool_value(failure_surface_gate.get("terminal_classification_stage_contradiction")):
        hard_stop = True
        if disposition in {"open", "prefer_provider_or_semantic", "measurement_progress_goal_productive_candidate"}:
            disposition = "terminal_classification_stage_repair_required"
    if bool_value(input_contract_gate.get("same_input_contract_violation")):
        hard_stop = True
        if disposition in {"open", "prefer_provider_or_semantic", "measurement_progress_goal_productive_candidate"}:
            disposition = "input_set_contract_repair_required"
    if bool_value(diagnostics_gate.get("instrumentation_supply_required")):
        hard_stop = True
        if disposition in {"open", "prefer_provider_or_semantic", "measurement_progress_goal_productive_candidate"}:
            disposition = "instrumentation_supply_required"
    verifier_source_value, verifier_source_error = call_adapter(
        domain_adapter,
        "verifier_source_paths",
        root=root,
        artifact_paths=[rel_path(root, path) for path in paths],
        changed_files=changed_files,
        gate_results=gate_inputs,
        quality_vector=quality,
        output_delta=output_delta,
        runner_validation=runner_validation,
        family_key=family_key,
        root_key=current_root_key,
    )
    verifier_source_map, verifier_source_hook_provided = normalize_verifier_source_paths(verifier_source_value)
    verifier_coupling_gate = coupled_verifier_gate(
        changed_files=changed_files,
        verifier_source_map=verifier_source_map,
        hook_provided=verifier_source_hook_provided,
        gates=[
            adapter_load_gate,
            validator_gate,
            coverage_gate,
            coverage_reconciliation_gate,
            dispatch_gate,
            substance_gate,
            corrective_gate,
            reachability_gate,
            metric_validity_gate,
            advice_gate,
            structure_gate,
            adapter_gate,
            chain_gate,
            forced_retarget_gate,
            primary_metric_gate,
            *gate_inputs,
        ],
    )
    if verifier_source_error:
        verifier_coupling_gate["adapter_error"] = verifier_source_error
    if bool_value(verifier_coupling_gate.get("pass_with_coupled_verifier")):
        hard_stop = True
        if disposition in {"open", "prefer_provider_or_semantic", "measurement_progress_goal_productive_candidate"}:
            disposition = "coupled_verifier_revalidation_required"
        gate_inputs.append({"name": "coupled_verifier_gate", **verifier_coupling_gate})
    envelope_thaw_streak = 0
    if bool_value(reachability_gate.get("envelope_thaw_item_required")):
        envelope_thaw_streak = 1
        for prior_row in reversed(registry_rows):
            if row_root_family(prior_row) != current_root_family_key:
                continue
            if bool_value(prior_row.get("envelope_thaw_item_required")):
                envelope_thaw_streak += 1
                continue
            break
    forced_task_options = list(forced_retarget_gate.get("forced_selected_task_options") or [])
    if bool_value(diagnostics_gate.get("instrumentation_supply_required")):
        existing_forced_kinds = gate_allowed_task_kinds({"forced_selected_task_options": forced_task_options})
        if not existing_forced_kinds.intersection({"instrumentation_supply", "execution_diagnostics_supply"}):
            forced_task_options.append(
                {
                    "selected_task_kind": "instrumentation_supply",
                    "task_kind": "instrumentation_supply",
                    "source": "diagnostics_unavailable_gate",
                    "actionable": True,
                    "failure_surface_count_key": failure_surface_gate.get("failure_surface_count_key"),
                    "diagnostics_unavailable_streak": diagnostics_gate.get("diagnostics_unavailable_streak"),
                    "instrumentation_trigger_threshold": diagnostics_gate.get("instrumentation_trigger_threshold"),
                }
            )
    forced_selected_task = forced_retarget_gate.get("forced_selected_task") or (forced_task_options[0] if forced_task_options else None)

    row = build_base_packet(locals())
    chain_untried_override, untried, ledger_entries = apply_root_cause_ledger(locals())
    apply_disposition_and_findings(locals())
    if existing_cycle:
        row["registry_idempotent_replay"] = True
        row["same_family_micro_hardening_count"] = existing_cycle.get("same_family_micro_hardening_count", count)
        row["micro_hardening_count"] = existing_cycle.get("micro_hardening_count", row["same_family_micro_hardening_count"])
        row["high_water_mark"] = existing_cycle.get("high_water_mark", high_water)
        row["semantic_progress"] = bool_value(existing_cycle.get("semantic_progress"))
        row["changed_vs_previous"] = bool_value(existing_cycle.get("changed_vs_previous"))
        row["recommended_disposition"] = existing_cycle.get("recommended_disposition", disposition)
        row["hard_stop_required"] = bool_value(existing_cycle.get("hard_stop_required"))
        for key in IDEMPOTENT_REPLAY_KEYS:
            if key in existing_cycle:
                row[key] = existing_cycle[key]
        if disagreement:
            existing_codes = {
                str(finding.get("code") or "")
                for finding in row.get("findings", [])
                if isinstance(finding, dict)
            }
            if "validator_disagreement" not in existing_codes:
                row.setdefault("findings", []).append(disagreement)
            row["authoritative_semantic_progress"] = False
            row["hard_stop_required"] = True
        return row, registry_rows, False
    registry_row = dict(row)
    return row, compact_registry([*registry_rows, registry_row], args.max_rows_per_family), True


class LoopbackEvaluator:
    def evaluate(self, args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]], bool]:
        return _evaluate_impl(args)


def evaluate(args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]], bool]:
    return LoopbackEvaluator().evaluate(args)

