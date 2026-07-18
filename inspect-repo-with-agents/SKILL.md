---
name: inspect-repo-with-agents
description: "Coordinate a dynamic 3-6 subagent inspection of the current repository with configured Tier 3 analysis and Tier 4 important-review routing, then synthesize evidence into an actionable repo-aware report. This recommendation-only inspection skill is capped at Tier 4; final direction remains with its caller. Use for multi-agent repository inspection, audit, investigation, architecture or feature-impact analysis, test-gap analysis, performance review, or security-oriented codebase analysis."
---

# Inspect Repo With Agents

## Overview

Use this skill to inspect the current repository through 3-6 focused subagents selected for the user's task. The main agent remains the coordinator: map the repo, assign non-overlapping perspectives, integrate reports, verify critical claims, and deliver a concise final assessment.

If subagents are unavailable, do not pretend that a multi-agent inspection happened. Perform the best local inspection possible and state the limitation.

`authority.operations.json` declares the repository inspection as read-only under the shared [authority v2 contract](../manage-agent-authority/references/authority-v2-contract.md). Delegation does not add mutation authority, and any proposed fix or durable report must use the exact operation of its owning writer skill.

When task-state artifacts exist, add ID traceability as a separate concern through `$manage-task-state-index`. ID work is additional and must not replace or consume one of the normal repository inspection agents.

## Agent Routing Policy

- Resolve delegated routes against `policy_id: configured-tiered-routing-v3`.
- Request `profile_id: code_analysis`, Tier 3, `requested_model_ref: model_ref:balanced`, and `requested_reasoning_effort: high` for ordinary repository code analysis.
- Request `profile_id: important_review`, Tier 4, `requested_model_ref: model_ref:balanced`, and `requested_reasoning_effort: xhigh` when the inspection controls completion evidence, post-implementation blockers, miss/candidate/issue cleanup recommendations, schema/API/CLI/data-contract compatibility, security-sensitive review, destructive or irreversible workflow review, or high-severity regression analysis.
- Do not downgrade code-analysis agents below `high` for speed. If a caller already requires `xhigh`, keep `xhigh`.
- Keep ID-only traceability agents routed through `$manage-task-state-index`; their fixed routing is `reasoning_effort: medium`.
- Keep runtime model bindings in caller configuration or a repository adapter. Do not embed provider names or deployment-specific model identifiers in this skill.
- Record `policy_id`, `profile_id`, `routing_tier`, `requested_model_ref`, `requested_model` as the resolved runtime value or the abstract reference when unresolved, `model_configuration_status`, optional `model_binding_receipt`, `requested_reasoning_effort`, reason codes, routing violations, `routing_enforcement`, and any `routing_limitation`. Treat an unresolved abstract reference as `reference_only`; it can support a prompt request but cannot prove enforced execution.
- Keep this recommendation-only skill capped at Tier 4. Do not take final direction authority or use delegated `ultra`.

## Workflow

1. Clarify the task only if needed.
   - Treat explicit invocation of this skill as authorization to use subagents for repository inspection.
   - Extract the inspection target, success criteria, risk areas, and any files, paths, or technologies named by the user.
   - Ask at most one concise question if the task is too ambiguous to choose agent scopes safely.

2. Build a quick local repo map before spawning.
   - Use `pwd`, `git status --short`, `rg --files`, and targeted reads of README, manifests, test config, CI config, and obvious entry points.
   - Identify languages, frameworks, important directories, test layout, generated/vendor directories to avoid, and likely ownership boundaries.
   - Do enough local reading to give each subagent a concrete, bounded assignment.
   - When present and relevant, include `.agent_goal/goal_schema_contract.md`, `.schema/`, and `.contract/` in the repo map so subagents can evaluate schema/contract-goal compliance.
   - If `.task/`, `.agent_log/`, `task.md`, `.agent_goal/`, `.interview/`, `.schema/`, or `.contract/` exists, run `$manage-task-state-index` `scan` and deterministic `audit` to collect ID context before final synthesis.

3. Choose 3-6 subagents dynamically.
   - Use 3 agents for narrow tasks with one main subsystem.
   - Use 4 agents for ordinary feature, bug, or migration inspections spanning code and tests.
   - Use 5 agents for cross-cutting behavior, multiple runtimes, architecture, data flow, or risk analysis.
   - Use 6 agents only when the repo/task has genuinely independent concerns such as backend, frontend, persistence, CI, security, and tests.
   - Prefer `explorer` agents for read-only inspection. Use `worker` only if the user also asks for implementation.
   - Spawn inspection agents with the configured Tier 3 route; use the configured Tier 4 route for important work review.
   - Load [perspective-catalog.md](references/perspective-catalog.md) when you need help selecting complementary perspectives.
   - If ID context exists, optionally spawn one additional read-only ID consistency agent using `$manage-task-state-index` guidance. This agent is not part of the 3-6 repo-inspection agent count and must not receive normal code-review ownership.

4. Assign bounded, non-duplicative inspections.
   - Give each subagent a distinct perspective, path focus, and output contract.
   - Include the repo path, the user's task, any relevant files already discovered, and explicit exclusions.
   - Include `.agent_goal/goal_schema_contract.md` and relevant `.schema/.contract` paths for any perspective involving architecture, data flow, CLI/script I/O, serialized artifacts, module boundaries, compatibility, or task-cycle governance.
   - Tell subagents not to edit files, not to spawn additional agents, and to cite file/line references for findings.
   - Keep prompts neutral. Do not include expected answers or suspected bugs unless the user's task itself names them.

5. Work locally while subagents run.
   - Inspect a coordinator-only slice such as repo topology, shared contracts, dependency graph, or final-report evidence.
   - Do not duplicate a subagent's assigned work unless needed to resolve contradictions or verify severe findings.

6. Integrate and verify.
   - Wait for agent reports when they are needed for synthesis.
   - Reconcile overlaps and conflicts. Prefer concrete file/line evidence over broad claims.
   - Spot-check high-severity, surprising, or contradictory findings locally before presenting them as facts.
   - Integrate ID audit findings separately from code findings. Treat broken links, missing task/audit/run/miss associations, duplicate active tasks, or stale digests as traceability findings, not code defects unless they hide a code governance risk.
   - Close agents that are no longer needed.

7. Report findings.
   - Lead with findings ordered by severity and tied to file/line references.
   - Include coverage: which agents inspected which perspectives.
   - Include ID coverage when available: active task ID, related candidate/miss/log/run/audit IDs, ID audit result, and unresolved global ID consistency issues.
   - Note test gaps, unknowns, and assumptions separately.
   - If there are no material findings, say that clearly and state residual risk from uninspected areas.
   - Keep the final answer concise unless the user requested a full audit artifact.

## ID Traceability Add-on

Use `$manage-task-state-index` opportunistically:

- If no usable ID context exists, continue the repository inspection normally and say ID traceability was not available.
- If ID context exists, run `scan` and `audit`; use `audit --write-report` when the inspection itself should become durable evidence.
- If an ID insight agent is used, keep it separate from normal inspection agents and ask only for ID/link/lifecycle consistency findings.
- For existing audit-style requests, add ID-based audit findings as a separate section or as low/medium/high traceability findings.

## Subagent Prompt Template

Use this shape and fill in the bracketed parts:

```text
You are one of [N] agents inspecting the repository at [repo path].

Agent routing:
- Use `policy_id: configured-tiered-routing-v3`, `profile_id: code_analysis`, Tier 3, `requested_model_ref: model_ref:balanced`, and `requested_reasoning_effort: high` for ordinary code analysis.
- Use `profile_id: important_review`, Tier 4, the same abstract model reference, and `requested_reasoning_effort: xhigh` for completion validation, blocker-clearing governance, miss/candidate/issue cleanup recommendations, schema/API/CLI/data-contract review, security-sensitive review, irreversible workflow review, or high-severity regression analysis.
- Report model configuration status, routing enforcement, and any limitation. A `reference_only` request is not enforced execution; do not use delegated `ultra` or take final direction authority.

User task:
[task]

Relevant goal/schema contract context:
[.agent_goal/goal_schema_contract.md and `.schema/.contract` paths when relevant]

Your assigned perspective:
[perspective]

Focus paths or components:
[paths/components]

Exclude:
[generated/vendor/unrelated paths]

Do not edit files. Do not spawn other agents.

Inspect the codebase with `rg`/targeted file reads. Report:
1. Findings with severity, confidence, and file/line references.
2. Relevant evidence or commands used.
3. Schema/contract-goal compliance findings when relevant: minimum fields, mandatory rules, target modules/scripts, versions, producers, consumers, validation evidence, and causal compatibility.
4. Missing tests or validation gaps.
5. Areas you did not inspect.

Keep the response concise and actionable.
```

## Output Shape

Prefer this final structure:

```text
Findings
- [Severity] [file:line] Concrete issue and impact.

Coverage
- Agent 1: perspective and paths.
- Agent 2: perspective and paths.

Gaps
- Untested or uninspected areas.

Next Steps
- Highest-value follow-up actions.
```
