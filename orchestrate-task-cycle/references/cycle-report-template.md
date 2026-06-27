# Task Cycle Report Template

Use this exact field order for the final response or durable cycle summary:

```text
기준 GT:
- <used .agent_goal/ file path, or 없음>

비-GT 방향성 문서:
- <used .agent_advice/active or applied advice path, or 없음>

주 진행 skill:
- $orchestrate-task-cycle

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

If commit evidence matters, add it after the required fields as `추가 참고`. Keep implementation and closeout commits separate. Do not backfill a closeout commit hash into a report file that is part of that same closeout commit; mention that hash only in the user-facing summary or a later artifact.
