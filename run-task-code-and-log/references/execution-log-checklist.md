# Execution Log Checklist

Use this checklist before writing the `.agent_log` entry through `$record-agent-work-log`.

## Execution Evidence

Capture:

- Workspace/cwd used for the run.
- Exact command line or code execution method.
- Runtime/interpreter/environment if relevant.
- Input files, config files, arguments, and environment assumptions that affected the run.
- Exit code or completion status.
- For authorized long-term runs: PID, session/job ID, log path, checkpoint path, latest heartbeat or output tail, monitor command, stop command, and next recommended check.
- Short stdout/stderr summary, not full noisy output.
- Produced artifacts, changed files, generated reports, or missing expected outputs.
- Validation performed after execution.
- Fail-closed gate prechecks and pre-execution gate self-checks when present, using scalar fields only.

## Log Field Mapping

`task_intent`:

- User-requested code/command.
- Requested execution method.
- Expected purpose or output.

`work_performed`:

- Commands run in order.
- Files inspected or created/changed.
- Environment selection and notable runtime details.
- Any safety redactions.

`result`:

- Status: success, running, partial, failed, or not_run.
- Exit code and key output summary.
- Active process metadata for `running` status.
- Artifacts produced or expected artifacts missing.
- Validation outcome.
- `failure_autopsy.classification`, `failure_autopsy.alternative_evidence_source`, and `failure_autopsy.gate_selfcheck` when a failure was autopsied.

`shortcomings`:

- Missing code, missing inputs, ambiguous instructions, unsafe assumptions, command failure, timeout, skipped validation, unavailable dependencies, or unverified output.
- For `running` status: final completion and final validation still pending.
- Sensitive details omitted from the log.

## Status Rules

- `success`: all requested execution steps completed and observed result matches the request.
- `running`: an authorized long-term run started, remains active, and has durable PID/session, log, monitor, and stop evidence, but final outputs or validation are not complete yet.
- `partial`: some work completed, but verification, outputs, dependencies, or follow-up remain.
- In `$orchestrate-task-cycle` ledgers, preserve this result status separately and record a completed `success` run stage as lifecycle `complete`.
- `failed`: the specified command or code ran and failed.
- `not_run`: execution did not happen because required code/method/input was missing or unsafe to infer.

## Gate Failure Fields

For fail-closed or pre-execution gates, record only scalar-safe routing evidence:

- `gate_satisfiability`: `gate_id`, `satisfiable`, `reason`, `evidence_source`, `alternative_evidence_source`, and `classification`.
- `gate_selfcheck`: `gate_id`, `blocked_pre_exec`, `repo_owned_pre_exec_blocker`, `contradicting_evidence`, `trusted_evidence_source`, `prior_pass_observed`, `status`, and `classification`.
- `classification: self_inflicted_gate_defect` only when repository-owned pre-execution blocker provenance is confirmed and the gate artifact has contradiction evidence, a trusted alternative evidence source, or a prior pass.
- `status: warn_missing_repo_owned_confirmation` when contradiction evidence exists but repository-owned confirmation is absent.

## Redaction Rules

- Replace secrets and tokens with `[REDACTED]`.
- Summarize large outputs instead of embedding them.
- Avoid raw dataset excerpts, private transcripts, and large copyrighted text.
