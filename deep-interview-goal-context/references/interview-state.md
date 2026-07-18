# Interview State Files

## Table of Contents

- [Directory Layout](#directory-layout)
- [`state.md`](#state-md)
- [`questions.md`](#questions-md)
- [`answers.md`](#answers-md)
- [`evidence_review.md`](#evidence-review-md)
- [`audit.md`](#audit-md)
- [`confirmation.md`](#confirmation-md)
- [`final_review.md`](#final-review-md)

Use `.interview/` as the durable state directory for this skill. It is separate from `.agent_goal/`; `.interview` records the elicitation process, while `.agent_goal` stores the final reusable goal context.

## Directory Layout

```text
.interview/
├── state.md
├── questions.md
├── answers.md
├── evidence_review.md
├── audit.md
├── confirmation.md
├── final_review.md
└── drafts/
    ├── goal_architecture.md
    ├── goal_theory.md
    ├── goal_schema_contract.md
    └── agent_authority.md
```

Final successful writes must create or update these exact files:

```text
.agent_goal/
├── goal_architecture.md
├── goal_theory.md
├── goal_schema_contract.md
└── agent_authority.md
```

Do not treat `.interview/drafts/goal_architecture.md`, `.interview/drafts/goal_theory.md`, `.interview/drafts/goal_schema_contract.md`, or `.interview/drafts/agent_authority.md` as final output.

Create missing files only after the `.agent_goal/final_goal.md` and `.agent_goal/conventions.md` hard gate passes.

<a id="state-md"></a>

## `state.md`

Track the current phase:

```markdown
# Interview State

- phase: initialized | questions_ready | awaiting_answers | drafting | evidence_review_needs_revision | audit_needs_more_interview | awaiting_user_final_confirm | final_confirmed | written
- last_updated: <date/time if available>
- active_batch: <Batch n or "none">
- current_question_id: <q-id or "none">
- last_asked_question_id: <q-id or "none">
- single_question_mode: yes | no
- goal_concept_graph_status: absent | draft | confirmed | unclassified_legacy
- legacy_authority_migration: not_required | unclassified | complete
- source_goal_files:
  - `.agent_goal/final_goal.md`
  - `.agent_goal/conventions.md`
- notes:
  - <short operational notes>
```

<a id="questions-md"></a>

## `questions.md`

Store selected user-facing questions, not every raw question produced by subagents.

```markdown
# Interview Questions

## Batch <n>

batch_status: active | answered | audited | superseded
batch_source: bootstrap | initial-summary | audit-follow-up | final-review-follow-up

- id: q-001
  status: pending | answered | skipped
  priority: blocker | important | optional
  target_file: goal_architecture.md | goal_theory.md | goal_schema_contract.md | agent_authority.md | both | all
  target_section: <section>
  question: <exact question to ask the user>
  why_needed: <gap or risk>
  source: initial-summary | audit-follow-up | final-review-follow-up
```

When asking the user during continuation mode, present exactly one pending question from the active batch. If `batch_status` is missing in an older file, derive it from the question statuses: a batch is complete when every question in that batch is `answered` or `skipped`.

For legacy state that predates the goal concept graph or operation-level authority contract, add only the missing state fields with `unclassified_legacy` / `unclassified`. Preserve existing answers and confirmations. Create a follow-up question only when a current final write or downstream decision depends on the missing classification. Never translate old silence, existing implementation, or a later approval into a historical user decision.

If `.interview/state.md` has no `active_batch`, use the first batch with a `pending` question. Keep asking one question from that batch across invocations until the batch is complete. Only after the batch is complete should the main workflow draft and audit, then either create a new follow-up batch or ask for final confirmation.

<a id="answers-md"></a>

## `answers.md`

Record user answers by question id. Preserve meaning faithfully, but redact sensitive raw content.

```markdown
# Interview Answers

## q-001

- answered_at: <date/time if available>
- source_question_id: q-001
- user_answer: <faithful answer, summarized only when needed for safety>
- interpretation_notes:
  - <what this answer supports>
- unresolved_parts:
  - <anything still unanswered>
```

When an answer follows a one-question prompt, map it to `.interview/state.md` `last_asked_question_id` unless the user explicitly references another id.

<a id="evidence-review-md"></a>

## `evidence_review.md`

Append each three-agent evidence-consistency cycle after a completed question batch has been incorporated into drafts and before final confirmation/write.

```markdown
# Evidence Consistency Review

## Cycle <n>

- draft_architecture: `.interview/drafts/goal_architecture.md`
- draft_theory: `.interview/drafts/goal_theory.md`
- draft_schema_contract: `.interview/drafts/goal_schema_contract.md`
- draft_agent_authority: `.interview/drafts/agent_authority.md`
- reviewed_interview_files:
  - `.interview/state.md`
  - `.interview/questions.md`
  - `.interview/answers.md`
  - `.interview/audit.md`
  - `.interview/confirmation.md`

### Reviewer 1
- verdict: CONFIRM | NEEDS_REVISION | NEEDS_MORE_INTERVIEW
- safe_to_write: yes | no
- hallucinations_or_unsupported_claims:
- interview_contradictions:
- convention_or_policy_violations:
- required_draft_edits:
- follow_up_questions:
- concept_graph_digest_valid: yes | no | not_evaluated
- authority_concept_rights_consistent: yes | no | not_evaluated

### Reviewer 2
...

### Reviewer 3
...

## Cycle Result
- all_confirmed: yes | no
- evidence_review_confirmed: yes | no
- next_phase: drafting | evidence_review_needs_revision | audit_needs_more_interview | awaiting_user_final_confirm
- hold_reason: <reason or "none">
```

Only a latest cycle with `all_confirmed: yes` allows the workflow to request final confirmation or write final `.agent_goal` files.

<a id="audit-md"></a>

## `audit.md`

Append each three-agent audit cycle.

```markdown
# Interview Audit

## Cycle <n>

- draft_architecture: `.interview/drafts/goal_architecture.md`
- draft_theory: `.interview/drafts/goal_theory.md`
- draft_schema_contract: `.interview/drafts/goal_schema_contract.md`
- draft_agent_authority: `.interview/drafts/agent_authority.md`

### Auditor 1
- verdict: CONFIRM | NEEDS_MORE_INTERVIEW
- safe_to_write: yes | no
- blocking_issues:
- follow_up_questions:

### Auditor 2
...

### Auditor 3
...

## Cycle Result
- all_confirmed: yes | no
- next_phase: awaiting_user_final_confirm | audit_needs_more_interview
```

<a id="confirmation-md"></a>

## `confirmation.md`

Track user-facing confirmation separately from agent audit.

```markdown
# Interview Confirmation

- status: collecting | audit_needs_more_interview | awaiting_user_final_confirm | final_confirmed | written
- audit_confirmed: yes | no
- evidence_review_confirmed: yes | no
- awaiting_user_final_confirm: yes | no
- final_confirmed: yes | no
- confirmed_by: <user message reference or "not confirmed">
- confirmed_at: <date/time if available>
- agent_write_confirmed: yes | no
- agent_write_confirmed_by: <main-agent | reviewer-summary | "not confirmed">
- agent_write_decision_at: <date/time if available>
- write_hold_reason: <reason or "none">
- final_output_paths:
  - `.agent_goal/goal_architecture.md`
  - `.agent_goal/goal_theory.md`
  - `.agent_goal/goal_schema_contract.md`
  - `.agent_goal/agent_authority.md`
- write_completed: yes | no
```

Only `final_confirmed: yes` allows the final 3-6 agent review to start. It does not by itself authorize writing. Final writing also requires `evidence_review_confirmed: yes` and `agent_write_confirmed: yes`, with `agent_write_confirmed` decided after final review and immediately before the write.

<a id="final-review-md"></a>

## `final_review.md`

Record the 3-6 final review agents run after final confirmation.

```markdown
# Final Review

## Reviewer <n>
- verdict: CONFIRM | NEEDS_MORE_INTERVIEW
- safe_to_write: yes | no
- blocking_issues:
- follow_up_questions:
- notes:

## Result
- all_confirmed: yes | no
- write_allowed: yes | no
- agent_write_confirmed: yes | no
- write_hold_reason: <reason or "none">
```

If `write_allowed: yes` and `agent_write_confirmed: yes`, write exactly `.agent_goal/goal_architecture.md`, `.agent_goal/goal_theory.md`, `.agent_goal/goal_schema_contract.md`, and `.agent_goal/agent_authority.md`; use `$manage-agent-authority finalize_from_interview` for `.agent_goal/agent_authority.md`. If not, hold all four files, add follow-up questions to `.interview/questions.md`, and set `final_confirmed: no`, `awaiting_user_final_confirm: no`, or `audit_needs_more_interview` as appropriate.
