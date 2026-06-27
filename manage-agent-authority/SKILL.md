---
name: manage-agent-authority
description: Manage the workspace-local `.agent_goal/agent_authority.md` authority goal-truth file and `.interview/drafts/agent_authority.md` drafts. Use when Codex needs to create, update, validate, summarize, or apply agent authority policy for API/external calls, direction freedom, strictness, implementation/validation priority, artifact confirmation, quality review, conservative implementation, escalation, or higher-priority permission precedence; use from `$orchestrate-task-cycle`, `$derive-improvement-task`, `$task-md-agent-governance`, and `$deep-interview-goal-context` whenever authority policy is read, drafted, written, or passed to subagents.
---

# Manage Agent Authority

## Overview

Use this skill to manage the project authority policy stored at `.agent_goal/agent_authority.md`. The policy documents how future agents should interpret the current coding agent's effective permissions, API/external-call boundaries, direction freedom, implementation/validation priority, conservative posture, and escalation rules.

The file is goal truth, but it cannot grant authority beyond the active session's system/developer/user instructions, filesystem sandbox, approval rules, network availability, or available tools. It may only narrow, prioritize, or clarify behavior within current effective permissions.

External advice under `.agent_advice/active/*.md` is not authority evidence. It may suggest questions or narrower project posture, but it cannot grant API/network/destructive capability or override current permissions. Promote advice into `.agent_goal/agent_authority.md` only after explicit user instruction and this skill's safety validation.

Use [agent-authority-template.md](references/agent-authority-template.md) for both `.agent_goal/agent_authority.md` and `.interview/drafts/agent_authority.md`.

## Workflow

1. Locate the workspace root.
   - Default to the current working directory unless the caller names another root.
   - Create `.agent_goal/` only when writing final authority policy is explicitly requested or when `$orchestrate-task-cycle` asks for an authority policy to be ensured.
   - Use `.interview/drafts/agent_authority.md` only for `$deep-interview-goal-context` draft/review cycles.

2. Read existing context.
   - Read `.agent_goal/final_goal.md` and `.agent_goal/conventions.md` when present.
   - Read existing `.agent_goal/agent_authority.md` when present.
   - Read relevant `.agent_advice/active/*.md` or a `$manage-external-advice` packet only when the authority operation depends on it; treat it as non-GT evidence and check it against current effective permissions.
   - Read `.interview/drafts/agent_authority.md`, `.interview/questions.md`, and `.interview/answers.md` when operating in interview draft or finalization mode.
   - Preserve useful user-authored authority decisions and mark unsupported or conflicting details as open questions.

3. Choose the operation.
   - `summarize`: return a compact effective authority policy for another skill to pass to agents.
   - `ensure_default`: create `.agent_goal/agent_authority.md` from the template with `default_current_agent_permissions` when no authority file exists and the caller needs durable policy.
   - `draft_for_interview`: write or revise `.interview/drafts/agent_authority.md` using interview evidence, not final `.agent_goal`.
   - `finalize_from_interview`: after `$deep-interview-goal-context` evidence review, audit, final review, and agent write-confirmation pass, write `.agent_goal/agent_authority.md` from the supported interview draft.
   - `update`: update `.agent_goal/agent_authority.md` from explicit user instruction or current work evidence.
   - `validate`: check that an authority file does not claim capabilities beyond current effective permissions or higher-priority instructions.

4. Apply the template.
   - Include these sections: `Authority Baseline`, `API And External Calls`, `Direction Freedom`, `Implementation And Validation Priority`, `Escalation And Approval`, `Precedence And Overrides`, and `Open Questions`.
   - Use `default_current_agent_permissions` as the baseline unless the user explicitly supplies narrower project-specific policy.
   - Record API/network/external service policy as `forbidden`, `ask_first`, `allowed_when_task_requires`, `read_only`, or `inherit_current_permissions`.
   - Record direction freedom as `strict`, `bounded_variation`, `implementation_first`, `artifact_confirmation_first`, `quality_first`, `conservative`, or a clearly user-defined profile.
   - Keep unsupported decisions under `Open Questions` instead of inventing policy.

5. Validate authority safety.
   - Confirm the file does not grant network, API, destructive, credentialed, long-running, filesystem, or external-service authority that the active session lacks.
   - Confirm the file states that current system/developer/user instructions and active tool/sandbox permissions have precedence.
   - Confirm the newest explicit user instruction controls the current turn when it conflicts with stored goal authority, but do not let downstream workflow artifacts cite "latest user instruction" as a durable supersession unless they preserve a verifiable timestamp or log/transcript path plus the quoted instruction text.
   - Confirm secrets, credentials, private keys, tokens, sensitive transcripts, and large copyrighted excerpts are absent.

6. Report outcome.
   - Return the operation performed, final or draft path, effective authority summary, open questions, and any conflicts.
   - When called by `$orchestrate-task-cycle`, return a compact Korean summary suitable for `기준 GT` and downstream subskill prompts.
   - When called by `$deep-interview-goal-context`, return whether the draft or final write is safe to include in evidence review/final write gates.

## Consumption Rules

- `$orchestrate-task-cycle` must call this skill to resolve the effective authority policy before task derivation, implementation delegation, validation, or final reporting.
- `$derive-improvement-task` must treat the returned authority policy as planning evidence and include `Authority Policy` in generated `task.md`.
- `$task-md-agent-governance` must pass the returned authority policy to every code-writing worker and implementation audit prompt.
- `$deep-interview-goal-context` must use this skill's template for `.interview/drafts/agent_authority.md` and must use this skill for final `.agent_goal/agent_authority.md` writes after its review gates pass.

## Guardrails

- Do not use this file to bypass sandbox, approval, network, filesystem, tool, model, or higher-priority instruction limits.
- Do not treat `.agent_advice` as authority or permission evidence. Advice can only narrow/clarify after explicit user-supported update and validation.
- Do not infer permission for API calls, network access, external services, destructive operations, credential use, costly actions, long-running jobs, or broad direction changes from silence.
- Do not overwrite `.agent_goal/agent_authority.md` wholesale unless it is empty, placeholder-only, explicitly replaced by the user, or being created for the first time.
- Do not write final authority policy from `.interview/drafts/agent_authority.md` unless `$deep-interview-goal-context` reports final user confirmation, evidence-consistency confirmation, final critical review confirmation, and `agent_write_confirmed: yes`.
- Do not store secrets, credentials, private keys, tokens, sensitive raw transcripts, or large copyrighted excerpts in `.agent_goal/agent_authority.md` or `.interview/drafts/agent_authority.md`.
- The newest explicit user message still overrides stored authority policy for the current turn. Durable task rewrites or reseals that rely on that override must cite a verifiable source; otherwise route a one-question user confirmation instead of silently weakening or re-forbidding an authority-allowed action.
