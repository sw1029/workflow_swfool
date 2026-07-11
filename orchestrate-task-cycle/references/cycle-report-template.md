# Task Cycle Report Template

Use this exact field order for the final response or durable cycle summary:

```text
기준 GT:
- <used .agent_goal/ file path, or 없음>

비-GT 방향성 문서:
- <used .agent_advice/active or applied advice path, or 없음>

주 진행 skill:
- $orchestrate-task-cycle

모델/effort 라우팅:
- T<tier> <profile_id>: <requested model/effort, reason codes, routing_enforcement, actual routing or limitation>

수행한 task:
- <task id>: <short summary>

변경한 파일:
- <file path>

실행한 검증:
- <command>: <result>

validation verdict:
- passed | failed | partial | not_run

progress verdict:
- advanced | safety_only | no_progress | regressed | not_run

progress axes:
- <axis>: <advanced | partial | blocked | no_progress | regressed | not_applicable>, or not_recorded

남은 blocker:
- 없음
- <.task/task_miss/ or .issue/ path>: <summary>

다음 task/방향성:
- <new active task id and short direction, or pending/blocker reason>

완료 여부:
- complete_verified | not_complete
```

Map `$validate-task-completion` `complete` to `passed`. Use `complete_verified` only when `validation verdict` is `passed`, `progress verdict` is `advanced`, and `남은 blocker` is `없음`; otherwise use `not_complete`. Use `safety_only` when the task passed by proving no-live/fail-closed safety without reducing the final-goal or issue blocker. Report goal-relevant axes when available, including `validation_set_axis`, `oracle_axis`, and `leakage_control_axis` when validation assets matter. Report only actually used `.agent_goal/` files under `기준 GT`; do not list merely available GT files. Report `.agent_advice` entries only under `비-GT 방향성 문서`; never mix them into `기준 GT`.

`complete_verified` additionally requires passing command outcomes and task-bound successful closure records for issue, derive, implementation commit (or a reasoned skipped/not-applicable commit), and dashboard. A closure record for another task, a failed/blocked commit, an unknown command outcome, or a bare command string without a result keeps the report `not_complete`.

Under `모델/effort 라우팅`, report policy/profile/tier, reason codes, signals, violations, and distinguish `enforced`, `prompt_only`, and `inherited_unverified`. Do not imply the already-running coordinator or any child used Terra or Sol when the runtime did not expose enforceable routing evidence. Report deterministic-only phases compactly and surface any tier/model/effort deviation or forbidden delegated `ultra`. A Sol route must identify Tier 5 final-direction ownership and signal evidence; a bounded Sol/max route must also identify `prior_tier5_evidence`, `max_escalation_reason`, and one-agent enforcement.

When Part K fields are present, surface unresolved `expectation_lineage_stale`, `parity_unverified`, missing adoption-axis classification, `measured_but_disqualified`, `resolution_downgrade`, and `report_key_divergence` under `남은 blocker` or the affected `progress axes`. Do not mark `complete_verified` while any of those fields blocks pass/close/adoption/baseline/comparison consumption.

When Part L fields are present, surface unresolved `pass_on_stale_lane`, `decision_metadata_revision`, `axis_starved_by_missing_producer`, restrictive `portfolio_quota_exceeded`, `unreachable_within_cycle`, `basis_overclaim`, and nonzero `surface_field_defect_matrix` under `남은 blocker` or the affected `progress axes`. Do not mark `complete_verified` while any of those fields blocks current-lane capability, measurement/adoption, producer-supply, long-run/throughput, metric-basis, or qualitative-review consumption.

If commit evidence matters, add it after the required fields as `추가 참고`. Keep implementation and closeout commits separate. Do not backfill a closeout commit hash into a report file that is part of that same closeout commit; mention that hash only in the user-facing summary or a later artifact.
