# Task State Index Schema

## JSONL Event Fields

Each `.task/index.jsonl` line is one JSON object. Treat the file as append-only.

Current writers emit `format_version: 2` and `schema_version: 1`. Detect versions before applying the current event discriminator. Readers accept legacy rows with either version field absent as version 1 and infer a missing legacy discriminator only from an unambiguous required upsert or link shape. Keep mutation readers strict: reject malformed JSON, non-object rows, invalid field shapes, unknown lifecycle statuses, and versions newer than the current reader before appending anything. Let audit readers quarantine malformed rows and continue with canonical rows without rewriting history.

Required fields:

- `event`: `upsert` or `link`.
- `id`: stable artifact ID.
- `updated_at`: local ISO-8601 timestamp.
- `format_version`: event serialization format; required on new rows.
- `schema_version`: event field contract; required on new rows.

Common `upsert` fields:

- `type`: `task`, `task_pack`, `past_task`, `candidate_task`, `task_miss`, `agent_log`, `execution`, `audit`, `validation`, `goal`, `goal_prompt`, `interview`, `environment`, `external_advice`, `issue`, `issue_resolution`, `issue_map`, `schema_contract`, or `schema_map`.
- `status`: one of the closed vocabulary `active`, `applied`, `archived`, `blocked`, `candidate`, `closed`, `complete`, `completed`, `deferred`, `deleted`, `deprecated`, `failed`, `in_progress`, `informational`, `logged`, `needs_review`, `not_applicable`, `obsolete`, `open`, `partial`, `partially_resolved`, `passed`, `raw`, `rejected`, `resolved`, `running`, `skipped`, `stale`, `superseded`, or `terminal_blocked`.
- `path`: workspace-relative artifact path.
- `title`: short human-readable label.
- `parent_id`: optional owning task or parent artifact ID.
- `content_sha256`: SHA-256 digest when the path exists.
- `fields`: optional structured metadata.
- `links`: optional list of relationship objects.
- `note`: concise factual note.

Lifecycle fields use the existing `fields` object: `record_class` (`mutable_alias` or `immutable_snapshot`), `snapshot_digest`, `snapshot_path`, `canonical_id`, and optional `alias_path`. Historical records compare only to their own immutable snapshot body/digest. Active switches return `lifecycle_transition_result` with ordered booleans for previous snapshot preservation, previous active supersede, new canonical add, alias update, link update, and index render.

Migration correction events may carry `fields.link_tombstones`, a list of exact `{rel,id}` pairs. Apply each tombstone only to that artifact's merged link projection before adding links from the same event. The historical link events remain byte-identical. This bounded suffix semantics is valid only under the sealed migration contract in [legacy-migration.md](legacy-migration.md).

Mapped legacy projections preserve changed source tokens in bounded `fields.legacy_original_event|status|type` objects containing the exact source `token` and mapping `reason_code`. Migration correction events carry a deterministic `fields.migration_correction_event_id`; non-independent quarantine manifest entries bind those IDs and their canonical event SHA-256 values under the sealed migration contract.

For task packs, retain bounded initial-selection fields when present: promotion origin, inline receipt ref, creation-snapshot ref, authority-receipt ref/digest, authority mode, historical-selection status, and normalization mode/verdict. Do not copy receipt bodies into the index or turn `current_ratification` into historical authority.

Treat `partially_resolved` as an active residual-bearing lifecycle state. It preserves the owning workflow's unresolved remainder and must not be normalized to `resolved` by substring matching.

## Stable Path and Replacement Contract

- `scan` keeps the current ID when artifact type and workspace-relative path are unchanged. A digest, title, status, or bounded-field change appends an update event to that ID.
- A new explicit `--id` or `add --replace` declares semantic replacement. Append the new canonical record, mark prior active same-path records `superseded`, and add reciprocal `supersedes` / `superseded_by` links.
- Never create multiple non-closed IDs for an ordinary same-path edit. When legacy duplicate active records are encountered during a stable update, retain one canonical ID and supersede the others.

## Durability Contract

Use workspace-local `.task/index.lock` for every JSONL or Markdown mutation. While holding the lock, validate the complete existing JSONL, prepare all related events, durably flush a same-directory temporary file, atomically replace `index.jsonl`, and atomically regenerate `index.md`. A malformed or unsupported ledger must remain byte-for-byte unchanged. Empty registries report `not_evaluated_no_artifacts`; they are not success or completion evidence.

`scan --dry-run` and `scan --check` are read-only publication planners. They must not create `.task/`, an index, a lock file, a snapshot, or a Markdown render. When an index exists, bind the observation to its pre/post SHA-256 and fail if it changes during the read. `--check` exits `1` when the plan reports a durable change and `0` when the projection is current; the exit code is not a completion verdict. A workspace with no standard artifacts and no task-state files is a clean no-context result, not a request to initialize an empty registry.

Before a mutating scan appends its first event, complete the same read-only plan over the entire discovered inventory, simulate canonical identity selection in discovery order, reject cross-path/cross-type collisions, and recheck the ledger and artifact anchors. This prevalidation prevents a deterministic later collision from leaving an earlier partial append; ordinary per-item append/recovery semantics remain unchanged.

A committed legacy migration is the sole exception to ordinary whole-file current-row parsing. It preserves the original bytes at offset zero, then appends correction, seal, and receipt-anchor events. Before allowing any exact prefix quarantine, run the two-pass receipt graph validation in [legacy-migration.md](legacy-migration.md), including the hash-bound final journal, immutable completion marker, and quarantine-to-correction bindings. A missing or invalid receipt graph retains ordinary fail-closed mutation behavior.

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

Audit output also reports bounded `index_read_results`, `legacy_normalized_count`, `malformed_row_count`, `projection_completeness`, and `current_projection_status`. Classify each malformed row's impact as `independent`, `affected`, or `unknown`. Preserve unrelated current traceability when independence is established; set affected or unknown current identities to `not_evaluated`. Prefer read-time normalization and a later append-only migration receipt over rewriting an immutable legacy row.

Use `--write-report` to create `.task/id_audit/YYYYMMDD-HHMMSS-id-consistency-audit.md` and index it as `audit-*`.

## Markdown Index

Evaluate `.task/index.md` against the JSONL projection after every state change, and republish it only when that rendered projection differs. The Markdown file is a view, not the canonical source. It should include:

- generation timestamp,
- artifact counts,
- grouped artifact tables,
- IDs, statuses, titles, paths, parent IDs, relationships, and update times.

Rendering is semantic and byte-stable. Re-render first with the existing single `Generated` value; if that payload exactly matches the existing bytes, do not replace the file or change its modification time. When the projection differs, or the view is missing, malformed, or stale, publish a fresh payload atomically and set a fresh generation value. Repairing only the view does not append a JSONL event.
