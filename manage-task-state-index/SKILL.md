---
name: manage-task-state-index
description: "Maintain workspace `.task/index.md` and `.task/index.jsonl` as a durable task-state index using deterministic helpers first and Tier 2 `model_ref:balanced`/medium only for optional ID insight or delegated ID correction. Use when Codex creates, updates, promotes, archives, resolves, deletes, audits, validates, or needs global ID consistency across task, issue, goal, advice, schema-contract, execution, and validation workflows."
---

# Manage Task State Index

## Overview

Use this skill to keep one workspace-local task lifecycle index under `.task/`. The canonical record is append-only `.task/index.jsonl`; the human-readable view is `.task/index.md`.

Every canonical index/lifecycle write is `mutate_task_state_index` in `authority.operations.json` and follows the shared [authority v2 contract](../manage-agent-authority/references/authority-v2-contract.md). Immutable plan preparation/publication alone is the authority-free `prepare_task_state_transition_plan`: it is reversible, non-canonical workflow metadata and grants no permission to apply the plan. An owning task artifact, published plan, or correct scan result does not authorize changing the canonical index for a different subject digest.

This skill records traceability only. It does not decide task completion, delete artifacts, or replace the source workflows that create `task.md`, candidate tasks, implementation issues, task misses, execution logs, goal/interview outputs, or audit logs.

## Routing Policy

- When called from `$orchestrate-task-cycle`, consume the canonical orchestration reference [workflow-routing.md](../orchestrate-task-cycle/references/workflow-routing.md) as caller context, but keep this skill's fixed ID-only routing below.
- Run deterministic scan/audit/render helpers without assigning a model. When an optional ID insight or delegated ID correction agent is needed, request Tier 2 `requested_model_ref: model_ref:balanced` with `requested_reasoning_effort: medium` under `configured-tiered-routing-v3`.
- Apply the same Tier 2 balanced-profile/medium route to delegated scan interpretation, link repair, lifecycle transition recording, candidate/miss cleanup gating, or durable ID audit reporting.
- Do not inherit `high` or `xhigh` routing from caller workflows for `$manage-task-state-index` ID correction. This skill's ID-specific routing is fixed at medium unless the user explicitly changes it.
- Keep runtime model bindings in caller configuration or a repository adapter. If the binding is absent, retain `model_configuration_status: reference_only`; if the delegation tool cannot enforce the resolved model/effort, report `routing_enforcement: prompt_only|inherited_unverified` and a limitation. Never claim enforced routing or actual-model execution from an abstract reference alone.

## Index Model

Use these files:

- `.task/index.jsonl`: append-only JSONL events for durable state changes.
- `.task/index.md`: regenerated summary view grouped by artifact type.

Use stable IDs for all important artifacts:

- `task-*`: current or historical `task.md` content.
- `pack-*`: `.task/task_pack/*.json` task-pack queue; Markdown renders are linked as fields, not separate canonical records.
- `past-*`: previous `task.md` content archived as `past_task` through `$record-agent-work-log`.
- `cand-*`: `.task/candidate_task/` proposal.
- `miss-*`: `.task/task_miss/` report.
- `log-*`: `.agent_log/` record.
- `run-*`: execution evidence from `$run-task-code-and-log`.
- `audit-*`: audit evidence from `$inspect-repo-with-agents` or `$inspect-oom-risk`.
- `val-*`: completion validation report from `$validate-task-completion`.
- `env-*`: environment discovery evidence from `$find-local-python-envs`.
- `issue-*`: `.issue/` local issue documents or GitHub issue mirror documents from `$manage-implementation-issues`.
- `issue-res-*`: resolved, closed, or archived `.issue/` resolution records.
- `issue-map-*`: `.issue/index.md` or local issue mapping/history views.
- `goal-*`: `.agent_goal/` files managed by goal-related skills.
- `prompt-*`: raw prompt shaping drafts or reports from `$shape-agent-goal-prompt`.
- `int-*`: `.interview/` state and audit artifacts from `$deep-interview-goal-context`.
- `adv-*`: `.agent_advice/` external advice artifacts from `$manage-external-advice`; advice is non-GT direction evidence, not `.agent_goal` truth.
- `schema-*`: `.schema/` or `.contract/` schema, module contract, script contract, compatibility note, or needs-review contract.
- `schema-map-*`: `.schema/index.md`, `.schema/causal_map.md`, `.contract/index.md`, `.contract/causal_map.md`, compatibility map, or contracts JSONL map/history artifact.

Use only the closed lifecycle vocabulary documented in [index-schema.md](references/index-schema.md). Keep `partially_resolved` active: it means evidence resolved part of the artifact while an explicit residual remains. Never collapse it to `resolved` because its text contains that substring.

For an authorized malformed/legacy migration, read [legacy-migration.md](references/legacy-migration.md) and run `migrate`. Keep mappings external, preserve a byte-identical sealed prefix, and require its committed receipt. Classify observed tokens by exact equality only—never prefix, substring, suffix, regex, or wildcard—and require `mapping_method: exact_token_review` plus `pattern_inference_used: false`. Schema-v2 migration evidence also binds lock-time task/pack anchors, original tokens/reasons, corrections, final journal, and completion marker; missing or tampered bindings keep normal readers fail-closed.

Use `verify-migration` for source-separated completion evidence. It is read-only, distrusts the producer, and requires a caller-owned byte-identical mapping manifest outside `.task/migrations` that is neither the same file nor a hard link. It recomputes the sealed graph, separates migration-boundary from current-tail IDs, and accepts only externally bound fixture observations proving the exact phase transition without changing live protected artifacts. See [Independent verifier](references/legacy-migration.md#independent-verifier).

Validation artifacts may also record a separate progress status such as `advanced`, `safety_only`, `no_progress`, or `regressed` in their title, links, or concise metadata. Do not treat progress status as a replacement for validation status.

For the complete event schema and link relationship names, read [index-schema.md](references/index-schema.md).

## Workflow

Prefer compact lifecycle intent compilation before writing an event batch. Put only lifecycle actions, artifact refs, relationship intents, and the expected current index revision in the intent; let the script derive stable IDs, content digests, event rows, and replay identity.

Minimal closed intent shape:

```json
{
  "schema_version": 1,
  "expected_index_revision": "current",
  "actions": [
    {
      "action": "set_lifecycle",
      "artifact_ref": "task.md",
      "artifact_type": "task",
      "identity": "current",
      "status": "superseded",
      "relationships": [
        {
          "rel": "superseded_by",
          "target_ref": "task.md",
          "target_type": "task",
          "target_identity": "new"
        }
      ]
    },
    {
      "action": "set_lifecycle",
      "artifact_ref": "task.md",
      "artifact_type": "task",
      "identity": "new",
      "status": "active",
      "relationships": [
        {
          "rel": "supersedes",
          "target_ref": "task.md",
          "target_type": "task",
          "target_identity": "current"
        }
      ]
    }
  ]
}
```

`identity` is `auto`, `current`, or `new`. Each action is exactly
`set_lifecycle`; optional fields are `note` and `relationships`. Relationship
targets use the same exact artifact ref/type plus `auto|current|new` identity.

Initialize the closed module environment once before the commands below:

```bash
export PYTHONPATH="${CODEX_HOME:-$HOME/.codex}/skills/manage-task-state-index/scripts:${CODEX_HOME:-$HOME/.codex}/skills/record-agent-work-log/scripts"
```

```bash
python3 -P -m manage_task_state_index index --root . compile-transition \
  --intent transition-intent.json --at 2026-01-01T00:00:00Z

python3 -P -m manage_task_state_index index --root . plan-transition \
  --intent transition-intent.json --at 2026-01-01T00:00:00Z --dry-run
```

Use the full `--request-json` path only for compatibility or contract diagnostics. Compilation is read-only and does not authorize `apply-plan`; subject or index drift requires recompilation rather than manual digest repair.

For `index_pre_validate`, run `compile-prevalidation --at <RFC3339>` and pass the binding unchanged. Preserve `prevalidation_owner_result_binding`; transition gates handle exact, intermediate-fresh, and final-index revalidation; see [index-schema.md](references/index-schema.md#compiler-first-scan-and-owner-validation). For a governed scan, never model-author owner JSON or call `upsert_item` per artifact. Fix one timestamp, compile the inventory, authorize its exact compilation/plan, then apply once:

```bash
python3 -P -m manage_task_state_index index --root . prepare-scan \
  --at 2026-01-01T00:00:00Z \
  --focus-ref .agent_advice/active/example.md --focus-sha256 <sha256>

python3 -P -m manage_task_state_index index --root . apply-scan \
  --compilation-ref .task/scan_compilations/<scan-id>.json \
  --compilation-sha256 <sha256>
```

`prepare-scan --dry-run` is zero-write. Preparation separates logical updates from expanded events and emits no artifact bodies; apply rechecks CAS, appends once, renders once, and publishes a schema-v2 receipt. The `owner_result_binding` returned by `apply-scan` is the complete owner result: pass that binding directly to orchestration and never ask a model to restate or wrap its body. Projection repair writes an immutable pre-effect intent and a lock-bound receipt, enabling exact retry and historical prefix reconstruction. The legacy `scan` CLI is compatibility-only. See [index-schema.md](references/index-schema.md#compiler-first-scan-and-owner-validation).

Lint scan results with `lint-owner-result --cycle-id <cycle>`. It reopens the
exact scan compilation and committed evidence. New compiler-first cycles require
schema v2 and `lint_status: pass`; schema v1 is historical-only and blocks when
the bound cycle carries the enforced profile. Authority settlement independently
rejects opaque legacy owner results for an enforced cycle. See
[index-schema.md](references/index-schema.md#compiler-first-scan-and-owner-validation).

Selected-successor publication is the sole schema-v2 request path. It binds prospective
task Markdown, declares `external_settlement_kind: selection_publication`, and uses
`prospective_source_sha256`. Follow [the full transaction](references/index-schema.md#prospective-selected-successor-settlement).
Each of its three effects requires a content-addressed lease epoch that reopens the exact
bundle/rows and revalidates all three current reservations under the authority lock
through the write. Tokens, producer capabilities, and the gate are not authority.
Schema-v1 task-alias plans/intents and uncommitted schema-v1/v2 publication prepares
cannot create effects; an existing exact receipt remains repair/read-only recovery.

Render that request and its predecessor/successor events mechanically:

```bash
python3 -P -m manage_task_state_index index --root . prepare-selected-successor \
  --source-decision-ref <selection-receipt-ref> --source-decision-sha256 <sha256> \
  --task-source-ref <prospective-task-ref> --task-source-sha256 <sha256> \
  --at 2026-01-01T00:00:00Z
```

The selection owner still validates the complete decision receipt; this renderer reopens the exact binding, checks its selected task ID against the prospective Markdown, and derives only task-index mechanics.

Before authority consumes or releases a task-index reservation, run `validate-owner-result` with the exact owner-result, reservation, and pre-commit bindings. A canonical scan result or settled external receipt is validated against its immutable plan, contiguous event batch, legal descendant suffix, and current full Markdown projection. Use `--phase current` while the selected task must still be current and `--phase historical` after a later successor. Legacy ad hoc scan JSON is reported as `unknown_effect`, never upgraded to confirmed effect.

1. Initialize or refresh the index.
   - Create `.task/` if missing.
   - Preserve existing `.task/index.jsonl`; never truncate it.
   - Regenerate `.task/index.md` from JSONL whenever state changes.
   - Prefer the bundled script:

     ```bash
     PYTHONPATH="${CODEX_HOME:-$HOME/.codex}/skills/manage-task-state-index/scripts:${CODEX_HOME:-$HOME/.codex}/skills/record-agent-work-log/scripts" \
     python3 -P -m manage_task_state_index index --root . init
     ```

2. Discover current artifacts.
   - Scan for `task.md`, `.task/candidate_task/*.md`, `.task/task_pack/*.json`, `.task/task_miss/**/*.md`, `.task/validation/*.md`, `.task/id_audit/*.md`, `.issue/**/*.md`, integrity-verified `.agent_log/**/*.md`, `.agent_goal/*.md`, `.agent_advice/**/*.md`, `.interview/**/*.md`, `.schema/` schema/contract/map artifacts, and `.contract/` auxiliary contract/map artifacts. Reject unsafe/invalid agent-log stores through the shared `$record-agent-work-log` inspector instead of following symlinks or indexing tampered/orphan bodies.
   - Assign IDs to artifacts that are not already indexed.
   - During `scan`, reuse the stable ID for the same artifact type and path and append an update event when content, title, status, or bounded metadata changes.
   - Create a new ID only for an explicit semantic replacement: pass a new `--id`, or use `add --replace`. Supersede and cross-link the previous active same-path record in the same locked transaction.
   - Do not infer semantic replacement from an ordinary digest change. This prevents `scan` from creating `duplicate_active_path` debt itself.
   - Treat `.task/task_pack/*.json` as canonical pack state and a same-stem Markdown file as its render only. During an ordinary scan, append a `superseded` correction for a legacy non-closed `task_pack` identity that points at the render while the canonical JSON is discovered; never delete either file or silently rewrite history.
   - Preserve an exact same-digest `task.md` mutable alias in `complete` or `completed` state as current but non-executable. Do not infer bounded completion from `blocked`, `terminal_blocked`, or `deferred`; those states require their existing explicit owner transition. Do not normalize a completed alias back to `active`. At every scan or direct upsert entrypoint, reject a changed body or executable status under that completed ID and require the existing explicit lifecycle-switch transaction with a distinct successor identity.
   - Use `scan --dry-run` for a read-only publication plan. It must not create `.task/`, acquire a writer lock, append events, create snapshots, or rewrite the Markdown view. Use `scan --check` for the same read-only plan with exit code `1` when applying `scan` would change durable task-state files and `0` otherwise.
   - A mutating `scan` must first complete the same read-only identity/collision plan for the full discovered inventory and recheck source hashes before its first append. Do not commit an earlier artifact when a later discovered artifact has a deterministic canonical-ID/path collision.
   - A normal `scan` regenerates `.task/index.md` only when its rendered projection changes. An exact projection match preserves the existing `Generated` value, bytes, and modification time; a missing or stale view is repaired without appending a ledger event when the JSONL projection itself is already current.
   - When a caller restricts indexing to exact-path add/link, record that restriction in the created/updated artifact note and include the reason global scan/audit was skipped.

     ```bash
     PYTHONPATH="${CODEX_HOME:-$HOME/.codex}/skills/manage-task-state-index/scripts:${CODEX_HOME:-$HOME/.codex}/skills/record-agent-work-log/scripts" \
     python3 -P -m manage_task_state_index index --root . scan
     PYTHONPATH="${CODEX_HOME:-$HOME/.codex}/skills/manage-task-state-index/scripts:${CODEX_HOME:-$HOME/.codex}/skills/record-agent-work-log/scripts" \
     python3 -P -m manage_task_state_index index --root . scan --check
     ```

3. Add or update a specific artifact when another workflow creates it.
   - Add the new artifact immediately after the owning workflow writes it.
   - Include the artifact type, path, status, concise title, parent ID when relevant, and relationship links.
   - Before adding a timestamped log or miss artifact, check whether an existing indexed artifact has the same type, task parent, canonical result path/check path, status, and content digest. If so, reuse/link the existing artifact rather than creating duplicate lifecycle meaning.

     ```bash
     PYTHONPATH="${CODEX_HOME:-$HOME/.codex}/skills/manage-task-state-index/scripts:${CODEX_HOME:-$HOME/.codex}/skills/record-agent-work-log/scripts" \
     python3 -P -m manage_task_state_index index --root . add \
       --type task \
       --path task.md \
       --status active \
       --title "Implement current task"
     ```

4. Link related artifacts.
   - Link the active task to the selected candidate, archived `past_task`, audit logs, execution logs, validation reports, and task_miss reports.
   - Link the active task to the task-pack item that supplied it with `promoted_from_pack` or `pack_for_task` when `.task/task_pack` is in scope.
   - Link implementation issues to active tasks, candidates, task_miss reports, validation reports, run logs, worktree/branch handoff records, and closing evidence.
   - Link external advice to tasks, candidates, schema/design notes, validations, or logs when advice was considered, incorporated, rejected, deferred, or retired.
   - Link schema contracts and schema maps to tasks, candidates, task_miss reports, goal artifacts, modules, scripts, and audits when known.
   - Use relationship names such as `derived_from`, `promoted_from_pack`, `pack_for_task`, `inserted_after`, `reordered_by`, `terminal_blocker_for`, `input_delta_for`, `consolidation_candidate_for`, `supersedes`, `produced`, `audit_for`, `run_for`, `miss_for`, `resolves`, `validates`, `issue_for`, `tracks_task`, `derived_from_issue`, `fixes_issue`, `closes_issue`, `resolved_by`, `worktree_for`, `branch_for`, `advice_for`, `incorporated_into`, `applied_by`, `rejected_by`, `superseded_by`, `conflicts_with_goal`, `conflicts_with_authority`, `contract_for`, `schema_for`, `module_contract_for`, `script_contract_for`, `depends_on`, `produces_schema`, `consumes_schema`, `compatible_with`, `breaks_contract`, and `supersedes_contract`.

     ```bash
     PYTHONPATH="${CODEX_HOME:-$HOME/.codex}/skills/manage-task-state-index/scripts:${CODEX_HOME:-$HOME/.codex}/skills/record-agent-work-log/scripts" \
     python3 -P -m manage_task_state_index index --root . link \
       --source-id task-20260522-213000-example \
       --link produced:miss-20260522-214000-generalization-gap
     ```

5. Record lifecycle transitions before destructive cleanup.
- Treat mutable aliases such as `task.md` separately from immutable task/advice/validation snapshots. Persist the alias body under `.task/snapshots/<canonical-id>.<ext>` when the canonical ID is first indexed. A historical record is checked only against its own `snapshot_path` and immutable snapshot digest; a later alias body must not create historical digest mismatch debt.
- Allow the current alias to point at a bounded-complete task even when no executable successor exists and global readiness is blocked or waiting. Such an alias is current history, not an active selector candidate. Preserve its immutable snapshot and lifecycle verdict; a later successor must use the active-switch transaction and a distinct canonical ID.
- For an active switch, perform and report one `lifecycle_transition_result` in this order: preserve the previous immutable snapshot, supersede the previous active canonical ID, add the new canonical ID, update the mutable alias, update links, then render the index. A partial sequence is not a completed switch.
- When an active switch or another caller-owned decision projects across authority, canonical task, and task index surfaces, extend that existing result with optional `state_projection`: one opaque `projection_epoch`, `source_decision_id`, per-surface digests, per-surface epoch echoes, and `projection_status: current|stale_projection|not_evaluated|conflict`. Ordinary index-only scans do not require it. The index owner stores and checks caller-supplied bindings; it does not mint authority or reinterpret the decision.
- Bind any retained/effective change role to the existing artifact `content_sha256` and a durable evidence link/reference with a full digest. A title, note, task message, producer label, or caller self-classification without retained bytes/evidence remains unverified governance metadata and must not be promoted to implementation or semantic change. When the digest-bound artifact and its independent role evidence agree, preserve the supplied bounded role without turning index retention itself into progress.
- A positive cross-surface transition requires all three epoch echoes to equal `projection_epoch` and every supplied digest to be a full hash. Any stale/missing surface is projection repair work, not a reason to ask the user to repeat an already identified source decision. Ask for user input only when the source decision itself is absent or ambiguous. Missing or malformed optional projection data fails quiet for unrelated scans but cannot authorize the dependent transition, execution, close, or promotion.
- A caller that starts such a dependent transition emits `state_projection_required: true` before applying it. Set `authority_projection_applied`, `task_projection_applied`, or `task_index_projection_applied` only after the corresponding surface has been projected from the same source decision; those booleans never substitute for the receipt. A required receipt that is absent, malformed, stale, or conflicting blocks only the dependent transition while unrelated index operations retain their existing behavior.
- Before deleting an applied candidate, mark it `applied` and link it to the active task.
- Before superseding, completing, or terminal-blocking a task pack, index the task-pack JSON and link the evidence with `reordered_by`, `terminal_blocker_for`, or `input_delta_for` as applicable.
- Before deleting a resolved task miss, mark it `resolved` or `deleted` and link the evidence report.
- Before closing, archiving, or deleting a local issue record, mark it `resolved`, `closed`, or `archived` and link the run/validation evidence through `$manage-implementation-issues`.
- Before moving advice to applied or rejected, ensure `$manage-external-advice` writes the lifecycle event and any `past_advice` log; this skill may index and link the resulting artifacts but does not decide advice application.
- Before replacing `task.md`, ensure the previous content has a `past-*` or `log-*` record linked from the new task.

6. Run global ID consistency audit.
   - Run the deterministic audit whenever a workflow is about to claim completion, delete an artifact, resolve a miss, publish an audit, or replace `task.md`.
   - Use this command for a non-mutating audit:

     ```bash
     PYTHONPATH="${CODEX_HOME:-$HOME/.codex}/skills/manage-task-state-index/scripts:${CODEX_HOME:-$HOME/.codex}/skills/record-agent-work-log/scripts" \
     python3 -P -m manage_task_state_index index --root . audit
     ```

   - Use this command when the audit itself should become a durable artifact:

     ```bash
     PYTHONPATH="${CODEX_HOME:-$HOME/.codex}/skills/manage-task-state-index/scripts:${CODEX_HOME:-$HOME/.codex}/skills/record-agent-work-log/scripts" \
     python3 -P -m manage_task_state_index index --root . audit --write-report
     ```

   - Use `audit --summary-only --focus-path <path>` for cycle reports that need global counts and current-surface issues without dumping unrelated historical debt. The summary output is not a replacement for full audit evidence when deletion, issue closure, or completion depends on global consistency.
   - Split `current_surface_blockers` from `historical_debt`. For completion-oriented close, block on a missing current canonical ID, duplicate active alias, or broken current link. Missing paths, stale alias digests, or links belonging only to inactive immutable history remain historical debt and do not block the current surface by themselves.
   - If several consecutive cycles used exact-path-only add/link instead of global scan/audit, recommend a global audit before the next completion claim, candidate deletion, issue closure, readiness promotion, or commit that changes workflow state.
   - When cycle/profile evidence reports over-threshold run directories, processed candidates, versioned command families, or repeated exact-path-only state mutations, register or link a consolidation candidate instead of recording the growth as informational only. Mark that candidate or index note as `progress_kind: governance_only` unless strict changed-and-semantic primary-output evidence proves otherwise. Use `consolidation_candidate_for`, `supersedes`, or `depends_on` links to tie the candidate to the budget evidence.
   - If no `.task`, `.issue`, `.agent_log`, `.agent_goal`, `.agent_advice`, `.interview`, `.schema`, `.contract`, or task artifact exists, do not force an ID workflow; report that no ID context was available and let the calling skill continue its original purpose.

7. Optionally request additional ID insight from a dedicated agent.
   - Use one separate read-only ID insight agent only when the calling workflow already authorizes agents or the user explicitly asks for ID/governance audit.
   - Spawn or request this ID insight agent with Tier 2 `requested_model_ref: model_ref:balanced` and fixed `requested_reasoning_effort: medium`.
   - This agent is additional; never count it as one of the existing implementation, inspection, question, review, or synthesis agents.
   - Give the agent `.task/index.md`, the deterministic `audit` JSON, and relevant artifact paths only. Do not assign repo implementation, OOM analysis, env discovery, prompt shaping, or task synthesis to it.
   - The agent may suggest missing links, stale IDs, duplicate lifecycle records, parent/child relationship corrections, and candidate/miss cleanup risks. The main agent owns all writes.
   - Use [id-agent-prompts.md](references/id-agent-prompts.md) for prompt shape.

8. Report the index state.
   - Include the updated `.task/index.md` path and the important IDs in the user-facing summary.
   - Report `agent_routing_applicability: deterministic_only` when no ID agent ran. When one ran, include its Tier 2 profile, requested model reference, model-configuration status, requested model/effort when resolved, reason codes, and routing enforcement or limitation.
   - If an artifact could not be linked because its producing workflow did not leave a durable file, record that as a note rather than inventing evidence.

## Script Commands

Use `python3 -P -m manage_task_state_index index` for deterministic updates:

- `init`: create `.task/index.jsonl` if needed and rebuild `.task/index.md`.
- `scan`: discover standard artifacts, append missing or changed index events, and publish the Markdown view only when its projection changes. Add `--dry-run` for a zero-write plan or `--check` for the same plan with CI-friendly `0`/`1` exit status.
- `add`: append or update one artifact event; use `--replace` or a new explicit `--id` only for semantic replacement.
- `link`: append a relationship from one indexed artifact to another.
- `rebuild`: regenerate `.task/index.md` from `.task/index.jsonl`.
- `audit`: inspect global ID consistency, broken links, duplicate active paths, stale digests, missing files, active task conflicts, and unindexed standard artifacts. Without `--write-report`, it shares an existing lock or verifies a stable lockless snapshot and creates no `.task` or lock. Add `--write-report` to write `.task/id_audit/*.md` and index it as `audit-*`. Add `--summary-only --focus-path <path>` to emit compact counts and focused issues for report packets.
- `compile-transition`: compile a closed compact lifecycle intent into the existing event-batch request without writing task state. It derives artifact identity and digests from current workspace/index bytes and fails with `recompile_required` on stale state.
- `prepare-scan` / `apply-scan`: canonical schema-v2 path; `lint-owner-result`: bounded pre-consumption check. Schema v1 is historical-only.
- `plan-transition`: build one content-bound event batch from the preferred `--intent <json-or-path>` plus explicit `--at`. The full `--request-json <json-or-path>` surface is legacy compatibility/contract diagnostics only and must not be used to make a coordinator author event arrays. Schema-v1 requests use ordinary current/expected anchors. Schema-v2 is reserved for selected-successor external settlement and requires an exact prospective `task.md` source plus `external_settlement_kind: selection_publication`. Markdown rendering is mandatory. Use `--dry-run` for a zero-write plan or omit it to immutably publish reversible, non-canonical workflow metadata at the sole canonical `.task/transition_plans/<plan-id>.json` path. If `--output` is supplied it must equal that path exactly; aliases are rejected because intent and receipt sidecars are keyed by `plan_id`. This prepare operation is authority-free; it cannot authorize `apply-plan`.
- `verify-plan`: read-only verify the immutable plan digest, event bindings, ledger/Markdown/artifact CAS anchors, exact replay state, and receipt consistency. Use `--phase planning` before dependency owners publish prospective artifacts: ledger/Markdown must still match the plan prestate and every artifact must match `before_sha256`. Use `--phase apply` after dependencies finish: the same ledger/Markdown prestate must hold and artifacts must match `expected_sha256`. Do not emulate this distinction by ignoring artifact defects.
- `apply-plan`: under `.task/index.lock`, CAS-apply every planned task/archive/supersede/advice/task-pack link event as one append batch and render once. Apply remains the separately authorized `mutate_task_state_index` operation. For schema v1 it publishes the settled apply receipt. For schema v2 require the exact selection-publication prepare through `--external-prepare-ref|sha256`, keep `task.md` at its before digest, and publish `activation_status: pending_external_settlement` under `.task/transition_pending_receipts/`; every normal writer remains blocked on that unfinished lifecycle. Exact replay appends zero events and returns the same pending or settled state.
- `settle-plan-external`: for one schema-v2 plan, reopen its pending receipt and the exact committed schema-v3 selection-publication receipt, verify that publication wrote the prospective bytes to `task.md` and bound the same prepare/plan, then publish the settled schema-v2 apply receipt. Replay returns `already_settled`. The result alone opens `selection_consumption_allowed`; it cannot select another publication or serve as a new authority source.
- `settle-plan-no-effect`: close one stale plan that has no plan-tagged event, no pending intent, and no apply receipt. It publishes an immutable plan/file-bound no-effect receipt only when apply-time CAS is no longer current. A still-applicable plan, partial or ambiguous intent, any observed plan effect, conflicting receipt, or unsafe owned path fails closed. Replay returns the original receipt. This supporting settlement record can release the existing reservation; it is not canonical index mutation, a new authority source, or permission to apply a replacement plan.

For task switches or other multi-artifact lifecycle projections, prefer the immutable `task_index_transition_plan` as the authority subject. The legacy `task_index` subject remains accepted for existing direct `scan|add|link|rebuild` callers. Apply results expose `execution_result_binding: {ref, sha256}` whose SHA-256 is the exact receipt file digest; `plan_sha256` and `receipt_content_sha256` are canonical body digests and must not be substituted for the exact `plan_file_sha256` or `receipt_file_sha256` bindings.

Example:

```bash
PYTHONPATH="${CODEX_HOME:-$HOME/.codex}/skills/manage-task-state-index/scripts:${CODEX_HOME:-$HOME/.codex}/skills/record-agent-work-log/scripts" \
python3 -P -m manage_task_state_index index --root . plan-transition \
  --intent transition-intent.json \
  --at 2026-01-01T00:00:00Z
PYTHONPATH="${CODEX_HOME:-$HOME/.codex}/skills/manage-task-state-index/scripts:${CODEX_HOME:-$HOME/.codex}/skills/record-agent-work-log/scripts" \
python3 -P -m manage_task_state_index index --root . verify-plan \
  --phase planning \
  --plan .task/transition_plans/<plan-id>.json
PYTHONPATH="${CODEX_HOME:-$HOME/.codex}/skills/manage-task-state-index/scripts:${CODEX_HOME:-$HOME/.codex}/skills/record-agent-work-log/scripts" \
python3 -P -m manage_task_state_index index --root . verify-plan \
  --phase apply \
  --plan .task/transition_plans/<plan-id>.json
PYTHONPATH="${CODEX_HOME:-$HOME/.codex}/skills/manage-task-state-index/scripts:${CODEX_HOME:-$HOME/.codex}/skills/record-agent-work-log/scripts" \
python3 -P -m manage_task_state_index index --root . apply-plan \
  --plan .task/transition_plans/<plan-id>.json
```

For a selected successor, orchestration callers must use
`orchestrate_task_cycle selected-successor execute|recover`; that guarded driver
issues one exact lease per effect and revalidates all three current pre-commits at each
owner boundary. Lower commands are historical-recovery diagnostics, never a first-effect
route:

```bash
python3 -P -m manage_task_state_index index --root . apply-plan \
  --plan .task/transition_plans/<plan-id>.json \
  --external-prepare-ref <publication-prepare-ref> \
  --external-prepare-sha256 <publication-prepare-raw-sha256>
python3 -P -m manage_task_state_index index --root . settle-plan-external \
  --plan .task/transition_plans/<plan-id>.json \
  --external-commit-ref <publication-receipt-ref> \
  --external-commit-sha256 <publication-receipt-raw-sha256>
```

If a foreign index write or a genuinely foreign artifact digest makes that exact plan stale before its intent is published, do not request the same semantic approval again. Verify `plan_effect_observed: false`, `plan_intent_observed: false`, and `no_effect_eligible: true`; publish the exact no-effect receipt; release the old reservation against that receipt; then prepare a new exact plan from the unchanged source decision. Artifacts that are all still at `before_sha256`, all at `expected_sha256`, or partially moving only between those two states are normal dependency states (`ready` or `materializing`), never no-effect. Only a changed semantic subject, effect, risk, or exclusion requires another user decision.

Use `python3 -P -m manage_task_state_index migrate` only for the bounded `inspect` and `migrate plan|apply|validate|recover` transaction documented in [legacy-migration.md](references/legacy-migration.md). `plan` and `apply --dry-run` must leave canonical `.task` state unchanged. Never use migration as a general malformed-row ignore mode.

Use `python3 -P -m manage_task_state_index verify-migration` only to verify a committed receipt with an external exact mapping manifest and caller-owned recovery expectation. It emits safe scalar, bounded opaque identity, evidence-ref, count, digest, and status evidence, with separate migration-boundary and current task/pack surfaces; failures expose only an allowlisted error code. A fixture recovery pass requires an exact, fully graph-bound pre-recovery observation and a phase-specific before/after transition; a path-name allowlist alone is not recovery ownership evidence. The verifier proves physical source separation, while the governing cycle must separately attest who selected the external expectation because equal bytes cannot prove human ownership. The verifier must not mutate the ledger, projection, transaction, task, pack, or local bytecode cache. Issue state and cycle-wide live-operation counts require external cycle evidence rather than relocated-fixture constants.

Successful commands print JSON so the caller can capture IDs and changed paths.
Contract or safety failures exit nonzero and may use concise stderr text; callers
must treat the exit status, not stdout shape, as the failure boundary.

All writers serialize through workspace-local `.task/index.lock`, validate the existing JSONL before mutation, and atomically replace changed `index.jsonl` and Markdown payloads after durable flush. Read-only `scan --dry-run|--check` does not enter this writer path. New events carry `format_version` and `schema_version`. Detect legacy versions before validating the current event discriminator and normalize only unambiguous legacy upsert/link shapes at read time. During audit, quarantine malformed rows, continue scanning valid rows, and classify their current-projection impact as `independent`, `affected`, or `unknown`; keep affected or unknown current identities `not_evaluated`. Keep mutation paths strict: malformed or future-version JSONL fails closed without append. An empty scan/audit is `not_evaluated_no_artifacts`, not success or completion evidence.

## Guardrails

- Do not use the index as proof that work is complete; use `$validate-task-completion` for verdicts.
- Do not delete, move, or rewrite task artifacts from this skill unless the user or owning workflow explicitly requested it.
- Do not overwrite `.task/index.jsonl`.
- Do not dispatch a plan after `settled_no_effect`. Do not accept `stale`, the plan file, or arbitrary JSON as no-effect evidence. Require `status: settled_no_effect`, `no_effect_verified: true`, both observed activity flags false, and the exact no-effect receipt file binding.
- Do not change `task.md` before applying a schema-v2 prospective plan, and do not treat its pending receipt as active task state. Require the exact committed publication receipt and `settle-plan-external` before selection consumption or terminal-wait retirement.
- Do not compare an immutable historical snapshot digest with the current mutable alias body. Store `record_class: mutable_alias|immutable_snapshot`, `snapshot_digest`, and `canonical_id` in the existing event `fields` when applicable.
- Do not remove historical events from `.task/index.jsonl`; append a correcting event instead.
- Do not store secrets, private tokens, raw sensitive data, or large copyrighted excerpts in index fields.
- Do not store full schema payloads or large contract bodies in index fields; store paths, titles, statuses, versions, and concise relationship fields.
- Do not treat `.agent_goal/goal_schema_contract.md` as a schema contract body. Index it as a `goal-*` artifact; index the `.schema/` and `.contract/` files that implement it as `schema-*` or `schema-map-*`.
- Do not treat `.agent_advice` as `.agent_goal` GT. Index advice as `external_advice` with `adv-*` IDs and non-GT lifecycle links.
- Do not mark a task_miss resolved without evidence from `$task-md-agent-governance`, `$inspect-repo-with-agents`, or `$validate-task-completion`.
- Do not mark an issue closed or resolved without evidence from `$manage-implementation-issues`, `$run-task-code-and-log`, or `$validate-task-completion`.
- Do not make a generic skill fail only because no ID context exists; ID management is best-effort unless the user explicitly requested an ID audit or completion validation.
- Do not treat a fresh authority surface plus stale task/index projections as a new authority question. Preserve the source decision and repair its projections first.
- Do not let an ID insight agent edit files or perform the owning workflow's normal analysis; it is an additional traceability reviewer only.
- Do not run optional ID insight agents with any reasoning effort other than `medium` when the tooling exposes `reasoning_effort`.
- Do not use `ultra` for an ID agent.
- Do not let exact-path-only indexing become an implicit proof of global consistency. Exact-path updates are allowed for safety-scoped cycles, but completion claims must state whether global audit was run, deferred, or intentionally skipped.
