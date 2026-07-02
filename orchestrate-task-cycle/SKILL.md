---
name: orchestrate-task-cycle
description: "Run the governed repository task workflow cycle: ensure `task.md`, resolve `.agent_goal/agent_authority.md`, consume repo-local `.codex/skills` adapters as compact non-GT packets including optional `code_convention_contract`, plan/build validation assets through `$build-validation-set-with-agents`, route implementation through `$task-md-agent-governance`, audit code structure and semantic modularity before execution, log execution, run single-agent qualitative review, audit loopback progress including semantic structure metrics, refresh schemas, derive the next task/task-pack transaction with fixed `xhigh`, optionally schedule repo-local adapter creation/update through `$skill-creator`, preserve one active `task.md`, enforce blocker/input-delta loop breakers and terminal state, index artifacts with fixed `medium`, validate progress axes and structure high-water, track issues, commit coherent partial or complete changes with fixed `low`, report in Korean, and keep the orchestrator summary-first."
---

# Orchestrate Task Cycle

## Overview

Use this skill to run one governed repository task cycle from task discovery through implementation routing, execution, review, loopback, next-task derivation, validation, issue tracking, Git finalization, dashboard/report rendering, and closeout.

The main agent is the coordinator. Each called skill owns its own implementation, validation, logging, indexing, schema, issue, and commit behavior. Keep the orchestrator summary-first: pass compact packets, IDs, paths, verdicts, blockers, and changed-file lists rather than loading implementation bodies into the main session.

## Reference Map

Read these first-level references only when the corresponding part of the cycle is active:

- [workflow-routing.md](references/workflow-routing.md): full phase order, detailed procedure, routing table, transition rules, worker reasoning/model policy, helper-script hooks, ordering rules, and failure handling.
- [workflow-interface-contracts.md](references/workflow-interface-contracts.md): skill handoff surfaces, packet ownership, required fields, helper-script inputs/outputs, fail-closed rules, and downstream consumers.
- [cycle-artifacts.md](references/cycle-artifacts.md): ledger, result-contract, visible-increment, validation-scope, evidence-cache, dashboard/profile, and running-execution artifact contracts.
- [repo-local-skill-adapters.md](references/repo-local-skill-adapters.md): repository-local `.codex/skills/` adapter scan, consumption, creation/update routing, validation, and `$skill-creator` compliance.
- [anti-loop-progress-gates.md](references/anti-loop-progress-gates.md): loopback progress gates, output-delta policy, provenance-hardened root-cause actionability, adapter mandate, cumulative goal-distance stalls, acceptance reachability, oracle/metric validity, gate satisfiability/self-check, terminal quiescence, terminal escalation, and no-overclaim boundaries.
- [task-pack-workflow.md](references/task-pack-workflow.md): optional `.task/task_pack` queues, pack mutation rules, positive input deltas, and terminal blocker shape.
- [code-structure-audit.md](references/code-structure-audit.md): generated/changed code size and responsibility-boundary audit policy.
- [cycle-report-template.md](references/cycle-report-template.md): required Korean final-report field order.

Do not add README, changelog, quick-reference, or auxiliary process documents. Put future detailed rules in the relevant `references/` file and link them here.

## Core Invariants

- Preserve one active `task.md`. Use task packs only as planning state; a pack item becomes executable only after `$derive-improvement-task` promotes it into `task.md`.
- Route all behavior-changing implementation edits through `$task-md-agent-governance`. The orchestrator and non-governance skills must not patch source files, tests, notebooks, runtime/build/CI config, or behavior-changing scripts.
- Treat `.agent_goal/*.md` as the only long-term goal truth. Treat `.agent_advice/` and repo-local `.codex/skills/` adapters as non-GT direction/capability evidence.
- Keep repo-specific code conventions in repo-owned files or adapters. Pass `code_convention_contract` into governance, code-structure audit, loopback, derive, and validation when available; when absent, keep convention findings warn-only and do not invent project-specific thresholds, kernel paths, naming rules, or dependency DAGs.
- When a loopback domain adapter is registered by declaration or conventional path, pass it into `$audit-cycle-loopback` and preserve `adapter_loaded`/`adapter_path` in the packet. A registered-but-unloaded adapter is `adapter_wiring_defect` and must route to wiring/load correction, not adapter absence.
- Preserve normalized acceptance-envelope contracts, producer-claim downgrades, adapter-collapsed root/dominant-parameter keys, and primary-metric C4 trigger fields across handoffs when supplied. These are in-place revisions of existing acceptance, progress, root-cause, and chain-stall decisions; they are not new authority, new gates, or permission to weaken acceptance.
- Resolve authority through `$manage-agent-authority` before derivation, implementation delegation, validation, reporting, or external/API behavior.
- Keep validation-set assets under `.validation/`; do not treat validation-set production as completion validation.
- Distinguish `validation_verdict`, `progress_verdict`, `progress_kind`, and output-delta-derived `effective_progress_kind`.
- Do not treat `running` execution as `success`, `passed`, or `complete` unless the task explicitly defines startup/heartbeat evidence as sufficient.
- Report user-facing cycle updates, dashboards, and final reports in Korean while preserving commands, paths, IDs, hashes, schema names, and canonical status tokens exactly.

## Phase Flow

Run the canonical phase order from [workflow-routing.md](references/workflow-routing.md). The high-level order is:

```text
context -> ledger_init -> authority -> acceptance -> repo_skill_adapter_scan -> route_plan -> validation_set_plan -> governance -> result_contract -> repo_skill_adapter_validate -> ledger_append -> code_structure_audit -> run -> qualitative_review -> loopback_audit -> validation_set_build -> schema_pre_derive -> visible_increment -> repo_skill_gap_analysis -> derive -> schema_post_derive -> index -> validate -> issue -> commit -> dashboard -> report -> closeout_commit
```

If `task.md` is absent, follow the initial-task route in [workflow-routing.md](references/workflow-routing.md): resolve authority, refresh schema contracts when relevant, derive the initial task with fixed `xhigh`, write the required `## Execution Environment` section, reconcile schema contracts again, then resume the normal cycle from route planning.

## Coordination Rules

Before each major subskill call, render the applicable packet with `scripts/render_subskill_packet.py`, validate the transition with `scripts/validate_cycle_transition.py`, and pass blockers/warnings to the owning skill. Validate important subskill results with `scripts/result_contract.py`, using `warn` by default and `block` for final report, running-state, issue closure, candidate deletion, task-pack promotion provenance, and commit gates.

Use [workflow-interface-contracts.md](references/workflow-interface-contracts.md) to determine producer/consumer ownership for `gate_satisfiability`, `failure_autopsy_packet`, `qualitative_review_packet`, `anti_loop_progress_gate`, `loop_breaker_packet`, `terminal_escalation_gate`, `terminal_blocker`, `repo_skill_adapter_packet`, and `repo_skill_gap_packet`.

Before `$derive-improvement-task`, pass the portfolio, output-delta, failure-autopsy, code-structure, validation-set, task-pack, repo-adapter, loop-breaker, terminal, and anti-loop packets described in [workflow-interface-contracts.md](references/workflow-interface-contracts.md). Apply [anti-loop-progress-gates.md](references/anti-loop-progress-gates.md) when cycles are safe but stationary, metadata-only, repeated, sealed, or terminal.

Use fixed routing requirements:

- `$task-md-agent-governance`: code analysis at least `high`; important review `xhigh`; code-writing workers on `model: gpt-5.5` with `reasoning_effort: medium` by default or `high` for high-reliability core logic.
- `$derive-improvement-task`: fixed `reasoning_effort: xhigh` for goal/convention alignment, task_miss analysis, issue-fit, improvement, synthesis, candidate prioritization, schema planning, and ID-consistency agents.
- `$manage-task-state-index`: fixed `reasoning_effort: medium` for ID scan, audit, link repair, lifecycle transition recording, and optional ID insight agents.
- `$repo-change-commit`: fixed `reasoning_effort: low` for Git status classification, staging, commit readiness, and commit creation.

## Completion And Reporting

Run `$validate-task-completion` before issue tracking, implementation commit, final report, or closeout commit. Validation must report `validation_verdict`, `progress_verdict`, and `progress_axes` when available. `progress_verdict: advanced` requires `terminal_outcome_changed=true` or strict changed-and-semantic observed output delta.

Call `$manage-implementation-issues` after validation and before `$repo-change-commit`. In a Git worktree, explicitly invoke `$repo-change-commit` after validation for coherent implementation/workflow changes; a raw `git status` check is not a substitute. A `partial` verdict can still produce a checkpoint commit when the changed set is coherent and blockers are named.

Use [cycle-report-template.md](references/cycle-report-template.md) for the Korean final report. Use `complete_verified` only when validation verdict is `passed`, progress verdict is `advanced`, and no blocker remains; otherwise use `not_complete`.

After report/dashboard artifacts are written, run the closeout commit phase when applicable. Do not regenerate closeout/dashboard/report/recheck artifacts merely to reconfirm terminal quiescence or G2 terminal escalation.

## Failure Handling

Preserve evidence and route remediation to the owning skill:

- Missing `task.md`: derive the initial task before governance.
- Governance blocker: stop before unsafe execution and keep task_miss/index evidence.
- Execution failure: log through `$run-task-code-and-log`, collect scalar-safe failure autopsy when possible, index evidence, then validate as `partial` or `failed`.
- Running execution: log monitor/stop details, index the active run, defer final-output-dependent derivation or completion claims.
- Review, validation-set, schema, issue, adapter, or Git failure: record the concrete blocker and continue only through safe downstream evidence-preserving steps.
- ID audit high-severity findings: do not delete artifacts or report completion unless `$validate-task-completion` resolves or downgrades them.
