---
name: manage-task-state-index
description: "Maintain workspace `.task/index.md` and `.task/index.jsonl` as a durable task-state index using deterministic helpers first and Tier 2 `model_ref:balanced`/medium only for optional ID insight or delegated ID correction. Use when Codex creates, updates, promotes, archives, resolves, deletes, audits, validates, or needs global ID consistency across task, issue, goal, advice, schema-contract, execution, and validation workflows."
---

# Manage Task State Index

## Overview

Use this skill to keep one workspace-local task lifecycle index under `.task/`. The canonical record is append-only `.task/index.jsonl`; the human-readable view is `.task/index.md`.

This skill records traceability only. It does not decide task completion, delete artifacts, or replace the source workflows that create `task.md`, candidate tasks, implementation issues, task misses, execution logs, goal/interview outputs, or audit logs.

## Routing Policy

- When called from `$orchestrate-task-cycle`, consume the canonical orchestration reference [workflow-routing.md](../orchestrate-task-cycle/references/workflow-routing.md) as caller context, but keep this skill's fixed ID-only routing below.
- Run deterministic scan/audit/render helpers without assigning a model. When an optional ID insight or delegated ID correction agent is needed, request Tier 2 `model_ref: model_ref:balanced` with `reasoning_effort: medium` under `configured-tiered-routing-v3`.
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

For an explicitly authorized malformed/legacy-ledger migration, read [legacy-migration.md](references/legacy-migration.md) and use `scripts/task_state_migration.py`. Keep repository-specific mappings outside the helper, preserve the source as a byte-identical sealed prefix, and require its committed receipt before normal mutation readers consume any quarantined prefix row. Review every observed token exactly: reject a mapping builder that uses prefix, substring, suffix, regex, or wildcard logic to decide lifecycle meaning even when its emitted JSON keys are exact tokens. Require `mapping_method: exact_token_review` and `pattern_inference_used: false`. Current migration plan, resolution-manifest, and receipt schema version 2 also requires lock-time safe task/pack anchor revalidation, exact original-token/reason preservation for mapped event/status/type values, correction ID/SHA bindings for every non-independent quarantine, a hash-bound final journal, and an immutable completion marker. Missing or tampered v2 bindings keep `scan|add|link|rebuild|audit` fail-closed.

Use `scripts/task_state_migration_verifier.py` when a committed migration needs source-separated completion evidence. The verifier is read-only, does not import `task_state_migration.py` as truth, and requires a caller-owned exact mapping manifest outside every `.task/migrations` tree that is byte-identical to, but neither the same file nor a hard link to, the published snapshot. It independently recomputes the sealed graph and reports immutable migration-boundary task/pack IDs and evidence refs separately from legitimate current-tail task/pack IDs and evidence refs. Its recovery evidence is limited to externally hash-bound observations over synthetic or copied fixtures: bind every observation field into the verification graph, prove the exact phase-specific owned transition, require the live projection and protected task/pack artifacts to be unchanged except for the phase's exact authorized publication, and never use verification to apply, recover, or replay the live ledger. See [Independent verifier](references/legacy-migration.md#independent-verifier).

Validation artifacts may also record a separate progress status such as `advanced`, `safety_only`, `no_progress`, or `regressed` in their title, links, or concise metadata. Do not treat progress status as a replacement for validation status.

For the complete event schema and link relationship names, read [index-schema.md](references/index-schema.md).

## Workflow

1. Initialize or refresh the index.
   - Create `.task/` if missing.
   - Preserve existing `.task/index.jsonl`; never truncate it.
   - Regenerate `.task/index.md` from JSONL whenever state changes.
   - Prefer the bundled script:

     ```bash
     python3 "${CODEX_HOME:-$HOME/.codex}/skills/manage-task-state-index/scripts/task_state_index.py" --root . init
     ```

2. Discover current artifacts.
   - Scan for `task.md`, `.task/candidate_task/*.md`, `.task/task_pack/*.json`, `.task/task_miss/**/*.md`, `.task/validation/*.md`, `.task/id_audit/*.md`, `.issue/**/*.md`, integrity-verified `.agent_log/**/*.md`, `.agent_goal/*.md`, `.agent_advice/**/*.md`, `.interview/**/*.md`, `.schema/` schema/contract/map artifacts, and `.contract/` auxiliary contract/map artifacts. Reject unsafe/invalid agent-log stores through the shared `$record-agent-work-log` inspector instead of following symlinks or indexing tampered/orphan bodies.
   - Assign IDs to artifacts that are not already indexed.
   - During `scan`, reuse the stable ID for the same artifact type and path and append an update event when content, title, status, or bounded metadata changes.
   - Create a new ID only for an explicit semantic replacement: pass a new `--id`, or use `add --replace`. Supersede and cross-link the previous active same-path record in the same locked transaction.
   - Do not infer semantic replacement from an ordinary digest change. This prevents `scan` from creating `duplicate_active_path` debt itself.
   - Preserve an exact same-digest `task.md` mutable alias in `complete` or `completed` state as current but non-executable. Do not infer bounded completion from `blocked`, `terminal_blocked`, or `deferred`; those states require their existing explicit owner transition. Do not normalize a completed alias back to `active`. At every scan or direct upsert entrypoint, reject a changed body or executable status under that completed ID and require the existing explicit lifecycle-switch transaction with a distinct successor identity.
   - Use `scan --dry-run` for a read-only publication plan. It must not create `.task/`, acquire a writer lock, append events, create snapshots, or rewrite the Markdown view. Use `scan --check` for the same read-only plan with exit code `1` when applying `scan` would change durable task-state files and `0` otherwise.
   - A mutating `scan` must first complete the same read-only identity/collision plan for the full discovered inventory and recheck source hashes before its first append. Do not commit an earlier artifact when a later discovered artifact has a deterministic canonical-ID/path collision.
   - A normal `scan` regenerates `.task/index.md` only when its rendered projection changes. An exact projection match preserves the existing `Generated` value, bytes, and modification time; a missing or stale view is repaired without appending a ledger event when the JSONL projection itself is already current.
   - When a caller restricts indexing to exact-path add/link, record that restriction in the created/updated artifact note and include the reason global scan/audit was skipped.

     ```bash
     python3 "${CODEX_HOME:-$HOME/.codex}/skills/manage-task-state-index/scripts/task_state_index.py" --root . scan
     python3 "${CODEX_HOME:-$HOME/.codex}/skills/manage-task-state-index/scripts/task_state_index.py" --root . scan --check
     ```

3. Add or update a specific artifact when another workflow creates it.
   - Add the new artifact immediately after the owning workflow writes it.
   - Include the artifact type, path, status, concise title, parent ID when relevant, and relationship links.
   - Before adding a timestamped log or miss artifact, check whether an existing indexed artifact has the same type, task parent, canonical result path/check path, status, and content digest. If so, reuse/link the existing artifact rather than creating duplicate lifecycle meaning.

     ```bash
     python3 "${CODEX_HOME:-$HOME/.codex}/skills/manage-task-state-index/scripts/task_state_index.py" --root . add \
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
     python3 "${CODEX_HOME:-$HOME/.codex}/skills/manage-task-state-index/scripts/task_state_index.py" --root . link \
       --source-id task-20260522-213000-example \
       --link produced:miss-20260522-214000-generalization-gap
     ```

5. Record lifecycle transitions before destructive cleanup.
- Treat mutable aliases such as `task.md` separately from immutable task/advice/validation snapshots. Persist the alias body under `.task/snapshots/<canonical-id>.<ext>` when the canonical ID is first indexed. A historical record is checked only against its own `snapshot_path` and immutable snapshot digest; a later alias body must not create historical digest mismatch debt.
- Allow the current alias to point at a bounded-complete task even when no executable successor exists and global readiness is blocked or waiting. Such an alias is current history, not an active selector candidate. Preserve its immutable snapshot and lifecycle verdict; a later successor must use the active-switch transaction and a distinct canonical ID.
- For an active switch, perform and report one `lifecycle_transition_result` in this order: preserve the previous immutable snapshot, supersede the previous active canonical ID, add the new canonical ID, update the mutable alias, update links, then render the index. A partial sequence is not a completed switch.
- When an active switch or another caller-owned decision projects across authority, canonical task, and task index surfaces, extend that existing result with optional `state_projection`: one opaque `projection_epoch`, `source_decision_id`, per-surface digests, per-surface epoch echoes, and `projection_status: current|stale_projection|not_evaluated|conflict`. Ordinary index-only scans do not require it. The index owner stores and checks caller-supplied bindings; it does not mint authority or reinterpret the decision.
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
     python3 "${CODEX_HOME:-$HOME/.codex}/skills/manage-task-state-index/scripts/task_state_index.py" --root . audit
     ```

   - Use this command when the audit itself should become a durable artifact:

     ```bash
     python3 "${CODEX_HOME:-$HOME/.codex}/skills/manage-task-state-index/scripts/task_state_index.py" --root . audit --write-report
     ```

   - Use `audit --summary-only --focus-path <path>` for cycle reports that need global counts and current-surface issues without dumping unrelated historical debt. The summary output is not a replacement for full audit evidence when deletion, issue closure, or completion depends on global consistency.
   - Split `current_surface_blockers` from `historical_debt`. For completion-oriented close, block on a missing current canonical ID, duplicate active alias, or broken current link. Missing paths, stale alias digests, or links belonging only to inactive immutable history remain historical debt and do not block the current surface by themselves.
   - If several consecutive cycles used exact-path-only add/link instead of global scan/audit, recommend a global audit before the next completion claim, candidate deletion, issue closure, readiness promotion, or commit that changes workflow state.
   - When cycle/profile evidence reports over-threshold run directories, processed candidates, versioned command families, or repeated exact-path-only state mutations, register or link a consolidation candidate instead of recording the growth as informational only. Mark that candidate or index note as `progress_kind: governance_only` unless strict changed-and-semantic primary-output evidence proves otherwise. Use `consolidation_candidate_for`, `supersedes`, or `depends_on` links to tie the candidate to the budget evidence.
   - If no `.task`, `.issue`, `.agent_log`, `.agent_goal`, `.agent_advice`, `.interview`, `.schema`, `.contract`, or task artifact exists, do not force an ID workflow; report that no ID context was available and let the calling skill continue its original purpose.

7. Optionally request additional ID insight from a dedicated agent.
   - Use one separate read-only ID insight agent only when the calling workflow already authorizes agents or the user explicitly asks for ID/governance audit.
   - Spawn or request this ID insight agent with Tier 2 `model_ref: model_ref:balanced` and fixed `reasoning_effort: medium`.
   - This agent is additional; never count it as one of the existing implementation, inspection, question, review, or synthesis agents.
   - Give the agent `.task/index.md`, the deterministic `audit` JSON, and relevant artifact paths only. Do not assign repo implementation, OOM analysis, env discovery, prompt shaping, or task synthesis to it.
   - The agent may suggest missing links, stale IDs, duplicate lifecycle records, parent/child relationship corrections, and candidate/miss cleanup risks. The main agent owns all writes.
   - Use [id-agent-prompts.md](references/id-agent-prompts.md) for prompt shape.

8. Report the index state.
   - Include the updated `.task/index.md` path and the important IDs in the user-facing summary.
   - Report `agent_routing_applicability: deterministic_only` when no ID agent ran. When one ran, include its Tier 2 profile, requested model reference, model-configuration status, requested model/effort when resolved, reason codes, and routing enforcement or limitation.
   - If an artifact could not be linked because its producing workflow did not leave a durable file, record that as a note rather than inventing evidence.

## Script Commands

Use `scripts/task_state_index.py` for deterministic updates:

- `init`: create `.task/index.jsonl` if needed and rebuild `.task/index.md`.
- `scan`: discover standard artifacts, append missing or changed index events, and publish the Markdown view only when its projection changes. Add `--dry-run` for a zero-write plan or `--check` for the same plan with CI-friendly `0`/`1` exit status.
- `add`: append or update one artifact event; use `--replace` or a new explicit `--id` only for semantic replacement.
- `link`: append a relationship from one indexed artifact to another.
- `rebuild`: regenerate `.task/index.md` from `.task/index.jsonl`.
- `audit`: inspect global ID consistency, broken links, duplicate active paths, stale digests, missing files, active task conflicts, and unindexed standard artifacts. Add `--write-report` to write `.task/id_audit/*.md` and index it as `audit-*`. Add `--summary-only --focus-path <path>` to emit compact counts and focused issues for report packets.

Use `scripts/task_state_migration.py` only for the bounded `inspect` and `migrate plan|apply|validate|recover` transaction documented in [legacy-migration.md](references/legacy-migration.md). `plan` and `apply --dry-run` must leave canonical `.task` state unchanged. Never use migration as a general malformed-row ignore mode.

Use `scripts/task_state_migration_verifier.py` only to verify a committed receipt with an external exact mapping manifest and caller-owned recovery expectation. It emits safe scalar, bounded opaque identity, evidence-ref, count, digest, and status evidence, with separate migration-boundary and current task/pack surfaces; failures expose only an allowlisted error code. A fixture recovery pass requires an exact, fully graph-bound pre-recovery observation and a phase-specific before/after transition; a path-name allowlist alone is not recovery ownership evidence. The verifier proves physical source separation, while the governing cycle must separately attest who selected the external expectation because equal bytes cannot prove human ownership. The verifier must not mutate the ledger, projection, transaction, task, pack, or local bytecode cache. Issue state and cycle-wide live-operation counts require external cycle evidence rather than relocated-fixture constants.

All commands print JSON so the caller can capture IDs and changed paths.

All writers serialize through workspace-local `.task/index.lock`, validate the existing JSONL before mutation, and atomically replace changed `index.jsonl` and Markdown payloads after durable flush. Read-only `scan --dry-run|--check` does not enter this writer path. New events carry `format_version` and `schema_version`. Detect legacy versions before validating the current event discriminator and normalize only unambiguous legacy upsert/link shapes at read time. During audit, quarantine malformed rows, continue scanning valid rows, and classify their current-projection impact as `independent`, `affected`, or `unknown`; keep affected or unknown current identities `not_evaluated`. Keep mutation paths strict: malformed or future-version JSONL fails closed without append. An empty scan/audit is `not_evaluated_no_artifacts`, not success or completion evidence.

## Guardrails

- Do not use the index as proof that work is complete; use `$validate-task-completion` for verdicts.
- Do not delete, move, or rewrite task artifacts from this skill unless the user or owning workflow explicitly requested it.
- Do not overwrite `.task/index.jsonl`.
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
