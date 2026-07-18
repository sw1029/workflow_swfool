---
name: manage-implementation-issues
description: Manage implementation issues that arise during task cycles by creating, tracking, indexing, and resolving GitHub-backed or local `.issue/` issue records. Use when Codex needs to open an issue for a new or failed `task.md`, track implementation blockers, allocate a dedicated Git branch/worktree for an issue, fall back to `.issue/` documents outside a Git/GitHub worktree, close or archive resolved issues with `$run-task-code-and-log` evidence, link issue artifacts through `$manage-task-state-index`, or coordinate issue-aware handoff with `$derive-improvement-task`, `$orchestrate-task-cycle`, and `$repo-change-commit`.
---

# Manage Implementation Issues

## Overview

Use this skill to keep implementation issues explicit during repository task cycles. Prefer a GitHub issue with a dedicated branch/worktree when the workspace is a Git worktree and GitHub issue tooling is available; otherwise create durable local issue documents under `.issue/`.

Use `authority.operations.json` and the shared [authority v2 contract](../manage-agent-authority/references/authority-v2-contract.md). Local issue lifecycle mutation and external issue-service mutation are different operations; external service availability, issue necessity, and local issue authority never substitute for an exact external-operation grant.

This skill manages issue state and traceability. It must not implement code fixes. Code changes belong to `$task-md-agent-governance`; execution or resolution evidence belongs to `$run-task-code-and-log`; commits belong to `$repo-change-commit`.

Use the closed result `issue_status` vocabulary `created | updated | open | tracked | partial | blocked | failed | reopened | resolved | closed | skipped | not_applicable`. Do not invent completion-like aliases.

For local issue file structure and fields, read [issue-format.md](references/issue-format.md). For the issue-fit analysis agent used by `$derive-improvement-task`, read [issue-agent-prompts.md](references/issue-agent-prompts.md).

When a task validation reports `progress_verdict: safety_only` or `no_progress`, preserve that distinction in the issue update. Do not describe a still-open issue as substantively advanced merely because a no-live/fail-closed guardrail passed.

When session governance is available, consume only a trusted-collector privacy-safe projection from [$audit-session-governance](../audit-session-governance/SKILL.md). A separate deterministic comparator receipt may support opening or updating an issue; a session-owned canonical claim, transcript-only observation, capture absence, quarantine, or incomplete packet cannot establish resolution, authority, or a blocker by itself unless acceptance/caller independently required audit completeness.

## Workflow

1. Load task and issue context.
   - Read `task.md`, `.task/index.md`, `.task/index.jsonl`, `.task/task_miss/`, `.agent_log/`, `.agent_goal/`, `.schema/`, `.contract/`, and `.issue/` when present.
   - Run `$manage-task-state-index` `scan` when `.task/`, `.issue/`, `.agent_log/`, or `task.md` exists.
   - Determine the operation: open/track a new issue, update an existing issue, resolve/close an issue, sync issue state, or audit issue traceability.
   - Default in `$orchestrate-task-cycle` is to reconcile the just-validated current task before `$derive-improvement-task` creates or promotes a successor. Return issue IDs, blocker state, and evidence paths so derivation can make an authoritative next-task decision.

2. Choose the issue backend.
   - Check whether the current directory is inside a Git worktree with `git rev-parse --is-inside-work-tree`.
   - If it is a Git worktree and a GitHub remote plus issue tooling is available, prefer creating or updating a GitHub issue.
   - Use the GitHub app when available; otherwise use `gh issue create`, `gh issue edit`, `gh issue close`, and `gh issue view` when authenticated.
   - If GitHub issue creation is unavailable, unauthenticated, or the remote is not GitHub, create or update local `.issue/` files instead and record the fallback reason.
   - Never block issue tracking only because GitHub tooling is unavailable; local `.issue/` is the durable fallback.

3. Open or track an issue.
   - Derive the issue title from the active `task.md` objective or validation blocker.
   - Include goal fit, task ID, validation status, issue source, expected branch/worktree, acceptance criteria, and links to task_miss, validation, schema/contract, and agent log evidence when known.
   - Include progress status when known (`advanced`, `safety_only`, `no_progress`, or `regressed`) and the remaining blocker-state transition required to move the issue forward.
   - For a session-audit finding, cite the trusted projection and, when present, the separate comparator receipt—not transcript text or packet-owned relation claims. Route semantic/source/task/acceptance repair through the owning governed skill; issue management records the work but does not apply it.
   - Before reopening or reactivating an issue in a quiesced or exhausted blocker family, inspect the latest loopback/progress-loop evidence for `terminal_quiescence_gate`, `quiescence_untried_reconcile`, `hypothesis_exhausted`, and `.task/anti_loop/root_cause_ledger.jsonl`. Reopen only when the issue supplies a concrete input delta, authority change, external-state change, or verified unexhausted repair path.
   - For GitHub-backed issues, create or update a local mirror under `.issue/open/` or `.issue/git/` containing the remote URL, issue number, branch, worktree path, and task links.
   - For local-only issues, create `.issue/open/YYYYMMDD-HHMMSS-<slug>.md` using [issue-format.md](references/issue-format.md).
   - After writing any local mirror or local-only issue, run `$manage-task-state-index` `scan` and link the issue to the active `task-*` with `issue_for` or `tracks_task`.

4. Allocate a Git branch and worktree for GitHub-backed issues.
   - Use a branch name such as `issue/<number>-<slug>` or `issue/<local-id>-<slug>`.
   - Use a sibling worktree path such as `../<repo-name>-issue-<number>-<slug>` unless the repository already has a worktree convention.
   - Create the branch/worktree only after preserving unrelated local changes and confirming no unsafe dirty-state assumptions are needed.
   - Prefer non-destructive commands such as `git worktree list`, `git branch --list <branch>`, and `git worktree add -b <branch> <path> HEAD`.
   - Record branch and worktree mapping in the issue body or local mirror.
   - Do not implement the issue in the newly allocated worktree from this skill.

5. Resolve or close an issue.
   - Require concrete evidence before closing: validation report, task_miss resolution, command output, or another factual run artifact.
   - Use `$run-task-code-and-log` to run or record the verification command/procedure and create `.agent_log` evidence, including failed or partial verification.
   - If verification succeeds, close the GitHub issue or move the local issue from `.issue/open/` to `.issue/resolved/` or `.issue/closed/`.
   - Preserve a resolution record under `.issue/resolved/` even when the remote GitHub issue is closed.
   - Link the issue to the run log, validation report, and resolving task with `resolved_by`, `run_for`, `validates`, or `closes_issue`.
   - If verification is partial or failed, keep the issue open and record the blocker.

6. Sync and index issue state.
   - Use `$manage-task-state-index` after issue creation, update, close, archive, or mirror refresh.
   - Index `.issue/` issue docs as `issue-*` artifacts.
   - Link issues to `task-*`, `cand-*`, `miss-*`, `run-*`, `val-*`, `schema-*`, `goal-*`, and `log-*` artifacts when known.
   - Use relation names such as `issue_for`, `tracks_task`, `blocked_by`, `derived_from_issue`, `fixes_issue`, `closes_issue`, `resolved_by`, `worktree_for`, and `branch_for`.
   - If the same issue records two or more consecutive `safety_only` or `no_progress` task completions, add a concise note that the next task should supply/validate missing evidence, perform a bounded source-backed preflight/run, batch remaining no-live boundaries, or stop with an explicit missing-input/authorization blocker.

7. Report status.
   - Summarize issue backend, issue ID or URL, local mirror path, branch/worktree path, linked task ID, index result, and any unresolved blockers.
   - Report `agent_routing_applicability: deterministic_only` unless the optional issue-fit agent ran. If it ran, include the `configured-tiered-routing-v3` Tier 3 `model_ref:balanced`/high profile, requested model reference, model-configuration status, requested model/effort when resolved, and routing enforcement or limitation. Runtime bindings belong to caller configuration or a repository adapter; `reference_only` cannot prove enforced or actual-model execution.
   - For `$orchestrate-task-cycle`, explicitly state whether the new active `task.md` is tracked by a GitHub issue or `.issue/` document.

## Orchestrated Cycle Behavior

When called by `$orchestrate-task-cycle` after `$validate-task-completion` and before `$derive-improvement-task`:

- Reconcile the validated current task and its existing issues before any successor task is written or promoted. Do not assume `task.md` has already been replaced.
- If validation is `partial` or `failed`, also create or update an issue for validation blockers and link it to the completed task evidence.
- If validation is `complete` but `progress_verdict` is `safety_only` or `no_progress`, keep the relevant issue open and record the remaining blocker-state transition; do not treat the issue as resolved.
- If a prior issue is quiesced or its root-cause hypothesis budget is exhausted, do not reopen it silently. Record `quiescence_override` with the supplied input-delta evidence, or keep it blocked/closed and route the next cycle to terminal/user escalation.
- If validation is `complete` and a prior issue is proven resolved, use `$run-task-code-and-log` evidence before closing or archiving it.
- Return `issue_status`, explicit `issue_ids` (an empty list when no issue applies), `blockers`, and `evidence_paths`. `$derive-improvement-task` consumes that packet; the post-derive task-state index links the selected successor to any carried issue.
- Do not commit issue files directly; leave commit classification and staging to `$repo-change-commit`.

## Git Integration

- Use `$repo-change-commit` for final staging and commits after issue tracking files or branch/worktree mappings are written.
- If an issue has a remote number, pass that context to `$repo-change-commit` so the commit can mention the issue when appropriate.
- Do not close GitHub issues from `$repo-change-commit`; issue closure remains this skill's responsibility after verification evidence exists.

## Progress Labels

- `advanced`: issue blocker materially reduced or a required evidence/readiness state was unlocked.
- `safety_only`: no-live/fail-closed safety boundary passed, but the issue's missing evidence/readiness blocker remains.
- `no_progress`: issue state did not change in a durable way.
- `regressed`: issue became worse or a required gate weakened.

## Guardrails

- Do not implement code, tests, scripts, notebooks, or runtime/build/CI changes from this skill.
- Do not create a GitHub issue that contains secrets, credentials, private tokens, sensitive raw data, or large copyrighted excerpts.
- Do not close or archive an issue without concrete `$run-task-code-and-log`, validation, or task_miss resolution evidence.
- Do not reopen a quiesced or `hypothesis_exhausted=true` issue without supplied input-delta, authority, external-state, or verified unexhausted root-cause evidence.
- Do not create destructive branch/worktree changes. Avoid deleting branches or worktrees unless the user explicitly asks and the issue is already closed or archived.
- Do not treat `.issue/` as a replacement for `task.md`; it tracks issue state and handoff, while `task.md` remains the actionable task.
- Do not leave GitHub-backed issues without a local mirror when task-state indexing is expected.
