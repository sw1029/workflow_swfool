# Selection re-entry and publication

Use these helpers only around the existing derive boundary. They do not create a new cycle phase, choose a task, grant authority, or establish goal truth. The executable wake rule is owned by the helper; caller-provided predicate and delta IDs are bounded policy labels, not executable expressions.

## Contents

- [Exact selection trigger variants](#exact-selection-trigger-variants)
- [Authority re-entry after user escalation](#authority-re-entry-after-user-escalation)
- [Terminal-wait selection tick](#terminal-wait-selection-tick)
- [Selection acknowledgement and baseline rebase](#selection-acknowledgement-and-baseline-rebase)
- [Authority-settled current baseline](#authority-settled-current-baseline)
- [Deterministic terminal-wait sequence](#deterministic-terminal-wait-sequence)
- [Recoverable selected-task publication](#recoverable-selected-task-publication)

## Exact selection trigger variants

Selection decisions always bind one persisted exact trigger. A terminal-wait re-entry
uses the authenticated `selection_required` tick described below. A normal cycle uses a
closed `normal_cycle_selection_trigger`, produced only by the decision pipeline from
these exact regular-file bindings:

- finalized cycle receipt;
- schema-pre-derive result;
- direct derive result containing the durable three-lens synthesis sources;
- current `task.md`;
- current task-index JSONL;
- current selection-publication head/status artifact.

The trigger also binds the synthesis input-evidence manifest digest and declares itself
non-GT, non-authority, non-validation evidence, and write-free. Its ID and integrity
digest are derived from the closed body. The validator reopens every binding; a missing,
stale, unsafe, extra-field, or hash-shaped-only binding fails closed.

For a normal cycle, use the same deterministic pipeline with an explicit trigger kind:

```bash
python3 -P -m orchestrate_task_cycle selection-decision-receipt --root . pipeline \
  --cycle-id <cycle-id> \
  --trigger-kind normal_cycle \
  --source-result-ref <derive-result-ref> \
  --source-result-sha256 <derive-result-raw-sha256> \
  --cycle-finalization-ref <cycle-finalization-ref> \
  --cycle-finalization-sha256 <cycle-finalization-raw-sha256> \
  --schema-pre-derive-ref <schema-pre-derive-ref> \
  --schema-pre-derive-sha256 <schema-pre-derive-raw-sha256> \
  --current-task-ref task.md \
  --current-task-sha256 <current-task-raw-sha256> \
  --task-index-ref .task/index.jsonl \
  --task-index-sha256 <task-index-raw-sha256> \
  --publication-head-ref <publication-head-ref> \
  --publication-head-sha256 <publication-head-raw-sha256>
```

The pipeline persists content-addressed trigger, synthesis, preliminary decision v2,
and selection-decision receipt v2 artifacts under the cycle's selection receipt
directory, then reopens the receipt chain. The receipt binds trigger kind/ID, synthesis
receipt ID, exact evidence-manifest digest, outcome, and selected task ID. It does not
choose a task, grant authority, validate completion, or mutate task topology. Do not
reuse a terminal-wait tick as a normal-cycle trigger or fabricate a trigger from the
known candidate ID.

## Authority re-entry after user escalation

`terminal_wait` and `user_escalation` have different re-entry contracts. A
terminal-wait baseline observes a later material input change through
`selection-tick`. A finalized normal cycle whose direct derive result is
`user_escalation` already contains the selection analysis; when its exact authority
request is later resolved by signed root grants, do not run `selection-tick`, allocate
new lenses, or initialize a new implementation cycle around the completed predecessor.
Reopen only the frozen selection boundary with the deterministic authority-reentry
compiler:

```bash
python3 -P -m orchestrate_task_cycle workflow cycle authority-reentry --root . publish \
  --cycle-id <historical-source-cycle-id> \
  --at <RFC3339-authority-reentry-evaluation-time> \
  --source-result-ref <direct-user-escalation-derive-ref> \
  --source-result-sha256 <derive-raw-sha256> \
  --cycle-finalization-ref <cycle-finalization-ref> \
  --cycle-finalization-sha256 <cycle-finalization-raw-sha256> \
  --schema-pre-derive-ref <schema-pre-derive-ref> \
  --schema-pre-derive-sha256 <schema-pre-derive-raw-sha256> \
  --current-task-ref task.md \
  --current-task-sha256 <completed-task-raw-sha256> \
  --task-index-ref .task/index.jsonl \
  --task-index-sha256 <task-index-raw-sha256> \
  --publication-head-ref <current-publication-receipt-ref> \
  --publication-head-sha256 <publication-receipt-raw-sha256> \
  --authority-decision-ref <allowed-decision-1-ref> \
  --authority-decision-sha256 <allowed-decision-1-raw-sha256> \
  --authority-decision-ref <allowed-decision-2-ref> \
  --authority-decision-sha256 <allowed-decision-2-raw-sha256>
```

`--at` is required. It is the one explicit authority re-evaluation time bound into the
compiler inputs and authority-resolution seal; dry-run, publication, replay, and
persisted validation reuse that exact normalized value and never sample an ambient
clock. Use `--dry-run` to perform the full write-free compilation and return only
compact prospective bindings. Publication recompiles under the registered producer
barrier and writes six content-addressed artifacts under `.task/selection_reentry/`:
the normal trigger, frozen synthesis, exact prospective task Markdown,
authority-resolution seal, schema-v3 preliminary decision, and schema-v3 selection
receipt. Exact replay returns the same bindings with `mutation_performed: false`. None
of these artifacts grants authority, mutates `task.md`, changes goal truth, validates
completion, or makes the historical cycle executable.

The compiler reopens the authority packet's historical decision at its exact artifact
ref and raw SHA-256, verifies the packet's exact `request_sha256`, and persists that
decision binding plus a request-semantic digest in the resolution. The semantic
projection removes only the three compiler allocation identities `request_id`,
`attempt_id`, and `idempotency_key`; cycle, task, subject, operation, capabilities,
effect/classification, cardinality/budget, context evidence, actor, pack, composition,
and every other request field remain exact. The later allowed decision for the
historically required operation must have the same semantic digest. Additional
operations may appear only when their own schema-v3 grants are exact request members
of the same signed root lineage.

The compiler accepts only this mechanically decidable shape:

- exactly three frozen derive lenses, each containing one byte-equivalent candidate;
- one canonical candidate union and a `blocked_authority` candidate;
- a direct finalized `user_escalation` derive result with no selected task;
- an allowed decision whose request is semantically identical to the frozen
  historical request except for compiler allocation identities;
- schema-v3 grants materialized from one shared signed-root approval lineage;
- exact resolved-design evidence bound to the authority subject;
- a clear single selection-publication head and unchanged trigger inputs.

The derived task ID and task Markdown are deterministic. The schema-v3 receipt owns the
exact `task_source` ref and SHA-256. Every publication, task-index, and selected-successor
consumer must compare that full binding; the same Task ID with different bytes, or the
same digest copied to a different ref, is not the selected source.

After re-entry, use the ordinary selected-successor preparation over the returned
receipt and task-source bindings. The historical decisions are evidence that the
candidate's old blocker changed; they are not topology or execution grants for the new
task. Settle the exact three-operation topology under its own signed plan, then
initialize a fresh compiler-first cycle for the selected task and compile a separate
dispatch/run plan. Because topology and fresh execution have different cycle scopes,
the current single-batch root-plan contract requires separate exact approvals.

## Terminal-wait selection tick

Run a read-only tick before assigning proposal agents while the current task is completed and non-executable:

```bash
python3 -P -m orchestrate_task_cycle selection-tick --root .
```

When an authority-settled current terminal-wait baseline exists, the command resolves and re-verifies `.task/terminal_wait_baseline/current.json` and uses its bound selection packet. Add `--previous-json <prior-tick.json>` only for initial publication, recovery, testing, or a caller that already owns the exact packet. Absence of both a current pointer and an explicit prior packet means an initial baseline observation, not permission to fan out.

`--watch-path` extends rather than replaces the default workflow observations. The packet may retain task aliases, advice indexes, completed pack/retirement history, and repository-adapter implementation/delegate/renderer surfaces for bounded audit comparison, but their static byte changes are availability or workflow-self-write evidence only. The task-pack row named by the canonical mutable `task.md` pointer remains distinct from completed pack history; changing, completing, or removing that current row is material only when `task_pack` is explicitly watched. Manifest-declared adapter components remain `adapter` availability rows even when their paths sit under a generic workflow directory. Bind any other current residual through an exact-subject/post-use receipt, an exact authority packet, or an explicitly watched decision-bearing class; do not use a filename, render, registration, or import success as semantic wake evidence.

### Executable wake semantics

Bind terminal wait to one or more `--wake-predicate <opaque-id>`, one or more supported `--watched-evidence-class <class>`, and one `--minimum-material-delta <opaque-id>`. Supported classes are `task_state`, `goal_truth`, `authority`, `advice`, `issue`, `schema_contract`, `adapter`, `task_pack`, `custom_watch`, and `exact_subject`; the default material set is `authority`, `exact_subject`, and `goal_truth`. The baseline owns these values, so comparison cannot silently widen, narrow, or replace them. `task_state` and advice-container rows remain availability-only. A historical baseline whose class set is the entire supported enum is treated as the former broad default, not as proof that every static row is current-blocker relevant. A narrower baseline may explicitly bind an open issue, required adapter/runtime/source surface, or another decision-bearing class, but its static digest opens re-evaluation only; actual consumption still requires the owning post-use receipt.

For fresh baselines, completed/noncurrent pack rows are `task_state` availability while the canonical current pointer row or an explicitly watched pack row is `task_pack`. A bound `task_pack` or `custom_watch` deletion retains its pre-change evidence class in the closed change row and is material; deleting completed history, an archive, an index render, or a retirement projection remains nonmaterial. A pre-existing narrow legacy baseline that lacks this distinction must be rebound from current inputs rather than granting historical rows semantic relevance.

`wake_predicates` and `minimum_material_delta` document policy intent. They are not parsed or evaluated as caller-defined expressions. The packet makes this explicit with:

- `wake_evaluation_rule: explicit-premise-or-bound-class-change-v1`;
- `wake_predicate_ids_are_policy_labels: true`.

The fixed rule opens selection only when the current manifest differs from the authenticated prior manifest and either an exact-premise row was added or content-changed, or at least one non-availability watch row belongs to a baseline-bound watched evidence class. A static task rename, archive/retirement change, index render, same-body report serialization, unbound adapter/workflow self-write, or byte change outside the material classes returns `no_op`. An identical manifest returns `no_op`; an identical premise receipt combined only with nonmaterial drift also returns `no_op`. The helper reports changed rows and material changed rows separately; consumers must not reinterpret a supplied-input boolean, registration, loader success, or policy label as proof that a fresh semantic premise exists.

Exact-premise and effective-authority watch rows are sticky. If a later tick omits them, the helper validates and carries their prior body-free rows forward instead of treating omission as removal. Re-supplying the same ID and semantic digest is therefore unchanged; supplying a changed receipt for the same premise ID, a new premise ID, or changed effective authority for an exact scope is a material comparison. Sticky carry-forward preserves comparison continuity but does not make the evidence GT or authority.

### Verified exact-subject premise contract

For unattended or repeatable re-entry, initialize the baseline with:

```bash
python3 -P -m orchestrate_task_cycle selection-tick --root . \
  --premise-input-contract validated_exact_subject_premise_receipt_v2 \
  --wake-predicate <policy-label> \
  --watched-evidence-class exact_subject \
  --minimum-material-delta <policy-label>
```

The premise-input contract is locked for the life of that baseline. `raw_exact_file_v1` remains a compatibility contract, but a raw file digest alone does not establish that the input is fresh, owned, actionable, or tied to the current wait. Use `validated_exact_subject_premise_receipt_v2` when those semantics matter. Version 1 validation receipts are structural/historical inputs only and cannot autonomously reopen selection.

Build and validate a premise through the `exact-subject-premise` command family, which first produces the deterministic v1 semantic decision and then seals a consumed decision as a path-free artifact-verified v2 receipt. Pass that persisted v2 receipt as the paired `--premise-path <receipt.json> --premise-id <opaque-id>`. The receipt contract requires all of the following:

```bash
python3 -P -m orchestrate_task_cycle exact-subject-premise \
  --root . \
  --context <workspace-relative-context.json> \
  --submission <workspace-relative-submission.json> \
  --binding-artifact <workspace-relative-task-or-baseline> \
  --subject-artifact <workspace-relative-current-subject> \
  --baseline-subject-artifact <workspace-relative-prior-subject> \
  --source-subject-artifact <workspace-relative-source-subject> \
  --evidence-artifact <invariant-evidence-id>=<workspace-relative-receipt> \
  --evidence-artifact <producer-or-source-receipt-id>=<workspace-relative-receipt> \
  --evidence-artifact <verifier-or-current-body-receipt-id>=<workspace-relative-receipt> \
  --evidence-artifact <replay-or-comparison-receipt-id>=<workspace-relative-receipt> \
  --prior-receipt <workspace-relative-prior-v2-receipt.json>
```

Omit baseline/source flags only when the selected evidence mode and freshness context make them inapplicable. Every input and evidence path must resolve to a regular non-symlink file inside `--root`; parent traversal and external absolute paths fail closed. A consumed semantic decision is emitted directly as v2 only after every applicable artifact is reopened and matched. A rejected semantic decision remains a v1 rejection record because there is no accepted artifact claim to seal. Prior consumed v1 receipts are historical-only and cannot be upgraded by replay; provide their previously artifact-verified v2 form.

- an exact current binding to either the terminal task or the authenticated selection baseline;
- a freshness baseline plus a subject ID, revision ID that changes for the same subject, and content digest;
- exactly one canonical writable owner, writable surface, and authority scope;
- the current first-failing invariant with failing evidence;
- either distinct producer/verifier/replay receipts over the same subject digest or source-separated source/current-body comparison evidence.
- successful workspace-local, regular, non-symlink reopening of every bound artifact, with its persisted raw digest kept distinct from any semantic/canonical binding digest.

The validator emits deterministic `consumed` or `rejected` semantic decisions and a replay identity. Only a consumed decision whose referenced artifacts were reopened and checked can be sealed as v2. Exact replay must reproduce the same outcome; conflicting replay is rejected. Neither receipt form persists a source body or source path. The selection tick accepts only a consumed v2 receipt, verifies its premise ID and current binding, and embeds the complete path-free receipt in the sticky row so terminal publication remains independently revalidatable. A rejected or v1-only receipt, wrong wait binding, unchanged freshness subject, non-advanced same-subject revision, owner mismatch, first-invariant mismatch, raw-digest mismatch, unsafe path, or malformed evidence fails closed. Exact replay of the already observed v2 receipt remains a deterministic `no_op`.

Add `--authority-packet <closed-v2-authority-packet.json>` for an approval or external-input wait. The tick persists only the exact scope ID, effective authority fingerprint, closed decision, and independent axis statuses. It rejects the mutable whole `.agent_goal/agent_authority.md` policy as a watch path. Unrelated policy/grant changes therefore cannot reopen a wait; an exact request/operation/subject, selected-grant/reservation, or relevant local/external/risk/GT axis change can.

When derive first emits `terminal_wait`, run the tick without a prior packet and retain the returned `baseline_recorded` packet in the terminal-wait result. Bind its canonical packet digest and `observed_input_manifest_sha256` separately from derive's frozen analysis-evidence digest. Before current-pointer activation, a next tick may consume either that retained packet or the derive-result JSON containing it through `--previous-json`. After activation, omit `--previous-json` so the command re-verifies and consumes the current owner binding. Both paths verify the packet ID and read-only/no-fanout flags before comparison. Using the analysis digest as the tick baseline is invalid because the two manifests cover different inputs and would spuriously reopen selection.

- `baseline_recorded|no_op`: preserve terminal wait and do not fan out agents.
- `selection_required`: run the existing derive selection only; do not start a full implementation cycle yet.
- `recovery_required`: recover the pending selection publication before any new proposal or selection.
- `drift_blocked`: the unique committed selection head no longer matches `task.md`; repair or explicitly reconcile that unjournaled drift before fanout.

A changed timestamp, renamed task, archive/retirement projection, index render, old advice, workflow self-write, or stale candidate is not an explicit premise. A missing ID, missing/external/symlinked/non-regular/oversized premise path, or a comparison that changes the baseline's wake contract is rejected.

### Selection acknowledgement and baseline rebase

A `selection_required` tick is a one-time trigger, not a reusable safe baseline. Name the currently activated safe baseline `A`, the new `selection_required` tick `B`, and the later input-stable rebased safe baseline `C`. Run only the existing three-lens derive selection from `B`, then choose one of two paths:

- if derive selects a distinct executable successor, publish it through the selection-publication owner and leave terminal wait;
- if derive returns to `terminal_wait`, acknowledge and rebase the exact trigger before publishing that wait result.

Do not collapse the return-to-wait evidence into one generic receipt. Persist and reopen this exact chain:

```text
three lens receipt projections + one canonical synthesis-output projection
  -> derive_selection_synthesis
  -> preliminary_selection_decision bound to B
  -> selection_decision_receipt bound to persisted B and the preliminary decision
  -> C, the acknowledgement/rebase of B
  -> direct full final derive result embedding C and the receipt identity
```

The first four files are the existing durable runtime artifacts under `.task/cycle/<cycle-id>/agent_receipts/`: three closed lens projections and one canonical synthesis-output projection. `derive_selection_synthesis` reopens those exact regular non-symlink files through the direct derive-selection source object and validates the complete three-lens analysis before sealing its own projection. The preliminary decision reopens that synthesis and binds its outcome, selected task, evidence digest, synthesis receipt ID, and exact trigger `B`. The selection-decision receipt then reopens both persisted `B` and the preliminary decision. These artifacts are non-GT, non-authority, and non-completion evidence; the preliminary decision is never the terminal baseline owner's `source_derive`.

Use the content-addressed `selection-decision-receipt pipeline` for the complete persisted chain. Supply the exact derive source and trigger bindings; the compiler reopens them, renders every mechanical envelope, writes each immutable artifact, computes its raw SHA-256, validates the finished chain, and returns body-free bindings:

```bash
python3 -P -m orchestrate_task_cycle selection-decision-receipt --root . pipeline \
  --cycle-id CYCLE_ID \
  --trigger-kind terminal_wait \
  --source-result-ref SOURCE_RESULT_REF \
  --source-result-sha256 SOURCE_RESULT_RAW_SHA256 \
  --trigger-tick-ref SELECTION_REQUIRED_B_JSON \
  --trigger-tick-sha256 B_RAW_SHA256
```

Uppercase values are placeholders for normalized workspace-relative refs or exact lowercase raw SHA-256 values; replace them before execution. The returned `synthesis`, `decision`, and `receipt` bindings identify the immutable artifacts under `.task/cycle/<cycle-id>/agent_receipts/selection/`; pass those bindings directly to the next owner. Exact replay returns the same bindings and `mutation_performed: false`. Every input ref must remain a normalized regular non-symlink path inside `--root`; absolute paths, traversal aliases, malformed digests, and oversized artifacts fail closed. The lower `render-synthesis`, `render-decision`, `render`, and `validate` commands remain compatibility/audit primitives only. They are not the normal workflow and must not be connected with shell redirection, coordinator-authored JSON, or coordinator-computed digests.

Rebase `B` into `C` with the trigger tick ID plus the validated selection-decision receipt ref and raw digest:

```bash
python3 -P -m orchestrate_task_cycle selection-tick --root . \
  --previous-json <selection-required-tick.json> \
  --acknowledge-selection-tick-id <exact-trigger-packet-id> \
  --selection-receipt-ref <workspace-relative-receipt.json> \
  --selection-receipt-sha256 <full-sha256>
```

The command authenticates `B`, reopens the workspace-relative regular non-symlink selection-decision receipt, verifies its exact bytes against the supplied raw digest, derives rather than trusts its receipt ID and integrity digest, and recursively reopens the receipt-bound preliminary decision, durable selection synthesis, four runtime artifacts, and persisted trigger. It then carries sticky premise/authority rows forward and accepts `C` only when no material watched input changed during selection and selection publication is clear. Nonmaterial availability/history drift is recomputed and may be absorbed into `C`; it cannot become another selection trigger. An ID plus an arbitrary 64-hex string is not acknowledgement evidence. Success returns a safe `baseline_recorded` packet with `baseline_rebased: true`, `selection_acknowledgement_status: accepted`, and the closed eight-field acknowledgement binding: trigger ID/digest, receipt ID/ref/raw digest/internal integrity digest, outcome, and selected task ID. For `terminal_wait`, `selected_task_id` is `null`.

Lineage is exact, not label-based. The terminal owner reopens the predecessor snapshot named by `expected_current_snapshot_sha256` and requires `B.previous_input_manifest_sha256 == A.observed_input_manifest_sha256`; it recomputes `B.changed_watch_entries` from `A` and requires the same wake contract. It then requires `C.previous_input_manifest_sha256 == B.observed_input_manifest_sha256`, recomputes `C.changed_watch_entries` from persisted `B`, requires an empty material-change set, and preserves the same wake contract. Thus `B` proves the material wake and `C` proves that selection introduced no additional blocker-relevant drift, while bounded history/render changes remain visible without reopening fanout.

After `C` is durable, produce a direct full final derive-result JSON object. It must pass the derive result contract in block mode, set the disjoint outcome/source to `terminal_wait`, carry `C` byte-for-value as `terminal_wait.selection_tick_baseline`, bind its canonical baseline digest and watched-input fields, and set `last_selection_receipt` to the validated selection-decision receipt ID. Its `improvement_analysis_manifest` must exactly match the manifest reopened through the durable selection synthesis. A `{ "result": ... }` wrapper, preliminary decision, receipt, or partial projection is not a valid `source_derive`. Input drift returns `selection_required` again; pending publication returns recovery state. Neither case may be coerced into a safe baseline.

This acknowledgement is what consumes a premise-triggered selection attempt. Without it, passing the same trigger forward would request selection repeatedly. With it, an omitted premise is sticky, an exact replay compares equal, and the next unchanged tick is `no_op`.

### Authority-settled current baseline

After the direct full terminal-wait derive result exists, publish `C` through the terminal-wait baseline owner. Build the authority subject from the non-executable terminal `task.md`, the direct full final `source_derive`, optional transition evidence, `C`, and `A`'s exact predecessor snapshot digest. Materialize that non-active subject before authority evaluation. Then use the authority-v2 lifecycle for `publish_terminal_wait_baseline_binding`: evaluate, reserve, verify `pre_dispatch`, construct the closed authority packet, and verify `pre_commit`. The baseline owner writes immutable prepare, snapshot, and completion artifacts first; none is current at that point. Consume the exact reservation against that completion, validate the resulting authority-use receipt, then activate through the expected-current compare-and-swap and expose `.task/terminal_wait_baseline/current.json` last.

The bounded command family is:

```bash
python3 -P -m orchestrate_task_cycle terminal-wait-baseline --root . materialize-subject \
  --subject <terminal-wait-authority-subject.json> --dry-run
python3 -P -m orchestrate_task_cycle terminal-wait-baseline --root . materialize-subject \
  --subject <terminal-wait-authority-subject.json>
python3 -P -m orchestrate_task_cycle terminal-wait-baseline --root . prepare \
  --plan <terminal-wait-baseline-plan.json> --dry-run
python3 -P -m orchestrate_task_cycle terminal-wait-baseline --root . prepare \
  --plan <terminal-wait-baseline-plan.json>
python3 -P -m orchestrate_task_cycle terminal-wait-baseline --root . activate \
  --completion-ref <ref> --completion-sha256 <sha256> \
  --use-receipt-ref <ref> --use-receipt-sha256 <sha256>
python3 -P -m orchestrate_task_cycle terminal-wait-baseline --root . retire-successor \
  --publication-ref <selection-publication-receipt-ref> \
  --publication-sha256 <selection-publication-receipt-sha256>
python3 -P -m orchestrate_task_cycle terminal-wait-baseline --root . resolve
python3 -P -m orchestrate_task_cycle terminal-wait-baseline --root . audit
```

`--subject` and `--plan` accept only normalized workspace-relative regular non-symlink files under `--root`; they never authorize an external absolute input. `materialize-subject` creates only the content-addressed, non-active subject that the authority preflight can hash exactly; it excludes the later authority packet and pre-commit verification to avoid a circular digest. Its dry run computes the same binding without writing. `prepare --dry-run` performs validation and CAS preflight without mutation. A normal prepare returns the exact completion binding and authority-consume inputs while keeping `current_pointer_exposed: false`. `activate` requires normalized ref/raw-digest bindings for the matching completion and settled use receipt, revalidates all bound artifacts, and is idempotent only for the exact same activation. `retire-successor` binds one current, settled selection-publication receipt and preserves an immutable inactive pointer/history; it cannot delete or silently abandon a stale baseline. `resolve` is read-only and returns body-free bindings. `audit` checks bounded append-only subjects, prepares, snapshots, completions, activations, settlement cardinality, orphans, and the current pointer; resolving an inactive pointer also reopens its retirement history. A category beyond the owner-defined artifact-count bound fails closed instead of being materialized without limit. Never hand-edit, copy forward, or select a current pointer by filename order.

Once activated, ordinary `selection-tick --root .` auto-discovers this verified packet. If the terminal task, snapshot lineage, selection packet, authority settlement, or pointer binding no longer verifies, resolution fails closed instead of falling back to an unbound baseline.

### Deterministic terminal-wait sequence

1. A completed, non-executable task has no distinct successor evidence. Derive emits `terminal_wait` and one safe `baseline_recorded|no_op` selection packet.
2. Publish that packet as the authority-settled current terminal-wait baseline.
3. On later invocations, resolve the current pointer and run only `selection-tick`. Unchanged inputs produce `no_op`; do not initialize a cycle or fan out agents.
4. A new consumed exact-subject receipt or a changed row in a bound evidence class produces `selection_required`; open only derive selection.
5. If selection produces a successor, use recoverable selected-task publication, settle its prospective task-state plan, and retire predecessor `A` to a verified inactive pointer. If it produces another wait, run the decision pipeline over the four runtime artifacts so it persists the durable synthesis, preliminary decision, and receipt; acknowledge `B` into `C`; write the direct full final derive result; then materialize, authority-settle, and activate the new baseline against predecessor `A`.
6. Replaying the same premise receipt, omitting sticky inputs, or rerunning with unchanged workflow inputs produces `no_op`. Only a new semantic receipt or another bound-class change can reopen selection.

## Recoverable selected-task publication

The derive owner must first produce one authoritative, digest-bound selection decision. Persist the deterministic synthesis/decision/receipt chain without asking the coordinator to write or hash JSON envelopes. A direct selected normal-cycle result uses `--trigger-kind normal_cycle` plus the six exact normal-cycle bindings above and produces receipt v2. A settled `user_escalation` result uses the authority-reentry compiler and produces receipt v3. A terminal-wait re-entry alone uses the trigger-tick pair:

```bash
python3 -P -m orchestrate_task_cycle selection-decision-receipt --root . pipeline \
  --cycle-id <cycle-id> \
  --trigger-kind terminal_wait \
  --source-result-ref <derive-result-ref> \
  --source-result-sha256 <derive-result-raw-sha256> \
  --trigger-tick-ref <selection-tick-ref> \
  --trigger-tick-sha256 <selection-tick-raw-sha256>
```

For new selected successors, first build and immutably publish one schema-v2
`task_state_transition_plan`. Its request binds the prospective task Markdown through
`artifact_sources`, marks the `task.md` anchor as
`prospective_source_sha256`, and declares
`external_settlement_kind: selection_publication`. The plan may compile the new active
task and superseded predecessor events before `task.md` changes because it binds the
prospective source bytes, not a false current-alias precondition.

For the normal path, do not author the prospective events or intent JSON. Render both
owners' preparation artifacts and the three-step authority contract from the two exact
semantic bindings:

```bash
python3 -P -m orchestrate_task_cycle selected-successor --root . prepare \
  --source-decision-ref <receipt-ref> \
  --source-decision-sha256 <raw-sha256> \
  --task-source-ref <prospective-task-ref> \
  --task-source-sha256 <raw-sha256> \
  --at <RFC3339>
```

The immutable body-free bundle contains the task-state plan and publication-prepare
bindings, the exact three operation identities and subjects, deterministic idempotency
keys, exact predicted pending/publication/settlement receipt bindings, execution order,
and recovery checkpoints. A canonical immutable
`successor_prepare_indexes/sha256/<input-sha256>.json` binds the exact decision, task
source, and timestamp inputs to that bundle. Exact prepare replay rechecks both source
files and the complete bundle contract through this O(1) index before consulting current
task state, so the same prepare remains stable after pending apply or full settlement.
A missing bundle index falls back to the ordinary prepare/recovery path: a new owner
prepare still requires full source validation, while only an exact existing owner
prepare index may replay historical validated work. The missing index alone cannot turn
a self-sealed decision into a write. The bundle does not execute an effect. Before the
first effect, an
executor must validate all three exact reservation and `pre_commit` bindings plus their
expected reservation versions; a missing, stale, consumed-as-current, or cross-bound
proof blocks the whole sequence with zero effects. `selected-successor execute` and
`selected-successor recover` are the only supported first-effect entrypoints. Both
reopen the canonical bundle, re-render its closed contract, validate all three authority
proofs, and publish one immutable pre-effect authority gate before step 1. `recover`
uses the same proof set and executor; the separate name makes crash-resumption intent
explicit rather than weakening the gate.

Compile the two semantic context artifacts before preparing authority. Supply the
complete actual session ceiling and goal-autonomy envelope; do not ask the model to
author either JSON body, its schema markers, CAS path, content seal, or raw digest:

```bash
python3 -P -m orchestrate_task_cycle selected-successor --root . \
  prepare-authority-context \
  --bundle-ref <bundle-ref> --bundle-sha256 <raw-sha256> \
  --actor-rank <S0-S4> \
  --external-input-status <status> \
  --goal-truth-status <status> \
  --risk-acceptance-status <status> \
  --design-selection-status <status> \
  --session-capability <actual-capability-1> \
  --session-capability <actual-capability-N> \
  --session-risk-ceiling <R0-R3> \
  --session-mutation-class <actual-mutation-class-1> \
  --session-mutation-class <actual-mutation-class-N> \
  --session-evidence-id <exact-session-evidence-id> \
  --goal-envelope-id <exact-goal-envelope-id> \
  --goal-capability <actual-capability-1> \
  --goal-capability <actual-capability-N> \
  --goal-risk-ceiling <R0-R3> \
  --goal-decision-class <actual-decision-class-1> \
  --goal-decision-class <actual-decision-class-N> \
  --goal-subject-digest <actual-subject-digest-1> \
  --goal-subject-digest <actual-subject-digest-N> \
  --goal-operation <skill:version:operation:version> \
  --goal-operation <additional-actual-operation> \
  --goal-source-ref <goal-source-ref> \
  --goal-source-sha256 <goal-source-raw-sha256> \
  --skills-root <skills-root>
```

Repeat every list flag for every value in the caller's real ceiling or envelope,
including values unrelated to this one bundle. The compiler normalizes and preserves
that caller-supplied scope. It opens the exact bundle and registered manifests only to
verify that all three required capabilities, risks, mutation classes, decision classes,
subjects, and operations are covered; it never derives a ceiling from manifest minima,
drops unrelated scope, or widens a supplied scope. `actor_rank`, session evidence ID,
envelope ID, risk ceilings, goal-source binding, and all four status axes are likewise
caller-owned semantic inputs.

Add `--external-input-evidence-ref` with its matching `--...-sha256` when external
status is `available`, `missing_supplyable`, or `missing_unsupplyable`. Add the paired
`--risk-acceptance-evidence-*` or `--design-selection-evidence-*` flags only when the
corresponding status is `resolved`; those evidence bindings must be absent for every
status that does not require them. A missing half, missing file, digest drift, symlink,
or evidence/status mismatch fails before either context is published.

Open each goal-envelope source and optional request-evidence artifact through the
no-follow bounded reader with a 1 MiB per-artifact limit. This bound applies before
digest acceptance and is independent of the 64 KiB cap on each generated context CAS
artifact. A new payload is rejected before resolving its store path; an oversized
existing CAS target is rejected from file metadata before its content is hashed.

The result is body-free: it returns the exact canonical
`successor_authority_request_contexts/sha256/` and
`successor_authority_evaluation_contexts/sha256/` bindings, registered manifest
bindings, scalar replay/mutation flags, and `model_authored_mechanical_bytes: 0`.
Both generated payloads are size-checked and both immutable targets are conflict-checked
before the first write, so an oversized evaluation context or a conflict in either CAS
cannot leave a half-published pair. Exact replay returns the same bindings with
`idempotent_replay: true`; store symlinks and immutable-content conflicts fail closed.
Neither artifact is authority evidence or an allow decision.

The mutation-capable `prepare-authority` and packet paths accept only those exact
producer-owned CAS locations. Copying canonical, digest-matching bytes to another
workspace ref does not make a valid input. There is no legacy flag, alternate directory,
or hidden loader opt-out. Existing audit/recovery validation may reopen the evaluation
context already embedded in a historical decision/proof chain; that read-only historical
proof path does not accept a standalone legacy context ref and cannot bootstrap a new
decision, reservation, packet, or effect.

Prepare the proof set and its compact packet from those two returned bindings through
the deterministic authority renderer, not by asking the coordinator to assemble three
requests or proof arguments:

```bash
python3 -P -m orchestrate_task_cycle selected-successor --root . prepare-authority \
  --bundle-ref <bundle-ref> --bundle-sha256 <raw-sha256> \
  --request-context-ref <request-context-ref> \
  --request-context-sha256 <raw-sha256> \
  --evaluation-context-ref <evaluation-context-ref> \
  --evaluation-context-sha256 <raw-sha256> \
  --index-grant-ref <grant-ref> --index-grant-sha256 <raw-sha256> \
  --publication-grant-ref <grant-ref> --publication-grant-sha256 <raw-sha256> \
  --settlement-grant-ref <grant-ref> --settlement-grant-sha256 <raw-sha256> \
  --at <RFC3339> --skills-root <skills-root>
```

The request context is a closed
`selected_successor_authority_request_context` artifact that binds the exact successor
bundle, the exact semantic `actor_rank`, and only the shared semantic request fields. The evaluation context is
an exact schema-v2 `authority_evaluation` artifact describing the actual session
ceiling and goal-autonomy envelope. Neither context is authority evidence. For each
action, supply exactly one branch of the closed union: the `--<prefix>-grant-ref` and
`--<prefix>-grant-sha256` pair, or the corresponding `--index-grant-absent`,
`--publication-grant-absent`, or `--settlement-grant-absent` flag. Never use a dummy
grant, omit one half of a binding, copy manifest requirements into a ceiling, or let
the renderer synthesize capability, subject, operation, decision-axis, source, or
grant facts.

Reopen the self-sealed request-context `actor_rank` and require every present grant's
`holder_rank` to equal it. An absent grant never permits rank inference from an operation
floor, another identity, or the strongest available grant. Rank disagreement fails
closed before compilation or lifecycle publication.

With three existing exact grant bindings, the renderer reopens the bundle, contexts,
subjects, manifests, grants, and grant states; derives the three requests with the
bundle's exact idempotency keys; and invokes the canonical evaluator for each
request. Only three `allowed` evaluator results may proceed. It then publishes the
three decisions, reserves the exact operations, produces their exact `pre_commit`
verifications, and finally publishes one immutable
`selected_successor_authority_packet`. The success result contains only the packet
binding and closed `execute_argv` / `recover_argv` projections. The renderer never
creates a source approval or grant and never treats the request or evaluation context,
selection receipt, compilation, packet, or CLI success as an allow decision.
Both argv projections use the version-portable isolated-module launcher and pin
the absolute current interpreter plus executable imports to the co-located
installed skills root. A supplied
`--skills-root` remains a manifest/proof validation argument; it cannot become a
Python import root or redirect executable owner code. Treat each argv list as one
opaque, host-local execution projection: execute the exact returned list without
parsing or reconstructing its interpreter prefix. Its absolute workspace and
installed-root arguments are not packet identity and are reproducible only under
the same bound host installation.

If genuine no-covering authority or another evaluator result is not `allowed`, publish one compact
`selected_successor_authority_approval_projection` binding and stop. This fail-closed
path may publish the three non-authoritative compilation bindings, but publishes zero decisions, reservations, or pre-commit verifications and performs
zero selected-successor effects. Present only that exact projection to the authority
owner; do not expose three model-authored request bodies, invent a replacement grant,
or continue with a mixed subset. If an action is declared absent but evaluation finds
covering authority, or a supplied binding differs from the selected grant, treat the
input as a conflict rather than misreporting approval-required. Exact replay reopens
the indexed inputs and returns
the same packet or approval-projection binding. Any bundle, context, grant, manifest,
subject, or state drift requires a fresh evaluation and cannot reuse the old packet.

The input identity, immutable index, and pre-index packet locator bind all three exact
operation-manifest digests. Publish the locator before the packet and the final index
last, so a packet/index crash can repair the index in O(1), even after exact execution
consumes the reservations. A present but invalid located packet fails closed; only a
truly absent packet may resume preparation. Generated execute/recover argv preserve an
explicit custom `--skills-root` used for compilation.

The compiler-internal schema-v2 `selection_publication_intent` binds the validated
selection-decision receipt, exact prospective task Markdown, and the immutable
prospective task-state plan:

```json
{
  "schema_version": 2,
  "kind": "selection_publication_intent",
  "source_decision": {"ref": "<receipt-ref>", "sha256": "<raw-sha256>"},
  "task_source": {"ref": "<prospective-task-ref>", "sha256": "<raw-sha256>"},
  "task_state_plan": {"ref": "<task-state-plan-ref>", "sha256": "<raw-sha256>"}
}
```

Execute the guarded sequence from the successful packet binding. Use the same arguments
with `recover` after an interrupted attempt:

```bash
python3 -P -m orchestrate_task_cycle selected-successor --root . execute \
  --authority-packet-ref <packet-ref> \
  --authority-packet-sha256 <raw-sha256> --at <RFC3339>
```

As a legacy-compatible path for already-issued proof sets, `execute` and `recover`
continue to accept the exact bundle plus all three explicit owner-issued proof triples:

```bash
python3 -P -m orchestrate_task_cycle selected-successor --root . execute \
  --bundle-ref <bundle-ref> --bundle-sha256 <raw-sha256> \
  --index-reservation-ref <ref> --index-reservation-sha256 <raw-sha256> \
  --index-pre-commit-ref <ref> --index-pre-commit-sha256 <raw-sha256> \
  --index-expected-version <version> \
  --publication-reservation-ref <ref> --publication-reservation-sha256 <raw-sha256> \
  --publication-pre-commit-ref <ref> --publication-pre-commit-sha256 <raw-sha256> \
  --publication-expected-version <version> \
  --settlement-reservation-ref <ref> --settlement-reservation-sha256 <raw-sha256> \
  --settlement-pre-commit-ref <ref> --settlement-pre-commit-sha256 <raw-sha256> \
  --settlement-expected-version <version> --at <RFC3339>
```

The executor checks the legal checkpoint prefix, then applies the compiled plan as
pending, publishes `task.md` by CAS, and settles task state from the exact publication
receipt. It consumes the three authority reservations only after all effects are exact.
Packet mode reopens the packet, bundle, decisions, reservations, pre-commit
verifications, expected versions, contexts, manifests, and grants and recovers the same
closed proof map used by the legacy arguments. The packet is a compact transport and
replay binding, not new authority. The two input forms are mutually exclusive and
neither can omit, union, replace, or weaken one of the three proofs.
On replay, an already consumed reservation is accepted only by reproducing and
validating its exact schema-v3 use receipt and owner validation; `partial` or unknown
state is never treated as no effect. Exact receipt/state/index crash points are repaired
through immutable intent bindings without transaction-history enumeration.

The lower-level `apply-plan`, `selection-publication apply-intent`, and
`settle-plan-external` commands describe owner internals and remain available for
prepare/debug or explicitly governed historical recovery. They are not a supported
selected-successor first-effect path, must not be invoked directly for this route, and
do not themselves establish or retroactively create the immutable
all-three-pre-commit gate. Verify downstream consumption with
`selection-publication status` after the guarded executor completes.

The publication compiler emits schema-v3 prepare material, reopens the complete decision,
task-source, and prospective-plan chains, derives all IDs, lineage, paths, before/after
digests, and transaction identity, and stores the exact task bytes once under
`.task/selection_publication/blobs/sha256/`. Its prepare and CLI output contain no Base64,
task body, or task-index body. Task-state index bytes remain owned by
`$manage-task-state-index`.

Internally, `apply-plan` appends the task-state event batch and renders the index, but publishes
`task_state_transition_pending_receipt` with
`activation_status: pending_external_settlement`; `task.md` must still match its before
digest and other task-state writers remain blocked behind the pending intent.
`apply-intent` requires that exact pending receipt, rechecks every CAS binding, publishes
only `task.md` last, and records a committed schema-v3 publication receipt. The final
`settle-plan-external` step reopens that receipt, verifies the candidate bytes now equal
`task.md`, and publishes the settled schema-v2 task-state apply receipt. Exact replay is
idempotent at every boundary.

Until settlement validates, `selection-publication status` returns
`settlement_required`, `selection_consumption_allowed: false`, and the exact task-state
settlement reason. A committed alias alone is therefore not a completed activation
lifecycle. Settlement validation is delegated to the task-index owner and accepts a
verified original event batch followed by legitimate append-only descendants; it does
not compare the current whole ledger hash to the historical plan-after hash. The current
Markdown projection must still match the complete current ledger. After settlement, the
gate becomes true. If this successor exits an active
terminal wait, retire the exact predecessor only after that gate opens:

```bash
python3 -P -m orchestrate_task_cycle terminal-wait-baseline --root . retire-successor \
  --publication-ref <publication-receipt-ref> \
  --publication-sha256 <publication-receipt-raw-sha256>
```

Retirement verifies the committed publication is current, settled when schema v3, and
actually supersedes the baseline's task digest. It writes immutable retirement history
and replaces `current.json` with a verified schema-v2 `inactive` pointer; it does not
delete baseline evidence. Exact replay returns the same inactive state.

One historical-recovery ordering is intentionally earlier. If a stale active baseline
already binds the predecessor of the *current* committed publication head, retire it
with that exact current receipt before preparing another successor transaction. A later
publication makes the historical receipt noncurrent, while its own `before_sha256` no
longer matches the older baseline, so neither receipt may be substituted afterward.
This exception applies only when the owner verifies the existing current head, its
settlement gate, and the exact baseline-before/current-task-after transition; it is not
permission to retire from a noncurrent or merely digest-shaped receipt.

Storage schema v4 keeps only one bounded committed head and at most one active
transaction in `state.json`. Schema-v2 intents have immutable
`intents/sha256/<intent-sha256>/prepare.json` and `commit.json` lookup records, so normal
status and exact intent replay never enumerate transaction history or reopen historical
source bodies. Use `status --deep` for historical audit and `migrate-state` to validate
legacy history, build the bounded state, and populate lookup records. Missing or schema-v1
state with existing journals reports `migration_required`; it never silently falls back
to a normal-path scan. Historical artifacts are neither rewritten nor garbage-collected.
A crash before alias publication remains publication recovery; a crash after alias
publication but before task-state settlement remains `settlement_required` and must
replay `selected-successor recover` with the same exact authority proof set, not invent
a new task or bypass the pre-effect gate with an individual owner command.

When one unique legacy committed head has independently authorized `task.md` drift,
compile compatibility reconciliation from the exact settled task-state transition
receipt rather than authoring another target payload:

```bash
python3 -P -m orchestrate_task_cycle selection-publication --root . reconcile-current \
  --source-ref <task-state-receipt-ref> --source-sha256 <raw-sha256>
```

### Legacy v1 plan and recovery

When recovering or replaying an existing v1 transaction, retain its caller-owned plan
and Base64 wire shape. The exact prepare journal must already exist; this command may
only replay/recover that transaction:

```bash
python3 -P -m orchestrate_task_cycle selection-publication --root . apply \
  --plan <selection-publication-plan.json>
```

The plan is caller-owned and has this shape:

```json
{
  "schema_version": 1,
  "kind": "selection_publication_plan",
  "selection_id": "opaque-selection-id",
  "source_decision_id": "opaque-decision-id",
  "source_decision_sha256": "<64 lowercase hex>",
  "targets": [
    {
      "role": "task_alias",
      "target_ref": "task.md",
      "before_sha256": "<64 lowercase hex or null when absent>",
      "after_payload_b64": "<non-empty exact prospective bytes>"
    }
  ]
}
```

Allowed roles are `past_task_archive`, `agent_log_index_jsonl`, `task_pack_state`, `task_pack_render`, `advice_index_jsonl`, `advice_index_markdown`, `task_index_jsonl`, `task_index_markdown`, and the required `task_alias`. The archive and its append-only `.agent_log/index.jsonl` projection must be supplied together. `past_task_archive`, `agent_log_index_jsonl`, and both pack roles are owner-committed projections: create them first through `$record-agent-work-log` or the task-pack helper, then supply identical before/after bytes. Publication binds and verifies those projections but cannot bypass their journals or mutate them. Paths are role-bounded, workspace-relative, non-symlink regular files or absent targets. Physical deletion is not representable. A pack removal therefore uses the task-pack owner's typed retirement state, not a missing after-payload.

The legacy recovery reader:

1. validates bounded roles, paths, payload size, source-decision binding, and exact before digests;
2. reopens the existing immutable prepare journal and explicit transaction lineage;
3. preflights every target before writing any target;
4. writes archives and projections before the authoritative `task.md` pointer;
5. verifies all after digests;
6. writes a committed receipt only after every target is verified.

All public v1 `prepare`, `apply`, and `reconcile --plan` surfaces reject a plan that does
not already match the bounded active or current committed transaction with
`legacy selection-publication v1 new write is forbidden`. New Base64 journals cannot be
created. Exact `recover --transaction-id` remains available, and multiple legacy pending
journals require explicit repair before `migrate-state`.

If a process stops after some targets reach their after-state, consumers must treat the pending journal as `recovery_required`. Forward-complete it with:

```bash
python3 -P -m orchestrate_task_cycle selection-publication --root . recover
```

Use `status` for a read-only pending/head check and `prepare` only when an explicit prepare-only boundary is required. At most one transaction may be pending: exact prepare/publish replay for that transaction is allowed, but any different prepare or uncommitted publish must fail before mutation until recovery completes. Multiple legacy pending journals are ambiguous and automatic recovery must not choose one by sort order. The status projection follows task-alias before/after links to the unique committed head: historical receipts may be superseded, but current unjournaled `task.md` drift or multiple heads blocks selection consumption. A target outside its exact before/after states blocks recovery and preserves the pending evidence; it never overwrites the foreign bytes. Replaying the same committed plan returns the existing receipt.

Do not create a new v1 drift-reconciliation journal. Use the body-free
`reconcile-current` intent path shown above after independent authorization. The former
`reconcile --plan` form is recovery-only and rejects a new Base64 plan.

The publication receipt proves logical atomicity of workflow projections only. It does not prove that the proposed task is correct. Downstream selection consumers must still verify the three-agent receipt contract, adapter seal, authority, exact subject, task-pack state, and derive result contract.
