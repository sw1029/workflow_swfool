---
name: monitor-running-execution
description: "Monitor long-running task executions recorded by `$run-task-code-and-log`. Use when a cycle has `running` status to record PID/session/job ID, log path, heartbeat/startup evidence, monitor command, stop command, and remaining validation without treating the run as success."
---

# Monitor Running Execution

## Overview

Use this skill to keep long-running execution state explicit while preserving the rule that `running` is not `success`.

Use `${CODEX_HOME:-$HOME/.codex}/skills/orchestrate-task-cycle/scripts/monitor_running_execution.py` for deterministic checks.

## Workflow

1. Read the run result or ledger event that reported `running`.
2. Verify that PID/session/job ID, log path, monitor command, stop command, startup/heartbeat evidence, and remaining validation are present.
3. For task-cycle long-running branches, also verify `run_id`, `owner_task_id`, `launch_cycle_id`, `output_dir`, expected completion signal/artifacts, and residual/harvest validation linkage when available.
4. When the long run was launched because `unreachable_within_cycle=true`, verify that required scale, throughput evidence, cycle cap, residual original acceptance, and harvest validation plan remain linked. A launch or heartbeat does not consume the original domain acceptance.
5. When the launch packet includes Part M fields, verify that launch-manifest anchors, target scale, `harvest_contract_preflight`, `harvest_risk_accepted`, terminal disposition policy, and reharvest linkage remain attached to the monitor or harvest handoff. Do not replace launch-time anchors with the current task, current lane, or monitor task context.
6. Check process, tmux session, log heartbeat, and expected completion artifacts only when safe and local.
7. Append a monitor event to the cycle ledger as `step: run` with `event_kind: long_run_monitor`; do not create a noncanonical `monitor` phase.
8. Report `running`, `completed_pending_validation`, `stale`, `missing_details`, or `not_running`.
9. The orchestrator may finalize validation scope and run `$validate-task-completion` only to produce an honest `partial` or `failed` handoff for the current cycle. Preserve the same `run_id` and pending blocker; this partial validation is not permission to promote/derive a successor, close an issue, or create an implementation/closeout commit.

## Guardrails

- Do not kill a process unless the user or task explicitly requested it.
- Do not mark completion unless final success criteria are met by evidence.
- Do not proceed to final-output-dependent derivation or commits from `running` alone.
- Do not block partial handoff validation merely because terminal output is pending; block only pass/advanced/close consumption and successor promotion until harvest/final validation completes.
- Do not treat `completed_pending_validation` as success; it only means harvest validation should consume the terminal artifacts.
- Do not mark a cycle-unreachable target complete from long-run launch, startup, or heartbeat evidence. Preserve harvest validation, throughput/scale evidence, or explicit descope/terminal/escalation.
- Do not let a monitor task switch silently invalidate or redefine terminal harvest expectations. Preserve launch-manifest anchors and any explicit `harvest_risk_accepted` decision.
