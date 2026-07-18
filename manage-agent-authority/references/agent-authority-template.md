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

## Decision Ownership And Autonomy Envelope

- Source-rank owners:
  - `S3` goal owner: <Who may ratify core goal, authority, and R3 changes.>
  - `S2` policy steward: <Which bounded authority/task decisions may be delegated.>
  - `S1` cycle coordinator: <Which task-slice and dispatch choices may be coordinated.>
  - `S0` executor: <Which implementation tactics may be selected.>
- Core concepts (`D0`, change requires goal-owner ratification):
  - <Opaque concept ID and exact revision/digest; do not include private source text.>
- Bounded design concepts (`D1`):
  - <Opaque concept ID, allowed options/range, deterministic selection rule, decision owner.>
- Task-topology decisions (`D2`):
  - <Allowed insert/delete/reorder/retarget scope and budget.>
- Execution tactics (`D3`):
  - <Reversible local choices allowed inside the bounded design.>
- External-input availability:
  - <available | missing_supplyable | missing_unsupplyable | unverified, independently from permission.>

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
- Approval cardinality default:
  - <single_use | bounded_reusable | task_lease | improvement_lease | standing_policy; prefer the narrowest sufficient choice.>
- Approval UX:
  - <State action, reason, exact subject/effects, exclusions, use/time/cost budget, delegated lower choices, revocation path, and safe alternative.>

## Typed Decision Separation

- Authority grants:
  - <Who may issue/delegate/revoke which exact capability namespaces.>
- Goal-truth ratification:
  - <Who may ratify D0 concept/revision changes; never infer from a grant.>
- Risk/cost acceptance:
  - <Which R2/R3 effects need separate consent; never infer from permission.>
- External-input supply:
  - <Who or what can supply it; do not treat approval as availability.>
- Design selection:
  - <Which bounded options are autonomous and which need an explicit choice.>

## Precedence And Overrides

- Highest priority: current system/developer/user instructions and active tool/sandbox permissions.
- This file may only narrow or clarify behavior.
- The newest explicit user instruction controls the current turn when it conflicts with stored goal authority.
- Runtime grants and leases must bind an immutable snapshot of this policy; do not bind new receipts to this mutable current file.
- Higher source rank may narrow or revoke a lower-rank grant only inside the same exact capability lineage and subject scope. It cannot create a session capability.

## Open Questions

- <Unsupported authority decision, missing approval rule, or unknown external-call policy.>
```
