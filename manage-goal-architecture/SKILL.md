---
name: manage-goal-architecture
description: Manage a workspace-local `.agent_goal/goal_architecture.md` file documenting the repository architecture relevant to the active goal. Use when the user asks to create, read, update, summarize, or align goal architecture, repo structure, module map, script inventory, architecture notes, component responsibilities, data flow, or workspace architecture documentation in the same `.agent_goal` style as `$manage-agent-goal`.
---

# Manage Goal Architecture

Use `authority.operations.json` and the shared [authority v2 contract](../manage-agent-authority/references/authority-v2-contract.md). Reading or summarizing is authority-free. Publishing a bounded design update requires an exact grant, while design selection and any core goal-truth change remain independent typed decisions.

## Overview

Use this skill to maintain `.agent_goal/goal_architecture.md`: a concise architecture note for future agents working toward the goal. It should describe the repository structure, major modules, important scripts, key data/artifact directories, and how those pieces relate to the goal.

Prefer a repo structure map at the top, then short responsibility summaries. Keep the file useful as onboarding context, not as exhaustive generated documentation.

When `.agent_goal/goal_theory.md` contains a goal concept graph, use its exact concept IDs, revisions, and digests to maintain a realization map. Architecture explains which components and consumers realize a concept; it does not reclassify concept truth or grant authority. Read the [goal concept graph contract](../deep-interview-goal-context/references/goal-concept-graph.md) when adding or changing this map.

When `.agent_advice/active/*.md` exists or the user names external advice, use it only as non-GT design evidence. It can suggest architecture questions or updates, but it must not override repository facts, `.agent_goal` GT, or the latest user instruction.

## Workflow

1. Locate the workspace root.
   - Default to the current working directory unless the user names another root.
   - Create `.agent_goal/` if it does not exist.
   - Manage only `.agent_goal/goal_architecture.md`.

2. Inspect the repository structure.
   - Use `rg --files`, `find`, or targeted directory listings.
   - Read high-signal files such as README, manifests, package files, CLI entry points, scripts, config, tests, and existing `.agent_goal` files.
   - Read relevant `.agent_advice/active/*.md` or a `$manage-external-advice` packet only when the architecture update depends on it; cite the advice path separately from `.agent_goal` sources.
   - Avoid reading large binaries, generated artifacts, datasets, logs, model files, archives, and caches in full.

3. Create or update the architecture file.
   - Preserve useful existing user-authored content.
   - Update stale module/script summaries when the repo structure changed.
   - Mark uncertain descriptions as inferred instead of presenting them as fact.
   - Bind concept realization rows to the current theory graph digest. Mark legacy or unresolved bindings `unclassified` rather than inferring user approval from existing code.
   - Prefer concise bullets over long prose.

4. Include required content.
   - Add a repo structure map using a tree-style code block or compact bullet outline.
   - Summarize each important module, package, app, service, script, test area, config area, and data/artifact directory.
   - Explain goal relevance: why each major area matters for the active goal.
   - Include known entry points and common commands when supported by repository evidence.
   - When a concept graph exists, map each active concept to its realizing components, downstream consumers, validation predicates, and compatibility boundary.

5. Report changes.
   - Tell the user whether `.agent_goal/goal_architecture.md` was created or updated.
   - Summarize the most important architectural facts and any gaps.

## Template

Use this structure for `.agent_goal/goal_architecture.md`:

````markdown
# Goal Architecture

## Scope

- Workspace: <path or repo name>
- Goal relevance: <how this architecture supports the current goal>
- Last updated: <date/time or "Not recorded">

## Repository Structure

```text
.
├── <directory-or-file>  # <short purpose>
└── <directory-or-file>  # <short purpose>
```

## Major Components

- `<path>`: <responsibility and goal relevance>

## Concept Realization Map

- Goal concept graph SHA-256: <digest from goal_theory.md>

| concept_id | concept_digest | realizing_component_ids | consumer_ids | validation_predicate_ids | realization_status |
| --- | --- | --- | --- | --- | --- |
| `<opaque id>` | `<sha256>` | `<opaque/path-safe ids>` | `<consumer ids>` | `<predicate ids>` | `realized | partial | planned | unclassified` |

## Scripts And Entry Points

- `<path>`: <what it does, expected inputs/outputs, important options if known>

## Data, Artifacts, And Generated Outputs

- `<path>`: <what lives here and whether it is source, generated, cache, report, or ignored>

## Tests, Validation, And Tooling

- `<path or command>`: <what it validates or builds>

## Architecture Notes

- <cross-module relationships, data flow, ownership boundaries, or constraints>

## Open Questions

- <unknown structure, unclear responsibility, or area not inspected>
````

## Guardrails

- Do not treat `.agent_goal/goal_architecture.md` as a replacement for source code, README, or the user's latest instruction.
- Do not treat `.agent_advice` as architecture GT. If advice changes architecture direction, label it as advice-backed evidence and keep conflicts/open questions explicit.
- Do not invent module purposes. If only a filename suggests a purpose, label it as inferred.
- Do not use architectural existence as proof that a concept is core, user-ratified, or authorized. Concept truth comes from the confirmed theory graph; effective authority comes from `$manage-agent-authority`.
- Do not silently remap a component to a different concept revision. Preserve stale bindings and route an explicit graph/architecture reconciliation.
- Do not overwrite existing architecture notes wholesale unless they are empty, placeholder-only, or the user explicitly requests replacement.
- Do not include secrets, credentials, raw sensitive data, or full large-file contents.
- Keep the file compact enough for future agents to read at the start of work.
