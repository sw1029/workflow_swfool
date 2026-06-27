# Completion Gate Matrix

## Gate Status Values

Use these values in validation reports:

- `passed`: evidence satisfies the gate.
- `partial`: evidence exists but has nonblocking gaps.
- `failed`: evidence shows a blocking defect.
- `missing`: required evidence was not produced.
- `blocked`: validation could not run because of an external blocker.
- `not_applicable`: gate is not relevant to this task.

## Progress Verdict Values

Report progress separately from validation status:

- `advanced`: the task moved a blocker, execution state, schema/contract state, issue state, or final-goal state forward.
- `safety_only`: validation passed, but the task only proved fail-closed/no-live behavior or added a defensive guard without reducing the active blocker.
- `no_progress`: the task did not produce meaningful new evidence or state movement.
- `regressed`: the task weakened, broke, or contradicted a required state.

Validation can be `complete` while progress is only `safety_only`; do not describe that as final-goal completion or issue closure unless the task explicitly defined that safety proof as the required state transition.

## Validation Profiles

Honor the `task.md` validation profile before requiring historical reruns:

- `current_only`: validate only the current task surface and its direct acceptance criteria.
- `affected_chain`: validate the current surface plus changed or newly dependent prerequisites named in the prerequisite manifest.
- `full_chain`: rerun the full prerequisite/history chain only for live dispatch, readiness promotion, shared validator/runtime changes, issue closure, or explicit user request.

If a task includes a prerequisite manifest with unchanged command, path, input, and check hashes, reuse prior passing evidence when the profile permits it. Missing, changed, or failed prerequisite evidence must be reported as `missing`, `partial`, or `failed` rather than silently reused.

## Required Gates

| Gate | Complete Requires | Partial When | Failed When |
| --- | --- | --- | --- |
| Task scope | All explicit `task.md` requirements and acceptance criteria are addressed. | Scope is mostly addressed but edge cases or minor requirements remain. | Core requested behavior is absent or contradicted. |
| Environment | Required runtime is identified and usable, or no runtime is needed. | Runtime likely exists but dependencies or activation are unverified. | Required runtime is unavailable and blocks validation. |
| Execution | Required commands/tests/scripts ran and passed with logs. | Some validation ran, but important commands were skipped or inconclusive. | Required execution fails or cannot start. |
| Repo audit | `$inspect-repo-with-agents` finds no blocking governance, regression, or generalization issue. | Audit was degraded or finds nonblocking risks. | Audit finds blocking defects, regressions, or severe overfitting. |
| Goal schema contract | Relevant schema/module/script contract changes satisfy `.agent_goal/goal_schema_contract.md`, and `.schema/` or `.contract/` evidence is current. | Goal schema-contract compliance is partly evidenced but has nonblocking missing fields, stale links, or unclear applicability. | Required schema-contract evidence is absent, stale, unsupported, or contradicts `.agent_goal/goal_schema_contract.md`. |
| External advice | Task-referenced `.agent_advice` was incorporated, rejected, deferred, or intentionally left active with rationale, and no advice was used as GT or authority. | Advice relevance is plausible but lifecycle links or rationale are incomplete. | Advice was ignored without rationale, applied despite higher-priority conflict, or treated as GT/authority. |
| Issue tracking | Linked implementation issues are either resolved by evidence, not applicable, or intentionally handed off to `$manage-implementation-issues` after validation. | Issue evidence exists but links, close evidence, or handoff state are incomplete. | An active issue proves the task objective is still blocked or contradicts the claimed completion. |
| OOM risk | `$inspect-oom-risk` passed or is not applicable. | Relevant OOM risk was not fully audited or has mitigated concerns. | Audit finds likely unbounded memory failure or unsafe resource behavior. |
| task_miss | No active linked miss is open, partial, or unverified. | Nonblocking misses remain and are recorded. | Severe active miss blocks the task objective. |
| Logs/index | `.agent_log` and `.task/index` link important evidence. | Some links are missing but evidence is recoverable. | Evidence is absent or cannot be traced. |
| ID consistency | `$manage-task-state-index` audit has no high-severity issues for the active workflow, or ID context is not applicable. | ID audit has low/medium issues or an ID insight agent was unavailable but deterministic evidence is recoverable. | Broken IDs, multiple active tasks, missing required task/run/audit/validation/miss links, or stale/deleted artifact ambiguity blocks completion evidence. |
| Progress | The task's declared progress target is met and progress verdict is `advanced`, or the target explicitly required only a safety proof. | Validation passed but progress is `safety_only` or the blocker movement is incomplete. | Progress is `no_progress` or `regressed`, or the evidence contradicts the declared progress target. |

## Verdict Rules

Return `complete` only when every required gate is `passed` or `not_applicable` and the progress gate does not contradict the task's declared progress target.

Return `failed` when any gate has a blocking `failed` status for the active task objective.

Return `partial` for every other state, including degraded audits, missing noncritical evidence, unresolved nonblocking task_miss, or skipped OOM/env checks that are relevant but not fatal.

When in doubt between `complete` and `partial`, choose `partial` and record the missing evidence.

If validation is complete but progress is `safety_only`, report the cycle as technically validated but not final-goal-progress unless the task itself was intentionally a safety gate. If progress is `no_progress` or `regressed`, do not return final completion even when commands passed.
