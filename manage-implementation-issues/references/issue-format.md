# Issue Format

Use `.issue/` as the local issue registry and as the indexable mirror for GitHub-backed issues.

## Layout

```text
.issue/
├── index.md
├── open/
│   └── YYYYMMDD-HHMMSS-<slug>.md
├── resolved/
│   └── YYYYMMDD-HHMMSS-<slug>.md
├── closed/
│   └── YYYYMMDD-HHMMSS-<slug>.md
└── git/
    └── github-<number>-<slug>.md
```

Use only the directories needed by the workspace. GitHub-backed issues should still have a `.issue/git/` or `.issue/open/` mirror so `$manage-task-state-index` can index them.

## Issue Document Template

```markdown
# Implementation Issue: <short title>

- issue_id: <local stable id or github-issue-number>
- status: open | blocked | in_progress | resolved | closed | superseded
- source: github | local
- remote_url: <GitHub issue URL or none>
- remote_number: <GitHub issue number or none>
- task_id: <task-* id or unknown>
- task_path: task.md
- priority: blocker | high | medium | low
- goal_fit: fit | partial | misfit | unknown
- branch: <issue branch or none>
- worktree_path: <dedicated worktree path or none>
- validation_status: missing | partial | passed | failed | not_applicable
- created_at: <date/time if available>
- updated_at: <date/time if available>

## Problem

<What issue must be tracked.>

## Goal Fit

<Why this issue fits or does not fit `.agent_goal` and current task direction.>

## Evidence

- <task, validation, run, audit, miss, schema, or source evidence>

## Required Resolution

- <observable resolution requirement>

## Links

- task:
- validation:
- run log:
- task_miss:
- schema/contract:

## Resolution

- resolved_by:
- verification:
- residual_risk:
```

## Indexing Notes

The task-state index scans `.issue/**/*.md` as issue artifacts. Keep the scalar fields near the top so the indexer can extract `issue_id`, `source`, `remote_url`, `remote_number`, `task_id`, `goal_fit`, `branch`, `worktree_path`, and `validation_status`.
