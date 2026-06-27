# Critical Reviewer Prompts

Use at least the first three reviewers for every raw prompt conversion. Run each of the first three reviewer prompts in its own separate independent subagent context. Also run Reviewer 4 whenever a separate compatibility pass is practical; if only three reviewers are used, explicitly add Reviewer 4's compatibility questions to one of the three reviewer prompts.

Pass only:
- the redacted raw prompt,
- the draft `.agent_goal` content,
- any retained existing `.agent_goal` content clearly labeled as existing content.

## Reviewer 1: Intent Preservation And Omission

```text
You are critically reviewing whether a draft `.agent_goal` conversion preserves the user's raw prompt.

Raw prompt:
[raw prompt]

Draft final_goal.md:
[draft]

Draft conventions.md:
[draft]

Do not rewrite the files. Do not add new requirements.
Report:
1. Any user intent missing from the draft.
2. Any priority or nuance that was weakened.
3. Any wording that could mislead future agents.
4. Concrete edits needed, each tied to the raw prompt.
If there is no issue, say so clearly.
```

## Reviewer 2: Overreach And Invention

```text
You are critically reviewing whether a draft `.agent_goal` conversion invents requirements not present in the user's raw prompt.

Raw prompt:
[raw prompt]

Draft final_goal.md:
[draft]

Draft conventions.md:
[draft]

Do not rewrite the files. Do not add new requirements.
Report:
1. Any objective, constraint, success criterion, forbidden action, or validation item not grounded in the raw prompt.
2. Any preference incorrectly elevated into a hard rule.
3. Any inferred content that should be labeled as inferred or moved to open questions.
4. Concrete deletions or softening edits needed.
If there is no issue, say so clearly.
```

## Reviewer 3: Ambiguity, Conflict, And Risk

```text
You are critically reviewing ambiguity and conflict in a draft `.agent_goal` conversion.

Raw prompt:
[raw prompt]

Draft final_goal.md:
[draft]

Draft conventions.md:
[draft]

Do not rewrite the files. Do not add new requirements.
Report:
1. Ambiguous phrases from the raw prompt that the draft resolved without evidence.
2. Conflicts inside the raw prompt or between the raw prompt and draft.
3. Risks future agents might misunderstand.
4. Items that should move to Open Questions.
If there is no issue, say so clearly.
```

## Reviewer 4: Manage-Agent-Goal Compatibility

```text
You are critically reviewing whether a draft `.agent_goal` conversion is compatible with the $manage-agent-goal file structure.

Raw prompt:
[raw prompt]

Draft final_goal.md:
[draft]

Draft conventions.md:
[draft]

Existing .agent_goal content being retained, if any:
[existing content or "None"]

Do not rewrite the files. Do not add new requirements.
Report:
1. Any file-name mismatch. Only `.agent_goal/final_goal.md` and `.agent_goal/conventions.md` are allowed.
2. Any missing required heading from the $manage-agent-goal templates.
3. Any content placed in the wrong file or section.
4. Any retained existing content that is not clearly labeled or grounded in raw prompt, existing files, workspace evidence, or open questions.
If there is no issue, say so clearly.
```

## Optional Reviewer 5: Validation Fit

Use when the prompt includes tests, acceptance criteria, benchmarks, audits, or completion gates.

```text
You are critically reviewing validation fit.

Raw prompt:
[raw prompt]

Draft final_goal.md:
[draft]

Draft conventions.md:
[draft]

Review only whether success criteria and validation items faithfully match the raw prompt. Flag missing, invented, or unverifiable checks. Tie every issue to source text. Do not rewrite the files.
```

## Optional Reviewer 6: Domain Terminology

Use when the prompt contains domain-specific terms, policy language, legal/medical/financial constraints, or project-local jargon.

```text
You are critically reviewing domain terminology.

Raw prompt:
[raw prompt]

Draft final_goal.md:
[draft]

Draft conventions.md:
[draft]

Review whether domain terms and constraints from the raw prompt were preserved without broadening or narrowing their meaning. Tie every issue to source text. Do not rewrite the files.
```
