# Initial-Selection Provenance Transactions

Use these transactions only for the first canonical item in a task pack. Keep authority policy, operation-authority receipt, creation snapshot, task snapshot, and inline selection receipt distinct.

## Prospective first selection

Prefer the self-service two-transaction path: create the planned pack, consume the returned immutable creation descriptor, issue authority for the exact first item/task, then promote it. The pack is not executable between the two transactions because every item remains planned.

Create with a complete bounded pack:

```json
{
  "action": "create_pack",
  "reason": "bounded reason code",
  "pack": {
    "schema_version": 1,
    "pack_id": "pack-P",
    "status": "active",
    "language": "ko",
    "goal": "Bounded pack goal.",
    "current_item_id": "item-I",
    "created_at": "2026-01-01T00:00:00+00:00",
    "updated_at": "2026-01-01T00:00:00+00:00",
    "items": [
      {
        "item_id": "item-I",
        "order": 1,
        "status": "planned",
        "title": "First item",
        "objective": "Perform the first bounded task.",
        "validation_profile": "current_only",
        "progress_target": "advanced"
      },
      {
        "item_id": "item-J",
        "order": 2,
        "status": "planned",
        "title": "Successor item",
        "objective": "Perform the dependent bounded task.",
        "validation_profile": "affected_chain",
        "progress_target": "advanced",
        "dependencies": ["item-I"]
      }
    ],
    "mutation_log": [],
    "terminal_blocker": null
  }
}
```

Run:

```bash
python3 -B "${CODEX_HOME:-$HOME/.codex}/skills/orchestrate-task-cycle/python3 -m orchestrate_task_cycle task-pack" \
  --root . apply-mutation --plan create-plan.json --render
```

Use the returned fields directly:

- `pack_path` → `pack_ref`
- `creation_snapshot.creation_snapshot_ref` → `pack_creation_snapshot_ref`
- `creation_snapshot.creation_snapshot_file_sha256` → `pack_creation_snapshot_sha256`
- `creation_snapshot.creation_snapshot_canonical_sha256` → `pack_creation_canonical_sha256`
- `pack_mutation_receipt.after_pack_sha256` → the promotion `before_pack_sha256`
- returned after item IDs/order/current item → the promotion coherence precondition

Compute the task digest with `sha256sum task.md`. The deterministic task snapshot ref is:

```text
.task/task_pack/task_snapshots/<pack_id>/<first 48 chars of item_id>-<first 48 chars of task_id>-<first 16 chars of task SHA-256>.md
```

Issue contemporaneous initial-selection authority. Set `issued_at` and `effective_at` no later than the selection receipt's `created_at`:

```json
{
  "schema_version": 1,
  "receipt_id": "authr-R",
  "receipt_kind": "operation_authority",
  "operation": "task_pack.initial_selection",
  "decision": "allowed",
  "basis_temporality": "contemporaneous_selection_authority",
  "issued_at": "2026-01-01T00:05:00+00:00",
  "effective_at": "2026-01-01T00:05:00+00:00",
  "subject": {
    "pack_ref": ".task/task_pack/pack-P.json",
    "pack_creation_snapshot_ref": ".task/task_pack/creation_snapshots/<returned-name>.json",
    "pack_creation_snapshot_sha256": "<returned file SHA-256>",
    "initial_item_id": "item-I",
    "initial_order": 1,
    "task_id": "task-T",
    "task_snapshot_ref": ".task/task_pack/task_snapshots/pack-P/item-I-task-T-<task-sha-prefix>.md",
    "task_snapshot_sha256": "<task SHA-256>"
  },
  "authority_basis": {
    "policy_ref": ".agent_goal/agent_authority.md",
    "source_kind": "explicit_current_user_instruction",
    "source_id": "instruction-I",
    "source_evidence_ref": ".task/authorization/instruction-I.md",
    "integrity_status": "verified"
  },
  "historical_effect": {
    "historical_selection_authority_status": "verified",
    "historical_authority_verdict": "pass",
    "retroactive_claim_allowed": false
  },
  "allowed_effects": ["promote_first_pack_item"],
  "forbidden_effects": [
    "promote_successor",
    "change_acceptance",
    "claim_semantic_progress"
  ]
}
```

```bash
PYTHONPATH="${CODEX_HOME:-$HOME/.codex}/skills/manage-agent-authority/scripts" python3 -B -m manage_agent_authority receipt \
  --root . issue --plan initial-authority-plan.json \
  --output .task/authority_receipts/authr-R.json
```

Submit the first promotion with the returned receipt digest:

```json
{
  "pack_disposition": "promote_next_item",
  "pack_path": ".task/task_pack/pack-P.json",
  "item_id": "item-I",
  "task_id": "task-T",
  "task_path": "task.md",
  "promotion_origin": "bootstrap_initial_selection",
  "reason": "bounded reason code",
  "initial_selection_receipt": {
    "schema_version": 1,
    "pack_ref": ".task/task_pack/pack-P.json",
    "pack_creation_snapshot_kind": "workspace_file",
    "pack_creation_snapshot_ref": ".task/task_pack/creation_snapshots/<returned-name>.json",
    "pack_creation_snapshot_sha256": "<returned file SHA-256>",
    "pack_creation_canonical_sha256": "<returned canonical SHA-256>",
    "pack_creation_canonicalization_version": 1,
    "creation_snapshot_state": "pre_selection",
    "initial_item_id": "item-I",
    "initial_order": 1,
    "task_id": "task-T",
    "task_snapshot_ref": ".task/task_pack/task_snapshots/pack-P/item-I-task-T-<task-sha-prefix>.md",
    "task_snapshot_sha256": "<task SHA-256>",
    "authority_receipt_ref": ".task/authority_receipts/authr-R.json",
    "authority_receipt_sha256": "<authority receipt SHA-256>",
    "authority_mode": "contemporaneous_selection_authority",
    "historical_selection_authority_status": "verified",
    "selection_reason": "bounded reason code",
    "created_at": "2026-01-01T00:06:00+00:00"
  },
  "pack_coherence": {
    "schema_version": 1,
    "canonical_pack_ref": ".task/task_pack/pack-P.json",
    "before_pack_sha256": "<create result after_pack_sha256>",
    "declared_before_item_ids": ["item-I", "item-J"],
    "declared_before_order": ["item-I", "item-J"],
    "declared_current_item": "item-I",
    "proposed_after_item_ids": ["item-I", "item-J"],
    "proposed_after_order": ["item-I", "item-J"],
    "mutation_kind": "promote"
  }
}
```

Run `apply-mutation --dry-run`, inspect `status=dry_run`, then rerun without `--dry-run`. The helper creates the deterministic task snapshot and publishes one promotion.

The optional one-call `create_pack.initial_selection` shape uses the same inline receipt. Reserve it for an orchestrator that can precompute the exact planned creation body, including defaults and the create mutation row. The two-transaction path above avoids that precomputation and is the general operator path.

If any create+selection validation fails before canonical publication, the helper removes only content-addressed creation/task evidence created by that call. It never removes pre-existing evidence. If canonical publication succeeds but rendering fails, preserve the pack and its bound evidence.

`apply-mutation --dry-run` validates the proposed create/selection state and reports `status=dry_run` without leaving a pack, render, creation snapshot/receipt, or task snapshot. The same no-durable-artifact rule applies to promotion dry-runs.

## Replacement first selection

When a clean successor replaces the unique active pack and its first item must be selected immediately, use one `pack_disposition: replace_pack` plan with an `initial_selection` object that follows the same receipt contract above. Do not supersede, create, and promote through three independent writes.

Precompute the successor creation body only after setting deterministic `created_at` and `updated_at`. At apply time, exact `task.md` must exist at the receipt-bound path and its byte SHA-256 must match the planned task snapshot, prospective preflight digest, and exact authority subject. The helper hash-verifies and snapshots those task bytes; `task.md` publication is outside the replacement transaction and is never implied by a successful pack receipt.

For prepublication dry-run while canonical `task.md` is absent or still contains the predecessor task, place the exact prospective bytes in a bounded noncanonical workspace staging file and add both fields to the same final plan:

```json
{
  "initial_selection": {
    "task_path": "task.md",
    "prospective_task_ref": ".task/prepublication/<opaque-id>.md",
    "prospective_task_sha256": "<64 lowercase hex>"
  }
}
```

First dry-run the replacement without selection to derive the creation identity, then construct the task-snapshot subject from the staged digest and issue the exact one-shot authority receipt. Run the complete final plan with `--dry-run`; the helper uses staging bytes for validation but records canonical `task_path`. After pass, overwrite/publish `task.md` with byte-identical staged bytes and apply the same plan. Apply reads canonical `task.md` and rejects any staging mismatch. Keep staging through apply, then delete it only after the committed replacement receipt validates. An unused authority receipt proves no selection and cannot authorize a different subject.

Dry-run the exact full replacement plan and require `findings: []` with no helper-owned pack/snapshot/journal/receipt or lifecycle residue; the declared staging file and unused subject-bound authority receipt are preparation evidence. Apply must reuse the byte-identical plan, successor timestamps, task bytes, creation-snapshot binding, and authority receipt input. If any digest or timestamp changes between dry-run/authority issue and apply, discard the stale prospective binding, rerun dry-run, and issue authority for the new exact subject. Do not patch the authority subject or creation snapshot after publication.

The replacement completion receipt covers only the predecessor/successor task-pack store and helper-owned renders, creation/task snapshots, journal, and receipt. It does not cover the pre-existing `task.md`, a `past_task` archive, `.task/index.*`, schema/issue state, Git staging, or a commit. If the helper reports a pending prepare journal, run `recover-replacement` to forward-complete that exact plan before any other pack mutation; do not recreate or truncate it.

## Existing-pack normalization

Use `normalize_initial_selection_provenance` only when the first item is already selected and lifecycle semantics must remain unchanged. Supply the same receipt fields as above, plus:

- `pack_creation_snapshot_kind=git_blob` with exact `pack_creation_git_commit`, `pack_creation_git_path`, and `git:<commit>:<path>` ref; or a durable workspace creation snapshot.
- `creation_snapshot_state=created_with_initial_selection` only when immutable legacy creation evidence already contains the first selection.
- operation-authority receipt operation `task_pack.normalize_initial_selection`.
- `authority_mode=current_ratification`, historical status `unverifiable_before_ratification`, and historical verdict `partial` for a present approval of an older selection.
- current `pack_coherence` version 1 with exact pack ref, before hash, item IDs/order/current item, unchanged proposed IDs/order, and mutation kind.

Complete outer plan:

```json
{
  "action": "normalize_initial_selection_provenance",
  "pack_disposition": "normalize_initial_selection_provenance",
  "pack_path": ".task/task_pack/pack-P.json",
  "item_id": "item-I",
  "promotion_origin": "bootstrap_initial_selection",
  "reason": "normalize provenance without historical rewrite",
  "initial_selection_receipt": {
    "schema_version": 1,
    "pack_ref": ".task/task_pack/pack-P.json",
    "pack_creation_snapshot_kind": "git_blob",
    "pack_creation_snapshot_ref": "git:<full-commit>:.task/task_pack/pack-P.json",
    "pack_creation_snapshot_sha256": "<Git blob byte SHA-256>",
    "pack_creation_canonical_sha256": "<canonicalized Git blob SHA-256>",
    "pack_creation_canonicalization_version": 1,
    "pack_creation_git_commit": "<full-commit>",
    "pack_creation_git_path": ".task/task_pack/pack-P.json",
    "creation_snapshot_state": "created_with_initial_selection",
    "initial_item_id": "item-I",
    "initial_order": 1,
    "task_id": "task-T",
    "task_snapshot_ref": ".task/task_pack/task_snapshots/pack-P/snapshot-T.md",
    "task_snapshot_sha256": "<task snapshot SHA-256>",
    "authority_receipt_ref": ".task/authority_receipts/authr-N.json",
    "authority_receipt_sha256": "<authority receipt SHA-256>",
    "authority_mode": "current_ratification",
    "historical_selection_authority_status": "unverifiable_before_ratification",
    "selection_reason": "bounded reason code",
    "created_at": "<original promoted_at>"
  },
  "pack_coherence": {
    "schema_version": 1,
    "canonical_pack_ref": ".task/task_pack/pack-P.json",
    "before_pack_sha256": "<current canonical pack SHA-256>",
    "declared_before_item_ids": ["item-I", "item-J"],
    "declared_before_order": ["item-I", "item-J"],
    "declared_current_item": "item-J",
    "proposed_after_item_ids": ["item-I", "item-J"],
    "proposed_after_order": ["item-I", "item-J"],
    "mutation_kind": "normalize_initial_selection_provenance"
  }
}
```

Find the immutable introduction commit and materialize its exact bytes:

```bash
git log --diff-filter=A --format=%H -- .task/task_pack/pack-P.json
git show <full-commit>:.task/task_pack/pack-P.json > /tmp/pack-P-creation.json
sha256sum /tmp/pack-P-creation.json
```

Compute both canonical digests through the public helper instead of recreating its rules:

```bash
PACK_TOOL="${CODEX_HOME:-$HOME/.codex}/skills/orchestrate-task-cycle/python3 -m orchestrate_task_cycle task-pack"
python3 -B - "$PACK_TOOL" /tmp/pack-P-creation.json <<'PY'
import importlib.util
import json
import pathlib
import sys

tool_path = pathlib.Path(sys.argv[1])
json_path = pathlib.Path(sys.argv[2])
spec = importlib.util.spec_from_file_location("task_pack_queue_contract", tool_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print(module.canonical_pack_sha256(json.loads(json_path.read_text(encoding="utf-8"))))
PY
python3 -B - "$PACK_TOOL" .task/task_pack/pack-P.json <<'PY'
import importlib.util
import json
import pathlib
import sys

tool_path = pathlib.Path(sys.argv[1])
json_path = pathlib.Path(sys.argv[2])
spec = importlib.util.spec_from_file_location("task_pack_queue_contract", tool_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print(module.canonical_pack_sha256(json.loads(json_path.read_text(encoding="utf-8"))))
PY
```

Canonicalization recursively removes `created_at`, `updated_at`, `timestamp`, `promoted_at`, `completed_at`, and every `mutation_log`; it then JSON-encodes with sorted keys, compact separators, UTF-8/non-ASCII preservation, and hashes those bytes with SHA-256.

Issue `task_pack.normalize_initial_selection` authority using the same exact subject, `allowed_effects=["append_initial_selection_normalization_provenance"]`, `basis_temporality=current_ratification`, historical status `unverifiable_before_ratification`, verdict `partial`, and `retroactive_claim_allowed=false`. Validate it with `--selected-at <original promoted_at>`, dry-run the normalization plan, then apply it.

The mutation may append only first-item provenance and one mutation-log row. It must preserve item IDs/order/status, acceptance, result, completion, current item, successor promotion, existing promotion fields, task bytes, and all semantic/readiness verdicts.

Literal replay of the same normalized receipt is a validated `already_normalized` no-op even when the original before hash is now stale. A different receipt for the bound first item is a conflict. A new mutation after unrelated pack changes still requires fresh coherence.

## Authority boundary

- Issue and validate receipts through `$manage-agent-authority`; pass both path and SHA-256.
- Reject bare refs, unknown source kinds, stale policy/source/receipt hashes, subject mismatch, backdating, advice/lifecycle-result authority, and body-bearing metadata.
- Current ratification authorizes the provenance append now. It never changes the historical verdict to pass.
- Retrospective assessment may verify an immutable contemporaneous authority record for normalization; it cannot create permission or authorize a new initial selection.
