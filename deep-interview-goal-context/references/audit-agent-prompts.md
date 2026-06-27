# Critical Audit Agent Prompts

Run exactly three independent audit agents after each draft cycle. Pass the base goal files, `.interview` questions and answers, all four drafts, existing retained content, and source evidence. Do not let auditors write files.

All auditors must use this output schema:

```text
verdict: CONFIRM | NEEDS_MORE_INTERVIEW
safe_to_write: yes | no
blocking_issues:
- ...
follow_up_questions:
- ...
ungrounded_claims:
- ...
missing_goal_links:
- ...
notes:
- ...
```

Use `NEEDS_MORE_INTERVIEW` when any material gap, unsupported claim, section mismatch, or unresolved goal alignment issue remains.

The main agent stores auditor outputs in `.interview/audit.md`. If any auditor returns `NEEDS_MORE_INTERVIEW`, the main agent adds targeted follow-up questions to `.interview/questions.md` and updates `.interview/confirmation.md`; auditors never edit those files directly.

## Auditor 1: Interview Coverage

```text
You are auditing whether the interview evidence is sufficient to fill `.agent_goal/goal_architecture.md`, `.agent_goal/goal_theory.md`, `.agent_goal/goal_schema_contract.md`, and `.agent_goal/agent_authority.md` for the existing base goal.

Review:
[final_goal.md]
[conventions.md]
[interview transcript]
[draft goal_architecture.md]
[draft goal_theory.md]
[draft goal_schema_contract.md]
[draft agent_authority.md]

Report:
1. Missing interview content needed to satisfy the base goal.
2. Architecture/theory/schema-contract/agent-authority sections that are under-supported.
3. Missing support for schema minimum fields, application intent, mandatory rules, or `$manage-schema-contracts` obligations.
4. Missing support for authority baseline, API/external-call policy, direction freedom, implementation/validation priority, conservative implementation, or escalation rules.
5. Targeted follow-up questions required.
6. Confirmation status using the required schema.

Confirm only if no material interview gaps remain.
```

## Auditor 2: Hallucination And Support

```text
You are auditing for hallucinated or unsupported content.

Review:
[final_goal.md]
[conventions.md]
[existing retained content]
[repository/source evidence]
[interview transcript]
[draft goal_architecture.md]
[draft goal_theory.md]
[draft goal_schema_contract.md]
[draft agent_authority.md]

Report:
1. Any claim not supported by interview answers, existing files, or source evidence.
2. Any inferred claim that should be labeled as inferred.
3. Any schema/contract requirement, target module/script, versioning rule, or causal relationship that was invented.
4. Any agent-authority requirement that was invented, conflicts with current effective agent permissions, or grants unsupported API/network/destructive authority.
5. Any content that should be removed.
6. Targeted follow-up questions required.
7. Confirmation status using the required schema.

Confirm only if every substantive claim is supported or clearly labeled.
```

## Auditor 3: Format And Goal Satisfaction

```text
You are auditing whether the drafts satisfy `$manage-goal-architecture`, `$manage-goal-theory`, the goal schema-contract template, the `$manage-agent-authority` agent-authority template, `$manage-schema-contracts` needs, `$orchestrate-task-cycle` / `$derive-improvement-task` / `$task-md-agent-governance` authority-consumption needs, and the base `$manage-agent-goal` content.

Review:
[final_goal.md]
[conventions.md]
[draft goal_architecture.md]
[draft goal_theory.md]
[draft goal_schema_contract.md]
[draft agent_authority.md]

Report:
1. Missing required headings or sections.
2. Content in the wrong file or section.
3. Missing schema-contract minimum fields, application intent, mandatory rules, versioning, target modules/scripts, producer/consumer, compatibility, validation, or causal-map requirements.
4. Missing agent-authority baseline, API/external-call policy, direction-freedom profile, implementation/validation priority, conservative implementation, escalation, or precedence requirements.
5. Mismatch with final goal or conventions.
6. Targeted follow-up questions required.
7. Confirmation status using the required schema.

Confirm only if all four drafts are structurally correct and aligned with the base goal.
```
