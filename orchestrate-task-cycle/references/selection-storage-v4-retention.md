# Selection storage v4 and retention

Use selection-CAS retention only as a compiler-first, reversible maintenance
transaction. Never ask the model to author the reference-barrier policy, GC
plan, archive manifest, effect receipt, owner result, or settlement evidence.

## Contents

- [Preconditions and backup](#preconditions-and-backup)
- [Adopt the producer barrier](#adopt-the-producer-barrier)
- [Plan and apply](#plan-and-apply)
- [Restore and settle](#restore-and-settle)
- [Recovery boundaries](#recovery-boundaries)

## Preconditions and backup

Stop all workspace processes that can create references or write selection
publication data. Before the first storage-v4 migration:

1. Back up the complete `.task/selection_publication/` tree to an external,
   immutable archive.
2. Record the archive hash and verify that the archive can be listed and read.
3. Record `selection-publication status --deep`, the current task alias hash,
   active/head identifiers, and receipt bindings.
4. Run `migrate-state`, then run `status --deep` again. Confirm that the
   compact projection preserves the active/head and receipt lineage and that
   the task alias is unchanged.

For example, from the skill's `scripts/` directory on `PYTHONPATH`:

```bash
python3 -P -m orchestrate_task_cycle selection-publication --root . status --deep
python3 -P -m orchestrate_task_cycle selection-publication --root . migrate-state
python3 -P -m orchestrate_task_cycle selection-publication --root . status --deep
```

Keep the backup path and its recorded hash outside
`.task/selection_publication/`. A migration failure or parity mismatch is a
stop boundary; do not proceed to adoption or GC.

## Adopt the producer barrier

Run the deterministic adoption compiler once after storage v4 is verified:

```bash
python3 -P -m orchestrate_task_cycle selection-publication --root . \
  adopt-reference-barrier
```

The compiler takes the exclusive producer barrier and publication lock,
computes a bounded descriptor-pinned workspace epoch, binds the exact current
storage-state digest and a code-hashed closed inventory of registered producer
APIs, and publishes the canonical policy at
`.task/selection_publication/reference-barrier.json`. It leaves no partial
policy or lock residue when the preconditions fail. Do not hand-author,
copy-edit, or synthesize this JSON.

The cooperative reference barrier uses `flock` on a no-follow descriptor for
the existing workspace-root directory, rechecking its device/inode identity
before use. It does not create a barrier lock file. The narrower
`.task/selection_publication/publication.lock` is an intentional persistent
serialization primitive for state transactions; code may create or acquire it
only after proving the matching shared producer or GC-exclusive barrier mode.
Whenever authority and selection storage are both needed, the sole lock order is
reference barrier (shared or exclusive), publication lock when applicable, then
authority lock. Per-effect lease/gate writers hold the registered shared barrier
before authority; GC keeps its exclusive barrier through publication and
authority validation.

The policy's coverage is exactly
`registered_selection_publication_producers_only`; it explicitly records
`external_writer_coverage=not_claimed`. The built-in selection publication and
CAS blob writers participate in the shared barrier. The compiler refreshes the
policy's exact state binding after supported state mutations and GC rejects a
stale state or producer-code inventory before scanning candidates.

The producer inventory binds each complete registered source file and verifies
every declared entrypoint against its module AST. Its bounded lint recursively
scans the whole `orchestrate_task_cycle` Python source tree and binds every
relative path and file digest into one source-tree digest. The lint uses an
exact protected-symbol-to-importer map; being present elsewhere in the
inventory does not authorize a low-level store, payload, or GC write primitive.
At runtime, ordinary registered writes require the opaque producer capability
and shared-barrier proof. Apply/restore writes require the distinct opaque
GC-exclusive capability plus a currently held exclusive-barrier proof. Direct
primitive calls, a generic producer token used under the exclusive barrier, a
missing entrypoint, or source/lint drift fail before mutation. These controls
cover built-in Python producers only and do not change the external-writer
limitation above.

Immutable producer leaves are staged, fsynced, and hard-linked into place.
Concurrent exact publication replays the winner; conflicting publication
fails without replacing it. An already-present immutable leaf is capability
checked and bounded-hashed before barrier entry, so an exact replay or conflict
does not create control files; an absent/racing leaf is checked again while the
barrier is held. Mutation and idempotent-replay fields come from the actual
hard-link outcome, not from a pre-write existence guess, so concurrent
same-content publishers report exactly one creator.

Adoption does not attest that arbitrary external or legacy writers are absent.
Quiesce, upgrade, prohibit, or independently host-enforce those writers before
adoption and throughout plan/apply. If that operational condition cannot be
established, do not delete anything.

Run `status --deep` after adoption and compare the same task/head/active and
receipt evidence recorded before it. A mismatch is a stop boundary.

## Plan and apply

Create a plan only through the compiler:

```bash
python3 -P -m orchestrate_task_cycle selection-publication --root . \
  gc-plan
```

Planning fails before a full CAS/workspace scan unless the exact canonical
adoption policy is present and its state and registered-producer bindings are
current. It requires storage v4 and no active publication.
The bounded scan:

- traverses the workspace and CAS through pinned, no-follow directory
  descriptors and revalidates ancestor identities;
- excludes `.git/` and the GC control subtree;
- fails closed on symlinks, non-regular files, malformed JSON/JSONL, or file,
  per-file-byte, and aggregate-byte limits;
- marks raw references and recursively decoded JSON strings, including escaped
  `/`, anywhere in the bounded workspace; and
- selects only unreferenced objects in registered GC-safe CAS roots. State,
  locks, receipts, transactions, arbitrary packets, successor indexes, and
  content-bound historical evidence are not candidates merely because a path
  string was not found.

Obtain authority for operation
`apply_selection_publication_retention` bound to the exact compiled plan
`ref`, digest, and revision. Then apply with the compiled authority-packet and
pre-commit-verification bindings:

```bash
python3 -P -m orchestrate_task_cycle selection-publication --root . \
  gc-apply --plan-id PLAN_ID \
  --authority-packet AUTHORITY_BINDING_JSON \
  --pre-commit-verification PRECOMMIT_BINDING_JSON
```

Apply holds the exclusive producer barrier from its final mark scan through
receipt publication. Immediately before the first effect it acquires an
authority-owned atomic effect lease and revalidates the exact reservation,
decision, operation, subject, and current pre-commit proof. If either barrier
or authority continuity is not provable, no deletion occurs.

The deterministic archive is published and byte-verified before deletion.
Each open candidate remains bound to its original inode, metadata, and bytes;
replacement, ancestor substitution, or drift blocks the effect. The command
unlinks only that verified object and proves every candidate absent again
immediately before publishing the immutable receipt.

The returned `owner_result` is not a model-authored packet. Settle it through
`$manage-agent-authority`; the fixed
`apply_selection_publication_retention` owner validator reopens the complete
plan, archive, receipt, effect-lease, authority, and final candidate state.
Pre-commit verification alone does not consume the grant.

## Restore and settle

To roll back a completed GC effect, obtain authority for
`restore_selection_publication_retention` bound to the exact GC receipt, then
run:

```bash
python3 -P -m orchestrate_task_cycle selection-publication --root . \
  gc-restore --plan-id PLAN_ID \
  --authority-packet AUTHORITY_BINDING_JSON \
  --pre-commit-verification PRECOMMIT_BINDING_JSON
```

Restore verifies the deterministic archive and refuses to overwrite a
conflicting target. It writes the exact archived bytes through pinned
descriptors, then reopens and verifies every restored target immediately before
publishing its receipt. Settle the returned owner result through
`$manage-agent-authority`; the fixed
`restore_selection_publication_retention` validator checks the receipt,
archive, authority effect lease, and exact final files.

Exact replay reopens the immutable authority and effect evidence recorded in
the receipt. A first effect, including recovery after a crash that occurred
before receipt publication, still requires a current reserved authority state,
current pre-commit proof, and a fresh atomic effect lease.

## Recovery boundaries

- Treat an empty plan as a valid audited outcome. Never broaden it merely to
  reclaim more space.
- Resume apply or restore only through the same command; immutable bindings
  make retries deterministic and reject drift.
- Use `gc-restore` for normal retention rollback and settle its owner result.
- Use the pre-migration archive only for an offline migration rollback: stop
  all writers, verify the recorded archive hash, preserve the failed current
  tree separately, restore into an empty target, and rerun deep status/parity
  checks before resuming.
- Never extract a backup over a live tree and never repair CAS, plan, receipt,
  policy, authority, or owner-result JSON by hand.

`migrate-state` is a separately bounded transaction. It rejects history beyond
4,096 transactions, 16,384 directory entries, 32 MiB per historical file,
256 MiB in aggregate reads, or an 8 MiB migration journal. The 32 MiB
per-file ceiling deliberately admits the observed 25.6–27.3 MiB legacy prepare
packets while remaining finite; raise it only with a new measured workspace
inventory, boundary tests, and an explicit contract revision.
Its visibility order is: immutable migration prepare/WAL, every historical
intent prepare/commit index, compact state, then completion receipt last.
Readers reject a compact state while its prepare exists without the exact
completion receipt. Re-running the command resumes the same prepared bytes;
completed older generations are retained before a later recovery migration.

Packet retention remains adapter-owned close hygiene under
`$maintain-cycle-ledger`. Without a valid adapter retention policy, rotate
nothing.
