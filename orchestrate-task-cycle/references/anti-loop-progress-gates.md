# Anti-Loop Progress Gates

Use this reference when recent task-cycle evidence shows safe but stationary work: repeated no-live contracts, metadata-only output, unchanged primary artifacts, provider avoidance, or repeated command-surface hardening. These gates are workflow controls, not goal truth, authority, issue closure evidence, or permission grants.

## Contents

- [Ownership](#ownership)
- [Domain-Adapter Contract](#domain-adapter-contract)
- [Part D In-Place Revision Contract](#part-d-in-place-revision-contract)
- [G1 Disposition Intersection Gate](#g1-disposition-intersection-gate)
- [G0 Pre-Cycle Regression Guard](#g0-pre-cycle-regression-guard)
- [G0-SAT Gate Satisfiability Precheck](#g0-sat-gate-satisfiability-precheck)
- [G2 Qualitative Review Clamp](#g2-qualitative-review-clamp)
- [G3 Strict Output Delta](#g3-strict-output-delta)
- [R-GCOV Coverage Gate Reconciliation](#r-gcov-coverage-gate-reconciliation)
- [G-INTEGRITY Validator Integrity And Coverage](#g-integrity-validator-integrity-and-coverage)
- [G-COV Coverage/Quality Delta Gate](#g-cov-coveragequality-delta-gate)
- [G-SUBSTANCE Output Substance Gate](#g-substance-output-substance-gate)
- [G-VACUOUS Vacuous Corrective Gate](#g-vacuous-vacuous-corrective-gate)
- [G-MEAS-CAP Measurement Exception Cap](#g-meas-cap-measurement-exception-cap)
- [G-FACET Root-Family Measurement Cap](#g-facet-root-family-measurement-cap)
- [G-ADAPTER Adapter-Mandate Gate](#g-adapter-adapter-mandate-gate)
- [G-CHAIN Cumulative Goal-Distance Gate](#g-chain-cumulative-goal-distance-gate)
- [G-REACH Acceptance Reachability Gate](#g-reach-acceptance-reachability-gate)
- [G-OENV Oracle/Metric Validity Gate](#g-oenv-oraclemetric-validity-gate)
- [G-ADVICE-FRESH Advice Freshness Gate](#g-advice-fresh-advice-freshness-gate)
- [G-BALANCE Detection/Correction Balance](#g-balance-detectioncorrection-balance)
- [G-DISPATCH Provider/Scale Duty Gate](#g-dispatch-providerscale-duty-gate)
- [G4 Behavior-Based GT Conflict Detection](#g4-behavior-based-gt-conflict-detection)
- [G5 Command-Surface Hard Stop](#g5-command-surface-hard-stop)
- [S-STRUCT Structure Signal](#s-struct-structure-signal)
- [G5b Consolidation Streak Cap](#g5b-consolidation-streak-cap)
- [G6 Same-Family Micro-Hardening Limit](#g6-same-family-micro-hardening-limit)
- [G7 Loopback Progress Packet](#g7-loopback-progress-packet)
- [A1 Measurement Progress Exemption](#a1-measurement-progress-exemption)
- [A2 Blocker Forward-Mutation Ledger](#a2-blocker-forward-mutation-ledger)
- [A2b Root-Cause Hypothesis Ledger](#a2b-root-cause-hypothesis-ledger)
- [A3 Terminal-Blocked Exit Guard](#a3-terminal-blocked-exit-guard)
- [A3b Terminal Quiescence Gate](#a3b-terminal-quiescence-gate)
- [A3c Terminal Escalation Gate](#a3c-terminal-escalation-gate)
- [A4 Advice-Intake Coherence Gate](#a4-advice-intake-coherence-gate)
- [A5 Command-Surface Carve-Out](#a5-command-surface-carve-out)
- [Capability Ladder Router](#capability-ladder-router)
- [No-Overclaim Boundaries](#no-overclaim-boundaries)

## Ownership

- `orchestrate-task-cycle` owns packet assembly, script execution, stage ordering, and hard-gate enforcement before derive.
- `review-cycle-output-quality` owns direct qualitative inspection and progress caps from inspected output quality.
- `derive-improvement-task` owns final next-task selection, candidate retention, task-pack mutation, and terminal-blocker state.
- Repository-specific scripts may produce packets, but they do not replace the skill-owned decision gates.

## Domain-Adapter Contract

Gate logic must stay domain-agnostic. A repository may supply a domain adapter to `$audit-cycle-loopback` with `--domain-adapter <path.py>`, `TASK_CYCLE_DOMAIN_ADAPTER_PATH`, or the conventional `.task/domain_adapter.py` path when present. The adapter owns domain-specific paths, metric names, lexicons, thresholds, and artifact interpretation. The workflow consumes only these interfaces:

- `quality_vector(...)`: coverage/quality vector for G-COV.
- `substance_metrics(...)`: primary-output substance vector for G-SUBSTANCE.
- `corrective_resolution(...)`: corrective/backfill lanes with `attempted/resolved` counts for G-VACUOUS.
- `facet_root_map(...)`: facet labels mapped to root families for G-FACET.
- `min_envelope_for(target, **context)`: optional D1 helper returning adapter-owned `envelope_floor` and `deficit_axis` for measurable acceptance targets.
- `output_fingerprint(...)`: current primary-output fingerprint for G-ADVICE-FRESH.
- `previous_accepted_fp(...)`: previous accepted primary-output fingerprint, optionally with previous quality/high-water vector, for R-GCOV baseline selection.
- `structure_metrics(...)`: optional structure metrics for S-STRUCT, such as entrypoint LOC, command count, active/legacy ratio, mechanical shard count, version-suffix file count, global-rebinding/coupling signal count, duplicate definition count, tree depth, directory fan-out, reuse ratio, max file LOC, consolidation recommendation, `structure_high_water_moved`, `improved_structure_axes`, and `refactor_effect_required`.
- `producer_progress_claim_fields(...)`: optional D2 helper listing producer-owned progress/completion fields that must be stored only as `observed_producer_claim`.
- `adapter_load_status(...)` or packet fields `adapter_loaded`/`adapter_path`: optional registered-adapter load status. A registered adapter that is not loaded is `adapter_wiring_defect`, not adapter absence.
- `capability_ladder(...)`: optional next-rung options for G-CHAIN forced retargeting, including abstract `selected_task_kind`, actionability, authority, local-data, and provider-bound prerequisites.
- `primary_metric(...)`: optional D4 helper exposing one adapter-owned north-star progress value and high-water comparison semantics for G-CHAIN/C4 trigger keying.
- `root_cause_hypotheses(...)`: optional root-cause hypothesis rows with domain-owned slugs and actionability booleans for the generic root-cause ledger.
- `repo_owned_source_roots(...)`: optional repository-owned source glob roots for provenance-based root-cause actionability. When a blocker hypothesis points to a repo-owned source under these roots, `$audit-cycle-loopback` derives `local=true`, `in_scope=true`, and `actionable=true` from provenance and rejects conflicting producer self-report fields. If absent, fail quiet and keep legacy actionability rules.
- `gate_selfcheck(...)`: optional pre-execution gate artifact self-check consumed by `$run-task-code-and-log` failure autopsy. It may report `blocked_pre_exec`, `contradicting_evidence`, `trusted_evidence_source`, `prior_pass_observed`, and `repo_owned_pre_exec_blocker`.
- `partial_progress_axes(...)`: optional warn-only axes for all-or-nothing gate flatlining. Use it to recommend gate decomposition; never let this hook alone promote or block progress.
- `acceptance_reachability(...)`: optional abstract G-REACH input with `acceptance_min_output`, `frozen_envelope`, and optional `reachability_verdict`.
- `metric_validity_self_check(...)`: optional G-OENV input that reports tautological, constant, or self-fulfilling metrics/oracles.

If the adapter is absent or omits a required vector, promotion must fail closed for the affected gate while packet production continues. If the adapter is registered by path or declaration but `adapter_loaded!=true`, set `adapter_wiring_defect=true`, route as `self_inflicted_gate_defect`, and select wiring/load correction instead of creating a new adapter. Do not hardcode project module paths, metric names, lexicon paths, or artifact filenames in the generic workflow skill body.

## Part D In-Place Revision Contract

These rules revise existing decision points. They do not create new detector phases, do not grant new authority, and do not weaken existing no-overclaim gates.

- D1 acceptance-envelope binding: `$normalize-acceptance-and-demo` treats a measurable acceptance target as the target plus adapter-owned `min_envelope_for(target)`. A selected slice below `envelope_floor` is acceptance-incomplete. Downstream derive may expand the envelope, preserve explicit descope with residual scope, or user-escalate; it must not lower the target to fit the smaller slice.
- D2 producer verdict seal: `$run-task-code-and-log` and downstream packets must downgrade producer progress labels to `observed_producer_claim`. Authoritative progress comes only from adapter recomputation, loopback/output-delta, or completion validation. A conflict is `split_brain_progress_claim` warning evidence, not a second truth source.
- D3 root-cause rekeying: distinct-root-cause vetoes and stall streaks use adapter-collapsed root family plus an adapter-owned dominant parameter such as `min_envelope_for(...).deficit_axis` when present. Proximate label churn cannot create a fresh untried root for the same pair. Missing hooks fail quiet to legacy keys.
- D4 C4 trigger rekeying: when `primary_metric(...)` is present, C4 forced-retargeting is triggered by zero high-water movement on that adapter-owned primary metric, not by mutable blocker labels. If C4 finds no actionable forced option, emit exactly one `user_escalation` backstop with the missing input, authority, or evidence kind.

## G1 Disposition Intersection Gate

When multiple active gates provide `allowed_dispositions`, combine them by intersection, not union. The packet must expose:

- `effective_allowed_dispositions`: the intersection of all gates where `hard_stop_required`, `hard_gate`, `requires_goal_productive_next`, `requires_goal_productive_or_user_escalation`, `status=block`, or `constrains_disposition=true`.
- `disposition_intersection_basis`: each contributing gate's allowed set, optional `allowed_task_kinds`, and whether it constrained the result.

Always preserve `terminal_blocked` and `user_escalation` as safety valves. `$derive-improvement-task` must select only from `effective_allowed_dispositions` when the field is present. A disposition allowed by only one gate, such as command-surface `consolidation` when root-axis requires `goal_productive`, is invalid unless it remains in the effective intersection. If a constraining gate allows `goal_productive` only for named task kinds, a task with another `selected_task_kind` is `governance_only` or blocked even when its disposition label says `goal_productive`.

## G0 Pre-Cycle Regression Guard

Before deriving the next task, compare at least the most recent 3 to 5 cycle records when available:

- current artifact family, target command surface, root key, semantic signature, and observed output class
- `provider_request_count`, `env_file_read`, local-model/provider attempt booleans, and terminal/provider status
- primary output fingerprints, semantic counts, and qualitative review caps
- command-surface budget state and same-family micro-hardening streak

If the same artifact family repeats with `provider_request_count=0` and stagnant semantic output for at least 3 recent cycles, block another no-provider micro-hardening task as `goal_productive`. The next selection must be one of:

- a bounded provider or semantic-output transition authorized by authority and GT
- a valid consolidation/refactor task for the over-budget surface
- a supplied-input/domain-delta task that can change the semantic artifact
- `terminal_blocked` or user escalation with the missing input/authority named

## G0-SAT Gate Satisfiability Precheck

Every fail-closed gate must prove that its evidence source can produce the required evidence shape in the current environment before the gate evaluates pass/fail. The run skill or repository adapter may expose:

```text
gate_satisfiability(gate_id, env, **context) -> {
  satisfiable: bool,
  reason: str,
  alternative_evidence_source?: str
}
```

If `satisfiable=true`, evaluate the gate normally. If `satisfiable=false` and `alternative_evidence_source` is present, evaluate the unchanged gate against the alternative source and record the fallback. If `satisfiable=false` and no alternative exists, classify the blocker as `self_inflicted_gate_defect` and route the next task to gate-contract/code correction or user escalation. Do not reclassify this state as an environment/runtime blocker, and do not select another same-gate recheck as progress.

For pre-execution gate artifacts, the run skill may also call:

```text
gate_selfcheck(gate_artifact, gate_id, **context) -> {
  blocked_pre_exec: bool,
  contradicting_evidence: list,
  trusted_evidence_source?: str,
  prior_pass_observed?: bool,
  repo_owned_pre_exec_blocker?: bool
}
```

Classify `self_inflicted_gate_defect` only when repository-owned blocker provenance is confirmed and the same gate artifact contains contradiction evidence, a trusted alternative evidence source, or prior pass evidence. Without repository-owned confirmation, emit warn-only self-check evidence and keep the original failure class.

Keep domain facts, hardware names, command names, thresholds, and evidence-source details in the adapter or task packet. The generic workflow stores only the adapter interface, scalar outcome, classification, and routing rule.

## G2 Qualitative Review Clamp

The qualitative review packet should carry these structured fields when reviewable artifacts exist:

- `semantic_ready`: `true`, `false`, or `unknown`
- `placeholder_event_found`: boolean
- `surface_entity_suspected`: boolean
- `relation_semantics_ready`: `true`, `false`, or `unknown`
- `quality_blocker_codes`: stable short strings
- `progress_cap`: `goal_productive`, `governance_only`, or `terminal_blocked`
- `cap_reason`: concise evidence-backed explanation

If `semantic_ready=false`, `placeholder_event_found=true`, or `surface_entity_suspected=true` affects the primary output, cap `effective_progress_kind` at `governance_only` unless an independent strict output-delta packet proves changed and semantic primary-output progress. A quality cap is direction evidence, not human approval and not final validation.

## G3 Strict Output Delta

Do not treat non-empty rows, scalar counts, lineage records, gap reports, or workflow metadata as domain progress by themselves. `produced_domain_delta=true` requires both:

- `changed_vs_previous=true`: stable fingerprints for repository-declared primary output paths differ from the accepted previous baseline.
- `semantic_progress=true`: the changed content includes meaningful domain semantics, such as named events, named characters/entities, causal/temporal/story-order evidence, supported relation candidates, or reviewed source-backed assertions.

Metadata-only outputs remain `effective_progress_kind: governance_only` unless the active task's acceptance criteria are explicitly metadata/governance work and the same family is not already repeating. Output-delta packets should include `previous_output_fingerprint`, `current_output_fingerprint`, `changed_vs_previous`, `semantic_progress`, `semantic_delta_summary`, `metadata_only`, and evidence paths.

If strict runner validation and output-delta disagree on the same evidence class, prefer the conservative output-delta value. A runner `semantic_progress=true` with output-delta `semantic_progress=false` must produce a block-level `validator_disagreement` finding, set `authoritative_semantic_progress=false`, and prevent runner pass from being used as completion or goal-productive evidence.

Producer progress labels captured from artifacts or run logs are not output-delta truth. Store them as `observed_producer_claim` and compare them only as warning evidence; if they conflict with adapter or strict output-delta evidence, emit `split_brain_progress_claim` and use the conservative recomputed value.

## R-GCOV Coverage Gate Reconciliation

When both output-delta and loopback emit `coverage_quality_delta_gate`, compare them as one logical G-COV. The packet should expose `coverage_quality_delta_reconciliation_gate` with compact local/external gates, `validator_disagreement`, `gcov_metric_name_collision`, metric value conflicts, and `status`.

If the two G-COV values disagree, or the same metric key has conflicting values, treat `status=block` as a conservative hard stop. Do not promote measurement, oracle, or capability-ladder progress from whichever G-COV is favorable. The next task must resolve the disagreement, produce strict changed-and-semantic primary-output evidence, or terminal/user-escalate with the missing evidence.

## G-INTEGRITY Validator Integrity And Coverage

Validator/oracle packets must fail closed when their own structure is contradictory or incomplete:

- A top-level validator success must equal the AND of embedded checks, sub-results, assertions, validator rows, or equivalent child results.
- A validator that declares a target population must inspect the full declared population. If `inspected_count`, `checked_count`, `validated_count`, or equivalent is below `population_count`, `target_count`, `expected_count`, or equivalent, surface `validator_coverage: under_detection`.

Packets should expose `validator_integrity_gate` with `validator_integrity`, `validator_coverage`, `status`, `hard_stop_required`, `allowed_dispositions`, and compact findings. If this gate blocks, do not cite the validator pass as goal-productive evidence. Derive may still choose correction/implementation work that fixes the primary output or the validator, but another validator-only task is not progress.

## G-COV Coverage/Quality Delta Gate

When output-delta or loopback evidence includes a high-water mark, require at least one real adapter-supplied coverage or quality axis to improve before measurement work can be promoted. Example axes include:

- `event_named_ratio`
- `proper_noun_character_ratio`
- `coreference_resolved_ratio`
- `causal_edge_count` or `causal_or_temporal_edge_count`
- `windows_covered` or an equivalent source-window count

The packet must expose `coverage_quality_delta_gate` with previous/current vectors, `improved_fields`, `quality_delta_pass`, and `status`. If `quality_delta_pass=false`, new validators, oracles, ladder checks, metrics, dashboards, lineage, gap reports, or scalar contracts remain `governance_only` unless independent strict output-delta evidence proves changed semantic primary output. Do not add new domain-specific metric names to this generic skill; put them behind the adapter.

## G-SUBSTANCE Output Substance Gate

Before a measurement/oracle transition or capability-ladder rung movement can support `goal_productive`, require adapter-supplied substance metrics to improve on at least one axis. The packet must expose `substance_delta_gate` with previous/current substance vectors, `improved_axes`, `substance_delta_pass`, `status`, and fail-closed metadata.

If `substance_delta_pass=false` or `status=missing`, validator/oracle existence, metric availability, or non-empty report rows cannot open the next rung by themselves. The next task must create real primary-output substance, choose correction/implementation work, or terminal/user-escalate with the missing adapter/output evidence. Independent strict output-delta evidence with `changed_vs_previous=true` and `semantic_progress=true` may still prove progress.

## G-VACUOUS Vacuous Corrective Gate

Corrective, repair, backfill, or reconciliation lanes must be counted by resolved items, not attempted rows. The packet must expose `vacuous_corrective_gate` with lane `attempted/resolved` counts, `surface_corrective_noop`, `excluded_delta_lanes`, and `status`.

If any lane has `attempted>0` and `resolved==0`, set `surface_corrective_noop=true`. Exclude those lanes from produced/semantic delta claims and do not let the task count as `goal_productive` unless independent strict changed-and-semantic primary-output evidence exists.

## G-MEAS-CAP Measurement Exception Cap

Measurement progress is capped to one transition per suffix-normalized `root_key`, and only when G-COV and G-SUBSTANCE pass. The packet must expose `measurement_progress`, `measurement_progress_allowed`, `measurement_progress_streak_for_root_key`, `measurement_streak_cap`, `measurement_check_ids`, `measurement_frontiers_observed`, and `measurement_progress_basis`.

Do not re-add `goal_productive` to `effective_allowed_dispositions` merely because a new check ID, oracle, metric, or capability-ladder observation appeared. Treat measurement as a `goal_productive` basis only when `measurement_progress_allowed=true`, `coverage_quality_delta_gate.quality_delta_pass=true`, and `substance_delta_gate.substance_delta_pass=true`. Otherwise set `measurement_goal_productive_allowed=false` and choose real implementation/output progress, `terminal_blocked`, or `user_escalation`.

## G-FACET Root-Family Measurement Cap

Normalize blocker and measurement families by removing version/date/run-directory suffixes and facet labels. When the domain adapter supplies `facet_root_map`, collapse facet labels through that map before applying family-level caps. Use `root_family_key` or `blocker_root_family`; do not let equivalent facet renames reset the measurement exception counter.

When `facet_root_map` is absent, empty, or fails, do not fall back to raw proximate blocker text as the family key. Emit `facet_root_map_missing=true` and group by a stable terminal-outcome family such as `artifact_family + terminal_outcome_key`; use that value as `family_key` and `root_family_key`, and preserve the previous artifact/signature key as `legacy_family_key`. The packet should expose `terminal_outcome_key`, `terminal_outcome_family_key`, `terminal_outcome_family_fallback_applied`, and `terminal_outcome_family_previous_count`. This fallback is intentionally conservative: if the terminal outcome is unchanged, blocker-label mutation cannot reset the same-family cap.

Packets should expose `measurement_progress_streak_for_root_family` alongside `measurement_progress_streak_for_root_key`. `measurement_progress_allowed=true` is valid only when both the root-key and root-family streaks are within cap and G-COV/G-SUBSTANCE passed.

Treat `blocker_mutation_kind=facet_rename` as lateral churn. Treat `blocker_mutation_kind=forward_mutation` only when the normalized root family actually changes or a recorded capability ladder transition is not merely a facet rename. If the terminal outcome remains unchanged, set `forward_mutation_vacuous=true` and keep the hard stop.

## G-ADAPTER Adapter-Mandate Gate

When `facet_root_map_missing=true`, `substance_delta_gate.status=missing`, or `quality_vector` is missing for the same `artifact_family` across the configured adapter cap, default `3`, and quality/substance high-water has not improved during that span, emit:

- `adapter_mandate_required: true`
- `adapter_missing_streak`
- `adapter_contract_unmet`, using only abstract contract names such as `facet_root_map`, `substance_metrics`, and `quality_vector`
- `adapter_mandate_gate.allowed_dispositions: [goal_productive, terminal_blocked, user_escalation]`

The next goal-productive task must register or strengthen the repository domain adapter. Do not count another domain-specific micro-repair as goal-productive until the adapter supplies the missing collapse/substance/quality contract or the cycle terminal/user-escalates with the exact adapter blocker.

If the repository has registered an adapter but the loopback packet reports `adapter_loaded!=true`, emit `adapter_wiring_defect=true` and `recommended_disposition=self_inflicted_gate_defect`. That state is local, in-scope, and actionable because the workflow failed to inject or load its own registered adapter. The next goal-productive task kind is `adapter_wiring_fix` or `adapter_load_fix`; do not misroute it as `adapter_mandate_required` or a new-adapter task.

If G-ADAPTER fires, it precedes G-CHAIN. This prevents adapter absence from being mistaken for a domain terminal state when the real missing prerequisite is the workflow's own adapter contract.

## G-CHAIN Cumulative Goal-Distance Gate

Track cumulative high-water movement by `root_family_key` after adapter facet collapse. If the adapter is absent, track by `artifact_family` instead of proximate blocker label or terminal outcome. This gate is independent of `blocker_signature`, terminal-outcome wording, version suffixes, and renamed hypotheses.

When the same scope has no G-COV or G-SUBSTANCE high-water improvement for the configured chain cap, default `3`, emit:

- `cumulative_goal_distance_stalled: true`
- `cumulative_goal_distance_stall_streak`
- `cumulative_goal_distance_scope_key`
- `high_water_vector`
- `high_water_last_improved_cycle`

If untried hypotheses remain in the same stalled scope, also emit `cumulative_untried_chain_without_quality_delta=true` and `untried_veto_overridden_by_chain_stall=true`. `$derive-improvement-task` must then ignore the usual untried-root-cause terminal veto. When the stall streak reaches the forced-retarget threshold and lateral churn continues, the packet must enumerate `forced_selected_task_options` before terminal/user escalation:

- self-inflicted gate defects such as `adapter_wiring_fix`;
- the first actionable adapter `capability_ladder` rung whose authority, local-data, and provider-bound prerequisites are satisfied.

If an option exists, expose it as `forced_selected_task` and allow `goal_productive` only for its `selected_task_kind`. If no option exists or the adapter omits the ladder hook, keep `terminal_blocked` or `user_escalation` under the existing fail-quiet rule.

Use this gate for the "distinct but non-converging hypothesis chain" case: each repair can be locally valid and still fail to reduce goal distance. Do not delete or weaken A2b; G-CHAIN adds a separate cumulative no-progress axis.

When the adapter exposes `primary_metric(...)`, key the C4 forced-retarget trigger to primary-metric high-water movement. If the primary metric has zero high-water movement for the configured cap, renamed labels, facets, or version suffixes cannot reset the trigger. If no forced option is actionable, emit one user-escalation backstop with the missing input, authority, or evidence kind; do not schedule another same-family retry solely to recheck the condition.

## G-REACH Acceptance Reachability Gate

Before derive promotes another repair inside a frozen envelope, compare the task acceptance lower bound with the frozen execution/resource/input envelope when the adapter or caller exposes abstract comparable values. The packet should carry:

- `acceptance_min_output`
- `frozen_envelope`
- `reachability_verdict: reachable|unreachable|indeterminate`
- `acceptance_unreachable_under_frozen_config`
- `relaxation_or_escalation_required`

If `reachability_verdict=unreachable`, another envelope-internal micro-repair is not goal-productive. Derive must choose a constraint-relaxation task when authority permits it, or `user_escalation` when relaxation needs user approval. If the values are absent or not comparable, use `indeterminate` and do not block solely from G-REACH.

When an `acceptance_envelope_contract` exists, treat `envelope_below_floor=true` as the same acceptance-incomplete condition before derive selects a task slice. This is not a new gate; it is the normalized acceptance contract saying the selected envelope cannot satisfy the target.

## G-OENV Oracle/Metric Validity Gate

When the adapter exposes `metric_validity_self_check(...)`, check whether a metric/oracle can pass tautologically, by constant output, or by echoing an input/order it is supposed to evaluate. The packet should expose `oracle_metric_validity_gate` with `metric_validity`, `metric_validity_states`, `metric_validity_self_check_provided`, and `metric_goal_productive_excluded`.

If `metric_goal_productive_excluded=true`, do not use that oracle/metric pass to justify measurement progress, capability-ladder promotion, or completion. The next task must correct the metric/oracle definition or provide independent strict changed-and-semantic output-delta evidence. If the adapter omits the self-check, warn only.

## G-ADVICE-FRESH Advice Freshness Gate

Advice is non-GT steering evidence. When active/root advice declares headline output fingerprints or metric snapshots, compare those claims to the current adapter/output fingerprint. The packet should expose `advice_freshness_gate` with `current_output_fingerprint`, declared fingerprint claims, stale advice paths, and `advice_metrics_stale`.

If `advice_metrics_stale=true`, warn and require refresh, defer, or reject rationale before relying on the advice's headline metrics for derive. This does not change phase order and does not promote advice to goal truth.

Gate-result regression is absorbed here rather than added as a separate hard gate. When a supplied gate packet shows `passed -> blocked` under a stable environment fingerprint, expose `gate_result_regression_stale=true` and warn. Route the next task through current evidence review, `gate_selfcheck`, or provenance-hardened root-cause repair before relying on stale headline gate state.

## G-BALANCE Detection/Correction Balance

Classify each cycle task as:

- `detection`: validator, oracle, metric, gate, contract, dashboard, lineage, gap report, coverage report, or other instrumentation added without primary-output semantic progress.
- `correction`: producer, prompt, transform, resolver, extraction, generation, provider dispatch, or other implementation work that can change primary output.
- `mixed`: both detection and correction are present.

If `detection_only` repeats for the same `blocker_root_family` at or above the cap, default `2`, and primary-output semantic progress remains false, expose `detection_balance_gate` or `requires_correction_or_terminal=true`. The next task must be correction/implementation work, `terminal_blocked`, or `user_escalation`. Another detection-only task cannot satisfy a goal-productive hard gate.

## G-DISPATCH Provider/Scale Duty Gate

When `ever_provider_dispatch=false`, provider request count is zero, and the coverage/quality high-water vector remains all-zero, do not select another surface-only, runner-surface, contract, preflight, locator, or accounting task as `goal_productive`. The packet should expose `provider_scale_dispatch_gate` with `dispatch_required`, `provider_request_count`, `high_water_all_zero`, `allowed_dispositions`, and `status`.

If current authority permits bounded dispatch or provider-free scale execution, derive must select real extraction/scale work such as full-window, multi-window, or multi-work execution. If authority, source input, or provider state blocks that work, derive must write `terminal_blocked` or user escalation naming the missing condition. A self-imposed missing runner surface is not a valid terminal blocker when an in-place Class B implementation can create the surface.

## G4 Behavior-Based GT Conflict Detection

Detect task-vs-GT conflict from behavior booleans, not only task text. Include scalar booleans and counts such as:

- `provider_request_count`
- `env_file_read`
- `local_model_loaded`
- `package_install_attempted`
- `raw_body_persisted`
- `bounded_retry_evidence`
- `legitimate_terminal`

If GT or authority allows or requires a provider/env path but the task/run avoids it with `provider_request_count=0`, `env_file_read=false`, and no legitimate terminal or authority blocker, derive must resolve the contradiction, select an authorized bounded attempt, or terminal/user-escalate. A wording change that still forbids required behavior does not satisfy the gate.

If goal truth or the active task requires corpus/generalization progress and behavior evidence shows `single_work_id:true`, `selected_work_count=1`, or a single-work-only streak for at least the local threshold, report `status:block` with reason `single_work_id_invariant_blocks_generalization`. The next task must implement bounded multi-work execution with `single_work_id` separation or terminal/user-escalate on the exact missing source/authority/provider condition.

## G5 Command-Surface Hard Stop

When `command_surface_budget.budget_exceeded=true` and `hard_gate=true`, do not allow another task on the same over-budget surface merely because it is labeled `goal_productive`. Classify the proposed command-surface change:

- Class A, blocked while over budget: new `cmd_*`, versioned `vNNN` wrapper, preflight, gate, locator, handoff, family rename, or alternate runner route.
- Class B, allowed and preferred when it directly creates primary-output progress: in-place modification of the single canonical extraction entrypoint with non-increasing command count.
- Class C, allowed consolidation: command count reduction, family retirement/freezing, or module extraction that reduces the over-budget surface.

Allowed dispositions before intersection are:

- consolidation/refactor candidate selected or registered
- `terminal_blocked`
- user escalation

Allow a goal-productive disposition only for strict changed-and-semantic primary-output evidence or a Class B in-place task that directly creates the missing primary-output transition and records why pure consolidation would not reduce the blocker. The derive result must cite the evidence path.

## S-STRUCT Structure Signal

When the domain adapter supplies `structure_metrics(...)`, expose `structure_metrics_gate` with numeric structure metrics, `structure_consolidation_recommended`, optional `structure_high_water_moved`, `improved_structure_axes`, and `refactor_effect_required`. Semantic structure metrics may include mechanical shard count, version-suffix file count, global-rebinding or hidden-coupling signal count, duplicate public definition count, tree depth, directory fan-out, reuse ratio, and max file LOC. Treat the adapter hook as the single truth source for structure progress; producer-local structure reports are advisory until absorbed into this hook. Treat the signal as warn-level unless another gate makes command-surface pressure hard. Use it to justify Class C consolidation, `semantic_consolidation`, `reuse_extraction`, `coupling_reduction`, or module-boundary work when that work reduces the reported structure burden.

For behavior-preserving refactor tasks whose objective is structural reduction, downstream validation must require real structure high-water movement. New modules, relocated helpers, additional files, token/pattern avoidance, or green tests are not enough when the adapter reports `refactor_effect_required=true` and `structure_high_water_moved=false`. Define coupling axes by durable dependency/reference counts or equivalent movement-resistant metrics, not only by absence of forbidden token strings.

If the adapter omits structure metrics, do nothing beyond warn-only generic code-structure audit findings. Do not hardcode project-specific module paths, metric names, kernel/reuse roots, dependency DAGs, or thresholds into this generic workflow reference.

## G5b Consolidation Streak Cap

Consolidation is governance-only unless it independently produces accepted primary-output progress. Track `consolidation_streak` over recent progress items. When `consolidation_streak >= consolidation_streak_cap` (default 2), remove `consolidation` from `effective_allowed_dispositions` and require `goal_productive`, `terminal_blocked`, or `user_escalation`.

## G6 Same-Family Micro-Hardening Limit

If the last 3 selected tasks in the same artifact family are micro-hardening changes such as `add_field`, `lineage`, `gap_report`, `relation_label_tweak`, `contract_scalar`, `preflight_scalar`, or renamed command variants, block the next same-family micro-hardening task as `goal_productive`.

The next task must be one of:

- provider or semantic-output transition
- valid consolidation/refactor of the repeated surface
- supplied-input or source-backed domain-delta task
- terminal/user escalation with evidence that no authorized productive alternative remains

## G7 Loopback Progress Packet

Run `$audit-cycle-loopback` after qualitative review and before derivation whenever raw run artifacts, output-delta evidence, or repeated-family loop evidence exists. The packet is workflow evidence only and must not be treated as goal truth, validation proof, human review, issue-closure evidence, or readiness/gold promotion evidence.

The producer must compute `anti_loop_progress_gate` from raw artifact content and the append-only family progress registry, not from self-declared `progress=advanced`, non-empty counts, renamed command families, or `produced_domain_delta` alone. Required packet fields include:

- `family_key`, `artifact_family`, and `semantic_signature`
- `changed_vs_previous` and `semantic_progress`
- `same_family_micro_hardening_count`
- `provider_request_count` and other safe provider/env behavior scalars when available
- `quality_vector`, including confidence and domain-context fields when the adapter supplies them
- `previous_accepted_baseline`, `coverage_quality_delta_reconciliation_gate`, `substance_delta_gate`, `vacuous_corrective_gate`, `facet_root_map_applied`, `advice_freshness_gate`, and `structure_metrics_gate`
- `repo_owned_source_roots_status`, `partial_progress_axes_gate`, and provenance-hardened root-cause actionability fields when supplied by the adapter
- `terminal_outcome_changed`, `observed_delta_class`, `forward_mutation_vacuous`, `root_cause_ledger_path`, `root_cause_unverified_hypotheses`, `root_cause_duplicate_hypotheses`, `untried_actionable_root_cause_exists`, `untried_root_cause_hypotheses`, `untried_promotion_budget`, `vacuous_untried_streak`, and `hypothesis_exhausted` when applicable
- `adapter_mandate_required`, `adapter_missing_streak`, `adapter_contract_unmet`, `adapter_loaded`, `adapter_wiring_defect`, `cumulative_goal_distance_stalled`, `cumulative_goal_distance_stall_streak`, `forced_selected_task_options`, `untried_veto_overridden_by_chain_stall`, `acceptance_unreachable_under_frozen_config`, `relaxation_or_escalation_required`, and `oracle_metric_validity_gate` when applicable
- `recommended_disposition`, `hard_stop_required`, `evidence_class`, and evidence paths

The repository adapter or shared module must fail closed on noisy quality inputs. If confidence is low, artifacts are missing/malformed, adapter output is missing, or domain interpretation is uncertain, emit `evidence_class: insufficient_evidence`, `recommended_disposition: conservative_hold`, and `hard_stop_required: true`. Legacy repository quality modules may remain as compatibility fallbacks, but new domain-specific metrics, paths, lexicons, and thresholds belong behind the adapter interface.

Use the packet as a derive gate:

- `semantic_progress=true` may reset the same-family streak, subject to ordinary validation and no-overclaim constraints.
- `semantic_progress=false` with `same_family_micro_hardening_count >= 3` blocks another same-family micro-hardening task as `goal_productive`.
- `evidence_class=insufficient_evidence` blocks `goal_productive` unless the next task supplies the missing raw artifacts, runs a bounded provider/semantic transition, or records terminal/user escalation with evidence.
- `effective_allowed_dispositions` bounds the next selected disposition. Do not choose a disposition by taking a union of individual gates.
- `disposition_intersection_basis.allowed_task_kinds` binds `goal_productive` to those task kinds. A label-only `goal_productive` task with another kind is not valid progress.
- `substance_delta_gate.substance_delta_pass=false` blocks measurement promotion unless strict changed-and-semantic primary-output evidence exists.
- `blocker_mutation_kind=forward_mutation` blocks rung promotion unless `terminal_outcome_changed=true`; set `forward_mutation_vacuous=true` when the ladder moved but observed domain output did not.
- `adapter_mandate_required=true` forces adapter registration/strengthening before another domain repair can count as `goal_productive`.
- `adapter_wiring_defect=true` forces adapter wiring/load correction as `self_inflicted_gate_defect`; it is not adapter absence.
- `cumulative_goal_distance_stalled=true` restricts the next disposition to `terminal_blocked` or `user_escalation` unless G-ADAPTER is active or `chain_stall_forced_retarget_gate` exposes an actionable forced task kind.
- `untried_actionable_root_cause_exists=true` invalidates terminal blocking and forces derive to select the untried root-cause repair only when `hypothesis_exhausted=false`, `untried_veto_overridden_by_chain_stall=false`, and the hypothesis is actionability-verified.
- `repo_owned_source_roots_status=provided` means repository-owned provenance can override conflicting producer self-report fields for root-cause `local`, `in_scope`, and `actionable`. Do not trust self-reported `local=false`, `in_scope=false`, or `actionable=false` for that hypothesis.
- `acceptance_unreachable_under_frozen_config=true` forces constraint relaxation or `user_escalation`.
- `oracle_metric_validity_gate.metric_goal_productive_excluded=true` blocks tautological metric/oracle passes from supporting progress.
- `root_cause_unverified_hypotheses` and `root_cause_duplicate_hypotheses` never override terminal/quiescence. Self-asserted actionability without structural fields or provenance is not enough, and rename/version suffix equivalents are not fresh hypotheses.
- `hypothesis_exhausted=true` means the same family has spent the untried repair budget on vacuous attempts; derive must terminal-block or user-escalate unless a supplied input delta changes the family.
- `vacuous_corrective_gate.surface_corrective_noop=true` blocks counting unresolved corrective rows as output delta.
- `partial_progress_axes_gate.status=warn` is advisory only: it recommends decomposing all-or-nothing gates when partial axes exist but high-water remains flat. It must not add a new blocker.
- `structure_metrics_gate.refactor_effect_required=true` with `structure_high_water_moved=false` means a refactor may be useful but cannot be completed as structural goal progress without residual work or explicit descope. File-count growth, mechanical splitting, token avoidance, or producer self-reports must not be treated as an improved structure axis.

## A1 Measurement Progress Exemption

When a cycle introduces a new validator, oracle, metric, or first-observed capability frontier, `anti_loop_progress_gate.measurement_progress=true` records workflow instrumentation only. It does not by itself count as goal-productive progress.

The packet must expose `measurement_progress_allowed`, `measurement_streak`, `measurement_progress_streak_for_root_key`, `measurement_streak_cap`, `measurement_check_ids`, `measurement_frontiers_observed`, and `measurement_progress_basis`. If `measurement_progress_allowed=true`, derive may treat a bounded measurement-linked transition as progress only because G-COV and G-SUBSTANCE also passed. If the root-key/root-family streak exceeds the cap, or if G-COV/G-SUBSTANCE fails, the next task must be real implementation/output progress, terminal-blocked, or user-escalated.

Known oracle/check reruns are not new measurement progress. Do not use this exemption for repeated accounting, dashboard, or metadata-only cycles that do not introduce a new check ID or first-observed frontier.

## A2 Blocker Forward-Mutation Ledger

Use `blocker_signature` and `blocker_ladder_rung` to distinguish same-family repetition from capability-ladder movement. `blocker_mutation_kind` values are:

- `repeat`: same blocker signature and no forward rung movement; preserve hard-stop behavior.
- `facet_rename` or `lateral`: changed label/facet without normalized root-family movement; require independent output/input evidence before counting progress.
- `forward_mutation`: normalized root family changed or a recorded capability ladder transition is not merely a facet rename. Treat it as changed blocker-state progress only when strict observed output-delta evidence sets `terminal_outcome_changed=true`; otherwise set `forward_mutation_vacuous=true` and do not reset the family loop counter.

Track `forward_mutation_budget_remaining`. When it reaches zero, set `force_implementation_cycle=true`: the next task must implement the next rung in place, terminal-block with a concrete authority/data blocker, or user-escalate. Do not keep climbing the ladder through governance or measurement-only cycles.

## A2b Root-Cause Hypothesis Ledger

`$audit-cycle-loopback` may append `.task/anti_loop/root_cause_ledger.jsonl` rows keyed by `family_key`, `root_key`, and `hypothesized_root_cause`. The hypothesis slug is domain-owned; the generic workflow evaluates whether it was attempted, whether terminal outcome changed, whether it is actionability-verified, and whether it is distinct from attempted hypotheses by normalized `(hypothesized_root_cause, target_surface, observed_delta_class)`.

When the adapter supplies a collapsed root plus `root_dominant_parameter_key`, distinctness is evaluated on that pair before proximate labels. Renaming prompt/schema/event-edge labels, version suffixes, or target-surface wording does not create a fresh untried hypothesis for the same collapsed root and dominant parameter.

Before terminal blocking or sealing, `$derive-improvement-task` must check the loopback packet or ledger summary. If `untried_actionable_root_cause_exists=true`, `hypothesis_exhausted=false`, and `untried_veto_overridden_by_chain_stall=false`, terminal blocking is invalid. Promote that hypothesis as the next `goal_productive` repair task unless authority, safety, or external state makes it non-actionable and records that rationale. If `hypothesis_exhausted=true` or `untried_veto_overridden_by_chain_stall=true`, do not promote another same-family untried repair without supplied input delta; terminal-block or user-escalate.

## A3 Terminal-Blocked Exit Guard

Before derive writes `terminal_blocked`, check the next unsatisfied capability-ladder rung against authority and local evidence:

- If the next rung uses only local data, needs no new permission, uses provider dependency `none` or `bounded`, stays inside `.agent_goal` scope, and can be implemented through an allowed command-surface class, terminal blocking is not allowed.
- Promote that rung as a `goal_productive` task-pack item or standalone implementation task instead.
- Allow terminal blocking only when no authorized local/bounded rung remains, required input or authority is missing, or safety/GT forbids the implementation path.

## A3b Terminal Quiescence Gate

When loop detection reports `terminal_quiescence_gate.quiescence_required=true`, the orchestrator must not automatically start another domain cycle for the same `root_key`. Record one user-handoff note and skip closeout/dashboard/report/recheck reproduction with `commit_skipped_reason: terminal_quiescence`.

This gate applies only when `has_supplied_input_delta=false` and the same root has reached terminal state at least `terminal_quiescence_threshold` consecutive times, default `2`. Count `untried_root_cause_repair_required` records with no terminal outcome change as same-root no-progress records for the streak. Use `quiescence_untried_reconcile` as the single source of truth for priority: a verified, unexhausted untried hypothesis may override quiescence; exhausted or unverified hypotheses may not.

## A3c Terminal Escalation Gate

When loop detection reports `terminal_escalation_gate.escalation_required=true`, the workflow must promote repeated terminal recheck into `user_escalation`. This gate applies when the same root family has `terminal_blocked`, terminal handoff, or recheck records for at least `terminal_escalation_threshold` consecutive cycles, default `2`, and `has_supplied_input_delta=false`.

The packet must expose `terminal_recheck_streak`, `root_family`, `forced_disposition: user_escalation`, `seal_required: true`, `seal_family_path`, and exactly one `missing_input` object. The missing input kind must be one of `new_input_kind`, `authority_change`, `external_state_change`, or `gate_contract_fix_approval`.

`terminal_blocked` recheck is not progress for this gate. `$derive-improvement-task` must seal the family and emit `selected_task_source: user_escalation` unless a verified unexhausted root-cause repair, supplied input delta, authority change, or external-state change reopens the family.

## A4 Advice-Intake Coherence Gate

At context and loopback stages, check root steering docs such as `task_advice.md`, `skill_advice.md`, and `task_doctor_steering.md`. If a root steering doc is not represented in `.agent_advice/active`, emit a warn-level `orphan_advice_not_intaken` finding and recommend `$manage-external-advice intake`.

This warning does not change the canonical phase order and does not make advice goal truth. It prevents derive from silently ignoring a direction document that has not entered the active non-GT advice channel.

## A5 Command-Surface Carve-Out

When `force_implementation_cycle=true`, command-surface budget pressure must still allow:

- Class B: in-place extension of the canonical entrypoint with non-increasing command count.
- Class C: surface reduction, retirement, or consolidation.

Class A remains blocked while over budget: new `cmd_*`, new versioned wrappers, alternate runners, handoff commands, locators, or family renames. Reinclude `goal_productive` only for Class B implementation work that directly advances the missing primary-output transition, or for Class C when it is the required consolidation path.

## Capability Ladder Router

When `goal_productive` is required and no concrete candidate exists, derive the next task from the next unsatisfied capability in the quality vector:

1. `M0_single_work_full_window`: one work has full-window coverage with source-backed primary output.
2. `M1_same_work_reconstruction_measured`: the same work has measured event reconstruction quality.
3. `M2_three_work`: three distinct works run with `single_work_id` separation preserved and no collapsed cross-work graph.
4. `M3_unseen_10`: ten unseen works run or are terminal-blocked with precise source/authority/provider evidence.
5. `M4_unseen_15`: fifteen unseen works run or are terminal-blocked with precise source/authority/provider evidence.

Promote the first unsatisfied rung as a goal-productive task-pack item only when it can be implemented through an allowed command-surface class and current authority permits the needed provider/runtime behavior. A rung passes by G-COV quality/coverage delta or strict changed-and-semantic output-delta evidence, not by oracle existence alone.

When G-CHAIN reaches the forced-retarget threshold, this ladder is not optional planning context. The loopback packet must expose the first actionable rung as `forced_selected_task` when authority, local data, and bounded/provider prerequisites allow it. `$derive-improvement-task` may terminal/user-escalate only after recording that no ladder rung or self-inflicted gate correction is actionable.

## No-Overclaim Boundaries

These gates must not close implementation issues, promote gold/readiness/rights/ZKP claims, or infer user/human review. They only decide whether the cycle can count as goal-productive progress and which next-task family is allowed.
