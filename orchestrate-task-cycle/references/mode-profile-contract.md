# Internal Mode Profile Contract

Keep canonical workflow modes limited to `normal|bootstrap`. Resolve optional observation behavior as a tracked internal profile with three independent axes:

- `capture`: `off|conversation_projection|structured_telemetry`
- `consume`: `shadow|advisory|required`
- `reaction`: `observe|proposal_only|derived_metadata_only`

Validate and resolve profiles with `python3 -m orchestrate_task_cycle mode-profile`. Revalidate a saved resolution with `verify-resolution`; the verifier recomputes it from the tracked base profile, embedded reducing override, and activation source. A profile or resolution is non-GT, non-validation evidence, and cannot change canonical phases, expand authority, upgrade verdicts, or authorize semantic mutation.

Only `rebuild_index -> .task/session_audit/index.json` is an unattended repair. It requires user instruction, caller policy, or an authority record plus a repair receipt. Session observations are not activation sources.

Use `$audit-session-governance` `auto-rebuild-index --mode-resolution <repo-local-resolution>` for that unattended operation. It fails closed on forged/default-activated resolutions and emits a content-derived receipt with the resolution ID, exact operation/target, index ID, and before/after SHA-256 values. The ordinary `rebuild-index` command remains an explicit manual maintenance path.

Example resolution command from the skill repository:

```bash
python3 orchestrate-task-cycle/python3 -m orchestrate_task_cycle mode-profile resolve \
  --base orchestrate-task-cycle/references/mode-profiles.json \
  --base-profile-id audit-index-repair --activation-source caller_policy
```

Local ignored overrides may only disable capture, lower consumption/reaction authority, remove repair capability, or add hook/consumer probe requirements. They may not switch to a different active capture capability or remove validation requirements.
