# Loopback Audit Packet Schema

Required fields:

- `schema_version`: `anti-loop-progress-gate-v1`
- `step`: `loopback_audit`
- `cycle_id`
- `family_key`
- `root_key`
- `root_family_key`
- `artifact_family`
- `semantic_signature`
- `changed_vs_previous`
- `semantic_progress`
- `terminal_outcome_changed`: observed terminal/domain outcome changed under strict output-delta evidence.
- `same_family_micro_hardening_count`
- `provider_request_count`
- `quality_vector`
- `quality_vector.quality_signal_confidence`: `high`, `medium`, or `low`
- `quality_vector.language_context`: work/document-level language resolution summary when available.
- `quality_vector.extractor_locale_locked`: boolean signal that extractor labels may be locale/length locked.
- `quality_vector.quality_signal_reasons`: include low-confidence causes such as unrecognized extractor statuses, OCR down-weighting, near-duplicate placeholder clustering, or missing threshold defaults when present.
- `previous_accepted_baseline`: baseline source, fingerprint, adapter error if any, and whether the adapter supplied a previous quality vector override.
- `coverage_quality_delta_reconciliation_gate`: R-GCOV packet comparing loopback G-COV with output-delta G-COV when both exist.
- `substance_delta_gate`: G-SUBSTANCE packet comparing adapter-supplied substance vectors.
- `vacuous_corrective_gate`: G-VACUOUS packet summarizing corrective/backfill attempted and resolved counts.
- `adapter_mandate_gate`: G-ADAPTER packet summarizing adapter contract gaps, missing streak, and whether adapter registration/strengthening is mandatory.
- `adapter_wiring_gate`: C1 packet summarizing registered adapter path/load status and whether a registered-but-unloaded adapter must be routed as `self_inflicted_gate_defect`.
- `cumulative_goal_distance_gate`: G-CHAIN packet summarizing high-water stall streak for an adapter-collapsed root family or adapter-missing artifact family.
- `chain_stall_forced_retarget_gate`: C4 packet listing actionable forced retarget options when cumulative goal-distance stall reaches the forced-retarget threshold under lateral churn.
- `primary_metric_gate`: optional adapter-supplied G-CHAIN/C4 trigger packet for single north-star high-water movement.
- `evidence_provenance_gate`: optional F2 packet that records independently verified versus producer-attested metric movement.
- `verification_source_separation_gate`: optional H4 packet proving `independently_verified_fields` have disjoint verification input paths or adapter `self_grounded` status.
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
- `authoritative_semantic_progress`: conservative semantic-progress value after disagreement resolution.
- `substance_delta_gate`: G-SUBSTANCE packet with `current_substance_vector`, `previous_substance_vector`, `improved_axes`, `substance_delta_pass`, `status`, and fail-closed disposition metadata.
- `vacuous_corrective_gate`: G-VACUOUS packet with lane `attempted/resolved` counts, `surface_corrective_noop`, `excluded_delta_lanes`, and `status`.
- `facet_root_map_applied` and `facet_root_map_size`: whether the domain adapter supplied facet-to-root family normalization before cap evaluation.
- `count_key_hygiene_gate`, `generation_dependent_count_key`, `count_key_trace_only`, and `effective_count_key`: G1 fields. They indicate that raw plan/advice/task-pack/cycle/run/date/hash/version key material was excluded from counting and preserved only for traceability.
- `adapter_mandate_required`, `adapter_missing_streak`, `adapter_contract_unmet`, and `adapter_mandate_gate`: G-ADAPTER fields. `adapter_contract_unmet` may include `facet_root_map`, `substance_metrics`, or `quality_vector`.
- `adapter_wiring_defect`, `adapter_loaded`, `adapter_registered`, `adapter_path`, `adapter_expected_path`, and `adapter_wiring_gate`: C1 fields. `adapter_wiring_defect=true` supersedes `adapter_mandate_required` for the current cycle.
- `cumulative_goal_distance_scope_key`, `cumulative_goal_distance_stall_streak`, `cumulative_goal_distance_stalled`, `cumulative_untried_chain_without_quality_delta`, `high_water_vector`, `high_water_last_improved_cycle`, and `untried_veto_overridden_by_chain_stall`: G-CHAIN fields.
- `chain_stall_forced_retarget_gate`, `forced_selected_task`, and `forced_selected_task_options`: C4 fields. Options use abstract `selected_task_kind` values such as adapter wiring/load fixes or adapter-owned capability-ladder rungs.
- `primary_metric_gate`, `primary_metric_high_water_moved`, `primary_metric_zero_movement_streak`, and `primary_metric_stalled`: D4/C4 trigger-key fields when the adapter exposes `primary_metric(...)`. The adapter owns the metric definition and comparison semantics.
- `evidence_provenance_gate`, `independently_verified_fields`, `producer_attested_fields`, and `attested_only_movement`: F2 fields. When provenance is supplied, high-water movement and goal-productive support may use only `independently_verified` fields; untagged fields are `producer_attested`.
- `verification_source_separation_gate`, `verification_input_paths`, `verified_artifact_paths`, `independent_source_separation_status`, and `independently_verified_downgraded_fields`: H4 fields. Missing or overlapping verification inputs downgrade affected independently verified fields to attested unless the adapter marks the axis `self_grounded`.
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
- `measurement_frontiers_observed`: first-observed capability frontiers such as `event_sequence_oracle`, `reconstruction_coverage`, `relation_class_filled`, or `story_vs_narrative_split`.
- `measurement_progress_basis`: introduced check IDs and new frontier observations that justified the exemption.
- `blocker_signature`: stable current blocker identifier before volatile suffix normalization.
- `blocker_root_family`: normalized blocker family used to prevent facet-renaming loops.
- `root_dominant_parameter_key`: optional adapter-owned dominant parameter, such as an acceptance `deficit_axis`, used with the collapsed root family for distinct-root-cause and stall equivalence.
- `blocker_ladder_rung`: current capability-ladder rung for the blocker family.
- `blocker_mutation_kind`: `initial`, `repeat`, `facet_rename`, `lateral`, or `forward_mutation`.
- `forward_mutation_budget_remaining`: remaining count before forward rung movement must force implementation rather than another measurement/governance cycle.
- `observed_delta_class`: compact observed output-delta class such as `node_edge_delta`, `changed_semantic_output`, or `no_observed_domain_delta`.
- `forward_mutation_vacuous`: boolean set when a blocker ladder moved but `terminal_outcome_changed=false`.
- `root_cause_ledger_path`: `.task/anti_loop/root_cause_ledger.jsonl` unless overridden.
- `root_cause_ledger_status`: `recorded` or `not_applicable_no_hypotheses`.
- `root_cause_ledger_entries`: ledger rows proposed or written for this cycle.
- `repo_owned_source_roots`, `repo_owned_source_roots_status`, and `repo_owned_source_roots_error`: optional adapter-supplied repository-owned source glob contract used for provenance-based actionability. `not_provided` is fail-quiet and must not become a new gate.
- `root_cause_unverified_hypotheses`: asserted-actionable hypotheses excluded because they lack structural actionability or provenance.
- `root_cause_duplicate_hypotheses`: hypotheses excluded because they are equivalent to an attempted hypothesis by normalized slug, target surface, and observed delta class.
- `untried_actionable_root_cause_exists`: boolean terminal-blocker veto when at least one verified local, bounded, provider-free, in-scope, authority-allowed or provenance-backed hypothesis remains untried and `hypothesis_exhausted=false`.
- `untried_root_cause_hypotheses`: compact list of remaining actionable untried hypotheses.
- `untried_promotion_budget`: same-family vacuous untried repair cap, default `2`.
- `vacuous_untried_attempt_count` and `vacuous_untried_streak`: count attempted untried repairs with `terminal_outcome_changed=false`.
- `hypothesis_exhausted`: boolean hard stop when the untried budget is spent without terminal outcome change.
- `hypothesis_exhaustion_seal_path`: `.task/sealed_blocker_families.json` path when exhaustion is fed into sealed-family workflow state.
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

Mutation rule: `blocker_mutation_kind=facet_rename` is same-family churn. `blocker_mutation_kind=forward_mutation` counts as blocker-state movement only when stricter gates are clear and `terminal_outcome_changed=true`. If `forward_mutation_vacuous=true`, consumers must not reset loop counters or promote `goal_productive`; route to untried root-cause repair when available, otherwise terminal/user escalation. If `force_implementation_cycle=true`, consumers must choose an in-place implementation task or terminal/user escalation when implementation is not authorized.

Root-cause ledger rule: `root_cause_ledger_entries` are non-GT workflow evidence keyed by `family_key`, `root_key`, and `hypothesized_root_cause`. A hypothesis is untried only when it is actionability-verified and distinct from attempted hypotheses by normalized root cause, target surface, and observed delta class. Assertion-only `actionable=true` rows are `unverified`; version-suffix or rename equivalents are duplicates. If adapter-supplied `repo_owned_source_roots` proves that a hypothesis provenance reference belongs to repository-owned source, derive `local=true`, `in_scope=true`, and `actionable=true` from that provenance and ignore conflicting self-report fields. Do not hardcode project paths in this generic schema; if the hook is absent, keep the old actionability basis. If `untried_actionable_root_cause_exists=true`, `hypothesis_exhausted=false`, and `untried_veto_overridden_by_chain_stall=false`, `terminal_blocked` is invalid unless current authority, safety, or external state makes that hypothesis non-actionable. If `hypothesis_exhausted=true`, derive must stop, terminal-block, or user-escalate unless a supplied input delta changes the family.

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

Adapter mandate rule: `adapter_mandate_required=true` means adapter contract gaps have repeated for the same `artifact_family` with no quality/substance high-water improvement for the configured cap. Consumers must select adapter registration/strengthening as the next goal-productive task, or terminal/user-escalate with the exact missing adapter contract. If `adapter_wiring_defect=true`, do not use this rule for the same cycle; route the registered-but-unloaded adapter as self-inflicted wiring/load correction.

Cumulative chain rule: `cumulative_goal_distance_stalled=true` means the same adapter-collapsed root family, or the same `artifact_family` when adapter collapse is unavailable, has not improved quality/substance high-water for the configured cap. If `cumulative_untried_chain_without_quality_delta=true`, distinct untried hypothesis labels do not override terminal/user escalation. When `chain_stall_forced_retarget_gate.chain_stall_force_retarget=true`, derive must first choose an actionable `forced_selected_task` option when one exists; only an empty option set permits terminal/user escalation.

Dominant-parameter key rule: when `root_dominant_parameter_key` is supplied, distinct-root-cause vetoes and stall streaks are keyed by the adapter-collapsed root plus that parameter, not by proximate blocker labels. If the key is absent, keep the legacy key path without inventing domain-specific parameters.

Primary metric C4 rule: when `primary_metric_gate.primary_metric_stalled=true`, C4 forced retargeting is keyed by zero high-water movement on the adapter-owned primary metric. Renamed labels, facets, or version suffixes cannot reset that trigger. If no `forced_selected_task_options` are actionable, emit `c4_user_escalation_backstop_required=true` and a single user-escalation handoff with the missing input, authority, or evidence kind.

Verifier coupling rule: `pass_with_coupled_verifier=true` means a passing verifier gate had a mapped verifier source path modified in the same change set. Consumers must not use that pass for close, high-water movement, semantic progress, or `goal_productive`. Route to non-coupled revalidation, independent evidence recalculation, explicit residual descope, terminal blocker, or user escalation.

Evidence provenance rule: `attested_only_movement=true` means one or more metrics moved only through producer-attested evidence. The movement must not update high-water, reset G-CHAIN/C4 stall counters, or satisfy `goal_productive`. If `evidence_provenance(...)` is provided, missing per-field provenance is `producer_attested`; if it is absent, keep legacy accounting.

Verification source separation rule: `independently_verified_fields` are consumable only when `verification_input_paths` are disjoint from `verified_artifact_paths`, unless the adapter marks the affected axis `self_grounded`. If `independent_source_separation_status` is `missing`, `overlap`, or `blocked`, consumers must treat `independently_verified_downgraded_fields` as attested and must not use those fields for high-water movement, close, or `goal_productive`.

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

Unchanged packet rule: when ledger events reference packet content that is identical by path and hash to a previous event, consumers should store/use `unchanged_ref(path+hash)` instead of reserializing identical packet bodies. Profile/cost consumers should count `unchanged_ref_count` separately from fresh fixed-cost evidence.

Metric rule: `quality_signal_confidence=low` is insufficient evidence for semantic progress and must fail closed as `conservative_hold`.

Generalization rule: quality metrics must come from the repository domain adapter or shared repository module, not producer-local token lists. Fallback name checks must use Unicode letter/category handling and external thresholds from repository-owned config; missing or unfamiliar language/script support lowers confidence rather than silently treating all names as absent.

Adapter rule: domain-specific paths, metrics, lexicons, and thresholds belong in the repository domain adapter or repository-owned shared module. The skill and producer should call only the adapter interface and remain domain-agnostic.

Advice freshness rule: `advice_freshness_gate.advice_metrics_stale=true` is a warn-level signal that active/root advice declares output fingerprint claims that do not match the current adapter/output fingerprint. Consumers should refresh, defer, or reject the advice before relying on its headline metrics.

Gate regression rule: `advice_freshness_gate.gate_result_regression_stale=true` is warn-only evidence that a gate verdict regressed from passed to blocked under a stable environment fingerprint. Consumers should combine it with `gate_selfcheck` or provenance-hardened root-cause evidence before routing a gate-fix task; it is not a separate hard gate.

Partial axes rule: `partial_progress_axes_gate.status=warn` recommends decomposing all-or-nothing progress gates when adapter-reported partial axes exist but quality/substance high-water remains flat. Consumers must not treat this warning as progress or as a blocker by itself.

Structure rule: `structure_metrics_gate.structure_consolidation_recommended=true` is a warn-level signal that Class C surface reduction, semantic consolidation, reuse extraction, coupling reduction, module extraction, or responsibility separation may be valid when it reduces the reported structure burden. When `refactor_effect_required=true`, downstream validation must require `structure_high_water_moved=true` or explicit residual/descope handling before closing the refactor as complete. File/module count increases, relocated helpers, token/pattern avoidance, and producer self-reports are not structure high-water movement unless adapter `structure_metrics` records real movement on a project-owned axis. When `structure_high_water_key_scope=global_invariant`, selected-scope improvement is insufficient unless `global_structure_high_water_moved=true` or equivalent global invariant movement is present. Absence of this optional adapter output must not crash packet production.

OCR and typo rule: typoed extractor labels, OCR provenance, and OCR near-duplicate placeholder surfaces must fail closed. Missing or incomplete threshold config must use conservative defaults rather than disabling structural placeholder or locale-lock checks.
