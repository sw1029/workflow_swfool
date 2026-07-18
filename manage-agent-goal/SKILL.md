---
name: manage-agent-goal
description: Manage a workspace-local `.agent_goal` directory containing `final_goal.md` for the final objective and `conventions.md` for constraints, rules, and operating conventions. Use when the user asks to create, read, update, summarize, or align an agent goal, final goal, project objective, constraints, conventions, working agreements, persistent instructions, or task guardrails stored in `.agent_goal/final_goal.md` and `.agent_goal/conventions.md`.
---

# Manage Agent Goal

## Overview

Use this skill to keep the workspace's long-running goal and constraints in two small Markdown files:

- `.agent_goal/final_goal.md`: the final objective, success criteria, current status, and open questions.
- `.agent_goal/conventions.md`: constraints and practices that must be followed while pursuing the goal.

The files are workspace artifacts. Read them before planning or editing when they exist, and update them only with information supported by the user request or current work evidence.

Use `authority.operations.json` with the shared [authority v2 contract](../manage-agent-authority/references/authority-v2-contract.md). Reading is authority-free. Updating `final_goal.md` and updating `conventions.md` are separate D0 grant-controlled operations bound to the exact prospective subject digest and revision. A write grant controls the effect but does not itself ratify goal truth: require the applicable explicit goal-owner decision and concept-graph/revision evidence independently, then reserve and reverify the exact write before publication.

When `.agent_advice/active/*.md` exists or the user provides external advice, treat it as non-GT evidence only. It may help explain a proposed goal or convention change, but it must not be copied into `.agent_goal` unless the user explicitly asks to promote that specific content and this skill applies the normal goal-edit guardrails.

If advice proposes durable workflow conventions such as "measurement/oracle cycles can be goal-productive despite zero primary-output delta" or "forward blocker mutations count as progress," add those lines to `.agent_goal/conventions.md` only when the user explicitly approves promoting that specific policy into goal truth.

## Workflow

1. Locate the workspace root.
   - Default to the current working directory unless the user names another root.
   - Create `.agent_goal/` if it does not exist.
   - Manage only `.agent_goal/final_goal.md` and `.agent_goal/conventions.md`.

2. Read existing goal files.
   - If a file exists, preserve useful user-authored content.
   - If content conflicts with the new request, state the conflict and update only when the user's intent is clear.
   - Read relevant `.agent_advice/active/*.md` or a `$manage-external-advice` packet only when the user names it or the goal update depends on that advice; record it as source evidence, not goal truth.
   - If a file is absent, create it from the template below.

3. Update `final_goal.md`.
   - Record the final goal as a concrete outcome, not a vague activity.
   - Include measurable success criteria when possible.
   - Track current status separately from the final goal.
   - Keep open questions explicit instead of hiding uncertainty.

4. Update `conventions.md`.
   - Record constraints, forbidden actions, required checks, coding/style rules, communication preferences, data safety rules, and validation expectations.
   - Do not duplicate generic system instructions unless the user made them project-specific.
   - Prefer short, durable rules over session-specific commentary.

5. Report changes.
   - Tell the user which files were created or changed.
   - Summarize the final goal and the most important conventions in a few lines.
   - Mention unresolved questions or conflicts.

## Templates

Use this structure for `.agent_goal/final_goal.md`:

```markdown
# Final Goal

## Objective

<Concrete final outcome.>

## Success Criteria

- <Observable completion condition.>

## Current Status

- <Known current state.>

## Open Questions

- <Unknown, blocker, or decision needed.>
```

Use this structure for `.agent_goal/conventions.md`:

```markdown
# Conventions

## Constraints

- <Hard requirement or limitation.>

## Required Practices

- <Practice to follow while working.>

## Forbidden Actions

- <Action not allowed without explicit user approval.>

## Validation

- <Required check, test, review, or evidence.>
```

## Guardrails

- Do not treat `.agent_goal` as a replacement for the user's latest instruction. The newest explicit user message still controls the current turn.
- Do not treat `.agent_advice` as `.agent_goal` GT or authority. Promotion into `.agent_goal/final_goal.md` or `.agent_goal/conventions.md` requires explicit user intent and a normal supported edit.
- Do not promote anti-loop, measurement-progress, blocker-mutation, or terminal-exit advice into `.agent_goal/conventions.md` merely because an advice file recommends it; require explicit user approval for the exact durable convention.
- Do not invent goals or constraints. If something is inferred, label it as inferred or put it under open questions.
- Do not overwrite existing files wholesale unless they are empty, placeholder-only, or the user explicitly requests replacement.
- Do not store secrets, credentials, private keys, tokens, or sensitive raw transcripts in `.agent_goal`.
- Keep both files concise enough to read at the start of future work.
