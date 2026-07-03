---
name: run-task-code-and-log
description: Execute user-specified task or issue-resolution code, commands, scripts, tests, notebooks, or run procedures exactly in the method the user names, then create a durable execution record through `$record-agent-work-log`. Use when the user asks Codex to actually run provided code or a specified command sequence and log the result; when `$manage-implementation-issues` needs verification evidence before closing or archiving an issue; when execution evidence such as command lines, exit status, output summary, artifacts, failures, shortcomings, or authorized long-running `running` status must be preserved in `.agent_log`; or when a reproducible task run needs a factual work log rather than only a chat summary.
---

# Run Task Code And Log

## Overview

Use this skill to run the code or command the user specified, capture the execution evidence, and immediately log the task through `$record-agent-work-log`.

The main value is traceability: what was intended, exactly how it was run, what happened, what files or outputs changed, and what remains incomplete.

Long-term execution is allowed when the user, `task.md`, an issue-resolution request, or an orchestrating skill explicitly authorizes it. In that case, the skill may log a durable `running` result instead of waiting indefinitely, but only after capturing enough evidence to monitor, resume, or stop the process later.

When task-state IDs are available, link the run evidence and log entry through `$manage-task-state-index`. If no ID context exists, still run and log exactly as requested.

## Efficiency And Idempotency

- Respect a task-declared validation profile when present:
  - `current_only`: run the current task command/validator and verify direct predecessor status or hash evidence; do not rerun the full historical chain.
  - `affected_chain`: rerun only prerequisites whose affected surfaces changed, plus the current command.
  - `full_chain`: rerun all named prerequisites. Use this only when the task, user, or orchestrator explicitly requires it.
- If a prerequisite manifest is supplied, prefer checking recorded path/status/hash evidence before rerunning unchanged prerequisite commands.
- Before creating a new timestamped `.agent_log` or task_miss-style execution artifact, check whether the same task ID, command/check path, relevant input hashes or artifact paths, exit status, and result summary already exist. If the evidence is identical, link or reference the existing artifact instead of creating a duplicate log.
- Create a fresh log when the run was intentionally fresh, inputs changed, output changed, exit status changed, stdout/stderr contains new material evidence, or the task explicitly requires a fresh execution artifact.
- Never use idempotent reuse to hide a failed rerun. If a command is executed and fails, log the failure even when an older passing log exists.

## Workflow

1. Parse the requested run.
   - Identify the task or issue-resolution intent, code or command to run, working directory, interpreter/runtime, environment, arguments, input files, expected outputs, issue ID or path when present, requested logging title, expected duration, and whether long-term execution is authorized.
   - Identify any validation profile (`current_only`, `affected_chain`, `full_chain`) and prerequisite manifest/check-hash evidence named by `task.md`, the user, or `$orchestrate-task-cycle`.
   - If the user specified a run method, follow that method instead of substituting a convenient alternative.
   - If code or run method is missing and cannot be inferred safely, ask for the missing command/code before running.
   - If the user supplied an inline snippet and did not require a file, prefer a direct interpreter invocation. Create files only when execution requires them or the user requested them.
   - For authorized long-term runs, identify the intended foreground/background mode, log path, checkpoint or heartbeat signal, monitor command, stop command, and minimum startup evidence before executing when possible.

2. Prepare safely.
   - Inspect only the files needed to understand the requested run.
   - Inspect prior execution logs or validation artifacts only enough to decide idempotent reuse, prerequisite hash validity, or changed input surfaces.
   - Do not edit source code, datasets, configs, or dependencies unless the user explicitly requested that as part of the run.
   - For destructive, credential-touching, network-heavy, package-installing, or large-data commands, surface the risk and require clear user instruction before proceeding.
   - For long-running commands, clear authorization may come from the user, `task.md`, an issue-resolution request, `$orchestrate-task-cycle`, or a governance result. If authorization or monitoring details are ambiguous, ask before leaving a process running.
   - Keep secrets, tokens, private paths, and sensitive raw data out of logs; summarize or redact them.
   - For fail-closed gates named by `task.md`, the caller packet, or the command harness, run a gate satisfiability precheck before evaluating the gate. Use a repository or environment adapter when available through `--domain-adapter`, `TASK_CYCLE_DOMAIN_ADAPTER_PATH`, or the caller-provided run packet. The adapter contract is `gate_satisfiability(gate_id, env, **context) -> {satisfiable: bool, reason, alternative_evidence_source?}`.
   - For pre-execution gate artifacts, also use adapter `gate_selfcheck(gate_artifact, gate_id, **context) -> {blocked_pre_exec, contradicting_evidence[], trusted_evidence_source?, prior_pass_observed?, repo_owned_pre_exec_blocker?}` when available. Classify as `self_inflicted_gate_defect` only when the blocker is confirmed repository-owned and at least one artifact-level contradiction, trusted evidence source, or prior pass exists. If repository-owned confirmation is missing, record warn-only `gate_selfcheck` and keep the original failure classification.
   - If `satisfiable=false` and `alternative_evidence_source` is present, evaluate the original gate against that alternative source and record `gate_satisfiability` plus `gate_evidence_source: alternative` in the run packet.
   - If `satisfiable=false` and no alternative source is present, classify the result as `self_inflicted_gate_defect`, not as an environment/runtime blocker. Stop before rechecking the same gate, record the exact gate id, reason, adapter/probe evidence, and required gate-contract/code correction, and let `$derive-improvement-task` route a gate-fix task or user escalation.
   - If `satisfiable=true`, keep the original fail-closed gate unchanged. This precheck must not weaken no-overclaim, no-raw-body, source-backed, cache, OOM, permission, or provider-safety gates.

3. Execute the specified code.
   - Run the command in the requested working directory.
   - For validation-profile-driven runs, execute only the commands required by the selected profile. Do not expand `current_only` or `affected_chain` into a full historical chain unless a changed surface or explicit instruction requires it.
   - Capture the exact command line, start/end time if available, exit code, relevant stdout/stderr summary, and produced artifacts.
   - If a process is long-running, monitor it until it completes, fails, reaches the authorized startup/heartbeat evidence threshold, or the user explicitly asks to leave it running.
   - When leaving an authorized process running, capture the PID, process/session/job ID when available, log file path, current output tail or heartbeat, checkpoint/artifact path if any, monitor command, stop command, and next recommended check.
   - If execution fails, do not hide the failure. Capture the error and stop unless the user requested retries or a fallback.
   - When execution fails with a nonzero exit, traceback, RuntimeError, or HTTP/provider-style error, run `scripts/safe_failure_autopsy.py` on captured stdout/stderr or bounded log files when available. Include only scalar diagnostics such as `error_type`, `exception_class`, `traceback_last_frame`, `http_status`, `missing_env_key_names`, `provider_request_count`, `provider_status`, `failure_class`, `provider_response_empty`, `provider_response_parse_failed`, `classification`, `alternative_evidence_source`, `gate_selfcheck`, `mitigations_attempted`, and `mitigations_unavailable`; do not persist raw source, prompt, provider, generated, stdout/stderr body, credential value, token, or secret-bearing payloads.
   - For every failed run, include `last_successful_stage` and an adapter/caller `execution_stage_ladder` when available. Use `execution_stage_ladder(**context)` from the domain adapter or pass `--execution-stage-ladder-json`; the autopsy derives `failure_surface_stage` as the next ladder rung after `last_successful_stage`. After the failure, include safe scalar/enum diagnostics with `--post-failure-diagnostics-json` or explicitly emit `diagnostics_unavailable=true` with a reason. A no-body policy still permits bounded scalar fields such as counts, enum labels, stage names, and status codes; it does not permit leaving the autopsy opaque when those fields are available.
   - If produced artifacts or command summaries contain progress verdict fields, downgrade those fields in the run packet and log to `observed_producer_claim`. Use adapter `producer_progress_claim_fields()` when available; otherwise treat conventional fields such as `progress_kind`, `effective_progress_kind`, `progress_verdict`, `goal_productive`, and `produced_domain_delta` as producer claims. Do not expose these fields as authoritative progress, completion, or goal-distance evidence from this skill.

4. Determine result status.
   - Use `success` only when the specified run completed with the expected result.
   - Use `running` when an authorized long-term run started, remains active, and has durable monitor/stop/log evidence, but final outputs or validation are not complete yet.
   - Use `partial` when some requested commands ran but validation, outputs, or follow-up work remain incomplete.
   - Use `failed` when execution ended in error.
   - Use `not_run` only when no command was executed because required code/method was missing or unsafe to infer.
   - When `$orchestrate-task-cycle` records this result in the cycle ledger, keep this result status in the run result packet and map a completed `success` run to ledger stage status `complete`. Do not require transition validators to treat raw run `success` as a lifecycle-stage status.

5. Log through `$record-agent-work-log`.
   - Use `$record-agent-work-log` after every attempted run, including failures and `not_run` outcomes caused by missing instructions.
   - If no command was rerun because identical durable evidence was reused, still report the reused artifact path and link it through `$manage-task-state-index` when possible; create a new log only if the calling workflow requires a handoff note.
   - Use the writer script from that skill for deterministic `.agent_log` records.
   - Include at minimum:
     - `task_intent`: what the user wanted to run and why.
     - `work_performed`: exact commands, working directory, environment notes, and files inspected or changed.
     - `result`: exit status, output summary, artifacts, active `running` metadata when applicable, and whether expectations were met.
     - `shortcomings`: failures, missing inputs, ambiguity, skipped steps, unverified assumptions, or unsafe details omitted.
   - Include the validation profile used, prerequisite manifest/hash evidence used, and whether the run was fresh or reused identical evidence.
   - Include `gate_satisfiability` entries for every fail-closed gate that was prechecked: `gate_id`, `satisfiable`, `reason`, `evidence_source`, `alternative_evidence_source`, and `classification`. Use `classification: self_inflicted_gate_defect` when the gate's required evidence shape is impossible in the current environment and no valid alternative source exists.
   - Include `gate_selfcheck` entries for pre-execution gate artifacts when available: `gate_id`, `blocked_pre_exec`, `repo_owned_pre_exec_blocker`, `contradicting_evidence`, `trusted_evidence_source`, `prior_pass_observed`, `classification`, `alternative_evidence_source`, and `status`. Treat these entries as scalar routing evidence only; do not persist raw gate bodies.
   - Include `failure_autopsy` for failed runs when safe scalar extraction was possible. For provider/runtime failures, include `provider_request_count`, `failure_class`, provider empty/parse flags, and mitigation fields when available so downstream derivation can distinguish transient/unmitigated failure from terminal state. Treat it as direction evidence for root-cause repair, not as remediation or validation success.
   - Include the H1 autopsy fields when applicable: `execution_stage_ladder_status`, `execution_stage_ladder`, `last_successful_stage`, `failure_surface_stage`, `post_failure_scalar_diagnostics`, `diagnostics_unavailable`, and `diagnostics_unavailable_reason`. If body capture is forbidden, still record safe scalar/enum diagnostics or `diagnostics_unavailable=true`; downstream loopback uses repeated unavailability to force instrumentation supply.
   - Include `observed_producer_claim` when a producer self-reported progress or completion. Keep it separate from any adapter-recomputed quality, substance, structure, or output-delta verdict. If a caller or adapter already reports disagreement, include only scalar `split_brain_progress_claim` warning details and leave the authoritative verdict to `$audit-cycle-loopback` and `$validate-task-completion`.
   - For `running` results, include PID/session/job identifiers, log and checkpoint paths, latest observed output or heartbeat, monitor and stop commands, expected completion signal, and remaining validation.
   - Use [execution-log-checklist.md](references/execution-log-checklist.md) when assembling the log fields.

6. Update task-state IDs when possible.
   - Before reporting, run `$manage-task-state-index` `scan` and `audit` if `.task/`, `.issue/`, `.agent_log/`, or `task.md` exists.
   - Add an `execution` artifact for durable run evidence when a report, output file, or log path exists. Link it with `run_for:<task-id>` when an active task ID is known.
   - Link execution evidence to relevant `issue-*` or `issue-res-*` artifacts with `resolved_by`, `fixes_issue`, or `related_to` when `$manage-implementation-issues` provided issue context.
   - Link the `.agent_log` entry to the execution artifact and active task with `produced`, `run_for`, or `related_to`.
   - If execution failed, link the failure to the active task and any blocking `task_miss` or validation artifact when present.
   - If execution is still `running`, link the active execution to the task or issue but do not mark the task, issue, or validation as complete solely from startup evidence.
   - If the workflow authorizes agents and ID context exists, a separate read-only ID insight agent may propose missing links. Do not assign execution, retry, or log-writing work to that agent.
   - If no durable artifact or active ID exists, skip ID linkage and preserve the normal run/log behavior.

7. Report back.
   - Tell the user what command was run, the result status, and where the `.agent_log` entry was saved.
   - For `running` status, report the PID/session/job ID, log path, monitor command, stop command, and next recommended check.
   - Include any task-state IDs or ID audit blockers when available.
   - Mention important output or failure details, but avoid dumping large logs or sensitive content.

## Logging Command Pattern

After execution, call the `$record-agent-work-log` writer script in the current workspace:

```bash
python3 /home/swfool/.codex/skills/record-agent-work-log/scripts/write_agent_log.py \
  --root . \
  --title "run task code" \
  --intent "..." \
  --work "..." \
  --result "..." \
  --shortcomings "..." \
  --command "<exact command that was run>" \
  --tag "execution" \
  --tag "task-code"
```

Add `--changed-file`, `--follow-up`, and additional `--command` values when relevant.

For failed pre-execution gate runs with a safe gate artifact, add the bounded gate artifact and repository-owned confirmation when known:

```bash
python3 /home/swfool/.codex/skills/run-task-code-and-log/scripts/safe_failure_autopsy.py \
  --stderr-path path/to/stderr.log \
  --exit-code 1 \
  --execution-stage-ladder-json .task/cycle/cycle-YYYYMMDD-HHMMSS/packets/execution_stage_ladder.json \
  --last-successful-stage parse_input \
  --post-failure-diagnostics-json .task/cycle/cycle-YYYYMMDD-HHMMSS/packets/post_failure_diagnostics.json \
  --gate-id pre_exec_gate \
  --gate-artifact-json path/to/gate_artifact.json \
  --domain-adapter .task/domain_adapter.py \
  --repo-owned-pre-exec-blocker \
  --output .task/cycle/cycle-YYYYMMDD-HHMMSS/packets/failure_autopsy.json
```

## Guardrails

- Do not invent code, commands, arguments, inputs, or success criteria.
- Do not log a run as successful when the command failed, timed out, was skipped, or was only partially verified.
- Do not log a still-active long-term run as `success`; use `running` until completion or validation evidence exists.
- Do not leave a process running unless long-term execution is authorized and durable PID/session, log, monitor, and stop details are captured.
- Do not omit a failed command from the `.agent_log` record.
- Do not let producer self-reported progress fields become workflow truth. Preserve them only as `observed_producer_claim`; downstream close/progress verdicts must come from adapter recomputation or strict changed-and-semantic output-delta evidence.
- Do not let redaction rules turn a failed run into an opaque terminal blocker when safe scalar autopsy can identify the failing file/line, exception class, HTTP status, or missing env key name without storing bodies or secrets.
- Do not omit `last_successful_stage`, `failure_surface_stage`, or safe post-failure scalar diagnostics when an execution stage ladder is available. If diagnostics cannot be collected, say `diagnostics_unavailable=true`; do not infer a terminal classification from an opaque failure.
- Do not rerun a fail-closed gate as an environment blocker after `gate_satisfiability.satisfiable=false` proves the gate's evidence shape is unsatisfiable and no alternative source exists. Record `self_inflicted_gate_defect` and route gate-contract correction instead of rechecking.
- Do not classify pre-execution gate contradiction evidence as `self_inflicted_gate_defect` unless repository-owned blocker provenance is confirmed by loopback/actionability evidence, the adapter, or an explicit caller flag. Without that confirmation, keep the self-check warn-only.
- Do not store full sensitive transcripts, credentials, raw tokens, private keys, or large copyrighted text in `.agent_log`.
- Do not let a helper or subagent write the log. The main agent runs `$record-agent-work-log`'s writer.
- Do not let an ID insight agent run commands, retry failures, or decide success; it only reviews traceability after the run evidence exists.
- Do not close, archive, or delete issues from this skill; `$manage-implementation-issues` owns issue lifecycle changes after this skill produces evidence.
