# Validation Set Contract

Use this contract for durable assets under `.validation/sets/<validation_set_id>/`.

## Contents

- Required Files
- Status and Consumption
- Manifest, Item, Label, Oracle, Results, Leakage, and Root Fields
- Source Binding
- Finalization Record
- Atomic Output Safety
- Source Class Vocabulary

## Required Files

- `validation_set_manifest.json`: set metadata, task linkage, quality tier, no-overclaim flags, and file paths.
- `validation_set_items.jsonl`: one JSON object per validation item.
- `validation_set_labels.jsonl`: zero or more label/adjudication records.
- `oracle_manifest.json`: oracle records or executable oracle references.
- `oracle_results.json`: durable runner output bound to the exact item and oracle-manifest bytes.
- `split_manifest.json`: split membership and label visibility.
- `leakage_report.json`: duplicate, contamination, source-class, and raw-body checks.
- `validation_set_root.json`: hashes that bind the above seven contract files. Create it only after contract validation; verify it before consumption.

## Status and Consumption

- Use `candidate_only`, `partial`, or `blocked` while items, oracles, splits, or leakage evidence are empty or unevaluated.
- Use `complete` only after the `finalize` module command verifies at least one byte/hash-bound or authoritatively attested item, at least one executed passing oracle pair, exact counts, complete split membership, and a completed non-blocking leakage check.
- Let deterministic runners return `not_evaluated` when no runnable item-oracle pairs exist. Do not translate `not_evaluated` into pass/ok.
- Treat versionless legacy manifests as readable migration inputs only. Report `migration_required`; do not consume or freeze them.

## Manifest Fields

Require:

- `manifest_schema_version: 2`
- `validation_set_id`
- `task_id` when tied to a task
- `validation_set_status`
- `quality_tier`
- `not_gold`
- `created_at`
- `source_class_distribution`
- `item_count`
- `label_count`
- `oracle_count`
- `items_path`
- `labels_path`
- `oracle_manifest_path`
- `oracle_results_path`
- `split_manifest_path`
- `leakage_report_path`

Additionally require `finalization_record` when `validation_set_status` is `complete`. Generate it atomically with `python3 -m build_validation_set_with_agents finalize` under the skill package `PYTHONPATH`; direct status edits are invalid.

Require JSON booleans, not strings or integers, for `not_gold` and every other boolean field. Require non-negative JSON integers, not numeric strings or booleans, for counts.

Recommended:

- `cycle_id`
- `failure_taxonomy`
- `scenario_coverage`
- `expectation_lineage_coverage`
- `comparison_parity_coverage`
- `adoption_gating_coverage`
- `resolution_downgrade_coverage`
- `report_key_divergence_coverage`
- `no_overclaim_flags`
- `forbidden_promotions`
- `sealed_holdout_status`
- `used_goal_truth`
- `used_advice`
- `advice_handling_rationale`

## Item Fields

Require:

- `item_id`
- `source_class`
- `evidence_status`
- `source_ref` or `source_hash`
- `task_family` or `failure_taxonomy`

Recommended:

- `source_locator`
- `source_span_ref`
- `source_hash`
- `source_binding_type`
- `source_attestation`
- `preimage_hash`
- `expected_output_ref`
- `oracle_ids`
- `no_overclaim_flags`
- `acceptance_scenario_id`
- `premise_satisfied`
- `expected_terminal_state`
- `observed_terminal_state`
- `expectation_anchor`
- `designated_baseline`
- `expectation_lineage_stale`
- `parity_axes`
- `parity_axis_status`
- `adoption_axis_classification`
- `gating_axis_expected_pass`
- `required_evidence_resolution`
- `observed_evidence_resolution`
- `report_key_divergence_expected`

Do not store `raw_body`, `provider_body`, `full_text`, `source_text`, `document_body`, or equivalent raw content fields.

### Source Binding

Schema-v2 candidate records use one of:

- `local_file`: require a root-relative `source_ref` without parent traversal and a lowercase SHA-256 `source_hash`. Resolve after symlinks, require the file to remain inside the declared root, and rehash its current bytes during validation and root verification.
- `authoritative_attestation`: require an opaque/URI-style `source_ref`, item `source_hash`, and `source_attestation` containing JSON boolean `authoritative: true`, non-empty `authority_ref`, non-empty `attestation_ref`, and `attested_sha256` equal to the item hash.
- `opaque_candidate`: preserve remote or unavailable source intent, but never consume or finalize it until converted to an authoritative attestation.

Reject local absolute paths, `..` traversal, missing files, symlink escape, malformed hashes, and byte/hash mismatch. Candidate status does not excuse path or symlink escape.

Scenario items are coverage evidence only when `premise_satisfied=true` and an oracle or live-run result observes the expected terminal state. A fixture that does not satisfy the premise is not scenario coverage, even if its test passes.

Each manifest `scenario_coverage` record is a covered claim and therefore requires `premise_satisfied: true`, matching non-empty expected/observed terminal states, a root-relative `evidence_path` plus matching `evidence_sha256`, and an oracle ID. Resolve evidence inside the declared root after symlinks and hash its current bytes. Bind the record to an item with the same scenario ID and terminal states. A deterministic oracle predicate must explicitly reference both `expected_terminal_state` and `observed_terminal_state`; otherwise require an accepted authoritative human adjudication that records both values. A green oracle over unrelated fields is not scenario evidence. Put false-premise or unavailable cases in `scenario_uncovered`.

If a premise-satisfying item observes or asserts the opposite terminal state, set `acceptance_inversion_candidate=true` in the item or manifest so completion validation can route code/contract repair.

Part K validation items should be scalar/id-only. For expectation lineage, use anchor ids and supersede/designated-baseline status rather than raw artifacts. For parity/adoption, use abstract axis names and statuses, not model/backend-specific values. For resolution downgrade, record required and observed resolution classes. For report key divergence, record duplicate JSON paths and scalar values only.

## Label Fields

Require:

- `label_id`
- `item_id`
- `label_type`: `deterministic`, `executable`, `agent_consensus`, `human_reviewed`, or `reference`
- `label_status`: `candidate`, `accepted`, `rejected`, `needs_human_review`, or `blocked`

Recommended:

- `labeler_id`
- `adjudication_status`
- `confidence`
- `oracle_ids`
- `evidence_refs`

Agent-generated semantic labels are not gold by default.

For `human_reviewed`, require `human_reviewer_ref` and at least one bounded `evidence_refs` entry. A gold set must contain an accepted human-reviewed label with those references, or identify every authoritative oracle through `authoritative_oracle_ids`. Each identified oracle must be deterministic/executable, set `authoritative: true` as a JSON boolean, and provide non-empty `evidence_paths`. A truthy string such as `"true"` or `"false"` is never evidence.

To cover a required pair that the runner does not execute, require the label to additionally use `label_status: accepted`, JSON boolean `authoritative: true`, and `oracle_ids` containing that exact oracle ID. Coverage is pair-specific and cannot be inferred from another item or oracle.

## Oracle Manifest Fields

Require `validation_set_id` and an `oracles` list. Require each oracle to include `oracle_id`, `oracle_type`, `target`, and `description`. When `oracle_count` is present, require it to equal the list length exactly.

## Oracle Results Fields

Require schema-v2 manifests to bind `oracle_results.json`. Require:

- `oracle_results_schema_version: 1`
- `runner: run_validation_oracles.py`
- matching `validation_set_id`
- lowercase `items_sha256` and `oracle_manifest_sha256` matching the current artifact bytes
- `execution_status` and `status`
- exact `item_count`, `oracle_count`, `result_count`, and `failed_count`
- exact `required_pair_count`, `executed_pair_count`, and `unsupported_pair_count`, plus `unsupported_pairs`
- `results`, with every runnable item/oracle pair represented exactly once
- per result, canonical `item_content_sha256` and `oracle_definition_sha256`

Consumption requires `execution_status: completed`, `status: passed`, at least one runnable pair, zero failed results, no stale input hash, and coverage of every required pair. Recompute each supported deterministic predicate during validation and require exact stored status/failures; file-hash or per-result-hash edits cannot substitute for execution. Require an accepted authoritative human-reviewed label for every enumerated unsupported pair. A direct runner invocation without durable manifest-bound output is diagnostic only.

## Finalization Record

For `complete`, require deterministic finalization provenance containing:

- `finalization_schema_version: 1`
- `finalizer: finalize_validation_set.py`
- validation-set ID and `complete` status
- `manifest_state_sha256`
- exact hashes for items, labels, oracle manifest, oracle results, split manifest, and leakage report
- exact item/label/oracle/result counts and source/leakage/oracle status summaries
- canonical `finalization_sha256`

Recompute the full record during every consumable validation. Any manifest or bound-input change requires rerunning oracle execution when applicable and rerunning the finalizer.

## Leakage Report Fields

Require `execution_status: completed` before consumption, plus `status` (`ok`, `warn`, or `block`), `item_count`, `label_count`, and `findings`. Use `execution_status: not_evaluated` and a non-ok `status` when there are no items to inspect.

## Root Fields

Require `root_schema_version: 2`, `root_type`, validation-set metadata, `file_hashes`, `root_sha256`, and the root-relative root-file `path`. Bind exactly the manifest, items, labels, oracle manifest, oracle results, split manifest, and leakage report with non-null SHA-256 digests. Resolve every bound path inside the declared root after symlink resolution. Reject a missing file, path/symlink escape, malformed/null digest, metadata mismatch, changed file, or invalid bound validation set. On any integrity finding, return top-level `status: block`, `readiness: blocked`, and `validation_status: block`.

Schema-v1 roots may be read for migration diagnostics, but a legacy/versionless complete set cannot remain consumable or be newly frozen.

## Atomic Output Safety

Create JSON/JSONL child artifacts and frozen roots with exclusive random temporary files in the resolved output parent, fsync them, and atomically replace the final name. Never open a predictable PID-derived temporary path for writing. Refuse an escaping parent/output path or safely replace a child symlink itself without following it to an external target.

## Source Class Vocabulary

Use one of:

- `test_fixture`
- `synthetic_fixture`
- `sampled_real_metadata`
- `sampled_real_positive_evidence`
- `real_reviewed_work`
- `local_dataset_candidate`
- `external_metadata`
- `generated_candidate`

If a repository needs another class, document it in the manifest and schema contract before use.
