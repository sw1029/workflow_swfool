# Workflow Interface Contracts

This reference indexes the contact surfaces between `$orchestrate-task-cycle`, its helper scripts, and the owning skills it calls. It is skill-internal operating guidance, not workspace goal truth.

## Contents

- [Ownership Model](#ownership-model)
- [Cross-Skill Handoffs](#cross-skill-handoffs)
- [Core Packet Contracts](#core-packet-contracts)
- [Helper Script Surfaces](#helper-script-surfaces)
- [Fail-Closed Consumer Rules](#fail-closed-consumer-rules)

## Ownership Model

The orchestrator coordinates packets and ordering. It does not own implementation edits, final validation, issue lifecycle decisions, schema authority, Git staging, or subskill-internal verdicts.

Use these ownership rules:

- `$task-md-agent-governance` owns implementation changes and post-implementation governance evidence.
- `$run-task-code-and-log` owns execution, durable run logging, running-state metadata, failure autopsy, and `gate_satisfiability` run records.
- `$review-cycle-output-quality` owns direct qualitative output review with exactly one read-only reviewer agent.
- `$audit-cycle-loopback` owns `anti_loop_progress_gate` production and family progress registry updates.
- `$build-validation-set-with-agents` owns reusable validation-set plan/build/refresh/consume evidence under `.validation/` and `.task/validation_set/`.
- `$manage-schema-contracts` owns `.schema/` and `.contract/` refresh/reconciliation.
- `$derive-improvement-task` owns archiving `task.md`, writing the next `task.md`, task-pack mutation decisions, terminal blocker derivation, and next-task selection.
- `$manage-task-state-index` owns task/index scan, audit, link repair, and ID lifecycle consistency.
- `$validate-task-completion` owns completion and progress verdicts.
- `$manage-implementation-issues` owns issue lifecycle updates.
- `$repo-change-commit` owns Git classification, staging, commit readiness, and commit creation.

## Cross-Skill Handoffs

| Surface | Producer | Consumers | Required handoff |
| --- | --- | --- | --- |
| Authority policy | `$manage-agent-authority` | Governance, derive, validation, report | Policy source, effective permissions, external/API posture, strictness, escalation posture. |
| Active advice packet | `$manage-external-advice` or orchestrator context | Governance, validation-set, review, derive, validation, report, commit | Advice ID/path, summary, actionable directives, application gates, raw-direct-reference requirement, disposition or explicit non-use rationale. |
| Acceptance packet | `$normalize-acceptance-and-demo` | Governance, validation-scope, run planning, loopback, derive, validation | Acceptance criteria, non-goals, demo surfaces, validation commands, forbidden shortcuts, optional `acceptance_envelope_contract` from adapter `min_envelope_for`, optional `acceptance_verifier_contract` from adapter target-to-verifier mapping, required gate-hook completeness for gates named by measurable acceptance, frozen-envelope reachability and `envelope_thaw_item`/`envelope_thaw_item_required` when supplied, and residual-gap value/cycle-cost comparison inputs when supplied. |
| Repo adapter packet | Orchestrator scan or `scripts/render_adapter_packet.py` | Validation-set, governance, run, review, loopback, schema, derive, validation | Adapter ID/path/status, consumed phase packet, loaded references, optional `code_convention_contract`, non-GT/authority limits, validation status. |
| Validation-set packet | `$build-validation-set-with-agents` | Governance, schema, derive, index, validation, report | Need/status, quality tier, `not_gold`, item/label/oracle counts, source-class distribution, oracle/split/leakage/root paths, blocked/candidate-only reasons. |
| Governance result | `$task-md-agent-governance` | Result contract, ledger, code audit, run, schema, validation | Task ID, changed files, task_miss, used GT/advice, implementation summary, validation profile, blockers. |
| Code-structure audit packet | `scripts/code_structure_audit.py` | Run, derive, validation, issue, report | Scanned changed files, oversize files, responsibility clusters, semantic structure metrics/findings, convention conformance, moduleization requirement, split plan, semantic-refactor plan, exemptions, evidence paths. |
| Run result | `$run-task-code-and-log` | Review, loopback, validation-set, schema, derive, index, validation, issue, report | Status, command, exit code, output/artifact paths, running metadata, log path, shortcomings, `failure_autopsy` including stage ladder, `last_successful_stage`, `failure_surface_stage`, scalar diagnostics or `diagnostics_unavailable`, `gate_satisfiability`, scalar `gate_selfcheck`, and any producer progress labels only as `observed_producer_claim`. |
| Qualitative review packet | `$review-cycle-output-quality` | Loopback, validation-set, schema, derive, validation, report | `review_agent_count`, reviewed artifacts, quality verdict, findings, progress cap, output-delta fields, goal-axis completeness fields, no-overclaim flags, evidence paths. |
| Anti-loop progress gate | `$audit-cycle-loopback` | Derive, validation, dashboard, report | Family/root keys, semantic signature, progress booleans, terminal outcome fields, generation-independent count-key fields, failure-surface stage gate, same-input contract gate, diagnostics-unavailable/instrumentation gate, verification source separation gate, frozen-envelope thaw gate, quality vector, effective dispositions, hard-stop state, findings, evidence paths. |
| Loop-breaker packet | `scripts/detect_progress_loop.py` plus orchestrator synthesis | Derive, task-pack, validation, report | Blocker/root/semantic signatures, root-axis counts, terminal quiescence/escalation gates, supplied-input delta, provider retry, command surface, sealed family, zero-candidate state. |
| Task-pack packet | `scripts/task_pack_queue.py` and `$derive-improvement-task` | Derive, index, validation, report, commit | Pack ID/path/status, current item, mutation plan, Markdown render, terminal blocker state, selected disposition, and `scope_fidelity` for measurable directive-derived items. |
| Validation result | `$validate-task-completion` | Issue, commit, dashboard, report | `validation_verdict`, `progress_verdict`, `progress_axes`, blockers, evidence paths, advice disposition, task-pack preservation, `acceptance_provenance_gate`, `acceptance_verifier_gate`, `failure_surface_stage_gate`, `diagnostics_unavailable_gate`, `verification_source_separation_gate`, `envelope_thaw` fields, `goal_axis_completeness_gate`, `residual_gap_marginality_gate`, `structure_metrics_gate`, and behavior-change live evidence gate when applicable. |
| Issue packet | `$manage-implementation-issues` | Commit, dashboard, report | Created/updated/closed issue IDs, blocker links, resolution evidence, skipped reason. |
| Commit packet | `$repo-change-commit` | Dashboard, report, closeout | `commit_role`, created/skipped/blocked status, commit hash/subject when created, skipped reason when not. |

## Core Packet Contracts

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

Do not persist raw prompts, provider bodies, generated bodies, stdout/stderr bodies, source bodies, credentials, tokens, or secrets in the autopsy packet.

When an execution stage ladder is available, `last_successful_stage` and `failure_surface_stage` are required for downstream H2 counting. If safe post-failure scalar/enum diagnostics cannot be collected, the packet must say `diagnostics_unavailable=true`; no-body and redaction policy still allows scalar diagnostics such as stage, enum status, count, HTTP code, and exception class.

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
- `scope_fidelity.narrowed`, `narrow_reason`, and `residual_item_id`: explicit descope record and open residual scope.
- `acceptance_provenance_gate.target_met`: validation result comparing actual achievement to the original target.
- `acceptance_provenance_gate.acceptance_diluted`: true when the item was closed against a weaker target.
- `acceptance_provenance_gate.explicit_descope_decision`: true only when a reason and residual item/link exist.

Consumers must not mark a measurable item consumed, applied, or complete when `acceptance_diluted=true`. A narrowed item may be useful progress, but it remains `partial` unless the original target is met or the residual target stays open under an explicit descope decision.

When adapter `residual_gap_policy` is available, consumers should preserve residual-gap fields supplied by normalize/derive such as `residual_gap_ratio`, `residual_gap_policy`, `marginal_repair`, and `descope_with_residual`. A residual gap below the adapter threshold should default to explicit descope with residual scope plus the next capability-ladder rung rather than another same-gap repair.

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
| `cycle_ledger.py` | `init`, `append`, `render`, `current`; stage JSON or explicit `--step` | `.task/cycle/<cycle-id>/stage.jsonl`, `current_stage.json`, packets, dashboard support | Dashboard, report, transition checks |
| `render_subskill_packet.py` | `--target <phase>`, context/stage evidence | Markdown or JSON packet with routing, required inputs/outputs, GT/advice separation | Every owning subskill |
| `validate_cycle_transition.py` | `--transition <name>`, context/status evidence | Transition `pass|warn|block` findings | Orchestrator before major phases |
| `result_contract.py` | `--target <target>`, `--mode warn|block`, result JSON | Contract findings and ledger-envelope readiness | Orchestrator before advancing stages |
| `code_structure_audit.py` | `--root`, changed-file list or input JSON, optional `--convention-json` | Scalar audit packet with size, responsibility, semantic structure, and convention-conformance fields; no source bodies; no patches | Run, derive, validation, report |
| `detect_gt_constraint_conflict.py` | `--root`, task/GT/behavior evidence | GT/task conflict packet | Derive |
| `detect_progress_loop.py` | `--root`, optional registry writes | Loop-breaker packet, feature-symbol gate, terminal gates, sealed-family evidence | Derive, task-pack, validation, report |
| `output_delta_contract.py` | `--root`, output paths/contracts when present | Output-delta packet or not-applicable reason | Review, loopback, derive, validation |
| `task_pack_queue.py` | `status`, `validate`, `render`, `next`, `apply-mutation`, `mark-consumed` | `.task/task_pack/*.json` canonical queue and Markdown render when mutating through derive-approved plan; validates `scope_fidelity` and measurable acceptance provenance when present | Derive, index, validation, report |
| `visible_increment.py` | Completed evidence and cycle ID | `.task/delta/<cycle-id>-visible-delta.{md,json}` with `not_validation_evidence: true` | Report only; not validation |
| `render_cycle_dashboard.py` | Cycle ledger evidence | Korean `dashboard.md` snapshot | Report, closeout |
| `profile_cycle_efficiency.py` | Cycle ledger evidence | Efficiency profile snapshot | Report |
| `monitor_running_execution.py` | Running process/log metadata | Running-state verification without success promotion | Validation, report |
| `assemble_cycle_report.py` | Context, validation, progress, commit JSON | Korean report draft/check in required field order | Final report |

## Fail-Closed Consumer Rules

- Treat missing or malformed packet evidence as `conservative_hold`, `not_applicable`, `partial`, or `blocked`; never silently upgrade it to success.
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
