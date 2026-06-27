---
name: repo-change-commit
description: "Inspect a local Git repository's implementation state and create an intentional commit using fixed `reasoning_effort: low` for commit finalization work. Separate intentional source changes from generated or local-only files, account for `.issue/` or GitHub issue context, enforce goal-aware commit readiness, update .gitignore for files that should not be tracked, verify source-change coherence, stage only the right files, include issue or goal/task references, and coordinate Git state with issue-tracked or `/goal` task cycles."
---

# Repo Change Commit

## Overview

Use this skill to turn a dirty repository into a deliberate commit without hiding important work or committing local noise. Keep the workflow conservative: inspect first, ignore generated artifacts precisely, stage only coherent changes, validate what is practical, then commit.

When a Codex `/goal` is active, treat `.agent_goal/goal_contract.yaml` as the commit contract. A commit is allowed only when the diff is inside the goal scope, a task node or checkpoint exists, validation is recorded as `passed` or explicitly `known_failed`, and the commit message carries the goal and task identity. Do not turn a partial goal state into an ambiguous success commit.

When invoked from `$orchestrate-task-cycle`, treat commit finalization as the authoritative source of created commit hashes. Workflow artifacts written before this skill may contain `base_commit` or pre-commit context; do not rely on those hashes as the final cycle commit. Use `commit_role: implementation` for the validation/issue-gated change set and `commit_role: closeout` for report/dashboard/ledger/advice artifacts after report rendering.

## Routing Policy

- When called from `$orchestrate-task-cycle`, consume the canonical orchestration reference [workflow-routing.md](../orchestrate-task-cycle/references/workflow-routing.md) as caller context, but keep commit finalization's own fixed routing below.
- Treat commit finalization as low-reasoning work. When this skill is invoked through a subagent or delegated skill call, set `reasoning_effort: low` whenever the tooling exposes it.
- Apply the same fixed `reasoning_effort: low` to Git status classification, `.gitignore` noise cleanup, staging decisions, commit-message assembly, and actual `git commit` execution performed by this skill.
- Do not inherit high/xhigh code-analysis or validation routing from caller workflows. Expensive code review should already have happened before this skill runs.
- If tooling cannot enforce `reasoning_effort: low`, include the low-effort requirement in the prompt and report the limitation in the outcome.

## Workflow

1. Establish repository state.
   - Confirm the current directory is inside a Git worktree.
   - Run `git status --short --branch`, `git diff --stat`, `git diff --name-status`, and `git ls-files --others --exclude-standard`.
   - Read the active task context if present, such as the user request, `task.md`, `.issue/` issue records or GitHub issue mirrors, recent changed files, or relevant project docs.
   - Read validation/progress context when present, especially `validation_verdict`, `progress_verdict`, active blockers, issue IDs, and whether the commit is complete, partial/checkpoint, or safety-only.
   - Read `commit_role` when supplied. For `$orchestrate-task-cycle`, default missing `commit_role` to `implementation` before report rendering and to `closeout` only when the closeout packet explicitly names rendered report/dashboard artifacts.
   - Read active goal context when present: `.goal/active_goal.md`, `.agent_goal/goal_contract.yaml`, `.task/goal_plan.yaml`, `.goal/progress.jsonl`, `.goal/checkpoints/`, and `.task/validation/latest.json`.
   - If `.issue/` names a branch/worktree for the active issue, confirm the current branch/worktree matches the intended issue context or report the mismatch before committing.
   - Inspect diffs for touched source, tests, config, docs, and `.gitignore`. Do not rely only on filenames.

2. Classify files before changing `.gitignore`.
   - Usually track: source code, tests, docs, lockfiles when the project already tracks them, migrations, schemas, intentional config, small fixtures, and reproducible project metadata.
   - Usually ignore: interpreter caches, test caches, build outputs, coverage outputs, dependency folders, local virtual environments, editor state, OS metadata, logs, temporary files, downloaded model/data caches, and runtime artifacts.
   - Treat `.issue/` issue records and GitHub issue mirrors as intentional workflow artifacts when they were created by `$manage-implementation-issues` and relate to the current task cycle.
   - Treat used `.agent_advice/active` or `.agent_advice/applied` files as intentional workflow artifacts when a task cycle consumed them, unless the caller records a sensitive/local-only reason.
   - For `commit_role: closeout`, usually track `.task/cycle/<cycle-id>/dashboard.md`, `final_report.md`, `commit-result.json`, `stage.jsonl`, `current_stage.json`, packets needed for handoff, and used advice lifecycle files.
   - Treat large data, binary outputs, generated reports, model weights, notebooks with generated output, and environment files as case-specific. Inspect enough context to decide whether they are source assets or local artifacts.
   - `.gitignore` does not untrack files already in Git. If a tracked file should become untracked, explain that `git rm --cached <path>` is needed and only do it when the user's request clearly authorizes that index change.

3. Update `.gitignore` narrowly.
   - Prefer project-specific patterns over broad patterns that could hide real source files.
   - Preserve existing organization and comments. Add short section comments only when they improve scanability.
   - Avoid ignoring secrets by pattern alone as the only safety measure; if likely secrets are present, stop and report the risk.
   - Validate important patterns with `git check-ignore -v <path>` when possible.
   - Re-run `git status --short --branch` and `git ls-files --others --exclude-standard` after edits to confirm noise is gone and important files remain visible.

4. Verify the nature of source changes.
   - Group changes by intent: implementation, tests, docs, config, `.gitignore`, generated cleanup, or unrelated local work.
   - Group issue tracking changes separately: `.issue/` mirrors, local issue records, issue resolution records, and branch/worktree handoff notes.
   - Group goal workflow changes separately: `.agent_goal/goal_contract.yaml`, `.task/goal_plan.yaml`, `.goal/progress.jsonl`, `.goal/checkpoints/`, `.task/validation/latest.json`, and schema/contract refresh artifacts.
   - Group closeout workflow changes separately: cycle dashboard, final report, commit-result, stage ledger/current_stage, rendered packets, and used advice lifecycle files.
   - If unrelated user changes are present, leave them unstaged and state that they were preserved.
   - Stop before committing if the diff contains unexplained rewrites, accidental formatting churn, secrets, huge files, broken conflict markers, or unclear generated code.
   - For a small task, a concise diff review is enough. For shared behavior or broad changes, inspect call sites and test coverage more deeply.

5. Apply the goal-aware commit gate when goal artifacts exist.
   - Require `.agent_goal/goal_contract.yaml` to be present and current relative to `.goal/active_goal.md` and `.agent_goal/final_goal.md`.
   - Confirm changed files match `allowed_touch_paths`, do not match `forbidden_touch_paths`, and stay inside the active `.task/goal_plan.yaml` node `touches` when an active node defines them.
   - Confirm an active task node or `.goal/checkpoints/` checkpoint exists.
   - Confirm `.task/validation/latest.json` records `verdict: passed`, or records a clear `known_failed` state when the user explicitly requested committing a known-broken checkpoint.
   - If validation passed but progress is `safety_only` or `no_progress`, allow a coherent checkpoint commit only when the commit message/body clearly states that final-goal or issue completion is not proven.
   - Confirm no unresolved `.task/task_miss` blockers, high-severity open `.issue` blockers, or running `.agent_log` jobs make the commit look complete when it is not.
   - If schema/interface files changed, require refreshed `.schema/` or `.contract/` evidence, or a documented `needs_review` schema contract note.
   - Stop before committing when the goal gate fails. Record the missing evidence instead of bypassing hook policy.

6. Run practical validation.
   - Prefer the repository's existing test or lint commands from docs, package scripts, Makefiles, CI config, or project conventions.
   - Prefer validation commands named in `.agent_goal/goal_contract.yaml` when a `/goal` is active.
   - If full validation is expensive or unavailable, run the cheapest meaningful checks, such as focused tests, type checks, import checks, or compile checks.
   - If validation cannot run because dependencies, network, or environment are missing, record that explicitly in the final response instead of implying success.

7. Stage and commit intentionally.
   - Stage exact paths for the coherent change set. Avoid broad `git add .` when unrelated files exist.
   - Before committing, inspect `git diff --cached --stat`, `git diff --cached --name-status`, and `git status --short`.
   - Use a short imperative commit subject, usually under 72 characters. Add a body only when it helps explain separate concerns such as `.gitignore` cleanup plus source changes.
   - Include a GitHub issue number or local issue ID in the commit body when `.issue/` or the active branch clearly identifies one.
   - Include `Goal: <goal_id>`, `Task: <task_id>`, `Validation: <command/result>`, and `Schema: clean|refreshed|needs_review|not_applicable` when `.agent_goal/goal_contract.yaml` or `.task/goal_plan.yaml` exists.
   - Include `Progress: advanced|safety_only|no_progress|regressed|not_recorded` when the validation report or orchestrator provides a progress verdict.
   - Include `Commit-Role: implementation|closeout` when `$orchestrate-task-cycle` supplies a role.
   - For `safety_only`, `no_progress`, `partial`, failed, or known-failed checkpoint commits, include an explicit remaining-blocker line and avoid subjects or bodies that imply task/final-goal completion.
   - For `commit_role: closeout`, keep the subject clearly about workflow closeout artifacts, and do not amend or rewrite a report solely to include the closeout commit hash created by the same commit.
   - Do not close issues from this skill. `$manage-implementation-issues` closes or archives issues only after verification evidence exists.
   - Run `git commit` only when the user asked for a commit. Afterward, report `git log -1 --oneline` and the remaining `git status --short --branch`.
   - Report both the pre-commit/base hash when known and the created commit hash. The created commit hash is the authoritative finalization result.

## Commit Message Guidance

Choose a message that names the user-facing or repository-facing intent, not the mechanics of the session.

Examples:

```text
Ignore local runtime artifacts
```

```text
Commit implementation state cleanup

- Ignore generated cache and log files
- Preserve unrelated local changes unstaged
```

```text
Add parser validation flow
```

Goal-aware example:

```text
feat(goal:T002): implement phishing URL feature extraction

Goal: 2026-05-23-main-refactor
Task: T002
Validation: pytest tests/phishing_url - passed
Schema: clean
```

## Safety Rules

- Never reset, checkout, delete, or overwrite local changes unless the user explicitly requested that exact operation.
- Never run commit finalization with inherited high/xhigh reasoning when the tooling exposes `reasoning_effort`; use fixed `low` for this skill.
- Never commit secrets, credentials, private tokens, local `.env` files, or generated files that appear to contain sensitive data.
- Never hide uncertainty by committing everything. If file ownership or intent is unclear, ask or leave the file unstaged and explain why.
- Keep `.gitignore` changes reversible and specific enough that future source files are unlikely to disappear from `git status`.
- Never close or archive GitHub/local issues as part of committing; preserve that lifecycle for `$manage-implementation-issues`.
- Never bypass the goal-aware hook gate by weakening `.agent_goal/goal_contract.yaml`, editing validation evidence without running validation, or omitting `Goal`/`Task` identity from a goal-cycle commit.
- Never label a `/goal` commit as complete unless the goal status is `complete_verified` and validation evidence is passed. Use an explicit known-failed checkpoint commit only when the user asked for that state.
- Never let a `safety_only` validation pass look like issue closure, readiness promotion, or final-goal progress in the commit message.
- Never write a commit hash into pre-existing workflow artifacts after committing unless a new follow-up commit or explicit amend is intended; report the created hash in the skill outcome instead.
- Never leave used active/applied advice or rendered closeout reports untracked in an orchestrated Git-backed cycle unless the caller records a local-only reason.
