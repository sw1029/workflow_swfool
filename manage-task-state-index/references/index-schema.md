# Task State Index Schema

## Contents

- [JSONL event fields](#jsonl-event-fields)
- [Stable path and replacement contract](#stable-path-and-replacement-contract)
- [Durability contract](#durability-contract)
- [Immutable transition plan contract](#immutable-transition-plan-contract)
- [Prospective selected-successor settlement](#prospective-selected-successor-settlement)
- [Link relationships](#link-relationships)
- [Global ID audit](#global-id-audit)
- [Markdown index](#markdown-index)

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

When a caller-owned decision must project across authority, canonical task, and index surfaces, `lifecycle_transition_result` may also carry this bounded optional object:

```json
{
  "state_projection": {
    "projection_epoch": "cycle_C",
    "source_decision_id": "packet_K",
    "surface_epochs": {
      "authority": "cycle_C",
      "task": "cycle_C",
      "index": "cycle_C"
    },
    "authority_digest": "full-sha256",
    "task_digest": "full-sha256",
    "index_digest": "full-sha256",
    "projection_status": "current"
  }
}
```

Allowed `projection_status` values are `current`, `stale_projection`, `not_evaluated`, and `conflict`. `current` requires one non-empty source decision, all three surface epochs equal to the canonical epoch, and valid digests. A missing surface or unequal epoch is `stale_projection`; malformed or contradictory bindings are `conflict`; absent evidence is `not_evaluated`. When the source decision is present, repair stale projections against that same decision before asking the user again. This object is transition evidence only: it cannot create authority, task selection, completion, or verification. Ordinary index-only scans omit it and retain their existing behavior.

Before a dependent cross-surface transition, the caller emits `state_projection_required: true`. It may set `authority_projection_applied`, `task_projection_applied`, and `task_index_projection_applied` only after each named surface is current for the same source decision. These trigger/receipt fields require the bounded object above; they are not substitutes for it. Missing or malformed projection evidence fails quiet for unrelated index-only work and fails closed only for the dependent transition.

Migration correction events may carry `fields.link_tombstones`, a list of exact `{rel,id}` pairs. Apply each tombstone only to that artifact's merged link projection before adding links from the same event. The historical link events remain byte-identical. This bounded suffix semantics is valid only under the sealed migration contract in [legacy-migration.md](legacy-migration.md).

Mapped legacy projections preserve changed source tokens in bounded `fields.legacy_original_event|status|type` objects containing the exact source `token` and mapping `reason_code`. Migration correction events carry a deterministic `fields.migration_correction_event_id`; non-independent quarantine manifest entries bind those IDs and their canonical event SHA-256 values under the sealed migration contract.

For task packs, retain bounded initial-selection fields when present: promotion origin, inline receipt ref, creation-snapshot ref, authority-receipt ref/digest, authority mode, historical-selection status, and normalization mode/verdict. Do not copy receipt bodies into the index or turn `current_ratification` into historical authority.

Treat `partially_resolved` as an active residual-bearing lifecycle state. It preserves the owning workflow's unresolved remainder and must not be normalized to `resolved` by substring matching.

## Stable Path and Replacement Contract

- `scan` keeps the current ID when artifact type and workspace-relative path are unchanged. A digest, title, status, or bounded-field change appends an update event to that ID.
- For `task.md`, an exact same-digest mutable alias in `complete` or `completed` remains current but non-executable. Do not infer bounded completion from `blocked`, `terminal_blocked`, or `deferred`; preserve those only through their existing explicit owner transition. A changed body or executable status under that completed ID is not an ordinary update: reject every scan and direct upsert entrypoint until the caller performs an explicit active switch with a distinct successor ID.
- A new explicit `--id` or `add --replace` declares semantic replacement. Append the new canonical record, mark prior active same-path records `superseded`, and add reciprocal `supersedes` / `superseded_by` links.
- Never create multiple non-closed IDs for an ordinary same-path edit. When legacy duplicate active records are encountered during a stable update, retain one canonical ID and supersede the others.

Static decision-boundary fixtures:

- Negative: `task_T` is bounded-complete, its mutable alias has the same digest, no successor exists, and global readiness waits. Expected verdict: `task_T` stays current but non-executable and scan does not emit `active`. Forbidden overclaim: selecting it again because the alias exists.
- Negative: the alias body changes while `task_T` remains completed and no lifecycle-switch receipt exists. Expected verdict: ordinary scan fails closed without mutation. Forbidden overclaim: reactivating `task_T` in place.
- Happy path: the caller preserves `task_T` as immutable history and performs the existing active-switch transaction to distinct `task_U`. Expected verdict: only `task_U` is active/executable. Forbidden overclaim: rewriting `task_T` history.

## Durability Contract

Use workspace-local `.task/index.lock` for every JSONL or Markdown mutation. While holding the lock, validate the complete existing JSONL, prepare all related events, durably flush a same-directory temporary file, atomically replace `index.jsonl`, and atomically regenerate `index.md`. A malformed or unsupported ledger must remain byte-for-byte unchanged. Empty registries report `not_evaluated_no_artifacts`; they are not success or completion evidence.

`scan --dry-run` and `scan --check` are read-only publication planners. They must not create `.task/`, an index, a lock file, a snapshot, or a Markdown render. When an index exists, bind the observation to its pre/post SHA-256 and fail if it changes during the read. `--check` exits `1` when the plan reports a durable change and `0` when the projection is current; the exit code is not a completion verdict. A workspace with no standard artifacts and no task-state files is a clean no-context result, not a request to initialize an empty registry.

Before a mutating scan appends its first event, complete the same read-only plan over the entire discovered inventory, simulate canonical identity selection in discovery order, reject cross-path/cross-type collisions, and recheck the ledger and artifact anchors. This prevalidation prevents a deterministic later collision from leaving an earlier partial append; ordinary per-item append/recovery semantics remain unchanged.

A committed legacy migration is the sole exception to ordinary whole-file current-row parsing. It preserves the original bytes at offset zero, then appends correction, seal, and receipt-anchor events. Before allowing any exact prefix quarantine, run the two-pass receipt graph validation in [legacy-migration.md](legacy-migration.md), including the hash-bound final journal, immutable completion marker, and quarantine-to-correction bindings. A missing or invalid receipt graph retains ordinary fail-closed mutation behavior.

### Immutable transition plan contract

`compile-transition` accepts a closed schema-v1 lifecycle intent containing exactly `schema_version`, `expected_index_revision`, and ordered `actions`. Each action uses `action=set_lifecycle` and supplies `artifact_ref`, `artifact_type`, `identity=auto|current|new`, `status`, plus optional `note` and `relationships`. Each relationship contains `rel`, `target_ref`, and optional `target_type` / `target_identity=auto|current|new`. `expected_index_revision` is `current`, null for an absent ledger, or the exact lowercase SHA-256 observed by the caller. The compiler reopens regular workspace files, resolves current identities from the ledger, derives new stable IDs and content hashes, resolves relationship targets exactly, and emits the existing transition-request schema. The compilation is read-only, content-bound, and non-authoritative. It cannot choose task meaning or apply the index mutation. Exact replay with the same explicit time is byte-stable; index or artifact drift requires recompilation.

For a task/archive/supersede/advice/task-pack link transition that spans several events, publish schema-v1 `task_state_transition_plan` JSON only at `.task/transition_plans/<plan-id>.json`. Filename aliases are invalid because intent and receipt sidecars use the same `plan_id`. The plan fixes one timestamp, ordered versioned events, a deterministic `transition_plan_id` binding on every event, artifact content anchors, exact pre/post ledger SHA-256 values, the exact pre-ledger byte length (`before_size`), mandatory Markdown rendering, and exact pre/post Markdown SHA-256 values. Final upsert paths and anchors form a one-to-one mapping. A planned `content_sha256` is the apply-time expected artifact digest, so prepare-all -> owner artifact publication -> index apply supports prospective missing files and mutable `task.md` replacement; an upsert without a content digest remains bound to its unchanged planning digest. Planning is read-only until the immutable plan itself is published; `plan-transition --dry-run` creates neither `.task/`, a lock, a plan, a snapshot, nor a render. Immutable plan publication is the authority-free, reversible `prepare_task_state_transition_plan` metadata operation and never grants canonical apply authority.

`verify-plan --phase planning` checks each artifact's planning `before_sha256`; `verify-plan --phase apply` checks its `expected_sha256`. Both phases retain the exact ledger and Markdown before-CAS binding. When a multi-owner dependency set is partly published and every observed artifact is exactly either its before or expected digest, the public status is `materializing`; it is nonterminal, cannot be settled no-effect, and becomes apply-ready only when every expected digest is present. This closed distinction lets a coordinator validate a prospective task, advice, or archive transition before dependency publication and then validate the intended bytes after publication without relabeling normal dependency progress as drift.

`apply-plan` validates the complete plan and every apply-phase CAS anchor before staging an append. Plan build reuses the same current-suffix and completed-alias batch validators required by apply. Under `.task/index.lock`, apply publishes an immutable `.task/transition_intents/<plan-id>.json` barrier before canonical append, appends the entire event list with the existing atomic JSONL writer, renders once, then publishes `.task/transition_receipts/<plan-id>.json`. Every normal suffix writer detects an unfinished intent and fails closed before append; only recovery of that same plan is allowed through the barrier. The canonical execution-result binding is the receipt file's actual SHA-256 (`execution_result_binding.ref|sha256` / `receipt_file_sha256`), not the canonical receipt-body digest. Likewise, `plan_file_sha256` binds the newline-bearing immutable plan file while `plan_sha256` identifies the canonical plan body. Transition plans, intents, apply receipts, and no-effect receipts reject symlinked owned directories, symlinked leaves, and non-canonical artifact paths.

An exact replay finds the unique complete ordered set of plan-tagged events, appends zero rows, and verifies or recovers the render and receipt. Recovery additionally proves that the first `before_size` ledger bytes hash to `before_sha256`, the exact canonical planned-event bytes occur immediately afterward as one contiguous batch, and every remaining byte is the canonical encoding of a suffix that passes the shared current-suffix/batch validators. A partial, noncontiguous, conflicting, or duplicate tag set; changed historical prefix; invalid suffix; changed plan body; stale ledger/Markdown/artifact anchor; or conflicting receipt fails closed. If the ledger batch committed but render or receipt publication was interrupted, replay repairs those derived/post-commit surfaces from this proven boundary. When a valid unrelated later suffix is already present, recovery preserves it and renders the current full ledger projection; it never rewinds to the historical plan boundary. Historical transaction completion is reported independently from `current_projection_healthy`; an exact historical receipt with a stale current Markdown projection is `recovery_required`, not a false `already_applied`. `verify-plan` is read-only and reports `ready`, `materializing`, `already_applied`, `settled_no_effect`, `recovery_required`, `stale`, or `conflict`, including receipt consistency and observed effect/intent flags.

For a stale untouched plan caused by canonical ledger/Markdown drift or an artifact digest that is neither its before nor expected value, `settle-plan-no-effect` records `.task/transition_no_effect_receipts/<plan-id>.json` under the same index lock. The receipt binds the exact plan body and newline-bearing plan file, the observed ledger, Markdown, and artifact digests, non-empty CAS defects, and false effect/intent observations. It contains no artifact body. Once present it is terminal for that plan: apply rejects it before creating canonical files, verifier reopens it, and a caller uses its actual file SHA-256 as no-effect execution evidence. All-before, all-expected, and partial before/expected dependency states are ineligible. An invalid or tampered receipt, an intent without a complete event batch, or any plan-tagged event requires conflict or recovery handling and can never be relabeled no-effect.

Use `task_index_transition_plan` as the preferred authority subject for this batch. Retain `task_index` only as the compatibility subject for legacy direct writers.

### Prospective selected-successor settlement

A selected successor uses transition request schema version 2 to break the former
publication cycle without weakening ownership. The request is the ordinary exact event
batch plus these closed fields:

```json
{
  "schema_version": 2,
  "external_settlement_kind": "selection_publication",
  "artifact_sources": [
    {
      "target_ref": "task.md",
      "source": {"ref": "<prospective-task-ref>", "sha256": "<raw-sha256>"}
    }
  ],
  "events": ["<exact supersede/new-active event rows>"],
  "render": true
}
```

The prospective source must be one safe regular workspace file and must exactly match
the new active task event's content digest. The plan records a `task.md` artifact anchor
whose expectation is `prospective_source_sha256`; it does not claim those bytes are
already current. Prospective sources must exactly cover all such anchors. Schema-v1
requests cannot declare artifact sources or external settlement, and schema-v2 requests
cannot use another external owner.

Use this closed transaction:

1. Publish the immutable task-state plan while ledger, render, and `task.md` still match
   their planning prestate.
2. Prepare a schema-v3 selection publication that binds the exact plan and prospective
   task source.
3. Run `apply-plan` with that publication prepare. Under the task-state lock, verify the
   plan/prepare/CAS bindings, publish the usual transition intent, append the exact event
   batch, render the index, and publish
   `.task/transition_pending_receipts/<plan-id>.json`. Its schema version is 2, kind is
   `task_state_transition_pending_receipt`, and activation is
   `pending_external_settlement`. It binds the plan/file digests, ledger/render after
   digests, event count, and exact publication prepare. `task.md` remains unchanged.
4. The selection-publication owner reopens that pending receipt, CAS-writes only
   `task.md` last, verifies the prospective digest, and commits a schema-v3 receipt that
   echoes the pending receipt and plan ID.
5. Run `settle-plan-external` with the exact committed publication binding. The task-state
   owner reopens the pending/prepare/commit chain, verifies current `task.md`, its exact
   event batch, and current render, then publishes
   `.task/transition_receipts/<plan-id>.json` with schema version 2, kind
   `task_state_transition_apply_receipt`, and `activation_status: settled`.

The pending intent remains a barrier to unrelated task-state writers until step 5.
`verify-plan` reports `pending_external_settlement` after step 3 and `already_applied`
after settlement. Exact replay appends no events and returns
`already_pending_external_settlement` or `already_settled`. A missing, stale, or
conflicting prepare/commit binding; foreign `task.md` bytes; missing exact event batch;
or stale projection fails closed. Never repair this lifecycle by writing `task.md`
ahead of publication or by manufacturing an apply receipt.

The settled receipt sets `selection_consumption_allowed: true`. The pending receipt and
committed publication without settlement keep that value false. External settlement is
a bound-lifecycle finalization of the already authorized exact task-state/publication
subject, not a second authority source.

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

Use `PYTHONPATH="${CODEX_HOME:-$HOME/.codex}/skills/manage-task-state-index/scripts:${CODEX_HOME:-$HOME/.codex}/skills/record-agent-work-log/scripts" python3 -m manage_task_state_index index --root . audit` for deterministic checks before completion, deletion, miss resolution, or `task.md` replacement. The audit checks:

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
