# Workflow Interface Contracts

This reference indexes the contact surfaces between `$orchestrate-task-cycle`, its helper scripts, and the owning skills it calls. It is skill-internal operating guidance, not workspace goal truth.

## Contents

- [Ownership Model](#ownership-model)
- [Cross-Skill Handoffs](#cross-skill-handoffs)
- [Core Packet Contracts](#core-packet-contracts)
- [Helper Script Surfaces](#helper-script-surfaces)
- [Fail-Closed Consumer Rules](#fail-closed-consumer-rules)

## Ownership Model

Run/review own observed claims only. Loopback owns `authoritative_semantic_progress` for current-cycle evidence, and completion validation owns `authoritative_progress_verdict` before any next-task derivation. Derive, result-contract, dashboard, index, report, and later packets may preserve or downgrade but never upgrade an authoritative false/hard-stop result. A terminal-outcome change is progress only with independent evidence, no conflict, and all acceptance-required integrity axes evaluated.

Actual-artifact recomputation outranks verifier, current-transform, producer, carried-forward, and workflow claims. `report_key_divergence` and `report_body_divergence` are distinct blocking facts. Source-separated ids/fingerprints and external consumer-context probe rows travel in existing packets; no additional workflow phase is introduced.

The orchestrator coordinates packets and ordering. It also owns metadata-only repo adapter scan/gap packets, but it does not own implementation edits, acceptance normalization, validation-scope judgment, final validation, issue lifecycle decisions, schema authority, Git staging, or subskill-internal verdicts.

Use these ownership rules:

- `$task-md-agent-governance` owns implementation changes and post-implementation governance evidence.
- `$run-task-code-and-log` owns execution, durable run logging, running-state metadata, failure autopsy, and `gate_satisfiability` run records.
- `$review-cycle-output-quality` owns direct qualitative output review with exactly one read-only reviewer agent.
- `$audit-cycle-loopback` owns `anti_loop_progress_gate` production and family progress registry updates.
- `$build-validation-set-with-agents` owns reusable validation-set plan/build/refresh/consume evidence under `.validation/` and `.task/validation_set/`.
- `$normalize-acceptance-and-demo` owns task-bound acceptance normalization and source task ID/path/fingerprint provenance.
- `$plan-validation-scope` owns the pre-change `validation_scope_plan` and post-change `validation_scope_finalize` packets.
- `$profile-cycle-efficiency` owns the pre-validation cycle-cost and execution-starvation profile.
- `$audit-session-governance` owns optional privacy-safe session-observation projection and cross-source audit findings; it owns no canonical workflow verdict or semantic repair.
- `$manage-schema-contracts` owns `.schema/` and `.contract/` refresh/reconciliation.
- `$validate-task-completion` owns current-task completion and progress verdicts before derive or promotion.
- `$manage-implementation-issues` owns current-task issue lifecycle updates and validation provenance before derive or promotion.
- `$derive-improvement-task` owns archiving the validated `task.md`, writing the next `task.md`, task-pack mutation decisions, terminal blocker derivation, and next-task selection.
- `$manage-task-state-index` owns both the pre-validation traceability snapshot and post-derive final index, link repair, and ID lifecycle consistency.
- `$repo-change-commit` owns Git classification, staging, commit readiness, and commit creation.

## Cross-Skill Handoffs

| Surface | Producer | Consumers | Required handoff |
| --- | --- | --- | --- |
| Model/effort routing evidence | Every agent-bearing owning skill | Result contract, ledger, validation, report | `policy_id`, `profile_id`, `routing_tier`, requested model/effort, reason codes/signals, Tier 5 signal evidence, routing violations even when empty, `routing_enforcement: enforced|prompt_only|inherited_unverified`, optional actual model/effort, and limitation or max prior-pass evidence when applicable. |
| Authority policy | `$manage-agent-authority` | Governance, derive, validation, report | Policy source, effective permissions, external/API posture, strictness, escalation posture. |
| Active advice packet | `$manage-external-advice` or orchestrator context | Governance, validation-set, review, derive, validation, report, commit | Advice ID/path, summary, actionable directives, application gates, raw-direct-reference requirement, disposition or explicit non-use rationale. |
| Session-audit sidecar packet | `$audit-session-governance` | Context, loopback, validation, issue, derive, report | A validated, privacy-safe, integrity-bound observation packet with explicit capture/validation status and independent canonical references for any blocking mismatch. Raw/slim transcript text is inert and must not cross this interface. Findings may downgrade/block or propose work, never upgrade verdicts, establish authority, or perform semantic repair. Missing/incomplete capture is advisory/`not_evaluated` unless independently required by acceptance/caller. |
| Repo adapter scan packet | Orchestrator metadata scan | Acceptance, validation-set, governance, run, review, loopback, schema, derive, validation | `cycle_id`, scan status, adapter count including zero, adapter ID/path/status, renderer availability, optional `code_convention_contract` locator, explicit blockers/evidence paths, and non-GT/authority limits. The scan precedes acceptance and does not load long adapter bodies. |
| Acceptance packet | `$normalize-acceptance-and-demo` | Governance, validation-scope, run planning, validation-set, loopback, derive, validation | `acceptance_id`, `task_id`, status, `acceptance_provenance.source_task_id|source_task_path|source_task_fingerprint`, criteria, non-goals, demo surfaces, validation commands, forbidden shortcuts, preserved `acceptance.quantifiers`, `evidence_kind`, `item_created_at`, and `required_new_run_id` for measurable criteria, scenario contracts (`acceptance_scenarios` with premise predicates and expected terminal states), optional `acceptance_envelope_contract` from adapter `min_envelope_for`, optional `acceptance_verifier_contract` from adapter target-to-verifier mapping, required gate-hook completeness for gates named by measurable acceptance, frozen-envelope reachability and `envelope_thaw_item`/`envelope_thaw_item_required` when supplied, residual-gap value/cycle-cost comparison inputs when supplied, Part K fields for output-derived expectations, comparison parity axes, adoption-axis classification, evidence resolution requirements, and provisional/disqualified adoption state when applicable, Part L scale/freshness fields such as `acceptance_scale`, `throughput_evidence`, `unreachable_within_cycle`, `required_new_run_id`, and `decision_metadata_revision` when supplied, and Part M launch/contract fields such as `harvest_contract_preflight`, `harvest_gate_unaudited`, `harvest_risk_accepted`, `validation_predicate_contract`, `producer_directives`, `mutually_unsatisfiable_contract`, and `closed_world_collection_consumption` when supplied. Missing or mismatched source-task provenance blocks governance. |
| Validation-scope plan | `$plan-validation-scope` | Governance, scope finalization, result contract | `step: validation_scope_plan`, `mode: plan`, task/profile floor, planned changed files/surfaces, commands/prerequisites, `finalized: false`, findings/evidence. Actual changed files remain explicit but empty until finalization. |
| Repo adapter validation packet | Orchestrator applying `$skill-creator` validation rules | Ledger, run, repo skill gap, validation | Task ID, validation status, changed-adapter and validated-adapter counts including zero, explicit blockers, evidence paths. Invalid changed adapters cannot become routing evidence. |
| Validation-set packet | `$build-validation-set-with-agents` | Governance, schema, derive, index, validation, report | Need/status, quality tier, `not_gold`, item/label/oracle counts, source-class distribution, oracle/split/leakage/root paths, scenario coverage fields (`acceptance_scenario_id`, `premise_satisfied`, `expected_terminal_state`, `observed_terminal_state`), blocked/candidate-only reasons. |
| Governance result | `$task-md-agent-governance` | Result contract, ledger, code audit, run, schema, validation | Task ID, changed files, task_miss, used GT/advice, implementation summary, validation profile, blockers. |
| Code-structure audit packet | `scripts/code_structure_audit.py` | Run, derive, validation, issue, report | Scanned changed files, oversize files, responsibility clusters, semantic structure metrics/findings, convention conformance, moduleization requirement, split plan, semantic-refactor plan, exemptions, evidence paths. |
| Run result | `$run-task-code-and-log` | Review, loopback, validation-set, schema, derive, index, validation, issue, report | Status, command, full body-free `command_argv` or `command_provenance_missing`, exit code, output/artifact paths, running metadata, log path, shortcomings, `failure_autopsy` including stage ladder, `last_successful_stage`, `failure_surface_stage`, scalar diagnostics or `diagnostics_unavailable`, `runtime_config_echo` and `config_overrides` when available, `run_disposition` (`failed_closed`, `candidate_degraded`, `candidate_written`), `gate_satisfiability`, scalar `gate_selfcheck`, actionable blocker fields when a gate returns a reason code, Part K report/comparison fields declared by artifacts, Part L lane/freshness/basis fields declared by artifacts or adapters (`production_lane_identity`, `current_decision_lane`, `measurement_run_id`, `upstream_contract_changed_since_measurement`, `metric_basis_inputs`, `basis_overclaim`), Part M terminal disposition and collection fields (`execution_cost_scalar`, `high_cost_artifact`, `destructive_disposition_requested`, `destructive_disposition_blocked`, `quarantine_required`, `failure_check_provenance`, `reharvest_path`, `reharvest_before_rerun_required`, `collection_truncated`, `sample_as_universe_misuse`) when supplied, and any producer progress labels only as `observed_producer_claim`. For `long_run_branch=true`, preserve `event_kind`, `long_run_role`, `run_id`, `owner_task_id`, `launch_cycle_id`, `workdir`, `output_dir`, `log_path`, heartbeat, monitor/stop commands, expected completion signal/artifacts, remaining validation, residual/harvest task linkage, and Part M harvest preflight/risk-acceptance anchors when supplied. |
| Qualitative review packet | `$review-cycle-output-quality` | Loopback, validation-set, schema, derive, validation, report | `review_agent_count`, reviewed artifacts, quality verdict, findings, progress cap, output-delta fields, goal-axis completeness fields, instrumentation-exercise/acceptance-encoding/report-only hardening observations when relevant, Part L surface-field review fields (`surface_field_classes`, `surface_field_defect_matrix`, `field_class_map_missing`, `surface_field_review_status`) when locator-backed surface classes are available, no-overclaim flags, evidence paths. |
| Anti-loop progress gate | `$audit-cycle-loopback` | Derive, validation, dashboard, report | Family/root keys, semantic signature, progress booleans, terminal outcome fields, generation-independent count-key fields, failure-surface stage gate, same-input contract gate, diagnostics-unavailable/instrumentation supply and exercise gates, instrumentation first-fire credit, acceptance encoding gate, verifier-surface hardening gate, run disposition, runtime config echo, stochastic feasibility findings, verification source separation gate, frozen-envelope thaw gate, Part K expectation/parity/adoption/resolution/report-key lineage fields, Part L lane identity, decision freshness, gating-axis producer starvation, portfolio quota, cycle reachability, metric basis, and surface-field review fields, Part M harvest preflight/disposition/reharvest/predicate-directive/collection fields, quality vector, effective dispositions, hard-stop state, findings, evidence paths. |
| Loop-breaker packet | `scripts/detect_progress_loop.py` plus orchestrator synthesis | Derive, task-pack, validation, report | Blocker/root/semantic signatures, root-axis counts, terminal quiescence/escalation gates, supplied-input delta, provider retry, command surface, sealed family, zero-candidate state. |
| Task-pack packet | `scripts/task_pack_queue.py` and `$derive-improvement-task` | Derive, index, validation, report, commit | Pack ID/path/status, current item, mutation plan, Markdown render, terminal blocker state, selected disposition, `scope_fidelity` for measurable directive-derived items, `acceptance.quantifiers`, `evidence_kind`, instrumentation supply/exercise ordering fields, Part K expectation/parity/adoption/resolution/report-key contracts, and Part M harvest/disposition/predicate/collection contracts when applicable. |
| Repo skill gap packet | Orchestrator | Efficiency profile, validation, derive, report | Task ID, status, gap count including zero, gap packet with select/defer/reject recommendation, blockers, evidence paths. Adapter work remains derive-owned. |
| Cycle-efficiency profile | `$profile-cycle-efficiency` | Validation-scope finalize, validation, derive, report | Task ID, profile status, cycle fixed cost/basis, recommendation, execution-starvation or consolidation constraints, blockers, evidence paths. It is produced before validation/derive so it can constrain selection. |
| Validation-scope final packet | `$plan-validation-scope` | Pre-validation index, validation, issue, derive, report | `step: validation_scope_finalize`, `mode: finalize`, task/profile floor, planned and actual changed files/surfaces, non-empty required commands, prerequisites, `finalized: true`, findings/evidence. This packet, not the plan, authorizes completion validation. |
| Pre-validation index snapshot | `$manage-task-state-index` | Validation, issue, schema, derive, report | Current task ID, index status, stable snapshot ID, traceability blockers, evidence paths. It snapshots current-cycle state and does not mutate the next task. |
| Validation result | `$validate-task-completion` | Issue, schema, derive, post-derive index, commit, dashboard, report | Current `task_id`, `validation_verdict`, `progress_verdict`, `progress_axes`, blockers, evidence paths, advice disposition, task-pack preservation, `acceptance_provenance_gate`, `acceptance_scenario_gate`, `acceptance_verifier_gate`, `acceptance_encoding_gate`, `instrumentation_exercise_gate`, `failure_surface_stage_gate`, `diagnostics_unavailable_gate`, `verification_source_separation_gate`, `envelope_thaw` fields, `goal_axis_completeness_gate`, `verifier_surface_hardening_gate`, `run_disposition_gate`, `runtime_config_echo_gate`, `command_provenance_gate`, `blocker_actionability_gate`, `stochastic_feasibility_gate`, `expectation_lineage_gate`, `comparison_parity_gate`, `adoption_axis_gate`, `resolution_downgrade_gate`, `report_key_integrity_gate`, Part L gates (`lane_identity_gate`, `decision_freshness_gate`, `gating_axis_producer_gate`, `portfolio_quota_gate`, `cycle_reachability_gate`, `metric_basis_gate`, `surface_field_review_gate`), Part M gates (`harvest_contract_preflight_gate`, `disposal_proportionality_gate`, `contract_satisfiability_gate`, `collection_consumption_gate`), `instrumentation_first_fire_gate`, `execution_starvation_gate`, `residual_gap_marginality_gate`, `structure_metrics_gate`, and behavior-change live evidence gate when applicable. This result must exist before issue/schema/derive. |
| Issue packet | `$manage-implementation-issues` | Schema, derive, post-derive index, commit, dashboard, report | `issue_packet_id`, current `task_id`, lifecycle status, explicit `issue_ids` including `[]` for a reasoned no-op, `issue_provenance.source_task_id` plus validation ID/report path, blocker links, resolution evidence, skipped reason. Mutation status requires a durable issue ID/path/URL. |
| Derive packet | `$derive-improvement-task` | Schema reconciliation, final index, commit, dashboard, report | Validated current-task ID/verdict, issue packet provenance, archived task link, selected next task or terminal/deferred disposition, task-pack mutation evidence, blockers/evidence paths. It cannot consume a pending long run as pass/advanced or promote before validation and issue. |
| Commit packet | `$repo-change-commit` | Dashboard, report, closeout | `commit_role`, created/skipped/blocked status, commit hash/subject when created, skipped reason when not. |
| Dashboard result | `$render-cycle-dashboard` | Report, closeout | Current task ID, `dashboard_status`, ledger `event_count`, explicit `current_stage_event_count`, snapshot status, validation/progress verdicts and axes, issue/commit summaries, blockers, malformed/noncanonical event visibility, dashboard path, and evidence paths. It is a snapshot, never a completion verdict. |

## Core Packet Contracts

### Bootstrap Transaction Boundary

When no `task.md` exists, `initial_init` is a separate bootstrap transaction with order `context -> authority -> schema_pre_derive -> derive -> schema_post_derive -> index`. Use the explicit `bootstrap` workflow mode and `bootstrap_complete` transition. It may resolve authority, refresh relevant schema contracts, derive exactly one initial task, record its execution environment, reconcile contracts, and index the bootstrap result. Its derive contract requires the real `next_task_id` but not a fabricated `completed_task_id`. It must not emit task-bound acceptance, governance, run, completion-validation, issue, or promotion packets. The first normal cycle starts afterward from a fresh context and `repo_skill_adapter_scan`, then binds acceptance to the newly created task ID/path/fingerprint.

### Model And Effort Routing Evidence

Use [model-effort-routing.md](model-effort-routing.md), [model-effort-profiles.json](model-effort-profiles.json), and `scripts/model_effort_router.py` for delegated LLM work. Request packets carry `policy_id`, `profile_id`, `routing_tier`, requested model/effort, reason codes, signals, and routing violations. Result packets carry the same selection plus `routing_enforcement`; include actual model/effort only when the runtime exposes them.

`prompt_only` means the routing was written into the prompt but the delegation API did not enforce it. `inherited_unverified` means the child inherited an unverified runtime selection. Neither value proves Terra execution. A result that claims `enforced` without runtime-selectable model/effort evidence is a routing-contract defect. Deterministic scripts and direct shell commands do not need routing evidence.

Do not use delegated `ultra`. Tier 5 Sol is valid only for a target/profile allowlisted final-direction role with explicit final-direction ownership and structured evidence for every active Tier 5 signal. A Sol `max` result requires one bounded `exceptional_arbitration` agent, `prior_tier5_unresolved=true`, a structured `prior_tier5_evidence` object bound to the earlier `derive_synthesis` Sol/xhigh pass and unresolved finding, and `max_escalation_reason` describing that ambiguity.

### Gate Satisfiability

Fail-closed gates named by `task.md`, caller packets, or command harnesses must be checked before the gate is evaluated. The repository or environment adapter may expose:

```python
gate_satisfiability(gate_id, env, **context) -> {
    "satisfiable": bool,
    "reason": str,
    "alternative_evidence_source": optional[str],
}
```

`$run-task-code-and-log` records one `gate_satisfiability` entry per prechecked gate: `gate_id`, `satisfiable`, `reason`, `evidence_source`, `alternative_evidence_source`, and `classification`.

If `satisfiable=false` and no alternative source exists, classify the run as `self_inflicted_gate_defect`. Consumers must route a gate-contract/code correction task or `user_escalation`; they must not schedule another same-gate environment recheck.

For pre-execution gate artifacts, `$run-task-code-and-log` may also include `gate_selfcheck` entries with `gate_id`, `blocked_pre_exec`, `repo_owned_pre_exec_blocker`, `contradicting_evidence`, `trusted_evidence_source`, `prior_pass_observed`, `status`, `classification`, and `alternative_evidence_source`. Treat `classification: self_inflicted_gate_defect` as valid only when repository-owned provenance is confirmed. Treat `status: warn_missing_repo_owned_confirmation` as advisory until `$audit-cycle-loopback` or the adapter confirms repository-owned blocker provenance.

### Failure Autopsy

When execution fails with a nonzero exit, traceback, runtime exception, or provider/HTTP-style error, `$run-task-code-and-log` should include scalar-safe diagnostics only:

- `error_type`
- `exception_class`
- `traceback_last_frame`
- `http_status`
- `missing_env_key_names`
- `provider_request_count`
- `provider_status`
- `failure_class`
- `provider_response_empty`
- `provider_response_parse_failed`
- `mitigations_attempted`
- `mitigations_unavailable`
- `classification`
- `alternative_evidence_source`
- `gate_selfcheck`
- `execution_stage_ladder_status`
- `execution_stage_ladder`
- `last_successful_stage`
- `failure_surface_stage`
- `post_failure_scalar_diagnostics`
- `diagnostics_unavailable`
- `diagnostics_unavailable_reason`
- `runtime_config_echo`
- `config_origin`
- `config_overrides`

Do not persist raw prompts, provider bodies, generated bodies, stdout/stderr bodies, source bodies, credentials, tokens, or secrets in the autopsy packet.

When an execution stage ladder is available, `last_successful_stage` and `failure_surface_stage` are required for downstream H2 counting. If safe post-failure scalar/enum diagnostics cannot be collected, the packet must say `diagnostics_unavailable=true`; no-body and redaction policy still allows scalar diagnostics such as stage, enum status, count, HTTP code, and exception class.

When runtime config echo is available, keep only scalar/enum effective settings, each field's `config_origin`, and derived `config_overrides`. A `code_default` override is routing evidence for self-inflicted gate/default repair when it explains the blocker; it is not completion evidence.

### Qualitative Review

The qualitative review packet must report exactly one read-only reviewer agent when delegation is available. It must include `review_agent_count: 1`, reviewer routing, reviewed artifacts, direct read scope, qualitative findings, direction recommendations, blocker taxonomy delta, no-overclaim flags, evidence paths, and active advice usage or disposition.

When output-delta evidence exists, include explicit values for `output_delta_status`, `changed_vs_previous`, `semantic_progress`, `produced_domain_delta`, `metadata_only`, `effective_progress_kind`, and `progress_cap`. Omit neither false nor not-applicable values.

### Anti-Loop Progress Gate

The canonical schema for `anti_loop_progress_gate` is owned by `$audit-cycle-loopback` and documented in [packet-schema.md](../../audit-cycle-loopback/references/packet-schema.md) when that skill is available, plus [anti-loop-progress-gates.md](anti-loop-progress-gates.md) for orchestrator policy.

Consumers must preserve:

- family keys: `family_key`, `root_key`, `root_family_key`, `blocker_root_family`
- progress fields: `changed_vs_previous`, `semantic_progress`, `authoritative_semantic_progress`, `terminal_outcome_changed`
- terminal outcome fields: `terminal_outcome_key`, `terminal_outcome_family_key`
- constraint fields: `effective_allowed_dispositions`, `disposition_intersection_basis` including optional `allowed_task_kinds`, `hard_stop_required`, `evidence_class`
- root-cause fields: `repo_owned_source_roots_status`, `root_cause_unverified_hypotheses`, `root_cause_duplicate_hypotheses`, `untried_actionable_root_cause_exists`, `untried_root_cause_hypotheses`, `hypothesis_exhausted`, and provenance-hardened ledger entries
- adapter/chain fields: `adapter_mandate_required`, `adapter_contract_unmet`, `adapter_missing_streak`, `adapter_loaded`, `adapter_registered`, `adapter_wiring_defect`, `adapter_wiring_gate`, `cumulative_goal_distance_stalled`, `cumulative_goal_distance_stall_streak`, `chain_stall_forced_retarget_gate`, `forced_selected_task`, `forced_selected_task_options`, `untried_veto_overridden_by_chain_stall`
- reachability/metric fields: `acceptance_envelope_contract`, `envelope_below_floor`, `acceptance_unreachable_under_frozen_config`, `relaxation_or_escalation_required`, `oracle_metric_validity_gate`, `primary_metric_gate`, `primary_metric_stalled`, `primary_metric_zero_movement_streak`, and `c4_user_escalation_backstop_required`
- gate completeness fields: per-gate `evaluation_status: pass|fail|not_evaluated`, `acceptance_verifier_not_evaluated`, `unverifiable_acceptance_contract`, and `metric_verifier_not_evaluated`
- verifier/provenance fields: `coupled_verifier_gate`, `pass_with_coupled_verifier`, `changed_verifier_source_paths`, `evidence_provenance_gate`, `independently_verified_fields`, `producer_attested_fields`, and `attested_only_movement`
- count-key hygiene fields: `legacy_family_key`, `raw_root_family_key`, `terminal_outcome_key`, `terminal_outcome_family_key`, `terminal_outcome_family_fallback_applied`, `root_dominant_parameter_key`, and any `generation_dependent_count_key`/trace-only finding supplied by loopback
- failure-surface fields: `execution_stage_ladder_status`, `execution_stage_ladder`, `last_successful_stage`, `failure_surface_stage`, `failure_surface_count_key`, `failure_surface_stage_gate`, `terminal_classification_stage_contradiction`, `terminal_classification_invalid_for_counting`, `same_input_contract_gate`, and `same_input_contract_violation`
- diagnostics/instrumentation fields: `diagnostics_unavailable`, `diagnostics_unavailable_streak`, `diagnostics_unavailable_gate`, and `instrumentation_supply_required`
- evidence lifecycle fields: `instrumentation_exercise_required`, `instrumentation_exercised`, `instrumentation_field_map`, `derived_from_existing_artifacts`, `acceptance.quantifiers`, `evidence_kind`, `acceptance_diluted`, `verifier_surface_hardening`, `guard_stacking_cap_reached`, `target_artifact_paths`, `run_disposition`, `candidate_degraded`, `runtime_config_echo`, `config_overrides`, and `execution_starvation`
- Part J fields: `acceptance_scenarios`, `scenario_coverage`, `scenario_uncovered`, `acceptance_inversion`, `command_argv` or `command_provenance_missing`, `blocker_actionability_gate`, repeated `blocker_opacity`, `instrumentation_first_fire`, `first_fire_consumed_item_id`, `outcome_variance`, `predetermined_unreachable`, and `floor_edge_envelope`
- Part K fields: `expectation_anchor`, `designated_baseline`, `expectation_anchor_missing`, `expectation_lineage_stale`, `parity_axes`, `parity_axis_status`, `parity_unverified`, `adoption_axis_classification`, `required_output_classes`, `majority_vote_adoption`, `provisional_adoption`, `measured_but_disqualified`, `required_evidence_resolution`, `observed_evidence_resolution`, `resolution_downgrade`, `surrogate_resolution_basis`, `report_key_divergence`, and duplicate report-key path/value evidence
- Part L fields: `production_lane_identity`, `current_decision_lane`, `lane_identity_missing`, `pass_on_stale_lane`, `decision_metadata_revision`, `stale_measurement_artifact`, `axis_starved_by_missing_producer`, `producer_supply_required`, `portfolio_quota_exceeded`, `unreachable_within_cycle`, `long_run_launch_required`, `basis_overclaim`, `actual_basis_class`, `field_class_map_missing`, and `surface_field_defect_matrix`
- Part M fields: `harvest_gate_inventory`, `harvest_contract_preflight`, `harvest_gate_unaudited`, `harvest_risk_accepted`, `lane_incompatible`, `scale_incompatible`, `contract_conflict`, `execution_cost_scalar`, `high_cost_artifact`, `destructive_disposition_requested`, `destructive_disposition_blocked`, `quarantine_required`, `failure_check_provenance`, `reharvest_path`, `reharvest_available`, `reharvest_before_rerun_required`, `rerun_before_reharvest`, `validation_predicate_contract`, `producer_directives`, `mutually_unsatisfiable_contract`, `closed_world_collection_consumption`, `collection_truncated`, `sample_as_universe_misuse`, `full_collection_required`, and `sample_consistency_only`
- verification source fields: `verification_source_separation_gate`, `verification_input_paths`, `verified_artifact_paths`, `independent_source_separation_status`, and `independently_verified_downgraded_fields`
- envelope thaw fields: `envelope_thaw_item_required`, `envelope_thaw_item`, `thaw_condition`, `thaw_schedule`, and `envelope_thaw_streak`
- goal-axis completeness fields: `goal_axis_map`, `unobserved_goal_axes`, `pass_with_unobserved_axes`, and `goal_axis_completeness_gate` when review or the adapter supplies them
- residual-gap cost fields: `cycle_fixed_cost`, `alternative_cycle_cost`, `marginal_gap_value`, `marginal_value_per_cycle_cost`, `alternative_value_per_cycle_cost`, and `residual_gap_cost_policy` when profile/normalize/derive supplies them
- truth-source fields: `producer_progress_claim_fields`, `observed_producer_claim`, and `split_brain_progress_claim`
- warn-only fields: `partial_progress_axes_gate` and `advice_freshness_gate.gate_result_regression_stale`
- mutation fields: `blocker_mutation_kind`, `root_dominant_parameter_key`, `forward_mutation_vacuous`, `forward_mutation_budget_remaining`, `force_implementation_cycle`
- evidence: findings and `evidence_paths`

### Acceptance Provenance

When task direction originates in advice, issue, task pack, or user steering with a measurable target, `$task-doctor` and `$derive-improvement-task` must preserve a directive-to-item mapping through `scope_fidelity`. `$validate-task-completion` owns the close-time comparison against the original target.

Generic fields:

- `scope_fidelity.directive_id`: stable source directive identifier.
- `scope_fidelity.original_target`: abstract measurable target. Project-specific metric definitions and thresholds belong in the advice packet, task pack, repository adapter, or project-owned contracts.
- `scope_fidelity.item_acceptance`: acceptance copied from or traceable to the original target.
- `scope_fidelity.acceptance.quantifiers`: original counts, rates, run counts, row counts, disjointness predicates, or other measurable relation predicates copied without reinterpretation.
- `scope_fidelity.acceptance.evidence_kind`: `live_run`, `derived_artifact`, `code_contract`, or `report_only`; a live-run requirement needs a satisfying run id after item creation.
- `scope_fidelity.narrowed`, `narrow_reason`, and `residual_item_id`: explicit descope record and open residual scope.
- `acceptance_provenance_gate.target_met`: validation result comparing actual achievement to the original target.
- `acceptance_provenance_gate.acceptance_diluted`: true when the item was closed against a weaker target.
- `acceptance_provenance_gate.explicit_descope_decision`: true only when a reason and residual item/link exist.

Consumers must not mark a measurable item consumed, applied, or complete when `acceptance_diluted=true`. A narrowed item may be useful progress, but it remains `partial` unless the original target is met or the residual target stays open under an explicit descope decision.

Consumers must not satisfy `evidence_kind=live_run` with a derived artifact, code contract, or report-only matrix. If a live-run criterion cannot be executed, preserve residual scope, explicit descope, terminal blocker, or user escalation.

When adapter `residual_gap_policy` is available, consumers should preserve residual-gap fields supplied by normalize/derive such as `residual_gap_ratio`, `residual_gap_policy`, `marginal_repair`, and `descope_with_residual`. A residual gap below the adapter threshold should default to explicit descope with residual scope plus the next capability-ladder rung rather than another same-gap repair.

### Acceptance Scenario Coverage

When normalized acceptance contains a scenario contract of the form premise class -> expected terminal state, the validation-set plan must require at least one fixture or live run whose scalar inputs satisfy the premise. The completion gate consumes only two facts: whether the premise was actually injected, and whether the observed terminal state equals the expected state.

Generic fields:

- `acceptance_scenarios`: list of `{scenario_id, premise_predicate, expected_terminal_state}`.
- `scenario_coverage`: list of `{scenario_id, evidence_path, premise_satisfied, observed_terminal_state}`.
- `scenario_uncovered`: true when no evidence item satisfies the premise.
- `acceptance_inversion`: true when evidence or changed tests assert the opposite terminal state for a premise-satisfying input.

Green tests, high test count, or verifier pass rate do not override this gate. `scenario_uncovered` routes back to validation-set planning; `acceptance_inversion` fixes the verdict at `partial` and routes implementation/code contract repair.

### Command Provenance And Blocker Actionability

Live execution packets must preserve the full argv once in body-free form. Redaction may mask values, but it must not remove argument names. If only a summarized command, `...`, or missing flags are recorded, set `command_provenance_missing=true`; the run may still be evidence for other facts but cannot be a baseline, A/B, comparison, or reproduction source.

Gate and validator blockers should be actionable. A blocker reason code should carry the violated abstract relation, observed scalar values, expected relation, and, when possible, a minimum input delta. If only a state name is returned, set `blocker_opacity=true`. Repeated opacity for the same gate is a derive candidate for blocker-contract repair; it is warn-only until the repeated condition exists.

### Long-Running Execution Branch

Use `step: run` for every long-running event. Set `event_kind` to `long_run_launch`, `long_run_monitor`, `long_run_harvest`, or `long_run_finalize`, and set `long_run_role` to `launch`, `monitor`, `harvest`, or `finalize`. Do not add a new canonical phase.

Required fields for `long_run_branch=true` are `run_id`, `owner_task_id`, `launch_cycle_id`, `command_argv`, `workdir`, `output_dir`, `log_path`, `startup_or_heartbeat_evidence`, `monitor_command`, `stop_command`, `remaining_validation`, `expected_completion_signal`, and `expected_completion_artifacts`.

`long_run_launch` can satisfy only the workflow handoff objective. If the original task required live-run/domain evidence, preserve it through `scope_fidelity`, `residual_item_id`, or `harvest_task_id`; do not mark the original target consumed from launch/startup evidence. `completed_pending_validation` means terminal artifacts appear to exist, but harvest validation still owns completion, output-delta, review, loopback, and issue/commit decisions.

### Stochastic Feasibility And First-Fire Credit

When adapter or caller evidence reports `outcome_variance` for a stochastic producer, exact equality contracts and envelope/floor slack smaller than observed variance are contract feasibility problems. Use `predetermined_unreachable` for exact-match contracts and `floor_edge_envelope` for too-small slack. Derive should route to interval/ratio/intersection criteria, envelope expansion, explicit residual descope, terminal blocker, or user escalation rather than another retry.

When a run first produces non-empty scalar evidence for supplied instrumentation, record `instrumentation_first_fire=true`. This credit is a positive evidence delta even when the run is failed or degraded, but it may consume only one workflow item and cannot also satisfy goal progress or the original instrumentation-supply item.

### Expectation And Comparison Lineage

Output-derived scalar expectations must carry `expectation_anchor` and, when supplied, current `designated_baseline`. If the anchor surface is superseded, set `expectation_lineage_stale`; derive must rebaseline or fail closed before live execution. Missing anchors are warning-level through `expectation_anchor_missing`, but consumers must not describe the expectation as lineage verified.

Comparison or adoption tasks must carry `parity_axes` with each axis classified as `controlled`, `measured`, or `unknown`. `unknown` axes force `parity_unverified` and make final adoption/baseline promotion invalid until resolved, explicitly provisional, terminal-blocked, or escalated. Axis definitions and echo/equality checks are adapter-owned.

Adoption axes must be classified before measurement as `gating` or `tradable`, using adapter/caller `required_output_classes` or equivalent goal-contract evidence. A failed gating axis makes the candidate `measured_but_disqualified` and blocks final adoption regardless of tradable-axis wins. Missing classification makes majority-vote adoption only provisional.

When a contract requires id, row, element-set, or intersection evidence but the implementation reports a count, ratio, ordinal, or other lower-resolution surrogate, preserve `resolution_downgrade` and `surrogate_resolution_basis`. First occurrence is provisional/warn evidence; repeated same-contract downgrade should route resolution restoration or contract revision.

When one report contains the same terminal key at multiple JSON paths with divergent values, set `report_key_divergence=true`. Result contracts and validation must block pass/close/adoption/baseline/comparison consumption of that report until the report is repaired or a single source with matching values is declared. Matching duplicate terminal keys are warn-only schema debt.

### Lane Lineage And Premise Supply

Capability, validation, comparison, adoption, and qualitative-review decisions must preserve what artifact lane and premise supply they actually consumed.

Generic fields:

- `production_lane_identity`: opaque key for the artifact or output lane validated by a verifier, review, or metric.
- `current_decision_lane`: opaque key for the lane currently under capability, adoption, baseline, comparison, or next-rung decision.
- `lane_identity_missing`: true when either lane hook is absent; this is warning evidence unless the task explicitly requires lane binding.
- `pass_on_stale_lane`: true when a verifier/review pass applies to a different lane than the current decision target.
- `decision_metadata_revision`: true when a decision update only relabels stale artifacts after relevant upstream production contract changes.
- `axis_starved_by_missing_producer`: true when a gating axis is zero/unmet because the producer path that should populate it is absent or unexercised.
- `portfolio_quota_exceeded`: true when recent verifier/guard/report/metadata work exceeds the adapter-owned verifier:producer quota.
- `unreachable_within_cycle`: true when required target scale exceeds observed cycle throughput times the cycle cap.
- `basis_overclaim`: true when a metric's claimed basis class is not derivable from consumed input classes.
- `surface_field_defect_matrix`: scalar counts by producer-written field class and defect class from locator-backed qualitative review.

Consumers must not use `pass_on_stale_lane` as current-lane capability, adoption, comparison-winner, or next-rung evidence. They may record the pass as historical or contract evidence and keep current-lane rerun/residual work open.

Consumers must treat `decision_metadata_revision` as governance or metadata progress only. It cannot consume a measurement/adoption pack item, reset high-water movement, or satisfy `goal_productive` unless a fresh current-lane run id exists or the packet proves the upstream change cannot affect the measured axis.

When `axis_starved_by_missing_producer=true`, derive should choose producer-supply work before adding another verifier, guard, consistency check, or report for the same axis. Those verifier-like items collapse under verifier-surface hardening until producer supply fires.

When `portfolio_quota_exceeded=true` and the adapter explicitly supplies `portfolio_quota_mode=restrict`, derive is limited to producer, envelope, long-run, descope-with-residual, terminal blocker, or user escalation. Default quota evidence without an adapter hook is warn-only.

When `unreachable_within_cycle=true`, derive must route to long-run launch with monitor/harvest plan, throughput improvement, explicit descope-with-residual, terminal blocker, or user escalation. `$monitor-running-execution` and later harvest validation own completion evidence; launch/startup evidence does not consume the original domain acceptance.

When `basis_overclaim=true`, downgrade affected metric fields to the actual consumed-input class and treat them as producer-attested or otherwise non-authoritative under F2. Honest downgrade of the basis label is not a regression.

When `surface_field_defect_matrix` has nonzero counts, loopback and derive should feed those counts into root-family and producer-supply routing. The review packet must not store raw excerpts unless authority explicitly allows them; absent `surface_field_classes` fails quiet.

### Execution Context Reaudit

Use [execution-context-contracts.md](execution-context-contracts.md) whenever Part M launch, terminal disposition, predicate/directive, or collection-consumption fields appear in a packet. These are in-place revisions of existing long-run, validation, derive, schema, and result-contract decisions; do not create a new canonical phase.

Generic fields:

- `harvest_contract_preflight`: prelaunch harvest-gate compatibility packet for cycle-unreachable long runs.
- `harvest_gate_unaudited`: true when an adapter inventory was absent; warn/fail-quiet unless acceptance declares the preflight required.
- `harvest_risk_accepted`: explicit acceptance of a known harvest risk when launch proceeds before repair.
- `lane_incompatible`, `scale_incompatible`, `contract_conflict`: non-degradable harvest preflight findings.
- `high_cost_artifact`, `destructive_disposition_blocked`, `quarantine_required`, `failure_check_provenance`, and `reharvest_path`: terminal disposition and reharvest routing fields.
- `validation_predicate_contract`, `producer_directives`, and `mutually_unsatisfiable_contract`: predicate/directive compatibility fields.
- `closed_world_collection_consumption`, `collection_truncated`, `sample_as_universe_misuse`, and `full_collection_required`: closed-world collection-consumption fields.

Consumers must route non-degradable harvest incompatibility to repair/mitigation or explicit `harvest_risk_accepted=true` before long-run launch. High-cost non-safety artifacts must be quarantined rather than destructively overwritten, and available reharvest should precede a new full rerun after verifier/governance failures. `mutually_unsatisfiable_contract=true` blocks consuming either predicate or directive as valid until reconciliation, residual descope, terminal blocker, or user escalation. `sample_as_universe_misuse=true` blocks pass/close consumption until a full collection is supplied or the contract is revised to sample-only consistency.

### Acceptance Envelope And Verifier

When normalized acceptance has a measurable target and a domain adapter exposes `min_envelope_for(target)`, the acceptance packet should carry `acceptance_envelope_contract` with abstract `envelope_floor`, `deficit_axis`, comparison status, and evidence paths. Project-specific metrics, capacities, model limits, paths, and thresholds remain in the adapter or project-owned contracts.

If `envelope_below_floor=true`, consumers must treat the selected or executed slice as acceptance-incomplete. They may select envelope expansion, explicit descope with residual scope, or user escalation; they must not lower the target silently or reclassify the planned failure as a new prompt/tool/schema blocker. If the adapter hook is absent, fail quiet and keep existing acceptance rules.

If reachability evidence says the target is unreachable under a frozen envelope, consumers must preserve `acceptance_unreachable_under_frozen_config`, `frozen_envelope`, `deficit_axis`, and either `envelope_thaw_item` with thaw condition/schedule or `envelope_thaw_item_required=true`. Derive and validation must not consume another envelope-internal micro-repair as `goal_productive` until thaw, constraint relaxation, residual descope, terminal blocker, or user escalation is recorded.

When normalized acceptance has a measurable target and a domain adapter or caller packet exposes a required live verifier, the acceptance packet should carry `acceptance_verifier_contract` with abstract `required_verifier`, `verifier_required`, `evaluation_status`, and evidence paths. A required verifier without an explicit passing evaluation is `not_evaluated`, not pass. If the required verifier is `not_evaluated`, consumers must treat the target as `unverifiable_acceptance_contract=true`: useful work may remain partial, but the original target cannot be consumed or marked applied without verifier implementation, explicit descope with residual scope, terminal blocker, or user escalation. If the target-to-verifier mapping hook is absent, fail quiet and keep existing acceptance rules.

If measurable acceptance names or depends on a gate whose SKILL.md contract lists required adapter hooks, those hooks are verifier completeness for that target. When a required hook is absent, failed to load, or returns `evaluation_status: not_evaluated`, normalize the target as `unverifiable_acceptance_contract=true` through the same E2 path. Do not count a gate's fail-quiet behavior as pass once acceptance declares that gate required.

### Goal-Axis Completeness

When a qualitative review is used as pass evidence for a measurable goal, the review or caller packet may carry `goal_axis_map` from the repository adapter. Consumers check only the formal condition that every active measurable goal maps to at least one `quality_vector` axis. If any goal maps to zero axes, the review packet must set `pass_with_unobserved_axes=true` and list `unobserved_goal_axes`; derive and validation must treat the review as not-pass for those goals. Preserve adapter axis-supply work, explicit descope with residual scope, terminal blocker, or user escalation. If `goal_axis_map` is absent, fail quiet to legacy review semantics without inventing domain axes.

### Residual Gap Cost Ratio

When `residual_gap_policy` is available and a cycle-efficiency profile supplies cost evidence, consumers should compare residual-gap repair by value per cycle cost. Generic fields are `marginal_gap_value`, `cycle_fixed_cost`, `marginal_value_per_cycle_cost`, `alternative_expected_value`, `alternative_cycle_cost`, and `alternative_value_per_cycle_cost`. If cost evidence is absent, use denominator `1` and preserve legacy F3. A below-policy cost ratio defaults to explicit descope-with-residual plus the next capability rung unless the adapter records a higher value case.

### Progress Truth-Source Seal

Producer artifacts and run logs may contain progress fields such as `progress_kind`, `effective_progress_kind`, `progress_verdict`, `goal_productive`, or `produced_domain_delta`. `$run-task-code-and-log` must store these under `observed_producer_claim` using adapter `producer_progress_claim_fields()` when available. Downstream loopback, derive, and validation must not read those claims as authoritative progress.

Authoritative progress must come from adapter-recomputed quality/substance/structure evidence, strict output-delta fields, or validation gates. If producer self-report conflicts with recomputed evidence, set `split_brain_progress_claim` and use the conservative recomputed verdict.

When `evidence_provenance_gate` is present, authoritative high-water and `goal_productive` evidence are limited to `independently_verified_fields`. `producer_attested_fields` and `attested_only_movement` are trace evidence only and must not reset stalls or satisfy progress requirements.

`independently_verified_fields` are authoritative only when H4 source separation holds: `verification_input_paths` must be disjoint from the verified artifacts unless the adapter marks the axis `self_grounded=true`. If source paths are missing or overlap, consumers must move the affected fields to attested evidence through `independently_verified_downgraded_fields`, even when a zero-disagreement result is reported.

### Refactor And Behavior-Change Evidence

When a behavior-preserving refactor or consolidation claims structural reduction, `$audit-cycle-loopback` may pass adapter-supplied `structure_metrics_gate.structure_high_water_moved`, `structure_high_water_key_scope`, `structure_global_invariant_metrics`, `improved_structure_axes`, `refactor_effect_required`, and semantic metrics such as shard count, coupling signal count, duplicate definition count, depth, fan-out, reuse ratio, and max LOC. `$validate-task-completion` must not complete a structural-reduction task from module creation, file-count growth, relocated helpers, token/pattern avoidance, producer self-reports, or green tests alone when that gate says high-water did not move. If `structure_high_water_key_scope=global_invariant`, selected-scope improvement cannot satisfy global structure progress while global invariants are flat.

When `disposition_intersection_basis` includes `allowed_task_kinds`, `$derive-improvement-task` must emit `selected_task_kind` and choose one of those kinds for `goal_productive`. Label-only `goal_productive` is a contract failure. When `forced_selected_task` is present, the selected task kind must match it unless the result is terminal/user escalation with evidence that the forced option became unactionable.

When a task changes runtime gate, routing, validator, dispatch, or judgment behavior, `$validate-task-completion` must require fresh live before/after evidence, or record an explicit defer gate that leaves follow-up work open. Unit/static evidence alone does not complete behavior-change work whose purpose is to change live outcomes.

### Loop Breaker And Terminal Gates

`scripts/detect_progress_loop.py` produces or contributes loop-breaker evidence. The derive packet must carry normalized `blocker_signature`, additive `semantic_signature`, suffix-normalized `root_key`, root-axis counts, compared cycle IDs, positive input delta status, provider reattempt/mitigation gate status, command-surface budget, sealed-family matches, and zero-candidate state.

When `terminal_escalation_gate.escalation_required=true`, the derive result must emit `selected_task_source: user_escalation`, `forced_disposition: user_escalation`, `terminal_recheck_streak`, `required_missing_input_count: 1`, exactly one `required_missing_input.kind`, and `.task/sealed_blocker_families.json` update or mutation-plan evidence.

When terminal blocking is selected, use the `terminal_blocker` shape in [task-pack-workflow.md](task-pack-workflow.md). Do not write another non-terminal recheck in a sealed family without a supplied input delta, authority change, external-state change, or verified unexhausted root-cause repair.

### Repo Adapter And Gap Packets

Repo adapter packet details are owned by [repo-local-skill-adapters.md](repo-local-skill-adapters.md). The orchestrator passes adapter packets as non-GT capability evidence only.

`repo_skill_gap_packet` should include repeated domain lookup, repeated command/profile discovery, validation/oracle/source-class ambiguity, progress-classification uncertainty, missing or stale `code_convention_contract`, adapter validation failures, task_miss caused by missing repo-specific procedure, recommended adapter name/scope/resources, and defer/reject rationale when not selected.

## Helper Script Surfaces

Helper scripts provide decision-support evidence. They do not replace owning skill judgment.

| Script | Inputs | Output or write surface | Consumers |
| --- | --- | --- | --- |
| `collect_cycle_context.py` | `--root`, optional Git/file limits | Compact JSON for `task.md`, `.agent_goal`, `.agent_advice`, `.task`, `.issue`, `.agent_log`, `.schema`, `.contract`, validation, Git | Context, packets, report |
| `cycle_ledger.py` | `init`, `append`, `render`, `current`; stage JSON or explicit `--step` | `initialization.json` storage bootstrap; `stage.jsonl` beginning with canonical `context`; `current_stage.json`, packets, dashboard support | Dashboard, report, transition checks |
| `render_subskill_packet.py` | `--target <phase>`, context/stage evidence | Markdown or JSON packet with routing, required inputs/outputs, GT/advice separation | Every owning subskill |
| `validate_cycle_transition.py` | `--transition <name>`, accumulated `--stage`, separate current `--routing-json`, optional `--workflow-mode bootstrap` | Transition `pass|warn|block` findings without reading a prior stage's route as the current target route | Orchestrator before major phases |
| `result_contract.py` | `--target <target>`, `--mode warn|block`, result JSON, optional long-run `--context`; stable facade over `result_contract_lib` rule registry | Contract findings, ledger-envelope readiness, pending-long-run pass/advanced and ordinary-derive blocks, plus target gate findings | Orchestrator before advancing stages; focused consumers may instantiate a target rule through `RuleContext`/`RuleRegistry` |
| `$plan-validation-scope` helpers | Planned files/surfaces before governance; actual changed files afterward | `validation_scope_plan` followed by authoritative `validation_scope_finalize` | Governance, pre-validation index, validation, derive, report |
| `code_structure_audit.py` | `--root`, changed-file list or input JSON, optional `--convention-json` | Scalar audit packet with size, responsibility, semantic structure, and convention-conformance fields; no source bodies; no patches | Run, derive, validation, report |
| `detect_gt_constraint_conflict.py` | `--root`, task/GT/behavior evidence | GT/task conflict packet | Derive |
| `detect_progress_loop.py` | `--root`, optional registry writes | Loop-breaker packet, feature-symbol gate, terminal gates, sealed-family evidence | Derive, task-pack, validation, report |
| `output_delta_contract.py` | `--root`, output paths/contracts when present | Output-delta packet or not-applicable reason | Review, loopback, derive, validation |
| `task_pack_queue.py` | `status`, `validate`, `render`, `next`, `apply-mutation`, `mark-consumed` | `.task/task_pack/*.json` canonical queue and Markdown render when mutating through derive-approved plan; validates `scope_fidelity` and measurable acceptance provenance when present | Derive, index, validation, report |
| `visible_increment.py` | Completed evidence, cycle ID, task ID | Formal `visible_increment` envelope; optional `.task/delta/<cycle-id>-visible-delta.{md,json}` with `not_validation_evidence: true` | Report only; not validation |
| `render_cycle_dashboard.py` | Cycle ledger evidence | Korean `dashboard.md` snapshot | Report, closeout |
| `profile_cycle_efficiency.py` | Task ID and cycle ledger evidence through repo skill gap analysis | Formal `cycle_efficiency_profile` envelope with cycle-cost and `execution_starvation` fields when applicable | Scope finalization, validation, derive, report |
| `monitor_running_execution.py` | Running process/log metadata, optional tmux session and completion artifact paths | Running-state verification without success promotion; optional `step: run` ledger append with `event_kind: long_run_monitor` | Validation, report |
| `assemble_cycle_report.py` | Context, validation, progress, commit JSON | Korean report draft/check in required field order | Final report |

## Fail-Closed Consumer Rules

- Treat missing or malformed packet evidence as `conservative_hold`, `not_applicable`, `partial`, or `blocked`; never silently upgrade it to success.
- For the optional session sidecar, reject raw transcript input and unvalidated/privacy-unsafe packets. Treat absence, transcript-only claims, incomplete capture, and quarantine as advisory/`not_evaluated` unless acceptance or the caller independently marked the audit required; only independently referenced canonical mismatches may lower or block an owning verdict.
- Treat missing/mismatched acceptance source task ID/path/fingerprint as blocking before governance. Acceptance from a prior task fingerprint is not reusable task-bound evidence.
- Treat a validation-scope plan as non-authoritative after implementation. Completion validation requires a `mode: finalize`, `finalized: true` packet with actual changed files explicitly present and at least one required command.
- Treat missing issue source-task/validation provenance as blocking before schema/derive. Created, updated, opened, resolved, or closed issue state without a durable issue ID/path/URL is invalid; an explicit `issue_ids: []` is allowed only for a reasoned skipped/not-applicable no-op.
- Treat acceptance scenarios as uncovered unless a fixture or live run actually satisfies the premise predicate. Green tests that never inject the premise are not scenario coverage.
- Treat `acceptance_inversion=true` as a code/contract repair condition and keep completion `partial` even when the current test suite is green.
- Treat `command_provenance_missing=true` as disqualifying for baseline, A/B, comparison, and reproduction evidence, while preserving the run for other scalar facts.
- Treat `blocker_opacity=true` as warn-only until repeated for the same gate; repeated opacity is a repair candidate for the gate/blocker contract.
- Treat `predetermined_unreachable` and `floor_edge_envelope` as contract-revision findings, not retry findings.
- Treat `instrumentation_first_fire=true` as one evidence credit only. Do not double-count it as goal progress and instrumentation-supply consumption.
- Treat `expectation_lineage_stale=true` as blocking live-execution promotion that depends on the stale scalar until rebaseline, explicit residual descope, terminal blocker, or user escalation.
- Treat `parity_unverified=true` and unknown parity axes as incompatible with final adoption, baseline promotion, or comparison-winner claims.
- Treat failed `gating` adoption axes and `measured_but_disqualified=true` as blocking adoption of that candidate while preserving the artifact as measured evidence.
- Treat `resolution_downgrade=true` as lower-resolution evidence only; do not consume it as high-resolution proof without contract revision or residual high-resolution scope.
- Treat `report_key_divergence=true` as a blocking report-integrity defect for pass/close/adoption/baseline/comparison/high-water claims.
- Enforce `effective_allowed_dispositions` as an intersection already computed by gates. Do not union individual gate dispositions.
- Enforce gate-constrained `allowed_task_kinds` inside `disposition_intersection_basis`; do not accept unrelated tasks merely because their disposition label is `goal_productive`.
- Treat `adapter_wiring_defect=true` as a self-inflicted workflow wiring/load bug. Do not downgrade it to adapter absence, adapter mandate, environment failure, or terminal blocker without a wiring/load correction attempt or user escalation.
- Treat self-reported `produced_domain_delta`, non-empty rows, lineage, gap reports, renamed commands, or metric existence as insufficient for goal-productive progress without strict changed-and-semantic output evidence or independent validated positive evidence.
- Treat `acceptance_diluted=true` as incompatible with final completion. Preserve residual measurable scope instead of consuming the original directive.
- Treat `unverifiable_acceptance_contract=true` as incompatible with final completion for the measurable target. Preserve required verifier work or explicit descope/residual scope.
- Treat behavior-preserving refactor completion claims as partial when adapter-supplied structure high-water is flat and the original objective was structural reduction. Additional files, numbered shards, version-suffix modules, relocated helpers, token/pattern avoidance, or producer-local reports are not structural progress by themselves.
- Treat `evaluation_status: not_evaluated` as not-pass when a gate is required by acceptance, task, advice, issue, or caller packet.
- Treat absent required adapter hooks for acceptance-referenced gates as `not_evaluated`, not pass.
- Treat `pass_with_coupled_verifier=true` as not-pass for completion, high-water movement, and `goal_productive`; require non-coupled revalidation, independent evidence recalculation, explicit residual descope, terminal blocker, or user escalation.
- Treat `pass_with_unobserved_axes=true` as not-pass for review-backed measurable goals; require adapter axis supply, explicit residual descope, terminal blocker, or user escalation.
- Treat generation-dependent count keys as trace-only. Do not let task/advice/pack/cycle/run IDs, dates, hashes, or version suffixes prove a blocker family is new.
- Treat terminal-classification/failure-surface contradictions as invalid for counting or close. Do not close or seal a family from a terminal classification whose allowed stage map excludes the observed `failure_surface_stage`.
- Treat same-condition input-set mismatch as invalid for same-family comparison. Do not reset stalls or close a family across mismatched windows/input sets.
- Treat repeated `diagnostics_unavailable` as an instrumentation-supply trigger. Do not advance another hypothesis repair unless instrumentation lands or a concrete observability rationale proves success/failure is already measurable.
- Treat supplied-but-unexercised instrumentation as unresolved. Do not advance dependent measurement, adoption, baseline, or close work unless a fresh run id exercised the supplied fields or a concrete observability rationale removes the dependency.
- Treat `evidence_kind=live_run` as requiring a run id after item creation. Derived artifacts, code contracts, and reports are not substitutes without explicit descope and residual scope.
- Treat same-target verifier/guard/report-only changes past the hardening cap as no-progress for `goal_productive`; require fresh execution-output evidence, explicit descope, terminal blocker, or user escalation.
- Treat `candidate_degraded` as preserved quality-miss evidence, not canonical success or baseline replacement. Only independently verified axes may be consumed later.
- Treat `runtime_config_echo` as failure/root-cause routing evidence only, and route plausible `code_default` overrides to self-inflicted default repair rather than opaque retry.
- Treat `execution_starvation=true` as a derive ranking input favoring execution-producing work over another guard/report/contract task unless safety, authority, or terminal constraints block execution.
- Treat pending long-running statuses (`launching`, `running`, `completed_pending_validation`, `stale`, `not_running`) as eligible only for partial handoff validation. They are incompatible with final-output-dependent review, loopback, ordinary derivation or task-pack promotion, issue closure, `validation_verdict: passed`, `progress_verdict: advanced`, and `complete_verified`. Select monitor, harvest, finalize, terminal blocker, or user escalation for the same `run_id`.
- Treat Part M harvest-gate incompatibility, destructive high-cost disposition, rerun-before-reharvest, mutually unsatisfiable predicate/directive contracts, and sample-as-universe misuse as incompatible with pass/close/progress consumption until their matching repair, explicit residual/descope, terminal blocker, or user escalation is recorded.
- Treat non-disjoint or missing verification inputs as an automatic downgrade from `independently_verified` to attested unless the adapter marks the axis `self_grounded`.
- Treat frozen-envelope unreachable acceptance as requiring `envelope_thaw_item`, constraint relaxation, explicit residual/descope, terminal blocker, or user escalation before ordinary repair can count.
- Treat below-policy residual-gap value per cycle cost as marginal repair; do not select or validate another same-gap repair as `goal_productive` without a higher value case.
- Treat `attested_only_movement=true` as no high-water movement. It cannot reset G-CHAIN/C4 stall counters or satisfy `goal_productive`.
- Treat runtime behavior-change completion claims as partial when fresh live before/after evidence is required but absent.
- Keep `available_goal_truth` separate from `used_goal_truth`; final `기준 GT` may list only actually used GT.
- Keep `.agent_advice` out of GT and authority. Active advice in scope requires `used_advice` or an explicit defer/reject/not-applicable rationale.
- Keep repo-local adapters out of GT, authority, human approval, and completion evidence.
- Preserve raw subskill statuses in result packets, but write lifecycle statuses such as `complete`, `partial`, `skipped`, `not_applicable`, `blocked`, or `failed` to the ledger.
- Do not let validation-set assets, visible-increment artifacts, dashboard snapshots, or closeout commits replace completion validation.
