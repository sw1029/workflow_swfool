---
name: manage-goal-theory
description: Manage a workspace-local `.agent_goal/goal_theory.md` file documenting the technical logic, theoretical background, models, algorithms, assumptions, tradeoffs, and reasoning principles relevant to the active goal. Use when the user asks to create, read, update, summarize, or align theory notes, technical rationale, algorithmic logic, domain model, conceptual overview, design theory, mathematical assumptions, or implementation reasoning in the same `.agent_goal` style as `$manage-agent-goal`.
---

# Manage Goal Theory

Use `authority.operations.json` and the shared [authority v2 contract](../manage-agent-authority/references/authority-v2-contract.md). Reading or summarizing is authority-free. Updating core theory is an exact D0 grant-controlled effect and does not by itself ratify changed goal truth.

## Overview

Use this skill to maintain `.agent_goal/goal_theory.md`: a concise theory and technical-logic note for future agents working toward the goal. It should explain why the chosen approach works, what concepts or algorithms matter, and what assumptions and tradeoffs must remain visible.

Keep this file complementary to `.agent_goal/final_goal.md`, `.agent_goal/conventions.md`, and architecture notes. It should explain reasoning and technical theory, not duplicate task status or repository maps.

When core-versus-variable ideas, bounded autonomy, or decision ownership matters, use the [goal concept graph contract](../deep-interview-goal-context/references/goal-concept-graph.md). Store its canonical concept/relation tables and graph digest in `goal_theory.md`; authority artifacts may reference exact concept IDs and digests but must not redefine them.

When `.agent_advice/active/*.md` exists or the user names external advice, use it only as non-GT technical evidence. Advice may raise hypotheses, tradeoffs, or validation questions, but it must not be presented as confirmed goal theory without repository/user support.

## Workflow

1. Locate the workspace root.
   - Default to the current working directory unless the user names another root.
   - Create `.agent_goal/` if it does not exist.
   - Manage only `.agent_goal/goal_theory.md`.

2. Gather theory and logic evidence.
   - Read existing `.agent_goal` files when present.
   - Inspect high-signal project docs, README, design notes, relevant source files, papers or references provided by the user, and comments explaining algorithms.
   - Read relevant `.agent_advice/active/*.md` or a `$manage-external-advice` packet only when the theory update depends on it; record the advice path as a source anchor or open question, not as GT.
   - Avoid broad source dumps. Read only enough to accurately summarize the technical logic.

3. Create or update `goal_theory.md`.
   - Preserve useful existing user-authored theory notes.
   - Separate confirmed project logic from inferred theory.
   - Preserve stable concept/relation IDs and classify missing legacy fields as `unclassified`; do not infer user ratification from existing code or silence.
   - Record assumptions and limits explicitly.
   - Keep explanations concise and useful for future implementation decisions.

4. Include required content.
   - Summarize the core technical idea behind the goal.
   - Describe key algorithms, models, data structures, protocols, formulas, or domain concepts.
   - Explain why these choices fit the goal and what tradeoffs they imply.
   - Record validation logic: what evidence would prove the theory is working.
   - Add open questions for uncertain or disputed theory.
   - When a concept graph is applicable, include exact classes, mutability, decision owners, allowed variation, deterministic rules, validation predicates, evidence IDs, revisions, and canonical digests.

5. Report changes.
   - Tell the user whether `.agent_goal/goal_theory.md` was created or updated.
   - Summarize the most important technical/theoretical points and any unresolved questions.

## Template

Use this structure for `.agent_goal/goal_theory.md`:

```markdown
# Goal Theory

## Scope

- Workspace: <path or repo name>
- Goal relevance: <what goal this theory supports>
- Last updated: <date/time or "Not recorded">

## Core Technical Idea

- <Main technical logic or theory in concise terms.>

## Key Concepts And Definitions

- `<term>`: <meaning in this project>

## Goal Concept Graph

- Graph revision: <opaque revision id>
- Graph SHA-256: <canonical digest>

### Concept Nodes

| concept_id | concept_class | mutability | decision_owner | D class | allowed_variation | deterministic_rule | revision_id | concept_digest |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `<opaque id>` | `<closed class>` | `<closed mutability>` | `<owner>` | `<D0-D3>` | `<closed range or none>` | `<rule or open-question id>` | `<revision>` | `<sha256>` |

### Concept Relations

| relation_id | relation_type | from | to | relation_mutability | decision_owner | revision_id | relation_digest |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `<opaque id>` | `<closed relation>` | `<concept id>` | `<concept id>` | `<mutability>` | `<owner>` | `<revision>` | `<sha256>` |

## Algorithms, Models, Or Mechanisms

- `<name>`: <how it works and where it appears>

## Assumptions

- <Assumption that must hold for the approach to work>

## Tradeoffs And Limits

- <Known limitation, cost, risk, or alternative>

## Validation Logic

- <Observation, test, metric, proof, or result that supports/refutes the theory>

## Source Anchors

- `<path or reference>`: <what evidence it provides>

## Open Questions

- <Unresolved theory, missing proof, unclear domain rule, or design decision>
```

## Guardrails

- Do not treat `.agent_goal/goal_theory.md` as a replacement for source code, tests, papers, or the user's latest instruction.
- Do not treat `.agent_advice` as confirmed theory or GT. Advice-backed theory belongs under assumptions, tradeoffs, source anchors, or open questions until supported.
- Do not invent theory to make the project look more rigorous. Mark inferred reasoning as inferred.
- Do not let a concept class, source rank, risk class, or decision owner act as an authority grant. They describe truth and requirements; `$manage-agent-authority` owns grants and leases.
- Do not rewrite a locked concept or relation digest without its recorded decision owner and fresh evidence. Preserve legacy gaps as `unclassified` rather than backfilling approval.
- Do not overwrite existing theory notes wholesale unless they are empty, placeholder-only, or the user explicitly requests replacement.
- Do not include secrets, credentials, private keys, tokens, sensitive raw transcripts, or large copyrighted excerpts.
- Keep the file compact enough for future agents to read before technical work.
