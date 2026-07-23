---
name: manage-agent-authority
description: Manage deterministic workspace authority policy, compiler-owned semantic contexts and operation batches, plan-bound root grants, leases, exact operation settlement, exhausted-source recovery recipes, and workflow-aware approval state without expanding active permissions. Use when Codex must summarize or update `.agent_goal/agent_authority.md`; compile authority inputs; prepare or materialize a plan-bound caller approval; distinguish approval from goal truth, risk acceptance, external input, and design choice; evaluate or resolve a versioned operation; reserve, verify, consume, release, or reconcile authority; resume an existing reservation instead of re-prompting; transition a grant; or validate legacy and immutable receipts.
---

# Manage Agent Authority

## Non-negotiable boundary

Treat the active system, developer, user, tool, sandbox, network, and approval constraints as the hard ceiling. Use stored policy and grants only to narrow or clarify that ceiling. Never let a policy, grant, advice file, adapter, receipt, or higher source-rank label create a capability that the active session lacks.

Keep goal truth, authority, evidence, and mutable state separate:

- Store durable goal-level policy in `.agent_goal/agent_authority.md`.
- Store content-addressed policy/source snapshots and immutable grants, decisions, reservations, and receipts under `.task/authorization/`.
- Store only current pointers and usage projections under `.task/authorization/state/`.
- Treat `.agent_advice/active/*.md` as non-GT, non-authority input.
- Preserve historical uncertainty. Never use current ratification to backdate permission.

Read [agent-authority-template.md](references/agent-authority-template.md) before drafting policy. Read [authority-v2-contract.md](references/authority-v2-contract.md) before issuing grants, evaluating operations, delegating, or changing lifecycle state. Read [operation-authority-receipt.md](references/operation-authority-receipt.md) before using the legacy-compatible `receipt` command.

## Authority model

Classify each operation on independent axes:

- Source rank: `S4` platform/session ceiling, `S3` user goal owner, `S2` delegated policy steward, `S1` cycle coordinator, `S0` executor.
- Risk: `R0` observation, `R1` reversible bounded local effect, `R2` consequential bounded effect, `R3` external, sensitive, destructive, goal-changing, or authority-changing effect.
- Decision: `D0` core goal, `D1` bounded design, `D2` task topology, `D3` execution tactic.
- Cardinality: `single_use`, `bounded_reusable`, `task_lease`, `improvement_lease`, or `standing_policy`.

Assign requirements per versioned operation, not per whole skill. Load `authority.operations.json` from the owning skill. Permit runtime classification only to add capabilities or increase risk/mutation/reversibility severity; reject a request that understates its manifest. Fail closed for an unknown mutating operation.

Declare one `authorization_mechanism` per operation. Use `grant` for ordinary governed effects, `typed_source_approval` for grant issuance/composition/transition, `bound_lifecycle_artifact` for delegation and reserve/verify/consume/release, and `none` only when authority is not applicable. This is the bootstrap boundary: authority administration is authorized by its closed source or lifecycle artifact, not by recursively requiring a grant that can only be issued by the same administration path.

Do not merge grants implicitly. Require one active grant to cover the complete capability set, exact subject, exact operation, actor rank, risk, decision class, time window, lease scope, and available use budget. Use an explicit, source-bound composition receipt only when a deliberately approved set of grants must cover the request together.

## Separate decision types

Set exactly one `intent_type` and route it to its actual owner:

- `grant_authority`: evaluate with this skill.
- `ratify_goal_truth`: require goal-owner ratification; a grant is not ratification.
- `accept_risk_or_cost`: require separate risk/cost acceptance; a grant is not consent.
- `supply_external_input`: report availability independently; permission does not create missing data.
- `select_design_option`: require design selection when the autonomy envelope does not already decide it.

Return one closed decision: `allowed`, `approval_required`, `denied`, `waiting_external_input`, `capability_unavailable`, `blocked_by_goal_truth`, `classification_repair`, `conflict`, or `not_applicable`.

Route unsupplyable external input to a local-data alternative, descope, or an explicit external-input limitation. Do not relabel it as a GT blocker or keep converting it into approval work.

## Deterministic workflow

### Use the shared compiler path by default

For every new operation, including a one-operation cycle, publish one cycle-shared
semantic context and one canonical operation set, then compile the batch. The
compiler derives manifest floors, exact subject bindings, versions, IDs, requests,
evaluation contexts, and CAS paths.

```bash
SKILLS_ROOT="${CODEX_HOME:-$HOME/.codex}/skills"
PYTHONPATH="$SKILLS_ROOT/orchestrate-task-cycle/scripts" \
  python3 -P -m orchestrate_task_cycle workflow authority \
  compile-semantic-context --root . \
  --initialization '{"ref":"...","sha256":"..."}' \
  --semantic semantic-context.json

PYTHONPATH="$SKILLS_ROOT/orchestrate-task-cycle/scripts" \
  python3 -P -m orchestrate_task_cycle workflow authority \
  publish-operation-set --root . --operations operation-seeds.json

PYTHONPATH="$SKILLS_ROOT/orchestrate-task-cycle/scripts" \
  python3 -P -m orchestrate_task_cycle workflow authority \
  compile-operation-batch --root . \
  --semantic-context '{"ref":"...","sha256":"..."}' \
  --operation-set '{"ref":"...","sha256":"..."}' \
  --at 2026-01-01T00:00:00Z
```

The following full `compile-operation` seed is historical compatibility and contract
diagnostics only. Do not use it as the normal single-operation path:

```json
{
  "skill_id": "task-doctor",
  "operation_id": "mutate_task_scope",
  "subject": {"ref": "plans/task-transition.json", "revision": "plan-1"},
  "scope": {"cycle_id": "cycle-1", "task_id": "task-1", "pack_id": null},
  "actor_rank": "S0",
  "context": {
    "external_input_status": "not_required",
    "goal_truth_status": "aligned",
    "risk_acceptance_status": "not_required",
    "design_selection_status": "not_required"
  },
  "session_ceiling": {
    "capabilities": ["task.scope.mutate"],
    "risk_ceiling": "R3",
    "mutation_classes": ["local_mutation"],
    "evidence_id": "session-1"
  },
  "goal_autonomy_envelope": {
    "envelope_id": "envelope-1",
    "capabilities": ["task.scope.mutate"],
    "risk_ceiling": "R3",
    "decision_classes": ["D2"],
    "subjects": ["<sha256-of-plans/task-transition.json>"],
    "operations": ["task-doctor:2.2.0:mutate_task_scope:1"],
    "source_ref": ".agent_goal/goal_architecture.md"
  }
}
```

The semantic seed uses the workspace-relative string `source_ref`; the compiler reopens it and derives the final `source_binding`. Omit optional evidence-ref keys when evidence is not required—do not send them as `null`.

For that diagnostic path, invoke `workflow authority compile-operation`; without
`--publish` it emits legacy full JSON, and with `--publish` it returns only
`{ref, sha256, compilation_fingerprint}`. Both forms are preparation only. They
cannot create approval, a grant, reservation, or settlement. Hand-authored full
request/context JSON is historical/diagnostic-only.

Derive cycle and task IDs from the exact canonical cycle `initialization.json`
binding; reject a copied initialization or conflicting caller echo. Keep the semantic
file limited to actor rank, four request-status axes and their evidence refs, actual
session ceiling, and actual goal-autonomy envelope.
Keep each operation-set seed limited to `skill_id`, `operation_id`,
subject/revision, scope, cardinality/budgets, upward-only classification, and optional
composition receipt. Derive both operation versions and fixed
`intent_type=grant_authority` from the current contract. Publish those seeds once and let the batch compiler
accept only the resulting producer-owned operation-set binding. Accept context,
operation set, and batch only from their producer-owned CAS stores; a byte-identical
arbitrary-path copy is not a compiler result. Reuse one context across the cycle. Do
not repeat its full JSON in every operation seed. Operation sets are canonical
order-independent sets: reject duplicates, more than 128 members, or more than
256 KiB of canonical semantic bytes. Re-render every batch compilation from the
bound set, context, timestamp, defaults, classification, and fixed provenance.

For ordinary S3 user root grants, use this order without collapsing boundaries:
preflight the controlling TTY, snapshot and activate the current policy, prepare one
exact plan, invoke the isolated signer, publish its verified outbox candidate, compile
the decision seed, then materialize the plan-bound grant. Run the TTY preflight before
preparing a plan; it must not read a plan, key, registry, or workspace authority
state. Reject any caller-selected stale non-current policy snapshot.

```bash
PYTHONPATH="$SKILLS_ROOT/manage-agent-authority/scripts" \
  python3 -P -m manage_agent_authority.root_authorization_signer preflight-tty

PYTHONPATH="$SKILLS_ROOT/orchestrate-task-cycle/scripts" \
  python3 -P -m orchestrate_task_cycle workflow authority \
  prepare-root-approval \
  --root . --operation-batch '{"ref":"...","sha256":"..."}' \
  --policy-snapshot '{"ref":"...","sha256":"..."}' \
  --grant-semantics root-grant-semantics.json --at 2026-01-01T00:00:00Z

PYTHONPATH="$SKILLS_ROOT/manage-agent-authority/scripts" \
  python3 -P -m manage_agent_authority.root_authorization_signer \
  approve-root-plan --workspace /absolute/workspace/root \
  --approval-plan-ref .task/authorization/root_approval_plans/sha256/<sha>.json \
  --approval-plan-sha256 <sha256> --key-id <key-id>

PYTHONPATH="$SKILLS_ROOT/orchestrate-task-cycle/scripts" \
  python3 -P -m orchestrate_task_cycle workflow authority \
  publish-root-authorization-evidence --root . \
  --evidence <exact-evidence_path-emitted-by-signer>

PYTHONPATH="$SKILLS_ROOT/orchestrate-task-cycle/scripts" \
  python3 -P -m orchestrate_task_cycle workflow authority \
  compile-root-decision-seed --root . \
  --approval-plan '{"ref":"...","sha256":"..."}' \
  --authorization-evidence '{"ref":"...","sha256":"..."}'

PYTHONPATH="$SKILLS_ROOT/orchestrate-task-cycle/scripts" \
  python3 -P -m orchestrate_task_cycle workflow authority \
  materialize-plan-bound-root-grant --root . \
  --approval-plan '{"ref":"...","sha256":"..."}' \
  --decision-seed '{"ref":"...","sha256":"..."}'
```

Require a host/user-signed closed evidence envelope containing `approved=true`, the
exact plan binding, decision time, evidence ID, issuer, key ID, and root-grant
audience. Verify its RSA/SHA-256 signature against an active public key in the
trusted skill-owned `root-authorization.trust.json`, then publish only the verified
bytes through `publish-root-authorization-evidence`. The shipped registry is empty:
until the host or administrator provisions a public key, ordinary root issuance
fails closed. Never accept a caller-selected registry, unsigned scalar approval, or
workspace self-fingerprint as authority.

For host-local key bootstrap, public-key registration, rotation, revocation, or exact
plan signing, read
[root-authorization-host-contract.md](references/root-authorization-host-contract.md).
Invoke only the isolated `root_authority_admin` and `root_authorization_signer`
modules described there. Never add secret-bearing options or expose those modules
through the ordinary authority CLI. Treat agent-managed local custody as a same-OS-
creates a verified outbox candidate, not authority. Require the signer to display
the resolved workspace identity and exact plan binding. Accept only the exact
confirmation phrase from a foreground controlling `/dev/tty`; never normalize
spaces, case, or punctuation and never use stdin or a non-interactive bypass. A TTY
or confirmation failure creates no authority effect. Retry the same unchanged plan
only while it is unexpired; after expiry or binding change, prepare and display a new
plan. Continue to publish, compile, or materialize through the ordinary producer-CAS
commands only when the active task authorizes them.

`compile-root-decision-seed` accepts only the verified evidence CAS binding and exact
plan, derives its schema-v3 compact seed, and emits only an immutable CAS binding.
The materializer
accepts only that producer-CAS binding, reopens and re-renders the plan, never accepts
caller-authored decision JSON or a full projection, and never infers approval. It
derives schema-v5 source approval bytes with
`decision_trust_class=host_user_signed_exact_plan`, one request-bound schema-v3
grant per compilation, snapshots, IDs, paths, hashes, a write-ahead prepare, and the
completion receipt. Every source preserves the exact per-grant projection, including
request digest and task/improvement/session/policy scope. Registration compares a
grant only with its own projection; the aggregate source union never authorizes a
Cartesian-product recombination. Materialization preflights all conflicts before its
first write, stages every grant as `draft`, and recovers an exact interrupted
transaction before reporting all grants active.
The transaction effect API accepts only the exact plan and decision-seed bindings.
Inside the authority lock it boundedly reopens the plan, signed host/user evidence,
and decision seed, re-renders source approval, capability coverage, source binding,
every grant, and the deterministic materialization identity, then reopens the staged
immutable bytes before activation and receipt publication. Never treat an importable
producer-capability object, private helper, or caller-supplied source/grant payload as
that boundary. Receipt visibility independently repeats the signed-chain derivation
under bounded reads and requires exact prepare, source materialization, source
snapshot/metadata, grant bytes, and receipt equality before exposing an active state.
Continue reading schema-v2 and caller-asserted schema-v4 sources as historical
artifacts, but never issue a new grant from either one.
Exact replay of an already registered byte-identical grant remains readable.
The ordinary caller path cannot select `platform_session_ceiling/S4`; S4 needs a
separate platform-owned producer and attestation contract.

For an owner batch renderer such as `selected-successor prepare-authority`, keep
compilation, evaluation, and lifecycle publication separate even when one command
coordinates them. For every new selected-successor batch, accept request/evaluation
contexts only from the exact producer-owned CAS bindings returned by
`selected-successor prepare-authority-context`; a byte-identical arbitrary-path copy,
hand-authored schema-v2 context, or hidden legacy-location flag cannot start new
lifecycle work. That producer validates the caller's complete actual session ceiling
and goal envelope against bundle requirements but never derives or widens either one.
Historical embedded decisions and proofs remain audit/recovery evidence only. Accept
explicit existing grant bindings; never create a source approval or grant. Derive
requests mechanically, but let only the canonical evaluator decide `allowed`. Validate the whole
batch before lifecycle writes. If canonical evaluation finds genuine no-covering
authority or another non-allowed result, return one compact approval projection with
the exact non-authoritative compilation bindings and publish no decision, reservation,
or verification. Treat an absent declaration that evaluates allowed as an input conflict.
After every result is allowed, publish the exact decisions, reserve each operation,
verify `pre_commit`, and expose only a compact packet binding to the executor.
An owner renderer may pass an immutable owner-derived idempotency key through the
Python-only `trusted_request_idempotency_key` compiler argument. Do not expose that
override in the semantic seed or CLI; ordinary compilations retain their derived key.

The required seed shape is closed and intentionally separates derived request facts
from asserted ceilings:

- operation: `skill_id`, `operation_id`, optional matching versions;
- subject/scope: `subject={ref,revision[,kind]}` and
  `scope={cycle_id,task_id,pack_id}` with explicit nulls where inapplicable;
- decision axes: `context={external_input_status,goal_truth_status,
  risk_acceptance_status,design_selection_status}` plus only the corresponding
  evidence refs when resolved;
- actual session assertion: `session_ceiling={capabilities,risk_ceiling,
  mutation_classes,evidence_id}`;
- actual goal assertion: `goal_autonomy_envelope={envelope_id,capabilities,
  risk_ceiling,decision_classes,subjects,operations,source_ref}`.

Read the selected owner's `authority.operations.json` for the exact capability,
operation identity, manifest floors, and allowed enum choices. Hash the current
subject for `subjects`; do not copy request requirements into either ceiling unless
the active session and goal evidence independently establish them. Optional seed
keys cover actor rank, intent/cardinality/use/reservation budgets, upward-only
classification, and composition receipt.

1. Resolve the workspace and current ceiling.
   - Read current instructions and tool/sandbox permissions first.
   - Read `.agent_goal/final_goal.md`, `.agent_goal/conventions.md`, `.agent_goal/agent_authority.md`, and relevant goal theory/architecture when present.
   - Load adapter classifications only as narrowing evidence.

2. Classify the operation.
   - Bind skill/operation IDs and versions, cycle/task/pack/attempt IDs, actor rank, exact subject `{kind, ref, digest, revision}`, namespaced capabilities, effect/data/mutation/reversibility, risk, decision class, requested cardinality/grant budget, per-dispatch `reservation_units`, and idempotency key.
   - Under schema v2, treat `subject.ref` as a workspace-relative existing regular file. Reject a missing, symlinked, or non-regular subject and require its current bytes to match `subject.digest` again before reserve, dispatch, and commit.
   - Require `single_use` budget 1, an exact task ID for `task_lease`, and an exact pack/improvement ID for `improvement_lease`.
   - Build a session ceiling and goal-autonomy envelope. Bind the envelope to exact concept/subject/operation IDs and evidence digest.
   - Keep external-input, GT-alignment, risk-acceptance, and design-selection status explicit.
   - Bind asserted available/missing external input, resolved risk acceptance, and resolved design selection to exact immutable `{ref, sha256}` evidence. Keep the evidence field `null` for unverified, unresolved, or not-required states.

3. Use manual source/grant flows only for historical inspection or producer-specific
   diagnostics. Ordinary new root authority must use the compiler plan path above.

```bash
PYTHONPATH="$SKILLS_ROOT/orchestrate-task-cycle/scripts" \
  python3 -P -m orchestrate_task_cycle workflow authority snapshot-policy \
  --root . --policy-ref .agent_goal/agent_authority.md --expected-version 0

PYTHONPATH="$SKILLS_ROOT/orchestrate-task-cycle/scripts" \
  python3 -P -m orchestrate_task_cycle workflow authority snapshot-source \
  --root . --source-ref .task/authorization/source-id.json
```

`snapshot-source` accepts only a closed producer-verifiable
`authority_source_approval`. Historical schema v2 remains loadable but this command
rejects it. New ordinary roots use schema v5 and
`host_user_signed_exact_plan`; historical caller-asserted schema v4 remains
read-only, and registered recovery producers may retain schema v3.
Before using an S1/S2 source, resolve and rehash its exact higher-rank binding and
prove that every scope and time window only narrows.
For schema v3/v4/v5, reopen and rehash the decision, require a registered root-plan or
recovery-recipe verifier, and prove the exact source-field relationship before
snapshot or grant registration. A generic, missing, or merely self-hashed decision
binding is not approval.

Never use a workspace-authored marker, timestamp, or self-fingerprint to upgrade a
schema-v2 source into prospective authority. Continue reading old v2 artifacts and
evaluating existing grants. Permit only exact idempotent replay of an already
registered grant.

4. Create child delegation and composition only from closed semantic intent.
   - `delegate` accepts a parent grant ID, an explicit time, and only the child
     narrowing fields. The compiler reopens the active parent and derives the parent
     digest/source binding, policy binding, issuer, lineage, grant ID, idempotency
     key, schema envelope, CAS path, and compact result.
   - Keep capabilities, subjects, operations, risk ceiling, decision classes,
     expiry, session/task/improvement scope, cardinality, budget, and holder rank no
     broader than the parent.
   - `compose` accepts a producer-owned operation-batch binding, one exact base
     request digest, exact grant IDs, a prospective producer-verifiable typed source
     binding, and an explicit time. The compiler derives the composition ID,
     idempotency key, request envelope, grant digests, receipt bytes, and CAS path.
   - `register-grant --grant` is sealed to exact replay of an already registered
     grant and cannot publish a missing prospective grant. Raw `delegate --grant`
     and `compose --composition` inputs are not workflow interfaces.

```bash
PYTHONPATH="$SKILLS_ROOT/orchestrate-task-cycle/scripts" \
  python3 -P -m orchestrate_task_cycle workflow authority \
  delegate --root . --parent-grant-id authg-parent \
  --semantics child-delegation-semantics.json --at 2026-01-01T00:00:00Z

PYTHONPATH="$SKILLS_ROOT/orchestrate-task-cycle/scripts" \
  python3 -P -m orchestrate_task_cycle workflow authority \
  compose --root . --operation-batch '{"ref":"...","sha256":"..."}' \
  --request-sha256 <base-request-sha256> \
  --grant-id authg-a --grant-id authg-b \
  --source-approval '{"ref":"...","sha256":"..."}' \
  --at 2026-01-01T00:00:00Z
```

The delegation semantics object contains exactly `holder_rank`, `capabilities`,
`subjects`, `operations`, `risk_ceiling`, `decision_classes`, `cardinality`,
`max_uses`, `expires_at`, `session_id`, `task_id`, and `improvement_id`. It never
contains an artifact kind/schema, grant or lineage ID, parent/source/policy binding,
creation time, or idempotency key.

5. Evaluate and persist the decision.

```bash
PYTHONPATH="$SKILLS_ROOT/orchestrate-task-cycle/scripts" \
  python3 -P -m orchestrate_task_cycle workflow authority evaluate --root . \
  --request request.json --context evaluation-context.json \
  --at 2026-01-01T00:00:00Z
```

Use `effective_authority_fingerprint` for approval-wait wakeup and exact replay. It contains only operation-relevant projections and selected immutable grant/policy bindings. Do not substitute a hash of the mutable whole policy or goal context.

Before prompting, run `authority resolve` or inspect `authority status`. For replayable diagnostics, pass `authority status --at <RFC3339>` and the same `--skills-root` used for evaluation; omission uses the current UTC time and default skills root, and every status result reports `evaluated_at`. Judge both the selected grant and every ancestor against that one time, including `not_before` and `expires_at`, while preserving each raw projection state separately from effective usability. Status inventory is reader-first: always validate every historical decision, reservation, grant/reservation state, and lifecycle receipt as a closed, deterministic, structurally bound, fully settled artifact, but do not make historical decision readability depend on the current operation-manifest digest. Resolve the current manifest separately. A missing, changed, unreadable, or identity-incompatible current manifest makes an old allowed decision stale, makes an old approval wait historical rather than promptable, and blocks a reserved operation as `reserved_authority_recovery`; it must never produce `ready_to_reserve` or `ready_to_resume`. Reserve, verify, settlement replay, recovery application, and every new action remain strict: require the exact current manifest and identity before any write. Reject symlinks in every component of authority-owned decision, source-snapshot, grant, state, and receipt directories; acquire inspected JSON as stable bytes and bind the reported digest to those same bytes. Publish authority-owned snapshots, immutable artifacts, and mutable state through stable directory descriptors with `O_NOFOLLOW` and pre/post parent-identity checks so an ancestor swap fails closed instead of redirecting a write.

Select workflow state in this order: unknown-effect quarantine; settled consumed or released reservation; usable reserved operation; reserved operation whose selected or ancestor authority is no longer usable; current exact allowed decision; exact source approval with a usable or cleanly materializable grant ID; source-authority defect; exhausted source authority; genuine approval wait. Return `should_prompt=false` for every system-recovery or reusable-authority state. A released reservation is terminal only with an exact release or reconciliation receipt proving no effect; return `already_released` and never redispatch it. Keep an unusable reserved projection reserved, preserve unknown-effect safety, return `reserved_authority_recovery`, and do not silently release it.

For a current producer-verifiable source approval, classify a missing grant ID as
materializable only when both its grant and state paths are absent and safe. A
historical schema-v2 source can reuse an existing exact grant but can never
materialize a missing one. Treat that read-only absence, or an exhausted/revoked/
expired/source-conflicted ID, as `source_authority_exhausted` and route to
`prepare_exact_recovery_recipe`.

Run `authority prepare-source-recovery` against the exact persisted exhausted decision binding. It publishes one immutable, prepare-only `authority_source_recovery_recipe` under `.task/authorization/recovery_recipes/`. The recipe binds the old decision, source snapshot, exhausted grant, and exact grant-state evidence; allocates distinct unused replacement request, attempt, source-approval, grant, lineage, and replay IDs; and includes a closed replacement request plus non-artifact source-approval and grant requirements. Exact replay is idempotent, while conflicting content for the same recovery identity fails closed. The recipe is neither approval nor authority. It must not contain any nested object accepted as `authority_source_approval` or `authority_grant`, any projected source-snapshot binding, or any claim that approval integrity is already verified. Materialize a source only from the actual later user-decision evidence and bind a grant only to the resulting immutable snapshot bytes; until then snapshot, registration, reserve, dispatch, and commit must fail closed.

Treat recipe `prepared_at` as T1 preparation evidence, never as the later user-decision time. The actual explicit decision supplies T2, with T2 greater than or equal to T1. A materialized source must set `not_before` to T2 or later; its grant must set both `not_before` and `created_at` to T2 or later. Evaluation at T1 must therefore remain non-allowed even if post-approval artifacts have subsequently been registered.

After a valid recipe exists, `status` and `resolve` supersede the system repair state with exactly one `needs_user_approval` result whose action is `approve_exact_recovery_projection`. Use the recovery projection, replay key, and effective-authority fingerprint as its new wait identity. Never revive the old projection or reuse an exhausted request, attempt, source, grant, lineage, or replay identity.

Preserve the machine-readable `post_approval_handoff` in prepare, status, and resolve output. After the exact user decision arrives, bind a closed `authority_recovery_user_decision` that echoes the whole recipe projection, recipe binding, decision time, and external evidence ID. Pass it to `materialize-approved-recovery`; the registered renderer creates and validates the schema-v3 `caller_asserted_exact_echo` source approval, snapshot, grant, replacement request, and allowed decision. The command cannot create or infer the user decision and must not label its caller echo as verified. From that point, poll `status` or `resolve` with `continuation_request_sha256`, not the exhausted original request digest.

Discover an existing recipe from its immutable historical decision/source/grant/state evidence before classifying a current generic approval wait. A later source expiry or other loss of current coverage must never revive the original approval projection or wait identity. If the recipe remains within its exact continuation window, preserve its one recovery prompt. If its expiry ceiling has closed, reuse `source_authority_exhausted` with reason `source_recovery_window_closed`, `should_prompt=false`, action `prepare_fresh_recovery_plan`, the exact recipe binding, and a non-authoritative closed-window handoff. Every non-prompt status or resolution exposes `approval_projection=null`.

```bash
PYTHONPATH="$SKILLS_ROOT/orchestrate-task-cycle/scripts" \
  python3 -P -m orchestrate_task_cycle workflow authority \
  prepare-source-recovery \
  --root . --decision-ref .task/authorization/decisions/authd-id.json \
  --decision-sha256 <sha256> --at 2026-01-01T00:00:00Z

PYTHONPATH="$SKILLS_ROOT/orchestrate-task-cycle/scripts" \
  python3 -P -m orchestrate_task_cycle workflow authority \
  materialize-approved-recovery \
  --root . --recovery-recipe '{"ref":"...","sha256":"..."}' \
  --user-decision '{"ref":"...","sha256":"..."}'
```

When the decision is `approval_required`, present the deterministic `approval_projection`: typed intent, exact operation/subject/capabilities/effect, bounded scope and budget, excluded effects, safe alternative, reason codes, and replay key. An approval of that projection does not authorize any excluded effect or broader reuse.

6. Reserve before dispatch.
   - Bind the persisted allowed decision by path and SHA-256.
   - Re-evaluate under a lock, verify the subject, operation manifest, selected grant and every lineage ancestor state/version, policy snapshot, expiry, scope, and available budget, then create a reservation and CAS-update usage across the lineage.
   - Treat an exact idempotent replay as the same reservation. Reject a conflicting replay.
   - Treat immutable event `state_changes` as a write-ahead recovery intent. Before every lifecycle/transition entry, scan all intents, complete each uniquely connected exact `before -> after` projection, accept an already-applied `after` or exact recorded descendant, and quarantine competing/unconnected state.

7. Verify before commit, then consume or release.
   - Run `authority verify --stage pre_commit` before committing effects.
   - For a registered owner operation, pass the exact reservation, pre-commit verification, and owner-result bindings to `authority settle`. Authority selects a fixed validator by `(skill_id, skill_version, operation_id, operation_version)`; workspace manifests cannot name code or arguments. Registered validator imports are pinned to the installed skills root co-located with this package; an explicit `--skills-root` must resolve to that exact root and cannot redirect executable owner code. Launch the fixed validator only through `owner_validator_process.isolated_owner_validator_argv`: its CPython 3.10+ `-B -I -c` bootstrap pins the current absolute interpreter, imports `runpy` before inserting canonical real owner roots, and excludes the caller CWD, `PYTHONPATH`, and user site. The selected interpreter's system site-packages remain its trusted third-party dependency surface. A confirmed effect consumes, confirmed no-effect releases, and unknown or legacy-opaque evidence quarantines without restoring budget.
   - Before calling that validator or writing lifecycle state, `settle` must acquire and hash the exact owner-result bytes under a 1 MiB limit. Capture the fixed validator through bounded pipes (256 KiB stdout and 64 KiB stderr), and load canonical owner-validation receipts once under a 256 KiB limit. Apply the same 1 MiB exact-byte limit when status or recovery classifies registered release evidence. These limits apply to the registered settlement path; they do not change the legacy unregistered schema-v2 consume/release contract.
   - `settle` first validates the current owner boundary, then writes the replay-stable historical owner-validation receipt and schema-v3 `authority_execution_result`. It derives effect status and the historical after boundary from owner evidence, permitting append-only descendants without accepting a forged current digest. Keep direct `consume --expected-subject-after-sha256` only for schema-v2 compatibility and operations not yet registered.
   - Run direct `authority release` only for an unregistered compatibility operation with evidence of `not_started` or `verified_no_effect`. Registered operations must use `authority settle`; its private release branch reopens the canonical owner-validation receipt, revalidates the current pre-commit CAS boundary, and re-runs the fixed owner validator. Public consume and release reject registered operations before any write and expose no caller-settable settlement bypass.
   - Replay and projection-intent recovery of a registered use or release must reopen reservation → decision, require the canonical historical owner-validation receipt, validate the typed pre-commit reservation/version binding without requiring the already-advanced current state, rerun the fixed owner validator, and require exact receipt equality before applying any projection.
   - Preserve pre-registry schema-v2 receipts without rewriting history. Status/inventory may read a receipt for an operation that is registered now only when its closed paths, digests, schemas, deterministic IDs, grant accounting, and state changes validate and every current projection equals the exact terminal `after` object. Treat that evidence as historical and legacy-unattested, never as schema-v3 owner validation. Recovery may skip an already exact-settled receipt but must reject its `before` state, a pending/missing projection, a descendant, or a forged transition before any write; direct consume/release remain forbidden.
   - Quarantine `unknown_effect`; do not restore its reserved budget automatically.
   - Run `authority prepare-reconciliation-evidence` to deterministically bind the quarantined reservation, operation, observed subject, outcome, time, and typed owner result. Pass its exact binding to `authority reconcile`. Map `confirmed_effect` to consumed, `confirmed_no_effect` to released, and `still_unknown` to a versioned quarantined state. Do not ask the user to approve the original operation again.

8. Transition grants explicitly.
   - Use CAS-bound `suspended`, `reactivated`, `revoked`, or `expired` transitions with immutable typed source approval.
   - Reactivation is the deliberate recovery path only from `suspended`: require a fresh exact event ID, the suspended state's expected version, and a still-effective source approval, and reject reactivation at or after the grant's expiry. A policy edit alone never reactivates a grant.
   - Apply `expired` only at or after the grant's exact `expires_at`; a grant without an expiry cannot take that transition.
   - Cascade revoke/expire to descendants. Suspension need not mutate every descendant projection, but an inactive ancestor makes every child unusable while that lineage remains invalid.

## Policy operations

Use these human-policy operations without conflating them with runtime leases:

- `summarize`: return effective policy and open questions.
- `ensure_default`: create the template only when a caller requires durable policy and no file exists.
- `draft_for_interview`: write `.interview/drafts/agent_authority.md` from interview evidence.
- `finalize_from_interview`: write final policy only after interview review, user confirmation, and agent write-confirmation gates.
- `update`: preserve supported user decisions and make only explicitly authorized changes.
- `validate`: reject capability expansion, unsupported sources, sensitive content, and precedence violations.

## Domain adapter contract

Accept optional project-owned hooks:

- `authority_axis_classify(...)`: classify a candidate as `already_granted`, `self_resolvable`, or `genuine_authority` with opaque evidence. Treat malformed or absent output as `authority_axis_unclassified`.
- `policy_consumption_sites(...)`: list opaque consumer sites and `reflects_policy`. Record false sites as `policy_propagation_incomplete` debt. Treat missing evidence as `propagation=unverified`.

Never let an adapter grant authority, lower a manifest requirement, manufacture external input, or define a broader generic capability. Use it only to narrow escalation through domain semantics.

## Legacy bridge

Keep `python3 -P -m manage_agent_authority receipt issue|validate` compatible with schema v1. Preserve v1 validation against the exact current file binding; do not silently reinterpret old receipts. Issue schema-v2 receipts with immutable policy/source snapshots so later policy edits do not invalidate them. Treat an unprovable legacy decision as historical partial/unverified, not retroactively allowed.

## Report contract

Return the same compact interaction projection from both status and resolve: `outcome`, `workflow_state`, `should_prompt`, nullable `user_action`, and one `next_action`. Set `outcome=workflow_state` to the selected machine state. Set `user_action=next_action` only when its actor is `user`; otherwise use `null`. Keep operation-specific detail, typed intent, reasons, exact subject, capabilities, axes, grant budget versus reservation units, immutable bindings, lifecycle version, scoped fingerprint, and conflicts in structured detail. Do not embed raw private or copyrighted source text.

For exact-request consumers, preserve `request_sha256_filter`, `workflow_basis`, and the exact decision, reservation/state, source-approval, recovery-recipe, settlement-receipt, and blocker bindings that justify the selected state. Public system states include `effect_reconciliation`, `already_consumed`, `already_released`, `ready_to_resume`, `reserved_authority_recovery`, `ready_to_reserve`, `source_approval_ready_for_grant`, `source_authority_defect`, and `source_authority_exhausted`. The only user-prompt state is `needs_user_approval`; its recovery variant uses `approve_exact_recovery_projection`. `idle` and `decision_<typed-decision>` remain non-prompt routing states.

## Guardrails

- Do not bypass active sandbox, approval, network, filesystem, model, tool, credential, cost, or higher-priority instruction limits.
- Do not use advice, task completion, validation success, issue status, silence, or a tier label as authority evidence.
- Do not use wildcard capabilities, wildcard subjects, implicit grant unions, self-delegation, circular delegation, rank escalation, retroactive receipts, or current mutable policy hashes for new receipts.
- Do not let task authority imply action authority, improvement authority rewrite core GT, authority imply risk consent, or approval imply external-input availability.
- Do not retry an unchanged approval wait as a new task. Replay the exact request and wake only when its scoped authority fingerprint or separate required input changes.
- Do not expose internal missing-grant state as a user approval when an exact effective source approval can materialize the grant.
- Do not turn an exhausted, revoked, expired, or source-conflicted existing grant ID into another approval for the same projection. Rebuild a new exact grant recipe first.
- Do not release a reservation with unknown effects. Quarantine it for evidence-backed recovery.
- Do not store secrets, credentials, tokens, raw private transcripts, or large copyrighted excerpts in authority artifacts.
