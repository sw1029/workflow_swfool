---
name: task-md-agent-governance
description: "Implement repository work described by a root or workspace `task.md` using Tier 2 `gpt-5.6-terra/medium` routine coding agents, Tier 3 `gpt-5.6-terra/high` high-reliability coding and code analysis, and Tier 4 `gpt-5.6-terra/xhigh` important post-implementation review. This skill never promotes code-writing or recommendation-only review to Tier 5 Sol. Use when a current `task.md` needs governed delegated implementation, review, convention enforcement, or durable miss/gap handling."
---

# Task.md Agent Governance

## Overview

Use this skill when a repository contains `task.md` and the expected workflow is: read the task, implement it with delegated coding agents, audit the result with `$inspect-repo-with-agents`, and record missed requirements or generalization gaps in `.task/task_miss/`. If audit evidence shows previously recorded misses are resolved, write a resolved-miss summary and remove them from the active miss set by archiving or deleting them according to the cleanup policy.

The main agent coordinates. Worker agents may edit only assigned code areas. Inspection agents are read-only unless the user separately asks for remediation.

Use `$manage-task-state-index` throughout this workflow when ID context is available. ID work is additional and must not be assigned to implementation workers or normal inspection agents.

When `task.md` includes `progress_target`, `progress_kind`, `validation_profile`, prerequisite manifest/check-hash instructions, supplied-input delta expectations, provider retry/probe constraints, or command-surface consolidation expectations from `$orchestrate-task-cycle` or `$derive-improvement-task`, preserve those fields as task constraints. Do not broaden a `current_only` or `affected_chain` task into a full historical validation chain unless changed implementation surfaces justify it.

Use `$manage-agent-authority` to resolve worker authority and operating posture. If `.agent_goal/agent_authority.md` is absent and no caller supplied an authority summary, use `authority_policy: default_current_agent_permissions`: the current coding agent's effective sandbox, approval rules, and higher-priority instructions, with no inferred extra network/API/destructive authority. The authority policy may constrain API calls, external service use, allowed direction variation, strictness, implementation-first versus validation-first behavior, output/artifact confirmation, quality-review priority, conservative implementation, and escalation behavior. It can narrow or rank implementation choices, but it cannot override higher-priority instructions or grant capabilities unavailable in the current session.

Use `$manage-external-advice` or the caller's packet for `.agent_advice/active/*.md` when the task references advice or active advice is present. Advice can constrain design or task interpretation, but it is not GT and cannot broaden task scope, grant authority, or override repository evidence. Include relevant advice in worker and audit prompts under `used_advice`.

Use a repository-owned `code_convention_contract` when available from a repo-local adapter packet, `.agent_goal/conventions.md`, or caller context. The contract may define naming rules, reuse roots, kernel/shared-module paths, dependency-layer direction, max LOC/depth/fan-out, and forbidden patterns. Keep project-specific values out of this skill body. If no structured convention contract is available, apply only generic review heuristics as warn-only evidence and continue without inventing repo-specific rules.

## Agent Routing Policy

- When called from `$orchestrate-task-cycle`, use its [model-effort-routing.md](../orchestrate-task-cycle/references/model-effort-routing.md) policy. This skill is capped at Tier 4 and requests `gpt-5.6-terra` for every delegated worker or audit agent.
- Treat ordinary code analysis and governance as `high`; use `xhigh` when review controls completion readiness, blocker-level misses, issue lifecycle, schema/API/CLI/data-contract compatibility, security-sensitive behavior, or irreversible cleanup.
- Route ID-only consistency work through `$manage-task-state-index` at fixed `medium`.
- Spawn routine code-writing workers at Tier 2 with `agent_type: worker`, `model: gpt-5.6-terra`, and `reasoning_effort: medium`.
- Use Tier 3 `gpt-5.6-terra/high` for high-reliability core logic, including schema/contract compatibility, durable task/index/issue state mutation, validation gates, security-sensitive behavior, irreversible workflow implementation, or code whose regression can corrupt durable artifacts.
- Keep authority boundaries explicit: Terra workers may implement assigned code/tests/scripts and report observations, but they do not decide task scope, validation verdicts, miss cleanup, issue state, schema-version sufficiency, or commit readiness.
- Include the effective `$manage-agent-authority` result in every code-writing worker prompt and every implementation audit prompt. Tell workers to ask/report a blocker instead of using API/network/external services, changing direction, or broadening implementation beyond the allowed freedom profile when the authority policy does not permit it.
- Include relevant `.agent_advice` summaries in every worker or audit prompt when the task names advice or the caller supplied active advice. Tell workers to treat it as non-GT task/design context and to report conflicts instead of silently applying it.
- Record `agent_routing_applicability`, `policy_id`, `profile_id`, `routing_tier`, requested model/effort, `routing_reason_codes`, `routing_signals`, `routing_violations` even when empty, and `routing_enforcement` in the result. If the delegation tool cannot enforce model or effort, include the request in the prompt, use `prompt_only` or `inherited_unverified`, and record the limitation instead of claiming Terra execution.

## Workflow

1. Locate and read `task.md`.
   - Default to the current workspace root.
   - If `task.md` is missing, stop and report that the skill cannot proceed.
   - Extract task intent, explicit requirements, acceptance criteria, constraints, named files/modules, and ambiguity.
   - Extract `progress_target`, `progress_kind`, `validation_profile`, prerequisite manifest paths, declared blocker-state transition, supplied-input delta requirement, provider re-attempt disposition, and command-surface consolidation expectation when present. If a task appears to be another isolated no-live micro-contract without a transition or batching rationale, record that as a governance concern rather than silently expanding the scope.
   - Use `$manage-agent-authority` in `summarize` mode when `.agent_goal/agent_authority.md` exists, or use its `default_current_agent_permissions` fallback when absent and no caller supplied an authority summary. Extract constraints on API calls, external service use, direction freedom, implementation/validation priority, strictness, conservative implementation, artifact/output confirmation, quality review, and escalation.
   - Read relevant `.agent_advice/active/*.md` or consume the caller's active advice packet when `task.md` lists `External Advice`, the caller provided `used_advice`, or active advice exists. Keep it separate from `.agent_goal` GT.
   - Read `.agent_goal/goal_schema_contract.md`, `.schema/`, and `.contract/` when present and the task can affect shared schemas, module contracts, script contracts, serialized artifacts, CLIs, or cross-module compatibility.
   - Read or consume the repo-owned `code_convention_contract` when present. If it is absent, record `code_convention_contract_status: not_provided` and keep convention enforcement warn-only instead of blocking implementation.
   - If ambiguity blocks safe implementation, ask one concise clarification before spawning workers.
   - Run `$manage-task-state-index` `scan` to assign or reuse the active `task-*` ID when possible. If no index can be created or no usable ID context exists, continue the implementation workflow and note that ID tracking was skipped.

2. Map the repository.
   - Use `pwd`, `git status --short`, `rg --files`, README/manifests/config/tests, and likely entry points.
   - Identify generated/vendor/data/cache areas to avoid.
   - Preserve unrelated user changes; do not revert files you did not intentionally modify.

3. Delegate implementation to worker agents.
   - Split work into disjoint write scopes based on `task.md` and repo structure.
   - Use worker agents for implementation when there is code to write.
   - Spawn each code-writing worker with `agent_type: worker`, `model: gpt-5.6-terra`, and `reasoning_effort: medium` by default; use `high` for high-reliability core logic. Use Terra for governance/audit agents too, with the effort owned by their role.
   - Tell every worker they are not alone in the codebase, must not revert others' edits, and must list changed files.
   - Tell every worker the effective authority policy and require them to stay within it. If a worker believes the task requires broader API/network/external access, direction freedom, destructive operations, or validation posture than allowed, the worker must report the mismatch instead of proceeding.
   - Tell every worker the relevant active advice constraints and require `used_advice` in their output when advice shaped implementation. If advice conflicts with the task, GT, authority, or repo facts, workers must report the conflict instead of deciding scope themselves.
   - Tell every worker the applicable `code_convention_contract` or explicitly say the contract is missing and warn-only. Require workers to:
     - search existing reuse roots/shared modules before creating a new utility, helper, command wrapper, validator, adapter, or abstraction;
     - prefer reusing or extending an existing owned abstraction over duplicating equivalent behavior;
     - name files, modules, functions, classes, and commands by semantic responsibility rather than numbered shards, version suffixes, or mechanical split labels;
     - place code in the repository's semantic module tree and respect dependency direction; if the contract is absent, infer only from nearby repo patterns and report uncertainty;
     - avoid global rebinding shims, import-time mutation bridges, god objects, and mechanical split files that preserve hidden coupling;
     - include `convention_conformance` in worker output with `reuse_checked`, `created_new_surface`, `semantic_names`, `placement_basis`, `dependency_direction`, `contract_status`, and any warn-only violations.
   - Keep ownership explicit: paths/modules, expected behavior, tests to update, and exclusions.
   - Use [worker-and-audit-prompts.md](references/worker-and-audit-prompts.md) for prompt shapes.

4. Integrate worker changes.
   - Review changed files locally.
   - Resolve conflicts or mismatches without discarding unrelated user work.
   - Run relevant formatting, tests, or validation that can be inferred from the repo.
   - Keep validation consistent with the task's declared validation profile. Use `current_only` or `affected_chain` when appropriate; reserve full prerequisite reruns for changed shared validators/runtime, live dispatch, readiness promotion, issue closure, or explicit task/user requirements.
   - Check worker `convention_conformance` before execution. Treat contract-backed violations as integration blockers or task_miss candidates. Treat missing contract or uncertain repo convention evidence as warn-only and preserve it for `code_structure_audit`, `$audit-cycle-loopback`, and `$validate-task-completion`.
   - Record commands and failures for the later miss report.

5. Audit with `$inspect-repo-with-agents`.
   - Run a multi-agent inspection of both existing code and newly written code.
   - Request `model: gpt-5.6-terra` and minimum `reasoning_effort: high` for ordinary code-analysis inspection agents.
   - Request Tier 4 Terra/xhigh for important work review, including blocker-level post-implementation governance, resolved-miss archive/delete recommendations, schema/API/CLI/data-contract compatibility, security-sensitive behavior, and completion-readiness risks.
   - Read existing `.task/task_miss/` reports before audit when that directory exists, and include unresolved prior misses in the audit target.
   - Include `.agent_goal/goal_schema_contract.md`, `.schema/`, and `.contract/` in the audit target when schema/module/script contract surfaces are relevant.
   - Include the `$manage-agent-authority` result in the audit target. Audit whether workers respected API/external-call policy, direction freedom, implementation/validation priority, strictness, conservative implementation, and escalation constraints.
   - Include active advice in the audit target when the task or caller referenced it. Audit whether implementation incorporated, deferred, rejected, or ignored advice correctly and whether any advice was incorrectly treated as GT.
   - Include at least two audit concerns:
     - Code governance: requirement coverage, maintainability, regressions, tests, ownership boundaries, and unsafe side effects.
     - Semantic code governance: reuse-before-create evidence, semantic naming, correct module placement, dependency direction, duplicate helper definitions, global rebinding or hidden coupling, god-object growth, and mechanical shard/version-suffix file creation.
     - Generalization: logic/design that only handles one case, hard-coded assumptions, weak abstractions, narrow fixtures, missing edge cases, or unscalable structure.
     - Schema-contract governance: whether changed interfaces, data artifacts, modules, scripts, producers, consumers, validation, versions, and causal links still satisfy `.agent_goal/goal_schema_contract.md` and are reflected in `.schema/` or `.contract/`.
     - Authority governance: whether implementation workers stayed within `.agent_goal/agent_authority.md` or the default current-agent authority fallback, including API/external-call, autonomy, strictness, implementation-priority, quality-priority, conservative-implementation, and escalation rules.
     - Advice governance: whether active `.agent_advice` constraints were considered, whether conflicts were surfaced, and whether advice remained separate from `.agent_goal` GT.
     - Resolution check: whether previously recorded `.task/task_miss` items are now fixed, still open, or no longer applicable.
     - Cleanup decision: whether each resolved prior miss should remain open, be archived, or be deleted from active `.task/task_miss/`.
     - ID governance: whether active task, worker outputs, audit reports, validation commands, task_miss reports, resolved/deleted miss records, and `.agent_log` entries are consistently linked in `.task/index`.
   - Prefer 4-6 inspection agents for cross-cutting tasks; use 3 only for narrow tasks.
   - Inspection agents must be read-only, cite file/line evidence, and identify missing tests or validation gaps.
   - Run `$manage-task-state-index` deterministic `audit`. If the workflow authorizes agents, spawn one additional read-only ID consistency agent for task-state links only. This ID agent is not one of the 4-6 code inspection agents.

6. Record misses, resolved misses, and cleanup actions under `.task/task_miss/`.
   - Always create or link a durable miss report, even if no material misses were found.
   - Use `.task/task_miss/YYYYMMDD-HHMMSS-task-miss.md`.
   - Before writing a new no-material miss report, check whether an identical report already exists for the same task ID, validation/check path, audit coverage, and result. If identical evidence exists in the same cycle, link/reuse it through `$manage-task-state-index` instead of creating another timestamp-only duplicate.
   - Include task summary, implementation summary, test/validation summary, audit coverage, confirmed misses, generalization gaps, suspected risks, and follow-up recommendations.
   - Include the expected `progress_verdict` (`advanced`, `safety_only`, `no_progress`, or `regressed`) when the governance audit can infer it from the task scope. Mark no-live/fail-closed-only work as `safety_only` unless it unlocks a named transition.
   - If the audit confirms that prior `.task/task_miss` entries are resolved, write `.task/task_miss/YYYYMMDD-HHMMSS-task-miss-resolved.md`.
   - The resolved report must cite the prior miss file, the original miss summary, the evidence that it is resolved, validation performed, and any residual risk.
   - After writing the resolved report, clean up each resolved prior miss:
     - Archive by moving it to `.task/task_miss/resolved/` when history should be retained in the repository.
     - Delete it when the user requested deletion or the task_miss cleanup policy is delete-resolved.
   - Before deleting, record a deletion entry in `.task/task_miss/YYYYMMDD-HHMMSS-task-miss-deleted.md` or in the resolved report's `Cleanup Actions` section.
   - Never delete still-open, partially resolved, or unverified miss files.
   - Use [task-miss-template.md](references/task-miss-template.md).
   - Do not store secrets, raw sensitive data, private tokens, or large copyrighted excerpts.
   - After writing any miss/resolved/deleted report, run `$manage-task-state-index` `scan`, link each `miss-*` to the active `task-*`, and run `audit` before any archive/delete cleanup. Treat high-severity broken ID links as cleanup blockers.

7. Report outcome.
   - Summarize what was implemented, validation result, audit findings, and the saved miss report path.
   - Include active task ID, miss IDs, audit IDs, log/run IDs, and ID audit blockers when available.
   - Include `agent_routing_applicability` and, for delegated work, `policy_id`, `profile_id`, `routing_tier`, requested model/effort, `routing_reason_codes`, signals/evidence, `routing_violations` even when empty, `routing_enforcement`, actual routing when exposed, and any limitation.
   - Lead with blocking misses or failed validation before implementation summary.

## ID Governance Add-on

- Use `$manage-task-state-index` at task start, after worker integration, after audit, after miss report creation, and before deleting or archiving any candidate/miss artifact.
- Use a separate ID consistency agent only for traceability analysis; do not assign it code implementation, code review, or generalization review.
- Include ID-based audit findings in `.task/task_miss/` only when they affect task governance, completion evidence, miss cleanup, or artifact traceability.
- If no ID context exists, continue the normal task governance workflow and explicitly state that task-state indexing was unavailable or skipped.

## Governance Criteria

Treat these as miss candidates:

- `task.md` requirement not implemented or only partially implemented.
- Logic that passes a single named case but fails plausible variants.
- Hard-coded paths, constants, shapes, IDs, prompts, or data assumptions not justified by `task.md`.
- Missing validation for edge cases, invalid inputs, concurrency, data size, permissions, or failure modes.
- New code that bypasses existing abstractions, conventions, error handling, logging, or tests.
- New helper, utility, command wrapper, validator, adapter, or abstraction created without a reuse-before-create search of the repository-owned reuse layer or local equivalents.
- New or changed code that violates a provided `code_convention_contract`, including semantic naming, module placement, dependency direction, LOC/depth/fan-out limits, forbidden naming patterns, or reuse-layer expectations.
- Mechanical splits, numbered shards, version-suffix modules, global rebinding shims, duplicate public definitions, or god-object growth introduced as apparent refactoring progress.
- New or changed schema/module/script contract behavior that violates `.agent_goal/goal_schema_contract.md`, leaves `.schema/` or `.contract/` stale, omits required minimum fields, or fails to update versions/causal links.
- New code, worker behavior, task broadening, API/network/external service use, destructive operation, or validation posture that violates `.agent_goal/agent_authority.md` or the `default_current_agent_permissions` fallback.
- Implementation or audit output that ignores task-referenced `.agent_advice`, treats advice as `.agent_goal` GT, or applies advice despite conflict with the task, authority, current user direction, or repository facts.
- Tests that only assert the happy path or mirror implementation details instead of behavior.
- A task that repeats a no-live/fail-closed safety proof on the same blocker without a declared transition, batching rationale, or evidence-supply path.
- A task that claims positive input progress from a renamed/new input kind without a non-empty supplied artifact path, `produced_domain_delta=true`, or another validated domain/output artifact.
- A provider-terminal or sealed-family implementation path that bypasses a task-declared bounded retry/probe or an authority-permitted productive alternative path.
- A command-surface task that adds another versioned contract/handoff/preflight command when the task declared consolidation/refactor as the expected direction.
- A validation plan that reruns the full historical prerequisite chain without a changed affected surface, live/readiness/issue-closure gate, shared validator/runtime change, or explicit user/task requirement.

Treat these as resolved miss candidates:

- A prior `.task/task_miss` item has direct code/test evidence showing the missing requirement is now implemented.
- A prior generalization gap is covered by broader logic plus tests or validation across representative variants.
- A prior suspected risk is disproven by repository evidence, validation, or explicit task scope clarification.
- A prior miss is no longer applicable because `task.md` or accepted scope changed; record the scope evidence.

## Cleanup Policy

Use these statuses for prior `.task/task_miss` files after audit:

- `still_open`: keep the file in `.task/task_miss/` and reference it in the new miss report.
- `partially_resolved`: keep the file in `.task/task_miss/`, add a new follow-up miss report, and do not delete it.
- `resolved_archive`: write a resolved report, then move the prior miss file into `.task/task_miss/resolved/`.
- `resolved_delete`: write a resolved/deleted report, then delete the prior miss file from `.task/task_miss/`.
- `obsolete_scope`: write the scope evidence; archive or delete only if the audit confirms it is no longer actionable.

## Guardrails

- Do not proceed without `task.md`.
- Do not let inspection agents edit files.
- Do not let worker agents write outside their assigned scopes.
- Do not spawn a code-writing implementation worker without requesting `gpt-5.6-terra` and the declared effort. When the tool cannot enforce them, record prompt-only or inherited-unverified routing instead of silently claiming compliance.
- Do not run code-analysis inspection agents below `reasoning_effort: high` when the tooling exposes reasoning effort.
- Do not run important post-implementation review below `reasoning_effort: xhigh` when the tooling exposes reasoning effort.
- Do not use `ultra` for delegated implementation or audit agents.
- Do not delegate governance decisions to code-writing workers.
- Do not claim `$inspect-repo-with-agents` coverage if subagents were unavailable; state the limitation in `.task/task_miss/`.
- Do not overwrite existing `.task/task_miss` reports.
- Do not mark a miss resolved without concrete audit evidence and at least one validation or rationale note.
- Do not delete still-open, partially resolved, or unverified miss files.
- Do not delete a resolved miss before writing a resolved/deleted summary that cites the deleted file path and resolution evidence.
- Do not treat `.task/task_miss` as a replacement for tests or issue tracking; it is a durable audit note for missed or weak areas.
- Do not let an ID consistency agent replace `$inspect-repo-with-agents`; it is additional traceability review only.
- Do not ignore `.agent_goal/goal_schema_contract.md` when implementing or auditing changes that affect schema, module contract, script contract, CLI, serialized artifact, producer/consumer, or compatibility behavior.
- Do not bypass `$manage-agent-authority` when implementing, delegating, or auditing code. If `.agent_goal/agent_authority.md` is absent, do not infer additional authority beyond the current coding agent's effective permissions.
- Do not treat `.agent_advice` as GT, authority, or a reason to broaden implementation scope. Advice is a non-GT constraint to consider and report through `used_advice`.
- Do not create duplicate timestamp-only no-material miss reports when identical evidence for the same task/check already exists and can be linked.
- Do not create new shared utilities, wrappers, validators, or adapters before checking existing reuse surfaces named by the repo-owned convention contract or evident local patterns.
- Do not turn repo-specific naming rules, thresholds, kernel paths, or dependency DAGs into this generic skill body; consume them from the repository contract or keep the finding warn-only.
