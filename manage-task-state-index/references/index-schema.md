# Task State Index Schema

## JSONL Event Fields

Each `.task/index.jsonl` line is one JSON object. Treat the file as append-only.

Required fields:

- `event`: `upsert` or `link`.
- `id`: stable artifact ID.
- `updated_at`: local ISO-8601 timestamp.

Common `upsert` fields:

- `type`: `task`, `task_pack`, `past_task`, `candidate_task`, `task_miss`, `agent_log`, `execution`, `audit`, `validation`, `goal`, `goal_prompt`, `interview`, `environment`, `external_advice`, `issue`, `issue_resolution`, `issue_map`, `schema_contract`, or `schema_map`.
- `status`: lifecycle status such as `active`, `candidate`, `applied`, `open`, `blocked`, `in_progress`, `resolved`, `closed`, `archived`, `deleted`, `passed`, `partial`, or `failed`.
- `path`: workspace-relative artifact path.
- `title`: short human-readable label.
- `parent_id`: optional owning task or parent artifact ID.
- `content_sha256`: SHA-256 digest when the path exists.
- `fields`: optional structured metadata.
- `links`: optional list of relationship objects.
- `note`: concise factual note.

Lifecycle fields use the existing `fields` object: `record_class` (`mutable_alias` or `immutable_snapshot`), `snapshot_digest`, `snapshot_path`, `canonical_id`, and optional `alias_path`. Historical records compare only to their own immutable snapshot body/digest. Active switches return `lifecycle_transition_result` with ordered booleans for previous snapshot preservation, previous active supersede, new canonical add, alias update, link update, and index render.

Relationship object:

```json
{"rel": "derived_from", "id": "cand-20260522-213000-parser"}
```

## Link Relationships

Use these relationship names consistently:

- `derived_from`: a task was selected from a candidate.
- `promoted_from_pack`: a task was promoted from a task-pack item.
- `pack_for_task`: a task pack constrains or supplies the current task.
- `inserted_after`: a task-pack item was inserted after another item.
- `reordered_by`: a task-pack order changed because of a workflow result.
- `terminal_blocker_for`: a terminal blocker prevents a new narrowing task.
- `input_delta_for`: positive input delta evidence for a task or pack item.
- `supersedes`: a new task replaces a prior task.
- `archived_as`: previous `task.md` was logged as `past_task`.
- `produced`: one artifact produced another artifact.
- `audit_for`: audit evidence for a task or miss.
- `run_for`: execution log for a task.
- `miss_for`: task_miss associated with a task.
- `resolves`: evidence resolves a task_miss.
- `validates`: validation report for a task.
- `blocked_by`: task is blocked by a miss, failed run, or missing environment.
- `environment_for`: environment discovery evidence for a task, run, or validation.
- `issue_for`: implementation issue associated with a task, candidate, miss, validation, or goal.
- `tracks_task`: issue tracks the active or next `task.md`.
- `derived_from_issue`: task or candidate was derived from issue analysis.
- `fixes_issue`: task, run, validation, or commit evidence fixes an issue.
- `closes_issue`: resolution artifact closes a local or GitHub issue.
- `resolved_by`: issue is resolved by a run, validation, task, or log artifact.
- `worktree_for`: branch/worktree mapping for an issue.
- `branch_for`: branch mapping for an issue.
- `prompt_for`: prompt-shaping evidence for goal files.
- `interview_for`: interview state or draft evidence for goal architecture/theory files.
- `contract_for`: `.schema/` or `.contract/` schema/module/script contract constrains a task, goal, module, script, or candidate.
- `schema_for`: schema artifact describes a module, script, task, or data artifact.
- `module_contract_for`: module contract for a target module path.
- `script_contract_for`: script contract for a target script path.
- `depends_on`: one contract or artifact depends on another.
- `produces_schema`: module/script/task produces a schema or schema-bearing artifact.
- `consumes_schema`: module/script/task consumes a schema or schema-bearing artifact.
- `compatible_with`: contract is compatible with another contract or versioned artifact.
- `breaks_contract`: change, task, or candidate would break a contract.
- `supersedes_contract`: contract version replaces a previous contract version.
- `causes`: causal-map edge from one schema/contract/module/script concern to another.
- `caused_by`: inverse causal-map edge when useful for scanability.
- `id_audit_for`: ID consistency audit evidence for a workflow or artifact.
- `id_insight_for`: additional ID insight agent output for a workflow or artifact.
- `advice_for`: external advice relevant to a task, candidate, goal-context operation, schema record, issue, or validation.
- `incorporated_into`: external advice was incorporated into a task, candidate, design/schema note, issue, or validation artifact.
- `applied_by`: evidence or log that retired an active advice item.
- `rejected_by`: evidence or log that rejected an advice item.
- `superseded_by`: newer advice or task direction supersedes the advice.
- `conflicts_with_goal`: advice conflicts with `.agent_goal` GT.
- `conflicts_with_authority`: advice conflicts with `.agent_goal/agent_authority.md` or effective permissions.
- `related_to`: fallback when no stronger relationship applies.

## Global ID Audit

Use `scripts/task_state_index.py --root . audit` for deterministic checks before completion, deletion, miss resolution, or `task.md` replacement. The audit checks:

- ID prefix/type mismatches,
- missing paths for non-deleted artifacts,
- digest mismatches after an artifact changed,
- missing parent IDs,
- broken or self links,
- multiple active task IDs,
- duplicate non-closed IDs for the same artifact path,
- task-related artifacts not linked to an active task,
- standard artifacts present on disk but not represented in the index,
- `.issue` implementation issue records and GitHub issue mirrors present on disk but not represented in the index,
- `.schema` and `.contract` schema contracts and causal maps present on disk but not represented in the index,
- `.agent_advice` external advice artifacts present on disk but not represented in the index,
- `.task/task_pack` JSON queues present on disk but not represented in the index,
- multiple active task packs,
- missing or stale `.task/index.md`.

Audit output separates `current_surface_blockers` from `historical_debt`. Only missing current canonical ID, duplicate active alias, and broken current links block completion-oriented close; inactive immutable-history defects remain debt.

Use `--write-report` to create `.task/id_audit/YYYYMMDD-HHMMSS-id-consistency-audit.md` and index it as `audit-*`.

## Markdown Index

Regenerate `.task/index.md` from JSONL after every state change. The Markdown file is a view, not the canonical source. It should include:

- generation timestamp,
- artifact counts,
- grouped artifact tables,
- IDs, statuses, titles, paths, parent IDs, relationships, and update times.
