# Evidence Consistency Agent Prompts

Run exactly three independent evidence-consistency agents after a completed interview batch has been incorporated into `.interview/drafts/goal_architecture.md`, `.interview/drafts/goal_theory.md`, `.interview/drafts/goal_schema_contract.md`, and `.interview/drafts/agent_authority.md`. These agents do not write files. The main agent records their outputs in `.interview/evidence_review.md`.

The purpose is to catch hallucinations, unsupported claims, contradictions, policy/convention violations, and output-path mistakes before final confirmation or `.agent_goal` writes.

## Shared Output Schema

```text
verdict: CONFIRM | NEEDS_REVISION | NEEDS_MORE_INTERVIEW
safe_to_write: yes | no
hallucinations_or_unsupported_claims:
- ...
interview_contradictions:
- ...
missing_interview_support:
- ...
convention_or_policy_violations:
- ...
template_or_output_path_issues:
- ...
required_draft_edits:
- ...
follow_up_questions:
- ...
notes:
- ...
```

Confirm only when the drafts and proposed final write content are fully supported by the existing interview record, base goal files, conventions, and repository evidence, and when the final output paths are exactly `.agent_goal/goal_architecture.md`, `.agent_goal/goal_theory.md`, `.agent_goal/goal_schema_contract.md`, and `.agent_goal/agent_authority.md`.

## Reviewer 1: Interview Evidence Coverage

```text
You are checking whether the draft architecture/theory/schema-contract/agent-authority content is supported by the existing interview record.

Review:
[.agent_goal/final_goal.md]
[.agent_goal/conventions.md]
[.interview/state.md]
[.interview/questions.md]
[.interview/answers.md]
[.interview/audit.md if present]
[.interview/confirmation.md]
[.interview/drafts/goal_architecture.md]
[.interview/drafts/goal_theory.md]
[.interview/drafts/goal_schema_contract.md]
[.interview/drafts/agent_authority.md]
[repository/source evidence summary if available]

Focus:
1. Claims that lack support in the interview answers, base goal files, or repository evidence.
2. Questions whose answers were ignored or contradicted by the drafts.
3. Missing questions required to support important draft content.
4. Schema-contract minimum fields, application intent, mandatory rules, and `$manage-schema-contracts` requirements that lack support.
5. Agent-authority claims about API calls, external services, direction freedom, implementation/validation priority, conservative posture, or escalation that lack support or imply unavailable permissions.
6. Draft sections that overstate certainty or should mark content as inferred.

Use the shared output schema. Return CONFIRM only if every material claim is supported or clearly labeled as inferred.
```

## Reviewer 2: Hallucination And Violation Check

```text
You are checking for hallucination, invented requirements, policy/convention violations, and unsafe stored content.

Review:
[.agent_goal/final_goal.md]
[.agent_goal/conventions.md]
[.interview/questions.md]
[.interview/answers.md]
[.interview/drafts/goal_architecture.md]
[.interview/drafts/goal_theory.md]
[.interview/drafts/goal_schema_contract.md]
[.interview/drafts/agent_authority.md]
[repository/source evidence summary if available]

Focus:
1. Architecture relationships, algorithms, constraints, or theory claims that were invented.
2. Schema/contract requirements, target modules/scripts, versioning rules, or causal relationships that were invented.
3. Agent-authority requirements that were invented, conflict with current agent permissions, or appear to grant API/network/destructive authority without explicit support.
4. Content that violates `.agent_goal/conventions.md` or interview constraints.
5. Sensitive raw transcripts, secrets, credentials, or large copyrighted excerpts.
6. Required draft edits before any final write.

Use the shared output schema. Return NEEDS_REVISION for draft-only fixes. Return NEEDS_MORE_INTERVIEW when user answers are required.
```

## Reviewer 3: Final Write Readiness

```text
You are checking whether the drafts can proceed toward final confirmation and final `.agent_goal` writing.

Review:
[.interview/state.md]
[.interview/questions.md]
[.interview/answers.md]
[.interview/drafts/goal_architecture.md]
[.interview/drafts/goal_theory.md]
[.interview/drafts/goal_schema_contract.md]
[.interview/drafts/agent_authority.md]
[proposed final `.agent_goal/goal_architecture.md`, `.agent_goal/goal_theory.md`, `.agent_goal/goal_schema_contract.md`, and `.agent_goal/agent_authority.md` content]

Focus:
1. Whether all active-batch questions are answered or skipped.
2. Whether the drafts use the correct goal architecture/theory/schema-contract/agent-authority placement and templates.
3. Whether the schema-contract draft includes supported minimum fields, application intent, mandatory rules, and `$manage-schema-contracts` obligations.
4. Whether the agent-authority draft preserves the default-current-agent baseline, cannot grant extra permissions, and contains supported API/external-call, direction-freedom, implementation/validation-priority, conservative-posture, and escalation rules.
5. Whether the final write destinations are exactly `.agent_goal/goal_architecture.md`, `.agent_goal/goal_theory.md`, `.agent_goal/goal_schema_contract.md`, and `.agent_goal/agent_authority.md`.
6. Whether any unresolved blocker should prevent final confirmation.

Use the shared output schema. Return CONFIRM only if the workflow can safely advance to final user confirmation or final review.
```
