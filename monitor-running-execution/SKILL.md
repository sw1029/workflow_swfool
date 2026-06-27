---
name: monitor-running-execution
description: "Monitor long-running task executions recorded by `$run-task-code-and-log`. Use when a cycle has `running` status to record PID/session/job ID, log path, heartbeat/startup evidence, monitor command, stop command, and remaining validation without treating the run as success."
---

# Monitor Running Execution

## Overview

Use this skill to keep long-running execution state explicit while preserving the rule that `running` is not `success`.

Use `/home/swfool/.codex/skills/orchestrate-task-cycle/scripts/monitor_running_execution.py` for deterministic checks.

## Workflow

1. Read the run result or ledger event that reported `running`.
2. Verify that PID/session/job ID, log path, monitor command, stop command, startup/heartbeat evidence, and remaining validation are present.
3. Check process/log heartbeat only when safe and local.
4. Append a monitor event to the cycle ledger.
5. Report `running`, `completed`, `stale`, `missing_details`, or `not_running`.

## Guardrails

- Do not kill a process unless the user or task explicitly requested it.
- Do not mark completion unless final success criteria are met by evidence.
- Do not proceed to final-output-dependent derivation or commits from `running` alone.
