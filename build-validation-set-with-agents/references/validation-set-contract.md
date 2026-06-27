# Validation Set Contract

Use this contract for durable assets under `.validation/sets/<validation_set_id>/`.

## Required Files

- `validation_set_manifest.json`: set metadata, task linkage, quality tier, no-overclaim flags, and file paths.
- `validation_set_items.jsonl`: one JSON object per validation item.
- `validation_set_labels.jsonl`: zero or more label/adjudication records.
- `oracle_manifest.json`: oracle records or executable oracle references.
- `split_manifest.json`: split membership and label visibility.
- `leakage_report.json`: duplicate, contamination, source-class, and raw-body checks.
- `validation_set_root.json`: hashes that bind the above files.

## Manifest Fields

Require:

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
- `split_manifest_path`
- `leakage_report_path`

Recommended:

- `cycle_id`
- `failure_taxonomy`
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
- `preimage_hash`
- `expected_output_ref`
- `oracle_ids`
- `no_overclaim_flags`

Do not store `raw_body`, `provider_body`, `full_text`, `source_text`, `document_body`, or equivalent raw content fields.

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
