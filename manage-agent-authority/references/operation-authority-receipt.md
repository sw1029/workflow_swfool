# Operation Authority Receipt Contract

Use this compatibility contract only for a bounded operation whose authority was already resolved. Use [authority-v2-contract.md](authority-v2-contract.md) for new generic grants and leases. A receipt is non-GT evidence; it cannot expand active permissions or rewrite historical facts.

## Schema versions

- Validate schema v1 against the exact mutable `policy_ref` and `source_evidence_ref` digests recorded at issue time. Preserve this behavior for compatibility; do not silently reinterpret v1.
- Issue schema v2 with immutable `policy_snapshot_ref`/`policy_snapshot_sha256` and `source_snapshot_ref`/`source_snapshot_sha256`. Keep original source refs/digests as provenance, but validate authority against the immutable snapshots.
- Never convert an old v1 receipt to v2 unless the exact historical policy/source bytes are available as immutable contemporaneous evidence.

## Receipt body

```json
{
  "schema_version": 2,
  "receipt_id": "authr-R",
  "receipt_kind": "operation_authority",
  "operation": "task_pack.normalize_initial_selection",
  "decision": "allowed",
  "basis_temporality": "current_ratification",
  "issued_at": "RFC3339",
  "effective_at": "RFC3339",
  "subject": {
    "pack_ref": ".task/task_pack/pack-P.json",
    "pack_creation_snapshot_ref": "snapshot-C",
    "pack_creation_snapshot_sha256": "64 lowercase hex",
    "initial_item_id": "item-I",
    "initial_order": 1,
    "task_id": "task-T",
    "task_snapshot_ref": ".task/task_pack/task_snapshots/snapshot-T.md",
    "task_snapshot_sha256": "64 lowercase hex"
  },
  "authority_basis": {
    "policy_ref": ".agent_goal/agent_authority.md",
    "policy_sha256": "digest at issue",
    "policy_snapshot_ref": ".task/authorization/policy_snapshots/policy-D.md",
    "policy_snapshot_sha256": "64 lowercase hex",
    "source_kind": "explicit_current_user_instruction",
    "source_id": "instruction-I",
    "source_evidence_ref": ".task/authorization/instruction-I.md",
    "source_evidence_sha256": "digest at issue",
    "source_snapshot_ref": ".task/authorization/source_snapshots/source_approval-D.md",
    "source_snapshot_sha256": "64 lowercase hex",
    "integrity_status": "verified"
  },
  "historical_effect": {
    "historical_selection_authority_status": "unverifiable_before_ratification",
    "historical_authority_verdict": "partial",
    "retroactive_claim_allowed": false
  },
  "allowed_effects": ["append_initial_selection_normalization_provenance"],
  "forbidden_effects": [
    "change_item_status",
    "change_item_result",
    "change_item_completion",
    "change_current_item",
    "change_acceptance",
    "promote_successor",
    "claim_historical_authority_pass"
  ]
}
```

## Temporal modes

- `contemporaneous_selection_authority`: require immutable authority evidence effective no later than selection.
- `current_ratification`: permit only prospective bounded continuation; require historical verdict `partial`, status `unverifiable_before_ratification`, and `retroactive_claim_allowed=false`.
- `retrospective_evidence_assessment`: assess immutable historical evidence only; never create permission.

## Validation

- Require `receipt_kind=operation_authority`, `decision=allowed`, a supported operation, RFC3339 times, and a complete exact subject.
- Require workspace-relative regular evidence files and full SHA-256 bindings.
- Require the caller's expected subject to equal the receipt subject exactly.
- Pass `--selected-at <RFC3339>` for full temporal validation. Without it, return `temporality_binding_status=consumer_required` and require the mutation helper to check selection time.
- Allow current ratification only from `explicit_current_user_instruction`.
- Accept only `explicit_current_user_instruction`, `effective_authority_policy`, or `contemporaneous_authority_record` as closed source kinds.
- Allow retrospective normalization only from a verified immutable contemporaneous record.
- Reject advice, task completion, run/validation/issue results, silence, and unknown sources.
- Permit only the operation allowlist. Keep normalization provenance-only.
- Reject body-bearing or sensitive keys including raw prompts, quotes, transcript bodies/paths, source text, corpus metadata, credentials, tokens, and secrets.

## Use

Issue v2 prospectively:

```bash
PYTHONPATH="<skills-root>/manage-agent-authority/scripts" \
  python3 -m manage_agent_authority receipt issue \
  --root . --plan receipt-plan.json \
  --output .task/authority_receipts/authr-R.json
```

Validate by receipt ref and digest at mutation time. Pass both receipt path and SHA-256 to the consumer. Keep policy, snapshots, and one-shot receipts separate.
