---
name: task-doctor
description: Review, retarget, replace, or task-pack a repository's active `task.md` only when the user gives explicit task-doctor direction. Use when Codex must externally adjust task scope or work direction before `$orchestrate-task-cycle`, optionally incorporate named `.agent_advice` non-GT documents, create/update `.task/task_pack` JSON+Markdown proposals that may include the current task, check `.agent_goal` conventions and repository rules, preserve task lifecycle IDs and `past_task` traceability, refresh schema/index/issue state, and invoke `$repo-change-commit`. Do not use for normal task implementation or ordinary next-task derivation.
---

# Task Doctor

## Overview

Use this skill as a pre-cycle intervention for task direction. It may replace or rewrite `task.md` from an explicit user instruction after checking goal truth, conventions, repository rules, and task-state traceability. It may also create or update a `.task/task_pack/` proposal when the user explicitly asks for a sequence of tasks or asks to include the current task in a task-pack plan.

This skill adjusts the workflow artifact that `$orchestrate-task-cycle` will later consume. It does not implement the task, run the full orchestrated cycle, or patch behavior-changing repository code.

When the user provides or names an external advice Markdown document, use `$manage-external-advice` to intake or render its active packet. Treat `.agent_advice/active/*.md` as non-GT direction evidence only: list it as `used_advice`, never as `.agent_goal` goal truth.

When creating or updating task packs, use the task-pack contract from `$orchestrate-task-cycle` [task-pack-workflow.md](../orchestrate-task-cycle/references/task-pack-workflow.md). The JSON queue under `.task/task_pack/` is canonical; the adjacent Markdown file is a user-language render. Keep one active `task.md`; task packs are planning state, not goal truth or completion evidence.

## Activation Gate

Proceed only when the user clearly asks to use `$task-doctor`, asks to doctor/replace/retarget/reassign `task.md`, asks to create/update a task pack from current task direction, or provides a direct instruction that the active task direction must be externally changed before continuing.

If the user only reports that a task failed, asks to execute the current task, or asks for the normal cycle, use `$orchestrate-task-cycle`, `$task-md-agent-governance`, or `$derive-improvement-task` instead.

Require at least one explicit direction source before writing:

- A new objective, work direction, constraint, or priority from the user.
- A named candidate, issue, task miss, goal file, or prior task that should become the new active task.
- A named `.agent_advice/active/*.md` document or newly provided advice Markdown that the user explicitly wants incorporated into the doctored task.
- A task-pack proposal, ordered task list, or instruction to include the current `task.md` plus proposed changes in `.task/task_pack/`.
- A clear instruction to narrow, expand, defer, or replace the active task.

If the direction source is missing or ambiguous, perform only read-only diagnosis and ask for the missing instruction. Do not infer a replacement task from repository state alone.

Active advice existing on disk is not enough by itself to trigger task doctoring. Use it in this skill only when the user asks for `$task-doctor`, names the advice, or explicitly asks to fold that advice into `task.md`.

An active task pack existing on disk is not enough by itself to trigger task doctoring. Use or modify it only when the user explicitly asks to doctor task direction, names the pack, or asks to turn the current task and changes into a pack proposal.

## Scope

Allowed writes:

- `task.md`
- `.task/` task-state artifacts through `$manage-task-state-index`
- `.task/task_pack/*.json` and `.task/task_pack/*.md` task-pack proposals when the explicit doctoring instruction requests a task pack
- `.agent_log/` `past_task` and task-doctor handoff logs through `$record-agent-work-log`
- `.schema/` and `.contract/` records through `$manage-schema-contracts`
- `.issue/` tracking through `$manage-implementation-issues` when the replacement creates, resolves, or defers an implementation issue
- `.agent_advice/` lifecycle artifacts only through `$manage-external-advice` when the explicit doctoring instruction intakes, applies, rejects, or defers advice
- Git commits through `$repo-change-commit`

Forbidden writes:

- Source code, tests, notebooks, scripts, runtime/build/CI configuration, or generated implementation outputs.
- Goal truth files such as `.agent_goal/final_goal.md` or `.agent_goal/conventions.md` unless the user explicitly asked to edit the goal itself with the owning goal skill.
- Validation evidence that was not actually produced.

If the task direction change reveals a required code change, write it into the new `task.md` and leave implementation to `$orchestrate-task-cycle` and `$task-md-agent-governance`.

## Workflow

1. Establish the workspace and explicit instruction.
   - Locate the repository or workspace root.
   - Restate the user's explicit task-doctor instruction in one or two sentences.
   - Confirm whether the operation is `initial_task`, `replace_task`, `retarget_task`, `candidate_promotion`, `task_pack_proposal`, `task_pack_update`, or `task_pack_promotion`.
   - Stop before writing if the user instruction is not concrete enough to determine the new active task.

2. Read task and rule context.
   - Read `task.md` when present.
   - Read `.agent_goal/final_goal.md`, `.agent_goal/conventions.md`, `.agent_goal/goal_architecture.md`, `.agent_goal/goal_theory.md`, and `.agent_goal/goal_schema_contract.md` when present.
   - Read or render `.agent_advice/active/*.md` only when the user names advice or the doctoring instruction depends on advice; use `$manage-external-advice render-packet` for a compact packet.
   - Check repository-local rule files when present, such as `AGENTS.md`, `CONVENTIONS.md`, `CONVENTION.md`, `RULES.md`, `README.md`, `.codex/`, `.task/`, `.issue/`, `.schema/`, and `.contract/`.
   - Read `.task/index.md`, `.task/candidate_task/`, `.task/task_pack/`, `.task/task_miss/`, `.issue/`, and recent `.agent_log/` summaries when they are relevant to the requested direction.
   - When `.task/task_pack/` is relevant, run or request `$orchestrate-task-cycle` `scripts/task_pack_queue.py --root . status --format json` and `validate` for the active or named pack.
   - When the requested doctoring changes provider, OpenAI, credential, `.env`, terminal-blocker, or seal constraints, run `$orchestrate-task-cycle` `scripts/detect_gt_constraint_conflict.py --root .` on the current task and account for any conflict before writing the replacement.
   - When the requested doctoring cites workflow loop/dedup advice, run or request `$orchestrate-task-cycle` `scripts/detect_progress_loop.py --root .` and account for `feature_symbol_gate` without treating the advice itself as goal truth.
   - When the requested retarget touches a quiesced, sealed, or root-cause-exhausted family, run or request `$orchestrate-task-cycle` `scripts/detect_progress_loop.py --root .` and read the latest `anti_loop_progress_gate` if available. Account for `terminal_quiescence_gate`, `quiescence_untried_reconcile`, `hypothesis_exhausted`, and `.task/anti_loop/root_cause_ledger.jsonl` before writing the replacement.
   - Keep inspection at workflow and convention level. Do not inspect implementation source to solve the task.

3. Refresh traceability before replacement.
   - Use `$manage-task-state-index` `scan` when any task-state artifact exists.
   - Use `$manage-task-state-index` `audit` before replacing `task.md` when `.task/index.jsonl` exists.
   - Treat high-severity active-task, missing-file, duplicate-ID, or broken-link findings as blockers unless the replacement is explicitly meant to repair that condition.

4. Decide the task update shape.
   - Preserve all applicable user requirements and repo conventions.
   - Preserve the previous `## Execution Environment` section only when it remains applicable to the new task.
   - If no environment is applicable, set `Status: not_applicable`.
   - If a Python or runnable environment is needed but unknown, use `$find-local-python-envs` or mark `Status: unresolved` with the blocker. Do not install dependencies from this skill.
   - Keep the result narrow enough for one `$orchestrate-task-cycle` pass.
   - If the user requested a task pack, keep `task.md` as the single active executable task and use `.task/task_pack/` only for the ordered proposal. If the current task is included in the pack, represent it as an item with `status: promoted` or `in_progress`, `promotion.task_path: task.md`, and a planned next item after it.
   - Use a task pack only when the explicit direction contains an ordered sequence or when a single doctored task would lose important sequencing context. Otherwise write only `task.md`.
   - Do not create multiple active task packs. Update the named/active pack, or mark the old pack `superseded` before creating a replacement.
   - If active advice was used, decide whether it is incorporated into the new task, deferred for later implementation, or rejected because it conflicts with user instruction, GT, authority, or repository facts.
   - Do not write a replacement task that forbids a `.agent_goal` allowed or required provider/credential action unless the new task explicitly resolves the conflict or cites a newer explicit user instruction that supersedes the GT with a verifiable source. A bare phrase such as "latest user instruction" is not enough; include a timestamp or log/transcript path plus the quoted instruction text, or keep the prior supersession/authority state and ask the user for confirmation.
   - Do not write a replacement task whose progress case depends only on self-declared `produced_domain_delta=true`; require observed output evidence, legitimate provider-terminal evidence, consolidation, or explicit terminal/user escalation.
   - Do not write a replacement task that treats a new oracle, validator, metric, ladder record, dashboard, lineage, or gap report as `goal_productive` unless `coverage_quality_delta_gate.quality_delta_pass=true` or strict changed-and-semantic output-delta evidence exists.
   - Do not retarget a quiesced or `hypothesis_exhausted=true` family silently. A user-directed retarget is allowed, but the new `task.md` or task-pack mutation must record `quiescence_override` with the user instruction, supplied input delta, authority change, external-state change, or verified unexhausted root-cause evidence.
   - Do not preserve `single_work_id:true` as an indefinite generalization blocker. When `.agent_goal` or the current task requires corpus/generalization progress, require a bounded multi-work path with `single_work_id` separation, or terminal-block on the exact missing source/authority/provider condition.
   - Put `## Execution Environment` immediately after `# Task`.

5. Archive the old task before overwriting.
   - If `task.md` exists, use `$record-agent-work-log` to create a `past_task` entry before changing it.
   - Include the old task content or a safe summary, the user-provided doctor instruction, and why the old task was superseded.
   - Run `$manage-task-state-index` `scan` after logging so the old task is indexed as `past-*` or `log-*` when possible.
   - If `task.md` is absent, treat the operation as `initial_task` and skip `past_task` archival.

6. Write the new `task.md`.
   - Use this structure:

     ```markdown
     # Task

     ## Execution Environment

     - Status: selected | unresolved | not_applicable
     - Source: previous_task | find-local-python-envs | repository_manifest | user_instruction | manual_inference
     - Type: conda | venv | local | non_python | unknown
     - Name:
     - Python:
     - Run Prefix:
     - Dependency Notes:
     - Task Pack: <pack-id/path | none>
     - Task Pack Item: <item-id | none>
     - Pack Position: <order/total | none>
     - Pack Source: planned | inserted | reordered | user_instruction | none

     ## Objective

     <One concrete externally adjusted objective.>

     ## Background

     - Task doctor instruction:
     - Goal alignment:
     - Convention/rule alignment:
     - External advice source:
     - Issue/candidate/task_miss source:
     - Schema contract link:

     ## Requirements

     - <Specific requirement>

     ## Acceptance Criteria

     - <Observable completion condition>

     ## Validation

     - <Command, test, review, metric, or evidence required>

     ## Constraints

     - <Relevant convention, forbidden action, compatibility or safety rule>

     ## Out Of Scope

     - <What the next cycle must not attempt>

     ## Open Questions

     - <Unknowns, or `None`>
     ```

   - If the new task came from `.task/candidate_task/`, delete the applied candidate only after the new `task.md` is written and the transition is indexed. Keep unapplied candidates.
   - Do not delete task misses or issues from this skill unless their owning skill confirms the lifecycle transition.

7. Write or update a task-pack proposal when requested.
   - Create `.task/task_pack/` only when the explicit doctor instruction asks for a pack, sequence, ordered proposal, or current-task-plus-followups plan.
   - Use canonical JSON under `.task/task_pack/pack-<timestamp>-<slug>.json` and render `.task/task_pack/pack-<timestamp>-<slug>.md` in the user's language.
   - Follow the schema from `$orchestrate-task-cycle` [task-pack-workflow.md](../orchestrate-task-cycle/references/task-pack-workflow.md): `schema_version`, `pack_id`, `status`, `language`, `goal`, `current_item_id`, `items`, `mutation_log`, and optional `terminal_blocker`.
   - If the current `task.md` remains active and is included in the pack, make it the current pack item and set `promotion.task_path: task.md`; do not create a second active task.
   - If the doctor instruction replaces `task.md` and also creates a pack, make the new task the promoted/current item and put follow-up tasks after it as `planned`.
   - If the instruction only asks for a pack proposal, do not overwrite `task.md` unless the user explicitly asks to retarget the active task.
   - Validate and render the pack with:

     ```bash
     python3 /home/swfool/.codex/skills/orchestrate-task-cycle/scripts/task_pack_queue.py --root . validate
     python3 /home/swfool/.codex/skills/orchestrate-task-cycle/scripts/task_pack_queue.py --root . render --language <language>
     ```

   - If validation reports a blocking pack-schema issue, fix the pack before continuing to index or commit.

8. Reconcile state after replacement.
   - Use `$manage-schema-contracts` when `.agent_goal/goal_schema_contract.md`, `.schema/`, `.contract/`, or the new task names schema/module/script contract work.
   - Use `$manage-task-state-index` `scan` after writing `task.md` or `.task/task_pack/`.
   - Link relevant `adv-*` artifacts to the new task with `advice_for` or `incorporated_into` when `.agent_advice/` and `.task/index` exist.
   - Link task-pack artifacts to the new or current task with `pack_for_task` or `promoted_from_pack` when IDs are known.
   - Use `$manage-external-advice mark-applied` only when the advice directive is fully consumed or retired by the doctored task/design record. Otherwise keep it active and list it as a non-GT source for the later cycle.
   - Use `$manage-task-state-index` `audit`; write an audit report when the replacement touched candidates, task packs, task misses, issues, schema records, or prior task links.
   - Use `$manage-implementation-issues` when the new task intentionally defers, supersedes, creates, or tracks an implementation blocker.

9. Commit the task-direction change.
   - If `git rev-parse --is-inside-work-tree` returns `true`, invoke `$repo-change-commit` as the final mutating step.
   - Commit intent: task-doctor direction update only; include `Task: <new task id if known>`, old task/past log ID when known, and `Validation: not_run` unless a real validation command was run.
   - Let `$repo-change-commit` stage only coherent workflow artifacts and preserve unrelated local changes unstaged.
   - If the workspace is not a Git worktree, report that Git finalization was not applicable.

10. Hand off to orchestration.
   - Do not automatically run `$orchestrate-task-cycle` unless the user explicitly asked for both task doctoring and execution.
   - Report the new active task summary, important convention checks, old-task archive path, task/index IDs, schema/issue updates, commit hash or commit skip reason, and the recommended next invocation: `$orchestrate-task-cycle`.

## Compatibility Rules

- Preserve `$orchestrate-task-cycle` ordering by doing only pre-cycle task replacement and state reconciliation.
- Use `$derive-improvement-task` only when the user asks for agent-derived alternatives rather than direct task-doctor replacement. If used, keep its `past_task`, candidate deletion, and top execution-environment rules.
- Use `$manage-task-state-index` before and after task replacement whenever task-state artifacts exist.
- Use `$manage-task-state-index` before and after task-pack proposal changes whenever `.task/` exists.
- Keep `.agent_advice` separate from `.agent_goal`: advice can explain task direction but cannot override GT, grant authority, or satisfy `기준 GT`.
- Keep quiescence overrides explicit: when doctoring re-enters a terminal/quiesced/exhausted family, record the override reason and evidence instead of relying on renamed task wording.
- Link the new active task to the archived old task with `supersedes` or `archived_as` when IDs are known.
- Link task-pack proposals to the active/new task with `pack_for_task` or `promoted_from_pack` when IDs are known.
- Keep `task.md` formatted so `$task-md-agent-governance` can implement it without additional interpretation.
- Keep `.task/task_pack` formatted so `$derive-improvement-task` and `$orchestrate-task-cycle` can consume, insert, reorder, or terminal-block it without additional interpretation.
- Never claim the doctored task is complete. Completion belongs to `$validate-task-completion` after the later orchestrated cycle.

## Reporting

Report in Korean when the surrounding workflow is Korean or the repository uses `$orchestrate-task-cycle`. Preserve file paths, IDs, commands, and commit hashes exactly.

Use this concise order:

- `task doctor 지시:` explicit user direction used
- `규칙 확인:` goal/convention/rule files checked
- `외부 조언:` used `.agent_advice` paths or `없음`
- `이전 task 처리:` archived path or `없음`
- `신규 task:` objective and path
- `task pack:` pack path/status/current item or `없음`
- `상태 갱신:` index/schema/issue actions and IDs when known
- `Git:` commit hash or skip reason
- `다음 단계:` `$orchestrate-task-cycle` or the specific blocker
