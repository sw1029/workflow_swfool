---
name: deep-interview-goal-context
description: Conduct a stateful critical deep-interview workflow to populate `.agent_goal/goal_architecture.md`, `.agent_goal/goal_theory.md`, `.agent_goal/goal_schema_contract.md`, and `.agent_goal/agent_authority.md`, only after `.agent_goal/final_goal.md` and `.agent_goal/conventions.md` exist from `$manage-agent-goal`. Use when the user asks to interview, answer, continue, confirm, audit, or fill architecture/theory/schema-contract/agent-authority goal context; when a weak invocation should continue `.interview` one pending question at a time; or when hallucination-resistant goal context requires staged questions, evidence review, final critical review, and guarded `.agent_goal` writes.
---

# Deep Interview Goal Context

Use `authority.operations.json` and the shared [authority v2 contract](../manage-agent-authority/references/authority-v2-contract.md). Drafting the interview concept graph is a reversible authority-free projection; final goal-truth publication is a separate exact grant-controlled effect and still requires independent goal-owner ratification.

## Overview

Use this skill to run a persistent interview that fills the goal architecture, theory, schema-contract, and agent-authority goal files only after the base goal files already exist and contain real content:

- Required prerequisites: `.agent_goal/final_goal.md` and `.agent_goal/conventions.md`.
- Interview state: `.interview/`.
- Final output targets: `.agent_goal/goal_architecture.md`, `.agent_goal/goal_theory.md`, `.agent_goal/goal_schema_contract.md`, and `.agent_goal/agent_authority.md`.
- Writer and consumer skills: `$manage-goal-architecture`, `$manage-goal-theory`, `$manage-schema-contracts`, `$manage-agent-authority`, `$orchestrate-task-cycle`, `$derive-improvement-task`, and `$task-md-agent-governance`.

Final architecture, theory, schema-contract, and agent-authority goal content must be written only under `.agent_goal/`. Files under `.interview/drafts/` are review drafts and must never be treated as final goal artifacts.

This is a stateful deep-interview workflow. Do not run an unbounded conversation loop in one turn. On each skill invocation, load `.interview`, determine the next state, present one pending question or record the user's answer, and then advance the stored state.

The process should treat the user's raw prompt as intent evidence, not as a complete specification. Split the prompt into confirmed facts, assumptions, open questions, and risks before drafting architecture, theory, schema-contract, or agent-authority content.

Read [goal-concept-graph.md](references/goal-concept-graph.md) whenever the interview must classify core ideas, bounded design freedom, runtime-adaptive choices, concept relationships, or downstream decision ownership. Keep the canonical graph inside the existing goal-theory and goal-architecture artifacts; do not add a fifth final goal file.

If the user invokes only this skill, provides no raw prompt, or provides a weak prompt such as "continue", "start interview", or a vague request to fill architecture/theory/schema-contract/agent-authority context, do not stop for lack of prompt detail after the hard gate passes. First inspect `.interview/questions.md`. If unanswered generated questions already exist and final confirmation is not complete, ask exactly one unanswered question from the active batch. If no prior questions exist, start with bootstrap interview questions from [bootstrap-questions.md](references/bootstrap-questions.md), store them in `.interview/questions.md`, and ask only the first unanswered question.

When task-state indexing is available, use `$manage-task-state-index` to give `.interview/` and `.agent_goal/` artifacts stable IDs. If no ID context exists, continue the interview workflow unchanged.

## Hard Gate

Before generating interview questions, read `.agent_goal/final_goal.md` and `.agent_goal/conventions.md`.

Proceed only when both files:

- Exist in `.agent_goal/`.
- Are not empty or placeholder-only.
- Define a concrete objective and at least one convention/constraint/practice.

If the gate fails, stop architecture/theory/schema-contract/agent-authority interviewing and ask prerequisite questions needed to complete `$manage-agent-goal` first. Do not create default architecture/theory/schema-contract/agent-authority content.

## Stateful Invocation Workflow

1. Load goal and interview state.
   - Read `.agent_goal/final_goal.md` and `.agent_goal/conventions.md`.
   - Read existing `.agent_goal/goal_architecture.md`, `.agent_goal/goal_theory.md`, `.agent_goal/goal_schema_contract.md`, and `.agent_goal/agent_authority.md` if present.
   - Create `.interview/` if the hard gate passed and no interview state exists.
   - Record whether the raw prompt is `present`, `absent`, or `weak` in `.interview/state.md`.
   - Follow the state files described in [interview-state.md](references/interview-state.md).
   - Track `active_batch`, `current_question_id`, and `last_asked_question_id` in `.interview/state.md` when asking one question at a time.
   - Detect legacy interview/final files that lack concept class, mutability, decision owner, relation, or exact authority-decision evidence. Preserve their content, record `legacy_authority_migration: unclassified|not_required|complete`, and create only blocking follow-up questions. Do not infer a historical user decision or retroactive delegation.
   - Run `$manage-task-state-index` `scan` when `.agent_goal/` or `.interview/` exists. Use `goal-*` and `int-*` IDs when available; do not block interviewing if they are absent.

2. If the newest user message answers pending questions, record it first.
   - Treat a message after a single-question prompt as the answer to `last_asked_question_id` unless the user explicitly names another question id.
   - Append the answer to `.interview/answers.md`.
   - Mark the answered question ids in `.interview/questions.md`.
   - Preserve the user's meaning; do not silently normalize intent.
   - Redact or summarize sensitive raw content instead of storing it verbatim.
   - If the active batch still has unanswered questions, ask exactly one next unanswered question from that same batch and stop the turn.
   - If the active batch is fully answered or skipped, proceed to drafting and audit instead of immediately generating another batch.

3. If unanswered questions are pending, present the next single question.
   - Load `.interview/questions.md`.
   - Select the active batch as the first batch whose questions are not all `answered` or `skipped`, unless `.interview/state.md` already names an active batch with pending questions.
   - Ask only one pending question from that batch.
   - Include the question id and the question text. Keep supporting context minimal; do not include unrelated pending questions.
   - Update `.interview/state.md` with `phase: awaiting_answers`, `active_batch`, `current_question_id`, and `last_asked_question_id`.
   - Do not regenerate all questions unless the pending set is empty or stale.

4. If no pending questions exist and interview evidence is incomplete, generate questions.
   - If the raw prompt is absent or weak and no prior questions exist, seed `.interview/questions.md` from [bootstrap-questions.md](references/bootstrap-questions.md) before spawning question-generation agents.
   - If bootstrap questions were seeded, ask only the first unanswered question immediately; run the full staged agent question generation later only after those answers are recorded or if extra coverage is needed.
   - Use six stages, in this order: perspective, process, theory, detailed elements, constraints, authority.
   - For each stage, spawn exactly three independent question-generator agents unless the user explicitly changes the count.
   - Spawn one final question-summary agent after all stage agents return.
   - Store selected questions as a new batch in `.interview/questions.md`; do not ask every generated question.
   - After storing a new batch, ask only the first unanswered question from that batch.
   - Use [question-agent-prompts.md](references/question-agent-prompts.md) and [summary-agent-prompt.md](references/summary-agent-prompt.md).
   - In theory and authority stages, require coverage of the goal concept graph: core/guardrail/variable classes, relation mutability, allowed variation, deterministic choice rules, decision owner, and exact concept revision/digest. Do not turn proposed graph rows into confirmed GT before the normal confirmation gates.

5. Draft into `.interview/drafts/`, not directly into `.agent_goal`.
   - Use only base goal files, existing retained context, repository evidence, and recorded interview answers.
   - Draft `.interview/drafts/goal_architecture.md` in the `$manage-goal-architecture` template.
   - Draft `.interview/drafts/goal_theory.md` in the `$manage-goal-theory` template.
   - Draft `.interview/drafts/goal_schema_contract.md` using [goal-schema-contract-template.md](references/goal-schema-contract-template.md).
   - Use `$manage-agent-authority` in `draft_for_interview` mode to draft `.interview/drafts/agent_authority.md` from its embedded [agent-authority-template.md](../manage-agent-authority/references/agent-authority-template.md).
   - The schema-contract draft must include minimum schema fields, application intent, mandatory application rules, target modules/scripts guidance, versioning expectations, and requirements that `$manage-schema-contracts` must satisfy when managing `.schema/` or `.contract/`.
   - The agent-authority draft must document the default-current-agent baseline and any supported project-specific policy for API/external calls, direction freedom, strictness, implementation priority, output/artifact confirmation, quality verification, conservative implementation, escalation, and override precedence.
   - Put the canonical draft concept-node/relation tables and graph digest in `goal_theory.md`; put the concept-to-component/consumer realization map in `goal_architecture.md`; let schema and authority drafts reference only exact concept IDs and digests. Authority records decision rights and operation requirements, not concept truth.
   - Treat these draft files as temporary review inputs only. They are not final goal architecture/theory/schema-contract/agent-authority files.
   - Mark inferred content as inferred and keep unsupported content out of the drafts.

6. Run the interview-evidence consistency loop.
   - After the active batch is fully answered or skipped and all four drafts exist, spawn exactly three independent evidence-consistency agents before any final `.agent_goal` write.
   - The agents must compare the drafts and proposed final write content against the existing `.interview` state, questions, answers, prior audit records, base goal files, and repository evidence.
   - Require reviewers to recompute or independently check concept/relation digests, identify unsupported core/locked classifications, and reject authority rows that widen a graph envelope or conflate grant, goal ratification, risk acceptance, external-input supply, and design selection.
   - Store their outputs in `.interview/evidence_review.md`; use [evidence-consistency-agent-prompts.md](references/evidence-consistency-agent-prompts.md).
   - If any agent reports `NEEDS_REVISION`, `NEEDS_MORE_INTERVIEW`, `safe_to_write: no`, hallucination, unsupported claim, or convention violation, do not ask for final confirmation and do not write `.agent_goal` files.
   - Convert unresolved evidence gaps into targeted follow-up questions in `.interview/questions.md`, set `.interview/state.md` to `evidence_review_needs_revision` or `audit_needs_more_interview`, set `.interview/confirmation.md` to `evidence_review_confirmed: no` and `audit_confirmed: no`, and return to single-question continuation.
   - If the fixes only require draft edits and no new user answer, revise `.interview/drafts/` and run the three-agent evidence-consistency loop again.
   - Repeat this feedback loop until all three evidence-consistency agents return `CONFIRM` and `safe_to_write: yes` in the same cycle.
   - When all three evidence-consistency agents confirm in the same cycle, set `.interview/confirmation.md` to `evidence_review_confirmed: yes`.
   - Only after all three evidence-consistency agents confirm may the workflow continue to the critical draft audit and later final confirmation.

7. Audit the drafts with three independent critical agents.
   - Spawn exactly three independent audit agents for each draft cycle.
   - Store results in `.interview/audit.md`.
   - If any auditor returns `NEEDS_MORE_INTERVIEW`, store selected follow-up questions as the next batch in `.interview/questions.md`, set `.interview/state.md` to `audit_needs_more_interview`, set `.interview/confirmation.md` to `audit_confirmed: no`, and ask only the first unanswered follow-up question on the current or next invocation.
   - If all three auditors return `CONFIRM`, set `.interview/state.md` to `awaiting_user_final_confirm`, set `.interview/confirmation.md` to `audit_confirmed: yes` and `awaiting_user_final_confirm: yes`, then ask the user for final confirmation before writing `.agent_goal` files.
   - Use [audit-agent-prompts.md](references/audit-agent-prompts.md).
   - If ID context exists, run `$manage-task-state-index` `audit` after draft audit. If the workflow authorizes agents, use one additional read-only ID consistency agent for `.interview` and `.agent_goal` links only. This agent is not one of the three draft auditors.

8. If final confirmation is present, run critical pre-write review and agent write-confirmation before writing.
   - Treat final confirmation as present only when `.interview/confirmation.md` records `final_confirmed: yes` or the newest user message explicitly confirms finalization after audit confirmation.
   - Before spawning final reviewers, verify `.interview/evidence_review.md` records the latest evidence-consistency cycle with all three agents confirmed. If not, return to the evidence-consistency loop and do not write final files.
   - Spawn at least three independent final critical review agents; use 3-6 reviewers by default.
   - These reviewers are mandatory even if the three audit agents already confirmed.
   - Reviewers must inspect `.interview` contents, evidence-consistency review status, drafts, audit status, final confirmation, and the proposed final `.agent_goal` write content.
   - Store final review results in `.interview/final_review.md`.
   - Before calling `$manage-goal-architecture` or `$manage-goal-theory`, the main agent must make and record an explicit `agent_write_confirmed: yes | no` decision in `.interview/confirmation.md`.
   - Set `agent_write_confirmed: yes` only when every final reviewer returns `verdict: CONFIRM`, every reviewer returns `safe_to_write: yes`, no blocking issue remains, and the proposed final write content is supported by goal files, answers, audit, or repository evidence.
   - If any final reviewer rejects, any reviewer is not safe to write, or the main agent cannot independently confirm support for the final write content, set `agent_write_confirmed: no`, set `write_completed: no`, store the hold reason and follow-up questions, and do not write final files.
   - If `agent_write_confirmed: no`, set `.interview/state.md` to `audit_needs_more_interview` when more interview is required, or keep it at `awaiting_user_final_confirm` when the only blocker is missing/ambiguous user confirmation.
   - If `agent_write_confirmed: yes`, write the final files exactly to `.agent_goal/goal_architecture.md`, `.agent_goal/goal_theory.md`, `.agent_goal/goal_schema_contract.md`, and `.agent_goal/agent_authority.md`. Use the corresponding goal-management skills for architecture/theory, write `goal_schema_contract.md` as the schema-governance goal artifact consumed by `$manage-schema-contracts`, and use `$manage-agent-authority` in `finalize_from_interview` mode to write `agent_authority.md` as the authority-governance goal artifact consumed by `$orchestrate-task-cycle`, `$derive-improvement-task`, and `$task-md-agent-governance`.
   - After writing, verify all four final paths exist under `.agent_goal/`. Do not create alternate final files in `.interview/`, `.task/`, `.schema/`, `.contract/`, the repository root, or any other directory.
   - After final writes, use `$manage-agent-authority` in `validate` or `summarize` mode so downstream cycle skills can consume the final authority policy.
   - After final writes, use `$manage-schema-contracts` when available so `.schema/` and `.contract/` contract management can be aligned to `.agent_goal/goal_schema_contract.md`.
   - Use [final-review-agent-prompts.md](references/final-review-agent-prompts.md).
   - After final writes, run `$manage-task-state-index` `scan`, link final `goal-*` artifacts to the relevant `int-*` interview artifacts with `interview_for`, and run global ID audit.

9. Report outcome.
   - List files created or updated.
   - Summarize the interview state, pending questions, evidence-consistency status, audit confirmations, final review status, schema-contract goal status, agent-authority goal status, ID traceability status, and any intentionally omitted unsupported content.

## ID Traceability Add-on

- Use `$manage-task-state-index` only for stable IDs and links among `.agent_goal/`, `.interview/`, audits, and final writes.
- Do not let an ID consistency agent generate interview questions, audit content, final review content, or goal text.
- If no ID context exists or no durable artifact has been written yet, skip ID linkage and continue the stateful interview.

## Single-Question Continuation

Use this rule whenever `.interview/confirmation.md` is not `final_confirmed: yes` or `write_completed: yes`, `.interview/questions.md` contains at least one unanswered question, and the user invokes `$deep-interview-goal-context` without additional substantive text.

1. Do not generate new questions, draft, audit, summarize all pending questions, or ask a batch.
2. Find the active batch from `.interview/state.md`; if absent, use the first batch containing a `pending` question.
3. Ask exactly one pending question from that batch.
4. Record `active_batch`, `current_question_id`, and `last_asked_question_id` in `.interview/state.md`.
5. End the turn after asking that single question.

When the next invocation contains an answer:

1. Map the answer to `last_asked_question_id` unless the user explicitly names another question id.
2. Append the answer to `.interview/answers.md` and mark that question `answered` in `.interview/questions.md`.
3. If the same batch still has pending questions, ask exactly one next pending question and stop.
4. If the batch has no pending questions, run the normal draft, evidence-consistency, and three-agent audit loops.
5. If evidence-consistency or audit needs more interview, write a new follow-up batch and return to single-question continuation.
6. If evidence-consistency and audit both confirm, set `awaiting_user_final_confirm` and ask for final confirmation instead of generating another batch.

## Evidence-Consistency Feedback Loop

Run this loop after every completed question batch has been incorporated into `.interview/drafts/goal_architecture.md`, `.interview/drafts/goal_theory.md`, `.interview/drafts/goal_schema_contract.md`, and `.interview/drafts/agent_authority.md`, and before requesting final confirmation or writing `.agent_goal` files.

1. Spawn exactly three independent agents using [evidence-consistency-agent-prompts.md](references/evidence-consistency-agent-prompts.md).
2. Require each agent to inspect the full existing interview record: `.interview/state.md`, `.interview/questions.md`, `.interview/answers.md`, `.interview/audit.md`, `.interview/confirmation.md`, drafts, base goal files, and repository evidence when available.
3. Store every cycle in `.interview/evidence_review.md`.
4. Treat the cycle as confirmed only when all three agents return `verdict: CONFIRM` and `safe_to_write: yes`.
5. If any agent flags hallucination, unsupported inference, contradiction with interview answers, missing answer coverage, convention violation, template misuse, sensitive content, or alternate output path, revise drafts and rerun the loop, or create follow-up questions and return to single-question continuation.
6. Record `evidence_review_confirmed: yes` only after all three agents confirm in the latest cycle; otherwise record `evidence_review_confirmed: no`.
7. Do not advance to user final confirmation, final review, agent write-confirmation, or `.agent_goal` writes until the latest evidence-consistency cycle is confirmed.

## Agent Write Confirmation Gate

Run this gate after user final confirmation and final critical review, but before writing `.agent_goal/goal_architecture.md`, `.agent_goal/goal_theory.md`, `.agent_goal/goal_schema_contract.md`, or `.agent_goal/agent_authority.md`.

1. Read `.interview/final_review.md`, `.interview/confirmation.md`, `.interview/drafts/goal_architecture.md`, `.interview/drafts/goal_theory.md`, `.interview/drafts/goal_schema_contract.md`, and `.interview/drafts/agent_authority.md`.
2. Decide `agent_write_confirmed: yes` only when all final reviewers explicitly confirm and the main agent can verify that the final write content is supported, non-sensitive, correctly placed, and not hallucinated.
3. Decide `agent_write_confirmed: no` for any ambiguity, missing final confirmation, reviewer disagreement, unsupported claim, unresolved blocker, template mismatch, or unsafe stored content.
4. Record the decision in `.interview/confirmation.md` with `agent_write_confirmed`, `agent_write_confirmed_by`, `agent_write_decision_at`, and `write_hold_reason`.
5. If the decision is `no`, hold all four goal files. Do not partially write architecture, theory, schema-contract, or agent-authority goal files.
6. If the decision is `yes`, write final files exactly as `.agent_goal/goal_architecture.md`, `.agent_goal/goal_theory.md`, `.agent_goal/goal_schema_contract.md`, and `.agent_goal/agent_authority.md`; use `$manage-agent-authority finalize_from_interview` for the authority file, then set `write_completed: yes`.
7. Verify all four `.agent_goal` files exist after the write. If any file is missing, treat the write as incomplete and report the missing target.

## Interview Discipline

- Do not ask all generated questions blindly. The summary agent must reduce them.
- Do not rerun the full question-generation pipeline when `.interview/questions.md` already contains unanswered questions.
- Do not ask more than one pending question per invocation during continuation mode, even if the stored batch contains several questions.
- Do not start the draft/audit loop until the active batch has no pending questions, unless the user explicitly cancels or skips the remaining questions.
- Do not ask for final confirmation while the latest evidence-consistency cycle has any non-confirming agent.
- Do not return "no raw prompt provided" as the only result after the hard gate passes; ask bootstrap questions instead.
- Do not bury critical constraints in theory or architecture prose; put them in the right sections.
- Do not treat repo inspection as a substitute for user answers when the information concerns intent, theory preference, or design constraints.
- Do not invent architecture relationships, algorithms, or technical rationale.
- If the user gives partial answers, record the supported parts, mark the rest unanswered, and keep the next questions in `.interview/questions.md`.

## Guardrails

- Do not create or update `goal_architecture.md`, `goal_theory.md`, `goal_schema_contract.md`, or `agent_authority.md` before `.agent_goal/final_goal.md` and `.agent_goal/conventions.md` are filled.
- Do not write final `.agent_goal/goal_architecture.md`, `.agent_goal/goal_theory.md`, `.agent_goal/goal_schema_contract.md`, or `.agent_goal/agent_authority.md` until `.interview/confirmation.md` has final confirmation and at least three final critical review agents confirm.
- Do not write final architecture/theory/schema-contract/agent-authority goal content to alternate paths such as `.interview/drafts/`, `.task/`, `.schema/`, `.contract/`, repository root files, `goal.md`, `theory.md`, `schema.md`, `authority.md`, or similarly named substitutes.
- Do not let question-generator, summary, or audit agents write files.
- Do not claim audit confirmation unless all three audit agents explicitly confirm.
- Do not claim final review confirmation unless every final reviewer explicitly confirms.
- Do not claim interview evidence consistency unless all three evidence-consistency agents confirm in the latest cycle.
- Do not write final `.agent_goal` architecture/theory/schema-contract/agent-authority files unless the latest evidence-consistency cycle is confirmed.
- Do not write final `.agent_goal` architecture/theory/schema-contract/agent-authority files unless `agent_write_confirmed: yes` is recorded immediately before the write.
- Do not treat an implementation default, legacy prose omission, or later approval as retroactive evidence that a concept, relation, delegation, or authority lease was previously user-approved.
- Do not bypass `$manage-agent-authority` when drafting, validating, or final-writing `.interview/drafts/agent_authority.md` or `.agent_goal/agent_authority.md`.
- Do not partially write only one, two, or three final goal artifacts after a failed agent write-confirmation. Hold all four files and ask or record the needed follow-up.
- Do not claim completion if final content exists only in `.interview/drafts/`; successful completion requires all four final files under `.agent_goal/`.
- Do not store secrets, credentials, private keys, tokens, sensitive raw transcripts, or large copyrighted excerpts in `.agent_goal`.
- Do not store sensitive raw transcripts or large copyrighted excerpts in `.interview`; summarize or redact them.
- The newest explicit user message still overrides `.agent_goal` content for the current turn.
- Do not treat ID audit success as a substitute for user final confirmation or critical pre-write review.
