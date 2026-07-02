---
name: validate-task-completion
description: "Run a common pre-close task completion gate that combines repository audit, OOM-risk audit, environment checks, execution logs, task_miss status, issue status, active `.agent_advice` usage/status, code convention conformance, semantic structure metrics/high-water movement, task index traceability, and agent log evidence into a `complete`, `partial`, or `failed` verdict. Treat repository and OOM code-analysis audits as important work review with `reasoning_effort: xhigh`. Use before Codex declares `task.md` implemented, closes a workflow cycle, promotes or deletes artifacts, reports final completion, or verifies outputs from task lifecycle skills."
---

# Validate Task Completion

## Overview

Use this skill as the final gate before saying a repository task is done. It gathers evidence from the task lifecycle, runs or verifies required audits, and writes a durable validation report with one verdict: `complete`, `partial`, or `failed`.

Also report task progress separately from validation correctness. A task can be validly complete for its narrow scope while still making only safety or no-live progress toward the final goal.

The validation report is evidence, not implementation. If the verdict is `partial` or `failed`, preserve the blockers in `.task/task_miss/` or the task index so the next workflow cycle can act on them.

ID consistency is a required validation concern when a task-state index exists. If no ID context exists and the task did not require indexed governance, continue the completion validation and mark ID traceability `not_applicable` or `missing` as appropriate.

When `task.md`, a caller packet, or active workflow evidence references `.agent_advice`, validate it as non-GT direction evidence. Confirm the advice was incorporated, deferred, rejected, or left active with a rationale; never count advice as `.agent_goal` goal truth or authority.

## Agent Routing Policy

- When called from `$orchestrate-task-cycle`, consume the canonical orchestration reference [workflow-routing.md](../orchestrate-task-cycle/references/workflow-routing.md) as caller context, but keep completion validation's own routing below.
- Treat completion validation repository audits as important work review. Invoke `$inspect-repo-with-agents` with `reasoning_effort: xhigh` whenever the tooling exposes it.
- Treat completion validation OOM audits as important work review when OOM risk is relevant. Invoke `$inspect-oom-risk` with `reasoning_effort: xhigh` whenever the tooling exposes it.
- Keep ID-only traceability correction routed through `$manage-task-state-index` with fixed `reasoning_effort: medium`.
- If a tool cannot enforce the requested effort, encode the requirement in the prompt and record the limitation in the validation report.

## Workflow

1. Collect local evidence.
   - Read `task.md`, `.task/index.jsonl`, `.task/index.md`, `.task/task_miss/`, `.task/candidate_task/`, `.issue/`, `.agent_log/`, `.agent_goal/goal_schema_contract.md`, `.agent_advice/`, `.schema/`, and `.contract/` when present.
   - Use the bundled collector for a compact inventory:

     ```bash
     python3 /home/swfool/.codex/skills/validate-task-completion/scripts/collect_completion_evidence.py --root . --include-git
     ```

2. Ensure task-state traceability.
   - If `.task/index.jsonl` or `.task/index.md` is missing or stale, use `$manage-task-state-index` to initialize, scan, and link the current artifacts.
   - The active task should link to relevant execution logs, audit logs, validation reports, and active or resolved task_miss files.
   - Active or resolved issue records should link to relevant tasks, execution logs, validation reports, task_miss files, and issue resolution evidence when present.
   - Run `$manage-task-state-index` deterministic global `audit`. Use `audit --write-report` when this validation report is closing a workflow cycle.
   - If the workflow authorizes agents and ID context exists, spawn one additional read-only ID consistency agent. This agent is separate from repo/OOM/env/run validation and must only inspect ID relationships and lifecycle status.

3. Verify execution environment.
   - Use `$find-local-python-envs` before execution when the task uses Python, notebooks, package imports, tests, model code, or dependency-constrained scripts.
   - Record the selected interpreter/environment and any unresolved dependency gaps.
   - If no environment is needed, mark the environment gate `not_applicable`.

4. Verify execution evidence.
   - Use `$run-task-code-and-log` when the task specifies code, commands, scripts, notebooks, tests, or a required run procedure.
   - Require factual evidence: command line, exit status, output summary, artifacts, failures, and saved `.agent_log` entry.
   - If the task changes a runtime gate, router, validator, dispatch decision, or other judgment whose expected output changes, require fresh live before/after evidence that the changed path actually changed result, or record an explicit defer rationale and cap completion at `partial`.
   - If execution cannot be run, classify the execution gate as `missing` or `blocked` and explain why.
   - Treat execution-log `observed_producer_claim` fields as producer self-report only. They may explain what the producer claimed, but they must not satisfy execution success, completion, progress, or goal-distance movement without adapter recomputation or strict changed-and-semantic output-delta evidence.

5. Run repository audit.
   - Use `$inspect-repo-with-agents` to audit requirement coverage, regressions, maintainability, tests, and generalization gaps.
   - Invoke this repository audit as important work review with `reasoning_effort: xhigh`.
   - Include both existing code and changed code when implementation occurred.
   - Include `.agent_goal/goal_schema_contract.md`, `.schema/`, and `.contract/` when the task touches shared schemas, module/script contracts, serialized artifacts, CLI/script I/O, producers, consumers, versions, or compatibility.
   - Include task-referenced `.agent_advice` when present. Audit whether implementation and task artifacts handled the advice as non-GT planning evidence and did not use it to override GT, authority, or repository facts.
   - Check whether schema/contract records satisfy the goal schema-contract minimum fields, application intent, mandatory rules, validation evidence, and causal-map expectations when relevant.
   - Include ID-based audit concerns or reuse the `$manage-task-state-index` ID audit: active task linkage, candidate/past_task lineage, run/log/audit/validation links, task_miss resolution links, and stale digest conflicts.
   - If multi-agent inspection is unavailable, state that limitation and cap the final verdict at `partial` unless the task is purely documentary and independently verifiable.

6. Run OOM-risk audit when relevant.
   - Use `$inspect-oom-risk` when the task touches large data loading, model inference/training, batching, concurrency, caches, build/test memory pressure, containers, GPU/VRAM, or unbounded accumulation.
   - Invoke relevant OOM-risk audit as important work review with `reasoning_effort: xhigh`.
   - If no plausible memory-risk surface exists, mark the OOM gate `not_applicable`.
   - If OOM audit is relevant but not run, cap the verdict at `partial`.

7. Evaluate `.task/task_miss`.
   - Treat active `open`, `still_open`, `partially_resolved`, or unverified miss files linked to the current task as blockers.
   - Treat resolved/deleted reports as closed only when they cite concrete resolution evidence.
   - If a miss is resolved during validation, do not delete it here unless the owning workflow requested cleanup; instead record the resolution evidence and update the index.

8. Evaluate `.issue`.
   - Treat active issue records linked to the current task as completion context, not automatic blockers.
   - If an issue describes unresolved validation, implementation, or goal-fit blockers for the current task, classify the relevant gate as `partial` or `failed`.
   - If the task appears to resolve an issue, do not close or archive it here; require `$manage-implementation-issues` after validation so `$run-task-code-and-log` evidence is attached before close/archive.

9. Evaluate `.agent_advice`.
   - If `task.md` includes `External Advice`, the caller supplied `used_advice`, or active advice exists, add an `External advice` gate to the validation report.
   - `passed`: task/audit/log/schema/issue evidence shows the advice was incorporated, rejected, deferred, or intentionally left active with a rationale, and no advice was reported as GT.
   - `partial`: advice relevance is plausible but lifecycle evidence or links are incomplete.
   - `failed`: a task-referenced advice directive was ignored without rationale, applied despite a higher-priority conflict, or used as GT/authority.
   - Use `$manage-external-advice mark-applied` only when the advice is fully consumed or retired by durable evidence. Otherwise keep it active and record the remaining gate.

10. Evaluate acceptance provenance, convention conformance, and structure effect.
   - When `task.md`, `.task/task_pack`, active advice, or caller packets provide `scope_fidelity`, compare the original measurable target against actual achievement before allowing close.
   - When a normalized acceptance packet provides `acceptance_envelope_contract`, verify that the executed or selected envelope satisfied the adapter-owned `envelope_floor`. If the execution envelope is below the floor, classify the acceptance as unmet or partial; do not reframe the planned-failure result as a tool, prompt, runtime, or schema blocker.
   - If the item inherited a measurable target and actual achievement is below the original target, set `acceptance_diluted=true`, return `partial`, and preserve or require an open residual follow-up. Do not mark the original directive applied or the pack item consumed.
   - Accept a narrower result only when there is an explicit descope decision with reason plus residual item/link. A weak item label such as `pilot`, `plan`, or `slice` is not descope evidence.
   - If a provided `code_convention_contract` applies and governance/code-structure audit reports an unresolved contract-backed violation, return `partial` or `failed` according to severity. If the contract is absent, record the convention gap as warn-only and preserve a repo-local adapter/convention-contract follow-up when repeated.
   - For behavior-preserving refactor tasks, require adapter-supplied structure high-water movement, such as reduced entrypoint burden, reduced command/flat-file/function burden, reduced mechanical shard count, reduced duplicate definitions, reduced global coupling, improved reuse ratio, reduced depth/fan-out, or another project-owned structure metric. Treat adapter `structure_metrics` as the structure-progress truth source; producer-local structure reports, file-count growth, relocated helpers, token/pattern avoidance, or green tests alone are insufficient for `complete` when the refactor objective was structural reduction.
   - If caller packets include `disposition_intersection_basis.allowed_task_kinds`, verify that any claimed `goal_productive` completion used a matching `selected_task_kind`; otherwise cap the verdict at `partial` and preserve the allowed correction as residual work.
   - If structure metrics worsen on a relevant axis, such as shard count up, duplicate count up, depth/fan-out beyond contract, reuse ratio down, or max LOC up against the task objective, cap the verdict at `partial` and preserve residual work unless the task explicitly scoped that regression out with evidence.
   - Record `acceptance_provenance_gate`, `convention_conformance_gate`, `structure_metrics_gate`, and `execution_evidence_gate` fields in the validation result when applicable so `$orchestrate-task-cycle` result contracts can enforce them.

11. Decide the verdict.
   - Use [completion-gates.md](references/completion-gates.md) for the gate matrix.
   - `complete`: acceptance criteria are met; required execution passed; relevant repo/OOM audits have no blockers; environment is known or not needed; active task_miss has no blockers; logs and index are updated.
   - If schema/module/script contracts are relevant, `complete` also requires `.agent_goal/goal_schema_contract.md` compliance or a documented non-applicable reason, plus updated `.schema/` or `.contract/` evidence.
   - If advice was referenced, `complete` also requires the `External advice` gate to be `passed` or `not_applicable`.
   - If measurable acceptance provenance, structure-effect, or behavior-change live evidence gates are applicable, `complete` also requires those gates to pass or a recorded explicit descope/defer decision that leaves residual work open and normally caps the verdict at `partial`.
   - If convention conformance is applicable, `complete` also requires unresolved contract-backed code convention violations to be absent or intentionally deferred with open residual scope. Missing convention contract evidence is warn-only unless the task explicitly required contract creation/update.
   - `partial`: core work appears useful but one or more nonfatal gates are missing, unverified, degraded, or have follow-up risks.
   - `failed`: implementation is absent, required execution fails, audit finds blocking defects, severe task_miss remains open, or the task cannot be safely validated.
   - If ID audit finds high-severity broken links, multiple active tasks, missing validation/run/audit evidence links, or unsafe candidate/miss deletion ambiguity, cap the verdict at `partial` or `failed` depending on whether the missing traceability blocks the task objective.
   - Separately decide `progress_verdict`:
     - `advanced`: the task unlocked a new execution/readiness/goal state, supplied or validated previously missing evidence, produced useful dataset/KG artifacts, improved qualitative output, or materially reduced an active blocker, and the evidence includes `terminal_outcome_changed=true` or strict observed `changed_vs_previous=true` plus `semantic_progress=true`.
     - `safety_only`: the task passed by proving fail-closed, no-live, non-dispatchable, or guardrail behavior without supplying source-backed evidence, producing dataset/KG artifacts, advancing readiness, or reducing the final-goal blocker.
     - `no_progress`: the task produced no new durable evidence or repeated already-proven safety checks without a new blocker-state transition.
     - `regressed`: the task weakened or broke a required state, contract, validation gate, safety boundary, or goal requirement.
   - Do not classify progress as `advanced` merely because a new input kind was named. Evidence-family progress requires a non-empty supplied artifact path, `produced_domain_delta=true`, or another validated positive domain/output artifact.
   - Do not classify progress as `advanced` from `observed_producer_claim`, self-declared `produced_domain_delta`, non-empty counts, fixture-only success, or a blocker-state label unless adapter-recomputed quality/substance/structure evidence, `terminal_outcome_changed=true`, or strict observed changed-and-semantic output-delta evidence is present. Otherwise cap progress at `safety_only`.
   - If `observed_producer_claim` reports `goal_productive`, `advanced`, or equivalent while adapter recomputation or strict output-delta evidence is missing or negative, record `split_brain_progress_claim=true`, ignore the producer claim for the verdict, and preserve residual work or blockers.
   - Do not classify progress as `advanced` when the run evidence is `self_inflicted_gate_defect` unless the task actually corrected the gate contract/code or supplied a valid alternative evidence source. Rechecking the same unsatisfiable gate is `no_progress` or `safety_only` at most.
   - Do not classify repeated `terminal_blocked`/recheck closeout as `advanced`. If `terminal_escalation_gate.escalation_required=true`, a valid completion must record `user_escalation`, exactly one missing input, and family seal evidence; otherwise cap the verdict at `partial` or `failed` depending on the task objective.
   - Do not let `validation_verdict: complete` imply final-goal progress when `progress_verdict` is `safety_only` or `no_progress`.

12. Write a validation report.
   - Create `.task/validation/YYYYMMDD-HHMMSS-task-validation.md`.
   - Include task ID if known, validation verdict, progress verdict, gate statuses, evidence paths, commands, audit summaries, active misses, and required follow-ups.
   - Update `$manage-task-state-index` with a `validation` artifact whose status is `passed`, `partial`, or `failed`.
   - Use `$record-agent-work-log` when the user requested durable logging of the validation work itself or when this report closes a larger agent cycle.

13. Report the outcome.
   - Lead with the verdict.
   - For `partial` or `failed`, list blockers before summarizing completed work.
   - Include the validation report path and the updated task index path.

## Validation Report Shape

Use this concise structure:

```text
# Task Completion Validation

- Timestamp:
- Validation Verdict: complete | partial | failed
- Progress Verdict: advanced | safety_only | no_progress | regressed
- Workspace:
- Active task ID:
- Validation artifact ID:

## Gate Status
| Gate | Status | Evidence | Notes |
| --- | --- | --- | --- |

Include an `ID consistency` gate whenever `.task/index` exists or should have been created for the workflow.

Include an `Issue tracking` gate whenever `.issue/` exists or `$manage-implementation-issues` should track the active or next task.

Include a `Goal schema contract` gate whenever `.agent_goal/goal_schema_contract.md`, `.schema/`, `.contract/`, or schema/module/script contract surfaces are relevant.

Include an `External advice` gate whenever `.agent_advice/` exists, the caller supplied `used_advice`, or `task.md` references an advice ID/path.

Include an `Acceptance provenance` gate whenever `scope_fidelity`, measurable advice targets, or directive-derived acceptance criteria are present.

Include a `Structure effect` gate whenever the task is a behavior-preserving refactor or consolidation intended to reduce structure burden.

Include a `Convention conformance` gate whenever implementation changed code and a repo-owned `code_convention_contract`, code-structure audit packet, or governance `convention_conformance` packet is present.

Include a `Behavior-change live evidence` gate whenever the task changes runtime gate, routing, validator, dispatch, or judgment outcomes.

## Blocking Findings
...

## Evidence
...

## Progress Assessment
...

## Follow-ups
...
```

## Guardrails

- Do not claim completion without execution evidence when the task required running code.
- Do not claim completion or progress from producer self-reported progress fields. Treat them only as `observed_producer_claim` and require adapter or strict output-delta truth.
- Do not claim repository audit coverage if `$inspect-repo-with-agents` did not run.
- Do not skip `$find-local-python-envs` for dependency-constrained Python tasks.
- Do not skip `$inspect-oom-risk` for data/model/batch/concurrency changes with plausible memory risk.
- Do not delete `.task/task_miss` files from this skill unless the user explicitly requested cleanup and evidence is already recorded.
- Do not mark unresolved task_miss as complete merely because implementation progressed.
- Do not mark `progress_verdict: advanced` merely because a no-live/fail-closed safety check passed; name the blocker-state transition or classify it as `safety_only`.
- Do not mark `progress_verdict: advanced` unless `terminal_outcome_changed=true` or strict observed `changed_vs_previous=true` and `semantic_progress=true` evidence is present.
- Do not mark named-only input changes as a positive input delta; require supplied artifact evidence or `produced_domain_delta=true`.
- Do not mark G2 terminal escalation complete without `selected_task_source: user_escalation`, `required_missing_input_count: 1`, a concrete `required_missing_input.kind`, and `.task/sealed_blocker_families.json` or equivalent pack-mutation evidence.
- Do not store secrets, credentials, private tokens, raw sensitive data, or large copyrighted excerpts in validation reports or logs.
- Do not count a repo, OOM, env, or execution agent as the ID consistency agent; ID validation is additional when agent-based insight is used.
- Do not mark schema/module/script contract changes complete when `.agent_goal/goal_schema_contract.md` applies but `.schema/` or `.contract/` evidence is stale, missing required fields, or lacks validation/causal-map coverage.
- Do not close, archive, or delete `.issue` records from this skill; issue lifecycle changes belong to `$manage-implementation-issues`.
- Do not treat `.agent_advice` as GT, authority, or completion evidence by itself.
- Do not mark advice applied without `$manage-external-advice` lifecycle evidence or a clear validation/report rationale.
- Do not return `complete` for `acceptance_diluted=true`; return `partial` and preserve residual scope.
- Do not complete measurable directive-derived work against a weaker criterion unless explicit descope and residual tracking exist.
- Do not complete measurable work when an adapter-supplied `acceptance_envelope_contract` proves the executed envelope was below the minimum needed for the target.
- Do not complete behavior-preserving refactor work from module creation or green tests alone when the objective required structural reduction.
- Do not complete structure work from file-count growth, numbered shards, version-suffix modules, relocated helpers, import shims, token/pattern avoidance, or producer-local structure reports alone.
- Do not complete a task as `goal_productive` when loopback/derive gates constrained allowed task kinds and the completed work used a different `selected_task_kind`.
- Do not complete code changes with unresolved contract-backed naming, reuse, placement, dependency-direction, depth/fan-out, duplicate-definition, or global-rebinding violations unless an explicit defer/descope leaves residual work open.
- Do not complete runtime behavior-change fixes without fresh live evidence or a documented defer that keeps follow-up work open.
