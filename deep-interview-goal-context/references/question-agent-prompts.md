# Question Generator Agent Prompts

Run six stages in order when `.interview/questions.md` has no pending questions. If the raw prompt is absent or weak, first seed `.interview/questions.md` from `bootstrap-questions.md` and ask those questions before running the full staged generation. In each stage, spawn exactly three independent agents unless the user explicitly changes the count. Pass only the base goal files, existing architecture/theory/schema-contract/agent-authority content if any, and relevant `.interview` history.

All question-generator agents must output questions only. They must not answer, infer, or draft `.agent_goal` content.

Each question should include:

- `question`: the exact user-facing question.
- `why_needed`: the gap or risk it closes.
- `goal_anchor`: the relevant point from `final_goal.md` or `conventions.md`.
- `target_file`: `goal_architecture.md`, `goal_theory.md`, `goal_schema_contract.md`, `agent_authority.md`, `both`, or `all`.
- `target_section`: the likely section that cannot be filled safely without the answer.
- `priority`: `blocker`, `important`, or `optional`.
- `state_action`: usually `add_to_interview_questions`; use `skip_duplicate` only if the question is already answered in `.interview/answers.md`.

## Stage 1: Perspective Questions

Prompt each of three independent agents. Assign different lenses such as user/stakeholder view, future-agent maintenance view, and system boundary view:

```text
You are generating perspective-oriented interview questions for `.agent_goal/goal_architecture.md`, `.agent_goal/goal_theory.md`, `.agent_goal/goal_schema_contract.md`, and `.agent_goal/agent_authority.md`.

Context:
[final_goal.md]
[conventions.md]
[existing goal_architecture.md if any]
[existing goal_theory.md if any]
[existing goal_schema_contract.md if any]
[existing agent_authority.md if any]
[raw prompt if present; otherwise state "raw prompt absent or weak"]
[prior .interview questions and answers if any]

Generate questions that reveal stakeholder viewpoint, operating perspective, intended scope, excluded scope, success viewpoint, and how future agents should interpret the goal. If the raw prompt is absent or weak, generate questions from the base goal and conventions instead of refusing. Do not answer the questions. Tie each question to a specific gap in the context.

Output 5-10 questions using this schema:
- question:
- why_needed:
- goal_anchor:
- target_file:
- target_section:
- priority:
```

## Stage 2: Process Questions

Prompt each of three independent agents. Assign different lenses such as workflow lifecycle, data/control flow, and review/rollback operations:

```text
Generate process-oriented interview questions for the same context. Focus on workflow, stages, data/control flow, expected commands, handoff points, review gates, dependencies, schema/contract management, authority-policy propagation, and failure handling needed to document architecture, theory, schema-contract governance, and agent-authority governance. Do not answer the questions. Tie each question to a specific gap.

Output 5-10 questions using this schema:
- question:
- why_needed:
- goal_anchor:
- target_file:
- target_section:
- priority:
```

## Stage 3: Theory Questions

Prompt each of three independent agents. Assign different lenses such as algorithmic logic, domain assumptions, and validation/proof criteria:

```text
Generate theory-oriented interview questions for the same context. Focus on technical logic, algorithms, models, assumptions, tradeoffs, validation theory, schema/contract reasoning, and domain concepts needed for `goal_theory.md` and related `goal_schema_contract.md` rules. Do not answer the questions. Tie each question to a specific gap.

Output 5-10 questions using this schema:
- question:
- why_needed:
- goal_anchor:
- target_file:
- target_section:
- priority:
```

## Stage 4: Detailed Element Questions

Prompt each of three independent agents. Assign different lenses such as module/script inventory, data/artifact inventory, and interfaces/configuration:

```text
Generate detailed-element interview questions for the same context. Focus on modules, scripts, interfaces, data artifacts, config files, source anchors, expected inputs/outputs, target modules/scripts, producers, consumers, schema fields, authority propagation points, and important implementation details needed for `goal_architecture.md`, `goal_theory.md`, `goal_schema_contract.md`, and `agent_authority.md`. Do not answer the questions. Tie each question to a specific gap.

Output 5-10 questions using this schema:
- question:
- why_needed:
- goal_anchor:
- target_file:
- target_section:
- priority:
```

## Stage 5: Constraint Questions

Prompt each of three independent agents. Assign different lenses such as safety/privacy constraints, implementation/tooling constraints, and validation/compliance constraints:

```text
Generate constraint-oriented interview questions for the same context. Focus on hard limits, forbidden actions, validation requirements, data safety, performance constraints, compatibility constraints, versioning rules, mandatory schema/contract fields, causal-map requirements, API/external-call restrictions, escalation requirements, and conventions that should affect architecture/theory/schema-contract/agent-authority documentation. Do not answer the questions. Tie each question to a specific gap.

Output 5-10 questions using this schema:
- question:
- why_needed:
- goal_anchor:
- target_file:
- target_section:
- priority:
```

## Stage 6: Authority Questions

Prompt each of three independent agents. Assign different lenses such as API/external-service permissions, direction freedom and autonomy, and implementation/validation priority:

```text
Generate agent-authority interview questions for the same context. Focus on the `$manage-agent-authority` template fields: default-current-agent permission baseline, API/network/external service policy, direction freedom profiles, strict versus bounded variation, implementation-first versus artifact/output-confirmation-first versus quality-first behavior, conservative implementation, destructive/long-running/costly action approvals, escalation, and precedence rules needed for `.agent_goal/agent_authority.md`. Do not answer the questions. Tie each question to a specific gap and do not imply that the authority file can grant permissions unavailable to the active session.

Output 5-10 questions using this schema:
- question:
- why_needed:
- goal_anchor:
- target_file:
- target_section:
- priority:
```
