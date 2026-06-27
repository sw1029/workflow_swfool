# Split Policy

Use split policy to control overfitting and label leakage.

## Splits

- `dev`: public criteria and labels may be visible to implementation workers.
- `regression`: committed regression checks; labels may be in-repo, but overfitting risk must be acknowledged.
- `public_test`: deterministic or executable tests that can be visible.
- `sealed_holdout`: labels must not be passed to implementation workers. If the same workspace stores labels, mark sealing as `quasi_sealed`.

## Required Split Manifest Fields

- `validation_set_id`
- `sealed_holdout_status`: `true_sealed`, `quasi_sealed`, `not_sealed`, or `not_applicable`
- `label_visibility_policy`
- `splits`: mapping from split name to item IDs or shard paths

## Visibility Rules

Expose only public criteria during implementation. Do not include sealed holdout labels in `$task-md-agent-governance` packets. If true sealing cannot be guaranteed, report the limitation instead of pretending the holdout is sealed.
