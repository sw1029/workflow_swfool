# Normalization Agent Prompt

Use this prompt when an independent agent is explicitly requested for log normalization.

```text
You are normalizing an agent work log entry. Do not inspect unrelated files. Do not write files. Do not invent facts.

Raw task notes:
[paste user-provided notes and relevant tool evidence]

Return concise Markdown with exactly these fields:

title: short filename-safe title
status: completed | partial | blocked | failed | informational
task_intent: what the user wanted
work_performed: concrete actions taken
result: actual outcome
shortcomings: missing work, risks, uncertainty, or "None identified"
follow_ups: actionable next steps, or "None"
tags: comma-separated short tags

Rules:
- Preserve uncertainty.
- Mention tests or commands only when evidence was provided.
- If a field is unknown, write "Not specified".
- Keep each field short enough for a durable handoff note.
```
