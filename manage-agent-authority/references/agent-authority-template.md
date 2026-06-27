# Agent Authority Template

Use this template for `.agent_goal/agent_authority.md` and `.interview/drafts/agent_authority.md`.

This file is the goal-level authority policy consumed by `$manage-agent-authority`, `$orchestrate-task-cycle`, `$derive-improvement-task`, `$task-md-agent-governance`, and `$deep-interview-goal-context`.

Do not use this file to grant authority beyond the active session's system/developer/user instructions, filesystem sandbox, approval rules, network availability, or tool capabilities. It may only narrow, prioritize, or clarify behavior within the current effective permissions.

```markdown
# Agent Authority

## Authority Baseline

- Default authority: `default_current_agent_permissions`
- Effective meaning: inherit the current coding agent's sandbox, approval rules, available tools, user/developer/system instructions, and repository/workspace permissions.
- Expansion rule: this file cannot grant network/API/destructive authority or external access that the active session does not already have.

## API And External Calls

- Default policy: <forbidden | ask_first | allowed_when_task_requires | read_only | inherit_current_permissions>
- Allowed examples:
  - <Supported API/network/external-service use, or `none confirmed`.>
- Approval requirements:
  - <When to request explicit user approval.>
- Forbidden or blocked calls:
  - <API/network/external actions that must not be attempted.>

## Direction Freedom

- Freedom profile: <strict | bounded_variation | implementation_first | artifact_confirmation_first | quality_first | conservative>
- Allowed variation:
  - <What task/implementation variation is allowed without asking.>
- Must ask or stop when:
  - <Direction changes requiring user confirmation.>

## Implementation And Validation Priority

- Implementation priority: <implementation_first | conservative_implementation | minimal_change | exploratory_allowed>
- Output/artifact confirmation priority: <required | preferred | not_applicable>
- Quality verification priority: <quality_first | balanced | smoke_check_only | user_directed>
- Validation posture:
  - <Required tests, artifact checks, manual review, or evidence before claiming completion.>

## Escalation And Approval

- Ask before:
  - <Network, API, destructive, long-running, costly, credentialed, or direction-changing actions.>
- May proceed without asking:
  - <Routine edits/checks allowed under current permissions.>
- Blocker reporting:
  - <How agents should report authority conflicts.>

## Precedence And Overrides

- Highest priority: current system/developer/user instructions and active tool/sandbox permissions.
- This file may only narrow or clarify behavior.
- The newest explicit user instruction controls the current turn when it conflicts with stored goal authority.

## Open Questions

- <Unsupported authority decision, missing approval rule, or unknown external-call policy.>
```
