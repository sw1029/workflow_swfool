# Task Miss Report Template

Write one Markdown report under `.task/task_miss/` after implementation and audit.

Filename:

```text
.task/task_miss/YYYYMMDD-HHMMSS-task-miss.md
```

Template:

```markdown
# Task Miss Report

- Timestamp:
- Workspace:
- Source task: `task.md`
- Status: success | partial | failed | audit_only

## Task Summary

- <intent and requirements extracted from task.md>

## Implementation Summary

- <files changed and behavior added>

## Validation Summary

- Commands run:
  - `<command>`: <result>
- Tests not run:
  - <reason>

## Audit Coverage

- Implementation workers:
  - <worker scope and changed files>
- `$inspect-repo-with-agents` coverage:
  - <agent/perspective/path coverage>

## Confirmed Misses

- Severity: blocker | high | medium | low
- Evidence: `<file:line>` or audit finding
- Miss: <requirement, behavior, or quality gap>
- Impact: <why it matters>
- Suggested follow-up: <specific remediation>

## Generalization Gaps

- Evidence: `<file:line>` or audit finding
- Narrow case: <single-case or hard-coded assumption>
- Missing variants: <inputs, contexts, data sizes, failure modes, users, environments>
- Suggested generalization: <how to broaden safely>

## Suspected Risks

- <risk not fully verified>

## No-Miss Notes

- If no material misses were found, state that explicitly and list residual uninspected risk.
```

Keep the report factual. Do not upgrade suspected risks into confirmed misses without evidence.

## Resolved Miss Report

When audit evidence shows prior misses are resolved, write a separate resolved report before archiving or deleting the prior miss file:

```text
.task/task_miss/YYYYMMDD-HHMMSS-task-miss-resolved.md
```

Template:

```markdown
# Task Miss Resolved Report

- Timestamp:
- Workspace:
- Source task: `task.md`
- Status: resolved | partially_resolved | obsolete_scope | resolved_archived | resolved_deleted

## Reviewed Prior Miss Files

- `.task/task_miss/<file>.md`: <prior miss summary>

## Resolution Summary

- <what changed or what evidence now resolves the miss>

## Evidence

- Code: `<file:line>` - <why it resolves the miss>
- Tests/validation: `<command or test>` - <result>
- Audit finding: <agent/perspective summary>

## Still Open Or Partial

- <remaining gap, if any>

## Cleanup Actions

- Prior file: `.task/task_miss/<file>.md`
- Action: keep_open | keep_partial | moved_to_resolved | deleted
- Destination if moved: `.task/task_miss/resolved/<file>.md`
- Deletion record: <why deletion was allowed and what evidence was preserved here>

## Generalization Check

- Original narrow case:
- Variants now covered:
- Variants still unverified:

## Residual Risk

- <remaining uncertainty>
```

Do not delete the prior miss file until this report preserves the original file path, original miss summary, resolution evidence, validation, cleanup action, and residual risk.

## Deleted Miss Report

If resolved prior miss files are deleted instead of archived, create this report:

```text
.task/task_miss/YYYYMMDD-HHMMSS-task-miss-deleted.md
```

Template:

```markdown
# Task Miss Deleted Report

- Timestamp:
- Workspace:
- Source task: `task.md`
- Deleted prior miss files:
  - `.task/task_miss/<file>.md`

## Deletion Basis

- Audit evidence:
- Validation evidence:
- User/task cleanup policy:

## Preserved Miss Summary

- Original miss:
- Original impact:
- Original follow-up:

## Resolution Evidence

- Code:
- Tests/validation:
- Audit finding:

## Residual Risk

- <remaining uncertainty or "None identified">
```

Only use deletion for audit-confirmed resolved or obsolete-scope misses. Keep still-open and partially resolved files active.
