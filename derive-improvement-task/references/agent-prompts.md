# Agent Prompts

## Contents

- [Goal alignment inspection request](#goal-alignment-inspection-request)
- [Task miss analysis agent](#task-miss-analysis-agent)
- [Issue goal-fit agent](#issue-goal-fit-agent)
- [Three improvement agents](#three-improvement-agents)
- [Synthesis agent](#synthesis-agent)

## Goal Alignment Inspection Request

Use this request with `$inspect-repo-with-agents`:

```text
Use $inspect-repo-with-agents to critically analyze whether the current repository direction and task planning context align with the `.agent_goal` files.

Agent routing:
- Use Tier 3 `profile_id: derive_inspector`, `model_ref: model_ref:balanced`, and `reasoning_effort: high` for goal/convention alignment inspectors.

Run this as a critical review, not as a confirmation pass. Look first for blockers, mismatches, convention violations, unsupported assumptions, scope creep, contradictions between goal files, missing evidence, and validation blind spots. Do not treat absent evidence as compliance.

Inspect:
- `.agent_goal/final_goal.md`
- `.agent_goal/conventions.md`
- `.agent_goal/goal_architecture.md`
- `.agent_goal/goal_theory.md`
- `$manage-agent-authority` result: `.agent_goal/agent_authority.md` summary or `authority_policy: default_current_agent_permissions`
- `.agent_goal/goal_schema_contract.md`
- `.agent_advice/active/*.md` non-GT direction evidence when present
- `.schema/` and `.contract/` schema/contract records if present
- `.issue/` implementation issue records and GitHub issue mirrors if present
- current `task.md` if present
- `.task/task_miss/` and `.task/candidate_task/` summaries if present
- `.task/task_pack/*.json` active pack summary and Markdown render when present
- caller-supplied loop_breaker_packet when present, including supplied-input delta gate, provider re-attempt gate, command-surface budget, and goal-distance hard-stop status
- relevant repository files

Required perspectives:
1. Final goal and success criteria alignment.
2. Convention/constraint compliance: extract the applicable `.agent_goal/conventions.md` rules, classify each relevant convention as `satisfied`, `violated`, `insufficient_evidence`, or `not_applicable`, and cite evidence.
3. Architecture fit and integration risk.
4. Theory/technical-logic fit and validation assumptions.
5. Agent-authority fit: API/external-call policy, direction freedom, implementation/validation priority, conservative implementation, escalation, and whether proposed directions exceed current effective permissions.
6. Schema-contract-goal fit: minimum fields, application intent, mandatory rules, target modules/scripts, versions, and causal compatibility.
7. External advice fit: whether active advice supports, conflicts with, or is irrelevant to the next-task direction without treating it as GT.
8. Issue goal-fit: whether active implementation issues align with the goal or are stale/misfit/duplicates.
9. Task-miss and candidate-task implications.

Report:
- alignment_verdict: aligned | partial | misaligned | insufficient_evidence
- convention_verdict: satisfied | violated | partial | insufficient_evidence
- recent_progress_pattern: advanced | safety_only | no_progress | regressed | mixed | insufficient_evidence
- blocker and high-risk findings first, before supportive alignment notes
- convention assessment table with evidence and impact
- authority assessment table with evidence and impact
- advice assessment table with status `incorporate | defer | reject | not_applicable`
- unsupported assumptions and missing evidence
- concrete findings with file/line evidence where possible
- recommended improvement directions and constraints for downstream improvement agents
- any repeated no-live or safety-only task pattern that should constrain the next task
- whether active task-pack order should be promoted, inserted before, reordered, superseded, or terminal-blocked
```

## Task Miss Analysis Agent

```text
You are analyzing `.task/task_miss/` to support the next `task.md`.

Agent routing:
- Use Tier 3 `profile_id: derive_inspector`, `model_ref: model_ref:balanced`, and `reasoning_effort: high`.

Review the provided task_miss reports and resolved/deleted records. Do not edit files.

Report:
1. Active unresolved misses.
2. Recurring miss patterns.
3. Generalization gaps and under-tested cases.
4. Resolved or obsolete misses that should not drive new work.
5. Highest-value improvement themes.
6. Candidate tasks implied by the miss history.
7. Whether recent misses indicate `advanced`, `safety_only`, `no_progress`, or `regressed` workflow progress.
8. Micro-contract candidates that should be batched instead of selected as isolated sequential tasks.
9. Any repeated blocker signature or missing positive input delta that should terminal-block or reorder a task pack.
```

## Issue Goal-Fit Agent

Use exactly one issue agent before the three improvement agents. Use the prompt from `$manage-implementation-issues` when available.

If issue-fit execution is unavailable, record `issue_fit.status: unavailable`, a bounded reason, and evidence IDs in the frozen evidence manifest. Continue evaluating non-issue candidates. Treat only candidates with `issue_derived: true` as unselectable; do not degrade unrelated repository-, goal-, miss-, or validation-derived candidates.

```text
Analyze `.issue/` local records, GitHub issue mirrors, and issue-related task index links before improvement candidates are generated.

Agent routing:
- Use Tier 3 `profile_id: issue_fit`, `model_ref: model_ref:balanced`, and `reasoning_effort: high`.

Classify each active issue against `.agent_goal` and current task direction:
- goal_fit: fit | partial | misfit | unknown
- should_influence_next_task: yes | no with reason
- issue_progress_state: unblocked | blocked | safety_only_evidenced | no_progress | unknown
- blocker_signature when identifiable
- related task/candidate/miss/validation evidence
- duplicate, stale, blocked, or already resolved status
- handoff note for improvement-analysis agents
- external advice relevance when active advice is present: incorporate | defer | reject | not_applicable

Do not edit files. Do not open, close, or modify issues.
```

## Three Improvement Agents

Freeze one `shared_evidence_manifest` before fanout. Bind cycle/task/attempt and input-state fingerprint. Legacy artifact identity remains valid unchanged. For the explicit form, bind subject/class/revision/full digest/lineage/freshness and all four applicability objects for body, lane, cohort, and producer run. The adapter packet carries the exact same reference; the post-use seal echoes exact subject fields and only applicable dimension values. Freeze active advice in `active_advice_clause_set` with the exact sorted actionable clause IDs, packet digest, per-clause source digests, and clause-set digest. If none is active, use the closed `not_applicable` form with an opaque reason and evidence IDs. Hash the canonical body. Missing or mismatched applicable values stop fanout; a declared `not_applicable` dimension is a normal bypass. If a registered adapter lacks a passing context or consumed-value seal, stop before fanout. An evidenced empty adapter registry may use explicit adapter `not_applicable`.

Run exactly three read-only agents in parallel. Give every agent the identical manifest digest and no sibling output. Use the canonical roles `goal_value`, `architecture_contract`, and `miss_validation`, and assign a unique opaque `agent_receipt_id` to each execution.

Spawn each improvement-analysis agent at Tier 3 with `profile_id: derive_inspector`, `model_ref: model_ref:balanced`, and `reasoning_effort: high`.

Every agent must return a structured receipt containing its role and receipt ID, the identical input digest, `read_only: true`, `status: complete`, an output ref/hash, and an output with `candidates`, `rejection_inventory`, `advice_clause_set_sha256`, and `advice_clause_assessments`. Return zero through five candidates. When zero are viable, enumerate reviewed options with unique option ID, rejection reason code, and evidence IDs instead of fabricating candidates. The advice assessment list must cover all and only the frozen actionable clause IDs in sorted order. Each row binds the clause ID, this lens's agent/receipt IDs, `incorporated|deferred|tested|rejected`, evidence IDs, related candidate IDs, and a canonical assessment digest. Empty advice uses the exact empty list; prose about the advice container is not clause consumption.

Each candidate must include `candidate_id`, exact-subject fingerprint, first-failing invariant, one canonical owner, task kind, expected blocker transition, `actionability: actionable|blocked_external|blocked_authority|unverified`, `issue_derived`, evidence IDs, validation IDs, and a `pack_disposition` from [the canonical derive selection contract](../../orchestrate-task-cycle/references/derive-selection-contract.json).

### Agent 1: Goal Fit (`goal_value`)

```text
Analyze improvement candidates through the lens of final goal, success criteria, and user value.

Agent routing:
- Use Tier 3 `profile_id: derive_inspector`, `model_ref: model_ref:balanced`, and `reasoning_effort: high`.

Return 0-5 viable candidates using the common structured receipt. For each:
- title
- problem addressed
- goal link
- issue link or ignored issue rationale
- schema contract link
- authority policy link
- external advice link or ignored advice rationale
- expected impact
- expected_progress_verdict: advanced | safety_only | no_progress | regressed
- progress_kind: goal_productive | governance_only
- semantic_signature when the candidate belongs to a repeated or sealed blocker family
- blocker_state_transition
- validation_profile: current_only | affected_chain | full_chain
- scope
- validation
- risks
- goal/convention blocker handled or avoided
- pack_disposition: use the canonical derive selection contract; do not invent aliases
- positive_input_delta: new input kind introduced plus non-empty supplied artifact path or `produced_domain_delta=true`, or why no delta is needed
- scope_fidelity: affected measurable directive IDs, original target preservation, narrowed/descope status, and residual item needed
- acceptance_verifier: required verifier status for measurable targets, especially `not_evaluated` verifier debt that must remain open or become the task
- required_gate_hooks: whether an acceptance-referenced gate has absent, fail-quiet, or `not_evaluated` adapter hooks that must become hook-supply work or remain residual
- goal_axis_completeness: whether review-backed measurable goals have mapped observing axes, or require axis-supply/residual handling because `pass_with_unobserved_axes=true`
- count_key_hygiene: whether repeated-family evidence uses generation-independent effective keys instead of task/advice/pack/cycle/run/date/hash/version labels
- failure_surface_stage: whether terminal classification agrees with the observed failure surface stage and same-input contract, or requires classification/input-contract repair
- instrumentation_supply: whether repeated `diagnostics_unavailable` requires instrumentation supply or an observability rationale
- verification_source_separation: whether independently verified evidence has disjoint verification input paths or should be treated as attested
- envelope_thaw: whether frozen-envelope-unreachable acceptance requires an `envelope_thaw_item`, thaw condition/schedule, residual descope, terminal blocker, or user escalation
- residual_value_per_cycle_cost: whether same-gap repair outranks descope plus next rung by value per cycle cost, or should be deferred/descoped
- Part L constraints: stale-lane pass, stale decision measurement, missing-producer gating axis, restrictive verifier-like portfolio quota, cycle-unreachable scale, basis-overclaimed metric, or surface-field defect matrix that changes the candidate order or residual work
- authority conflict handled or avoided
- advice conflict handled, deferred, or marked not_applicable
- should_be_next_task: yes/no with reason
```

### Agent 2: Architecture And Theory Fit (`architecture_contract`)

```text
Analyze improvement candidates through architecture, technical logic, maintainability, and design fit.

Agent routing:
- Use Tier 3 `profile_id: derive_inspector`, `model_ref: model_ref:balanced`, and `reasoning_effort: high`.

Return 0-5 viable candidates using the common structured receipt. For each:
- title
- architecture/theory link
- issue-fit implication
- schema-contract-goal link
- authority-policy implication
- external-advice implication
- affected components
- design risk
- schema/contract compatibility risk
- generalization risk
- convention compliance risk
- authority compliance risk
- advice compliance risk
- expected_progress_verdict: advanced | safety_only | no_progress | regressed
- progress_kind: goal_productive | governance_only
- blocker_state_transition
- validation_profile: current_only | affected_chain | full_chain
- prerequisite surfaces that justify `affected_chain` or `full_chain`, if any
- validation
- pack_disposition: use the canonical derive selection contract; do not invent aliases
- blocker_signature, semantic_signature, sealed-family, goal-distance, and input-delta implications
- count-key implications: effective root/dominant-parameter key or terminal-outcome fallback when raw generated labels changed
- structure_high_water_key_scope: whether any structure proposal moves adapter-owned global invariants or only a selected local scope
- goal-axis and residual-cost implications: missing observing axes, required adapter hook supply, or below-policy value per cycle cost that changes task order
- Part H implications: failure-surface/terminal-classification mismatch, same-input mismatch, instrumentation supply trigger, non-disjoint independent verification, or missing frozen-envelope thaw item
- Part L implications: lane identity mismatch, fresh-measurement need after upstream contract change, producer path absence for gating axes, verifier-like portfolio excess, cycle-scale reachability, metric basis derivability, or source-locator surface-field review coverage
- should_be_next_task: yes/no with reason
```

### Agent 3: Miss And Candidate Fit (`miss_validation`)

```text
Analyze improvement candidates through `.task/task_miss/`, `.task/candidate_task/`, validation gaps, and residual risk.

Agent routing:
- Use Tier 3 `profile_id: derive_inspector`, `model_ref: model_ref:balanced`, and `reasoning_effort: high`.

Return 0-5 viable candidates using the common structured receipt. For each:
- title
- source miss or candidate
- source issue or issue-fit finding
- source advice or advice-fit finding
- schema/contract relevance
- urgency
- unresolved risk addressed
- blocked/unblocked status
- convention conflict or insufficient-evidence note
- authority conflict or insufficient-evidence note
- advice conflict, deferral, or not-applicable note
- expected_progress_verdict: advanced | safety_only | no_progress | regressed
- progress_kind: goal_productive | governance_only
- semantic_signature when the miss/candidate belongs to a repeated or sealed blocker family
- blocker_state_transition
- validation_profile: current_only | affected_chain | full_chain
- batchability with related no-live or micro-contract candidates
- pack_disposition: use the canonical derive selection contract; do not invent aliases
- whether active pack order should change and why
- acceptance_verifier risk: required verifier missing, failed, or `not_evaluated`
- required gate-hook risk: acceptance-referenced gate hooks absent, fail-quiet, or `not_evaluated`
- pass_with_unobserved_axes risk: measurable review target has zero mapped observing axes
- residual cost risk: same-gap repair value per cycle cost is below policy or missing denominator
- Part H risk: terminal-stage contradiction, same-input mismatch, diagnostics unavailable without instrumentation, non-disjoint independent verification, or frozen-envelope thaw debt
- Part L risk: stale-lane validation, stale decision reclassification, starved gating-axis producer, quota-excess verifier-like work, cycle-unreachable target, metric basis overclaim, or unresolved surface-field defect counts
- validation
- should_be_next_task: yes/no with reason
```

## Synthesis Agent

```text
You are synthesizing the final next `task.md`.

Agent routing:
- Use Tier 5 `profile_id: derive_synthesis`, `model_ref: model_ref:direction`, and `reasoning_effort: xhigh`; this agent owns final next-task, pack-topology, and terminal-disposition direction.
- If this pass leaves an allowed high-impact ambiguity, one bounded Tier 5 direction-profile/max arbitration may follow only with `prior_tier5_unresolved: true`, `prior_tier5_evidence` pointing to this pass and finding, `max_escalation_reason`, and `agent_count: 1`. Do not use `ultra`.

Inputs:
- critical goal/convention alignment inspection
- `$manage-agent-authority` result: `.agent_goal/agent_authority.md` summary or `authority_policy: default_current_agent_permissions`
- `.agent_goal/goal_schema_contract.md` and `.schema/.contract` evidence when present
- active `.agent_advice` packet as non-GT direction evidence when present
- active `.task/task_pack` packet and Markdown render when present
- loop_breaker_packet: blocker signatures, semantic signatures, same-signature counts, same-semantic-family counts, sealed-family matches, goal-distance gate, governance-only streak, positive input delta gate with `has_supplied_input_delta` and `supplied_input_artifact_paths`, provider re-attempt gate, command-surface budget, terminal blocker recommendation
- output_delta_packet, qualitative_review_packet, and anti_loop_progress_gate: `changed_vs_previous`, `semantic_progress`, semantic readiness/cap fields, `substance_delta_gate`, `vacuous_corrective_gate`, `adapter_mandate_required`, `cumulative_goal_distance_stalled`, `root_dominant_parameter_key`, `failure_surface_stage_gate`, `failure_surface_stage`, `terminal_classification_stage_contradiction`, `same_input_contract_gate`, `diagnostics_unavailable_gate`, `instrumentation_supply_required`, `verification_source_separation_gate`, `independent_source_separation_status`, `independently_verified_downgraded_fields`, `primary_metric_gate`, `primary_metric_stalled`, `c4_user_escalation_backstop_required`, `pass_with_coupled_verifier`, `coupled_verifier_gate`, `changed_verifier_source_paths`, `evidence_provenance_gate`, `independently_verified_fields`, `producer_attested_fields`, `attested_only_movement`, `residual_gap_ratio`, `residual_gap_policy`, `marginal_repair`, `cycle_fixed_cost`, `marginal_value_per_cycle_cost`, `residual_gap_cost_policy`, `generation_dependent_count_key`, `effective_count_key`, `terminal_outcome_family_key`, `goal_axis_completeness_gate`, `unobserved_goal_axes`, `pass_with_unobserved_axes`, required gate-hook status, `untried_veto_overridden_by_chain_stall`, `acceptance_envelope_contract`, `envelope_below_floor`, `acceptance_unreachable_under_frozen_config`, `envelope_thaw_item_required`, `envelope_thaw_item`, `oracle_metric_validity_gate`, Part L fields (`production_lane_identity`, `current_decision_lane`, `pass_on_stale_lane`, `decision_metadata_revision`, `axis_starved_by_missing_producer`, `portfolio_quota_exceeded`, `unreachable_within_cycle`, `basis_overclaim`, `surface_field_defect_matrix`), `observed_producer_claim`, `split_brain_progress_claim`, `advice_freshness_gate`, `repo_owned_source_roots_status`, provenance-hardened root-cause entries, provider/env behavior booleans, same-family micro-hardening count, command-surface hard-stop state, and allowed dispositions
- issue goal-fit report from `$manage-implementation-issues`
- task_miss analysis
- candidate_task analysis
- three improvement-agent reports
- the frozen shared-evidence digest and exactly three validated execution receipts
- current task.md if present
- mode: replacement | initial_init
- previous task.md execution-environment section if present
- environment discovery result from $find-local-python-envs when needed

Tasks:
1. Build the exact deduplicated union of validated lens candidate IDs. Select only an actionable member of that union, or emit `terminal_wait`, `terminal_blocked`, or `user_escalation` when no actionable member remains.
2. Explain why it outranks alternatives.
3. Produce final `task.md` content using the template, with `## Execution Environment` immediately after `# Task`.
4. List unselected candidates that should be saved under `.task/candidate_task/`.
5. List existing candidate_task files that should be deleted because they were applied.
6. Include issue IDs, GitHub URLs, or `.issue/` paths that the selected task tracks or explicitly ignores.
7. Include `.schema` and `.contract` update requirements when the selected task affects schemas, module/script contracts, or causal compatibility.
8. Include the effective authority policy in the generated `## Execution Environment` and explain any API/external-call, direction-freedom, conservative-implementation, validation-priority, or escalation constraint that affects the selected task.
9. Include `External Advice` in the generated `## Execution Environment`: list used `adv-*` IDs/paths or `none`, and explain whether each active advice item is incorporated, deferred, rejected, or not applicable. Reconcile every frozen actionable clause against all three lens-assessment digests and emit exact clause rows with final disposition, evidence IDs, selected candidate IDs, and canonical row/set digests.
10. Choose exactly one canonical disposition from [derive-selection-contract.json](../../orchestrate-task-cycle/references/derive-selection-contract.json). Never emit legacy aliases in a new receipt.
11. If writing or updating a task pack, produce canonical JSON content plus the user-language Markdown render requirement. New sequences contain 2-5 newly derived items. A replacement over five total items may add at most five new items and must identify every excess item as exact planning-contract carry-forward in predecessor-relative order. Do not relabel an old ID as new or omit a nonterminal predecessor item; carry it exactly or declare an evidence-hash-bound retirement. Use the helper-owned replacement transaction rather than separate supersede/create writes.
12. Include `progress_kind: goal_productive|governance_only` and the selected or terminal `semantic_signature` in the derive result.
13. If mode is `initial_init`, state that no `past_task` archive is required because no previous task.md exists.

Selection constraints:
- Emit three lens receipts with three distinct opaque `agent_id` values and unique receipt IDs. Emit one synthesis receipt with a fourth distinct opaque agent ID that echoes the frozen input digest, consumes all and only the three unique lens receipt IDs, binds the exact candidate-union IDs/digest, and records `selected_candidate_id`, `selection_outcome`, and canonical `pack_disposition`. It must also echo the exact advice clause-set digest, consume the three assessment digests per clause, and bind the reconciliation-set digest. Persist three closed lens receipt projections containing each exact output plus identity/status/input/ref/digest fields and the canonical synthesis-output projection as four distinct compact canonical JSON files under `.task/cycle/<cycle-id>/agent_receipts/`; only a `durable_runtime_artifact_bound` receipt rebuilt after reopening those safe regular non-symlink files may produce `wired` rows.
- Do not claim advice `verified` from synthesis alone. Verification requires fresh happy and negative forward producer artifacts bound to the current clause-set/synthesis-output digests plus distinct verifier receipts and invariant owners. Persist each exact producer output and complete outer forward receipt in the same cycle-local store and validate them using the workspace root. Require negative expected/observed decision state to differ from happy state. Verifier input/invariant IDs must be disjoint from producer preconditions/evidence. The artifact store proves exact durable bytes and distinct declared IDs, not cryptographic process identity; therefore still perform actual agent delegation. Reused identities, coupled evidence, a no-op negative path, self-hashed booleans, stale inputs, missing files, arbitrary refs, path escape, or symlinks leave the clause at `wired` or `pending`.
- Do not use majority vote. Deduplicate by exact subject, first-failing invariant, canonical owner, task kind, and blocker transition; rank evidence and actionability. GT, authority, safety, and schema violations are vetoes.
- Keep `selected`, `terminal_wait`, `terminal_blocked`, and `user_escalation` disjoint. `terminal_wait` requires watched evidence, the fixed executable wake-rule ID, policy-label predicates/delta, locked premise-input contract, the frozen analysis digest, and a separately hash-bound safe `selection-tick` baseline packet whose watched-input digest drives re-entry; never use the analysis digest as that tick baseline. Treat exact-premise and effective-authority rows as sticky; an identical premise plus only nonmaterial drift is `no_op`. If this fanout was opened by `selection_required`, name the activated predecessor `A`, the exact trigger `B`, and the input-stable rebased packet `C`. Persist the three lens projections and canonical synthesis-output projection, reopen those four artifacts into `derive_selection_synthesis`, bind it to `B` in a preliminary decision, and bind persisted `B` plus that decision in a selection-decision receipt. Validate the entire chain before acknowledging `B`; require `B` to descend from `A`, `C` to descend unchanged from `B`, and `last_selection_receipt` to equal the closed eight-field acknowledgement binding's receipt ID. Then emit a direct full final derive result that embeds `C` and the receipt-reopened analysis. A raw exact-file digest is not semantic freshness or canonical-owner proof; an arbitrary ID/hash pair, preliminary decision, receipt, partial projection, or `{ "result": ... }` wrapper is not a valid terminal source. `terminal_blocked` requires justified hard-stop evidence; user escalation requires a bounded requested input or authority. Never combine their fields.
- Do not publish a selection, terminal seal, escalation, or pack mutation from fewer than three valid lens receipts. A fanout limitation is an incomplete analysis, not a degraded substitute for independent evidence.
- Keep `progress_target` in `advanced|safety_only|no_progress|regressed` and expected progress kind in `goal_productive|governance_only`. Put labels such as `workflow_capability`, `artifact_truth_only`, or artifact-truth verification in open `item_kind`, preserve the source target in `scope_fidelity`, and do not propose enum expansion or a shadow expected-progress field.
- Before recommending archive/publication, require a finding-free dry-run over the exact deterministic task/pack inputs. Replacement must reuse those bytes and recover any pending helper journal. The task-pack helper is atomic only for its pack-owned targets; publish the selected `task.md` plus archive/index/pack projections through the orchestrator's `selection-publication` exact-before/after journal, and require its committed receipt before consumption. Git remains outside both publication transactions and cannot substitute for either receipt.
- Do not select a task that conflicts with `.agent_goal/final_goal.md` or `.agent_goal/conventions.md` unless the selected task explicitly resolves that conflict.
- Do not select a task that conflicts with the `$manage-agent-authority` result unless the selected task explicitly resolves that conflict. If the authority file is absent, do not infer permission beyond `default_current_agent_permissions`.
- Do not select a task that treats `.agent_advice` as GT or authority. If active advice is incompatible with GT, authority, current user direction, or repo facts, reject or defer it explicitly.
- Do not downgrade convention violations into generic risk notes.
- Do not downgrade authority violations into generic risk notes.
- Treat `insufficient_evidence` as an open validation or discovery requirement in the generated task.
- Prefer a task that moves a blocker or goal state forward over another isolated no-live safety proof.
- If an evaluated same-blocker recurrence gate reaches its supplied `safety_only` budget, select evidence supply, bounded preflight/run, or a batched boundary task unless that is explicitly blocked. Without an evaluated budget, use the sequence only for ranking.
- If the bounded current task is complete, no successor is justified, and global readiness is blocked or waiting, emit the completed identity with no successor and do not select that same identity again. Preserve the mutable alias as non-executable current history.
- Do not select a sequential micro-contract only because it is next in order; batch it with adjacent checks when target, issue, prerequisite chain, and validation surface are the same.
- If recent cycles repeat the same normalized blocker signature, do not select another narrowing/handoff task unless a new input kind, authority change, external-state change, or safe pack item changes the state.
- If the only novelty is task/advice/pack/cycle/run/date/hash/version label churn, preserve it as trace-only and select using the effective count key or terminal-outcome family fallback.
- If a required gate hook for measurable acceptance is absent, fail-quiet, or `not_evaluated`, select hook-supply/verifier correction, explicit residual descope, terminal blocker, or user escalation; do not consume the target as goal-productive.
- If `pass_with_unobserved_axes=true`, select adapter axis supply, output-producing work that supplies the missing observable axis, explicit residual descope, terminal blocker, or user escalation; do not consume the qualitative review as pass evidence.
- If `terminal_classification_stage_contradiction=true`, `terminal_classification_invalid_for_counting=true`, or `same_input_contract_violation=true`, select classification-stage/input-contract repair, instrumentation supply, terminal blocker, or user escalation; do not close/count the family.
- If `instrumentation_supply_required=true`, select instrumentation supply or record why success/failure is already observable without new instrumentation.
- If `independent_source_separation_status=missing|overlap|blocked` or `independently_verified_downgraded_fields` is nonempty, treat those fields as attested and do not select `goal_productive` from them.
- If `envelope_thaw_item_required=true`, select/reserve `envelope_thaw_item`, constraint relaxation, residual descope, terminal blocker, or user escalation before ordinary repair.
- If residual value per cycle cost is below policy, prefer descope-with-residual plus the next capability rung unless a higher value case is recorded.
- If recent cycles repeat the same suffix-normalized root key or semantic signature, treat it as the same blocker family even when target-surface, run names, dates, or `vN` suffixes changed.
- If the goal-distance gate requires goal-productive work, select `progress_kind: goal_productive` or emit terminal blocker state; do not select another governance-only sidecar/reconciliation task.
- If the progress-loop detector status is `block`, select `progress_kind: goal_productive` or emit terminal blocker state with provider-track and provider-neutral/quality-track attempt evidence.
- If provider mitigation is required, do not terminal-seal provider failure while required mitigations remain missing. If provider re-attempt is required, select bounded provider retry/probe work and set `provider_reattempt_disposition`.
- If output-delta evidence lacks `changed_vs_previous=true` and `semantic_progress=true`, treat non-empty counts, lineage, gap reports, or workflow metadata as `governance_only` unless independent validated positive evidence exists.
- Treat `observed_producer_claim` as trace-only. If `split_brain_progress_claim=true`, use adapter/output-delta truth, preserve residual work, or terminal/user-escalate rather than citing the producer claim.
- If qualitative review caps progress because semantic output is not ready, placeholder events were found, or surface entities are suspected, preserve that cap unless strict changed-and-semantic output-delta evidence overrides it.
- If anti-loop evidence reports `substance_delta_gate.substance_delta_pass=false` or `status=missing`, do not treat validator/oracle/metric existence or capability-ladder observation as `goal_productive` unless strict changed-and-semantic primary-output evidence exists.
- If `acceptance_envelope_contract.envelope_below_floor=true`, select envelope expansion, explicit descope with residual scope, terminal blocker, or user escalation; do not choose envelope-internal work as `goal_productive`.
- If `acceptance_verifier_contract` or loopback evidence reports a required verifier with `evaluation_status: not_evaluated`, select verifier implementation/correction, explicit descope with residual scope, terminal blocker, or user escalation; do not consume the measurable target.
- If `root_dominant_parameter_key` is present, proximate root-cause label changes are not distinct untried repairs for the same collapsed root and dominant parameter.
- If `primary_metric_stalled=true` or `primary_metric_gate.primary_metric_stalled=true`, apply the forced-retarget rule; if `c4_user_escalation_backstop_required=true`, select user escalation unless an actionable forced option exists.
- If `pass_with_coupled_verifier=true`, do not cite the coupled verifier pass as completion, semantic progress, high-water movement, or `goal_productive`; select non-coupled revalidation, independent recalculation, explicit residual descope, terminal-block, or user escalation.
- If `attested_only_movement=true` or only `producer_attested_fields` moved, treat the movement as no high-water progress. Do not reset stalls, avoid C4, or satisfy `goal_productive` from producer-attested scalar movement.
- If `residual_gap_policy` marks a below-threshold residual gap or `marginal_repair=true`, rank explicit descope-with-residual plus the next capability-ladder rung ahead of another same-gap repair unless the candidate records higher marginal value.
- If anti-loop evidence reports `vacuous_corrective_gate.surface_corrective_noop=true`, do not count attempted corrective/backfill rows as output delta; select lane-resolving correction work, terminal-block, or user escalation.
- If root-cause actionability was derived from repo-owned source provenance, do not trust conflicting producer self-report fields such as `local=false`, `in_scope=false`, or `actionable=false`.
- If anti-loop evidence reports `advice_freshness_gate.advice_metrics_stale=true`, refresh, defer, reject, or justify any use of that advice against current raw evidence.
- If command-surface budget requires consolidation, register or select a consolidation candidate unless strict changed-and-semantic primary-output evidence already justifies goal-productive work, or the result is terminal/user escalation.
- If `structure_high_water_key_scope=global_invariant`, require global invariant movement before classifying structure work as goal-productive; local selected-scope improvement alone is governance-only unless residual global scope remains open.
- If `pass_on_stale_lane=true`, select current-lane rerun/revalidation, explicit residual descope, terminal blocker, or user escalation before consuming capability/adoption/comparison evidence.
- If `decision_metadata_revision=true` or `stale_measurement_artifact=true`, select fresh current-lane measurement or no-impact proof before consuming decision/adoption work as measurement progress.
- If `axis_starved_by_missing_producer=true`, select producer-supply work before another verifier/guard/report for that axis.
- If restrictive `portfolio_quota_exceeded=true`, select producer, envelope, long-run, descope, terminal blocker, or user escalation until quota recovers.
- If `unreachable_within_cycle=true`, select long-run launch/monitor/harvest, throughput improvement, explicit residual descope, terminal blocker, or user escalation instead of another small smoke.
- If `basis_overclaim=true`, select basis-compatible measurement, metric-basis repair, contract downgrade with residual scope, or terminal/user escalation before using the metric as independent progress.
- If `surface_field_defect_matrix` has unresolved nonzero counts, select producer/field repair, residual descope, terminal blocker, or user escalation before consuming the review pass for those fields.
- If anti-loop evidence shows 3 same-family micro-hardening tasks, block another same-family micro task as `goal_productive`; choose provider/semantic transition, consolidation, supplied-input/domain-delta work, or terminal/user escalation.
- If a semantic family is sealed, do not select another non-terminal task in that family unless you name the new input kind, authority change, or external-state change that reopens it.
- If `positive_input_delta_required` is true, name the newly introduced input kind and the supplied artifact path or `produced_domain_delta=true`. If no supplied delta exists, terminal-block or select a task that obtains the missing input.
- If a candidate derives from a measurable directive, preserve the original target in `scope_fidelity`; if narrowed, require explicit descope plus an open residual item. Do not call a pilot/plan/slice complete against a weaker target.
- Before terminal-blocking or sealing, verify no authority-permitted productive alternative path remains unattempted.
- If zero actionable standalone candidates and pack items remain, use `terminal_wait` with a named policy-label wake predicate plus the fixed executable wake rule, `user_escalation` for a bounded missing input/authority request, or `terminal_blocked` only for a justified hard stop with exhausted alternatives. For a rebased wait, settle and activate only after the four runtime artifacts, durable synthesis, preliminary decision, selection-decision receipt, `C`, and direct full final derive result are durable and the authority subject binds predecessor `A`; an unactivated prepare/completion is not current. Do not invent work or combine outcome fields.

Execution environment rules:
- Reuse the previous task.md environment only when it is explicit and still applies.
- If environment info is absent for a Python task, use the provided `$find-local-python-envs` result.
- Prefer conda first, venv second, local/system Python third.
- Include status, source, type, name/path, Python/interpreter, run prefix, and dependency notes.
- Include `Progress Target`, `Validation Profile`, and prerequisite manifest/check-hash summary when historical prerequisites are reused.
- Include `Authority Policy` from the `$manage-agent-authority` result: `.agent_goal/agent_authority.md` when present, otherwise `default_current_agent_permissions`.
- Include `External Advice` from active `.agent_advice` when it influenced requirements, constraints, design, or validation; otherwise use `none`.
- Include `Task Pack`, `Task Pack Item`, `Pack Position`, and `Pack Source`; use `none` for standalone tasks.
- Use `current_only` by default for a localized current task, `affected_chain` when an upstream prerequisite changed, and `full_chain` only for live dispatch, readiness promotion, shared runtime/validator changes, issue closure, or explicit user request.
- If no usable environment exists, mark `Status: unresolved` and make it a visible prerequisite.
- If no Python/code execution is required, mark `Status: not_applicable`.

Do not invent requirements. Mark assumptions and open questions explicitly.
```
