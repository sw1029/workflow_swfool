# Agent Prompts

## Goal Alignment Inspection Request

Use this request with `$inspect-repo-with-agents`:

```text
Use $inspect-repo-with-agents to critically analyze whether the current repository direction and task planning context align with the `.agent_goal` files.

Agent routing:
- Use fixed `reasoning_effort: xhigh` for all goal/convention alignment inspectors when the tooling exposes reasoning effort.

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
- Use fixed `reasoning_effort: xhigh`.

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

```text
Analyze `.issue/` local records, GitHub issue mirrors, and issue-related task index links before improvement candidates are generated.

Agent routing:
- Use fixed `reasoning_effort: xhigh`.

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

Run these three in parallel with the same evidence package, including the critical goal/convention alignment report and the issue goal-fit report.

Spawn each improvement-analysis agent with fixed `reasoning_effort: xhigh`.

### Agent 1: Goal Fit

```text
Analyze improvement candidates through the lens of final goal, success criteria, and user value.

Agent routing:
- Use fixed `reasoning_effort: xhigh`.

Return 3-5 candidates. For each:
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
- task_pack_disposition: standalone | promote_pack_item | insert_pack_item | reorder_pack | terminal_block_pack | not_applicable
- positive_input_delta: new input kind introduced plus non-empty supplied artifact path or `produced_domain_delta=true`, or why no delta is needed
- authority conflict handled or avoided
- advice conflict handled, deferred, or marked not_applicable
- should_be_next_task: yes/no with reason
```

### Agent 2: Architecture And Theory Fit

```text
Analyze improvement candidates through architecture, technical logic, maintainability, and design fit.

Agent routing:
- Use fixed `reasoning_effort: xhigh`.

Return 3-5 candidates. For each:
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
- task_pack_disposition: standalone | promote_pack_item | insert_pack_item | reorder_pack | terminal_block_pack | not_applicable
- blocker_signature, semantic_signature, sealed-family, goal-distance, and input-delta implications
- should_be_next_task: yes/no with reason
```

### Agent 3: Miss And Candidate Fit

```text
Analyze improvement candidates through `.task/task_miss/`, `.task/candidate_task/`, validation gaps, and residual risk.

Agent routing:
- Use fixed `reasoning_effort: xhigh`.

Return 3-5 candidates. For each:
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
- task_pack_disposition: standalone | promote_pack_item | insert_pack_item | reorder_pack | terminal_block_pack | not_applicable
- whether active pack order should change and why
- validation
- should_be_next_task: yes/no with reason
```

## Synthesis Agent

```text
You are synthesizing the final next `task.md`.

Agent routing:
- Use fixed `reasoning_effort: xhigh`.

Inputs:
- critical goal/convention alignment inspection
- `$manage-agent-authority` result: `.agent_goal/agent_authority.md` summary or `authority_policy: default_current_agent_permissions`
- `.agent_goal/goal_schema_contract.md` and `.schema/.contract` evidence when present
- active `.agent_advice` packet as non-GT direction evidence when present
- active `.task/task_pack` packet and Markdown render when present
- loop_breaker_packet: blocker signatures, semantic signatures, same-signature counts, same-semantic-family counts, sealed-family matches, goal-distance gate, governance-only streak, positive input delta gate with `has_supplied_input_delta` and `supplied_input_artifact_paths`, provider re-attempt gate, command-surface budget, terminal blocker recommendation
- output_delta_packet, qualitative_review_packet, and anti_loop_progress_gate: `changed_vs_previous`, `semantic_progress`, semantic readiness/cap fields, `substance_delta_gate`, `vacuous_corrective_gate`, `advice_freshness_gate`, provider/env behavior booleans, same-family micro-hardening count, command-surface hard-stop state, and allowed dispositions
- issue goal-fit report from `$manage-implementation-issues`
- task_miss analysis
- candidate_task analysis
- three improvement-agent reports
- current task.md if present
- mode: replacement | initial_init
- previous task.md execution-environment section if present
- environment discovery result from $find-local-python-envs when needed

Tasks:
1. Select exactly one improvement as the next `task.md`, or emit terminal blocker state when no viable task remains.
2. Explain why it outranks alternatives.
3. Produce final `task.md` content using the template, with `## Execution Environment` immediately after `# Task`.
4. List unselected candidates that should be saved under `.task/candidate_task/`.
5. List existing candidate_task files that should be deleted because they were applied.
6. Include issue IDs, GitHub URLs, or `.issue/` paths that the selected task tracks or explicitly ignores.
7. Include `.schema` and `.contract` update requirements when the selected task affects schemas, module/script contracts, or causal compatibility.
8. Include the effective authority policy in the generated `## Execution Environment` and explain any API/external-call, direction-freedom, conservative-implementation, validation-priority, or escalation constraint that affects the selected task.
9. Include `External Advice` in the generated `## Execution Environment`: list used `adv-*` IDs/paths or `none`, and explain whether each active advice item is incorporated, deferred, rejected, or not applicable.
10. If an active task pack exists, choose one disposition: `promote_next_item`, `insert_item`, `reorder_items`, `supersede_pack`, `derive_standalone`, or `terminal_blocked`.
11. If writing or updating a task pack, produce canonical JSON content plus the user-language Markdown render requirement.
12. Include `progress_kind: goal_productive|governance_only` and the selected or terminal `semantic_signature` in the derive result.
13. If mode is `initial_init`, state that no `past_task` archive is required because no previous task.md exists.

Selection constraints:
- Do not select a task that conflicts with `.agent_goal/final_goal.md` or `.agent_goal/conventions.md` unless the selected task explicitly resolves that conflict.
- Do not select a task that conflicts with the `$manage-agent-authority` result unless the selected task explicitly resolves that conflict. If the authority file is absent, do not infer permission beyond `default_current_agent_permissions`.
- Do not select a task that treats `.agent_advice` as GT or authority. If active advice is incompatible with GT, authority, current user direction, or repo facts, reject or defer it explicitly.
- Do not downgrade convention violations into generic risk notes.
- Do not downgrade authority violations into generic risk notes.
- Treat `insufficient_evidence` as an open validation or discovery requirement in the generated task.
- Prefer a task that moves a blocker or goal state forward over another isolated no-live safety proof.
- If the last two completed tasks were `safety_only` for the same blocker, select evidence supply, bounded preflight/run, or a batched boundary task unless that is explicitly blocked.
- Do not select a sequential micro-contract only because it is next in order; batch it with adjacent checks when target, issue, prerequisite chain, and validation surface are the same.
- If recent cycles repeat the same normalized blocker signature, do not select another narrowing/handoff task unless a new input kind, authority change, external-state change, or safe pack item changes the state.
- If recent cycles repeat the same suffix-normalized root key or semantic signature, treat it as the same blocker family even when target-surface, run names, dates, or `vN` suffixes changed.
- If the goal-distance gate requires goal-productive work, select `progress_kind: goal_productive` or emit terminal blocker state; do not select another governance-only sidecar/reconciliation task.
- If the progress-loop detector status is `block`, select `progress_kind: goal_productive` or emit terminal blocker state with provider-track and provider-neutral/quality-track attempt evidence.
- If provider mitigation is required, do not terminal-seal provider failure while required mitigations remain missing. If provider re-attempt is required, select bounded provider retry/probe work and set `provider_reattempt_disposition`.
- If output-delta evidence lacks `changed_vs_previous=true` and `semantic_progress=true`, treat non-empty counts, lineage, gap reports, or workflow metadata as `governance_only` unless independent validated positive evidence exists.
- If qualitative review caps progress because semantic output is not ready, placeholder events were found, or surface entities are suspected, preserve that cap unless strict changed-and-semantic output-delta evidence overrides it.
- If anti-loop evidence reports `substance_delta_gate.substance_delta_pass=false` or `status=missing`, do not treat validator/oracle/metric existence or capability-ladder observation as `goal_productive` unless strict changed-and-semantic primary-output evidence exists.
- If anti-loop evidence reports `vacuous_corrective_gate.surface_corrective_noop=true`, do not count attempted corrective/backfill rows as output delta; select lane-resolving correction work, terminal-block, or user escalation.
- If anti-loop evidence reports `advice_freshness_gate.advice_metrics_stale=true`, refresh, defer, reject, or justify any use of that advice against current raw evidence.
- If command-surface budget requires consolidation, register or select a consolidation candidate unless strict changed-and-semantic primary-output evidence already justifies goal-productive work, or the result is terminal/user escalation.
- If anti-loop evidence shows 3 same-family micro-hardening tasks, block another same-family micro task as `goal_productive`; choose provider/semantic transition, consolidation, supplied-input/domain-delta work, or terminal/user escalation.
- If a semantic family is sealed, do not select another non-terminal task in that family unless you name the new input kind, authority change, or external-state change that reopens it.
- If `positive_input_delta_required` is true, name the newly introduced input kind and the supplied artifact path or `produced_domain_delta=true`. If no supplied delta exists, terminal-block or select a task that obtains the missing input.
- Before terminal-blocking or sealing, verify no authority-permitted productive alternative path remains unattempted.
- If zero viable standalone candidates and zero viable pack items remain, emit `selected_task_source: terminal_blocked` with `terminal_blocker` instead of inventing work.

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
