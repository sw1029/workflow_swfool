---
name: build-validation-set-with-agents
description: Build reusable validation-set assets with source tracing, oracle manifests, split manifests, leakage checks, label adjudication, and no-overclaim controls. Use when a task needs to plan, create, refresh, freeze, or consume validation sets for extractors, parsers, classifiers, evaluators, KG/data pipelines, regression suites, sampled-real evidence preflights, or when `$orchestrate-task-cycle` routes `validation_set_plan` or `validation_set_build`.
---

# Build Validation Set With Agents

## Overview

Use this skill to produce validation assets, not completion verdicts. Keep `$validate-task-completion` as the final task gate and keep behavior-changing code/test/script changes owned by `$task-md-agent-governance`.

The skill may create or update `.validation/sets/`, `.validation/candidates/`, `.validation/registry.jsonl`, and cycle-local `.task/validation_set/` evidence. It must not edit implementation source, tests, runtime/build/CI config, or validator code; route those changes to `$task-md-agent-governance`.

## Modes

Use `plan` mode before implementation when a task needs evaluation criteria without exposing holdout labels. Produce task family, failure taxonomy, oracle strategy, split strategy, leakage policy, label visibility policy, source boundary, and no-overclaim constraints.

Use `build` mode after run/output evidence exists, or when the task is explicitly a validation-set construction task. Produce or refresh manifests, items, labels, oracles, splits, leakage reports, disagreement reports, and a validation-set root.

Use `consume` mode when an existing validation set should be run against current outputs. Execute deterministic oracles with `scripts/run_validation_oracles.py` when applicable and return evidence paths for `$run-task-code-and-log` or `$validate-task-completion`.

Use `blocked_or_candidate_only` when admissible source evidence is absent. Preserve the blocker explicitly instead of promoting fixture, synthetic, or metadata-only records into sampled-real or gold evidence.

When normalized acceptance provides `acceptance_scenarios`, include scenario coverage in plan/build/consume modes. Each scenario needs at least one fixture or live run whose scalar inputs satisfy the premise predicate and whose oracle/assertion checks the expected terminal state. Do not count tests that never satisfy the premise as scenario coverage.

When normalized acceptance or caller packets provide Part K lineage/comparison fields, plan or build reusable regression items for those contracts when the task asks for validation assets: stale `expectation_anchor` versus current `designated_baseline`, missing/unknown `parity_axes`, failed `gating` adoption axes, `majority_vote_adoption` without axis classification, `resolution_downgrade` from id/set/intersection evidence to a surrogate, and `report_key_divergence` inside one report. Keep fixture payloads scalar/id-only and leave domain axis definitions to adapters.

## Required Boundaries

- Treat `.agent_goal/*.md` as goal truth only when actually used. Treat `.agent_advice/` as non-GT direction evidence and record disposition.
- Preserve source class. Never promote `test_fixture`, `synthetic_fixture`, `sampled_real_metadata`, or `local_dataset_candidate` into `sampled_real_positive_evidence` or `real_reviewed_work` without explicit admissible evidence.
- Do not persist raw body text, provider bodies, full source text, private content, or large copyrighted excerpts in durable validation artifacts. Store locators, hashes, spans, and bounded snippets only when authority permits.
- Default agent-generated semantic sets to `quality_tier: candidate` or `silver`; set `not_gold: true` unless human-reviewed evidence or a fully deterministic authoritative oracle proves otherwise.
- Do not pass sealed holdout labels to implementation workers. If true sealing is impossible in a shared workspace, report `sealed_holdout_status: quasi_sealed` or `not_sealed`.
- Keep validation assets separate from completion reports: reusable sets live under `.validation/sets/`; cycle-local results live under `.task/validation_set/`; completion validation reports stay under `.task/validation/`.

## Workflow

1. Load the task packet, authority policy, actual GT used, active advice packet, schema/contract summaries, task_miss/issue validation gaps, prior validation registry, and run/output evidence when available.
2. Decide route: `not_applicable`, `plan`, `build`, `refresh`, `consume`, or `blocked_or_candidate_only`.
3. In `plan` mode, write or return only public evaluation criteria: task family, failure taxonomy, source-class boundary, oracle feasibility, split policy, leakage policy, and label visibility policy.
4. In `plan` mode, for every `acceptance_scenarios` record, state the required premise-satisfying input class, expected terminal state, and acceptable evidence source (`fixture` or `live_run`). If no admissible premise-satisfying input can be created, return `scenario_uncovered` and the missing condition.
5. In `build` mode, sample source-linked candidate items, run independent labeler passes when semantic labels are needed, adjudicate disagreements, prefer deterministic/executable oracles, create splits, run leakage checks, and freeze a root hash. For scenario items, mark `premise_satisfied=true` only when the fixture/run inputs actually meet the predicate.
6. In `consume` mode, run existing deterministic oracles and report pass/fail counts by failure taxonomy, split, source class, oracle type, and scenario coverage when applicable.
7. In `plan`, `build`, or `consume` mode for Part K contracts, report whether each lineage/comparison fixture covers the intended contract class: expectation rebaseline, parity-axis coverage, gating-axis adoption rejection, resolution restoration, or duplicate-key divergence. Do not claim task completion from the fixture; hand the result to `$validate-task-completion`.
8. Validate artifacts with `scripts/validate_validation_set.py`; if a root is produced, write it with `scripts/freeze_validation_set_root.py`.
9. Return a compact result packet with required fields and no-overclaim flags.

## Result Packet

Return these fields when applicable:

- `task_id`
- `cycle_id`
- `validation_set_id`
- `validation_set_status`: `complete`, `partial`, `blocked`, `not_applicable`, or `candidate_only`
- `quality_tier`: `candidate`, `silver`, `human_review_required`, or `gold`
- `not_gold`
- `item_count`, `label_count`, `oracle_count`
- `source_class_distribution`
- `label_type_distribution`
- `oracle_type_distribution`
- `split_manifest_path`
- `oracle_manifest_path`
- `leakage_report_path`
- `disagreement_report_path`
- `validation_set_root_path`
- `sealed_holdout_status`
- `scenario_coverage`
- `scenario_uncovered`
- `acceptance_inversion_candidate`
- `expectation_lineage_coverage`
- `comparison_parity_coverage`
- `adoption_gating_coverage`
- `resolution_downgrade_coverage`
- `report_key_divergence_coverage`
- `no_overclaim_flags`
- `forbidden_promotions`
- `blockers`
- `evidence_paths`
- `used_goal_truth`
- `used_advice` or `advice_handling_rationale`

If `validation_set_status` is blocked, include `blocked_reason` and the exact missing source/authority/oracle condition. If `quality_tier` is `gold`, include human-reviewed or fully deterministic authoritative evidence.

For scenario coverage, include `acceptance_scenario_id`, `premise_satisfied`, `expected_terminal_state`, `observed_terminal_state`, `evidence_path`, and `oracle_id`. If a changed or generated test asserts a non-expected terminal state for a premise-satisfying input, set `acceptance_inversion_candidate=true` for `$validate-task-completion`; do not hide it behind overall green status.

If a producer artifact or `observed_producer_claim` reports a residual blocker that directly contradicts the scenario's expected terminal state, copy only the scalar blocker summary into the scenario item as `acceptance_inversion_candidate=true` plus evidence path. Do not treat the producer report as authoritative coverage; use it to force scenario review or code/contract repair.

## Resources

Read [validation-set-contract.md](references/validation-set-contract.md) before writing or validating manifests, items, labels, roots, or cycle-local result packets.

Read [oracle-taxonomy.md](references/oracle-taxonomy.md) before choosing oracle types or interpreting oracle results.

Read [split-policy.md](references/split-policy.md) before creating dev/regression/public/sealed splits or deciding label visibility.

Read [leakage-policy.md](references/leakage-policy.md) before running leakage/decontamination checks or handling raw/source body boundaries.

Read [label-adjudication.md](references/label-adjudication.md) before using multiple labeler agents, resolving disagreements, or claiming semantic quality.

Use these scripts when their operation applies:

- `scripts/build_validation_set.py`: package bounded candidate JSONL into a validation-set directory.
- `scripts/validate_validation_set.py`: validate contract fields and no-overclaim guardrails.
- `scripts/run_validation_oracles.py`: run simple deterministic oracle manifests over item records.
- `scripts/leakage_check.py`: detect duplicate IDs, duplicate source hashes, missing label targets, and forbidden raw-body fields.
- `scripts/freeze_validation_set_root.py`: hash manifest/items/labels/oracles/splits/leakage reports into a root file.
