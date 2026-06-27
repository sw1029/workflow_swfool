# Task And Candidate Templates

## `task.md` Template

Use this shape for the final selected task:

```markdown
# Task

## Execution Environment

- Status: selected | unresolved | not_applicable
- Source: previous_task | find-local-python-envs | repository_manifest | manual_inference
- Type: conda | venv | local | non_python | unknown
- Name:
- Python:
- Run Prefix:
- Dependency Notes:
- Progress Target: advanced | safety_only | no_progress | regressed
- Progress Kind: goal_productive | governance_only
- Validation Profile: current_only | affected_chain | full_chain
- Authority Policy: `$manage-agent-authority` result (`.agent_goal/agent_authority.md` | default_current_agent_permissions)
- External Advice: <adv-id/path | none>
- Task Pack: <pack-id/path | none>
- Task Pack Item: <item-id | none>
- Pack Position: <order/total | none>
- Pack Source: planned | inserted | reordered | none
- Prerequisite Manifest: <path/status/hash summary, or none>

## Objective

<One concrete improvement objective.>

## Background

- Goal alignment:
- Issue link:
- Architecture/theory link:
- Authority policy link:
- External advice link:
- Schema contract link:
- Task miss or candidate source:

## Requirements

- <Specific requirement>

## Acceptance Criteria

- <Observable completion condition>

## Validation

- <Test, command, metric, review, or evidence required>

## Constraints

- <Relevant convention, forbidden action, compatibility or safety rule>

## Out Of Scope

- <What this task should not attempt>

## Open Questions

- <Unknowns that must be resolved before or during implementation>
```

Environment section rules:

- Put `## Execution Environment` immediately after `# Task`.
- Prefer the previous `task.md` environment section when it is explicit and still applicable.
- If it is absent for a Python task, use `$find-local-python-envs` and choose in this priority order: conda, venv, local/system Python.
- `Run Prefix` must be directly usable, such as `conda run -n ENV`, `/path/to/.venv/bin/python`, or `python3`.
- Use `Status: unresolved` when no usable environment is found; include the blocker in `Dependency Notes`.
- Use `Status: not_applicable` only when the task requires no Python/code execution.
- Include `Progress Target` for every task. Use `advanced` only when the task is expected to unlock a new execution/readiness/goal state or materially reduce a blocker.
- Include `Progress Kind` for every task. Use `goal_productive` only when the task is expected to produce goal-relevant output, quality evidence, source-backed validation, or another non-sidecar artifact that reduces goal distance.
- Include `Validation Profile` for every executable or verifiable task. Use `full_chain` only for live dispatch, readiness promotion, issue closure, shared validator/runtime changes, or explicit user request.
- Include `Authority Policy` for every task from `$manage-agent-authority`. Use `.agent_goal/agent_authority.md` when present; otherwise use `default_current_agent_permissions` and do not infer API/network/destructive authority.
- Include `External Advice` as `none` unless an `.agent_advice/active` document influenced selection, requirements, constraints, or validation. When used, list the `adv-*` ID or path and keep it separate from goal truth.
- Include task-pack fields as `none` for standalone tasks. When a pack item is promoted, list the pack ID/path, item ID, item position, and whether it was planned, inserted, or reordered.

## Candidate Task Template

Store unapplied candidates under `.task/candidate_task/YYYYMMDD-HHMMSS-<slug>.md`.

```markdown
# Candidate Task

- Status: candidate | blocked | deferred
- Source: goal_alignment | task_miss | prior_candidate | synthesis
- Candidate Class: state_transition | batchable_micro_contract | safety_only | goal_progress
- Expected Progress: advanced | safety_only | no_progress | regressed
- Progress Kind: goal_productive | governance_only
- Semantic Signature:
- Supplied Input Delta Needed: yes | no
- Validation Profile: current_only | affected_chain | full_chain
- Authority Policy: `$manage-agent-authority` result (`.agent_goal/agent_authority.md` | default_current_agent_permissions)
- External Advice: <adv-id/path | none>
- Created:
- Supersedes:

## Candidate Objective

<Concrete improvement candidate.>

## Why Not Applied Now

- <Reason this was not selected as the current task.md>

## Evidence

- <Goal, issue, authority, external advice, architecture, theory, task_miss, or repo evidence>

## Potential Requirements

- <Requirement if promoted later>

## Validation Idea

- <How to verify if later applied>

## Blocking Questions

- <Unknowns or dependencies>
```

## Task Pack JSON Template

Store task packs under `.task/task_pack/pack-YYYYMMDD-HHMMSS-<slug>.json`. The JSON queue is canonical; render a same-name `.md` file in the user's requested language after every JSON change.

```json
{
  "schema_version": 1,
  "pack_id": "pack-YYYYMMDD-HHMMSS-slug",
  "status": "active",
  "language": "ko",
  "goal": "Long-range task goal.",
  "current_item_id": "item-001",
  "created_at": "ISO-8601",
  "updated_at": "ISO-8601",
  "items": [
    {
      "item_id": "item-001",
      "order": 1,
      "status": "planned",
      "title": "Promotable task title",
      "objective": "One concrete task objective.",
      "acceptance": ["Observable condition"],
      "validation_profile": "current_only",
      "progress_target": "advanced",
      "dependencies": [],
      "source_evidence": [],
      "blocker_signature_expected": "taxonomy|issue|surface|missing_input",
      "semantic_signature_expected": "stable-goal-axis-family",
      "progress_kind_expected": "goal_productive",
      "positive_input_delta_required": false,
      "required_new_input_kinds": [],
      "promotion": {
        "task_id": null,
        "task_path": null,
        "promoted_at": null
      },
      "result": {
        "validation_verdict": null,
        "progress_verdict": null,
        "progress_kind": null,
        "semantic_signature": null,
        "blocker_signature": null
      }
    }
  ],
  "mutation_log": [],
  "terminal_blocker": null
}
```

Pack rules:

- Keep at most one active task pack unless a caller explicitly authorizes multiple packs.
- Prefer 2-5 items. Use a standalone task when only one item is known.
- Promote only one item into the active `task.md` per derivation.
- Use `terminal_blocked` when no viable item remains and no supplied input delta, authority change, or external-state change exists. Include `semantic_signature`, `root_cause_attempted_for_family`, authorized-alternative-path status, provider re-attempt status, and dual-track attempt evidence when a hard loop gate applies, so later derivation can seal the family rather than only the current target surface.
- Refresh the Markdown render with `$orchestrate-task-cycle/scripts/task_pack_queue.py --root . render --language <language>` after any JSON edit.

## Candidate Application Rule

When a candidate becomes the real `task.md`:

1. Log the old `task.md` as `past_task`.
2. Write the candidate-derived final `task.md`.
3. Delete the applied candidate file from `.task/candidate_task/`.
4. Mention the deleted candidate path in the final response and `past_task` log note.

If no previous `task.md` exists, treat the write as `initial_init`: skip `past_task` logging, write the initial `task.md`, index it when possible, and only delete an applied candidate after the new task is written and the candidate transition is recorded.
