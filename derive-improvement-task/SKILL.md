---
name: derive-improvement-task
description: "Derive the next actionable `task.md` or bounded task-pack transaction from agent-based repository analysis with fixed `reasoning_effort: xhigh` for improvement, issue-fit, task_miss, synthesis, schema-planning, and ID-consistency agents. Use when Codex should combine `.agent_goal` alignment, `$manage-agent-authority`, active `.agent_advice` non-GT direction, `.issue`, `.task/task_miss`, `.task/candidate_task`, semantic structure/convention evidence, and optional `.task/task_pack` queues; create an initial task when absent; create a bounded task pack when long-range ordering prevents myopic loops; promote one active task-pack item into `task.md`; archive the old task as `past_task`; write the new task with a top execution-environment section; retain candidates; update task packs for insert/reorder/skip/supersede/terminal blocker state; and delete applied candidates only after the real task is written."
---

# Derive Improvement Task

## Overview

Use this skill to turn current goal context, repository evidence, previous misses, and candidate ideas into the next concrete `task.md`.

When long-range ordering is needed, this skill may also create or update a task pack under `.task/task_pack/`. The pack is planning state only; the final executable output remains one active `task.md`. Treat pack updates as a transaction: choose exactly one `pack_disposition`, mutate the JSON queue with evidence, refresh the Markdown render, and promote at most one item into `task.md`.

The workflow is intentionally agent-heavy: use `$inspect-repo-with-agents` for critical goal/convention-alignment analysis, agent-based `.task/task_miss` analysis, one issue goal-fit agent from `$manage-implementation-issues`, three parallel improvement-analysis agents, one synthesis agent, and `$record-agent-work-log` to preserve the previous `task.md` as `past_task` before replacing it.

Use `$manage-task-state-index` for task, candidate, miss, past_task, log, audit, and validation IDs whenever possible. If no ID context exists, continue deriving the improvement task and report that indexing was skipped.

Use `.agent_goal/goal_schema_contract.md` and `.schema/` or `.contract/` contract context from `$manage-schema-contracts` when present. Schema, module, script, version, and causal compatibility contracts are planning evidence, not optional documentation, when the selected task can change interfaces or data artifacts.

Use `$manage-agent-authority` to resolve authority goal truth for task selection. Its result should describe the current agent's effective operating permissions and any narrower project-specific policy for API calls, external service use, direction freedom, strictness, implementation-first versus validation-first priority, output/artifact confirmation, quality review, conservative implementation, and escalation. If the file is absent, consume `authority_policy: default_current_agent_permissions`: current sandbox, approval, user/developer/system instructions, and no inferred extra API/network/destructive authority. This policy may constrain or rank task options, but it cannot override higher-priority instructions or grant missing capabilities.

Use `$manage-external-advice` when `.agent_advice/active/*.md` exists or the caller passes an advice packet. Active advice is non-GT planning evidence: it can steer task choice, design notes, schema planning, and validation expectations, but it must be listed as `used_advice`, kept out of `.agent_goal`, and rejected or deferred if it conflicts with GT, authority, current user instruction, or repository facts.

Use `.issue/` and GitHub issue mirrors from `$manage-implementation-issues` when present. Active issues are planning evidence only after a first-pass issue agent classifies whether each issue fits the goal.

Use `.task/task_pack/*.json` when present. The JSON queue is canonical; `.md` files beside it are user-language renders. Read [task-pack-workflow.md](../orchestrate-task-cycle/references/task-pack-workflow.md) when a caller supplies a task-pack packet or `.task/task_pack/` exists.

If `task.md` is absent, run this skill in initial-init mode: derive the first actionable `task.md` from goal context, repository evidence, issues, task_miss, and candidate_task without requiring or archiving a previous task.

## Selection Efficiency Policy

Keep task derivation conservative, but avoid selecting another task whose main effect is only to add one more small no-live check.

- Prefer blocker-state-transition tasks: select work that moves a blocker from one meaningful state to the next, such as `missing evidence -> intake path proven`, `intake path proven -> bounded preflight`, `bounded preflight -> source-backed validation`, or `schema drift -> compatibility proven`.
- Merge adjacent no-live micro-contracts when they share the same target script/module, issue blocker, prerequisite chain, promotion boundary, and validation surface. A merged task may still be narrow, but it should close a coherent boundary as one cycle.
- Classify recent completed tasks by progress, not only validation. Use `advanced` when the task unlocked a new execution or goal state, `safety_only` when it only proved fail-closed/no-live safety, `no_progress` when it added no meaningful blocker movement, and `regressed` when it weakened or broke a required state.
- If the last two completed tasks are `safety_only` and the same blocker remains open, the selected next task must supply or validate the missing evidence path, perform a bounded source-backed run/preflight, consolidate remaining no-live boundaries into one batch task, or explicitly stop with a blocker explaining the missing external input or authorization.
- If no active task pack exists and a known 2-5 step sequence would prevent repeated myopic derivation, create a bounded pack and promote only the first safe item into `task.md`.
- If an active task pack exists, consider the next pack item before standalone candidates. Promote it unless current evidence requires insertion, reordering, skipping/excluding, superseding, standalone bypass, or terminal blocking.
- If a candidate or pack item comes from a measurable user/advice/issue directive, preserve the original target through `scope_fidelity` and copied acceptance. Do not make the item `goal_productive` by replacing the original target with a weaker pilot/plan/slice criterion.
- If a measurable directive must be narrowed for one cycle, set `scope_fidelity.narrowed=true`, record `narrow_reason`, and create an open residual item before the narrowed item can be promoted or consumed.
- If normalized acceptance or a caller packet provides `acceptance_envelope_contract`, do not select a task slice whose planned execution envelope is below the adapter-owned `envelope_floor` as `goal_productive`. Select envelope expansion, constraint relaxation, explicit descope with residual scope, terminal-block, or user escalation according to authority; do not lower the measurable target to fit the slice.
- If recent evidence repeats the same normalized blocker signature, do not select another narrowing or handoff task unless a new input kind, authority change, external-state change, or safe pack item changes the blocker state.
- If recent evidence repeats the same suffix-normalized `root_key` or `semantic_signature`, treat it as the same blocker family even when target-surface, run directory, timestamp, `after-*`, date, sequence, or `vN` suffixes changed. Do not select another non-terminal task in a sealed semantic family without a supplied input artifact/domain delta, authority change, or external-state change.
- If the caller supplies `feature_symbol_gate`, use it as the observed-over-declared loop signal. Treat repeated symbols with `observed_output_class` of `metadata_only` or `terminal_record` as the same workflow attempt even when labels, task names, run directories, signatures, or version suffixes changed.
- If `feature_symbol_gate.hard_stop_required=true`, select goal-productive work, consolidation, terminal-blocked, or user escalation. Do not satisfy this gate with another metadata-only handoff, renamed command family, or task that relies only on self-declared `produced_domain_delta`.
- If the caller supplies an output-delta gate, use `effective_progress_kind` instead of a self-reported `progress_kind`. A task is `goal_productive` only when repository-declared output layer paths changed and `semantic_progress=true`, validated positive evidence changed, or another non-sidecar artifact reduces goal distance. Metadata-only, workflow-only, reconciliation-only, sidecar-only work, and non-empty counts without semantic change remain `governance_only` even when validation passes.
- If run or producer artifacts contain `observed_producer_claim`, treat it as trace-only self-report. Do not use producer-declared `goal_productive`, `advanced`, `effective_progress_kind`, or `produced_domain_delta` as the selected task's progress truth source unless adapter-recomputed or strict output-delta evidence independently supports it.
- When an output-delta gate includes `observed_output_class`, prefer the observed value over declared fields. Only `observed_output_class: node_edge_delta` resets no-delta loop counters.
- For evidence-family tasks with `positive_input_delta_required: true`, require at least one newly introduced input kind and a supplied positive input delta before claiming progress. The supplied delta must be a non-empty artifact path in `supplied_input_artifact_paths` or `produced_domain_delta=true`.
- For metadata-only loop evidence, require a positive output delta or supplied input artifact before treating the next evidence-family task as progress. New wording, a new timestamp, a renamed input kind, or another metric-only cohort is insufficient.
- If the caller supplies `qualitative_review_packet.progress_cap=governance_only` because semantic output is not ready, placeholder events were found, or surface entities are suspected, preserve that cap unless independent strict output-delta evidence proves changed-and-semantic primary-output progress.
- If the caller supplies `gt_constraint_conflict_packet.status=block`, do not select a task that inherits the contradictory prohibition. Select a task that resolves the task-level contradiction, set `resolves_gt_constraint_conflict=true` or `selected_task_kind: gt_constraint_conflict_resolution`, or emit `selected_task_source: terminal_blocked` with the required user decision.
- If run evidence, failure autopsy, or the loop-breaker packet includes `classification: self_inflicted_gate_defect`, do not select another same-gate environment recheck. Select a gate-contract/code correction task that makes the gate satisfiable, switch to the recorded `alternative_evidence_source` when one exists, or emit `selected_task_source: user_escalation` with `required_missing_input.kind: gate_contract_fix_approval`.
- If `anti_loop_progress_gate.repo_owned_source_roots_status=provided` and a root-cause ledger entry has `repo_owned_source_refs` or `self_report_rejected_fields`, treat that entry as provenance-hardened actionability. Do not terminal-block merely because the same producer reported `local=false`, `in_scope=false`, or `actionable=false`.
- If `failure_autopsy.gate_selfcheck.status=warn_missing_repo_owned_confirmation`, use it as a warning only. Require loopback/actionability provenance, adapter confirmation, or an explicit caller flag before selecting a self-inflicted gate-fix task from that self-check alone.
- When the caller supplies `goal_distance_gate.requires_goal_productive_next`, select `progress_kind: goal_productive` work or emit `selected_task_source: terminal_blocked`. Do not satisfy this gate with workflow sidecars, hash renames, or another governance-only reconciliation task.
- When the caller supplies `root_axis_gate.autonomous_retarget_disabled=true`, select `progress_kind: goal_productive` work or emit `selected_task_source: terminal_blocked`. A new `semantic_signature`, new wording, new version suffix, or provider-neutral retarget on the same `root_axis`/`root_key` is not enough.
- When the caller supplies `effective_allowed_dispositions`, choose the selected task disposition from that list only. Treat gate `allowed_dispositions` as an intersection already computed by loopback/orchestration, not a menu to union. If `disposition_intersection_basis` includes `allowed_task_kinds`, emit `selected_task_kind` and keep `goal_productive` inside that set; a matching label with a different task kind is `governance_only` or blocked. If the only effective options are `terminal_blocked` and `user_escalation`, do not write another standalone consolidation task.
- When the caller supplies `consolidation_streak >= consolidation_streak_cap`, do not select another consolidation task unless independent strict changed-and-semantic primary-output evidence resets the streak.
- Classify the selected task as `progress_kind: goal_productive` or `progress_kind: governance_only`. After two governance-only cycles, select goal-productive work or terminal-block instead of deriving another narrowing/handoff task.
- After two metadata-only cycles, select `resume_primary_output`, bounded source-backed run/preflight, safe failure root-cause repair, or terminal-block. Do not derive another measurement-only task unless a repository output-delta contract reports `produced_domain_delta: true` or the task directly creates the missing primary output path.
- If `anti_loop_progress_gate.measurement_progress=true`, count it as governance-only instrumentation unless `measurement_progress_allowed=true`, `coverage_quality_delta_gate.quality_delta_pass=true`, `coverage_quality_delta_reconciliation_gate.status!=block`, and `substance_delta_gate.substance_delta_pass=true`. Do not use the exemption when `measurement_progress_streak_for_root_key > measurement_streak_cap`, `measurement_progress_streak_for_root_family > measurement_streak_cap`, when the check/oracle ID is already known, when validator disagreement, R-GCOV disagreement, or validator integrity blocks the packet, or when G-COV/G-SUBSTANCE fails.
- If `anti_loop_progress_gate.substance_delta_gate.status=missing` or `substance_delta_pass=false`, do not promote validator/oracle existence, scalar metrics, or capability-ladder observations as `goal_productive` unless strict changed-and-semantic primary-output evidence exists. Select substance-producing implementation/correction work, terminal-block with the missing adapter/output evidence, or user escalation.
- If `anti_loop_progress_gate.adapter_wiring_defect=true`, select `selected_task_kind: adapter_wiring_fix` or `adapter_load_fix` as the next goal-productive task before adapter creation, adapter strengthening, or another domain micro-repair. If authority or local context prevents the correction, emit `terminal_blocked` or `user_escalation` with `adapter_path`, `adapter_expected_path`, and evidence paths.
- If `anti_loop_progress_gate.adapter_mandate_required=true`, select adapter registration or adapter strengthening as the next goal-productive task before another domain micro-repair. If authority or local context prevents adapter work, emit `terminal_blocked` or `user_escalation` with `adapter_contract_unmet`, `adapter_missing_streak`, and evidence paths.
- If `anti_loop_progress_gate.cumulative_goal_distance_stalled=true`, first select `anti_loop_progress_gate.forced_selected_task.selected_task_kind` when `chain_stall_forced_retarget_gate` provides an actionable forced option. Otherwise select only `terminal_blocked` or `user_escalation` unless `adapter_mandate_required=true` is the preceding forced adapter task. If `untried_veto_overridden_by_chain_stall=true`, do not promote another distinct untried hypothesis merely because its label or terminal outcome is new.
- If `anti_loop_progress_gate.root_dominant_parameter_key` is present, treat distinct root-cause and stall evidence as keyed by collapsed root plus that parameter. Do not promote another untried repair merely because proximate labels, suffixes, target-surface wording, or rung names changed.
- If `anti_loop_progress_gate.primary_metric_gate.primary_metric_stalled=true` or `primary_metric_stalled=true`, apply the C4 forced-retarget rule even when blocker labels changed. If `c4_user_escalation_backstop_required=true` and no forced option is actionable, select `user_escalation` with exactly the missing input, authority, or evidence kind named.
- If `anti_loop_progress_gate.acceptance_unreachable_under_frozen_config=true`, select a constraint-relaxation task when authority permits it, or `user_escalation` when permission/input is required. Do not select another repair constrained inside the frozen envelope as `goal_productive`.
- If `anti_loop_progress_gate.oracle_metric_validity_gate.metric_goal_productive_excluded=true`, do not use the corresponding oracle/metric pass for measurement promotion, capability-ladder movement, or completion. Select metric/oracle correction, independent changed-and-semantic output production, terminal-block, or user escalation.
- If `anti_loop_progress_gate.blocker_mutation_kind=forward_mutation` but `terminal_outcome_changed=false` or `forward_mutation_vacuous=true`, do not promote the rung movement as `goal_productive`. Select the untried actionable root-cause repair if present, otherwise select output-producing correction work, terminal-block, or user escalation with the missing evidence named.
- If `anti_loop_progress_gate.vacuous_corrective_gate.surface_corrective_noop=true`, do not count corrective/backfill rows as output delta. Select a task that resolves the lane, changes the producer/corrector in place, or terminal/user-escalates with the unresolved condition.
- If `anti_loop_progress_gate.advice_freshness_gate.advice_metrics_stale=true`, do not rely on stale advice headline metrics. Refresh, defer, reject, or use the advice only with an explicit raw-review/current-evidence rationale.
- If `anti_loop_progress_gate.coverage_quality_delta_reconciliation_gate.status=block`, do not rely on a favorable G-COV source. Select a task that reconciles output-delta and loopback evidence, produces strict changed-and-semantic primary-output evidence, or terminal/user-escalates with the missing evidence.
- If `anti_loop_progress_gate.structure_metrics_gate.structure_consolidation_recommended=true`, Class C consolidation, `semantic_consolidation`, `reuse_extraction`, `coupling_reduction`, or module-boundary work is valid only when it reduces the reported structure burden or unlocks the next primary-output transition.
- If `code_structure_audit_packet.semantic_structure_findings`, `convention_conformance`, or `structure_metrics_gate` shows mechanical shards, version-suffix modules, global rebinding, duplicate definitions, excessive depth/fan-out, low reuse ratio, or max-LOC pressure, select structure work only with acceptance that measures real movement on those axes. Do not select file-count growth, renaming-only shuffles, or another mechanical split as goal-productive.
- If `anti_loop_progress_gate.validator_integrity_gate.status=block`, do not cite the validator pass as completion, semantic progress, or goal-productive evidence. Select correction work that fixes the validator/primary output, select terminal-blocked, or user-escalate with the missing evidence.
- If `anti_loop_progress_gate.requires_correction_or_terminal=true` or `detection_balance_gate.requires_correction_or_terminal=true`, do not select another detection-only task as `goal_productive`. Select producer/prompt/transform/resolution/provider/primary-output correction work, or emit terminal/user escalation.
- If `provider_scale_dispatch_gate.dispatch_required=true`, do not select another surface-only, contract, preflight, locator, or measurement task as `goal_productive`. Select bounded extraction/scale work if authority permits, or terminal/user-escalate with the precise missing authority/input.
- If the caller supplies `provider_reattempt_gate.provider_mitigation_required=true`, do not seal provider failure as terminal while required mitigations remain missing. If `provider_reattempt_required=true`, select a bounded provider retry/probe task and record `provider_reattempt_disposition`; if authority forbids the mitigation, terminal/user escalation must name the authority blocker instead of treating `timeout`, `transient`, `rate_limit`, `parse`, or `empty` as permanent provider unavailability.
- Do not seal a blocker family until at least one root-cause/autopsy repair task has been attempted for that family, unless the derive result records an explicit `root_cause_not_required_for_family` rationale grounded in authority, safety, or unavailable external state.
- Do not seal or terminal-block a blocker family when `untried_actionable_root_cause_exists=true`, unless `hypothesis_exhausted=true` or `untried_veto_overridden_by_chain_stall=true`. Promote the first untried local, bounded, provider-free, in-scope, authority-allowed hypothesis from `untried_root_cause_hypotheses` as the next `goal_productive` repair task only while the cumulative goal-distance chain has not stalled.
- Do not seal a blocker family while an authority-permitted productive alternative path remains unattempted. Record `authorized_alternative_path`, `authorized_alternative_path_exists`, `authorized_alternative_path_attempted`, `alternative_in_gt_allowed`, `gt_allowed_alternative_attempted`, `gt_allowed_alternative_evidence_paths`, and `authorized_alternative_source_gt_paths` before terminal blocking or sealing. Do not treat a fabricated or non-GT input class as an authorized alternative.
- If the caller supplies `detect_progress_loop status=block`, select `progress_kind: goal_productive` or emit `selected_task_source: terminal_blocked` with dual-track attempt evidence. Another governance-only handoff, contract, or sidecar task is invalid.
- If the caller supplies `command_surface_budget.consolidation_candidate_required=true` or `hard_gate=true`, register or select consolidation/refactor work unless strict changed-and-semantic primary-output evidence already justifies goal-productive work, or the selected result is terminal/user escalation. Do not add another version-suffixed command family to the over-budget surface merely by renaming it.
- Under command-surface budget pressure, distinguish blocked Class A changes (new `cmd_*`, `vNNN` wrapper, preflight, gate, locator, handoff, family rename, alternate route) from allowed Class B/C work. Class B is in-place expansion of the canonical extraction entrypoint with non-increasing command count; Class C reduces or retires command surface. Class B may be `goal_productive` when it directly creates primary-output progress.
- If `anti_loop_progress_gate.force_implementation_cycle=true`, Class B and Class C remain allowed even under command-surface pressure. Select an in-place implementation task for the next capability rung, a surface-reducing task that unlocks it, or terminal/user escalation with the concrete authority/input blocker. Class A remains blocked.
- If the caller supplies `anti_loop_progress_gate.same_family_micro_hardening_count>=3`, do not select another same-family `add_field`, `lineage`, `gap_report`, `relation_label_tweak`, scalar-contract, preflight-scalar, or renamed-command task as `goal_productive`. Select provider/semantic transition, consolidation, supplied-input/domain-delta work, or terminal/user escalation.
- If `anti_loop_progress_gate.blocker_mutation_kind=facet_rename`, treat it as lateral churn under the same root blocker family. If `anti_loop_progress_gate.blocker_mutation_kind=forward_mutation`, treat the blocker family as changed rather than repeated only when stricter gates are clear and `terminal_outcome_changed=true`; preserve no-overclaim boundaries and prefer the next capability-ladder rung over another handoff or measurement task. If `forward_mutation_vacuous=true`, route to untried root-cause repair or output-producing correction instead.
- If `terminal_escalation_gate.escalation_required=true`, do not write another `terminal_blocked`, recheck, closeout, dashboard, or handoff task. Emit `selected_task_source: user_escalation`, `forced_disposition: user_escalation`, `terminal_recheck_streak`, `required_missing_input_count: 1`, exactly one `required_missing_input.kind`, and a seal update or mutation plan for `.task/sealed_blocker_families.json`.
- If `goal_productive` remains effectively allowed but no concrete candidate exists, build one from the corpus-scale ladder: `M0_single_work_full_window`, `M1_same_work_reconstruction_measured`, `M2_three_work`, `M3_unseen_10`, then `M4_unseen_15`. A rung passes by G-COV quality/coverage delta or strict changed-and-semantic output-delta evidence, not by oracle existence alone. If all rungs are satisfied or the next rung is not authorized, user-escalate or terminal-block with the blocker named.
- Before writing `terminal_blocked`, check whether the next unsatisfied corpus-scale ladder rung is executable with current authority, local data, provider dependency `none` or `bounded`, and an allowed Class B/C command-surface path. If yes, terminal blocking is invalid; promote that rung as the selected task or a task-pack item.
- If the caller supplies `terminal_quiescence_gate.quiescence_required=true` and no untried actionable root-cause exists, do not create another domain retry, narrowing, handoff, dashboard, report, or recheck task for that same root. Write terminal handoff state with `commit_skipped_reason: terminal_quiescence` instead.
- If there are zero viable standalone candidates and no viable pack items, write terminal blocker state instead of inventing another narrowing task.
- Do not select a candidate merely because it is the next sequential version number. Prefer candidates that reduce the primary blocker, improve final-goal progress, or make a blocked transition possible.
- The generated `task.md` must include a `progress_target` and a validation profile in `## Execution Environment`: `current_only`, `affected_chain`, or `full_chain`. Use `full_chain` only for live dispatch, readiness promotion, issue closure, shared validator/runtime changes, or explicit user request.
- When `$optimize-task-slice` advisory evidence is supplied, treat it as non-authoritative classification input. It may recommend state-transition work, batched micro-contracts, evidence supply, bounded preflight, narrowing, or stopping with a blocker, but it must not replace this skill's fixed `xhigh` synthesis or final next-task selection.
- If `$optimize-task-slice` reports `narrowing_of_measurable_target=true`, require an explicit descope rationale and residual item in the derive result before selecting `narrow_current_only`.

## Agent Routing Policy

- When called from `$orchestrate-task-cycle`, include the canonical orchestration reference [workflow-routing.md](../orchestrate-task-cycle/references/workflow-routing.md) in the evidence packet, but keep this skill's fixed routing policy below.
- Treat improvement derivation as xhigh-reasoning work. When spawning or requesting goal/convention alignment, task_miss analysis, issue goal-fit, improvement-analysis, synthesis, candidate-prioritization, schema-contract planning, or ID-consistency agents, set `reasoning_effort: xhigh` whenever the subagent tooling exposes it.
- Do not downgrade these agents to `high`, `medium`, or inherited effort for speed. The selected next task controls downstream implementation direction, so the reasoning effort is fixed.
- If a called skill owns its own subagents, include the fixed `reasoning_effort: xhigh` requirement in that skill request.
- If the available delegation tool cannot enforce `reasoning_effort: xhigh`, include the requirement in the prompt and report the limitation in the outcome.
- If the available thread/agent budget cannot run the exact requested fanout, run the maximum available independent xhigh-capable lenses, keep synthesis evidence-separated, and record `degraded_agents: true` with the unavailable agents, covered lenses, missing lenses, and risk. Do not claim the exact agent policy was satisfied.

## Workflow

1. Load planning context.
   - Read `.agent_goal/final_goal.md`, `.agent_goal/conventions.md`, `.agent_goal/goal_architecture.md`, `.agent_goal/goal_theory.md`, and `.agent_goal/goal_schema_contract.md` when present.
   - Use `$manage-agent-authority` in `summarize` mode when `.agent_goal/agent_authority.md` exists. If absent and no caller supplied an authority summary, use `$manage-agent-authority` to return `authority_policy: default_current_agent_permissions` without writing.
   - Read existing `task.md` if present.
   - Extract any existing execution-environment section or command from the previous `task.md`; preserve its structure when it is still applicable.
   - If `task.md` is missing, set mode to `initial_init`; skip previous-task analysis, skip `past_task` archival, and derive the initial task from the remaining evidence.
   - Read `.issue/` implementation issue records and GitHub issue mirrors when present.
   - Read `.task/task_miss/` reports and `.task/candidate_task/` candidate files when present.
   - Read `.task/task_pack/*.json` and their `.md` renders when present. Validate the active pack with `$orchestrate-task-cycle` `scripts/task_pack_queue.py --root . status --format json` when available.
   - Read each pack item's `scope_fidelity` when present. Treat missing residual scope, missing original target, or consumed measurable items without `acceptance_provenance_gate.target_met=true` as task-pack blockers to address before ordinary promotion.
   - Read any caller-supplied `loop_breaker_packet`, including blocker signature repetition, `semantic_signature` repetition, sealed-family matches, goal-distance gate, governance-only streak, positive input delta gate with `has_supplied_input_delta` and `supplied_input_artifact_paths`, provider re-attempt gate, command-surface budget, terminal blocker recommendation, `terminal_escalation_gate`, and `terminal_recheck_streak`.
   - Read any caller-supplied `output_delta_packet`, `qualitative_review_packet`, `code_structure_audit_packet`, and `anti_loop_progress_gate`. Use `changed_vs_previous`, `semantic_progress`, semantic readiness/cap fields, provider/env behavior booleans, `previous_accepted_baseline`, `coverage_quality_delta_gate`, `coverage_quality_delta_reconciliation_gate`, `structure_metrics_gate`, `code_structure_audit_packet.semantic_structure_findings`, `code_structure_audit_packet.convention_conformance`, `provider_scale_dispatch_gate`, measurement-progress fields, blocker-mutation fields, adapter mandate fields, cumulative goal-distance fields, acceptance-envelope fields, reachability fields, oracle/metric validity fields, producer-claim downgrade fields, primary-metric C4 fields, and same-family micro-hardening counts as hard selection constraints, not optional commentary.
   - Read `effective_allowed_dispositions`, `disposition_intersection_basis`, `allowed_task_kinds`, `forced_selected_task`, `forced_selected_task_options`, `consolidation_streak`, `measurement_progress_allowed`, `measurement_streak`, `measurement_progress_streak_for_root_key`, `measurement_progress_streak_for_root_family`, `root_family_key`, `blocker_root_family`, `root_dominant_parameter_key`, `task_correction_class`, `detection_only_streak_for_root_family`, `requires_correction_or_terminal`, `validator_integrity_gate`, `blocker_mutation_kind`, `terminal_outcome_changed`, `forward_mutation_vacuous`, `forward_mutation_budget_remaining`, `adapter_wiring_defect`, `adapter_loaded`, `adapter_path`, `adapter_expected_path`, `adapter_mandate_required`, `adapter_contract_unmet`, `cumulative_goal_distance_stalled`, `primary_metric_gate`, `primary_metric_stalled`, `c4_user_escalation_backstop_required`, `untried_veto_overridden_by_chain_stall`, `acceptance_envelope_contract`, `envelope_below_floor`, `acceptance_unreachable_under_frozen_config`, `relaxation_or_escalation_required`, `oracle_metric_validity_gate`, `observed_producer_claim`, `split_brain_progress_claim`, `repo_owned_source_roots_status`, `root_cause_ledger_path`, `untried_actionable_root_cause_exists`, `untried_root_cause_hypotheses`, `force_implementation_cycle`, `authoritative_semantic_progress`, `terminal_escalation_gate`, `terminal_recheck_streak`, R-GCOV findings, and `validator_disagreement` findings when present. Treat them as hard selection constraints.
   - Read any caller-supplied `feature_symbol_gate`, including registry path, symbol counts, no-delta counts, observed output classes, terminal-history matches, and allowed dispositions.
   - Read any caller-supplied `gt_constraint_conflict_packet`. If it reports `status: block`, carry the exact conflicting actions into goal/convention alignment and synthesis as blocker-level evidence.
   - Read `.schema/index.md`, `.schema/causal_map.md`, `.schema/contracts.jsonl`, relevant `.schema/` contract files, and `.contract/` records when present.
   - Read `.agent_advice/active/*.md` or consume the caller's active advice packet when present. If direct intake is needed, use `$manage-external-advice` first; do not copy raw advice into `.agent_goal`.
   - Read `$optimize-task-slice` advisory output when the caller supplies it. Keep it advisory and separate from GT, authority, issue verdicts, and final synthesis authority.
   - If all `.agent_goal` files are absent, continue from repo evidence and note the goal-context gap; do not invent goal alignment.
   - Run `$manage-task-state-index` `scan` and deterministic `audit` when `.task/`, `.issue/`, `.agent_log/`, `.agent_goal/`, `.agent_advice/`, `.interview/`, `.schema/`, `.contract/`, or `task.md` exists. Use existing IDs in all agent evidence packages.

2. Analyze goal alignment with `$inspect-repo-with-agents`.
   - Invoke `$inspect-repo-with-agents` to inspect whether the repo and current/planned task direction align with `$manage-agent-goal`, `$manage-goal-architecture`, `$manage-goal-theory`, the `$manage-agent-authority` result, and `.agent_goal/goal_schema_contract.md` outputs.
   - Request fixed `reasoning_effort: xhigh` for all alignment inspectors when the tooling exposes reasoning effort.
   - Run the inspection with a critical review stance, not a confirmation-seeking stance. Require inspectors to actively search for goal mismatch, convention violations, unsupported assumptions, scope creep, overfitting to the current task, contradictions between goal files, missing repository evidence, and validation blind spots.
   - Treat `.agent_goal/conventions.md` as first-class evaluation criteria. Inspectors must name the relevant conventions considered, classify each as `satisfied`, `violated`, `insufficient_evidence`, or `not_applicable`, and cite evidence where possible.
   - Treat the `$manage-agent-authority` result as first-class evaluation criteria. Inspectors must classify relevant API/external-call permission, direction-freedom, implementation-priority, validation-priority, strictness, conservative-implementation, and escalation rules as `satisfied`, `violated`, `insufficient_evidence`, or `not_applicable`.
   - Treat active `.agent_advice` as a separate non-GT direction source. Inspectors must identify whether advice supports, conflicts with, or is irrelevant to the next-task direction without upgrading it into goal truth.
   - Require coverage of final objective, conventions, architecture fit, theory/technical logic fit, schema-contract-goal fit, validation gaps, and risks.
   - Include schema/module/script contract alignment: whether a candidate preserves or intentionally updates `.schema` and `.contract` versions, targets, producers, consumers, required minimum fields, and causal compatibility links to satisfy `.agent_goal/goal_schema_contract.md`.
   - The inspection must cite file/line evidence where possible and distinguish confirmed facts from inferred alignment. Missing evidence must be reported as `insufficient_evidence`, not treated as compliance.
   - Require a findings-first report with blockers and convention violations before supportive alignment notes, plus an explicit alignment verdict: `aligned`, `partial`, `misaligned`, or `insufficient_evidence`.
   - Include ID-based traceability as an additional audit concern: whether current task, past_task, candidate_task, issue, task_miss, goal, audit, run, and validation artifacts are consistently linked.
   - Pass the critical goal/convention alignment report to issue analysis, task_miss analysis, improvement agents, and synthesis. Later agents must not dilute blocker-level convention violations into generic risks.

3. Analyze `.task/task_miss` with agents.
   - Use 2-4 read-only agents, or include this as a distinct `$inspect-repo-with-agents` perspective, to analyze `.task/task_miss/`.
   - Require fixed `reasoning_effort: xhigh` for task_miss analysis agents.
   - Extract unresolved misses, resolved/deleted miss records, recurring patterns, generalization gaps, failed validation, and candidate follow-ups.
   - Identify repeated `safety_only` or no-live/fail-closed cycles that preserve safety but do not reduce the active issue blocker; pass that pattern to improvement-analysis and synthesis agents as a task-selection constraint.
   - Do not treat old misses as still active if a later resolved/deleted report clearly closed them.

4. Explore `.task/candidate_task/`.
   - Read existing candidate files under `.task/candidate_task/`.
   - Classify candidates as applicable now, blocked, obsolete, duplicate, or lower priority.
   - Also classify candidates as `state_transition`, `batchable_micro_contract`, `safety_only`, or `goal_progress` so synthesis can avoid unnecessary sequential micro-tasks.
   - If a candidate is selected for the new `task.md`, delete that candidate file after the new `task.md` is written successfully.
   - Keep unapplied candidates in `.task/candidate_task/` and update or create candidate files for good but unselected proposals.

5. Explore `.task/task_pack/`.
   - If no active pack exists, agents may propose `pack_disposition: create_pack` only when a sequence of 2-5 ordered tasks is necessary to avoid repeated myopic derivation. Otherwise derive a single standalone task.
   - If an active pack exists, classify the next item as `promote_now`, `blocked`, `obsolete`, `needs_insert_before`, `needs_reorder`, `superseded`, or `terminal_blocked`.
   - Do not create multiple active packs. Supersede the old pack before activating a replacement.
   - Treat pack creation, insertion, reordering, skipping/exclusion, supersession, and terminal blocking as workflow-state mutations that must cite new evidence, repeated blocker signature, missing positive input delta, provider-neutral retargeting, dependency repair, user-supplied exclusion direction, or terminal blocker state.
   - When active advice or another steering source contains measurable targets, map each directive to one or more pack items through `scope_fidelity`. If an item narrows the target, require a residual item and do not mark the directive consumed.
   - Keep `.task/task_pack/*.json` canonical and refresh the user-language Markdown render after any pack change.

6. Analyze implementation issues with one issue goal-fit agent.
   - Spawn exactly one read-only issue agent before the three improvement-analysis agents.
   - Spawn or request this issue agent with fixed `reasoning_effort: xhigh`.
   - Use the issue prompt from `$manage-implementation-issues` [issue-agent-prompts.md](../manage-implementation-issues/references/issue-agent-prompts.md) when available.
   - Give the issue agent the critical goal/convention alignment report so it can classify whether issues reinforce, conflict with, or distract from the goal and conventions.
   - Give the issue agent active advice summaries when present so it can classify whether issue-driven work should incorporate, defer, reject, or ignore that advice.
   - The issue agent must classify active `.issue/` or GitHub-mirrored issues as `fit`, `partial`, `misfit`, or `unknown` against `.agent_goal` and current task direction.
   - The issue agent must identify duplicates, stale issues, already resolved issues, blocked issues, and issues that should or should not influence the next `task.md`.
   - Pass the issue insight report to the three improvement-analysis agents and the synthesis agent.
   - Do not let the issue agent open, close, edit, or implement issues.

7. Run three parallel improvement-analysis agents.
   - Spawn exactly three independent agents unless the user requests a different count.
   - Spawn all three improvement-analysis agents with fixed `reasoning_effort: xhigh`.
   - Give each agent the same evidence package, including the critical goal/convention alignment report, but a different lens:
     - Goal and user-value fit.
     - Architecture/theory/code-governance fit.
     - Miss/candidate/validation-risk fit.
   - Each agent must propose concrete improvement candidates, expected impact, required scope, risks, validation, and whether the candidate should become `task.md` now.
   - Each agent must classify the proposal's expected `progress_verdict` as `advanced`, `safety_only`, `no_progress`, or `regressed`, classify `progress_kind` as `goal_productive` or `governance_only`, and explain what blocker-state transition or goal-distance reduction the task should achieve.
   - Each agent must propose the cheapest valid validation profile: `current_only`, `affected_chain`, or `full_chain`, and name the surfaces that justify rerunning historical prerequisites when applicable.
   - Each agent must account for any supplied `$optimize-task-slice` advisory classification without treating it as the final task choice.
   - Each agent must explain how its proposal resolves or avoids any blocker-level goal mismatch or convention violation from the critical alignment report.
   - Each agent must explain whether its proposal respects the effective authority policy, including whether it requires API/network/external service use, expands task direction beyond the allowed freedom profile, prioritizes implementation versus validation appropriately, or needs explicit user approval.
   - Each agent must receive the issue goal-fit report and explain whether any issue should drive, constrain, or be ignored by its proposals.
   - Each agent must identify whether its proposal changes any `.schema` or `.contract` contract and whether `$manage-schema-contracts` should update versions, target modules/scripts, minimum fields, mandatory rules, or causal links required by `.agent_goal/goal_schema_contract.md`.
   - Each agent must explain how active advice affects the proposal: `incorporate`, `defer`, `reject`, or `not_applicable`, with conflict evidence when relevant.
   - Each agent must identify measurable directive targets affected by the proposal and state whether the proposal preserves the original target, explicitly descopes it with residual scope, or should be rejected as diluted.
   - Each agent must identify whether the proposal is `semantic_consolidation`, `reuse_extraction`, or `coupling_reduction` when structure evidence is relevant, and name the expected structure high-water axes that should improve.
   - Each agent must explain whether the proposal should be standalone, used to create a bounded pack, promoted from the active task pack, inserted/reordered/skipped inside the task pack, or used to terminal-block/supersede the pack.
   - Use [agent-prompts.md](references/agent-prompts.md).
   - If ID context exists and the workflow authorizes agents, spawn one separate read-only ID consistency agent. It is not one of the three improvement-analysis agents and must only analyze task-state IDs, lifecycle transitions, and candidate/miss/log link integrity.
   - Spawn the separate ID consistency agent with fixed `reasoning_effort: xhigh`.
   - If thread limits prevent the exact issue/improvement/ID agent fanout, preserve distinct lenses in the agents that can run, perform a main-agent synthesis over the evidence packet, and emit a degraded-agent note instead of silently reducing coverage.

8. Synthesize the final task with one agent.
   - Spawn one synthesis agent after the three improvement agents return.
   - Spawn the synthesis agent with fixed `reasoning_effort: xhigh`.
   - The synthesis agent must select one final improvement to become `task.md`, or write a terminal blocker result when no viable task or pack item remains.
   - The synthesis agent must choose exactly one pack disposition when a pack is in scope: `create_pack`, `promote_next_item`, `insert_items`, `reorder_items`, `skip_items`, `supersede_pack`, `derive_standalone`, or `terminal_blocked`.
   - For `insert_items`, `reorder_items`, `skip_items`, `supersede_pack`, `create_pack`, or `terminal_blocked`, it must emit a `pack_mutation_plan` with `action`, `reason`, `evidence_paths`, `pack_path` when mutating an existing pack, changed item IDs, `before_order` and `after_order` when order changes, and `terminal_blocker` when terminal-blocking.
   - For any measurable directive-derived item, it must emit `scope_fidelity` and preserve the original measurable target in `acceptance`, or emit explicit descope with `narrowed=true`, `narrow_reason`, and `residual_item_id`.
   - It must not select `promote_next_item` when the next pack item has `acceptance_diluted=true`, missing measurable `scope_fidelity`, or a narrowed target without an open residual item.
   - The synthesis agent must prefer a state-transition or batched-boundary task over a single additional no-live scalar/check contract unless the single contract unlocks a concrete next execution state or prevents a named unsafe transition.
   - If it selects a `safety_only` task while the same issue blocker has remained through the last two completed tasks, it must explicitly justify why evidence supply, bounded preflight/run, or batch consolidation is not currently possible.
   - If failure autopsy and loopback together establish `self_inflicted_gate_defect`, it must select a gate/code correction, use `alternative_evidence_source`, or user-escalate for gate-contract approval. It must not write another same-gate environment proof, handoff, or terminal blocker that trusts the rejected self-report.
   - If the caller's goal-distance gate requires goal-productive work, it must select `progress_kind: goal_productive` or emit `selected_task_source: terminal_blocked` with required handoff/input/authority. It must not choose another governance-only sidecar/reconciliation task as progress.
   - If the caller's GT-constraint conflict packet reports `status: block`, it must not write a next task that repeats the contradiction. It must choose conflict resolution or contradiction removal and set `resolves_gt_constraint_conflict=true` or `selected_task_kind: gt_constraint_conflict_resolution`, or emit terminal/user escalation.
   - If the caller's root-axis gate reports `autonomous_retarget_disabled=true`, it must select `progress_kind: goal_productive` or emit `selected_task_source: terminal_blocked`; provider-neutral/governance retargeting on the same root axis or suffix-normalized root key is exhausted.
   - If the caller's progress-loop detector returned `status: block`, it must select `progress_kind: goal_productive` or emit `selected_task_source: terminal_blocked` with provider-track and provider-neutral/quality-track attempt evidence. It must not choose another governance-only contract, handoff, sidecar, or preflight-only task.
   - If the caller's feature-symbol gate reports repeated no-delta symbols or terminal-history matches, it must either select a task that creates an observed primary output delta, select consolidation, or terminal/user-escalate with the symbol, registry path, and prior terminal evidence. It must not treat a new label, new `vN`, or self-declared delta as progress.
   - If the caller's output-delta gate returns `produced_domain_delta: false`, `changed_vs_previous: false`, `semantic_progress: false`, or `metadata_only: true`, it must either set `effective_progress_kind: governance_only` or explain the independent validated positive evidence that overrides the gate. Non-empty scalar counts alone do not override the gate.
   - If the caller supplies `observed_producer_claim`, it must not cite that claim as progress or completion truth. If `split_brain_progress_claim=true`, it must choose from adapter/output-delta truth, preserve residual work, or terminal/user-escalate with the disagreement evidence.
   - If the caller's anti-loop gate reports `measurement_progress=true`, it may select the next measurement-linked task as `goal_productive` only when `measurement_progress_allowed=true`, root-key/root-family measurement streaks remain within cap, `coverage_quality_delta_gate.quality_delta_pass=true`, `coverage_quality_delta_reconciliation_gate.status!=block`, and `substance_delta_gate.substance_delta_pass=true`; otherwise measurement-linked work is governance-only and cannot satisfy a hard goal-productive gate.
   - If the caller's anti-loop gate reports `adapter_wiring_defect=true`, it must select `selected_task_kind: adapter_wiring_fix` or `adapter_load_fix`, or terminal/user-escalate with the registered adapter path and load failure. It must not choose adapter creation, adapter mandate, or another domain micro-repair for the same blocker.
   - If the caller's anti-loop gate reports `adapter_mandate_required=true`, it must select adapter registration/strengthening as the next goal-productive task, or terminal/user-escalate with the missing adapter contract. It must not choose another domain micro-repair while `adapter_contract_unmet` remains unresolved.
   - If the caller's anti-loop gate reports `cumulative_goal_distance_stalled=true`, it must select `forced_selected_task.selected_task_kind` when an actionable forced option is present; otherwise it must select `terminal_blocked` or `user_escalation` unless `adapter_mandate_required=true` is the active preceding mandate. If `untried_veto_overridden_by_chain_stall=true`, it must not select another distinct untried repair solely from `untried_root_cause_hypotheses`.
   - If the caller's anti-loop gate reports `root_dominant_parameter_key`, it must not treat proximate root-cause label changes as distinct untried repairs for the same collapsed root and dominant parameter.
   - If the caller's anti-loop gate reports `primary_metric_gate.primary_metric_stalled=true` or `primary_metric_stalled=true`, it must apply C4 forced retargeting even when blocker labels changed. If `c4_user_escalation_backstop_required=true`, it must select `user_escalation` unless a forced option is newly actionable with evidence.
   - If the caller supplies `acceptance_envelope_contract` with `envelope_below_floor=true`, it must select envelope expansion, constraint relaxation, explicit descope with residual scope, terminal-block, or user escalation. It must not write another envelope-internal repair as `goal_productive`.
   - If the caller's anti-loop gate reports `acceptance_unreachable_under_frozen_config=true`, it must select a constraint-relaxation task or `user_escalation`; envelope-internal repair is invalid as `goal_productive`.
   - If the caller's anti-loop gate reports `oracle_metric_validity_gate.metric_goal_productive_excluded=true`, it must not cite the tautological oracle/metric pass as progress. It must select metric/oracle correction, independent changed-and-semantic output work, terminal-block, or user-escalation.
   - If `validator_integrity_gate.status=block`, it must not cite the validator pass as completion, semantic progress, or goal-productive evidence. It must select correction work, terminal-block, or user-escalate.
   - If the caller's provider/scale dispatch gate reports `dispatch_required=true`, it must select bounded extraction/scale work when authority permits, or terminal/user-escalate with the exact missing authority/input. It must not satisfy the gate with another runner-surface, contract, preflight, locator, dashboard, or measurement-only task.
   - If the caller's anti-loop gate reports `requires_correction_or_terminal=true` or a detection balance gate blocks, it must not select another validator/oracle/metric/gate/dashboard/lineage/report task as `goal_productive`. It must choose correction work, terminal-block, or user-escalation.
   - If the caller's anti-loop gate reports `blocker_mutation_kind=facet_rename`, it must treat the rename as same-family churn. If it reports `blocker_mutation_kind=forward_mutation`, it must not terminal-block merely because the suffix-normalized family repeated, unless stricter gates block. It may treat the rung as progress only when `terminal_outcome_changed=true`; when `forward_mutation_vacuous=true`, it must route to untried root-cause repair, output-producing correction, or terminal/user escalation with the specific missing authority/input. It must either promote the next rung, choose allowed Class B/C implementation when `force_implementation_cycle=true`, or terminal/user-escalate with the specific missing authority/input.
   - If the caller supplies `effective_allowed_dispositions`, it must set the selected disposition inside that list. Do not select `consolidation` when it appears only in one individual gate and not in the effective intersection.
   - If the caller supplies `disposition_intersection_basis.allowed_task_kinds`, it must set `selected_task_kind` to an allowed kind for `goal_productive`. If the selected work is useful but outside the allowed kind set, mark it `governance_only`, preserve a residual task, or terminal/user-escalate.
   - If the caller supplies a block-level `validator_disagreement`, it must not cite strict runner pass as completion, semantic progress, or goal-productive evidence unless a newer output-delta packet resolves the disagreement.
   - If the caller supplies a sealed `semantic_signature`, it must not select another non-terminal task in that family unless it names the new input kind, authority change, or external-state change that reopens the family.
   - If the caller supplies `provider_reattempt_gate.provider_mitigation_required=true`, it must not terminal-seal provider failure while required mitigations are missing. If `provider_reattempt_required=true`, it must select bounded provider retry/probe work and record `provider_reattempt_disposition: selected_bounded_provider_retry|selected_probe_retry`; if retry/probe is unauthorized, it must terminal/user-escalate on the authority constraint, not on provider permanence.
   - If the caller supplies `command_surface_budget.consolidation_candidate_required=true`, it must register/select a consolidation candidate unless strict changed-and-semantic primary-output evidence already justifies goal-productive work, or the result is terminal/user escalation.
   - If `consolidation_streak >= consolidation_streak_cap`, it must not register/select another consolidation candidate as the next task; choose goal-productive work within the effective disposition list, terminal-block, or user-escalate.
   - If the caller supplies `anti_loop_progress_gate.same_family_micro_hardening_count>=3`, it must block another same-family micro-hardening task as `goal_productive` and choose provider/semantic transition, consolidation, supplied-input/domain-delta work, or terminal/user escalation.
   - If the caller supplies `$optimize-task-slice` advice with `semantic_consolidation`, `reuse_extraction`, or `coupling_reduction`, it must either select a task in that class with measurable structure high-water acceptance, reject it with evidence, or terminal/user-escalate when convention/adapter evidence is missing. It must not translate the class into generic "add modules" work.
   - If the caller supplies a code-structure audit packet with unresolved contract-backed convention violations, it must select a correcting task, preserve a residual item, or terminal/user-escalate. If the convention contract is missing and the finding is warn-only, it may select a repo-local adapter/convention-contract strengthening task when the gap is recurring.
   - If the caller supplies `terminal_escalation_gate.escalation_required=true`, it must set `selected_task_source: user_escalation` and must not write another non-terminal task for that family. The result must include `forced_disposition: user_escalation`, `terminal_recheck_streak`, `required_missing_input_count: 1`, exactly one `required_missing_input` object, and evidence that the family was sealed or a pack mutation will seal it.
   - If it terminal-blocks or seals a family, it must include `root_cause_attempted_for_family: true` or a concrete `root_cause_not_required_for_family` rationale.
   - If `untried_actionable_root_cause_exists=true`, it must not terminal-block or seal the family unless `hypothesis_exhausted=true` or `untried_veto_overridden_by_chain_stall=true`. While the veto is active, it must select the untried hypothesis as the next repair task and include `root_cause_ledger_path` plus the chosen `hypothesized_root_cause` in the derive result.
   - If it terminal-blocks or seals a family, it must include `authorized_alternative_path_exists`, `authorized_alternative_path`, `authorized_alternative_path_attempted`, `alternative_in_gt_allowed`, `gt_allowed_alternative_attempted`, `gt_allowed_alternative_evidence_paths`, and `authorized_alternative_source_gt_paths`; an unattempted authority-permitted productive alternative path or a non-GT fabricated alternative blocks the seal.
   - If it terminal-blocks while a corpus-scale ladder rung remains, it must include `terminal_blocked_exit_guard` with `next_rung`, `provider_dependency`, `uses_only_local_data`, `within_goal_scope`, `authority_requires_new_permission`, and `actionable=false` evidence. Omitting this guard invalidates the terminal blocker.
   - If it terminal-blocks due to terminal quiescence, it must include `terminal_quiescence=true`, `commit_skipped_reason: terminal_quiescence`, the repeated `root_key`, `terminal_streak`, and the evidence paths that prove no supplied input delta exists.
   - The synthesis agent must not select a task that conflicts with `.agent_goal/final_goal.md` or `.agent_goal/conventions.md` unless the selected task explicitly exists to resolve that conflict.
   - The synthesis agent must not select a task that conflicts with the `$manage-agent-authority` result unless the selected task explicitly exists to clarify or resolve that authority-policy conflict. When the authority file is absent, the synthesis agent must not infer permission for API calls, network access, external services, destructive changes, or broad direction changes beyond the current agent's effective permissions.
   - The synthesis agent must not select a task that treats `.agent_advice` as GT or authority. If advice is used, the final task must list the advice path/ID and say whether the task incorporates, defers, or tests it.
   - The synthesis agent must write `task.md` with `## Execution Environment` immediately after `# Task`.
   - The execution-environment section must include `progress_target`, `validation_profile`, `authority_policy` (`.agent_goal/agent_authority.md` path or `default_current_agent_permissions`), and, when historical prerequisites are reused, a prerequisite manifest/check-hash summary or a reason no manifest exists yet.
   - The execution-environment section must include `progress_kind` and, when output-delta evidence is available, `effective_progress_kind` plus the output-delta status that justified it.
   - The execution-environment section must include `selected_task_kind` when any anti-loop or workflow gate constrains `goal_productive` by task kind.
   - The execution-environment section must include `Task Pack`, `Task Pack Item`, `Pack Position`, and `Pack Source` when the selected task came from or updated a task pack. Use `none` for standalone tasks.
   - The execution-environment section must include `External Advice: <adv-id/path | none>` when active advice influenced selection or validation.
   - If the selected task changes shared schemas, module contracts, script contracts, or causal compatibility, the task must explicitly include `.schema` and, when applicable, `.contract` update requirements, validation evidence, and how the update satisfies `.agent_goal/goal_schema_contract.md`.
   - Pass the previous `task.md` execution-environment section to the synthesis agent when present.
   - If the previous `task.md` has no usable environment information and the selected task likely requires Python execution, use `$find-local-python-envs` before finalizing `task.md`.
   - Rank environment choices in this order: conda environment, project virtualenv/venv, local/system Python interpreter.
   - Record the selected environment type, interpreter or env name/path, exact run prefix, dependency gaps, and discovery source in the top environment section.
   - It must also list unselected but still useful candidates for `.task/candidate_task/`.
   - It must list task-pack JSON changes when applicable, including `pack_disposition`, inserted/reordered/skipped/superseded item IDs, terminal blocker content, mutation-log reason, and Markdown render path.
   - It must cite any issue that the selected task tracks or intentionally ignores, and it must include issue links or local `.issue/` paths when known.
   - It must cite any `adv-*` ID or `.agent_advice` path that the selected task incorporates, defers, rejects, or intentionally ignores.
   - Use [agent-prompts.md](references/agent-prompts.md) and [task-and-candidate-templates.md](references/task-and-candidate-templates.md).

9. Archive existing `task.md` as `past_task`.
   - Before replacing `task.md`, use `$record-agent-work-log` to create an `.agent_log` entry titled `past_task`.
   - Include the old `task.md` content or a safe summary if it is too large or sensitive.
   - Record why it is being replaced, the new task source, selected candidate if any, and any candidates left unapplied.
   - Do not overwrite `task.md` until the `past_task` log entry is written.
   - After logging, run `$manage-task-state-index` `scan`, index the `past_task` log as `past-*` or `log-*`, and link it from the new task later with `supersedes` or `archived_as`.
   - In `initial_init` mode, skip this step because no previous `task.md` exists. Record in the final response and index note that the new task is an initial task, not a replacement.

10. Write final `task.md`, task packs, and candidates.
   - Write the synthesized final task in `task.md` format with `## Execution Environment` at the top.
   - Do not write a Python-execution task without environment information. If `$find-local-python-envs` cannot identify a usable environment, write the environment section with `Status: unresolved`, the commands attempted, and the exact blocker.
   - If the selected task does not require executable code or Python, write `Status: not_applicable` and explain the basis briefly.
   - Create `.task/candidate_task/` if needed.
   - Create `.task/task_pack/` if the synthesis selected a new task pack. Write the JSON queue first, then render the Markdown view in the user-requested language. Prefer `$orchestrate-task-cycle` `scripts/task_pack_queue.py --root . apply-mutation --plan <derive-pack-plan.json> --render --language <user-language>` for `create_pack` when available.
   - If promoting from an active pack, update that pack item's promotion metadata and set the pack `current_item_id` to the next planned item after the new `task.md` is written.
   - If promoting or consuming a measurable item, preserve `scope_fidelity` in the pack and copy the original target or explicit descope/residual rationale into the new `task.md` acceptance and validation sections.
   - If inserting, reordering, skipping, superseding, or terminal-blocking pack items, append `mutation_log` entries with evidence paths and refresh the Markdown render. Prefer `task_pack_queue.py apply-mutation` over manual JSON edits when available.
   - If terminal-blocking, user-escalating, or zero-candidate state applies, write `terminal_blocker` with semantic signature, blocker signature, reason, required handoff/input/authority, root-cause attempt status, `root_cause_ledger_path`, `untried_actionable_root_cause_exists=false` or `untried_veto_overridden_by_chain_stall=true`, authorized-alternative-path status, provider re-attempt status, dual-track attempt evidence when a hard loop gate applies, adapter/chain/reachability/metric-validity fields when applicable, terminal quiescence fields when applicable, G2 escalation fields when applicable, recent cycle IDs, and evidence paths. Also update `.task/sealed_blocker_families.json` with the semantic signature or root family when possible. Do not write another narrowing `task.md` as a substitute for terminal or user-escalation state.
   - Save each unapplied improvement as `.task/candidate_task/YYYYMMDD-HHMMSS-<slug>.md`.
   - If the final task came from an existing candidate file, delete that candidate file from `.task/candidate_task/` after writing `task.md`.
   - Do not delete blocked or unapplied candidate files.
   - Before deleting an applied candidate, mark the candidate ID `applied` and link it to the new `task-*` with `derived_from`.
   - After writing `task.md` and candidate files, run `$manage-task-state-index` `scan` and global `audit`. Treat high-severity ID inconsistencies as blockers to candidate deletion and record them under `.task/candidate_task/`, `.task/task_miss/`, or `.issue/` as appropriate.

11. Report outcome.
   - Summarize the selected task, why it won, issue insights used or ignored, where `past_task` was logged, which candidates were retained, which applied candidate file was deleted, and the relevant task/candidate/issue/past/log IDs.
   - Include `selected_task_source: task_pack | candidate_task | standalone | terminal_blocked | user_escalation`, `pack_disposition` when a pack is in scope, `progress_kind: goal_productive | governance_only`, selected or terminal `semantic_signature`, `task_pack_status` when a pack exists, mutation evidence paths, and `loop_breaker_disposition`.
   - In `initial_init` mode, report that no `past_task` log was created because there was no previous `task.md`.

## Initial Init Mode

Use this mode when `task.md` is absent and a caller needs the first task before implementation can begin.

- Do not fail only because `task.md` is missing.
- Do not create a `past_task` log.
- Do not run previous-task replacement analysis.
- Use `.agent_goal`, `.issue`, `.task/task_miss`, `.task/candidate_task`, repository evidence, and goal-alignment inspection to select the initial task.
- Still include `## Execution Environment` at the top of the generated `task.md`.
- Still save good but unselected proposals under `.task/candidate_task/`.
- Still run `$manage-task-state-index` after writing the initial `task.md` when possible.

## ID Governance Add-on

- Use `$manage-task-state-index` before and after replacing `task.md`.
- Do not assign task synthesis or candidate prioritization to the ID consistency agent.
- Use ID audit insights to prevent deleting the wrong candidate, orphaning miss reports, or losing the link from old `task.md` to `past_task`.
- If no ID context exists, continue the improvement workflow and report that ID governance was unavailable.

## Execution Environment Selection

- Prefer an environment section copied from the previous `task.md` only when it names a runnable environment and still matches the selected task's language/dependencies.
- If environment information is absent, stale, or too vague for a Python task, invoke `$find-local-python-envs` with dependencies inferred from the selected task, repository manifests, tests, imports, notebooks, and candidate evidence.
- Choose the highest-ranked usable environment in this priority order:
  1. Conda: `conda run -n <env> ...` or a conda prefix command.
  2. Venv/virtualenv: `<repo>/.venv/bin/python ...`, `venv/bin/python ...`, or a documented project venv.
  3. Local/system Python: `python`, `python3`, or an absolute interpreter path discovered on PATH.
- Do not install packages or create environments during task derivation.
- If no candidate satisfies dependencies, still write the task but make the unresolved environment a visible prerequisite in the top section and validation plan.

## Selection Rules

Prefer the improvement that:

- Best advances `.agent_goal/final_goal.md` success criteria.
- Respects `.agent_goal/conventions.md`; if a convention conflict exists, the selected task explicitly resolves or documents it as a blocker rather than proceeding as if compliant.
- Fits the documented architecture and theory, or explicitly updates gaps discovered by analysis.
- Incorporates active `.agent_advice` only when it is compatible with current user direction, GT, authority, and repository facts; otherwise explicitly defers or rejects it.
- Preserves documented `.schema` and `.contract` compatibility, or makes the necessary schema/contract version update explicit in the task.
- Respects the `$manage-agent-authority` result, including `.agent_goal/agent_authority.md` when present or the `default_current_agent_permissions` fallback when absent, including API/external-call policy, direction freedom, strictness, implementation/validation priority, and conservative implementation constraints.
- Satisfies `.agent_goal/goal_schema_contract.md` minimum fields, mandatory rules, target module/script guidance, and causal-map expectations when schema/contract surfaces are involved.
- Addresses high-severity `.task/task_miss` patterns.
- Fits active implementation issues that the issue agent classifies as goal-aligned, or explicitly explains why a misfit/stale/duplicate issue should not drive the next task.
- Can be validated with concrete tests, commands, metrics, or review evidence.
- Is `goal_productive` when the caller's goal-distance gate requires it: expected to produce changed-and-semantic goal-relevant output, quality evidence, source-backed validation, or another non-sidecar artifact that reduces goal distance.
- Uses a `selected_task_kind` allowed by `disposition_intersection_basis.allowed_task_kinds` whenever gates constrain `goal_productive` to specific correction classes.
- Is not classified as `goal_productive` merely because it writes workflow metadata, sidecar metrics, schema records, task-state records, non-empty counts, lineage, gap reports, or measured absences without changed-and-semantic repository-declared output delta or validated positive evidence.
- Advances the blocker state or final-goal state more than it adds another isolated safety proof.
- Minimizes repeated prerequisite work by declaring `current_only` or `affected_chain` validation when full historical reruns are not needed.
- Is narrow enough to become one actionable `task.md`, or narrow enough to become the next item in a bounded task pack.
- Consumes an active task-pack item when that item is still safe, aligned, and not blocked by repeated blocker signatures or missing input delta; otherwise records the pack mutation needed before the next execution item.
- Preserves measurable directive scope with `scope_fidelity`; if the selected item is intentionally narrowed, it keeps the residual target open instead of redefining completion around the smaller slice.

## Guardrails

- Do not replace `task.md` before logging the existing one as `past_task`.
- Do not require `past_task` archival in `initial_init` mode when no previous `task.md` exists.
- Do not delete `.task/candidate_task/` wholesale.
- Do not delete an unapplied candidate.
- Do not claim `$inspect-repo-with-agents` analysis happened if subagents were unavailable.
- Do not claim exact issue/improvement/synthesis/ID agent fanout when thread limits forced degraded execution; record the degraded state and missing independent lenses.
- Do not let analysis agents edit files.
- Do not spawn or request improvement-derivation agents with any reasoning effort other than `xhigh` when the tooling exposes `reasoning_effort`.
- Do not let the issue goal-fit agent open, close, edit, or implement issues.
- Do not treat absent or weak evidence as goal alignment or convention compliance.
- Do not allow supportive goal-fit summaries to override blocker-level convention violations unless the selected task directly addresses those violations.
- Do not bypass `$manage-agent-authority` when deriving tasks that require API calls, network/external service use, broad direction changes, implementation-first tradeoffs, quality-first validation, conservative implementation, or explicit escalation.
- Do not treat `.agent_advice` as `.agent_goal` GT, authority, or permission evidence.
- Do not silently ignore active advice when the caller supplied it; record whether it was used, deferred, rejected, or not applicable.
- Do not mark advice applied from this skill unless `$manage-external-advice` has lifecycle evidence that the selected task/design artifact fully consumed or retired it.
- Do not store secrets, credentials, raw sensitive data, or large copyrighted excerpts in `task.md`, candidate files, or `.agent_log`.
- Do not ignore `.agent_goal/goal_schema_contract.md`, `.schema`, or `.contract` compatibility risks when deriving an interface- or data-contract-changing task.
- Do not delete an applied candidate until its ID transition and link to the new task are recorded when ID context exists.
- Do not omit the top execution-environment section from generated `task.md`.
- Do not derive repeated `safety_only` no-live micro-contracts on the same blocker without either batching them, naming the unlocked transition, or recording why evidence supply/bounded execution is blocked.
- Do not let `$optimize-task-slice` write `task.md`, apply/delete candidates, or downgrade this skill's fixed `reasoning_effort: xhigh` routing.
- Do not create multiple active `task.md` files or multiple active task packs to simulate parallelism.
- Do not create, reorder, insert, skip, supersede, or terminal-block task-pack items without citing new evidence, repeated blocker signature, missing supplied positive input delta, provider-neutral retargeting, dependency repair, user-supplied exclusion direction, or terminal blocker state.
- Do not use task packs as `.agent_goal` goal truth, authority, or completion evidence.
- Do not derive another narrowing/handoff task when zero viable candidates remain; write `terminal_blocked` with required handoff/input/authority details instead.
- Do not satisfy a positive input delta gate with `new_input_kinds` alone; require non-empty supplied artifact evidence or `produced_domain_delta=true`.
- Do not mark a measurable directive-derived pack item `consumed` unless `$validate-task-completion` or the pack result records `acceptance_provenance_gate.target_met=true`, or records an explicit descope decision and open residual item.
- Do not use `pilot`, `plan`, `slice`, `bounded`, or similar wording as implicit descope of an original measurable target.
- Do not terminal-seal a provider family while `provider_mitigation_required=true`, while `provider_reattempt_required=true`, or while an authority-permitted productive alternative path remains unattempted.
- Do not terminal-seal a family with `authorized_alternative_path_attempted=true` unless `alternative_in_gt_allowed=true`, `gt_allowed_alternative_attempted=true`, and `gt_allowed_alternative_evidence_paths` is non-empty.
- Do not ignore `command_surface_budget.consolidation_candidate_required`; register/select consolidation unless strict changed-and-semantic primary-output evidence already justifies goal-productive work, or the result is terminal/user escalation.
- Do not continue same-family micro-hardening loops after the anti-loop gate reports 3 repeated micro tasks without provider/env behavior and semantic-output change.
