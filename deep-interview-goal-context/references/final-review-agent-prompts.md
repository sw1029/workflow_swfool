# Final Review Agent Prompts

Run at least three independent critical final review agents only after `.interview/confirmation.md` records final confirmation. Use 3-6 reviewers by default. Final reviewers do not write files, and final `.agent_goal` writing is forbidden unless every reviewer confirms and the main agent records `agent_write_confirmed: yes` immediately before the write.

## Shared Prompt

```text
You are performing final review before `.agent_goal/goal_architecture.md`, `.agent_goal/goal_theory.md`, `.agent_goal/goal_schema_contract.md`, and `.agent_goal/agent_authority.md` are written.

Review:
[.agent_goal/final_goal.md]
[.agent_goal/conventions.md]
[.interview/state.md]
[.interview/questions.md]
[.interview/answers.md]
[.interview/evidence_review.md]
[.interview/audit.md]
[.interview/confirmation.md]
[.interview/drafts/goal_architecture.md]
[.interview/drafts/goal_theory.md]
[.interview/drafts/goal_schema_contract.md]
[.interview/drafts/agent_authority.md]
[repository/source evidence summary if available]
[proposed final `.agent_goal/goal_architecture.md`, `.agent_goal/goal_theory.md`, `.agent_goal/goal_schema_contract.md`, and `.agent_goal/agent_authority.md` write content]

Task:
1. Confirm that final user confirmation is present.
2. Confirm that interview answers are sufficient to support the drafts.
3. Confirm that the latest three-agent evidence-consistency cycle confirmed and that all evidence-review blockers are resolved or explicitly carried as open questions.
4. Confirm that all prior audit blockers are resolved or explicitly carried as open questions.
5. Identify hallucinated, unsupported, or over-specific content.
6. Verify that final drafts use the `$manage-goal-architecture`, `$manage-goal-theory`, goal schema-contract template, and `$manage-agent-authority` agent-authority template structures.
7. Verify that `.agent_goal/goal_schema_contract.md` includes supported minimum fields, application intent, required application rules, versioning expectations, target module/script guidance, and `$manage-schema-contracts` obligations.
8. Verify that `.agent_goal/agent_authority.md` preserves the default-current-agent authority baseline, cannot grant unavailable permissions, and includes supported API/external-call, direction-freedom, implementation/validation-priority, conservative-implementation, escalation, and precedence rules.
9. Verify that sensitive raw content, secrets, credentials, and large copyrighted excerpts are not stored.
10. Confirm that no final architecture/theory/schema-contract/agent-authority content is being added only because the prompt was absent, weak, or guessed.
11. Confirm that the proposed final write destinations are exactly `.agent_goal/goal_architecture.md`, `.agent_goal/goal_theory.md`, `.agent_goal/goal_schema_contract.md`, and `.agent_goal/agent_authority.md`, not `.interview/drafts/`, `.schema/`, `.contract/`, or alternate filenames.

Output exactly this schema:
verdict: CONFIRM | NEEDS_MORE_INTERVIEW
safe_to_write: yes | no
agent_write_recommendation: CONFIRM_WRITE | HOLD_WRITE
blocking_issues:
- ...
follow_up_questions:
- ...
unsupported_or_risky_claims:
- ...
template_or_placement_issues:
- ...
write_hold_reason: <reason or "none">
notes:
- ...

Confirm only if the latest evidence-consistency cycle is confirmed and the final drafts can be written without adding unsupported content and without violating the base goal, conventions, schema-contract governance requirements, or agent-authority governance requirements. Return `agent_write_recommendation: HOLD_WRITE` whenever there is any uncertainty, missing support, unresolved evidence-review blocker, unresolved audit blocker, unsafe content, unsupported authority expansion, or template mismatch. If the interview began from bootstrap questions because the raw prompt was absent or weak, verify that every project-specific claim is supported by later user answers or repository evidence.
```

## Reviewer Lens Suggestions

Use different lenses when spawning reviewers:

- Goal coverage and missing interview evidence.
- Hallucination, source support, and inference labeling.
- Architecture template, repo structure, and module responsibility placement.
- Theory template, assumptions, algorithms, tradeoffs, and validation logic.
- Goal schema-contract template, minimum fields, mandatory rules, versioning, and `$manage-schema-contracts` usability.
- `$manage-agent-authority` template, API/external-call policy, direction freedom, implementation/validation priority, conservative implementation, escalation, and higher-priority instruction precedence.
- Safety/privacy/redaction and forbidden content.
- Operational continuity: whether future agents can resume from `.interview` and `.agent_goal`.
