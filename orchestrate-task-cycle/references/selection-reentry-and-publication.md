# Selection re-entry and publication

Use these helpers only around the existing derive boundary. They do not create a new cycle phase, choose a task, grant authority, or establish goal truth. The executable wake rule is owned by the helper; caller-provided predicate and delta IDs are bounded policy labels, not executable expressions.

## Contents

- [Terminal-wait selection tick](#terminal-wait-selection-tick)
- [Selection acknowledgement and baseline rebase](#selection-acknowledgement-and-baseline-rebase)
- [Authority-settled current baseline](#authority-settled-current-baseline)
- [Deterministic terminal-wait sequence](#deterministic-terminal-wait-sequence)
- [Recoverable selected-task publication](#recoverable-selected-task-publication)

## Terminal-wait selection tick

Run a read-only tick before assigning proposal agents while the current task is completed and non-executable:

```bash
python3 -m orchestrate_task_cycle selection-tick --root .
```

When an authority-settled current terminal-wait baseline exists, the command resolves and re-verifies `.task/terminal_wait_baseline/current.json` and uses its bound selection packet. Add `--previous-json <prior-tick.json>` only for initial publication, recovery, testing, or a caller that already owns the exact packet. Absence of both a current pointer and an explicit prior packet means an initial baseline observation, not permission to fan out.

`--watch-path` extends rather than replaces the default workflow inputs. The packet hashes the exact workflow inputs, every canonical pack JSON (including non-active residual packs), repository-adapter implementation/delegate/renderer/authority-projection surfaces, and explicit premise inputs without copying source bodies or corpus metadata.

### Executable wake semantics

Bind terminal wait to one or more `--wake-predicate <opaque-id>`, one or more supported `--watched-evidence-class <class>`, and one `--minimum-material-delta <opaque-id>`. Supported classes are `task_state`, `goal_truth`, `authority`, `advice`, `issue`, `schema_contract`, `adapter`, `task_pack`, `custom_watch`, and `exact_subject`. The baseline owns these values, so comparison cannot silently widen, narrow, or replace them.

`wake_predicates` and `minimum_material_delta` document policy intent. They are not parsed or evaluated as caller-defined expressions. The packet makes this explicit with:

- `wake_evaluation_rule: explicit-premise-or-bound-class-change-v1`;
- `wake_predicate_ids_are_policy_labels: true`.

The fixed rule opens selection only when the current manifest differs from the authenticated prior manifest and either an exact-premise row was added or content-changed, or at least one changed watch row belongs to a baseline-bound watched evidence class. A byte change outside those classes returns `no_op`. An identical manifest returns `no_op`; an identical premise receipt combined only with nonmaterial drift also returns `no_op`. The helper reports changed rows and material changed rows separately; consumers must not reinterpret a supplied-input boolean or policy label as proof that a fresh semantic premise exists.

Exact-premise and effective-authority watch rows are sticky. If a later tick omits them, the helper validates and carries their prior body-free rows forward instead of treating omission as removal. Re-supplying the same ID and semantic digest is therefore unchanged; supplying a changed receipt for the same premise ID, a new premise ID, or changed effective authority for an exact scope is a material comparison. Sticky carry-forward preserves comparison continuity but does not make the evidence GT or authority.

### Verified exact-subject premise contract

For unattended or repeatable re-entry, initialize the baseline with:

```bash
python3 -m orchestrate_task_cycle selection-tick --root . \
  --premise-input-contract validated_exact_subject_premise_receipt_v2 \
  --wake-predicate <policy-label> \
  --watched-evidence-class exact_subject \
  --minimum-material-delta <policy-label>
```

The premise-input contract is locked for the life of that baseline. `raw_exact_file_v1` remains a compatibility contract, but a raw file digest alone does not establish that the input is fresh, owned, actionable, or tied to the current wait. Use `validated_exact_subject_premise_receipt_v2` when those semantics matter. Version 1 validation receipts are structural/historical inputs only and cannot autonomously reopen selection.

Build and validate a premise through the `exact-subject-premise` command family, which first produces the deterministic v1 semantic decision and then seals a consumed decision as a path-free artifact-verified v2 receipt. Pass that persisted v2 receipt as the paired `--premise-path <receipt.json> --premise-id <opaque-id>`. The receipt contract requires all of the following:

```bash
python3 -m orchestrate_task_cycle exact-subject-premise \
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

A changed timestamp, renamed task, old advice, or stale candidate is not an explicit premise. A missing ID, missing/external/symlinked/non-regular/oversized premise path, or a comparison that changes the baseline's wake contract is rejected.

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

Use the `selection-decision-receipt` CLI in four persisted stages. Each `<sha256>` is the raw digest of the exact workspace-relative file emitted by the previous stage; do not substitute an internal canonical digest or an arbitrary 64-hex value.

```bash
# 1. Reopen the four durable runtime artifacts and seal their selection synthesis.
python3 -m orchestrate_task_cycle selection-decision-receipt --root . \
  render-synthesis \
  --source-result-ref SOURCE_RESULT_REF \
  --source-result-sha256 SOURCE_RESULT_RAW_SHA256 \
  > DERIVE_SELECTION_SYNTHESIS_JSON

# 2. Bind the durable synthesis to the exact selection-required trigger B.
python3 -m orchestrate_task_cycle selection-decision-receipt --root . \
  render-decision \
  --trigger-tick-ref SELECTION_REQUIRED_B_JSON \
  --trigger-tick-sha256 B_RAW_SHA256 \
  --selection-synthesis-ref DERIVE_SELECTION_SYNTHESIS_JSON \
  --selection-synthesis-sha256 SELECTION_SYNTHESIS_RAW_SHA256 \
  > PRELIMINARY_SELECTION_DECISION_JSON

# 3. Bind persisted B and the preliminary decision into the decision receipt.
python3 -m orchestrate_task_cycle selection-decision-receipt --root . \
  render \
  --trigger-tick-ref SELECTION_REQUIRED_B_JSON \
  --trigger-tick-sha256 B_RAW_SHA256 \
  --selection-decision-ref PRELIMINARY_SELECTION_DECISION_JSON \
  --selection-decision-sha256 PRELIMINARY_DECISION_RAW_SHA256 \
  > SELECTION_DECISION_RECEIPT_JSON

# 4. Reopen and validate the complete persisted receipt chain before rebase.
python3 -m orchestrate_task_cycle selection-decision-receipt --root . \
  validate \
  --receipt-ref SELECTION_DECISION_RECEIPT_JSON \
  --receipt-sha256 SELECTION_DECISION_RECEIPT_RAW_SHA256 \
  --trigger-tick-ref SELECTION_REQUIRED_B_JSON \
  --trigger-tick-sha256 B_RAW_SHA256
```

Uppercase values are placeholders for normalized workspace-relative refs or exact lowercase raw SHA-256 values; replace them before execution. These are four serialization/verification stages inside the existing derive boundary, not four new workflow phases. Persist each output before the next command because every downstream stage reopens exact bytes from `--root`.

Every `*-ref` argument in this chain must be a normalized workspace-relative path. Absolute paths, parent traversal, backslash aliases, symlink traversal, non-regular files, uppercase or non-hex digests, and oversized artifacts fail closed. CLI stdout is not durable merely because it was emitted: write it to a workspace file, compute the raw digest of those exact bytes, and only then pass its binding to the next stage.

Rebase `B` into `C` with the trigger tick ID plus the validated selection-decision receipt ref and raw digest:

```bash
python3 -m orchestrate_task_cycle selection-tick --root . \
  --previous-json <selection-required-tick.json> \
  --acknowledge-selection-tick-id <exact-trigger-packet-id> \
  --selection-receipt-ref <workspace-relative-receipt.json> \
  --selection-receipt-sha256 <full-sha256>
```

The command authenticates `B`, reopens the workspace-relative regular non-symlink selection-decision receipt, verifies its exact bytes against the supplied raw digest, derives rather than trusts its receipt ID and integrity digest, and recursively reopens the receipt-bound preliminary decision, durable selection synthesis, four runtime artifacts, and persisted trigger. It then carries sticky premise/authority rows forward and accepts `C` only when watched inputs did not change during selection and selection publication is clear. An ID plus an arbitrary 64-hex string is not acknowledgement evidence. Success returns a safe `baseline_recorded` packet with `baseline_rebased: true`, `selection_acknowledgement_status: accepted`, and the closed eight-field acknowledgement binding: trigger ID/digest, receipt ID/ref/raw digest/internal integrity digest, outcome, and selected task ID. For `terminal_wait`, `selected_task_id` is `null`.

Lineage is exact, not label-based. The terminal owner reopens the predecessor snapshot named by `expected_current_snapshot_sha256` and requires `B.previous_input_manifest_sha256 == A.observed_input_manifest_sha256`; it recomputes `B.changed_watch_entries` from `A` and requires the same wake contract. It then requires `C.previous_input_manifest_sha256 == B.observed_input_manifest_sha256`, `C.observed_input_manifest_sha256 == B.observed_input_manifest_sha256`, identical watch entries and wake contract, and empty changed/material-changed/class-change sets. Thus `B` proves the material wake and `C` proves that selection itself introduced no watched-input drift.

After `C` is durable, produce a direct full final derive-result JSON object. It must pass the derive result contract in block mode, set the disjoint outcome/source to `terminal_wait`, carry `C` byte-for-value as `terminal_wait.selection_tick_baseline`, bind its canonical baseline digest and watched-input fields, and set `last_selection_receipt` to the validated selection-decision receipt ID. Its `improvement_analysis_manifest` must exactly match the manifest reopened through the durable selection synthesis. A `{ "result": ... }` wrapper, preliminary decision, receipt, or partial projection is not a valid `source_derive`. Input drift returns `selection_required` again; pending publication returns recovery state. Neither case may be coerced into a safe baseline.

This acknowledgement is what consumes a premise-triggered selection attempt. Without it, passing the same trigger forward would request selection repeatedly. With it, an omitted premise is sticky, an exact replay compares equal, and the next unchanged tick is `no_op`.

### Authority-settled current baseline

After the direct full terminal-wait derive result exists, publish `C` through the terminal-wait baseline owner. Build the authority subject from the non-executable terminal `task.md`, the direct full final `source_derive`, optional transition evidence, `C`, and `A`'s exact predecessor snapshot digest. Materialize that non-active subject before authority evaluation. Then use the authority-v2 lifecycle for `publish_terminal_wait_baseline_binding`: evaluate, reserve, verify `pre_dispatch`, construct the closed authority packet, and verify `pre_commit`. The baseline owner writes immutable prepare, snapshot, and completion artifacts first; none is current at that point. Consume the exact reservation against that completion, validate the resulting authority-use receipt, then activate through the expected-current compare-and-swap and expose `.task/terminal_wait_baseline/current.json` last.

The bounded command family is:

```bash
python3 -m orchestrate_task_cycle terminal-wait-baseline --root . materialize-subject \
  --subject <terminal-wait-authority-subject.json> --dry-run
python3 -m orchestrate_task_cycle terminal-wait-baseline --root . materialize-subject \
  --subject <terminal-wait-authority-subject.json>
python3 -m orchestrate_task_cycle terminal-wait-baseline --root . prepare \
  --plan <terminal-wait-baseline-plan.json> --dry-run
python3 -m orchestrate_task_cycle terminal-wait-baseline --root . prepare \
  --plan <terminal-wait-baseline-plan.json>
python3 -m orchestrate_task_cycle terminal-wait-baseline --root . activate \
  --completion-ref <ref> --completion-sha256 <sha256> \
  --use-receipt-ref <ref> --use-receipt-sha256 <sha256>
python3 -m orchestrate_task_cycle terminal-wait-baseline --root . resolve
python3 -m orchestrate_task_cycle terminal-wait-baseline --root . audit
```

`--subject` and `--plan` accept only normalized workspace-relative regular non-symlink files under `--root`; they never authorize an external absolute input. `materialize-subject` creates only the content-addressed, non-active subject that the authority preflight can hash exactly; it excludes the later authority packet and pre-commit verification to avoid a circular digest. Its dry run computes the same binding without writing. `prepare --dry-run` performs validation and CAS preflight without mutation. A normal prepare returns the exact completion binding and authority-consume inputs while keeping `current_pointer_exposed: false`. `activate` requires normalized ref/raw-digest bindings for the matching completion and settled use receipt, revalidates all bound artifacts, and is idempotent only for the exact same activation. `resolve` is read-only and returns body-free bindings. `audit` checks bounded append-only subjects, prepares, snapshots, completions, activations, settlement cardinality, orphans, and the current pointer; a category beyond the owner-defined artifact-count bound fails closed instead of being materialized without limit. Never hand-edit, copy forward, or select a current pointer by filename order.

Once activated, ordinary `selection-tick --root .` auto-discovers this verified packet. If the terminal task, snapshot lineage, selection packet, authority settlement, or pointer binding no longer verifies, resolution fails closed instead of falling back to an unbound baseline.

### Deterministic terminal-wait sequence

1. A completed, non-executable task has no distinct successor evidence. Derive emits `terminal_wait` and one safe `baseline_recorded|no_op` selection packet.
2. Publish that packet as the authority-settled current terminal-wait baseline.
3. On later invocations, resolve the current pointer and run only `selection-tick`. Unchanged inputs produce `no_op`; do not initialize a cycle or fan out agents.
4. A new consumed exact-subject receipt or a changed row in a bound evidence class produces `selection_required`; open only derive selection.
5. If selection produces a successor, use recoverable selected-task publication. If it produces another wait, persist the four runtime artifacts, durable selection synthesis, preliminary decision, and selection-decision receipt; acknowledge `B` into `C`; write the direct full final derive result; then materialize, authority-settle, and activate the new baseline against predecessor `A`.
6. Replaying the same premise receipt, omitting sticky inputs, or rerunning with unchanged workflow inputs produces `no_op`. Only a new semantic receipt or another bound-class change can reopen selection.

## Recoverable selected-task publication

The derive owner must first produce one authoritative, digest-bound selection decision. When publishing that decision touches `task.md` plus its archive, task index, advice index, or pack projection, use one bounded publication transaction instead of independent writes:

```bash
python3 -m orchestrate_task_cycle selection-publication --root . apply \
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

The helper:

1. validates bounded roles, paths, payload size, source-decision binding, and exact before digests;
2. writes an immutable prepare journal;
3. preflights every target before writing any target;
4. writes archives and projections before the authoritative `task.md` pointer;
5. verifies all after digests;
6. writes a committed receipt only after every target is verified.

If a process stops after some targets reach their after-state, consumers must treat the pending journal as `recovery_required`. Forward-complete it with:

```bash
python3 -m orchestrate_task_cycle selection-publication --root . recover
```

Use `status` for a read-only pending/head check and `prepare` only when an explicit prepare-only boundary is required. At most one transaction may be pending: exact prepare/publish replay for that transaction is allowed, but any different prepare or uncommitted publish must fail before mutation until recovery completes. Multiple legacy pending journals are ambiguous and automatic recovery must not choose one by sort order. The status projection follows task-alias before/after links to the unique committed head: historical receipts may be superseded, but current unjournaled `task.md` drift or multiple heads blocks selection consumption. A target outside its exact before/after states blocks recovery and preserves the pending evidence; it never overwrites the foreign bytes. Replaying the same committed plan returns the existing receipt.

When `status` reports one unique `drift_blocked` head and the unjournaled `task.md` bytes are independently authorized, reconcile only that exact task-alias transition with:

```bash
python3 -m orchestrate_task_cycle selection-publication --root . reconcile \
  --plan <selection-publication-drift-reconciliation-plan.json>
```

The reconciliation plan must contain exactly one `task_alias` target. Its before digest must equal the unique head's expected task digest, and its after payload must reproduce the current regular, non-symlink `task.md` bytes exactly. Reconciliation records a successor journal and receipt without rewriting `task.md`; it rejects extra projections, stale or noncurrent payloads, pending publication, and ambiguous heads.

The publication receipt proves logical atomicity of workflow projections only. It does not prove that the proposed task is correct. Downstream selection consumers must still verify the three-agent receipt contract, adapter seal, authority, exact subject, task-pack state, and derive result contract.
