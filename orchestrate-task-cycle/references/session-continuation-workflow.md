# Session Continuation Workflow

Use this contract when one user-approved host session should carry a bounded sequence
of owner actions and task cycles without repeating the same approval interaction.
The controller is deterministic; it never invokes a model by itself.

## Contents

- [Entry and authority](#entry-and-authority)
- [Durable state](#durable-state)
- [Continuation actions](#continuation-actions)
- [Controller loop](#controller-loop)
- [Budgets and applicability](#budgets-and-applicability)
- [Long runs and failed closure](#long-runs-and-failed-closure)
- [Cross-cycle continuation](#cross-cycle-continuation)
- [Git closeout](#git-closeout)
- [Recovery and stop](#recovery-and-stop)

## Entry and authority

Start only from one live `authority_session_lease`. The lease must bind the current
workspace, host thread, eligible signed activation, goal, policy, manifest, operation
groups, risk ceiling, expiry, and budgets. A platform host receipt is the primary
approval evidence. When the host exposes no receipt, one exact foreground TTY
confirmation may create an agent-mediated narrowing lease.

Neither path authorizes R3, push, external/destructive effects, credentials,
authority/goal design changes, or policy/mode changes. Those remain separate exact
boundaries.

```bash
SKILLS_ROOT="${CODEX_HOME:-$HOME/.codex}/skills"

PYTHONPATH="$SKILLS_ROOT/manage-agent-authority/scripts" \
  "$SKILLS_ROOT/manage-agent-authority/scripts/authority-mode" \
  session-start --workspace /absolute/workspace

PYTHONPATH="$SKILLS_ROOT/orchestrate-task-cycle/scripts" \
  python3 -P -m orchestrate_task_cycle workflow cycle session start \
  --root /absolute/workspace --cycle-id <cycle>
```

`CODEX_THREAD_ID` is required. The host may inject
`CODEX_SESSION_APPROVAL_RECEIPT`; its raw value is hashed and never stored.

This lease narrows workflow authority; it does not enlarge the host filesystem
sandbox. For a repository such as `~/dataset/novel/소설_dataset`, open that exact
repository as the host workspace or approve it as a writable root once before
starting the session. Otherwise platform path approval remains a separate host
boundary regardless of the workflow lease.

## Durable state

The controller writes one closed
`.task/authorization/sessions/<session-id>/workflow-session.json`. It binds:

- the exact session-lease ref and digest;
- goal and task-family envelope;
- all admitted cycle IDs and the active task/cycle;
- live/host-boundary/stopped/complete/quarantined status;
- pending and accepted action identities;
- cycle, agent-action, long-run, and per-cycle commit usage;
- optimistic `state_version` and `state_sha256`.

Every update replaces the file atomically. A continuation token binds the state
immediately before its pending action. A token equal to the current state is circular;
an older version is stale. Replaying an accepted action is allowed only with the same
result digest.

## Continuation actions

`continuation_action@v1` is closed and has one actor:

| Actor | Kinds | Meaning |
|---|---|---|
| `system` | `monitor_run`, `complete`, `stop` | Deterministic controller state |
| `agent` | `run_owner`, `run_hybrid`, `monitor_run` | Execute one exact owner work order |
| `user` | `request_approval`, `stop` | Genuine user decision boundary |
| `host` | `request_host_approval` | Host receipt is absent or stale |
| `external` | `wait_external` | Required external state is unavailable |

Owner actions bind exact preparation/work-order refs, target, owner skill, routing
profile, effect class, result contract, and continuation token. External or unknown
effects are never auto-dispatched as an agent action.

The registry's combined `external_or_long_running_effect` is not authority by
itself. It becomes `local_long_run` only when a preparation-v3 context and work
order bind the current cycle authority packet, that packet reopens as the exact
allowed/reserved/pre-dispatch-verified
`run-task-code-and-log:run_long:1` operation, its selected grant is bound to the
current session, and the live activation/lease still permits `local_long_run`.
Provider, R3, external, cross-session, stale, legacy, or incomplete evidence remains
a user boundary.

Public output is a compact interaction card. The host dispatch adapter opts into
the sealed action with `--emit-action`; do not paste it into ordinary conversation.

## Controller loop

Use:

```bash
python3 -P -m orchestrate_task_cycle workflow cycle session continue --root .
python3 -P -m orchestrate_task_cycle workflow cycle session status --root .
```

The orchestration driver calls `continue --emit-action`, invokes the exact owner
skill for an `agent` action, sends the bound result to `accept-action`, and calls
`continue` again in the same turn. It must keep cycling while the lease and budgets
remain live. It yields to the user only for a `user`, `host`, or `external` action,
or for terminal `complete`/`stop`; an agent action is not a conversational stop.

One `continue` call:

1. Reloads and validates the session lease and continuation state.
2. Rechecks host liveness, activation expiry, and drift.
3. Reuses an unchanged pending owner action; it does not mint another action.
4. Re-evaluates a user/external boundary against underlying durable evidence.
   An unchanged evidence fingerprint returns the identical action and state; only a
   changed fingerprint clears the boundary for progression. A retry is not approval.
5. Runs bounded deterministic stage advancement.
6. Returns one owner, user, host, external, complete, or stop action.

Use `session accept-action --action-id <id> --result <json-or-file>` only for the
exact pending agent action. The stage adapter reopens the published preparation,
publishes owner/semantic/routing inputs through their registered producers, and
submits through the normal result and transition gates. A monitor result is accepted
only when its exact run observation already exists in the cycle ledger.

Use `manage-agent-authority authority inspect` for display-only authority state and
`authority advance` for one effectful resolution step. Do not use the deprecated
effectful `resolve` alias as a status renderer.

## Budgets and applicability

Default hard limits are:

- at most 3 cycles;
- at most 72 owner/monitor agent actions across the three-cycle session;
- at most 1 active long run;
- at most 1 closeout commit per cycle.

`stage_applicability_plan@v1` preserves the canonical 31-stage order while marking
evidenced optional work `not_applicable`. Unknown facts escalate to `required`.
The normal `commit` stage is deferred to batched closeout; `closeout_commit` is
required only when a tracked cycle delta exists. Facts come only from an exact,
complete Git projection or already completed producer events. The compiler may
publish a target-valid N/A receipt for its closed allowlist and advance through
consecutive optional stages; every receipt still passes the ordinary owner-result,
routing, submission, and transition contracts.

Preparation-v3 owner/hybrid work orders use bound lazy context, never inline
`selected_context`, and are capped at 12 KiB. Deterministic targets expose no
model-visible work order.

## Long runs and failed closure

Launching or observing a live run requires a stable `run_id` and occupies the single
long-run slot. Terminal observation removes that ID. Monitor actions consume the same
agent-action budget as other owner actions.

Never retry a failed run automatically. `run_terminal_projection@v1` binds the exact
cycle/run and distinguishes
`running`, `succeeded`, and `failed_closed`. A failed-closed projection must bind the
same run ID, terminal monitor state, harvest disposition, failure evidence,
`automatic_retry=false`, and disjoint safe-surviving versus discarded artifacts.

Only a projection reopened from the fixed producer CAS and appended by the terminal
observer makes the run terminal for ordering. The first terminal projection is
single-assignment for that cycle/run; only an exact replay is reusable. Then the
controller sets `closure_only=true` and may continue through qualitative review,
loopback, validation, derive/report, and safe closeout. Missing or altered evidence
keeps the run as a global blocker.

For every downstream preparation, reopen the terminal projection again and compile
`run_terminal_owner_intake@v1`. Owner context may receive only the explicitly safe
surviving bindings plus verified autopsy evidence; it may retain only a discarded
artifact count as deny-list metadata, never discarded refs or content. Both the
continuation adapter and the preparation-bound owner-result producer reject a
discarded ref before opening the proposed source.

## Cross-cycle continuation

The state machine accepts a successor only when:

- the prior cycle is complete;
- its derive event reopens an exact selected selection receipt;
- its exact bundle, three execution leases/checkpoints, authority settlements, and
  current session lease all replay unchanged;
- the goal/task-family envelope is unchanged;
- the next cycle is not already in the session; and
- the cycle budget remains.

The read-only compatibility bridge still accepts one already initialized exact
successor. The session adapter additionally derives one deterministic cycle ID from
the settled proof and initializes the missing compiler-first cycle under the source
cycle lock. It replays the proof before and after initialization, converges on the
same cycle under retry/concurrency, and never initializes from an unsettled,
ambiguous, stale, cross-session, or risk-mismatched selection.

## Git closeout

Adaptive sessions do not create an implementation commit and then a second metadata
commit. `$repo-change-commit` prepares one `git_embedded_settlement@v1` anchor that
binds parent, message, payload tree, staged/unstaged deltas, goal, task, cycle,
session, and authority evidence. The anchor is included in the same closeout commit.

Verification reopens `HEAD` and derives the terminal receipt without writing another
tracked artifact. Push remains a separate exact R3 operation and is never covered by
the session lease.

## Recovery and stop

Use `session recover` after interruption. Observe-only work may be safely rechecked.
For a potentially effectful action, accept an exact found result or quarantine
`unknown_effect`; never relaunch blindly.

The owner effect matrix is closed over every owner/hybrid target. Only
`qualitative_review` is safe to reissue without a producer receipt, and only
`closeout_commit` has exact anchor-based result recovery. All other local writes,
ordinary commits, authorized long runs, and monitor writes quarantine on ambiguous
host loss until a target-specific idempotency proof is added.

When the lease disappears, preserve any pending agent action as the durable recovery
handle and expose a transient host boundary. Repeated `continue` calls while the host
is absent do not replace or redispatch that possible effect. After a live lease
returns, recover before reissuing:

- `not_dispatched` gets a fresh continuation token and may be offered once;
- `result_found` is accepted without relaunch;
- `pending` remains an external recovery wait;
- `settled` without its exact result, or any unknown effect, is quarantined.

Observe-only work may be rechecked. A local effect without an owner-verifiable result
is intentionally not guessed from coordinator state.

```bash
python3 -P -m orchestrate_task_cycle workflow cycle session stop --root .
```

Stop updates both controller state and the matching authority lease. Expiry, drift,
budget exhaustion, user stop, or unknown effect are terminal for new dispatch.
