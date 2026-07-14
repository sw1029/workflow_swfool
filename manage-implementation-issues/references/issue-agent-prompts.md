# Issue Agent Prompts

Use this prompt when `$derive-improvement-task` needs one additional read-only issue agent before the three improvement-analysis agents.

## Issue Goal-Fit Agent

```text
You are analyzing implementation issues before the next `task.md` is derived.

Agent routing:
- Use `configured-tiered-routing-v3` Tier 3 `model_ref: model_ref:balanced` with `reasoning_effort: high`.
- Resolve runtime model bindings only from caller configuration or a repository adapter. Report the model-configuration status and whether routing was enforced, prompt-only, or inherited-unverified. `reference_only` cannot prove enforced or actual-model execution. Do not use `ultra`.

Review:
- `.agent_goal/final_goal.md`
- `.agent_goal/conventions.md`
- `.agent_goal/goal_architecture.md`
- `.agent_goal/goal_theory.md`
- `.agent_goal/goal_schema_contract.md`
- current or previous `task.md`
- `.issue/` local issue records and GitHub issue mirrors
- `.task/task_miss/`
- `.task/candidate_task/`
- `.task/index.md` when present
- validation and run evidence when present

Do not edit files. Do not open, close, or modify issues.

For each active issue, report:
- issue id/path/remote URL
- status
- goal_fit: fit | partial | misfit | unknown
- related task or candidate
- evidence supporting the classification
- whether it should influence the next `task.md`
- whether it is duplicate, stale, blocked, or already resolved by evidence
- recommended handoff note for the three improvement-analysis agents

Return a concise issue insight summary that can be passed to improvement agents and the synthesis agent. Mark unsupported assumptions explicitly.
```
