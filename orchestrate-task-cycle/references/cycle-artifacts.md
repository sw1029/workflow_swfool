# Cycle Artifact Contracts

This reference defines durable workflow artifacts for `$orchestrate-task-cycle`. These artifacts are not workspace goal truth and do not replace owning skill verdicts.

## Contents

- [Cycle Ledger](#cycle-ledger)
- [Result Contracts](#result-contracts)
- [Visible Increment](#visible-increment)
- [Validation Scope](#validation-scope)
- [Evidence Cache](#evidence-cache)
- [Dashboard And Profile Snapshots](#dashboard-and-profile-snapshots)
- [Running Execution](#running-execution)

## Cycle Ledger

Store cycle state under `.task/cycle/<cycle-id>/`:

- `stage.jsonl`: append-only stage events.
- `current_stage.json`: latest stage summary.
- `packets/*.md` or `packets/*.json`: rendered subskill packets.
- `.task/cycle/<cycle-id>/packets/code_structure_audit_packet.json`: read-only generated-code size, module-boundary, semantic-structure, and convention-conformance audit evidence.
- `final_report.md`: durable final report draft when written.
- `dashboard.md`: Korean dashboard snapshot rendered from ledger evidence, preserving canonical step/status tokens, paths, IDs, hashes, and the rendered `event_count`.
- `commit-result.json`: implementation or closeout commit result when written.
- `.task/quality_review/<cycle-id>-direct-output-quality-review.{md,json}`: optional direct qualitative output review evidence from `$review-cycle-output-quality`.
- `.task/cycle/<cycle-id>/packets/loopback_audit_packet.json`: anti-loop progress packet from `$audit-cycle-loopback`.
- `.task/validation_set/<cycle-id>-validation-set-*.{md,json}`: cycle-local validation-set plan/build/consume evidence from `$build-validation-set-with-agents`.

Task-pack planning artifacts are stored outside the cycle ledger under `.task/task_pack/`:

- `.task/task_pack/pack-<timestamp>-<slug>.json`: canonical task-pack queue.
- `.task/task_pack/pack-<timestamp>-<slug>.md`: user-language Markdown render of the JSON queue.

Task packs are workflow planning state, not `.agent_goal` goal truth. A task pack may contain many planned items, but the workspace must still have only one active `task.md`.

Reusable validation assets are stored outside the cycle ledger under `.validation/`:

- `.validation/sets/<validation-set-id>/validation_set_manifest.json`
- `.validation/sets/<validation-set-id>/validation_set_items.jsonl`
- `.validation/sets/<validation-set-id>/validation_set_labels.jsonl`
- `.validation/sets/<validation-set-id>/oracle_manifest.json`
- `.validation/sets/<validation-set-id>/split_manifest.json`
- `.validation/sets/<validation-set-id>/leakage_report.json`
- `.validation/sets/<validation-set-id>/disagreement_report.json` when adjudication occurred
- `.validation/sets/<validation-set-id>/validation_set_root.json`
- `.validation/candidates/<cycle-id>-<slug>/` for non-frozen candidates
- `.validation/registry.jsonl` and `.validation/index.md` when maintained

Each stage event should include these fields when known:

- `cycle_id`
- `event_id`
- `step`
- `status`
- `reason`
- `task_id`
- `completed_task_id`
- `next_task_id`
- `changed_files`
- `artifacts`
- `artifact_refs`
- `unchanged_refs`
- `validation_verdict`
- `progress_verdict`
- `progress_kind`
- `blockers`
- `qualitative_review`
- `code_structure_audit`
- `validation_set`
- `task_pack_id`
- `task_pack_item_id`
- `blocker_signature`
- `semantic_signature`
- `goal_distance_gate`
- `input_delta_gate`
- `supplied_input_delta_gate`
- `count_key_hygiene_gate`
- `failure_surface_stage_gate`
- `diagnostics_unavailable_gate`
- `instrumentation_exercise_gate`
- `instrumentation_first_fire_gate`
- `acceptance_encoding_gate`
- `acceptance_scenario_gate`
- `command_provenance_gate`
- `command_argv`
- `command_provenance_missing`
- `long_run_branch`
- `long_run_role`
- `event_kind`
- `run_id`
- `owner_task_id`
- `launch_cycle_id`
- `output_dir`
- `expected_completion_signal`
- `expected_completion_artifacts`
- `remaining_validation`
- `blocker_actionability_gate`
- `blocker_opacity`
- `stochastic_feasibility_gate`
- `runtime_config_echo`
- `run_disposition`
- `execution_starvation`
- `verification_source_separation_gate`
- `envelope_thaw_item_required`
- `envelope_thaw_item`
- `goal_axis_completeness_gate`
- `residual_gap_cost_policy`
- `expectation_lineage_gate`
- `expectation_anchor`
- `designated_baseline`
- `expectation_anchor_missing`
- `expectation_lineage_stale`
- `comparison_parity_gate`
- `parity_axes`
- `parity_axis_status`
- `parity_unverified`
- `adoption_axis_gate`
- `adoption_axis_classification`
- `required_output_classes`
- `majority_vote_adoption`
- `provisional_adoption`
- `measured_but_disqualified`
- `resolution_downgrade_gate`
- `required_evidence_resolution`
- `observed_evidence_resolution`
- `resolution_downgrade`
- `surrogate_resolution_basis`
- `report_key_integrity_gate`
- `report_key_divergence`
- `provider_reattempt_gate`
- `command_surface_budget`
- `anti_loop_progress_gate`
- `terminal_blocker`
- `used_advice`
- `authority_policy`
- `authority_policy_source`
- `created_at`

Use `context`, `ledger_init`, `authority`, `acceptance`, `route_plan`, `validation_set_plan`, `governance`, `result_contract`, `ledger_append`, `code_structure_audit`, `run`, `qualitative_review`, `loopback_audit`, `validation_set_build`, `schema_pre_derive`, `visible_increment`, `derive`, `schema_post_derive`, `index`, `validate`, `issue`, `commit`, `dashboard`, `report`, and `closeout_commit` as canonical step names.

Ledger append calls must provide a non-empty canonical `step`. Noncanonical steps require an explicit helper flag and must be treated as malformed/noncanonical evidence, not as normal dashboard stages. If a raw subskill result JSON is passed to the ledger writer, the JSON must already contain the top-level canonical `step` or the append command must overlay `--step <canonical-step>`.

Ledger `status` is a workflow-stage lifecycle status, not the owning subskill's raw result status. Use `complete` for a stage whose owning skill produced successful completion evidence. Keep result statuses such as run `success`, validation `passed`, or commit-specific statuses in the subskill result packet or in a separate field such as `source_status`/`result_status`. The ledger writer normalizes incoming stage `success` or `succeeded` to `complete` and preserves the original in `source_status`; transition validators should stay strict on canonical lifecycle statuses.

When an event references an artifact path already recorded with the same SHA-256, the ledger writer should emit `artifact_refs[].unchanged_ref: {path, sha256}` and top-level `unchanged_refs`. Downstream profile snapshots use `unchanged_ref_count` to avoid counting repeated packet bodies as fresh fixed cost.

## Result Contracts

Use `$validate-subskill-result-contract` or `scripts/result_contract.py` before advancing major stages.

- Default mode is `warn`.
- Use `block` mode for final report fields, running execution details, issue closure, candidate deletion, or commit creation gates.
- Required fields vary by target but generally include `task_id`, verdicts, changed files, blockers, evidence paths, commit status, and skipped/pending reasons.
- Result contracts also check ledger-envelope readiness for direct append: the top-level `step` should match the target. This is a warning in normal `warn` mode because a coordinator may instead pass `--step` at append time.
- The `qualitative_review` target must include `task_id`, `review_agent_count`, `reviewer_routing`, `review_status`, `quality_verdict`, `reviewed_artifacts`, `direct_read_scope`, `qualitative_findings`, `direction_recommendations`, `blocker_taxonomy_delta`, `no_overclaim_flags`, and `evidence_paths`; exactly one read-only reviewer agent must be reported. Do not satisfy this contract by naming the main coordinator as the reviewer. When reviewer delegation is unavailable, use `review_status: blocked|partial|not_applicable` with `reviewer_delegation_unavailable_reason` instead of `complete`. When `goal_axis_map` is supplied and any active measurable goal has zero mapped axes, the target must carry `goal_axis_completeness_gate`, `unobserved_goal_axes`, or `pass_with_unobserved_axes` and must not report that review as an acceptable pass for those goals.
- The `qualitative_review` target must carry the output-delta handoff shape with `output_delta_status`, `changed_vs_previous`, `semantic_progress`, `produced_domain_delta`, `metadata_only`, `effective_progress_kind`, and `progress_cap`, using explicit false/not-applicable/blocked values rather than omitting fields. When durable evidence is written, include `.task/quality_review/<cycle-id>-direct-output-quality-review.{md,json}` in `evidence_paths`.
- The `loopback_audit` target must include `cycle_id`, `family_key`, `changed_vs_previous`, `semantic_progress`, `same_family_micro_hardening_count`, `recommended_disposition`, `hard_stop_required`, `evidence_class`, and `evidence_paths`. When applicable, it must preserve `pass_with_coupled_verifier`, `coupled_verifier_gate`, `evidence_provenance_gate`, `attested_only_movement`, `primary_metric_gate`, `c4_user_escalation_backstop_required`, count-key hygiene fields, `failure_surface_stage_gate`, `same_input_contract_gate`, `diagnostics_unavailable_gate`, `instrumentation_exercise_gate`, `instrumentation_first_fire_gate`, `acceptance_scenario_gate`, `command_provenance_gate`, `blocker_actionability_gate`, `stochastic_feasibility_gate`, `verification_source_separation_gate`, `envelope_thaw_item_required`, `verifier_surface_hardening_gate`, `run_disposition`, `candidate_degraded`, `runtime_config_echo`, required gate-hook completeness, goal-axis completeness fields, residual value-per-cycle-cost fields, expectation lineage fields, comparison parity fields, adoption-axis fields, evidence-resolution downgrade fields, and report-key integrity fields.
- The `code_structure_audit` target must include `task_id`, `audit_status`, `changed_files_scanned`, `oversize_files`, `thresholds`, `responsibility_clusters`, `semantic_structure_metrics`, `semantic_structure_findings`, `convention_conformance`, `moduleization_required`, `suggested_module_root`, `responsibility_split_plan`, `semantic_refactor_plan`, and `evidence_paths`. Use `audit_status: pass|warn|refactor_required|blocked|not_applicable`. `moduleization_required=true` requires a non-empty `responsibility_split_plan` or a concrete existing-debt exemption. This target must not include raw source bodies.
- The `validation_set_plan` target must include `task_id`, `validation_set_need`, `task_family`, `oracle_strategy`, `split_strategy`, and `evidence_paths` when applicable.
- The `validation_set_build` target must include `task_id`, `validation_set_id`, `validation_set_status`, `quality_tier`, `not_gold`, `item_count`, `oracle_manifest_path`, `split_manifest_path`, `leakage_report_path`, `validation_set_root_path`, and `evidence_paths`. Block unsupported `quality_tier: gold`, raw body persistence, source-class promotion, and sealed holdout label exposure.
- The `derive` target must include `completed_task_id`, `selected_task_source`, `loop_breaker_disposition`, `progress_kind`, `semantic_signature`, and `evidence_paths`. For non-terminal derivation, include `next_task_id`. When an active task pack exists, include `task_pack_status`; when `selected_task_source: task_pack`, include `task_pack_path` and `task_pack_item_id` or `promoted_item_id`; when derivation is terminal, include `terminal_blocker` with `semantic_signature` when known.
- `derive` results must not route stale `expectation_lineage_stale`, `parity_unverified`, failed adoption gating axes, repeated `resolution_downgrade`, or `report_key_divergence` into ordinary goal-productive work. Select the matching rebaseline, parity-axis, adoption-axis, resolution restoration/contract revision, report repair, terminal, or user-escalation task kind.
- `derive` results must treat `new_input_kinds` as a hint only. A positive input delta requires `has_supplied_input_delta=true`, a non-empty `supplied_input_artifact_paths` entry, or `produced_domain_delta=true` backed by `changed_vs_previous=true` and `semantic_progress=true`.
- If `provider_mitigation_required=true`, the `derive` result must not terminal-seal provider failure while required mitigations remain missing. If `provider_reattempt_required=true`, it must select bounded provider retry/probe work and record `provider_reattempt_disposition`; terminal/provider-family sealing is blocked until that retry/probe/mitigation evidence exists or the gate no longer applies.
- If `detect_progress_loop status=block`, the `derive` result must select `progress_kind: goal_productive` or record terminal blocker state with dual-track attempt evidence.
- If `command_surface_budget.consolidation_candidate_required=true`, the `derive` result must record `consolidation_candidate_registered=true`, select consolidation work, select goal-productive work, or record terminal state.
- Use `progress_kind: goal_productive` only when the selected task is expected to produce goal-relevant output, quality evidence, source-backed validation, or another non-sidecar artifact that reduces goal distance. Use `progress_kind: governance_only` for workflow, metadata, reconciliation, or sidecar-only tasks even when `progress_verdict` may later pass validation.
- Use `effective_progress_kind: governance_only` when output-delta review reports `produced_domain_delta: false` or `metadata_only: true`. A self-reported `progress_kind: goal_productive` is invalid when the output-delta gate proves the work is metadata-only and no independent validated positive evidence is recorded.
- `goal_productive` is invalid when it relies on `pass_with_coupled_verifier=true`, `attested_only_movement=true`, or producer-attested metric fields without independent recalculation.
- `goal_productive` is invalid when it relies on `pass_with_unobserved_axes=true`, generation-dependent raw family keys, terminal-classification/failure-stage contradiction, same-input contract mismatch, unresolved `instrumentation_supply_required`, unresolved `instrumentation_exercise_required`, non-disjoint independent verification inputs, missing `envelope_thaw_item` for frozen-envelope reachability, stale expectation lineage, parity-unverified comparison/adoption, unclassified majority-vote adoption, failed gating axes, downgraded high-resolution evidence, duplicate divergent report keys, acceptance-required gate hooks that are absent/not_evaluated, guard/report-only `verifier_surface_hardening` after the detection cap, or below-policy residual value per cycle cost without residual descope plus the next rung or a higher value case.
- Terminal or sealed blocker-family derivation should include `root_cause_attempted_for_family: true`, or an explicit rationale that root-cause repair is impossible, unauthorized, or unsafe.
- Preserve both `blocker_signature` and `semantic_signature`: `blocker_signature` remains compatibility evidence, while `semantic_signature` removes volatile target-surface/run suffixes and drives repeated-family loop breakers.
- The `report` target must preserve task-pack promotion provenance when it references `.task/task_pack/` evidence or the next task was promoted from a pack: include `task_pack_status`, `task_pack_path`, and `task_pack_item_id` or `promoted_item_id`. If duplicate terminal report keys carry divergent values, preserve `report_key_divergence` with duplicate paths and values and block pass/close consumption until repaired. If duplicate terminal keys have matching values, record warn-only schema debt without blocking consumption.
- Commit targets must include `commit_role`: use `implementation` for the validation/issue-gated change set and `closeout` for report/dashboard/ledger/advice artifacts. Created commits must include `commit_hash` and `commit_subject`; skipped, blocked, or failed commits must include `commit_skipped_reason`.
- The `validate` target must preserve Part G/H/I/J/K gates when supplied: `count_key_hygiene_gate`, `failure_surface_stage_gate`, `same_input_contract_gate`, `diagnostics_unavailable_gate`, `instrumentation_exercise_gate`, `instrumentation_first_fire_gate`, `acceptance_scenario_gate`, `command_provenance_gate`, `blocker_actionability_gate`, `stochastic_feasibility_gate`, `acceptance_encoding_gate`, `verification_source_separation_gate`, `envelope_thaw_item_required`, `verifier_surface_hardening_gate`, `run_disposition`, `runtime_config_echo`, `goal_axis_completeness_gate`, `residual_gap_marginality_gate` or `residual_gap_cost_policy`, `expectation_lineage_gate`, `comparison_parity_gate`, `adoption_axis_gate`, `resolution_downgrade_gate`, `report_key_integrity_gate`, and required gate-hook fields. `complete` or `advanced` is invalid when these gates show generation-key family reset, contradictory terminal classification, same-input mismatch, unresolved instrumentation supply/exercise, double-counted first-fire credit, uncovered/inverted scenario coverage, missing command provenance for comparison/baseline claims, repeated opaque blockers, stochastic infeasible contracts, live-run acceptance satisfied only by derived artifacts, non-disjoint independent verification, missing thaw item, unobserved measurable axes, stale expectation lineage, parity-unverified comparison/adoption, missing adoption-axis classification, failed gating axes, downgraded high-resolution evidence, duplicate divergent report keys, missing required hooks, guard-stacking cap exhaustion, unsafe promotion of `candidate_degraded`, or below-policy residual value per cycle cost without explicit residual handling.
- When active `.agent_advice/active/` exists, governance, validation-set planning/building, derivation, and validation result contracts must include `used_advice` or an explicit advice disposition rationale such as `advice_deferred_reason`, `advice_rejected_reason`, `advice_not_applicable_reason`, or `advice_handling_rationale`.

## Visible Increment

`$record-visible-increment` writes:

- `.task/delta/<cycle-id>-visible-delta.md`
- `.task/delta/<cycle-id>-visible-delta.json`

The JSON must include `not_validation_evidence: true`. A visible increment can explain user-visible changes, but it cannot satisfy tests, validation, issue closure, or completion gates.

## Validation Scope

Validation scope artifacts record:

- `validation_profile`: `current_only`, `affected_chain`, or `full_chain`.
- `validation_set_profile`: `none`, `plan`, `build`, `refresh`, `consume`, or `seal`.
- `changed_surfaces`
- `changed_files`
- `required_commands`
- `reused_prerequisites`
- `escalation_reason`

Use `full_chain` only for live dispatch, readiness promotion, issue closure, shared validator/runtime changes, high-risk contract changes, or explicit user request.

## Evidence Cache

Evidence cache records live in `.task/evidence_cache/index.jsonl` by default. The cache may return only:

- `reuse`
- `fresh_required`
- `stale`
- `unsafe_to_reuse`

`reuse` is a candidate classification only. The owning validation or run skill still decides whether cached evidence is acceptable. Preserve failed, partial, and running records; do not overwrite them.

## Dashboard And Profile Snapshots

Dashboard and efficiency-profile artifacts are point-in-time renders over `stage.jsonl`. They must include or preserve the ledger `event_count` they were rendered from. Profile snapshots should also preserve `unchanged_ref_count` and `cycle_cost_basis` when available so duplicate unchanged packets do not inflate fixed-cost accounting. If a later `closeout_commit` event updates `stage.jsonl` or `current_stage.json`, the earlier dashboard/profile are pre-closeout snapshots; either regenerate them after the final append or state that snapshot boundary in the user-facing summary.

## Running Execution

A `running` result is valid in-progress evidence only when it includes:

- PID, session ID, or job ID.
- Log path.
- Startup or heartbeat evidence.
- Monitor command.
- Stop command.
- Remaining validation.

Do not convert `running` into `success`, `passed`, or `complete` unless the task explicitly defines startup/heartbeat evidence as sufficient.

For long-running branches, keep all lifecycle events on canonical `step: run` and distinguish them with:

- `event_kind`: `long_run_launch`, `long_run_monitor`, `long_run_harvest`, or `long_run_finalize`.
- `long_run_role`: `launch`, `monitor`, `harvest`, or `finalize`.
- Required handoff fields: `run_id`, `owner_task_id`, `launch_cycle_id`, `command_argv`, `workdir`, `output_dir`, `log_path`, `startup_or_heartbeat_evidence`, `monitor_command`, `stop_command`, `remaining_validation`, `expected_completion_signal`, and `expected_completion_artifacts`.

Use `completed_pending_validation` only when expected completion artifacts are present but harvest validation has not yet consumed them. It is not `success`, `passed`, `advanced`, or `complete_verified`.
