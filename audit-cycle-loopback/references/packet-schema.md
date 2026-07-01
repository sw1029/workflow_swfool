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
- `cumulative_goal_distance_gate`: G-CHAIN packet summarizing high-water stall streak for an adapter-collapsed root family or adapter-missing artifact family.
- `acceptance_reachability_gate`: G-REACH packet with abstract acceptance minimum, frozen envelope, reachability verdict, and relaxation/escalation requirement.
- `oracle_metric_validity_gate`: G-OENV packet with optional oracle/metric validity self-check status and tautological-metric exclusion.
- `advice_freshness_gate`: G-ADVICE-FRESH packet comparing declared advice fingerprints to current output fingerprint when available.
- `structure_metrics_gate`: S-STRUCT packet exposing optional adapter-supplied structure metrics and consolidation recommendations.
- `high_water_mark`
- `recommended_disposition`
- `hard_stop_required`
- `evidence_class`
- `not_goal_truth`
- `evidence_paths`

Additive anti-loop gate fields:

- `effective_allowed_dispositions`: intersection of all active constraining gates' `allowed_dispositions`, with `terminal_blocked` and `user_escalation` always preserved as safety valves.
- `disposition_intersection_basis`: per-gate `allowed_dispositions` and `constrains_disposition` basis used to compute the intersection.
- `consolidation_streak`: consecutive recent `consolidation` dispositions whose effective progress is `governance_only`.
- `consolidation_reduces_goal_distance`: always `false` unless a repository-specific gate proves a primary-output transition.
- `validator_disagreement` finding: block-level finding when strict runner validation reports `semantic_progress=true` while output-delta reports `semantic_progress=false`.
- `coverage_quality_delta_reconciliation_gate`: R-GCOV packet with local/external G-COV compact values, `validator_disagreement`, `gcov_metric_name_collision`, `metric_value_conflicts`, `status`, and disposition metadata.
- `validator_integrity_gate`: G-INTEGRITY packet with `validator_integrity`, `validator_coverage`, `status`, `hard_stop_required`, `allowed_dispositions`, and compact findings.
- `authoritative_semantic_progress`: conservative semantic-progress value after disagreement resolution.
- `substance_delta_gate`: G-SUBSTANCE packet with `current_substance_vector`, `previous_substance_vector`, `improved_axes`, `substance_delta_pass`, `status`, and fail-closed disposition metadata.
- `vacuous_corrective_gate`: G-VACUOUS packet with lane `attempted/resolved` counts, `surface_corrective_noop`, `excluded_delta_lanes`, and `status`.
- `facet_root_map_applied` and `facet_root_map_size`: whether the domain adapter supplied facet-to-root family normalization before cap evaluation.
- `adapter_mandate_required`, `adapter_missing_streak`, `adapter_contract_unmet`, and `adapter_mandate_gate`: G-ADAPTER fields. `adapter_contract_unmet` may include `facet_root_map`, `substance_metrics`, or `quality_vector`.
- `cumulative_goal_distance_scope_key`, `cumulative_goal_distance_stall_streak`, `cumulative_goal_distance_stalled`, `cumulative_untried_chain_without_quality_delta`, `high_water_vector`, `high_water_last_improved_cycle`, and `untried_veto_overridden_by_chain_stall`: G-CHAIN fields.
- `acceptance_unreachable_under_frozen_config`, `relaxation_or_escalation_required`, and `acceptance_reachability_gate`: G-REACH fields.
- `oracle_metric_validity_gate`: G-OENV fields. `metric_goal_productive_excluded=true` means tautological metric/oracle evidence cannot support goal-productive progress.
- `advice_freshness_gate`: G-ADVICE-FRESH packet with `current_output_fingerprint`, declared fingerprint claims, stale advice paths, and `advice_metrics_stale`.
- `advice_freshness_gate.gate_result_regression_stale`: warn-only signal for a supplied gate verdict that changed from passed to blocked under a stable environment fingerprint.
- `partial_progress_axes_gate`: warn-only packet with adapter-supplied partial axes and `recommendation: decompose_all_or_nothing_gate` when high-water remains flat.
- `structure_metrics_gate`: S-STRUCT packet with `structure_metrics`, `structure_consolidation_recommended`, `status`, and warning metadata.
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

Disposition rule: consumers must select the next-task disposition from `effective_allowed_dispositions` when present. Do not treat separate gate `allowed_dispositions` as a union.

Measurement rule: `measurement_progress_allowed=true` may reinclude `goal_productive` without setting `semantic_progress=true`; consumers must still preserve no-overclaim boundaries and must stop using the exemption after the root-key or root-family streak cap.

Substance rule: `measurement_progress_allowed=true` requires `substance_delta_gate.substance_delta_pass=true`. Capability-ladder `forward_mutation` promotion requires `terminal_outcome_changed=true` from strict observed output-delta evidence; missing adapter substance metrics still fail closed for measurement promotion, but must not crash packet production.

R-GCOV rule: `coverage_quality_delta_reconciliation_gate.status=block` prevents measurement and capability-ladder promotion from relying on the favorable G-COV source. Consumers must treat the cycle as conservatively blocked until the output-delta and loopback G-COV values agree or the selected next task resolves the disagreement.

Vacuous corrective rule: `vacuous_corrective_gate.surface_corrective_noop=true` means attempted corrective/backfill rows resolved zero items. Consumers must not count those rows as produced or semantic delta.

Integrity rule: `validator_integrity_gate.status=block` prevents validator-derived progress claims. Consumers may choose correction work, but must not cite the validator pass as completion or goal-productive evidence.

Mutation rule: `blocker_mutation_kind=facet_rename` is same-family churn. `blocker_mutation_kind=forward_mutation` counts as blocker-state movement only when stricter gates are clear and `terminal_outcome_changed=true`. If `forward_mutation_vacuous=true`, consumers must not reset loop counters or promote `goal_productive`; route to untried root-cause repair when available, otherwise terminal/user escalation. If `force_implementation_cycle=true`, consumers must choose an in-place implementation task or terminal/user escalation when implementation is not authorized.

Root-cause ledger rule: `root_cause_ledger_entries` are non-GT workflow evidence keyed by `family_key`, `root_key`, and `hypothesized_root_cause`. A hypothesis is untried only when it is actionability-verified and distinct from attempted hypotheses by normalized root cause, target surface, and observed delta class. Assertion-only `actionable=true` rows are `unverified`; version-suffix or rename equivalents are duplicates. If adapter-supplied `repo_owned_source_roots` proves that a hypothesis provenance reference belongs to repository-owned source, derive `local=true`, `in_scope=true`, and `actionable=true` from that provenance and ignore conflicting self-report fields. Do not hardcode project paths in this generic schema; if the hook is absent, keep the old actionability basis. If `untried_actionable_root_cause_exists=true`, `hypothesis_exhausted=false`, and `untried_veto_overridden_by_chain_stall=false`, `terminal_blocked` is invalid unless current authority, safety, or external state makes that hypothesis non-actionable. If `hypothesis_exhausted=true`, derive must stop, terminal-block, or user-escalate unless a supplied input delta changes the family.

Facet rule: adapter-supplied `facet_root_map` entries collapse facet labels before root-family streaks and measurement caps are computed. Without a map, the producer applies only conservative suffix/date/run/facet normalization.

Adapter mandate rule: `adapter_mandate_required=true` means adapter contract gaps have repeated for the same `artifact_family` with no quality/substance high-water improvement for the configured cap. Consumers must select adapter registration/strengthening as the next goal-productive task, or terminal/user-escalate with the exact missing adapter contract.

Cumulative chain rule: `cumulative_goal_distance_stalled=true` means the same adapter-collapsed root family, or the same `artifact_family` when adapter collapse is unavailable, has not improved quality/substance high-water for the configured cap. If `cumulative_untried_chain_without_quality_delta=true`, distinct untried hypothesis labels do not override terminal/user escalation.

Reachability rule: `acceptance_unreachable_under_frozen_config=true` means the abstract acceptance minimum and frozen envelope are incompatible. Consumers must select constraint relaxation or `user_escalation`; another envelope-internal micro-repair is not goal-productive.

Metric validity rule: `oracle_metric_validity_gate.metric_goal_productive_excluded=true` means an oracle/metric can pass tautologically. Consumers must not use that metric pass as goal-productive evidence without independent changed-and-semantic output-delta proof. Missing metric validity self-check is warning-only.

Balance rule: `requires_correction_or_terminal=true` blocks another detection-only next task as goal-productive. Consumers must choose correction/implementation work, `terminal_blocked`, or `user_escalation`.

Idempotent replay rule: re-running the same `cycle_id` for the same `family_key` must preserve the recorded measurement, blocker-mutation, disposition, consolidation, and finding fields from the existing row. A replay must not erase A1/A2 progress fields by treating its own check IDs or frontiers as prior evidence.

Metric rule: `quality_signal_confidence=low` is insufficient evidence for semantic progress and must fail closed as `conservative_hold`.

Generalization rule: quality metrics must come from the repository domain adapter or shared repository module, not producer-local token lists. Fallback name checks must use Unicode letter/category handling and external thresholds from repository-owned config; missing or unfamiliar language/script support lowers confidence rather than silently treating all names as absent.

Adapter rule: domain-specific paths, metrics, lexicons, and thresholds belong in the repository domain adapter or repository-owned shared module. The skill and producer should call only the adapter interface and remain domain-agnostic.

Advice freshness rule: `advice_freshness_gate.advice_metrics_stale=true` is a warn-level signal that active/root advice declares output fingerprint claims that do not match the current adapter/output fingerprint. Consumers should refresh, defer, or reject the advice before relying on its headline metrics.

Gate regression rule: `advice_freshness_gate.gate_result_regression_stale=true` is warn-only evidence that a gate verdict regressed from passed to blocked under a stable environment fingerprint. Consumers should combine it with `gate_selfcheck` or provenance-hardened root-cause evidence before routing a gate-fix task; it is not a separate hard gate.

Partial axes rule: `partial_progress_axes_gate.status=warn` recommends decomposing all-or-nothing progress gates when adapter-reported partial axes exist but quality/substance high-water remains flat. Consumers must not treat this warning as progress or as a blocker by itself.

Structure rule: `structure_metrics_gate.structure_consolidation_recommended=true` is a warn-level signal that Class C surface reduction, module extraction, or responsibility separation may be valid when it reduces the reported structure burden. Absence of this optional adapter output must not crash packet production.

OCR and typo rule: typoed extractor labels, OCR provenance, and OCR near-duplicate placeholder surfaces must fail closed. Missing or incomplete threshold config must use conservative defaults rather than disabling structural placeholder or locale-lock checks.
