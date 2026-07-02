# Code Structure Audit

Use this reference for the `code_structure_audit` phase in `$orchestrate-task-cycle`. This gate is read-only workflow evidence. It may recommend a moduleization, semantic consolidation, reuse extraction, or coupling-reduction task, but it must not create directories, move code, or patch implementation files.

## Purpose

Catch oversized generated code, mixed responsibilities, mechanical shards, duplicate helpers, hidden global coupling, and weak reuse signals immediately after `$task-md-agent-governance`, before execution normalizes the structure as acceptable. Preserve existing behavior by routing any refactor through the next `$task-md-agent-governance` cycle.

Use repo-owned convention data when available. `code_convention_contract` may come from a repo-local adapter packet, caller packet, or `.agent_goal/conventions.md` summary. It owns naming rules, depth/fan-out limits, kernel/reuse roots, dependency-layer direction, and forbidden patterns. If the contract is absent or unstructured, semantic convention findings are warn-only and must not block execution by themselves.

## Inputs

- Governance changed-file list when available.
- `git status --short` changed files as fallback.
- Current task ID and module/script context when available.
- Explicit exemptions for generated, vendor, migration, snapshot, lockfile, or data-only files.
- Optional `code_convention_contract` or `--convention-json` containing repo-owned code convention rules.

## Thresholds

Default thresholds:

- `soft_file_logical_loc`: 500
- `hard_file_logical_loc`: 900
- `soft_function_logical_loc`: 80
- `hard_function_logical_loc`: 140
- `soft_class_logical_loc`: 250
- `hard_class_logical_loc`: 420
- `soft_responsibility_cluster_count`: 3
- `hard_responsibility_cluster_count`: 4

Treat thresholds as advisory for legacy unchanged code. Treat them as gates for newly generated files or files materially expanded by the current governance step.

## Responsibility Clusters

Detect clusters conservatively from path names, symbol names, imports, and keyword evidence. Common clusters:

- `cli`
- `configuration`
- `provider_runtime`
- `io`
- `domain_transform`
- `schema_contract`
- `validation`
- `reporting`
- `persistence`
- `orchestration`

Multiple clusters are not automatically bad. A gate is justified when size thresholds and unrelated clusters combine in one changed file.

## Semantic Modularity Signals

Report scalar/symbol-level signals only. Do not persist raw source bodies.

- `mechanical_naming_signals`: numbered part/shard/chunk/section files, numeric-only stems, version-suffix files, or repo-forbidden patterns.
- `global_rebinding_signals`: global rebinding, `_binding` shims, prebind/reserved global tables, or import-time mutation bridges.
- `duplicate_symbol_name_count`: repeated public function/class names across changed files.
- `max_changed_tree_depth` and `max_changed_dir_fan_out`: structure burden from changed file placement.
- `reuse_root_import_ratio`: ratio of imports from repo-owned reuse/kernel roots when the convention contract names those roots.
- `max_file_logical_loc`: largest changed file logical LOC.

Use these fields to detect file-count-as-progress mistakes. Creating more files is not structural improvement unless an adapter or validation packet shows lower coupling, fewer mechanical shards, less duplication, better reuse, lower burden, or a named transition unlocked.

## Status Policy

- `pass`: no changed implementation file crosses soft thresholds.
- `warn`: soft threshold, mixed clusters, or warn-only semantic convention findings detected, but split is not required before completion.
- `refactor_required`: hard threshold, high mixed-responsibility risk, or enforced convention-contract violation detected. Execution may continue when safe, but validation, derive, issue tracking, and final reporting must carry the moduleization or semantic-refactor requirement.
- `blocked`: generated code is unsafe to execute, violates hard thresholds without a split plan, or mixes responsibilities in a way that can corrupt durable workflow/schema/task artifacts.
- `not_applicable`: no changed implementation source file was present. Record a concrete reason.

## Output Contract

Emit JSON with:

- `step: "code_structure_audit"`
- `task_id`
- `audit_status`
- `changed_files_scanned`
- `oversize_files`
- `thresholds`
- `responsibility_clusters`
- `semantic_structure_metrics`
- `semantic_structure_findings`
- `convention_conformance`
- `moduleization_required`
- `suggested_module_root`
- `responsibility_split_plan`
- `semantic_refactor_plan`
- `compatibility_constraints`
- `validation_scope_delta`
- `existing_debt_exemptions`
- `forbidden_raw_source_persisted: true`
- `evidence_paths`

`responsibility_split_plan` should name target modules and responsibilities, not implementation code. `compatibility_constraints` should preserve public APIs, CLIs, schemas, artifact paths, and tests that callers rely on.

`convention_conformance` should expose `code_convention_contract_status`, `enforcement`, `warn_only`, `status`, and checked axes. If `code_convention_contract_status=not_provided`, findings remain warn-only and downstream derive may schedule a repo-local adapter/convention-contract task instead of pretending generic rules are sufficient.

## Derive Handoff

When `moduleization_required=true`, pass the packet to `$derive-improvement-task`. The next task should normally be a bounded refactor task with:

- One stable module directory or package root.
- Responsibility-based modules.
- Semantic names instead of numbered shards or version suffixes.
- Reuse-before-create evidence for new shared helpers.
- Explicit dependency flow instead of global rebinding or hidden import-time mutation.
- Compatibility shims or unchanged public entry points when required.
- Focused validation profile: `current_only` for isolated refactors, `affected_chain` for shared APIs, `full_chain` only before readiness promotion or high-risk shared contract changes.

Do not count the audit itself as goal-productive progress. It is workflow quality evidence unless the subsequent governance cycle implements and validates the split.
