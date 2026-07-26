# Authority Interaction Mode Contract

Use this contract for the optional `authority_interaction_mode`; it is not a
new workflow phase and is never a source of authority by itself.

## Host input and modes

Read only `$CODEX_HOME/authority-interaction/config.toml`. The directory must
be a real current-UID `0700` directory and the config must be a real
current-UID `0600` file. Reject symlinks, unsafe ownership/modes, oversized
files, unknown TOML keys, unavailable `tomllib`/`tomli`, profile expansion,
and unknown operation groups. A missing config means `enabled=false`.

The only profiles are `workspace` and `governed`. Both are closed selections
from the installed operation registry. They can only authorize registered local
operations below their source/risk/decision/cardinality ceilings. `manual` and
`observe` produce no child grant. Runtime permissions and Codex/Claude modes
can narrow this result but cannot broaden it.

Always require an exact approval for SSH push, external/destructive work,
credentials, dependency/model acquisition, policy/authority/goal/design
changes, selection retention, D0/D1, R3, and unknown manifests. `push_git_ssh`
is S3/R3/external/single-use and binds the exact remote identity, refspec,
branch, and commit SHA in its request subject. Force pushes, tag deletion, and
remote replacement are outside the registered operation.

## Signed activation

`authority-mode activate --workspace <absolute-root> --mode governed` first
checks the real foreground `/dev/tty`. If unavailable, it creates no plan and
returns the stable TTY code plus the same external-terminal command. Otherwise
it publishes an immutable activation plan whose filename is its raw SHA-256.
The signer displays only that binding and requires:

```text
ACTIVATE AUTHORITY MODE <activation-plan-sha256>
```

The plan binds canonical workspace path/device/inode/Git common directory,
goal/policy snapshot, config bytes and normalized profile, operation manifest
digests, S3-to-S2 broker delegation, absolute 30-day expiry, limits, and the
always-ask exclusions. It deliberately excludes cycle and task identity. The
outbox evidence is separately domain-signed and must be published and
materialized before a broker can issue anything. `resume-activation` only
publishes/materializes existing signed outbox evidence; it never signs again.

Record only code, plan binding, retryability, and next action in the host-local
`0600` recent-attempt state. Never record TTY confirmation, passphrases, keys,
or evidence bodies.

## Exact child broker

The deterministic S2 broker runs only after ordinary evaluation has returned
`approval_required` for one exact request. It checks the signed activation,
current config, mode/runtime narrowing, workspace/goal/policy/manifest drift,
key status, non-sliding expiry, profile operation registry, and global budgets.
It then emits one schema-v6 `authority_source_approval` and a schema-v4 grant
bound to the canonical request SHA and its individual child materialization
receipt. No model/S1 coordinator can issue a child directly.

All existing evaluator selection, reservation, pre-dispatch/pre-commit
verification, settlement, use accounting, exact replay, and lineage rules stay
in force. A mode child is not reusable for a fresh-cycle request because the
request SHA includes cycle/task/subject context. Expiry, revocation, drift,
disable, or budget exhaustion prevents new reserve/evaluate selection; it does
not silently release an already reserved operation.

The effective authority is always:

```text
hard tier ∩ signed activation ∩ current config ∩ runtime ceiling
          ∩ OS/tool sandbox ∩ exact request
```
