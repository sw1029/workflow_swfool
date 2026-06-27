# Goal Schema Contract Template

Use this template for `.interview/drafts/goal_schema_contract.md` and final `.agent_goal/goal_schema_contract.md`.

The file is the goal-level contract that `$manage-schema-contracts` must satisfy when creating or updating `.schema/` and `.contract/` artifacts. It defines the minimum fields, application intent, and mandatory rules for repository schema/contract governance.

```markdown
# Goal Schema Contract

## Purpose

- Define why schema/contract governance is required for this goal.
- State how `.schema/` and `.contract/` artifacts support `.agent_goal/final_goal.md`, `.agent_goal/conventions.md`, `.agent_goal/goal_architecture.md`, `.agent_goal/goal_theory.md`, and `.agent_goal/agent_authority.md` when authority policy affects validation, API/external calls, or execution posture.

## Application Intent

- Intended use by `$manage-schema-contracts`:
- Intended use by task derivation, governance audits, validation, and repo inspection:
- Scope boundaries:

## Minimum Contract Fields

Every managed schema/contract artifact must preserve or explicitly mark these fields as not applicable:

- `contract_id`
- `type`
- `status`
- `version`
- `owner_path`
- `target_modules`
- `target_scripts`
- `producers`
- `consumers`
- `inputs`
- `outputs`
- `invariants`
- `compatibility`
- `validation`
- `source_evidence`
- `updated_at`

## Required Application Rules

- Versioning rule:
- Target module/script rule:
- Producer/consumer rule:
- Compatibility rule:
- Causal-map rule:
- Validation evidence rule:
- Needs-review rule:
- Prohibited content rule:

## Required Causal Relationships

List relationship types that `.schema/causal_map.md`, `.schema/contracts.jsonl`, or `.contract/` artifacts must track:

- `contract_for`
- `schema_for`
- `module_contract_for`
- `script_contract_for`
- `depends_on`
- `produces_schema`
- `consumes_schema`
- `compatible_with`
- `breaks_contract`
- `supersedes_contract`

## Mandatory Checks For Future Agents

- During `$orchestrate-task-cycle`:
- During `$derive-improvement-task`:
- During `$task-md-agent-governance`:
- During `$validate-task-completion`:
- During `$inspect-repo-with-agents`:

## Open Questions

- <schema/contract governance issue that still needs user or repository evidence>
```
