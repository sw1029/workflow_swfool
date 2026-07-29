---
name: repo-change-commit
description: "Inspect a local Git repository and create one intentional, goal-aware commit. Use for coherent staging, validation-aware checkpoint/closeout messages, and session-cycle one-commit settlement that embeds its own verification anchor without a follow-up metadata commit."
---

# Repo Change Commit

## Overview

Use this skill to turn a dirty repository into a deliberate commit without hiding important work or committing local noise. Keep the workflow conservative: inspect first, ignore generated artifacts precisely, stage only coherent changes, validate what is practical, then commit.

Creating the commit is `finalize_git_state` in `authority.operations.json` and follows the shared [authority v2 contract](../manage-agent-authority/references/authority-v2-contract.md). Validation, coherent staging, or task completion does not itself authorize committing a different exact repository subject; pushing remains a separate external operation. `push_git_ssh` is S3/R3/external/single-use, always requires an exact confirmation, and must bind the SSH remote identity, branch, refspec, and commit SHA. Never let authority-interaction mode cover push, force, tag deletion, or remote changes.

When a Codex `/goal` is active, treat `.agent_goal/goal_contract.yaml` as the commit contract. A commit is allowed only when the diff is inside the goal scope, a task node or checkpoint exists, validation is recorded as `passed` or explicitly `known_failed`, and the commit message carries the goal and task identity. Do not turn a partial goal state into an ambiguous success commit.

When invoked from `$orchestrate-task-cycle`, treat commit finalization as the authoritative source of the created commit hash. Workflow artifacts written before this skill may contain `base_commit` or pre-commit context; those are not the final cycle commit. A non-session caller may use `commit_role: implementation|closeout`. The adaptive session workflow batches implementation and workflow artifacts into one `closeout` commit after validation, derive, index, dashboard, and report.

## One-commit session settlement

For an adaptive session, do not create an implementation commit followed by a
closeout-metadata commit. Stage the complete coherent payload except the anchor, then
prepare `git_embedded_settlement@v1`:

```bash
SKILLS_ROOT="${CODEX_HOME:-$HOME/.codex}/skills"
PYTHONPATH="$SKILLS_ROOT/repo-change-commit/scripts:$SKILLS_ROOT/manage-agent-authority/scripts" \
  python3 -P -m repo_change_commit prepare-anchor \
  --root . \
  --anchor-path .task/authorization/settlements/<cycle-id>.json \
  --message-file /path/to/exact-message.txt \
  --intent settlement-intent.json
```

The closed intent binds `commit_role`, nullable goal/task/cycle/session IDs, exact
producer-owned authority request and reservation, and pre-commit evidence. The
producer reopens their fixed artifacts, validates request/reservation/pre-commit
and session lineage, then uses a
temporary index to project the payload without touching the real index, writes the
canonical anchor, and stages only that anchor. Reinspect the final staged set, make
one commit with the exact message, then verify `HEAD` read-only:

```bash
PYTHONPATH="$SKILLS_ROOT/repo-change-commit/scripts:$SKILLS_ROOT/manage-agent-authority/scripts" \
  python3 -P -m repo_change_commit verify-head \
  --root . \
  --anchor-path .task/authorization/settlements/<cycle-id>.json
```

Verification binds the parent, message digest, anchor bytes, payload tree, changed
paths, goal/task/cycle/session, and authority evidence. It returns a terminal derived
receipt with `tracked_post_commit_receipt_required=false`; never create a second
tracked receipt or amend solely to record the commit hash. Push is still a separate
exact S3/R3 operation.

## Routing Policy

- When called from `$orchestrate-task-cycle`, consume the canonical orchestration reference [workflow-routing.md](../orchestrate-task-cycle/references/workflow-routing.md) as caller context, but keep commit finalization's own fixed routing below.
- Treat commit finalization as Tier 1 low-reasoning work. When invoked through a subagent or delegated skill call, request `model_ref: model_ref:balanced` with `reasoning_effort: low` under `configured-tiered-routing-v3`.
- Apply the same fixed `reasoning_effort: low` to Git status classification, `.gitignore` noise cleanup, staging decisions, commit-message assembly, and actual `git commit` execution performed by this skill.
- Do not inherit high/xhigh code-analysis or validation routing from caller workflows. Expensive code review should already have happened before this skill runs.
- Keep runtime model bindings in caller configuration or a repository adapter. If the binding is absent, retain `model_configuration_status: reference_only`; if tooling cannot enforce the resolved model/effort, report `routing_enforcement: prompt_only|inherited_unverified` and a limitation. Never claim enforced routing or actual-model execution from an abstract reference alone.

## Workflow

1. Establish repository state.
   - Confirm the current directory is inside a Git worktree.
   - Run `git status --short --branch`, `git diff --stat`, `git diff --name-status`, and `git ls-files --others --exclude-standard`.
   - Read the active task context if present, such as the user request, `task.md`, `.issue/` issue records or GitHub issue mirrors, recent changed files, or relevant project docs.
   - Read validation/progress context when present, especially `validation_verdict`, `progress_verdict`, active blockers, issue IDs, and whether the commit is complete, partial/checkpoint, or safety-only.
   - Read `commit_role` when supplied. For an adaptive session, require `closeout` and one complete payload. For a non-session `$orchestrate-task-cycle` call, default missing `commit_role` to `implementation` before report rendering and to `closeout` only when the closeout packet explicitly names rendered report/dashboard artifacts.
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
   - For `commit_role: closeout`, keep the subject about the coherent task/cycle outcome, not merely metadata. Do not amend or rewrite a report solely to include the commit hash created by the same commit.
   - In an adaptive session, prepare and validate the embedded settlement anchor after every intended payload path is staged and before `git commit`; verify `HEAD` immediately afterward without writing another tracked artifact.
   - Do not close issues from this skill. `$manage-implementation-issues` closes or archives issues only after verification evidence exists.
   - Run `git commit` only when the user asked for a commit. Afterward, report `git log -1 --oneline` and the remaining `git status --short --branch`.
   - Report both the pre-commit/base hash when known and the created commit hash. The created commit hash is the authoritative finalization result.
   - Report `agent_routing_applicability: deterministic_only` when commit work ran directly. When delegated, include the Tier 1 profile, requested model reference, model-configuration status, requested model/effort when resolved, reason codes, and routing enforcement or limitation.

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
- Never use delegated `ultra` or raise effort to resolve readiness ambiguity; return the ambiguity to validation or issue handling.
- Never commit secrets, credentials, private tokens, local `.env` files, or generated files that appear to contain sensitive data.
- Never hide uncertainty by committing everything. If file ownership or intent is unclear, ask or leave the file unstaged and explain why.
- Keep `.gitignore` changes reversible and specific enough that future source files are unlikely to disappear from `git status`.
- Never close or archive GitHub/local issues as part of committing; preserve that lifecycle for `$manage-implementation-issues`.
- Never bypass the goal-aware hook gate by weakening `.agent_goal/goal_contract.yaml`, editing validation evidence without running validation, or omitting `Goal`/`Task` identity from a goal-cycle commit.
- Never label a `/goal` commit as complete unless the goal status is `complete_verified` and validation evidence is passed. Use an explicit known-failed checkpoint commit only when the user asked for that state.
- Never let a `safety_only` validation pass look like issue closure, readiness promotion, or final-goal progress in the commit message.
- Never write a commit hash into pre-existing workflow artifacts after committing unless a new follow-up commit or explicit amend is intended; report the created hash in the skill outcome instead.
- Never create a second “receipt commit” after an embedded session settlement; `verify-head` is deliberately read-only.
- Never leave used active/applied advice or rendered closeout reports untracked in an orchestrated Git-backed cycle unless the caller records a local-only reason.
