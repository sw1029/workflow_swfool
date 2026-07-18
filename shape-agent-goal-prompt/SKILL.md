---
name: shape-agent-goal-prompt
description: Transform a user's raw prompt into draft or persisted `.agent_goal/final_goal.md` and `.agent_goal/conventions.md` content compatible with `$manage-agent-goal`, while preserving the user's intent through mandatory critical review by at least three independent subagents. Use when the user explicitly asks to draft, create, update, refine, formalize, normalize, or enter a raw prompt into agent goal files; when Codex needs to separate final objective from constraints/conventions; or when preventing misinterpretation, overreach, omission, or distortion of a prompt is important before updating `.agent_goal`. Write files only when the user requested persistence or approves the reconciled draft.
---

# Shape Agent Goal Prompt

## Overview

Use this skill before `$manage-agent-goal` when a raw user prompt must be converted into the two `.agent_goal` files or drafted for review. The conversion must preserve the user's meaning, avoid adding invented requirements, and distinguish objective, success criteria, current status, open questions, constraints, required practices, forbidden actions, and validation.

This skill requires at least three independent critical-review subagents for every raw prompt conversion. If three independent reviews cannot be completed, do not write `.agent_goal` files; produce only a local draft and state that independent review could not be performed.

`authority.operations.json` declares prompt shaping as a read-only draft operation under the shared [authority v2 contract](../manage-agent-authority/references/authority-v2-contract.md). It never authorizes persistence. When publication is requested, `$manage-agent-goal` owns the exact `update_final_goal` or `update_goal_conventions` operation and independently requires the applicable goal-owner decision.

When task-state indexing is available, use `$manage-task-state-index` to track prompt-shaping and goal artifacts. If no ID context exists, keep the original prompt-shaping behavior.

## Workflow

1. Preserve the raw prompt.
   - Keep the user's wording available during the whole conversion.
   - Do not paraphrase first and then reason only from the paraphrase.
   - Preserve multiple explicit compatible goals. Move only unclear priority, conflicts, dependencies, missing decisions, or ambiguous scope into open questions.
   - Before reviewer handoff, redact secrets, credentials, private keys, tokens, and sensitive personal content while preserving intent. If redaction would change the meaning, ask the user before continuing.

2. Draft the goal files.
   - Produce draft content for `.agent_goal/final_goal.md` and `.agent_goal/conventions.md` using the `$manage-agent-goal` templates.
   - Put desired end state and success conditions in `final_goal.md`.
   - Put operating constraints, conventions, forbidden actions, and validation expectations in `conventions.md`.
   - Label inferred content as inferred or put it under open questions. Do not silently upgrade preferences into hard constraints.
   - If preserving existing `.agent_goal` content, keep it clearly labeled as existing content in the draft and reviewer handoff.

3. Launch at least three critical-review subagents.
   - Use independent `explorer` agents unless implementation is also requested.
   - Give each agent the raw prompt and the draft, not your private reasoning.
   - Assign distinct review lenses:
     - Intent preservation and omission check.
     - Overreach and invented requirement check.
     - Ambiguity, conflict, and risk check.
     - `$manage-agent-goal` file and template compatibility check.
   - Use at least four reviewers when separate compatibility review is practical; if using exactly three reviewers, assign compatibility to one reviewer explicitly and report that combined lens.
   - For complex prompts, add a fifth or sixth reviewer for domain terminology or validation criteria.
   - Use [critic-prompts.md](references/critic-prompts.md) for exact prompts.
   - If ID context exists and the workflow authorizes agents, optionally launch one additional read-only ID consistency agent. This agent is not a critical reviewer and must not review prompt semantics; it only checks whether raw prompt evidence, draft artifacts, final goal files, and logs can be linked.

4. Reconcile critique.
   - Accept critiques that cite a concrete mismatch between raw prompt and draft.
   - Reject critiques that add requirements not grounded in the raw prompt.
   - Preserve disagreement as an open question when it cannot be resolved from the raw prompt.
   - Update the draft only after considering all reviewers.

5. Apply through `$manage-agent-goal`.
   - Proceed only after at least three independent reviewer reports have been received and reconciled.
   - Write files only if the user explicitly asked to persist `.agent_goal` files or approves the reconciled draft; otherwise return the draft only.
   - Use the final reconciled draft as input to `$manage-agent-goal`.
   - Write only `.agent_goal/final_goal.md` and `.agent_goal/conventions.md` in the workspace root.
   - Preserve existing useful content unless the user asked for replacement.
   - After writing or updating `.agent_goal`, run `$manage-task-state-index` `scan`, add `goal_prompt` evidence if there is a durable prompt-shaping artifact, link generated `goal-*` files with `prompt_for`, and run deterministic ID audit when an index exists.

6. Report the outcome.
   - List files created or changed.
   - Summarize the final objective and the most important conventions.
   - Include a short review summary: reviewers used, material critiques accepted, unresolved questions, and ID traceability status when available.

## ID Traceability Add-on

- Use `$manage-task-state-index` only after there is a durable `.agent_goal` file, prompt-shaping artifact, or related log.
- Do not block draft-only output when no ID can be assigned.
- Do not count an ID consistency agent toward the required three prompt critics.
- Do not let the ID agent decide whether the prompt was preserved correctly; that remains the responsibility of the critical reviewers and main agent.

## Conversion Rules

- Keep the user's priority order when the raw prompt implies one.
- Convert "must", "never", and "only" into constraints or forbidden actions only when they are the user's direct durable instruction to future agents; preserve quoted, hypothetical, optional, or example text as such.
- Convert "should", "prefer", and "try to" into required practices only when the prompt clearly treats them as operating rules; otherwise omit them from goal files or include them as clearly labeled preferences under `Required Practices`.
- Convert tests, checks, proof, acceptance, and completion language into validation or success criteria.
- Convert uncertainty, missing inputs, and decision points into open questions.
- Do not record secrets, credentials, private keys, tokens, or sensitive raw transcripts in `.agent_goal`.

## Output Shape Before Writing

Use this pre-write shape so reviewers and the user can inspect the conversion:

```text
Raw Prompt Summary
- ...

Draft final_goal.md
- # Final Goal
- ## Objective
- ...
- ## Success Criteria
- ...
- ## Current Status
- ...
- ## Open Questions
- ...

Draft conventions.md
- # Conventions
- ## Constraints
- ...
- ## Required Practices
- ...
- ## Forbidden Actions
- ...
- ## Validation
- ...

Critical Review Summary
- Reviewer 1: ...
- Reviewer 2: ...
- Reviewer 3: ...

Reconciliation
- Accepted changes: ...
- Rejected changes: ...
- Open questions: ...
```

## Guardrails

- Do not skip the three-reviewer step for any raw prompt conversion.
- Do not write `.agent_goal` files when fewer than three independent critical-review agents completed review.
- Do not let reviewers edit files.
- Do not treat the converted files as superior to a newer explicit user message.
- Do not hide ambiguity by making a confident final goal from an unclear raw prompt.
- If existing `.agent_goal` files conflict with the raw prompt, report the conflict before overwriting.
- If retained existing content is included, reviewers must receive it clearly labeled so they can distinguish it from new raw-prompt-derived content.
- Do not treat ID audit success as prompt correctness.
