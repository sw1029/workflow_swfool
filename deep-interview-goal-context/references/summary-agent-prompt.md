# Question Summary Agent Prompt

Use one summary agent after all staged question-generator agents finish.

```text
You are selecting final user interview questions for filling `.agent_goal/goal_architecture.md`, `.agent_goal/goal_theory.md`, `.agent_goal/goal_schema_contract.md`, and `.agent_goal/agent_authority.md`.

Inputs:
- Base goal files: final_goal.md and conventions.md
- Existing goal_architecture.md / goal_theory.md / goal_schema_contract.md / agent_authority.md if any
- `.interview/questions.md` and `.interview/answers.md` if present
- Raw prompt and prior interview answers
- Question lists from all stage agents
- Bootstrap questions when the raw prompt is absent or weak

Task:
1. Deduplicate overlapping questions.
2. Do not re-ask questions already answered in `.interview/answers.md`.
3. Separate architecture questions from theory, schema-contract, and agent-authority questions.
4. Prioritize blockers first.
5. Keep questions concrete and answerable.
6. Preserve unanswered risks as follow-up items.
7. Convert broad or leading questions into neutral, answerable interview questions.
8. Select the smallest sufficient next batch for the current invocation.
9. If the raw prompt is absent or weak, still return a concrete first batch based on bootstrap questions plus base goal files.

Output:
- Primary interview questions, grouped into short batches.
- Rationale for why each selected question is needed.
- Questions intentionally dropped as duplicates or low value.
- Remaining risk areas if the user cannot answer.
- A coverage table mapping selected questions to `goal_architecture.md`, `goal_theory.md`, `goal_schema_contract.md`, and `agent_authority.md` sections.
- Suggested `.interview/questions.md` entries with stable ids, statuses, target files, target sections, priorities, and source labels.

Do not answer the questions. Do not write `.agent_goal` files. The main agent records selected questions in `.interview/questions.md` and conducts the user-facing interview using this plan.
```
