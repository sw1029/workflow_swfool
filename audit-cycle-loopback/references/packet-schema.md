# Loopback Audit Packet Schema

## Contents

- [Packet fields](#packet-fields)
- [Consumer and decision rules](#consumer-and-decision-rules)
- [Static decision-boundary fixtures](#static-decision-boundary-fixtures)

## Packet fields

Required fields:

- `schema_version`: `anti-loop-progress-gate-v1`
- `handoff_contract_version`: `1` for current pre-derive handoff validation.
- `step`: `loopback_audit`
- `cycle_id`
- `family_key`
- `root_key`
- `root_family_key`
- `artifact_family`
- `decision_artifact_ref`: legacy flat artifact identity remains valid when no applicability object is present. The explicit form binds `decision_subject_id`, `subject_class_id`, `revision_id`, full `subject_digest`, `lineage_id`, and `freshness_status`, plus all four objects `body_fingerprint`, `production_lane`, `cohort`, and `producer_run`, each with `applicability: applicable|not_applicable` and a value only when applicable. Consumers echo the exact subject fields and only applicable values in `decision_identity_echo.dimension_values`; a not-applicable dimension is a normal bypass.
- `gate_compatibility_results`: per-gate A2 compatibility records; only `compatible` records may contribute to disposition, hard-stop, residual, or completion decisions.
- `input_state_fingerprint` and `attempt_identity`: version-2 content-bound registry identity over cycle id plus either the exact explicit subject/revision/digest/lineage and only its applicable dimension values, or the complete legacy id/hash/lane/body/cohort binding, together with a canonical hash of the consumer's bounded decision-input projection. A valid explicit `not_applicable` dimension is an intentional bypass and must not be converted into a legacy missing-field failure. Finalize this identity only after decision-relevant provenance, primary-metric, and terminal root-cause inputs are present. Exclude receipt rows, receipt self-hashes, and attempt-identity fields from that projection to avoid circular binding, while retaining the required-consumer ID set. Family, root, and blocker labels are trace metadata; a concrete root-cause decision input remains content-bound even though its display label cannot independently reset recurrence.
- Optional `progress_scope_contract`, `work_intent`, `progress_observations`, `closeout_projection`, `retained_change_evidence`, and `retained_change_classification` follow the orchestrator's [shared scoped-progress contract](../../orchestrate-task-cycle/references/workflow-interface-contracts.md#scoped-progress-and-retained-change). The intent is prospective only. The effective class is recomputed from actual changed paths/digest pairs and exact task/root/global observations; a tests/schema/verifier/lifecycle-only change is capped to its bounded role.
- `root_stall_reset` is valid only for comparable same-basis `improved` root evidence with a reduced/resolved residual and `verified|independently_verified|explicit_self_grounded` provenance. `global_stall_reset` and global semantic progress additionally require applicable exact-bound independent high-water movement with complete non-conflicting active-axis observations. Missing or conflicting axes are `not_evaluated`, never an optimistic aggregate pass.
- `attempt_identity_version`: `2` for the label-independent identity contract.
- `legacy_attempt_identity`: trace-only pre-v2 identity that included family and blocker labels. Never use it to split a logical attempt.
- `attempt_revision_candidate`: proposed revision number. On correction, `supersedes_attempt_revision_candidate` and `supersedes_attempt_identity_candidate` identify the prior durable projection; these fields are non-authoritative until finalization.
- `finalization_required`, `finalization_state`, and `authoritative_consumption_allowed`: candidate boundary. Loopback emits `true`, `candidate`, and `false`; only the orchestrator's separate finalization receipt permits authoritative consumption.
- `finalized_state_cycle_id`, `finalized_state_status`, `finalized_state_error`, and `registry_state_source`: identify whether recurrence state came from a helper-verified current finalization, a legacy fallback used only because no canonical pointer exists, or a fail-closed invalid finalization.
- `recurrence_identity` and `recurrence_identity_status`: optional caller-owned separation of `stable_root_id`, `facet_id`, and `local_family_id`; root/facet/local counts; evaluation-debt streak; content-bound input delta; and split/merge/reclassification/correction lineage. The stable root is a content-bound tuple of root ID, violated-relation predicate ID, and applicable scope ID; a prior count requires the prior tuple and digest. Applicable state must validate before it becomes a `recurrence_identity` typed operation. Label, task, fixture, timestamp, wrapper, or version novelty is cosmetic and cannot reset stable-root recurrence. A caller `root_predicate_unchanged` flag is only an echo and must match the two bound tuples. A changed tuple requires lineage whose parent/child IDs connect the prior and current roots. A material delta requires the exact bounded field set: full content digest, typed difference IDs, opaque rationale ID and rationale evidence digest, explicit boolean authority/external/toolchain premise-change flags, `violated_relation_effect=affects_violated_relation`, and a canonical digest over the full delta. Missing flags, extra raw metadata, or tampering cannot reset recurrence. Lineage aggregate counts preserve the prior-attempt lower bound, and a correction supersedes one logical attempt revision.
- `semantic_signature`
- `changed_vs_previous`
- `semantic_progress`
- `terminal_outcome_changed`: observed terminal/domain outcome changed under strict output-delta evidence.
- `same_family_micro_hardening_count`
- `provider_request_count`
- `budget_evaluations`: map of policy id to a typed budget contract with `budget_id`, optional `budget_value`, `budget_evaluation_status`, optional `source`, and `reason_code`. Status is `evaluated`, `budget_unverified`, or `not_evaluated`.
- `budget_evaluation_status` and `budget_unverified`: packet-level summary and sorted policy ids whose required caller/adapter/config budget is absent or invalid. Unverified budgets preserve counters as observations but cannot grant budget-based progress credit or create exhaustion, stall, forced-retarget, or threshold hard-stop decisions.
- `quality_vector`
- `quality_delta_policy`: normalized adapter-owned G-COV keys and aliases. An empty policy means G-COV was not evaluated, not that every domain metric was zero.
- `quality_vector.quality_signal_confidence`: `high`, `medium`, or `low`
- `quality_vector` may carry adapter-owned scalar context and confidence reasons; generic consumers must not interpret domain-specific field names.
- `previous_accepted_baseline`: baseline source, fingerprint, adapter error if any, and whether the adapter supplied a previous quality vector override.
- `coverage_quality_delta_reconciliation_gate`: R-GCOV packet comparing loopback G-COV with output-delta G-COV when both exist.
- `substance_delta_gate`: G-SUBSTANCE packet comparing adapter-supplied substance vectors.
- `vacuous_corrective_gate`: G-VACUOUS packet summarizing corrective/backfill attempted and resolved counts.
- `adapter_mandate_gate`: G-ADAPTER packet summarizing adapter contract gaps, missing streak, and whether adapter registration/strengthening is mandatory.
- `adapter_wiring_gate`: C1 packet summarizing registered adapter path/load status and whether a registered-but-unloaded adapter must be routed as `self_inflicted_gate_defect`.
- `domain_adapter.adapter_revision_sha256` and `domain_adapter.scan_handoff_status`: bind the loaded callable wrapper to the manifest/wrapper/delegate/renderer revision selected by the orchestrator scan.
- `cumulative_goal_distance_gate`: G-CHAIN packet summarizing high-water stall streak for an adapter-collapsed root family or adapter-missing artifact family.
- `chain_stall_forced_retarget_gate`: C4 packet listing actionable forced retarget options when cumulative goal-distance stall reaches the explicitly supplied stall budget under lateral churn. It does not derive another numeric threshold from that budget.
- `primary_metric_gate`: optional adapter-supplied G-CHAIN/C4 trigger packet for one content-bound north-star observation. It preserves legacy scalar comparison and also supports set, vector, ordered, and predicate high-water contracts.
- `evidence_provenance_gate`: optional F2 packet that records independently verified versus producer-attested metric movement.
- `verification_source_separation_gate`: optional H4 packet classifying source separation and decisive-invariant separation independently. Each independent axis carries producer/verifier invariant-owner IDs and `invariant_separation_status`; different paths alone do not pass. `self_grounded` is limited to explicit root-local structural checks and is not source-independent semantic verification.
- `failure_surface_stage_gate`: optional H2 packet resolving `last_successful_stage`, `failure_surface_stage`, terminal classification stage consistency, and count-key extension.
- `diagnostics_unavailable_gate`: optional H3 packet tracking repeated unavailable diagnostics and whether instrumentation supply is required.
- `instrumentation_exercise_gate`: optional I1 packet tracking whether supplied instrumentation was exercised by a fresh run with non-empty scalar field evidence.
- `instrumentation_first_fire_gate`: optional J5 packet tracking whether a fresh run first emitted non-empty supplied instrumentation fields and which workflow item receives the one allowed evidence credit.
- `acceptance_encoding_gate`: optional I2 packet preserving measurable quantifiers, evidence kind, and dilution status.
- `acceptance_scenario_gate`: optional J1 packet tracking scenario premise injection and expected terminal-state observation.
- `command_provenance_gate`: optional J2 packet tracking full body-free argv recording and missing-provenance restrictions.
- `blocker_actionability_gate`: optional J3 packet tracking violated relation, observed scalar values, expected relation, minimum input delta, and blocker opacity.
- `stochastic_feasibility_gate`: optional J4 packet tracking observed outcome variance, exact-match impossibility, and floor-edge envelope slack.
- `expectation_lineage_gate`: optional K1 packet tracking output-derived expectation anchor, designated baseline, missing anchor, and stale-anchor status.
- `comparison_parity_gate`: optional K2 packet tracking comparison parity axes and per-axis status.
- `adoption_axis_gate`: optional K3 packet tracking gating/tradable axis classification and disqualified measured candidates.
- `resolution_downgrade_gate`: optional K4 packet tracking required versus observed evidence resolution and surrogate downgrade declarations.
- `report_key_integrity_gate`: optional K5 passthrough packet tracking duplicate terminal report keys and divergence findings.
- `lane_identity_gate`: optional L1 packet tracking verified artifact lane identity, current decision lane identity, missing lane hooks, and stale-lane pass downgrades.
- `decision_freshness_gate`: optional L2 packet tracking whether decision/adoption/reclassification updates used a fresh current-lane run after upstream production contract changes.
- `gating_axis_producer_gate`: optional L3 packet tracking gating axes starved by missing or unexercised producer paths.
- `portfolio_quota_gate`: optional L4 packet tracking verifier/guard/report/metadata versus producer/envelope/long-run recent-work ratio and any adapter-supplied restriction.
- `cycle_reachability_gate`: optional L5 packet tracking target scale, observed cycle throughput, cycle cap, and `unreachable_within_cycle` verdict.
- `metric_basis_gate`: optional L6 packet tracking claimed metric basis classes, consumed input classes, derivability, and basis-overclaim downgrades.
- `surface_field_review_gate`: optional L7 packet tracking reviewed surface field classes, locator status, sample count, and scalar defect-count matrix.
- `verifier_surface_hardening_gate`: optional I3 packet collapsing guard/verifier/report-only changes over the same target artifact paths.
- `run_disposition`: optional I4 execution disposition: `failed_closed`, `candidate_degraded`, or `candidate_written`.
- `runtime_config_echo`: optional I5 safe scalar/enum runtime setting echo from failure autopsy.
- `execution_starvation`: optional I6 profile/derive ranking signal for recent cycles with no fresh run ids.
- `coupled_verifier_gate`: optional F1 packet that records verifier-source coupling for gates whose verifier code changed in the current change set.
- `acceptance_reachability_gate`: G-REACH packet with abstract acceptance minimum, frozen envelope, reachability verdict, `evaluation_status: pass|fail|not_evaluated`, and relaxation/escalation requirement.
- `acceptance_envelope_contract`: optional normalized acceptance packet field binding a measurable target to an adapter-owned minimum executable envelope.
- `oracle_metric_validity_gate`: G-OENV packet with optional oracle/metric validity self-check status, `evaluation_status: pass|fail|not_evaluated`, and tautological-metric exclusion.
- `advice_freshness_gate`: G-ADVICE-FRESH packet comparing declared advice fingerprints to current output fingerprint when available.
- `structure_metrics_gate`: S-STRUCT packet exposing optional adapter-supplied structure metrics and consolidation recommendations, including semantic structure axes and global invariant axes when available.
- `count_key_hygiene_gate`: optional G1 packet or finding showing whether the effective count key is generation-independent. Generation-dependent raw keys are trace-only and must not reset family counters.
- `goal_axis_completeness_gate`: optional G3 packet from review/caller evidence showing whether active measurable goals have at least one adapter-owned quality/vector axis.
- `residual_gap_cost_policy`: optional G4 packet or passthrough fields comparing residual-gap value per cycle cost against alternatives when cycle-efficiency evidence is available.
- `high_water_mark`
- `recommended_disposition`
- `hard_stop_required`
- `evidence_class`
- `not_goal_truth`
- `evidence_paths`

Additive anti-loop gate fields:

The D1-D4 fields in this list revise existing acceptance, progress truth-source, root-cause distinctness, and C4 trigger decisions. They are not additional detector phases or new authority surfaces.

- `effective_allowed_dispositions`: intersection of all active constraining gates' `allowed_dispositions`, with `terminal_blocked` and `user_escalation` always preserved as safety valves.
- `disposition_intersection_basis`: per-gate `allowed_dispositions`, optional `allowed_task_kinds`, and `constrains_disposition` basis used to compute the intersection and bind `goal_productive` labels to specific correction classes.
- `consolidation_streak`: consecutive recent `consolidation` dispositions whose effective progress is `governance_only`.
- `consolidation_reduces_goal_distance`: always `false` unless a repository-specific gate proves a primary-output transition.
- `validator_disagreement` finding: block-level finding when strict runner validation reports `semantic_progress=true` while output-delta reports `semantic_progress=false`.
- `coverage_quality_delta_reconciliation_gate`: R-GCOV packet with local/external G-COV compact values, `validator_disagreement`, `gcov_metric_name_collision`, `metric_value_conflicts`, `status`, and disposition metadata.
- `validator_integrity_gate`: G-INTEGRITY packet with `validator_integrity`, `validator_coverage`, `status`, `hard_stop_required`, `allowed_dispositions`, and compact findings.
- `authoritative_semantic_progress`: conservative loopback candidate after disagreement resolution; it is not the finalized authoritative verdict.
- `substance_delta_gate`: G-SUBSTANCE packet with `current_substance_vector`, `previous_substance_vector`, `improved_axes`, `substance_delta_pass`, `status`, and fail-closed disposition metadata.
- `vacuous_corrective_gate`: G-VACUOUS packet with lane `attempted/resolved` counts, `surface_corrective_noop`, `excluded_delta_lanes`, and `status`.
- `facet_root_map_applied` and `facet_root_map_size`: whether the domain adapter supplied facet-to-root family normalization before cap evaluation.
- `count_key_hygiene_gate`, `generation_dependent_count_key`, `count_key_trace_only`, and `effective_count_key`: G1 fields. They indicate that raw plan/advice/task-pack/cycle/run/date/hash/version key material was excluded from counting and preserved only for traceability.
- `adapter_mandate_required`, `adapter_missing_streak`, `adapter_contract_unmet`, and `adapter_mandate_gate`: G-ADAPTER fields. `adapter_contract_unmet` may include `facet_root_map`, `substance_metrics`, or `quality_vector`.
- `adapter_hook_demand`, `hook_supply_required`, `demanded_hooks`, and `hook_demand_threshold`: G-ADAPTER demand-ledger extension fields. Each `adapter_hook_demand` row has `{hook_id, skip_count, decision_relevant_skip_count, affected_gate_ids, first_skip_cycle_id, last_skip_cycle_id}`. `hook_supply_required=true` is emitted only when one or more rows reach the threshold, and `demanded_hooks` contains the opaque hook ids.
- `adapter_wiring_defect`, `adapter_loaded`, `adapter_registered`, `adapter_path`, `adapter_expected_path`, and `adapter_wiring_gate`: C1 fields. `adapter_wiring_defect=true` supersedes `adapter_mandate_required` for the current cycle.
- `cumulative_goal_distance_scope_key`, `cumulative_goal_distance_stall_streak`, `cumulative_goal_distance_stalled`, `cumulative_untried_chain_without_quality_delta`, `high_water_vector`, `high_water_last_improved_cycle`, and `untried_veto_overridden_by_chain_stall`: G-CHAIN fields.
- `chain_stall_forced_retarget_gate`, `forced_selected_task`, and `forced_selected_task_options`: C4 fields. Options use abstract `selected_task_kind` values such as adapter wiring/load fixes or adapter-owned capability-ladder rungs.
- `primary_metric_gate`, `metric_basis_id`, `metric_dimension_id`, `metric_subject_id`, `metric_provenance_id`, `value_kind`, `comparison_semantics`, `comparison_config`, `metric_observation_sha256`, `primary_metric_high_water_sha256`, `metric_comparability_status`, `metric_comparison_relation`, `basis_migration_observed`, `primary_metric_high_water_moved`, `primary_metric_zero_movement_streak`, and `primary_metric_stalled`: D4/C4 trigger-key fields when the adapter exposes `primary_metric(...)`. `value_kind` is `scalar|set|vector|ordered|predicate`. Applicable comparator pairs are scalar with `higher_is_better|lower_is_better|equal_required`, set with `set_relation`, vector with `pareto`, ordered with `higher_is_better|lower_is_better|equal_required`, and predicate with `predicate_only`. Set comparisons require `set_relation_direction`; Pareto vectors require exact `vector_directions`; ranked ordered comparisons require an exact duplicate-free `ordered_values`; equality requires `target_value`. The generic reducer compares only exact-bound, source-separated values under an identical stable metric/basis/dimension/subject/provenance/value-kind/comparator/configuration scope. Non-scalar rows additionally require the opaque subject and provenance identities. A missing or changed identity, invalid value, mismatched vector axes, invalid prior high-water digest, or unknown comparator is `not_evaluated` and cannot reset or increment stall. Local G-CHAIN family recurrence remains separate. Secondary safety, artifact-truth, structure, storage, or diagnostic movement does not reset the primary high-water.
- `evidence_provenance_gate`, `independently_verified_fields`, `producer_attested_fields`, and `attested_only_movement`: F2 fields. When provenance is supplied, high-water movement and goal-productive support may use only `independently_verified` fields; untagged fields are `producer_attested`.
- `verification_source_separation_gate`, input/artifact IDs and fingerprints, `verification_axes`, invariant-owner IDs, `independent_source_separation_status`, `independent_invariant_separation_status`, and `independently_verified_downgraded_fields`: H4/A4 fields. Missing/overlapping inputs or coupled/unknown invariant ownership downgrade affected fields while preserving axis provenance. Valid root-local structural `self_grounded` remains separate rather than independent.
- `execution_stage_ladder_status`, `execution_stage_ladder`, `last_successful_stage`, `failure_surface_stage`, `failure_surface_count_key`, `effective_count_key`, `failure_surface_stage_gate`, `terminal_classification_stage_contradiction`, and `terminal_classification_invalid_for_counting`: H1/H2 fields. They extend counting by observed failure surface and invalidate contradictory terminal classifications.
- `same_input_contract_gate` and `same_input_contract_violation`: H2 fields. Same-condition comparisons with mismatched input sets are invalid for counting/close.
- `diagnostics_unavailable`, `diagnostics_unavailable_streak`, `diagnostics_unavailable_gate`, and `instrumentation_supply_required`: H3 fields. Repeated unavailable diagnostics force instrumentation supply or an explicit observability rationale.
- `instrumentation_exercise_required`, `instrumentation_exercised`, `instrumentation_exercise_gate`, `instrumentation_field_map`, `instrumentation_run_id`, `instrumentation_fields_nonempty`, and `derived_from_existing_artifacts`: I1 fields. Supplied instrumentation must be exercised by a fresh run before dependent measurement/adoption work consumes it.
- `acceptance_encoding_gate`, `acceptance.quantifiers`, `evidence_kind`, `item_created_at`, `required_new_run_id`, `satisfying_run_id`, and `acceptance_diluted`: I2 fields. Live-run criteria require a post-item run id; derived substitution is partial/residual scope.
- `verifier_surface_hardening_gate`, `verifier_surface_hardening`, `change_set_kind`, `target_artifact_paths`, `target_artifact_key`, `verifier_surface_hardening_streak`, and `guard_stacking_cap_reached`: I3 fields. Name-changing verifier/guard/report-only work over the same target collapses to one family.
- `run_disposition`, `failed_closed`, `candidate_degraded`, `candidate_written`, `disposition_unclassified`, `safety_violations`, `degradation_reasons`, and `candidate_degraded_axes`: I4 fields. Quality-miss artifacts may be preserved without canonical promotion; unsafe artifacts fail closed.
- `runtime_config_echo`, `config_origin`, `config_overrides`, and `code_default_override_self_inflicted_gate_candidate`: I5 fields. Store only scalar/enum settings and origins.
- `execution_starvation`, `recent_cycle_run_id_count`, `execution_starvation_window`, and `execution_candidate_priority_boost`: I6 fields from profile/caller evidence.
- `instrumentation_first_fire`, `first_fire_consumed_item_id`, `instrumentation_first_fire_gate`, and `first_fire_double_count_blocked`: J5 fields. First fire is one evidence credit and must not also satisfy goal progress or the instrumentation supply item.
- `acceptance_scenario_gate`, `acceptance_scenarios`, `scenario_coverage`, `scenario_uncovered`, and `acceptance_inversion`: J1 fields. They prove or reject premise-class injection for scenario-shaped acceptance.
- `command_argv`, `argv_redaction_policy`, `command_provenance_gate`, and `command_provenance_missing`: J2 fields. `command_argv` is body-free and redacted; missing provenance restricts baseline/reproduction use.
- `blocker_actionability_gate`, `blocker_opacity`, `violated_relation`, `observed_values`, `expected_relation`, `minimum_input_delta`, abstract input-key names, and `authorization_contract_repair_candidate`: J3 fields. Opaque blockers are warning evidence until repeated for the same gate; multi-input authorization relations may become contract-repair candidates for a named single authorization input.
- `stochastic_feasibility_gate`, `outcome_variance`, `predetermined_unreachable`, `floor_edge_envelope`, `slack`, and `variance_sample_count`: J4 fields. They route exact-match/floor-edge contracts to revision rather than retry.
- `expectation_anchor`, `designated_baseline`, `expectation_anchor_missing`, `expectation_lineage_stale`, and `expectation_lineage_gate`: K1 fields. They bind output-derived scalar expectations to their source surface and current designated surface status.
- `parity_axes`, `parity_axis_status`, `parity_unverified`, and `comparison_parity_gate`: K2 fields. They preserve controlled/measured/unknown parity axes for comparison/adoption decisions.
- `adoption_axis_classification`, `required_output_classes`, `majority_vote_adoption`, `provisional_adoption`, `measured_but_disqualified`, and `adoption_axis_gate`: K3 fields. They distinguish gating axes from tradable axes before adoption consumption.
- `required_evidence_resolution`, `observed_evidence_resolution`, `resolution_downgrade`, `surrogate_resolution_basis`, and `resolution_downgrade_gate`: K4 fields. They record lower-resolution surrogate evidence without treating it as full-resolution proof.
- `report_key_divergence`, `duplicate_key_paths`, `duplicate_key_values`, and `report_key_integrity_gate`: K5 fields. They preserve single-report duplicate terminal key divergence for result-contract/validation blocking.
- `lane_identity_gate`, `production_lane_identity`, `current_decision_lane`, `validated_artifact_lane`, `lane_identity_missing`, `pass_on_stale_lane`, and `current_lane_residual_required`: L1 fields. They prevent a verifier pass on a historical or different lane from proving current-lane capability/adoption.
- `decision_freshness_gate`, `upstream_contract_changed_since_measurement`, `measurement_run_id`, `measurement_artifact_created_at`, `required_new_run_id`, `stale_measurement_artifact`, and `decision_metadata_revision`: L2 fields. They distinguish relabeling stale artifacts from fresh measurement progress.
- `gating_axis_producer_gate`, `axis_starved_by_missing_producer`, `gating_axis_id`, `producer_path_status`, `producer_supply_required`, and `producer_path_evidence`: L3 fields. They route starved gating axes to producer-supply work before additional verifier surfaces.
- `portfolio_quota_gate`, `recent_verifier_like_count`, `recent_producer_like_count`, `portfolio_ratio`, `portfolio_quota_exceeded`, `portfolio_quota_mode`, and `allowed_next_work_kinds`: L4 fields. Only a content-bound adapter/authority/caller/config budget with an evaluated status may restrict next selection; otherwise the gate is `not_evaluated` and observed quota evidence is advisory.
- `cycle_reachability_gate`, `acceptance_scale`, `throughput_evidence`, `required_scale`, `observed_cycle_throughput`, `cycle_execution_cap`, capacity lower/upper bounds, `cycle_reachability_sha256`, `unreachable_within_cycle`, `long_run_launch_required`, and `harvest_validation_required`: L5 fields. The pure calculation is `applicable` only for positive comparable scale/throughput/cap inputs with matching units; otherwise it is fail-quiet `not_evaluated`. Upper-bound capacity below required scale proves unreachable, lower-bound capacity at/above required scale proves reachable, and an interval crossing the target is indeterminate. An unreachable result routes to long-run launch/monitor/harvest, throughput improvement, descope, terminal blocker, or escalation.
- `metric_basis_gate`, `metric_basis_inputs`, `claimed_basis_class`, `consumed_input_classes`, `basis_derivable`, `basis_overclaim`, `actual_basis_class`, and `basis_downgraded_fields`: L6 fields. They downgrade overclaimed metric provenance and exclude it from high-water/progress consumption.
- `surface_field_review_gate`, `surface_field_classes`, `field_class_map_missing`, `review_sample_count`, `surface_field_defect_matrix`, `surface_field_review_status`, and `surface_field_review_authority`: L7 fields. They preserve scalar qualitative-review coverage over producer-written surface string fields.
- `coupled_verifier_gate`, `pass_with_coupled_verifier`, and `changed_verifier_source_paths`: F1 fields. A gate pass from a verifier source modified in the same change set is not an effective pass.
- `c4_user_escalation_backstop_required`: boolean set only when C4/primary-metric stall has no actionable forced task option and the workflow must emit one user-escalation handoff instead of another same-family retry.
- `acceptance_unreachable_under_frozen_config`, `acceptance_verifier_not_evaluated`, `unverifiable_acceptance_contract`, `relaxation_or_escalation_required`, `envelope_thaw_item_required`, `envelope_thaw_item`, `envelope_thaw_streak`, and `acceptance_reachability_gate`: G-REACH/E2/H5 fields. `unverifiable_acceptance_contract=true` means a measurable target requires a live verifier but that verifier is `not_evaluated`; `envelope_thaw_item_required=true` means frozen-envelope-unreachable acceptance needs thaw/relax/descope/escalation before ordinary repair continues.
- `residual_gap_policy`, `residual_gap_ratio`, and `marginal_repair`: F3 passthrough fields from normalized acceptance or adapter policy. They inform derive's marginal-value comparison but do not by themselves close or block work.
- `cycle_fixed_cost`, `alternative_cycle_cost`, `marginal_gap_value`, `marginal_value_per_cycle_cost`, `alternative_value_per_cycle_cost`, and `residual_gap_cost_policy`: G4 passthrough fields from cycle-efficiency or normalized acceptance evidence. When absent, consumers use denominator `1` and legacy F3.
- `acceptance_envelope_contract`, `envelope_floor`, `execution_envelope`, `envelope_deficit_axis`, and `envelope_below_floor`: optional D1 fields. These are abstract adapter-owned values; absence is warn-only and must not crash packet production.
- `oracle_metric_validity_gate` and `metric_verifier_not_evaluated`: G-OENV fields. `metric_goal_productive_excluded=true` means tautological or required-but-not-evaluated metric/oracle evidence cannot support goal-productive progress.
- `advice_freshness_gate`: G-ADVICE-FRESH packet with `current_output_fingerprint`, declared fingerprint claims, stale advice paths, and `advice_metrics_stale`.
- `advice_freshness_gate.gate_result_regression_stale`: warn-only signal for a supplied gate verdict that changed from passed to blocked under a stable environment fingerprint.
- `partial_progress_axes_gate`: warn-only packet with adapter-supplied partial axes and `recommendation: decompose_all_or_nothing_gate` when high-water remains flat.
- `goal_axis_map`, `unobserved_goal_axes`, and `pass_with_unobserved_axes`: G3 fields. They mean review pass cannot be consumed for measurable goals whose observing axis set is empty.
- `structure_metrics_gate`: S-STRUCT packet with `structure_metrics`, `structure_global_invariant_metrics`, `structure_high_water_key_scope`, `structure_consolidation_recommended`, optional `structure_high_water_moved`, `global_structure_high_water_moved`, `improved_structure_axes`, `refactor_effect_required`, `status`, and warning metadata. `structure_metrics` may include numeric semantic axes such as `mechanical_shard_file_count`, `version_suffix_file_count`, `global_rebinding_signal_count`, `duplicate_symbol_name_count`, `max_changed_tree_depth`, `max_changed_dir_fan_out`, `reuse_root_import_ratio`, and `max_file_logical_loc`.
- `measurement_progress`: boolean indicating newly introduced or first-observed measurement/oracle coverage.
- `measurement_progress_allowed`: boolean indicating the measurement exemption is still within `measurement_streak_cap`.
- `measurement_streak` and `measurement_streak_cap`: bounded exemption counters for consecutive measurement cycles.
- `measurement_progress_streak_for_root_key`: bounded exemption counter for the suffix-normalized root key.
- `measurement_progress_streak_for_root_family`: bounded exemption counter for the normalized root family after facet/version/date/run suffix removal.
- `measurement_check_ids`: stable check/oracle IDs observed in the current cycle.
- `measurement_frontiers_observed`: first-observed opaque capability frontier IDs supplied by the caller or adapter.
- `measurement_progress_basis`: introduced check IDs and new frontier observations that justified the exemption.
- `blocker_signature`: stable current blocker identifier before volatile suffix normalization.
- `blocker_root_family`: normalized blocker family used to prevent facet-renaming loops.
- `root_dominant_parameter_key`: optional adapter-owned dominant parameter, such as an acceptance `deficit_axis`, used with the collapsed root family for distinct-root-cause and stall equivalence.
- `blocker_ladder_rung`: current capability-ladder rung for the blocker family.
- `blocker_mutation_kind`: `initial`, `repeat`, `facet_rename`, `lateral`, or `forward_mutation`.
- `forward_mutation_budget_remaining`: remaining count before forward rung movement must force implementation rather than another measurement/governance cycle.
- `observed_delta_class`: compact observed output-delta class such as `material_delta`, `changed_semantic_output`, or `no_observed_domain_delta`.
- `forward_mutation_vacuous`: boolean set when a blocker ladder moved but `terminal_outcome_changed=false`.
- `root_cause_ledger_path`: `.task/anti_loop/root_cause_ledger.jsonl` unless overridden.
- `root_cause_ledger_status`: `prepared_not_finalized` or `not_applicable_no_hypotheses`.
- `root_cause_ledger_updated`: always `false` during loopback evaluation.
- `root_cause_ledger_update_candidate`: whether the finalizer has proposed ledger entries to consider.
- `root_cause_ledger_entries`: ledger rows proposed for this cycle; loopback never writes them.
- `repo_owned_source_roots`, `repo_owned_source_roots_status`, and `repo_owned_source_roots_error`: optional adapter-supplied repository-owned source glob contract used for provenance-based actionability. `not_provided` is fail-quiet and must not become a new gate.
- `root_cause_unverified_hypotheses`: asserted-actionable hypotheses excluded because they lack structural actionability or provenance.
- `root_cause_duplicate_hypotheses`: hypotheses excluded because they are equivalent to an attempted hypothesis by normalized slug, target surface, and observed delta class.
- `untried_actionable_root_cause_exists`: boolean terminal-blocker veto when at least one verified local, bounded, provider-free, in-scope, authority-allowed or provenance-backed hypothesis remains untried and `hypothesis_exhausted=false`.
- `untried_root_cause_hypotheses`: compact list of remaining actionable untried hypotheses.
- `untried_promotion_budget`: explicitly supplied same-family vacuous untried repair cap. Absence is `budget_unverified` and cannot produce `hypothesis_exhausted=true`.
- `vacuous_untried_attempt_count` and `vacuous_untried_streak`: count attempted untried repairs with `terminal_outcome_changed=false`.
- `hypothesis_exhausted`: boolean hard stop when the untried budget is spent without terminal outcome change.
- `hypothesis_exhaustion_seal_path`, `hypothesis_exhaustion_seal_status`, and `hypothesis_exhaustion_seal_candidate`: target path, `prepared_not_finalized` status, and pure upsert payload. Loopback never writes the seal.
- `terminal_blocked_invalid_due_to_untried_root_cause`: alias boolean for derive/result-contract consumers.
- `force_implementation_cycle`: boolean requiring derive to choose implementation work after the forward-mutation budget is exhausted.
- `task_correction_class`: `detection`, `correction`, `mixed`, or `unknown`.
- `producer_progress_claim_fields`: optional adapter-supplied field names that were downgraded from producer progress reports.
- `observed_producer_claim`: captured producer self-report values, stored only for traceability and never as authoritative progress.
- `split_brain_progress_claim`: warning boolean/details when producer self-report conflicts with adapter/output-delta truth.
- `detection_only`: boolean indicating detection work without semantic primary-output progress.
- `detection_only_streak_for_root_family` and `detection_only_streak_cap`: G-BALANCE streak and cap.
- `requires_correction_or_terminal`: boolean requiring correction/implementation work, terminal blocking, or user escalation.
- `orphan_advice_not_intaken` finding: warn-level finding when root steering docs exist but are not represented in `.agent_advice/active`.

## Consumer and decision rules

Disposition values:

- `open`: computed progress was found.
- `prefer_provider_or_semantic`: computed but stagnant below threshold.
- `provider_or_semantic_transition_or_terminal`: stagnant at or above threshold.
- `conservative_hold`: insufficient evidence or malformed inputs.

Consumer rule: `produced_domain_delta=true` is not a substitute for this packet unless it is backed by `changed_vs_previous=true` and `semantic_progress=true`.

Producer claim rule: producer-owned progress fields must be represented as `observed_producer_claim` and excluded from authoritative progress. If the adapter or strict output-delta evidence disagrees, set `split_brain_progress_claim` and use the conservative adapter/output-delta verdict.

Disposition rule: consumers must select the next-task disposition from `effective_allowed_dispositions` when present. Do not treat separate gate `allowed_dispositions` as a union.

Task-kind rule: when `disposition_intersection_basis` contains `allowed_task_kinds`, consumers must not accept a task as `goal_productive` unless its `selected_task_kind` is in that set. A matching `goal_productive` label alone is insufficient.

Measurement rule: `measurement_progress_allowed=true` may reinclude `goal_productive` without setting `semantic_progress=true`; consumers must still preserve no-overclaim boundaries and must stop using the exemption after the root-key or root-family streak cap.

Substance rule: `measurement_progress_allowed=true` requires `substance_delta_gate.substance_delta_pass=true`. Capability-ladder `forward_mutation` promotion requires `terminal_outcome_changed=true` from strict observed output-delta evidence; missing adapter substance metrics still fail closed for measurement promotion, but must not crash packet production.

R-GCOV rule: `coverage_quality_delta_reconciliation_gate.status=block` prevents measurement and capability-ladder promotion from relying on the favorable G-COV source. Consumers must treat the cycle as conservatively blocked until the output-delta and loopback G-COV values agree or the selected next task resolves the disagreement.

Vacuous corrective rule: `vacuous_corrective_gate.surface_corrective_noop=true` means attempted corrective/backfill rows resolved zero items. Consumers must not count those rows as produced or semantic delta.

Integrity rule: `validator_integrity_gate.status=block` prevents validator-derived progress claims. Consumers may choose correction work, but must not cite the validator pass as completion or goal-productive evidence.

Mutation rule: `blocker_mutation_kind=facet_rename` is same-family churn. When a caller supplies `recurrence_identity`, the predicate-and-scope-bound stable-root count is authoritative over child/facet novelty and can fall only after a content-bound material delta that affects the same violated relation or a lineage transition connecting prior/current roots while preserving the conservative aggregate lower bound. `blocker_mutation_kind=forward_mutation` counts as blocker-state movement only when stricter gates are clear and `terminal_outcome_changed=true`. If `forward_mutation_vacuous=true`, consumers must not reset loop counters or promote `goal_productive`; route to untried root-cause repair when available, otherwise terminal/user escalation. If `force_implementation_cycle=true`, consumers must choose an in-place implementation task or terminal/user escalation when implementation is not authorized.

Root-cause ledger rule: `root_cause_ledger_entries` are prepared non-GT workflow evidence bound to the registry `attempt_identity` and compact hypothesis distinctness. A label-only correction with the same content-bound attempt identity does not append or increment an attempt; a changed `input_state_fingerprint` does. A same-cycle legacy row without that exact attempt identity remains history and cannot restore a prior disposition. Loopback must not write the ledger or seal. The orchestrator may commit accepted entries only with the same final verdict, revision, and content-bound receipt. A hypothesis is untried only when it is actionability-verified and distinct from attempted hypotheses by normalized root cause, target surface, and observed delta class. Assertion-only `actionable=true` rows are `unverified`; version-suffix or rename equivalents are duplicates. If adapter-supplied `repo_owned_source_roots` proves that a hypothesis provenance reference belongs to repository-owned source, derive `local=true`, `in_scope=true`, and `actionable=true` from that provenance and ignore conflicting self-report fields. Do not hardcode project paths in this generic schema; if the hook is absent, keep the old actionability basis. If `untried_actionable_root_cause_exists=true`, `hypothesis_exhausted=false`, and `untried_veto_overridden_by_chain_stall=false`, `terminal_blocked` is invalid unless current authority, safety, or external state makes that hypothesis non-actionable. If `hypothesis_exhausted=true`, derive must stop, terminal-block, or user-escalate unless a supplied input delta changes the family.

Facet rule: adapter-supplied `facet_root_map` entries collapse facet labels before root-family streaks and measurement caps are computed. Without a map, the producer applies only conservative suffix/date/run/facet normalization.

Count-key hygiene rule: same-family counters, hypothesis exhaustion, family seals, and stall streaks must use generation-independent keys. Raw keys that contain task/advice/task-pack identifiers, cycle IDs, run IDs, dates, hashes, or version suffixes are valid only as `legacy_family_key` or trace fields. The effective key must be the adapter-collapsed root plus dominant parameter, or the terminal-outcome family fallback when the adapter map is absent. Unmapped facets merge conservatively by `terminal_outcome_key` rather than creating a new family.

Failure-surface stage rule: when `execution_stage_ladder` and `last_successful_stage` are available, count the failure by `failure_surface_stage` as part of `failure_surface_count_key`; loopback should expose that key as `effective_count_key` for same-family counter decisions. If `terminal_classification_stage_contradiction=true`, terminal classification is invalid for counting, close, or family seal until classification-stage repair or terminal/user escalation records the conflict.

Same-input contract rule: if `same_input_contract_violation=true`, same-family comparison is invalid because the compared input sets/windows differ. Do not reset stalls, close, or seal from that comparison.

Diagnostics instrumentation rule: if `instrumentation_supply_required=true`, derive must include/select instrumentation supply or record why success/failure is already observable without new instrumentation. Validation must not accept `advanced` progress while the requirement remains unresolved.

Instrumentation exercise rule: if `instrumentation_exercise_required=true`, derive must include/select an `instrumentation_exercise` item before measurement/comparison/adoption work that depends on the supplied fields. A fresh run id with non-empty fields according to `instrumentation_field_map` is required; `derived_from_existing_artifacts=true` is insufficient.

Acceptance encoding rule: live-run acceptance must preserve original quantifiers and require a post-item run id. If a derived artifact, code contract, or report-only matrix is used instead, set `acceptance_diluted=true`; validation must return partial and preserve residual scope.

Guard-stacking rule: verifier, guard, or report-only change sets with no fresh run id and the same target artifact key are counted as `verifier_surface_hardening` regardless of verifier names. When `guard_stacking_cap_reached=true`, consumers must remove further guard/verifier/report addition from allowed dispositions.

Run disposition rule: `candidate_degraded` is durable quality-miss evidence, not canonical success. Consumers may use only independently verified axes for baseline/comparison and must not let a degraded candidate replace a known-good baseline without separate promotion evidence. `failed_closed` means unsafe output was discarded.

Runtime config echo rule: `runtime_config_echo` is safe scalar failure-autopsy evidence. `config_origin=code_default` overrides can route to self-inflicted gate/default repair when they explain the blocker.

Execution starvation rule: `execution_starvation=true` does not force unsafe execution, but it raises execution-producing candidates above another guard/report/contract task in derive ranking unless safety, authority, or terminal constraints block execution.

Scenario coverage rule: `scenario_uncovered=true` means no validation asset or live run satisfied a scenario premise. Consumers must route validation-set planning or fixture/live-run supply before close. `acceptance_inversion=true` means the observed or asserted state contradicts the expected terminal state for a premise-satisfying input; validation remains partial and derive routes code/contract repair even if tests are green.

Command provenance rule: `command_provenance_missing=true` means the run lacks full body-free argv. Consumers must not use that run for baseline, A/B, comparison, or reproduction evidence. Redaction may mask values but must preserve argument names.

Blocker actionability rule: `blocker_opacity=true` means a gate returned only a state/code without the violated relation, observed scalar values, expected relation, or minimum input delta. Consumers warn on first observation and feed blocker-contract repair after repeated opacity for the same gate. When the violation is an implicit relation across multiple caller inputs, preserve abstract input-key names and `authorization_contract_repair_candidate=true` if a named single authorization input would make the precondition discoverable.

Stochastic feasibility rule: `predetermined_unreachable=true` and `floor_edge_envelope=true` are contract-revision findings. Retry does not satisfy the finding unless a new variance/slack packet proves the contract became feasible.

First-fire rule: `instrumentation_first_fire=true` is a positive evidence delta even when the run disposition is failed or degraded. It may be credited to one workflow item only and cannot also prove goal progress or consume the instrumentation supply item.

Expectation lineage rule: `expectation_lineage_stale=true` means an output-derived scalar expectation points to a superseded anchor. Consumers must rebaseline against `designated_baseline`, explicitly descope, terminal-block, or user-escalate before dependent live execution. `expectation_anchor_missing=true` is warn-only but cannot be lineage-verified expectation evidence.

Comparison parity rule: `parity_unverified=true` or any `parity_axis_status=unknown` makes comparison/adoption provisional. Consumers must not finalize adoption, baseline promotion, or comparison-winner claims until parity axes are resolved or residual/terminal/escalation state is recorded.

Adoption axis rule: failed `gating` axes and `measured_but_disqualified=true` block adoption regardless of tradable-axis wins. Majority-vote adoption without `adoption_axis_classification` is provisional only.

Resolution downgrade rule: `resolution_downgrade=true` means a higher-resolution evidence contract was satisfied only by a surrogate. Consumers may preserve first occurrence as warning/provisional evidence; repeated same-contract downgrade should route resolution restoration or contract revision. Do not treat it as full-resolution proof.

Report key integrity rule: `report_key_divergence=true` blocks pass/close/adoption/baseline/comparison/high-water consumption of that report. Matching duplicate keys are schema debt; divergent values are blocking because no consumer can know which copy is authoritative.

Lane identity rule: `pass_on_stale_lane=true` means the verifier pass is valid only for the artifact lane it actually inspected. Consumers must not use it for current-lane capability, adoption, comparison winner, or next-rung prerequisites until a current-lane run or residual item resolves `current_lane_residual_required`. If lane hooks are missing, preserve `lane_identity_missing` as warning evidence and keep legacy consumption.

Decision freshness rule: `decision_metadata_revision=true` means a task updated labels, annotations, or decision metadata without a fresh measurement after relevant upstream production contract changes. It may be useful governance evidence, but it cannot consume a measurement/adoption pack item, reset high-water movement, or count as `goal_productive`.

When the artifact class has implementation/deliverable/review lineage, preserve this projection inside the existing result packet rather than flattening it into one freshness boolean:

```yaml
decision_freshness_lineage:
  applicability: applicable|not_applicable
  decision_subject_id: <opaque_id>
  decision_subject_digest: <full_sha256>
  latest_implementation_revision_id: <opaque_id_or_null>
  latest_compatible_deliverable_revision_id: <opaque_id_or_null>
  latest_semantically_reviewed_deliverable_revision_id: <opaque_id_or_null>
  lineage_status: all_current|implementation_ahead_of_artifact|artifact_ahead_of_review|no_domain_artifact|not_applicable
  fresh_measurement_receipt: <exact-subject_content-bound_receipt_or_null>
  no_impact_receipt: <exact-subject_content-bound_receipt_or_null>
```

`all_current` requires all three revisions to agree when a domain artifact exists. `implementation_ahead_of_artifact` remains stale until a compatible deliverable is produced; a report or fixture does not repair it. `artifact_ahead_of_review` preserves the artifact-production fact but blocks review-backed readiness. `no_domain_artifact` is a normal state for non-domain work but cannot prove semantic artifact movement. A producer-run-applicable decision requires a measurement receipt containing the current implementation input revision, run id, output fingerprint, subject identity, and content digest. A no-impact receipt is allowed only for non-producer-run dimensions and must bind the same subject/revision plus a named predicate and evidence digest. Scalar or truthy no-impact flags fail closed.

Terminal authority rule: terminality, local resolvability, external waiting, and risk/cost confirmation are independent axes. For every terminal-relevant residual preserve an opaque `item_id`, `resolution_kind_id`, `authority_status=already_granted|new_authority_required|unverified`, `local_resolution_status=available|unavailable|unverified`, `external_dependency=none|waiting_state|missing_external_input|unverified`, `risk_or_cost_confirmation=required|not_required|unverified`, explicit `classification_valid`, and bound evidence IDs. Any non-unverified authority/external/risk assertion needs governance evidence; both available and unavailable local-capability assertions need capability evidence. Local resolution prohibits goal-terminal classification; waiting state routes the existing monitor/harvest owner; new authority or risk/cost confirmation routes user escalation; omitted validation flags, empty required evidence, or any unverified axis routes bounded classification repair. Pack exhaustion and task close are not authority evidence.

Gating-axis producer rule: `axis_starved_by_missing_producer=true` means a gating axis is zero or unmet because the producer path that should populate it is absent or unexercised. Consumers must select producer-supply work or terminal/escalation/descope; another verifier, guard, or report over that axis is verifier-surface hardening until producer supply fires.

Portfolio quota rule: `portfolio_quota_exceeded=true` with `portfolio_quota_mode=restrict` limits the next selected work kind to producer, envelope, long-run, descope-with-residual, terminal blocker, or user escalation. With `portfolio_quota_mode=warn`, preserve the ratio but do not restrict selection.

Cycle reachability rule: `unreachable_within_cycle=true` means the required acceptance scale exceeds observed cycle throughput times the cycle cap. Consumers must route long-run launch with monitor/harvest plan, throughput improvement, explicit residual descope, terminal blocker, or user escalation. Repeating a small smoke at the same scale is not goal-productive.

Metric basis rule: `basis_overclaim=true` downgrades the affected metric to `actual_basis_class`. The value can remain trace evidence, but consumers must treat movement as producer-attested or otherwise downgraded under F2 unless later evidence proves the claimed basis from appropriate inputs. Honest downgrade does not count as regression.

Surface-field review rule: `surface_field_defect_matrix` is scalar review evidence keyed by field class and defect class. Nonzero counts feed root-family/producer-supply derivation; missing `surface_field_classes` fails quiet with `field_class_map_missing` and must not invent domain fields.

Adapter mandate rule: `adapter_mandate_required=true` means adapter contract gaps have repeated for the same `artifact_family` with no quality/substance high-water improvement for the configured cap. Consumers must select adapter registration/strengthening as the next goal-productive task, or terminal/user-escalate with the exact missing adapter contract. If `adapter_wiring_defect=true`, do not use this rule for the same cycle; route the registered-but-unloaded adapter as self-inflicted wiring/load correction.

Adapter hook demand rule: `adapter_hook_demand` is a cumulative hook-demand ledger embedded in the existing family progress registry rows, not a new artifact. `decision_relevant_skip` means the gate's non-hook inputs were already sufficient and only the missing adapter hook caused the fail-quiet skip, using only adapter-free checks to avoid recursion. When any `decision_relevant_skip_count` reaches `hook_demand_threshold`, G-ADAPTER emits `hook_supply_required=true` and `demanded_hooks`; this signal guides derive selection but does not by itself hard-stop the current packet.

Cumulative chain rule: `cumulative_goal_distance_stalled=true` means the same adapter-collapsed root family, or the same `artifact_family` when adapter collapse is unavailable, has not improved quality/substance high-water for the configured cap. If `cumulative_untried_chain_without_quality_delta=true`, distinct untried hypothesis labels do not override terminal/user escalation. When `chain_stall_forced_retarget_gate.chain_stall_force_retarget=true`, derive must first choose an actionable `forced_selected_task` option when one exists; only an empty option set permits terminal/user escalation.

Dominant-parameter key rule: when `root_dominant_parameter_key` is supplied, distinct-root-cause vetoes and stall streaks are keyed by the adapter-collapsed root plus that parameter, not by proximate blocker labels. If the key is absent, keep the legacy key path without inventing domain-specific parameters.

Primary metric C4 rule: when `primary_metric_gate.primary_metric_stalled=true`, C4 forced retargeting is keyed by zero high-water movement on the adapter-owned primary metric. Renamed labels, facets, or version suffixes cannot reset that trigger. If no `forced_selected_task_options` are actionable, emit `c4_user_escalation_backstop_required=true` and a single user-escalation handoff with the missing input, authority, or evidence kind.

Primary metric partial-order rule: strict movement in the declared set direction and Pareto dominance may advance high-water. A non-nested set relation or a Pareto trade-off is `metric_comparability_status=incomparable`; preserve the prior high-water value and digest, the prior zero-movement streak, and any existing stalled state. Such an observation neither moves high-water nor increments/resets the stall counter. A changed, otherwise valid metric basis is `basis_migration_observed=true`. It establishes a new baseline only when `basis_migration_receipt` has the exact closed contract-version-1 shape and recomputed receipt digest, independently verified provenance, opaque receipt/basis/mapping/verifier IDs, old/new basis IDs, prior observation digest, old/new lineage IDs, mapping digest, exact decision-binding digest, exact verification-gate digest, and a new-observation-input digest recomputed from the current contract, normalized value, subject binding, and verification gate. The nested independent-verification receipt additionally binds a verifier revision, non-empty disjoint producer/verifier input-ID sets, different producer/verifier invariant owners, `source_overlap_status=disjoint`, and `invariant_separation_status=independent`; a rehashed coupled receipt is invalid. Its only accepted comparability verdict is `new_baseline_required`; the resulting gate is `basis_migration_status=verified_new_baseline`, `metric_comparability_status=basis_migration_new_baseline`, and `primary_metric_high_water_moved=false`. Missing or invalid receipts remain `basis_migration_no_comparable_baseline` and cannot be reloaded as the new basis baseline. Migration never erases the prior zero-streak/stall observation. Content hashes bind normalized values and the exact comparison contract; a non-scalar prior row with a missing or mismatched high-water digest is not a baseline.

Primary metric observation rule: keep canonical `metric_observation` material plus `metric_observation_sha256` in the live evaluation packet. It binds the normalized contract/current value, high-water value/digest, zero-streak/stall/comparability state, exact current decision subject and explicit applicability rows (or the complete legacy bridge), verification-gate digest, provenance, and compatible decision-consumption receipt. Before family-progress durable projection, replace every raw non-scalar value, raw string collection, and unbounded string in current/prior/high-water/observation/comparison-config value positions with exact `{contract_version, value_ref, full_content_sha256, summary}` material. `value_ref` is derived from the digest; `summary` carries only the registered value kind, scalar/enum/collection/vector class, and cardinality. Mark that gate `durable_value_projection_status: reference_only`. Recompute live observation and high-water digests after owner rehydration; never treat a reference-only durable row as a comparable value by digest alone. A digest-only legacy scalar, reference-only non-scalar, self-declared exact/independent label, stale/conflicted subject, missing material, tampered binding, or incompatible gate is diagnostic trace only and cannot supply a baseline, high-water, or stall reset.

Verifier coupling rule: `pass_with_coupled_verifier=true` means a passing verifier gate had a mapped verifier source path modified in the same change set. Consumers must not use that pass for close, high-water movement, semantic progress, or `goal_productive`. Route to non-coupled revalidation, independent evidence recalculation, explicit residual descope, terminal blocker, or user escalation.

Evidence provenance rule: `attested_only_movement=true` means one or more metrics moved only through producer-attested evidence. The movement must not update high-water, reset G-CHAIN/C4 stall counters, or satisfy `goal_productive`. If `evidence_provenance(...)` is provided, missing per-field provenance is `producer_attested`; if it is absent, keep legacy accounting.

Verification separation rule: consume `independently_verified_fields` only when the axis receipt proves disjoint verification/producer identities or fingerprints and a distinct decisive-invariant owner. Preserve explicit root-local structural `self_grounded`, but do not promote it to source-independent semantic evidence. Missing, overlapping, coupled, unknown, global self-grounded, or semantic self-grounded fields cannot drive high-water movement, close, or `goal_productive`.

Actual artifact truth rule: when measurable acceptance requires body truth, use `truth_basis` precedence `independently_recomputed_actual_artifact`, `source_separated_verifier`, `current_transform_report`, `producer_report`, `carried_forward_report`, then `workflow_status_claim`. Preserve `body_projection_fingerprint`, `recomputed_fields`, `source_artifact_ids`, and `current_artifact_id`; keep carried values in `source_*` and current transform values in `current_*`. `report_body_divergence` is distinct from `report_key_divergence`, and either blocks positive consumption. Missing required projection is `not_evaluated`, never pass.

Consumer context rule: `consumer_context_conformance` rows are actual invocation receipts keyed by project-owned required consumer IDs or a decision-required hook that was invoked. Each required row includes `consumer_context_id`, exact artifact/body/lane/cohort echoes, current `cycle_id`, `input_state_fingerprint`, `attempt_identity`, `adapter_loaded`, `hook_resolved`, `required_hook_callable`, `hook_signature_compatible`, `invocation_completed`, `return_contract_valid`, `artifact_identity_echo_valid`, `value_consumed_by_decision`, `evidence_provenance`, a non-empty `probe_evidence_ref`, and `probe_evidence_sha256`. Legacy single-hook rows remain valid when no explicit manifest/consumer/decision set exists. Otherwise require `consumer_contract_version: 2`, a full `consumer_revision_sha256`, the registered `validator_signature_sha256`, and closed `hook_io_receipts` rows binding invocation index, hook ID, exact input/output digests, callable-signature digest, and completed/failed/unavailable status. Also require exact current `task_id`, `adapter_revision_sha256`, expected `hook_id`, `required_hook_ids`, `required_gate_ids`, `consumed_hook_ids`, `consumed_gate_ids`, `excluded_gate_ids`, and `result_contract_status`. Completed required hook I/O must equal consumed hooks; consumed hooks equal required hooks. Consumed and excluded gates are disjoint and their union equals required gates. Bind version, validator, hook I/O, arrays, and status into the canonical hash. Any excluded required gate is `not_evaluated`, including incompatibility; never remove it from required scope. Recompute the SHA-256 before consumption, compare the row to the external expected contract, and require every duplicate row across existing conformance aliases to pass. Only source-separated runner receipts or the consumer's current direct invocation are pass-eligible; producer rows remain diagnostic. Optional absent hooks are not global failures. Repository-root import, hook strings, metric labels, rehashed booleans, arbitrary full hashes, or adapter self-attestation do not satisfy a row.

Explicit identity floor rule: an artifact envelope that declares `decision_identity_kind: explicit_v2` or an identity-bearing `contract_version: 2` remains explicit-v2 after nested-ref extraction. A nested legacy identity, missing explicit echo, wrapper fallback, or omitted attempt binding is `consumer_wiring_defect`; it cannot become a verified legacy selection, adapter absence, exact no-change, or terminal justification. The existing hash-bound handoff keeps the packet ref/digest; derive and finalization reopen that packet and compare its complete `decision_artifact_ref` and `attempt_identity` with the actual current decision and the derive-owned `finalization_consumption.attempt_id`. A metadata-only verification receipt cannot substitute for the producer body. `legacy_v1` remains valid only when no explicit-v2 floor exists for that attempt.

Terminal self-resolution rule: normalize residuals to `current_envelope_mutation_allowed`, `local_diagnostic_possible`, `local_deterministic_repair_possible`, `bounded_producer_execution_possible`, `new_authority_required`, `new_external_input_required`, `external_state_change_required`, or `unverified`. Re-evaluate the same gate after existing root-cause/disposition synthesis and before returning the candidate. Any of the first four classes, or an unverified required classification, prohibits a goal-terminal claim.

Progress ownership rule: run/review packets provide observation claims. This packet owns the loopback candidate for `authoritative_semantic_progress`; completion validation may only preserve or downgrade it while constructing the final verdict candidate. `$orchestrate-task-cycle` owns the atomic finalization write and receipt. No consumer may treat the packet, a registry projection, ledger entry, or seal candidate as current durable truth without a matching receipt. Terminal-outcome change is positive only with independent evidence, no conflict, and all required integrity axes evaluated.

Prepared-mutation rule: `registry_updated=false` is invariant for loopback evaluation. `registry_update_candidate`, `registry_update_status`, `write_registry_deferred`, and `durable_mutation_candidate` expose the exact v2 typed-operation contract for existing registry, ledger, seal, and applicable recurrence projection. The outer candidate binds `contract_version: 2`, producer, attempt, ordered operation IDs/expected target revisions, operation-set digest, and candidate digest. Each operation binds deterministic operation/idempotency IDs, target kind/ref, registered operation kind, target revision CAS, the same attempt, dependencies, payload schema, complete replayable payload/digest, and recovery policy; aliases must exactly echo canonical fields. Hashes without payloads, anonymous/v1 producers, and generic empty operation lists are invalid. A true empty delta uses only the ledger helper's exact same-attempt `no_durable_state_change` reason/evidence receipt. `--write-registry` requests preparation only; it never performs a write. A later evaluation may consume a finalized projection only through `orchestrate_task_cycle.load_current_finalized_state(root, finalized_cycle_id)`; never trust an unverified packet copy or select a prior cycle by mtime.

Durable privacy rule: only finalization operation payloads are bounded; the immutable candidate packet remains diagnostic evidence. Projection payloads retain opaque identifiers, full content hashes, enums, reason codes, counters, lanes, and required gate scalars. They exclude source/work/artifact paths, locators, direct quotations, titles, offsets, exact character counts, timestamps, trace-only task/family labels, path-like provenance references, and verbose finding evidence. Operation `target_ref` may identify the generic workflow artifact path but is not part of the state payload.

Terminal self-resolution rule: before terminal/escalation, classify every residual as `self_resolvable_local`, `offline_recompute`, `existing_authority`, `genuine_new_authority`, `external_state_change`, or `unverified`. The first three prohibit goal terminal; missing required classification sets `offline_scope_unverified`. Distinguish pack exhaustion, authority block, goal terminal, and quiescent latch in the existing terminal disposition.

Gate evaluation rule: required gate packets use `evaluation_status: pass|fail|not_evaluated`. `not_evaluated` is not a pass. A required verifier with no explicit passing verifier status is `not_evaluated`. Consumers may fail quiet only when no measurable acceptance or caller contract says the gate is required.

Reachability rule: `acceptance_unreachable_under_frozen_config=true` means the abstract acceptance minimum and frozen envelope are incompatible. Consumers must select constraint relaxation, reserve `envelope_thaw_item` with thaw condition/schedule, explicitly descope with residual scope, or `user_escalation`; another envelope-internal micro-repair is not goal-productive.

Envelope thaw rule: `envelope_thaw_item_required=true` is unresolved reachability debt. Consumers must not complete or advance frozen-envelope-unreachable acceptance without `envelope_thaw_item`, residual/descope, terminal blocker, or user escalation. Repeated thaw omission can be a blocking G-REACH finding.

Acceptance envelope rule: `acceptance_envelope_contract` binds a measurable target to an adapter-owned minimum envelope. If `envelope_below_floor=true`, consumers must treat the slice as acceptance-incomplete and choose envelope expansion, explicit descope with residual scope, or user escalation. Do not lower the target and do not reclassify the planned failure as a new prompt/tool/schema blocker.

Metric validity rule: `oracle_metric_validity_gate.metric_goal_productive_excluded=true` means an oracle/metric can pass tautologically. Consumers must not use that metric pass as goal-productive evidence without independent changed-and-semantic output-delta proof. Missing metric validity self-check is warning-only.

Verifier completeness rule: `unverifiable_acceptance_contract=true` means measurable acceptance is incomplete because the required live verifier is `not_evaluated`. Consumers must preserve a verifier-hook follow-up, explicit descope with residual scope, terminal blocker, or user escalation; they must not mark the original target consumed.

Required-hook rule: a gate named by measurable acceptance inherits E2 verifier completeness for its required adapter hooks. If the hook is missing, unloaded, or `not_evaluated`, set or preserve `unverifiable_acceptance_contract=true`; fail-quiet does not mean pass for a required gate.

Residual gap rule: `marginal_repair=true` or a below-threshold `residual_gap_policy` means derive should compare another same-gap repair against explicit descope-with-residual plus the next capability-ladder rung. The packet carries the adapter-owned abstract comparison only; thresholds and domain metrics stay outside this schema.

Residual gap cost rule: when cycle-efficiency evidence supplies cost fields, compare residual work by value per cycle cost. If `marginal_value_per_cycle_cost` is below adapter policy, consumers must prefer descope-with-residual plus the next rung unless a higher value case is recorded. If cost fields are absent, the denominator is `1` and the legacy F3 rule is unchanged.

Goal-axis completeness rule: a review-backed pass is not consumable for a measurable goal when `pass_with_unobserved_axes=true` or that goal appears in `unobserved_goal_axes`. Consumers must preserve adapter axis-supply work, explicit residual descope, terminal blocker, or user escalation. Missing `goal_axis_map` fails quiet to legacy review semantics.

Balance rule: `requires_correction_or_terminal=true` blocks another detection-only next task as goal-productive. Consumers must choose correction/implementation work, `terminal_blocked`, or `user_escalation`.

Idempotent replay rule: re-running the same `cycle_id` for the same `family_key` must preserve the recorded measurement, blocker-mutation, disposition, consolidation, and finding fields from the existing row. A replay must not erase A1/A2 progress fields by treating its own check IDs or frontiers as prior evidence.

Unchanged packet rule: when ledger events reference packet content that is identical by the exact path-and-hash pair to a previous event, consumers should store/use `unchanged_ref(path+hash)` instead of reserializing identical packet bodies. A same path with another hash, or another path with the same hash, is not that reference. Profile/cost consumers should count `unchanged_ref_count` separately from fresh fixed-cost evidence. Storage reduction is neither semantic progress nor permission to delete audit evidence.

Metric rule: `quality_signal_confidence=low` is insufficient evidence for semantic progress and must fail closed as `conservative_hold`.

Generalization rule: quality metrics must come from the repository domain adapter or shared repository module, not producer-local token lists. Fallback name checks must use Unicode letter/category handling and external thresholds from repository-owned config; missing or unfamiliar language/script support lowers confidence rather than silently treating all names as absent.

Adapter rule: domain-specific paths, metrics, lexicons, and thresholds belong in the repository domain adapter or repository-owned shared module. The skill and producer should call only the adapter interface and remain domain-agnostic.

Advice freshness rule: `advice_freshness_gate.advice_metrics_stale=true` is a warn-level signal that active/root advice declares output fingerprint claims that do not match the current adapter/output fingerprint. Consumers should refresh, defer, or reject the advice before relying on its headline metrics.

Gate regression rule: `advice_freshness_gate.gate_result_regression_stale=true` is warn-only evidence that a gate verdict regressed from passed to blocked under a stable environment fingerprint. Consumers should combine it with `gate_selfcheck` or provenance-hardened root-cause evidence before routing a gate-fix task; it is not a separate hard gate.

Partial axes rule: `partial_progress_axes_gate.status=warn` recommends decomposing all-or-nothing progress gates when adapter-reported partial axes exist but quality/substance high-water remains flat. Consumers must not treat this warning as progress or as a blocker by itself.

Structure rule: `structure_metrics_gate.structure_consolidation_recommended=true` is a warn-level signal that Class C surface reduction, semantic consolidation, reuse extraction, coupling reduction, module extraction, or responsibility separation may be valid when it reduces the reported structure burden. When `refactor_effect_required=true`, downstream validation must require `structure_high_water_moved=true` or explicit residual/descope handling before closing the refactor as complete. File/module count increases, relocated helpers, token/pattern avoidance, and producer self-reports are not structure high-water movement unless adapter `structure_metrics` records real movement on a project-owned axis. When `structure_high_water_key_scope=global_invariant`, selected-scope improvement is insufficient unless `global_structure_high_water_moved=true` or equivalent global invariant movement is present. Absence of this optional adapter output must not crash packet production.

OCR and typo rule: typoed extractor labels, OCR provenance, and OCR near-duplicate placeholder surfaces must fail closed. Missing or incomplete repository-owned threshold config must preserve the affected check as `not_evaluated` or `budget_unverified`, with no positive credit; do not invent a generic numeric threshold.

## Static Decision-Boundary Fixtures

- Exact consumption negative: `consumer_C` presents a receipt for `attempt_A` while the current decision is `attempt_B`, or the row came only from a producer packet. Expected verdict: the consumer and affected semantic/goal result are `not_evaluated`. Forbidden overclaim: accepting matching artifact names or a syntactically valid arbitrary hash.
- Exact consumption happy path: `consumer_C` directly consumes `artifact_revision_R`, echoes `body_fp_A`, `lane_L`, `source_cohort_C`, current attempt/input identities, and a recomputable receipt digest. Expected verdict: the consumer row passes its own conformance gate. Forbidden overclaim: promoting final readiness from that row alone.
- Explicit-floor negative: an outer explicit-v2 envelope or identity-bearing contract version 2 contains a legacy nested identity, or an explicit packet reaches derive through a legacy/downlevel handoff. Expected verdict: `consumer_wiring_defect`, with dependent consumption left `not_evaluated`. Forbidden overclaim: compatibility fallback to `legacy_v1`.
- Legacy happy path: no explicit-v2 marker exists and the complete legacy identity is exact for the applicable attempt. Expected verdict: preserve the existing legacy decision path. Forbidden overclaim: inferring legacy applicability merely from a missing explicit argument.
- Primary metric negative: a secondary structure scalar moves from `1` to `2` while independently verified `axis_G` and `body_fp_A` are unchanged. Expected verdict: bounded secondary evidence may be retained, but primary high-water does not move and global stall remains. Forbidden overclaim: resetting stall from secondary movement.
- Primary metric happy path: exact-bound, independently verified `axis_G` moves from `1` to `2` for the same stable axis id. Expected verdict: only `axis_G` becomes a high-water candidate. Forbidden overclaim: marking other axes, task completion, or final publication as passed.
- Terminal negative: `residual_A` is `local_deterministic_repair_possible` or `bounded_producer_execution_possible`. Expected verdict: goal terminal is prohibited. Forbidden overclaim: reporting no local actionable root cause.
- Terminal happy path: every residual is classified as new authority, new external input, or external state, with no local actionable class and complete evidence. Expected verdict: this gate no longer vetoes the existing terminal reducer. Forbidden overclaim: asserting that terminal is independently proven.
- Compact-reference negative: `artifact_A` keeps its path but changes hash. Expected verdict: record fresh evidence rather than `unchanged_ref`. Forbidden overclaim: treating lower storage as progress.
- Compact-reference happy path: the exact path-and-hash pair is unchanged. Expected verdict: use one `unchanged_ref(path+hash)` and preserve the earlier audit evidence. Forbidden overclaim: deleting history or resetting any stall.
