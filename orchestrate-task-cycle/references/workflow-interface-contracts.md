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
| Repo adapter packet | Orchestrator scan or `scripts/render_adapter_packet.py` | Validation-set, governance, run, review, loopback, schema, derive, validation | Adapter ID/path/status, consumed phase packet, loaded references, non-GT/authority limits, validation status. |
| Validation-set packet | `$build-validation-set-with-agents` | Governance, schema, derive, index, validation, report | Need/status, quality tier, `not_gold`, item/label/oracle counts, source-class distribution, oracle/split/leakage/root paths, blocked/candidate-only reasons. |
| Governance result | `$task-md-agent-governance` | Result contract, ledger, code audit, run, schema, validation | Task ID, changed files, task_miss, used GT/advice, implementation summary, validation profile, blockers. |
| Code-structure audit packet | `scripts/code_structure_audit.py` | Run, derive, validation, issue, report | Scanned changed files, oversize files, responsibility clusters, moduleization requirement, split plan, exemptions, evidence paths. |
| Run result | `$run-task-code-and-log` | Review, loopback, validation-set, schema, derive, index, validation, issue, report | Status, command, exit code, output/artifact paths, running metadata, log path, shortcomings, `failure_autopsy`, `gate_satisfiability`, and scalar `gate_selfcheck` when a pre-execution gate artifact exists. |
| Qualitative review packet | `$review-cycle-output-quality` | Loopback, validation-set, schema, derive, validation, report | `review_agent_count`, reviewed artifacts, quality verdict, findings, progress cap, output-delta fields, no-overclaim flags, evidence paths. |
| Anti-loop progress gate | `$audit-cycle-loopback` | Derive, validation, dashboard, report | Family/root keys, semantic signature, progress booleans, terminal outcome fields, quality vector, effective dispositions, hard-stop state, findings, evidence paths. |
| Loop-breaker packet | `scripts/detect_progress_loop.py` plus orchestrator synthesis | Derive, task-pack, validation, report | Blocker/root/semantic signatures, root-axis counts, terminal quiescence/escalation gates, supplied-input delta, provider retry, command surface, sealed family, zero-candidate state. |
| Task-pack packet | `scripts/task_pack_queue.py` and `$derive-improvement-task` | Derive, index, validation, report, commit | Pack ID/path/status, current item, mutation plan, Markdown render, terminal blocker state, selected disposition, and `scope_fidelity` for measurable directive-derived items. |
| Validation result | `$validate-task-completion` | Issue, commit, dashboard, report | `validation_verdict`, `progress_verdict`, `progress_axes`, blockers, evidence paths, advice disposition, task-pack preservation, `acceptance_provenance_gate`, `structure_metrics_gate`, and behavior-change live evidence gate when applicable. |
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

Do not persist raw prompts, provider bodies, generated bodies, stdout/stderr bodies, source bodies, credentials, tokens, or secrets in the autopsy packet.

### Qualitative Review

The qualitative review packet must report exactly one read-only reviewer agent when delegation is available. It must include `review_agent_count: 1`, reviewer routing, reviewed artifacts, direct read scope, qualitative findings, direction recommendations, blocker taxonomy delta, no-overclaim flags, evidence paths, and active advice usage or disposition.

When output-delta evidence exists, include explicit values for `output_delta_status`, `changed_vs_previous`, `semantic_progress`, `produced_domain_delta`, `metadata_only`, `effective_progress_kind`, and `progress_cap`. Omit neither false nor not-applicable values.

### Anti-Loop Progress Gate

The canonical schema for `anti_loop_progress_gate` is owned by `$audit-cycle-loopback` and documented in [packet-schema.md](../../audit-cycle-loopback/references/packet-schema.md) when that skill is available, plus [anti-loop-progress-gates.md](anti-loop-progress-gates.md) for orchestrator policy.

Consumers must preserve:

- family keys: `family_key`, `root_key`, `root_family_key`, `blocker_root_family`
- progress fields: `changed_vs_previous`, `semantic_progress`, `authoritative_semantic_progress`, `terminal_outcome_changed`
- terminal outcome fields: `terminal_outcome_key`, `terminal_outcome_family_key`
- constraint fields: `effective_allowed_dispositions`, `disposition_intersection_basis`, `hard_stop_required`, `evidence_class`
- root-cause fields: `repo_owned_source_roots_status`, `root_cause_unverified_hypotheses`, `root_cause_duplicate_hypotheses`, `untried_actionable_root_cause_exists`, `untried_root_cause_hypotheses`, `hypothesis_exhausted`, and provenance-hardened ledger entries
- adapter/chain fields: `adapter_mandate_required`, `adapter_contract_unmet`, `adapter_missing_streak`, `cumulative_goal_distance_stalled`, `cumulative_goal_distance_stall_streak`, `untried_veto_overridden_by_chain_stall`
- reachability/metric fields: `acceptance_unreachable_under_frozen_config`, `relaxation_or_escalation_required`, `oracle_metric_validity_gate`
- warn-only fields: `partial_progress_axes_gate` and `advice_freshness_gate.gate_result_regression_stale`
- mutation fields: `blocker_mutation_kind`, `forward_mutation_vacuous`, `forward_mutation_budget_remaining`, `force_implementation_cycle`
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

### Refactor And Behavior-Change Evidence

When a behavior-preserving refactor or consolidation claims structural reduction, `$audit-cycle-loopback` may pass adapter-supplied `structure_metrics_gate.structure_high_water_moved`, `improved_structure_axes`, and `refactor_effect_required`. `$validate-task-completion` must not complete a structural-reduction task from module creation and green tests alone when that gate says high-water did not move.

When a task changes runtime gate, routing, validator, dispatch, or judgment behavior, `$validate-task-completion` must require fresh live before/after evidence, or record an explicit defer gate that leaves follow-up work open. Unit/static evidence alone does not complete behavior-change work whose purpose is to change live outcomes.

### Loop Breaker And Terminal Gates

`scripts/detect_progress_loop.py` produces or contributes loop-breaker evidence. The derive packet must carry normalized `blocker_signature`, additive `semantic_signature`, suffix-normalized `root_key`, root-axis counts, compared cycle IDs, positive input delta status, provider reattempt/mitigation gate status, command-surface budget, sealed-family matches, and zero-candidate state.

When `terminal_escalation_gate.escalation_required=true`, the derive result must emit `selected_task_source: user_escalation`, `forced_disposition: user_escalation`, `terminal_recheck_streak`, `required_missing_input_count: 1`, exactly one `required_missing_input.kind`, and `.task/sealed_blocker_families.json` update or mutation-plan evidence.

When terminal blocking is selected, use the `terminal_blocker` shape in [task-pack-workflow.md](task-pack-workflow.md). Do not write another non-terminal recheck in a sealed family without a supplied input delta, authority change, external-state change, or verified unexhausted root-cause repair.

### Repo Adapter And Gap Packets

Repo adapter packet details are owned by [repo-local-skill-adapters.md](repo-local-skill-adapters.md). The orchestrator passes adapter packets as non-GT capability evidence only.

`repo_skill_gap_packet` should include repeated domain lookup, repeated command/profile discovery, validation/oracle/source-class ambiguity, progress-classification uncertainty, adapter validation failures, task_miss caused by missing repo-specific procedure, recommended adapter name/scope/resources, and defer/reject rationale when not selected.

## Helper Script Surfaces

Helper scripts provide decision-support evidence. They do not replace owning skill judgment.

| Script | Inputs | Output or write surface | Consumers |
| --- | --- | --- | --- |
| `collect_cycle_context.py` | `--root`, optional Git/file limits | Compact JSON for `task.md`, `.agent_goal`, `.agent_advice`, `.task`, `.issue`, `.agent_log`, `.schema`, `.contract`, validation, Git | Context, packets, report |
| `cycle_ledger.py` | `init`, `append`, `render`, `current`; stage JSON or explicit `--step` | `.task/cycle/<cycle-id>/stage.jsonl`, `current_stage.json`, packets, dashboard support | Dashboard, report, transition checks |
| `render_subskill_packet.py` | `--target <phase>`, context/stage evidence | Markdown or JSON packet with routing, required inputs/outputs, GT/advice separation | Every owning subskill |
| `validate_cycle_transition.py` | `--transition <name>`, context/status evidence | Transition `pass|warn|block` findings | Orchestrator before major phases |
| `result_contract.py` | `--target <target>`, `--mode warn|block`, result JSON | Contract findings and ledger-envelope readiness | Orchestrator before advancing stages |
| `code_structure_audit.py` | `--root`, changed-file list or input JSON | Scalar audit packet; no source bodies; no patches | Run, derive, validation, report |
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
- Treat self-reported `produced_domain_delta`, non-empty rows, lineage, gap reports, renamed commands, or metric existence as insufficient for goal-productive progress without strict changed-and-semantic output evidence or independent validated positive evidence.
- Treat `acceptance_diluted=true` as incompatible with final completion. Preserve residual measurable scope instead of consuming the original directive.
- Treat behavior-preserving refactor completion claims as partial when adapter-supplied structure high-water is flat and the original objective was structural reduction.
- Treat runtime behavior-change completion claims as partial when fresh live before/after evidence is required but absent.
- Keep `available_goal_truth` separate from `used_goal_truth`; final `기준 GT` may list only actually used GT.
- Keep `.agent_advice` out of GT and authority. Active advice in scope requires `used_advice` or an explicit defer/reject/not-applicable rationale.
- Keep repo-local adapters out of GT, authority, human approval, and completion evidence.
- Preserve raw subskill statuses in result packets, but write lifecycle statuses such as `complete`, `partial`, `skipped`, `not_applicable`, `blocked`, or `failed` to the ledger.
- Do not let validation-set assets, visible-increment artifacts, dashboard snapshots, or closeout commits replace completion validation.
