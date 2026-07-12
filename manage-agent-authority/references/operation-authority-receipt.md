# Operation Authority Receipt Contract

Use this contract only for a bounded operation whose authority has already been resolved. A receipt is non-GT evidence; it cannot expand current permissions or rewrite historical facts.

## Receipt body

```json
{
  "schema_version": 1,
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
    "policy_sha256": "64 lowercase hex",
    "source_kind": "explicit_current_user_instruction",
    "source_id": "instruction-I",
    "source_evidence_ref": ".task/authorization/instruction-I.md",
    "source_evidence_sha256": "64 lowercase hex",
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

- `contemporaneous_selection_authority`: require authority evidence effective no later than selection.
- `current_ratification`: allow the bounded operation now; require historical verdict `partial`, historical status `unverifiable_before_ratification`, and `retroactive_claim_allowed=false`.
- `retrospective_evidence_assessment`: assess immutable historical evidence only; do not create a new permission.

## Validation

- Require schema version 1, `receipt_kind=operation_authority`, `decision=allowed`, a supported operation, RFC3339 times, and a complete subject.
- Require workspace-relative regular policy/source files and exact SHA-256 bindings.
- Require the caller's expected subject to equal the receipt subject exactly.
- Pass `--selected-at <RFC3339>` for complete temporal validation. Without it, the standalone validator returns `temporality_binding_status=consumer_required`; the consuming helper must then bind and check the original selection time before mutation.
- Allow current ratification only from `explicit_current_user_instruction`.
- Require a non-empty opaque `source_id` and one closed source kind: `explicit_current_user_instruction`, `effective_authority_policy`, or `contemporaneous_authority_record`.
- Allow `retrospective_evidence_assessment` only for normalization from an immutable contemporaneous authority record that verifies a historical pass; never use it to create permission.
- Reject advice, task completion, run, validation, issue results, and unknown source kinds as authority sources.
- Permit only the operation's allowlisted effects. For task-pack normalization, permit provenance append only.
- Reject sensitive or body-bearing keys such as `raw_prompt`, `prompt_body`, `quote`, `bounded_quote`, `instruction_text`, `user_message`, `transcript_body`, `transcript_path`, `source_text`, `credential`, `token`, and `secret` anywhere in the receipt.
- Keep opaque IDs, workspace-relative references, digests, enums, timestamps, and bounded reason codes only.

## Use

Issue after the authority decision, then pass both receipt path and SHA-256 to the consuming helper. Validate again at mutation time. Store policy and one-shot receipts separately; do not add receipts to the authority-policy template.
