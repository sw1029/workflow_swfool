개인적으로 만든 워크플로우 목적의 스킬 모음입니다.

생각날때 업데이트합니다.

## Skill 작동 흐름도

이 섹션은 각 스킬이 어떤 입력을 읽고, 어떤 판단을 하며, 어떤 산출물을 만들고, 어느 다음 스킬로 넘어가는지 확인하기 위한 흐름도이다.

- Mermaid 블록은 렌더링 가능한 다이어그램이다.
- 순수 텍스트 블록은 Mermaid 렌더링 없이도 같은 논리를 읽을 수 있는 흐름도이다.
- `.agent_goal/*.md`는 장기 목표/권한/규칙의 GT로 취급한다.
- `.agent_advice/*`는 비-GT 방향성 문서로만 취급한다.
- `.task/*`, `.agent_log/*`, `.issue/*`, `.schema/*`, `.contract/*`, `.validation/*`는 워크플로우 증거와 추적 상태이다.
- `.agent_log`의 현재 형식은 Markdown 본문과 `index.jsonl`을 `body_sha256`, `content_id`, `record_id`로 결합한다. context/completion collector, task-state index, progress-loop consumer는 공통 no-follow integrity 검사 후에 읽으며, 변조·중복·orphan·missing·symlink는 의미 소비와 색인을 fail-close한다. collector는 진단을 위한 integrity/file metadata만 표면화할 수 있다. legacy 행은 `legacy_unverified`로 읽을 수 있지만 body-integrity 보장은 없다.
- `logs/codex/*`, `logs/claude-code/*`의 Stop-hook projection과 `.task/session_audit/*`는 선택적 off-chain 관찰 사이드카이다. raw fallback 없이 최소 user/assistant projection만 보존하며 GT·권한·검증·진전·완료 증거가 아니다. 저장소 retention policy가 요구할 때만 해당 local path를 좁게 ignore한다.
- required session audit는 coordinator-owned collector가 현재 source를 결정론적으로 재검증하고 complete·bound·evaluated-integrity·consumable 조건과 `source_projection_verified=true`를 모두 충족한 경우에만 통과한다. direct/result-owned packet과 packet-owned canonical/cross-source claim은 계속 advisory이며, 별도 comparator contract가 두 입력을 독립적으로 소유해 새 관계를 수립해야 한다.
- canonical workflow mode는 계속 `normal|bootstrap`뿐이다. 선택적 ModeSpec은 capture/consume/reaction 축을 조합하되 phase·권한·verdict·semantic artifact를 변경하지 않으며, unattended repair는 비-default activation을 거친 `.task/session_audit/index.json` 재생성만 허용한다.
- domain metric, alias, lexicon, threshold, generalization pattern, capability ladder는 명시적 repo adapter가 소유한다. quality policy가 없으면 domain metric gate는 `not_evaluated`, capability ladder가 없으면 domain rung은 unavailable, GT policy가 없으면 generalization inference는 disabled이다. generic provider/credential 검사는 계속 동작한다.
- 완료 판정은 `$validate-task-completion`이 담당하며, 실행 성공/로그/대시보드/인덱스만으로 완료를 선언하지 않는다.
- adapter나 caller가 verifier contract를 요구하는 measurable acceptance는 live verifier가 pass해야 완전하다. required verifier의 `not_evaluated`는 pass가 아니며, full close 대신 verifier follow-up, explicit descope, terminal blocker, user escalation 중 하나로 보존한다.
- acceptance가 참조하는 gate의 required hook 부재, `pass_with_unobserved_axes`, generation-dependent count key, below-policy residual value per cycle cost는 pass/advance/close 근거가 아니다. hook supply, axis supply, effective key/terminal-outcome fallback, residual descope plus next rung, terminal blocker, user escalation 중 하나로 보존한다.
- acceptance scenario coverage, full body-free `command_argv`, actionable blocker relation, stochastic feasibility는 해당 증거가 등장한 cycle에서 completion/advance 소비 전에 gate로 재확인한다. `scenario_uncovered`, `acceptance_inversion`, `command_provenance_missing`, repeated `blocker_opacity`, `predetermined_unreachable`, `floor_edge_envelope`는 같은 결함 재시도가 아니라 scenario/argv/blocker/contract repair, descope, terminal blocker, user escalation 중 하나로 보존한다.
- 구조 진전은 어댑터가 `structure_metrics.global_*` 전역 불변량을 제공하면 per-scope 감소가 아니라 global high-water 이동으로 판정한다.
- depth/fan-out는 단독 차단 신호가 아니며 cohesion, reuse-root import ratio, duplicate symbol, mechanical shard, repo-owned `code_convention_contract`와 결합될 때만 구조 부담으로 소비한다. same-directory numbered/flat sharding이나 `relocated_mechanical_shard`는 size-driven refactor 완료 근거가 아니다.
- Part P/Q 증거는 기존 흐름의 pass/advance 소비를 더 엄격하게 만든다. `feature_regressed_artifact`, fresh producer execution 부재, `condition_unsatisfiable_for_input_generation`, `diminishing_reprocess`, fabricated hook provenance, primary reason-code 미수리는 completion/progress 전에 inheritance repair, producer re-execution/input refresh, existing-capability wiring, hook/provenance repair, explicit descope, terminal blocker, user escalation 중 하나로 보존한다. `adapter_hook_debt`/`unenforced`는 honest missing-hook debt이고, `terminal_delta_record`와 `governance_packet_budget`는 반복 기록 비용만 줄이며 blocker, escalation, validation 의미를 약화하지 않는다.
- S7~S10은 기존 판정의 성립조건 보정이다. `target_metric_delta`가 `moved=false`를 반환하면 측정/프록시/observed 필드만으로 완료하지 않고, `policy_consumption_sites`의 미반영 site는 전파 부채로 남기며, `gate_artifact_compatibility=false`는 gate fail이 아니라 `not_evaluated` 스킵이다. `first_seen_generation`/`consecutive_generation_count`/`chronic_threshold`는 chronic blocker 부채를 보이게 할 뿐 완료/검증 verdict를 바꾸지 않는다.
- scoped progress는 기존 `--gate-state-json` 입력에서 추출해 공통 계약으로 재평가한다. 실제 retained change가 task-local이면 bounded task close만 허용하고 root/global stall은 reset하지 않는다. root reset은 동일 basis의 residual 감소와 독립 observation 또는 완전한 self-grounded replay가, global reset은 모든 active axis에 대해 source·invariant owner·decisive function이 분리된 exact-bound receipt가 필요하다. 상충하거나 malformed인 scoped 입력은 선언된 surface만 보존하고 positive movement는 만들지 않는다.
- `$plan-validation-scope`의 two-pass 경로는 `decision_artifact_ref`와 `verification_source_separation_gate`가 공급되면 plan에서 current identity와 source/invariant/function 분리를 검사하고, finalize에서 같은 decision subject/lineage의 최신 revision과 gate를 다시 요구한다. plan 결함은 `affected_chain` 이상으로 올려 warn하고, finalize의 누락·stale·subject 변경·coupling은 fail-close한다.
- 장기 실행은 새 canonical phase가 아니라 `step: run`의 분기이다. `event_kind: long_run_launch|long_run_monitor|long_run_harvest|long_run_finalize`와 `long_run_role: launch|monitor|harvest|finalize`를 기록하며, `running`과 `completed_pending_validation`은 성공이 아니라 남은 harvest/validation의 증거이다.
- terminal-wait 재진입은 새 canonical phase나 전체 cycle이 아니라 pre-cycle selection boundary이다. authority-settled current baseline을 `selection-tick`이 재검증하고, 동일 입력은 `no_op`, 미완료 publication은 `recovery_required`, unjournaled head/lineage drift는 `drift_blocked`, exact premise 또는 baseline에 묶인 evidence-class 변화만 `selection_required`로 분기한다. successor가 선택되면 journal 기반 `selection-publication`으로 `task.md`를 마지막에 노출하고, 다시 wait하면 persisted selection receipt로 trigger `B`를 safe baseline `C`로 acknowledge한 뒤 authority-settled terminal-wait baseline을 CAS 활성화한다.
- 권한 실행 경계는 스킬 전체가 아니라 각 `authority.operations.json`의 versioned operation과 `authorization_mechanism`이다. `grant` operation의 allowed mutation만 decision → reserve → pre-dispatch verification → closed authority packet → initial pre-commit verification → 선택적 owner PREPARE → current/pre-commit revalidation → effect → consume/release/quarantine 경로를 사용한다. PREPARE/activation journal은 해당 operation owner가 계약으로 선언한 경우에만 삽입한다. `typed_source_approval`과 `bound_lifecycle_artifact`는 각각 exact source/lifecycle verifier가 소유하며, `none`은 `not_applicable`로 처리한다. authority·local resolution·external input·risk/cost·goal truth 축은 서로 대체하지 않는다.
- 스킬 실행 진입점은 스킬별 underscore 패키지의 `python3 -m <package> <command>` 형식으로 통일한다. 평면 `scripts/*.py` 호환 shim은 두지 않으며, 패키지 내부는 명시적 import와 정적 명령 레지스트리를 사용한다.

### 스크립트 모듈 아키텍처

- 각 `SKILL.md`는 자신의 `scripts/` 디렉터리를 `PYTHONPATH`에 추가하는 composition root이며, 외부 공개 진입점은 패키지의 `__main__.py` 하나이다.
- 루트 명령은 정적 `CommandSpec` 레지스트리에서 명시적으로 선택한다. 명령 이름 중복은 import 시 차단하고, 런타임 파일 탐색이나 `globals()` 기반 자동 등록은 사용하지 않는다.
- 상태 저장과 검증은 Repository/Unit-of-Work 경계로 분리하고, 분석 흐름은 작은 Stage/Strategy를 조합하는 Pipeline으로 구성한다. 상속은 상태 공유용 mixin 대신 안정된 추상 계약이나 `Protocol`이 실제 대체 가능성을 제공할 때만 사용한다.
- 생산자와 독립 검증자는 공개 스키마와 content-bound receipt를 경계로 상호작용한다. 예외적으로 session-audit consumer는 source parity를 재현하기 위해 producer의 `validate_packet`을 지연 호출하지만, 그 replay를 독립 신뢰나 verdict 승격으로 취급하지 않고 consumer-owned schema/source/canonical-ref 검사와 함께 advisory로 제한한다.
- 기능별 하위 패키지는 `api`/`cli` 또는 `command_registry` facade, 도메인 서비스, 저장소, 검증기, 렌더러를 분리한다. 공용 `utils.py`, 번호·버전 접미사 shard, wildcard import, 내부 `sys.path` 수정은 금지한다.
- 구조 회귀 테스트는 평면 production 진입점 부재, 임의 작업 디렉터리의 `python3 -m` 실행, 파일·함수 크기 상한, 정적 import/명령 레지스트리, 기존 출력·스키마 회귀를 함께 확인한다.

| 스킬 | 공개 패키지 | 루트 명령 |
|---|---|---|
| `audit-cycle-loopback` | `audit_cycle_loopback` | `evaluate` |
| `audit-session-governance` | `audit_session_governance` | `capture`, `audit` |
| `build-validation-set-with-agents` | `build_validation_set_with_agents` | `build`, `run-oracles`, `leakage`, `finalize`, `validate`, `freeze`, `verify-root` |
| `find-local-python-envs` | `find_local_python_envs` | `inventory` |
| `manage-agent-authority` | `manage_agent_authority` | `authority`, `receipt` |
| `manage-external-advice` | `manage_external_advice` | `registry` |
| `manage-task-state-index` | `manage_task_state_index` | `index`, `migrate`, `verify-migration` |
| `normalize-acceptance-and-demo` | `normalize_acceptance_and_demo` | `identity` |
| `orchestrate-task-cycle` | `orchestrate_task_cycle` | `ledger`, `transition`, `packet`, `context`, `report`, `dashboard`, `result-contract`, `task-pack`, `progress-loop`, `gt-conflict`, `evidence-cache`, `mode-profile`, `model-effort`, `monitor`, `output-delta`, `efficiency`, `visible-increment`, `code-structure`, `changed-surface`, `validation-scope`, `selection-tick`, `selection-decision-receipt`, `selection-publication`, `terminal-wait-baseline`, `exact-subject-premise`, `repo-adapter`, `authority-packet` |
| `plan-validation-scope` | `plan_validation_scope` | `changed-surface`, `plan`, `finalize` |
| `record-agent-work-log` | `record_agent_work_log` | `write`, `migrate`, `verify-migration` |
| `run-task-code-and-log` | `run_task_code_and_log` | `failure-autopsy` |
| `validate-task-completion` | `validate_task_completion` | `collect-evidence` |

각 스킬은 `PYTHONPATH="$SKILLS_ROOT/<skill>/scripts" python3 -m <package> <command>`로 호출한다. 다른 스킬의 공개 API를 소비하는 경우 해당 스킬의 `scripts/` 루트만 `PYTHONPATH`에 추가한다.

#### 확장 지점과 적용 규칙

1. 루트 명령을 추가할 때는 해당 패키지의 composition root에 명시적 handler와 `CommandSpec` 한 개를 등록한다. 파일명 탐색, `globals()`, `getattr()` 기반 dispatch는 사용하지 않는다.
2. 분석 단계를 추가할 때는 입력·누적 상태를 typed Context/State로 전달하고, 작은 `Protocol`/Strategy 구현을 정해진 Pipeline 순서에 삽입한다. 순서 자체가 출력 계약인 경우 registry tuple과 회귀 테스트에서 함께 고정한다.
3. 결과 계약을 확장할 때만 안정된 `ContractRule` 계층을 상속하고, 대상별 rule을 `RuleRegistry`에 등록한다. 상태 공유를 위한 mixin 다중 상속은 사용하지 않으며, 기존 rule을 바꾸지 않고 새 target을 추가할 수 있어야 한다.
4. durable write는 Repository와 Unit-of-Work 경계에서 prepare/commit/rollback을 분리한다. producer와 verifier는 공개 schema, hash, receipt를 기준으로 검증한다. session-audit producer replay처럼 명시적으로 허용된 호환 경로는 독립 검증 근거가 아니라 재현성 보조 신호로만 소비한다.
5. facade는 기존 import 심볼과 CLI를 유지하고 구현 세부사항은 하위 모듈로 위임한다. 새 확장에는 임의 cwd 모듈 호출, 출력 동등성, fail-close, 크기 상한 테스트를 함께 추가한다.

### Mermaid Flowchart 0: 현재 패키지·모듈 composition

```mermaid
flowchart TB
  Skill["SKILL.md<br/>scripts/ 경로를 PYTHONPATH에 추가"]
  Main["&lt;package&gt;/__main__.py<br/>공개 module entrypoint"]
  Registry["cli.py 또는 command_registry.py<br/>정적 CommandSpec / explicit handler"]

  Skill --> Main --> Registry

  subgraph Orchestrator["orchestrate_task_cycle composition root"]
    OCLI["orchestrate_task_cycle/cli.py<br/>27개 정적 root command"]
    Ledger["ledger<br/>cycle_ledger.py facade → ledger/*<br/>Repository + finalization Unit-of-Work"]
    Transition["transition<br/>validate_cycle_transition.py facade → transition/*<br/>ValidationContext + 21 ordered stages"]
    Packet["packet<br/>render_subskill_packet.py facade → packet/*<br/>PacketBuildContext + static target registry"]
    Reporting["dashboard / report<br/>facade → dashboard/* / report/*<br/>typed builder pipelines"]
    Result["result-contract<br/>result_contract/api.py → engine + validation_pipeline/*<br/>RuleRegistry → rules/*; sibling _rule_checks/* 지원"]
    Progress["progress-loop<br/>progress/cli.py → AnalysisContext + AnalysisPipeline<br/>evidence → aggregation → roots → gates → findings → result"]
    TaskPack["task-pack<br/>task_pack/cli.py → validation / mutation / receipts<br/>journal recovery + legacy-retirement settlement"]
    Selection["selection-tick / selection-decision-receipt / selection-publication<br/>terminal-wait-baseline / exact-subject-premise<br/>pre-cycle re-entry + recoverable pointer publication"]
    AuthorityRuntime["authority-packet<br/>owner decision / grant lineage / reservation / verification 재개방<br/>closed v2 dispatch projection"]
    RepoAdapter["repo-adapter scan / handoff<br/>repo-owned metadata validation + phase/consumer binding"]
    Analysis["code-structure / efficiency / output-delta / gt-conflict / model-effort<br/>compatibility facade → typed responsibility package"]
    Support["context / evidence-cache / mode-profile / monitor<br/>visible-increment / changed-surface / validation-scope<br/>public facade → responsibility module"]
    OCLI --> Ledger
    OCLI --> Transition
    OCLI --> Packet
    OCLI --> Reporting
    OCLI --> Result
    OCLI --> Progress
    OCLI --> TaskPack
    OCLI --> Selection
    OCLI --> AuthorityRuntime
    OCLI --> RepoAdapter
    OCLI --> Analysis
    OCLI --> Support
  end

  Registry --> OCLI

  subgraph SiblingPackages["독립 skill packages"]
    Loopback["audit_cycle_loopback evaluate<br/>commands.py → package __init__.py facade/cache bridge<br/>→ cli.py → evaluator.py + evaluation_stages/*"]
    Session["audit_session_governance capture / audit<br/>capture_projection.py + session_service.py<br/>session_parsing.py + session_packets.py"]
    Durable["record_agent_work_log / manage_task_state_index<br/>writer·index facade → integrity / migration / verifier<br/>producer와 verifier 구현 독립"]
    Validation["build_validation_set_with_agents / plan_validation_scope<br/>build·leakage·run-oracles·finalize·validate<br/>changed-surface·plan·finalize"]
    Leaf["authority / advice / acceptance / env / completion<br/>정적 command registry → 도메인 facade"]
  end

  Registry --> Loopback
  Registry --> Session
  Registry --> Durable
  Registry --> Validation
  Registry --> Leaf

  Ledger --> Artifacts[".task/cycle/* + content-bound receipt"]
  Result --> Artifacts
  TaskPack --> Artifacts
  Selection --> SelectionArtifacts[".task/selection_publication/*<br/>.task/terminal_wait_baseline/* + decision receipts"]
  AuthorityRuntime --> AuthorityArtifacts[".task/authorization/*<br/>immutable owner artifacts + CAS state"]
  RepoAdapter --> AdapterArtifacts["repo_skill_adapter_packet<br/>implementation / legacy_compatibility / renderer<br/>decision_identity_validator / authority_projection bindings"]
  Durable --> DurableArtifacts[".agent_log/* + .task/index.*"]
  Session --> SessionArtifacts["off-chain projection + .task/session_audit/*"]
  Loopback --> LoopArtifacts["anti_loop_progress_gate + prepared mutation candidate"]
```

### Mermaid Flowchart 1: 전체 task cycle orchestration

```mermaid
flowchart TD
  Request([사용자 요청 또는 cycle 후보])
  TerminalGate{"current task가 terminal + non-executable이고<br/>authority-settled baseline이 있는가?"}
  SelectionTick["pre-cycle: orchestrate_task_cycle selection-tick<br/>current baseline과 sticky exact-premise/authority row 재검증<br/>proposal fanout과 cycle init은 아직 금지"]
  TickResult{"tick status"}
  PreserveWait(["no_op | baseline_recorded<br/>wait 유지, fanout 없음"])
  RecoverSelection["recovery_required<br/>pending selection-publication forward recovery"]
  RepairSelectionDrift["drift_blocked<br/>committed-head / ambiguous-lineage drift 명시적 수리"]
  DeriveSelection["selection_required<br/>기존 derive의 3-lens selection boundary만 실행"]
  SelectionOutcome{"selection outcome"}
  PublishSuccessor["distinct successor<br/>selection-publication prepare/apply/recover<br/>owner-committed projection bind/verify<br/>publisher-owned projection 후 task.md pointer 마지막"]
  RebaseWait["terminal_wait again<br/>selection-decision-receipt → B acknowledge/rebase C<br/>authority-settled terminal-wait-baseline activation"]
  Start([normal/bootstrap cycle 실제 시작])
  Context["python3 -m orchestrate_task_cycle context<br/>README, task.md, .agent_goal, .agent_log,<br/>.task, .issue, .schema, .contract, .validation 수집"]
  LedgerInit["$maintain-cycle-ledger<br/>python3 -m orchestrate_task_cycle ledger init<br/>initialization.json + current_stage.json + packets/ 생성<br/>첫 canonical context append 시 stage.jsonl 생성"]
  Authority["$manage-agent-authority v2 mechanism routing<br/>grant + allowed mutation만 evaluate → reserve → pre_dispatch → authority-packet<br/>initial pre_commit → optional PREPARE → revalidate → effect/settle<br/>typed source / bound lifecycle은 owning verifier; none은 not_applicable"]
  Acceptance["$normalize-acceptance-and-demo<br/>python3 -m normalize_acceptance_and_demo identity<br/>acceptance, non-goals, demo, validation commands 정규화<br/>measurable → verifier / movement / scenario / freshness contract"]
  AdapterScan["python3 -m orchestrate_task_cycle repo-adapter scan / handoff<br/>manifest/component digest + declared phase/consumer/hook map 검증<br/>adapter_loaded=false metadata binding만 반환<br/>실제 hook 실행은 downstream owning consumer 책임"]
  RoutePlan["route_plan<br/>task.md 존재 여부와 cycle 경로 결정"]

  PacketGate["각 major call 전: orchestrate_task_cycle packet<br/>render_subskill_packet.py → PacketBuilder + TARGET_BUILDERS"]
  TransitionGate["orchestrate_task_cycle transition<br/>누적 --stage + 별도 --routing-json<br/>transition/pipeline.py ordered validation"]
  OwningCall["target owning skill / deterministic helper 실행"]
  ResultGate["major result 후: orchestrate_task_cycle result-contract<br/>SessionAuditRule + RuleRegistry target rules"]
  LedgerAppend["orchestrate_task_cycle ledger append<br/>검증된 stage envelope 기록"]

  NoTask{"task.md 없음?"}
  DeriveInitial["$derive-improvement-task initial_init<br/>초기 task.md 생성"]
  SchemaPreInit["$manage-schema-contracts<br/>초기 task가 schema/contract 영향이면 계약 정렬"]

  ValPlan["$plan-validation-scope<br/>python3 -m plan_validation_scope plan<br/>current_only / affected_chain / full_chain 결정<br/>current decision identity + source/invariant/function 분리 검사<br/>결함은 warn + affected_chain floor"]
  ValSetPlan["$build-validation-set-with-agents planning workflow<br/>package build 입력으로 oracle/split/leakage 정책 공급<br/>plan/consume은 CLI root command가 아님"]
  Governance["$task-md-agent-governance<br/>task.md 구현, worker 위임, repo audit, task_miss 기록"]
  ResultContract1["$validate-subskill-result-contract<br/>python3 -m orchestrate_task_cycle result-contract<br/>result_contract/api.py → engine + validation_pipeline/*<br/>RuleRegistry → rules/*; sibling _rule_checks/* 지원"]
  AdapterValidate["repo_skill_adapter_validate<br/>load/signature/return contract +<br/>consumer_context_conformance 검증"]
  CodeStructure["python3 -m orchestrate_task_cycle code-structure<br/>code_structure_audit.py facade → code_structure/cli.py<br/>audit pipeline → aggregation/state/report<br/>구조/컨벤션/semantic modularity packet"]
  Run["$run-task-code-and-log<br/>명령 실행, full command_argv, 실패 autopsy,<br/>observed_producer_claim downgrade,<br/>.agent_log v3 content-bound 기록, long_run_launch 가능"]
  Running{"run status = running?"}
  Monitor["$monitor-running-execution<br/>python3 -m orchestrate_task_cycle monitor<br/>canonical step=run + event_kind long_run_*<br/>PID/log/heartbeat/artifact/remaining_validation 추적"]
  Quality["$review-cycle-output-quality<br/>단일 read-only xhigh 출력 품질 리뷰<br/>goal-axis completeness, landed_feature_inventory,<br/>feature_presence_evidence body anchor<br/>applicable hook result id+digest가 final decision에 소비됐는지 확인"]
  Loopback["$audit-cycle-loopback<br/>semantic_progress, same-family loop, explicit quality/domain metrics,<br/>3-state gates, verifier contract, count-key hygiene,<br/>scoped retained change → task/root/global reset 분리,<br/>source + invariant owner + decisive function separation,<br/>gate/artifact compatibility skip, chronic blocker debt,<br/>goal-axis completeness, residual cost ratio,<br/>scenario/argv/blocker/stochastic findings,<br/>feature regression, frozen input, self-resolvable input routing,<br/>audit_cycle_loopback packet + root-cause ledger"]
  ValSetBuild["python3 -m build_validation_set_with_agents<br/>build → leakage → run-oracles → finalize → validate<br/>선택적 frozen root: freeze → verify-root"]
  SchemaPreDerive["$manage-schema-contracts pre-derive<br/>schema/contract 영향, stale contract,<br/>S8 policy propagation debt 확인"]
  Visible["$record-visible-increment<br/>보이는 변화 기록; not_validation_evidence=true"]
  GapAnalysis["repo_skill_gap_analysis<br/>adapter/skill gap 또는 skill-creator 후보"]
  Profile["$profile-cycle-efficiency<br/>python3 -m orchestrate_task_cycle efficiency<br/>cycle_efficiency/* typed analysis pipeline<br/>중복 로그, metadata-only 반복, command surface budget 감지"]
  ScopeFinalize["$plan-validation-scope finalize<br/>실제 changed files + current decision_artifact_ref +<br/>verification_source_separation_gate 재검증<br/>누락/stale/subject 변경/coupling은 block<br/>계획 profile보다 낮출 수 없음"]
  IndexPre["python3 -m manage_task_state_index index scan<br/>pre-validation task/run/validation evidence scan"]
  Slice["$optimize-task-slice<br/>state_transition, batch, evidence_supply, verifier_completion,<br/>scenario_supply, command_provenance_repair,<br/>feature/freshness/frozen-input repair, consolidation 등 advisory"]
  DeriveNext["$derive-improvement-task<br/>다음 task.md 또는 task_pack/terminal blocker 도출"]
  SchemaPost["$manage-schema-contracts post-derive<br/>새 task/schema/contract 링크 정리"]
  Index["$manage-task-state-index<br/>python3 -m manage_task_state_index index scan/link/audit<br/>task/candidate/miss/log/schema/issue IDs"]
  Validate["$validate-task-completion<br/>complete / partial / failed + progress_verdict<br/>required verifier pass + target metric movement,<br/>structure global effect 확인<br/>evidence freshness, landed feature inheritance,<br/>adapter hook provenance, frozen input lineage gate"]
  FinalCandidate["identity-bound final_candidate<br/>six verdict axes + attempt/revision binding"]
  LedgerFinalize["orchestrate_task_cycle ledger finalize<br/>immutable snapshot + CAS current_finalization.json<br/>content-bound cycle_finalization_receipt"]
  FinalVerify["orchestrate_task_cycle ledger verify-finalization<br/>current receipt/snapshot 재검증<br/>authoritative_final projection"]
  Issue["$manage-implementation-issues<br/>issue open/update/resolve, .issue mirror, GitHub fallback"]
  Pending{"long-run 결과가 아직 pending?"}
  Commit["$repo-change-commit<br/>coherent implementation/checkpoint commit"]
  Dashboard["$render-cycle-dashboard<br/>python3 -m orchestrate_task_cycle dashboard<br/>render_cycle_dashboard.py facade → dashboard/*"]
  Report["$maintain-cycle-ledger<br/>python3 -m orchestrate_task_cycle report<br/>assemble_cycle_report.py facade → report/*"]
  Closeout["$repo-change-commit closeout<br/>report/dashboard/ledger closeout commit"]
  End([cycle 결과 보고])

  Request --> TerminalGate
  TerminalGate -- no --> Start
  TerminalGate -- yes --> SelectionTick --> TickResult
  TickResult -- no_op / baseline_recorded --> PreserveWait
  TickResult -- recovery_required --> RecoverSelection --> SelectionTick
  TickResult -- drift_blocked --> RepairSelectionDrift --> SelectionTick
  TickResult -- selection_required --> DeriveSelection --> SelectionOutcome
  SelectionOutcome -- distinct successor --> PublishSuccessor --> Start
  SelectionOutcome -- terminal_wait --> RebaseWait --> PreserveWait
  Start --> Context --> LedgerInit --> Authority --> NoTask
  NoTask -- yes --> DeriveInitial --> SchemaPreInit --> Context
  NoTask -- no --> AdapterScan --> Acceptance --> RoutePlan --> ValPlan
  LedgerInit -. each major call .-> PacketGate --> TransitionGate --> OwningCall --> ResultGate --> LedgerAppend
  LedgerAppend -. next target .-> PacketGate
  ValPlan --> ValSetPlan --> Governance --> ResultContract1 --> AdapterValidate --> CodeStructure --> Run --> Running
  Running -- yes --> Monitor --> ScopeFinalize
  Running -- no --> Quality --> Loopback --> ValSetBuild --> Visible --> GapAnalysis --> Profile --> ScopeFinalize
  ScopeFinalize --> IndexPre --> Validate --> FinalCandidate --> LedgerFinalize --> FinalVerify --> Issue --> Pending
  Pending -- yes --> Dashboard
  Pending -- no --> SchemaPreDerive --> Slice --> DeriveNext --> SchemaPost --> Index --> Commit --> Dashboard
  FinalVerify -. verified truth .-> Dashboard
  Dashboard -->|canonical order| Report --> Closeout --> End
```

### Mermaid Flowchart 2: goal, authority, interview, advice

```mermaid
flowchart TD
  RawPrompt([raw user goal prompt])
  Shape["$shape-agent-goal-prompt<br/>raw prompt 보존, draft 생성, 3명 이상 critic review"]
  Goal["$manage-agent-goal<br/>.agent_goal/final_goal.md<br/>.agent_goal/conventions.md"]
  DeepGate{"base goal files<br/>실내용 존재?"}
  Deep["$deep-interview-goal-context<br/>stateful single-question interview"]
  Questions[".interview/questions.md<br/>.interview/answers.md<br/>.interview/state.md"]
  Drafts[".interview/drafts/<br/>architecture, theory, schema_contract, authority draft"]
  EvidenceReview{"3 evidence reviewers<br/>모두 CONFIRM?"}
  AuditReview{"3 critical auditors<br/>모두 CONFIRM?"}
  UserConfirm{"user final confirmation<br/>있음?"}
  FinalReview{"3-6 final reviewers<br/>모두 safe_to_write?"}
  Architecture["$manage-goal-architecture<br/>.agent_goal/goal_architecture.md"]
  Theory["$manage-goal-theory<br/>.agent_goal/goal_theory.md"]
  SchemaGoal["goal_schema_contract write<br/>.agent_goal/goal_schema_contract.md"]
  Authority["$manage-agent-authority policy owner<br/>.agent_goal/agent_authority.md<br/>장기 narrowing policy; runtime grant/receipt와 분리"]
  Operation["versioned authority.operations.json<br/>exact operation / capability / subject / risk / cardinality"]
  Mechanism{"authorization_mechanism"}
  AuthEval["manage_agent_authority authority<br/>policy/source snapshot + grant lineage<br/>evaluate → immutable closed decision"]
  AuthDecision{"grant decision"}
  AuthReserve["reserve exact uses<br/>lineage CAS + immutable reservation"]
  AuthPacket["pre_dispatch verify<br/>orchestrate_task_cycle authority-packet<br/>owner artifacts를 workspace에서 재개방"]
  AuthPrepare["optional owner PREPARE<br/>declared journal/activation contract만"]
  AuthInitialCommit["initial pre_commit verify<br/>packet에 묶인 current subject/grant/reservation"]
  AuthRevalidate["after PREPARE current/pre_commit revalidation<br/>packet/subject/grant/reservation 다시 개방"]
  AuthEffect["exact effect + immutable execution-result"]
  AuthSettle["consume → authority_use_receipt<br/>또는 not_started / verified-no-effect release<br/>unknown-effect quarantine"]
  AuthTyped["typed_source_approval<br/>exact source/rank/subset/lineage verifier<br/>recursive grant 없이 administrative action"]
  AuthBound["bound_lifecycle_artifact<br/>exact reservation/receipt/state-change verifier<br/>이미 승인된 lifecycle만 finalization"]
  AuthNone["none<br/>authority decision=not_applicable<br/>grant reservation/preflight 없이 owner contract 적용"]
  AuthRoute["approval_required / denied / wait / repair / conflict<br/>authority·external input·risk·GT 축을 분리 routing"]
  SchemaRegistry["$manage-schema-contracts<br/>.schema/.contract registry 정렬<br/>policy_propagation_incomplete debt 기록"]
  AdviceIn["외부 조언 파일 또는 본문"]
  Advice["$manage-external-advice<br/>canonical directive parse + exact disposition coverage<br/>prepare → applied/log projections → canonical event last<br/>commit receipt / forward recovery; never GT or authority"]
  AdvicePacket["active advice packet<br/>not_goal_truth=true"]
  Index["$manage-task-state-index<br/>python3 -m manage_task_state_index index scan/link/audit<br/>goal-*, int-*, adv-*, schema-* 링크"]
  Consumers["orchestrate / derive / governance / validate<br/>GT와 비-GT를 분리 소비<br/>additive signal 대신 acceptance/gate/progress key에 반영"]

  RawPrompt --> Shape --> Goal
  Goal --> DeepGate
  DeepGate -- no --> Goal
  DeepGate -- yes --> Deep --> Questions --> Drafts --> EvidenceReview
  EvidenceReview -- no --> Questions
  EvidenceReview -- yes --> AuditReview
  AuditReview -- no --> Questions
  AuditReview -- yes --> UserConfirm
  UserConfirm -- no --> Questions
  UserConfirm -- yes --> FinalReview
  FinalReview -- no --> Questions
  FinalReview -- yes --> Architecture --> Index
  FinalReview -- yes --> Theory --> Index
  FinalReview -- yes --> SchemaGoal --> SchemaRegistry --> Index
  FinalReview -- yes --> Authority --> Index
  Authority -. narrowing policy input .-> Mechanism
  Operation --> Mechanism
  Mechanism -- grant --> AuthEval --> AuthDecision
  AuthDecision -- allowed mutation --> AuthReserve --> AuthPacket --> AuthInitialCommit --> AuthRevalidate --> AuthEffect --> AuthSettle --> Consumers
  AuthInitialCommit -. owner contract가 선언할 때 .-> AuthPrepare --> AuthRevalidate
  AuthDecision -- other closed decision --> AuthRoute --> Consumers
  Mechanism -- typed_source_approval --> AuthTyped --> Consumers
  Mechanism -- bound_lifecycle_artifact --> AuthBound --> Consumers
  Mechanism -- none --> AuthNone --> Consumers
  AdviceIn --> Advice --> AdvicePacket --> Consumers
  Index --> Consumers
```

### Mermaid Flowchart 3: task selection, doctoring, task-pack, anti-loop

```mermaid
flowchart TD
  Trigger([next task 필요 / terminal-wait 재진입 / 명시적 task doctor 요청])
  WaitBound{"verified current terminal-wait baseline?"}
  WaitSelection["Flowchart 9 pre-cycle boundary<br/>selection-tick → no_op | baseline_recorded / recovery_required<br/>/ drift_blocked / selection_required<br/>cycle init과 proposal fanout을 먼저 차단"]
  WaitHold(["terminal wait 유지<br/>cycle init과 fanout 없이 종료"])
  WaitRecovery["recovery_required<br/>pending selection-publication forward recovery<br/>완료 후 current baseline을 다시 resolve/tick"]
  WaitDrift["drift_blocked<br/>committed-head / ambiguous-lineage drift 명시적 수리<br/>완료 후 current baseline을 다시 resolve/tick"]
  ExplicitDoctor{"명시적 doctor/replace/pack 지시?"}
  TaskDoctor["$task-doctor<br/>task.md retarget/replace 또는 task_pack proposal"]
  DoctorRead["읽기: task.md, .agent_goal, named advice, .task, .issue, .schema"]
  DoctorArchive["$record-agent-work-log<br/>old task를 past_task로 보존"]
  DoctorWrite["새 task.md 또는 .task/task_pack/*.json + *.md 작성"]
  DoctorIndex["$manage-task-state-index<br/>supersedes, promoted_from_pack, advice links"]
  DoctorCommit["$repo-change-commit<br/>task-direction change commit"]

  NormalDerive["$derive-improvement-task"]
  Inputs["입력 수집<br/>.agent_goal, authority, active advice, .issue,<br/>task_miss, candidates, task_pack, schema/contract,<br/>qualitative_review, loopback, validation/profile packets"]
  Alignment["$inspect-repo-with-agents<br/>goal/convention/schema alignment"]
  MissAgents["2-4 task_miss analysis agents"]
  CandidateScan[".task/candidate_task 분류<br/>now/blocked/obsolete/duplicate"]
  PackScan[".task/task_pack 분류<br/>promote/insert/reorder/skip/supersede/terminal"]
  IssueFit["$manage-implementation-issues issue-fit agent<br/>fit/partial/misfit/unknown"]
  ImproveAgents["3 parallel improvement-analysis agents<br/>goal fit, architecture fit, miss/risk fit"]
  LensReceipts["3 durable lens projections + canonical synthesis output<br/>동일 frozen manifest / exact candidate union / advice clause reconciliation"]
  Synthesis["1 xhigh synthesis agent<br/>digest-bound authoritative selection decision"]
  Decision{"선택 결과"}
  ArchivePast["$record-agent-work-log<br/>기존 task.md past_task archive"]
  MutatePack["task_pack transaction<br/>create/promote/insert/reorder/skip/supersede/terminal"]
  PublicationPlan["selection-publication plan<br/>source decision + bounded roles + exact before/after bytes"]
  Publish["selection-publication apply<br/>owner-committed archive/log/task-pack은 unchanged bind/verify<br/>publisher-owned advice/index 후 task.md alias last<br/>after-state 검증 후 committed receipt"]
  Candidates["unselected proposals → candidate lifecycle 유지<br/>selected candidate도 applied/superseded로 전이<br/>physical deletion 없이 provenance 보존"]
  WaitAgain["terminal_wait<br/>selection-decision receipt + A/B/C rebase<br/>authority-settled baseline publication은 Flowchart 9"]
  Terminal["terminal_blocker / user_escalation<br/>sealed family와 missing input 기록"]
  DeriveIndex["python3 -m manage_task_state_index index scan<br/>then index audit"]

  LoopInputs["run + quality review + output-delta artifacts<br/>failure autopsy, runner validation, gate states,<br/>long-run history, scenario/argv/blocker/stochastic,<br/>Part P/Q freshness, feature, lineage, provenance fields,<br/>S7-S10 movement/propagation/compat/chronic fields,<br/>scoped progress + actual changed-file/content evidence"]
  ProgressDetect["python3 -m orchestrate_task_cycle progress-loop<br/>progress/cli.py → AnalysisContext + AnalysisPipeline<br/>evidence → aggregation → roots → gates → findings → result"]
  Loopback["$audit-cycle-loopback<br/>python3 -m audit_cycle_loopback evaluate<br/>commands.py → package facade/cache → cli.py → evaluator.py<br/>api.py는 별도 stable explicit export facade"]
  LoopGate["anti_loop_progress_gate<br/>effective_allowed_dispositions, allowed_task_kinds,<br/>adapter_wiring_defect, adapter_mandate,<br/>failure surface, source+invariant+function separation,<br/>scoped retained change + task/root/global reset permissions,<br/>acceptance/verifier/axis/count-key/scenario gates,<br/>gate compatibility skip, chronic blocker debt,<br/>feature regression, frozen input, self-resolvable input,<br/>reason-code rank, structure global invariant metrics"]
  LongRunDebt{"active long_run_branch<br/>pending final output?"}
  LongRunRoute["derive constraint<br/>monitor/harvest/finalize same run_id<br/>or terminal/user escalation"]
  ScopedDebt{"scoped progress surface가<br/>root/global reset을 block?"}
  ScopedRoute["preserve bounded task close only<br/>retain root/global stall and route evidence repair"]
  VerifierDebt{"required verifier<br/>not_evaluated?"}
  VerifierRoute["derive constraint<br/>verifier hook/metric correction/descope/<br/>terminal blocker/user escalation"]
  EvidenceDebt{"scenario/argv/blocker/stochastic<br/>repair required?"}
  EvidenceRoute["derive constraint<br/>scenario_supply / command_provenance_repair /<br/>blocker_contract_repair / contract revision"]
  MetricMoveDebt{"target metric movement<br/>missing or false?"}
  MetricMoveRoute["derive constraint<br/>real target-metric movement / measurement repair<br/>or explicit residual/descope"]
  PolicyDebt{"policy propagation<br/>incomplete?"}
  PolicyRoute["derive constraint<br/>update unreflected judgment site<br/>or keep propagation=unverified debt"]
  PartPDebt{"Part P freshness/feature/<br/>frozen-input debt?"}
  PartPRoute["derive constraint<br/>inheritance repair / producer re-execution /<br/>input refresh / descope / terminal / escalation"]
  PartQDebt{"Part Q self-resolvable/provenance/<br/>reason-rank debt?"}
  PartQRoute["derive constraint<br/>existing-capability wiring / hook provenance repair /<br/>primary reason repair / structure handoff"]
  GlobalInvariant{"structure global invariant<br/>metrics present?"}
  GlobalMoved{"global high-water<br/>moved?"}
  GlobalRoute["global invariant present + local-only reduction<br/>cannot consume global structure target"]
  Slice["$optimize-task-slice<br/>state_transition/batch/evidence/verifier_completion/<br/>scenario_supply/command_provenance_repair/consolidation advisory"]
  Profile["$profile-cycle-efficiency<br/>sprawl, duplicate evidence, safety_only loops"]

  Trigger --> ExplicitDoctor
  ExplicitDoctor -- yes --> TaskDoctor --> DoctorRead --> DoctorArchive --> DoctorWrite --> DoctorIndex --> DoctorCommit
  ExplicitDoctor -- no --> WaitBound
  WaitBound -- yes --> WaitSelection
  WaitBound -- no --> NormalDerive
  WaitSelection -- no_op / baseline_recorded --> WaitHold
  WaitSelection -- recovery_required --> WaitRecovery --> WaitSelection
  WaitSelection -- drift_blocked --> WaitDrift --> WaitSelection
  WaitSelection -- selection_required --> NormalDerive
  LoopInputs --> ProgressDetect --> Loopback --> LoopGate --> LongRunDebt
  LongRunDebt -- yes --> LongRunRoute --> NormalDerive
  LongRunDebt -- no --> ScopedDebt
  ScopedDebt -- yes --> ScopedRoute --> NormalDerive
  ScopedDebt -- no or absent --> VerifierDebt
  VerifierDebt -- yes --> VerifierRoute --> NormalDerive
  VerifierDebt -- no --> EvidenceDebt
  EvidenceDebt -- yes --> EvidenceRoute --> NormalDerive
  EvidenceDebt -- no --> MetricMoveDebt
  MetricMoveDebt -- yes --> MetricMoveRoute --> NormalDerive
  MetricMoveDebt -- no --> PolicyDebt
  PolicyDebt -- yes --> PolicyRoute --> NormalDerive
  PolicyDebt -- no --> PartPDebt
  PartPDebt -- yes --> PartPRoute --> NormalDerive
  PartPDebt -- no --> PartQDebt
  PartQDebt -- yes --> PartQRoute --> NormalDerive
  PartQDebt -- no --> GlobalInvariant
  GlobalInvariant -- no --> Slice
  GlobalInvariant -- yes --> GlobalMoved
  GlobalMoved -- no --> GlobalRoute --> NormalDerive
  GlobalMoved -- yes --> Slice --> NormalDerive
  Profile --> NormalDerive
  NormalDerive --> Inputs --> Alignment --> MissAgents --> CandidateScan --> PackScan --> IssueFit --> ImproveAgents --> LensReceipts --> Synthesis --> Decision
  Decision -- standalone task --> ArchivePast --> Candidates --> PublicationPlan
  Decision -- pack mutation --> ArchivePast --> MutatePack --> Candidates
  PublicationPlan --> Publish --> DeriveIndex
  Decision -- terminal_wait --> WaitAgain --> DeriveIndex
  Decision -- terminal_blocked / user_escalation --> Terminal --> DeriveIndex
```

### Mermaid Flowchart 4: implementation, execution, validation

```mermaid
flowchart TD
  Task([active task.md])
  Acceptance["$normalize-acceptance-and-demo<br/>python3 -m normalize_acceptance_and_demo identity<br/>acceptance_identity.py → normalized packet<br/>verifier/movement/scenario/freshness/hook contract"]
  ValScope["$plan-validation-scope<br/>python3 -m plan_validation_scope plan<br/>validation_scope.py → current_only/affected_chain/full_chain<br/>current decision identity + source/invariant/function 분리<br/>결함은 warn + affected_chain floor"]
  EnvNeed{"Python/dependency constrained?"}
  FindEnv["$find-local-python-envs<br/>python3 -m find_local_python_envs inventory<br/>local env inventory + ranked run commands"]
  DepMissing{"필수 dependency/cache 없음?"}
  Install["$install-deps-with-agent<br/>find-local-python-envs 후 exactly one install agent"]
  ValSetNeed{"validation set 필요?"}
  ValSet["$build-validation-set-with-agents<br/>python3 -m build_validation_set_with_agents<br/>build → leakage → run-oracles → finalize → validate<br/>optional freeze → verify-root; planning은 workflow mode"]
  Governance["$task-md-agent-governance"]
  ReadTask["task.md, authority, advice, schema, code_convention_contract 읽기"]
  MapRepo["repo map<br/>git status, rg --files, manifests, tests"]
  Workers["Tier 2-3 configured balanced-profile workers<br/>medium/high, disjoint write scopes, authority/advice/convention 포함"]
  Integrate["worker changes 통합<br/>format/tests, convention_conformance 확인"]
  Inspect["$inspect-repo-with-agents<br/>3-6 read-only code/schema/authority/generalization audit"]
  CodeStructure["python3 -m orchestrate_task_cycle code-structure<br/>code_structure_audit.py facade → code_structure/cli.py<br/>audit.py → aggregation.py + state.py + report.py<br/>contracts/source/semantics 지원"]
  TaskMiss[".task/task_miss report<br/>miss/resolved/deleted cleanup evidence"]
  Run["$run-task-code-and-log"]
  Execute["정해진 command 실행<br/>validation_profile 준수<br/>full body-free command_argv 보존"]
  Failure{"실패 또는 gate unsatisfiable?"}
  Autopsy["python3 -m run_task_code_and_log failure-autopsy<br/>safe_failure_autopsy.py + failure_diagnostics.py<br/>stage ladder + scalar diagnostics + gate selfcheck"]
  Log["$record-agent-work-log<br/>python3 -m record_agent_work_log write<br/>write.py → integrity/append.py<br/>content-bound .agent_log + index.jsonl"]
  Running{"long-running authorized?"}
  Monitor["$monitor-running-execution<br/>python3 -m orchestrate_task_cycle monitor<br/>step=run long_run_* event<br/>completed_pending_validation != success"]
  Quality["$review-cycle-output-quality<br/>single reviewer, output quality/delta/no-overclaim<br/>goal-axis completeness + landed_feature_inventory<br/>feature_presence_evidence body anchor<br/>hook result id+digest + final-decision consumption gate"]
  ScopeFinalize["$plan-validation-scope finalize<br/>actual changed files + current decision_artifact_ref +<br/>verification_source_separation_gate<br/>missing/stale/subject change/coupling은 block"]
  Completion["$validate-task-completion<br/>python3 -m validate_task_completion collect-evidence<br/>completion gate가 evidence bundle 소비"]
  Gates["gates: env, execution, repo audit, OOM if relevant,<br/>task_miss, issue, advice, schema, acceptance,<br/>required verifier/hook pass, target metric movement,<br/>goal axes, scenario, command, blocker, stochastic feasibility,<br/>policy propagation debt, gate compatibility skip,<br/>evidence freshness, landed feature inheritance,<br/>adapter hook provenance, frozen input lineage,<br/>structure global invariant, behavior-change live evidence, ID"]
  Verdict{"validation_verdict<br/>complete / partial / failed"}
  Progress{"progress_verdict<br/>advanced / safety_only / no_progress / regressed"}
  Candidate["identity-bound cycle_final_candidate<br/>six verdict axes + attempt/revision binding<br/>ledger finalization의 유일한 입력"]

  Task --> Acceptance --> ValScope --> EnvNeed
  EnvNeed -- yes --> FindEnv --> DepMissing
  DepMissing -- yes --> Install --> ValSetNeed
  DepMissing -- no --> ValSetNeed
  EnvNeed -- no --> ValSetNeed
  ValSetNeed -- yes --> ValSet --> Governance
  ValSetNeed -- no --> Governance
  Governance --> ReadTask --> MapRepo --> Workers --> Integrate --> Inspect --> CodeStructure --> TaskMiss --> Run
  Run --> Execute --> Failure
  Failure -- yes --> Autopsy --> Log
  Failure -- no --> Log
  Log --> Running
  Running -- yes --> Monitor --> ScopeFinalize
  Running -- no --> Quality --> ScopeFinalize
  ScopeFinalize --> Completion
  Completion --> Gates --> Verdict --> Progress --> Candidate
```

### Mermaid Flowchart 5: evidence, state, issue, commit, reporting

```mermaid
flowchart TD
  EffectRequest([grant-authorized mutating skill operation])
  OperationManifest["authority.operations.json<br/>authorization_mechanism=grant<br/>versioned operation + exact subject"]
  AuthorityOwner["$manage-agent-authority v2<br/>allowed decision → reserve → pre_dispatch verify"]
  AuthorityPacket["orchestrate_task_cycle authority-packet<br/>decision/grant/reservation/verification artifact 재개방"]
  InitialPreCommit["initial pre_commit verify<br/>packet-bound current CAS / subject / manifest"]
  Prepare["optional operation owner PREPARE<br/>owner contract가 선언한 경우에만<br/>effect는 아직 operationally inactive"]
  RevalidatePreCommit["after PREPARE revalidate<br/>current CAS / subject / packet / pre_commit 재개방"]
  EffectSettlement["exact effect → immutable execution-result<br/>consume + authority_use_receipt<br/>not_started / verified-no-effect release<br/>unknown-effect quarantine"]
  Evidence([어떤 스킬이 artifact 생성])
  Cache["$manage-evidence-cache<br/>python3 -m orchestrate_task_cycle evidence-cache<br/>fingerprint → reuse/fresh_required/stale/unsafe_to_reuse"]
  Log["$record-agent-work-log<br/>python3 -m record_agent_work_log write<br/>write.py → integrity/append.py<br/>body_sha256/content_id/record_id binding"]
  LogIntegrity["shared agent_log_integrity gate<br/>no-follow containment + body/index binding<br/>collector/index/progress consumers가 공유"]
  LogClass{"integrity status"}
  Legacy["legacy_unverified<br/>읽기 가능; body-integrity 보장 없음"]
  Invalid["unsafe / invalid<br/>duplicate/orphan/missing/tamper/symlink<br/>integrity metadata only; semantic use/indexing 제외"]
  Contract["$validate-subskill-result-contract<br/>python3 -m orchestrate_task_cycle result-contract<br/>api.py → engine.py → validation_pipeline/*<br/>RuleRegistry → rules/*; sibling _rule_checks/* 지원"]
  Ledger["$maintain-cycle-ledger<br/>python3 -m orchestrate_task_cycle ledger append<br/>stage.jsonl + current_stage.json + packets/<br/>long-run events remain step=run"]
  TerminalDelta["P5 terminal_delta_record / governance_packet_budget<br/>unchanged_ref(path+hash), input-delta, disposition, streak<br/>recording-cost reduction only"]
  Chronic["S10 chronic_blocker debt<br/>first_seen_generation + consecutive_generation_count<br/>visibility only, not verdict"]
  FinalCandidate["$validate-task-completion output<br/>identity-bound final_candidate"]
  Finalize["python3 -m orchestrate_task_cycle ledger finalize<br/>immutable snapshot + CAS current_finalization.json<br/>content-bound cycle_finalization_receipt"]
  FinalizeState{"finalization result"}
  PendingConflict["state_commit_status=recovery_required<br/>attempt_memory_disposition=pending_conflict<br/>expected predecessor/target revision mismatch를 immutable 보존<br/>현재 authoritative state는 변경하지 않음"]
  ResolvePending{"pending-finalization resolution"}
  RebasedRetry["rebase candidate + finalize retry<br/>successful publish가 matching pending을 auto-merge"]
  ManualMerged["merged<br/>exact committed_finalization_token 필수"]
  RetiredPending["retired<br/>committed token 금지; pending 종료<br/>current authoritative state 불변"]
  Verify["ledger verify-finalization<br/>load_current_finalized_state<br/>authoritative verified projection"]
  Index["$manage-task-state-index<br/>python3 -m manage_task_state_index index scan/link/audit<br/>task/log/run/audit/val/miss/issue/goal/adv/schema IDs"]
  Visible["$record-visible-increment<br/>visible delta, not_validation_evidence=true"]
  Issue["$manage-implementation-issues<br/>GitHub 또는 .issue fallback, issue lifecycle"]
  Commit["$repo-change-commit<br/>diff 분류, gitignore 정리, validation context, exact staging"]
  Dashboard["$render-cycle-dashboard<br/>python3 -m orchestrate_task_cycle dashboard<br/>render_cycle_dashboard.py facade → dashboard/*"]
  Report["$maintain-cycle-ledger<br/>python3 -m orchestrate_task_cycle report<br/>assemble_cycle_report.py facade → report/*"]
  Closeout["$repo-change-commit closeout<br/>dashboard/report/ledger artifacts commit"]
  User([사용자에게 결과 보고])

  EffectRequest --> OperationManifest --> AuthorityOwner --> AuthorityPacket --> InitialPreCommit --> RevalidatePreCommit --> EffectSettlement --> Evidence
  InitialPreCommit -. owner contract가 선언할 때 .-> Prepare --> RevalidatePreCommit
  Evidence --> Cache
  Evidence --> Log --> LogIntegrity --> LogClass
  Evidence --> Contract --> Ledger
  LogClass -- valid --> Index
  LogClass -- legacy_unverified --> Legacy --> Index
  LogClass -- unsafe/invalid --> Invalid
  Ledger --> TerminalDelta --> Index
  Ledger --> Chronic --> Index
  Evidence --> Visible --> Ledger
  Evidence -. completion bundle .-> FinalCandidate
  FinalCandidate --> Finalize --> FinalizeState
  FinalizeState -- state_commit_status=committed --> Verify
  FinalizeState -- recovery_required + pending_conflict --> PendingConflict --> ResolvePending
  ResolvePending -- rebased retry --> RebasedRetry --> Finalize
  ResolvePending -- merged --> ManualMerged --> Verify
  ResolvePending -- retired --> RetiredPending --> Index
  Verify --> Index
  Index --> Issue --> Commit
  Verify --> Dashboard
  Commit --> Dashboard -->|canonical order| Report --> Closeout --> User
```

### Mermaid Flowchart 6: diagnostic and support skills

```mermaid
flowchart TD
  Need([지원/진단 필요])
  PythonNeed{"Python 실행환경 또는 import 문제?"}
  Env["$find-local-python-envs<br/>python3 -m find_local_python_envs inventory<br/>manifest/import/env inventory + ranked commands"]
  InstallNeed{"기존 env/cache로 부족?"}
  Install["$install-deps-with-agent<br/>cache-first 후 one install/download agent"]
  OOMNeed{"large data/model/batch/concurrency/OOM risk?"}
  OOM["$inspect-oom-risk<br/>static risk map, scaling variable, memory domain, mitigation"]
  RepoReviewNeed{"multi-agent repo audit/review 필요?"}
  RepoReview["$inspect-repo-with-agents<br/>3-6 perspectives, file/line findings"]
  RunNeed{"long-running execution 상태 확인?"}
  Monitor["$monitor-running-execution<br/>python3 -m orchestrate_task_cycle monitor<br/>canonical step=run monitor event<br/>running/completed_pending_validation != success"]
  EvidenceNeed{"이전 evidence 재사용 가능성?"}
  Cache["$manage-evidence-cache<br/>python3 -m orchestrate_task_cycle evidence-cache<br/>reuse 후보만 제공; pass로 변환하지 않음"]
  Output([지원 결과를 caller packet 또는 사용자 보고로 반환])

  Need --> PythonNeed
  PythonNeed -- yes --> Env --> InstallNeed
  InstallNeed -- yes --> Install --> Output
  InstallNeed -- no --> Output
  PythonNeed -- no --> OOMNeed
  OOMNeed -- yes --> OOM --> Output
  OOMNeed -- no --> RepoReviewNeed
  RepoReviewNeed -- yes --> RepoReview --> Output
  RepoReviewNeed -- no --> RunNeed
  RunNeed -- yes --> Monitor --> Output
  RunNeed -- no --> EvidenceNeed
  EvidenceNeed -- yes --> Cache --> Output
  EvidenceNeed -- no --> Output
```

### Mermaid Flowchart 7: anti-loop and progress detection internals

```mermaid
flowchart TD
  Inputs["inputs<br/>registry, artifact paths, changed files,<br/>runner validation, output delta,<br/>failure autopsies, gate states,<br/>scenario/command/blocker/stochastic fields,<br/>long-run event history, Part P/Q evidence,<br/>S7-S10 hook/debt fields,<br/>scoped progress via --gate-state-json"]

  LoopbackCLI["python3 -m audit_cycle_loopback evaluate<br/>static package command"]
  LoopbackDispatch["__main__.py → commands.py<br/>static CommandSpec registry + dispatch"]
  LoopbackFacade["package __init__.py main<br/>legacy public facade + runtime-cache bridge<br/>cli.py argument/output orchestration"]
  LoopbackAPI["api.py<br/>stable explicit public API exports<br/>CLI/cache 실행 경로와 분리"]
  LoopbackEval["evaluator.py<br/>LoopbackEvaluator / ordered evaluation"]
  AdapterPolicy{"explicit quality/domain metric policy supplied?"}
  AdapterLayer["adapters.py facade<br/>adapter_loading + artifact_selection<br/>artifact_compatibility + adapter_quality"]
  QualityLayer["quality.py facade<br/>quality_policy + quality_values + quality_gates<br/>metric aliases/axes/thresholds stay repo-local"]
  GenericOnly["generic contracts only<br/>domain metric gates remain not_evaluated<br/>no global metric fallback"]
  EvalStages["ordered stage families<br/>setup_* → failure_* → progress_*<br/>→ decision_* → finalize_*"]
  ConsumerReceipt["consumer receipt + decision identity<br/>artifact/subject/revision/lineage binding 재검증"]
  PrimaryMetric["typed primary metric comparator<br/>scalar / set / vector / ordered / predicate<br/>basis migration + source-separated high-water gate"]
  Reachability["cycle reachability<br/>producer supply / acceptance scale / lane / quota로<br/>현재 cycle에서 가능한 변화인지 판정"]
  Recurrence["cli.py post-evaluator recurrence identity<br/>stable basis + semantic delta<br/>packet을 downgrade할 수 있음"]
  ScopedSelect["setup_external_gates<br/>scoped declarations 추출 + conflict fail-close<br/>actual changed-file/content evidence 전달"]
  ScopedAssess["progress stage의 shared assess_scoped_progress<br/>retained_change_classification 재계산<br/>task/root/global reset permission 분리"]
  LoopGates["gates + acceptance + verification + blockers<br/>coverage/substance, verifier status, target movement,<br/>source + invariant owner + decisive function separation,<br/>scenario/argv/blocker/stochastic, compatibility skip,<br/>feature/frozen-input/Q1, failure/source/chain stalls"]
  RootCause["root_cause.py + root_cause_runtime.py<br/>hypotheses, repo-owned actionability,<br/>reason_to_attempt, exhaustion and untried repair"]
  LoopRegistry["registry.py + family_registry.py + finalized_state.py<br/>durable_projection.py + registry_identity.py<br/>evaluator가 registry/root-cause/seal rows를 반환"]
  LoopPacket["packet.py + assembly.py + outcome.py<br/>anti_loop_progress_gate packet<br/>effective dispositions + allowed task kinds"]
  DurableCandidate["cli.py가 recurrence 반영 후 조립<br/>recurrence-bound durable_mutation_candidate<br/>orchestrator가 최종화"]

  DetectCLI["python3 -m orchestrate_task_cycle progress-loop<br/>static package command"]
  DetectFacade["progress/cli.py → analysis.py compatibility facade<br/>ProgressLoopAnalyzer builds AnalysisContext"]
  DetectPipeline["AnalysisPipeline<br/>six ordered Strategy stages"]
  DetectEvidence["1 EvidenceCollectionStage<br/>evidence.py + fingerprints.py + normalizers.py"]
  DetectAggregate["2 ProgressAggregationStage<br/>declared/observed/input/provider aggregation"]
  DetectRoots["3 RootMetricStage<br/>root axis/key + feature symbol"]
  DetectGates["4 GateEvaluationStage<br/>output/input/validator + terminal/provider gates"]
  DetectFindings["5 FindingBuilderStage<br/>loop/stall/terminal findings"]
  DetectResult["6 ResultBuilderStage<br/>loop-breaker packet + prepared registry update"]
  DetectRegistry["progress/registry.py<br/>evidence collection 중 history load<br/>result에서 update candidate 준비"]

  GTPolicy{"explicit gt_constraint_policy supplied?"}
  GTDetector["python3 -m orchestrate_task_cycle gt-conflict<br/>detect_gt_constraint_conflict.py facade<br/>gt_constraint/cli.py → analysis.py + common.py"]
  GTGeneric["generic provider/credential checks only<br/>generalization inference disabled"]
  Capability["derive adapter capability_ladder<br/>consume only when explicitly supplied<br/>absent => no domain rung candidate"]

  Derive["$derive-improvement-task<br/>next task / terminal blocker / user escalation constraints"]

  Inputs --> LoopbackCLI --> LoopbackDispatch --> LoopbackFacade --> LoopbackEval
  LoopbackAPI -. explicit import surface .-> LoopbackEval
  LoopbackEval --> AdapterPolicy
  AdapterPolicy -- yes --> AdapterLayer --> QualityLayer --> EvalStages
  AdapterPolicy -- no --> GenericOnly --> EvalStages
  Inputs -. consumer binding evidence .-> ConsumerReceipt
  Inputs -. cycle supply / scale / lane / quota .-> Reachability
  Inputs -. scoped declarations + changed content .-> ScopedSelect --> ScopedAssess
  Inputs -. typed metric evidence .-> PrimaryMetric
  ConsumerReceipt -. setup / failure / finalize checks .-> EvalStages
  Reachability -. earlier progress stage .-> PrimaryMetric
  ScopedAssess -. earlier progress stage .-> PrimaryMetric
  PrimaryMetric -. later progress / decision checks .-> EvalStages
  EvalStages --> LoopGates --> RootCause --> LoopRegistry --> LoopPacket
  LoopPacket --> Recurrence --> DurableCandidate --> Derive

  Inputs --> DetectCLI --> DetectFacade --> DetectPipeline --> DetectEvidence --> DetectAggregate --> DetectRoots --> DetectGates --> DetectFindings --> DetectResult --> Derive
  DetectRegistry -. history input .-> DetectEvidence
  DetectResult -. prepared update .-> DetectRegistry
  Inputs --> GTPolicy
  GTPolicy -- yes --> GTDetector --> Derive
  GTPolicy -- no --> GTGeneric --> Derive
  Inputs --> Capability --> Derive
```

### Mermaid Flowchart 8: off-chain session observation, ModeSpec, bounded repair

```mermaid
flowchart TD
  Registry["tracked mode-profiles.json<br/>capture / consume / reaction"]
  Activation["activation provenance<br/>default / user_instruction / caller_policy / authority_record<br/>observation cannot self-activate"]
  Override["repo-local override<br/>capability reduction + probe additions only"]
  Resolve["python3 -m orchestrate_task_cycle mode-profile<br/>resolve + verify-resolution<br/>canonical normal|bootstrap and phase order unchanged"]

  Stop["optional Codex/Claude Code Stop hook<br/>session_id + absolute transcript_path"]
  Capture["python3 -m audit_session_governance capture<br/>capture_projection.py<br/>bounded strict UTF-8/JSON + no-follow walk<br/>user/assistant text only; no raw fallback"]
  Offchain["repo-local off-chain projection<br/>logs/codex or logs/claude-code/session.jsonl<br/>narrow ignore only when retention policy requires"]
  Inspect["python3 -m audit_session_governance audit inspect<br/>session_audit.py → session_service.py<br/>→ session_parsing.py + session_packets.py<br/>body-free content-addressed packet"]
  ProducerValidate["python3 -m audit_session_governance audit validate<br/>producer schema/source projection validation"]
  Collector["result_contract/_session_audit/collection.py<br/>→ packet.py + projection.py<br/>consumer-owned source/schema/canonical-ref 검사"]
  Replay["packet.py가 producer validate_packet 지연 import<br/>deterministic replay + exact source parity<br/>독립 verifier가 아닌 advisory compatibility check"]

  Direct["direct packet / result-owned projection<br/>packet-owned canonical or cross-source claim"]
  Advisory["advisory / not_evaluated<br/>no GT, authority, validation, progress,<br/>completion, or verdict upgrade"]
  Required["caller-required audit satisfied<br/>only by verified collector projection"]
  Rejected["required audit not satisfied<br/>direct/result-owned, forged, partial,<br/>quarantined, or failed projection"]
  Comparator["external/future comparator contract<br/>현재 repository에는 미구현<br/>두 입력·relation·binding을 독립 소유해야 함"]
  Consumers["existing consumers only<br/>context / loopback / validate / issue / derive / report<br/>no session_audit canonical phase"]

  RepairGate{"validated audit-index-repair<br/>with non-default activation?"}
  Rebuild["python3 -m audit_session_governance audit auto-rebuild-index<br/>only .task/session_audit/index.json<br/>manual path: audit rebuild-index"]
  Receipt["content-derived repair receipt<br/>resolution/operation/target/index ID<br/>before/after SHA-256"]
  Owner["semantic/source/task/acceptance/goal/authority change<br/>route to owning governed skill"]

  Registry --> Resolve
  Activation --> Resolve
  Override --> Resolve
  Resolve -- capture enabled --> Stop --> Capture --> Offchain --> Inspect --> ProducerValidate --> Collector --> Replay
  Replay -- complete + exact parity --> Advisory
  Replay -- complete + bound + evaluated integrity + consumable + exact parity + required --> Required --> Consumers
  Replay -- partial/quarantined/failed --> Advisory
  Replay -- required but any trust condition fails --> Rejected
  Direct --> Advisory
  Direct -. required gate .-> Rejected
  Advisory -. optional observation .-> Consumers
  Advisory -. future relation request / packet claim stays advisory .-> Comparator
  Comparator -. not implemented here .-> Consumers
  Resolve -. consume/reaction ceiling .-> Advisory
  Resolve --> RepairGate
  RepairGate -- exact allowlist --> Rebuild --> Receipt --> Consumers
  RepairGate -- absent or semantic mutation --> Owner
```

### Mermaid Flowchart 9: authority v2 settlement and terminal-wait selection

```mermaid
flowchart TD
  subgraph AuthorityV2["operation-bound authority v2"]
    Manifest["authority.operations.json<br/>versioned operation / authorization mechanism<br/>capability / mutation / risk"]
    Request["exact request + existing regular-file subject<br/>session ceiling + GT autonomy envelope"]
    Mechanism{"authorization_mechanism"}
    Evaluate["grant mechanism<br/>manage_agent_authority authority evaluate<br/>policy/source snapshot + one covering grant or explicit composition"]
    Decision{"grant decision"}
    WaitRoute["approval_required / denied / waiting_external_input<br/>capability_unavailable / blocked_by_goal_truth<br/>classification_repair / conflict / not_applicable"]
    TypedApproval["typed_source_approval<br/>exact source/rank/subset/lineage owner verifier"]
    BoundLifecycle["bound_lifecycle_artifact<br/>exact reservation/receipt/state-change owner verifier"]
    NoAuthority["none<br/>authority decision=not_applicable<br/>owner contract만 적용"]
    Reserve["reserve exact uses<br/>selected grant + unique lineage ancestors CAS"]
    PreDispatch["authority verify --stage pre_dispatch<br/>subject / manifest / grant / reservation freshness"]
    ClosedPacket["orchestrate_task_cycle authority-packet<br/>result-contract --target authority --mode block<br/>owner artifacts를 workspace에서 재개방"]
    InitialPreCommit["initial authority verify --stage pre_commit<br/>packet-bound current state 검증"]
    Prepare["optional operation owner PREPARE<br/>declared non-active journal / prospective effect binding"]
    RevalidatePreCommit["after PREPARE reopen/revalidate<br/>current subject / packet / pre_commit"]
    Effect["operation-specific exact effect<br/>bounded mutation"]
    ExecutionResult["immutable execution-result binding"]
    Settlement{"effect status"}
    Consume["consume<br/>authority_use_receipt + lineage state changes"]
    Release["not_started | verified_no_effect<br/>release reserved use"]
    Quarantine["unknown_effect<br/>quarantined_unknown_effect; budget 유지"]
    Activation["optional operation owner settlement validation<br/>declared expected-current CAS activation"]

    Request --> Manifest --> Mechanism
    Mechanism -- grant --> Evaluate --> Decision
    Decision -- decision=allowed + mutation --> Reserve --> PreDispatch --> ClosedPacket --> InitialPreCommit --> RevalidatePreCommit --> Effect --> ExecutionResult --> Settlement
    InitialPreCommit -. owner contract가 선언할 때 .-> Prepare --> RevalidatePreCommit
    Decision -- other closed decision --> WaitRoute
    Mechanism -- typed_source_approval --> TypedApproval
    Mechanism -- bound_lifecycle_artifact --> BoundLifecycle
    Mechanism -- none --> NoAuthority
    Settlement -- known effect --> Consume
    Consume -. owner contract가 선언할 때 .-> Activation
    Settlement -- not_started / verified no effect --> Release
    Settlement -- unknown --> Quarantine
  end

  subgraph TerminalWait["terminal-wait bounded pre-cycle re-entry"]
    Current[".task/terminal_wait_baseline/current.json<br/>pointer → activation → completion → snapshot<br/>authority settlement + source bindings 재검증"]
    ExactPremise["exact-subject-premise<br/>artifact-reopened consumed v2 receipt<br/>v1/raw digest는 autonomous wake 불가"]
    Tick["selection-tick<br/>current baseline auto-discovery<br/>sticky exact-premise/effective-authority rows"]
    TickStatus{"tick status"}
    Preserve["no_op | baseline_recorded<br/>terminal wait 유지<br/>fanout=false, full_cycle=false"]
    Recovery["recovery_required<br/>pending selection-publication forward recovery"]
    DriftRepair["drift_blocked<br/>committed-head / ambiguous-lineage drift repair"]
    DeriveOnly["selection_required<br/>기존 derive의 3-lens selection만 실행<br/>full implementation cycle은 시작하지 않음"]
    Outcome{"selection outcome"}
    Publication["distinct successor<br/>selection-publication prepare/apply/recover<br/>exact before/after journal"]
    ProjectionWrites["owner-committed archive/log/task-pack projection은<br/>unchanged bind/verify; publisher-owned advice/index만 write"]
    TaskPointer["task.md alias를 마지막에 write<br/>committed publication receipt"]
    NormalCycle(["successor가 활성화됨<br/>이후 fresh normal cycle 시작 가능"])
    RuntimeReceipts["terminal_wait again<br/>3 lens projections + canonical synthesis output<br/>preliminary decision + selection-decision receipt"]
    Rebase["A predecessor → material trigger B<br/>receipt로 acknowledge → input-stable safe baseline C"]
    DirectFinal["direct full final derive result<br/>C + receipt identity + exact analysis manifest"]
    BaselineSubject["terminal-wait-baseline materialize-subject<br/>non-active content-addressed exact authority subject"]
    BaselineArtifacts["terminal-wait owner effect artifacts<br/>immutable snapshot + completion<br/>current pointer는 아직 미노출"]
    BaselineActivate["settled use receipt 검증 후 activate<br/>expected predecessor CAS<br/>current pointer를 마지막에 노출"]

    Current --> Tick
    ExactPremise --> Tick
    ClosedPacket -. exact authority scope row .-> Tick
    Tick --> TickStatus
    TickStatus -- no_op / baseline_recorded --> Preserve
    TickStatus -- recovery_required --> Recovery --> Tick
    TickStatus -- drift_blocked --> DriftRepair --> Tick
    TickStatus -- selection_required --> DeriveOnly --> Outcome
    Outcome -- distinct successor --> Publication --> ProjectionWrites --> TaskPointer --> NormalCycle
    Outcome -- terminal_wait --> RuntimeReceipts --> Rebase --> DirectFinal --> BaselineSubject
    BaselineSubject -. publish_terminal_wait_baseline_binding subject .-> Request
    Effect -. terminal-wait owner effect .-> BaselineArtifacts --> ExecutionResult
    Consume -. exact settled receipt .-> BaselineActivate --> Current
  end

  LegacyPack["invalid but declared-closed legacy task pack<br/>raw bytes/findings 보존 + exact retirement subject"]
  LegacyArtifacts["raw snapshot/overlay → completion<br/>canonical pack은 변경하지 않고 settlement 대기"]
  LegacyActivation["settled receipt 검증<br/>activate-legacy-retirement"]
  LegacyOverlay["operational retired_legacy projection<br/>historical completion/authority를 증명하지 않음"]
  LegacyPack -. mutate_task_topology authority operation .-> Request
  Effect -. legacy owner effect .-> LegacyArtifacts -. completion binding .-> ExecutionResult
  Consume -. settled legacy-retirement receipt .-> LegacyActivation --> LegacyOverlay
```

## 순수 텍스트 Flowchart

아래 블록은 Mermaid 렌더링 없이도 구조가 보이도록 박스, 분기, 화살표만으로 그린 텍스트 도형이다.

### Text Flowchart 1: 전체 cycle

```text
+--------------------------------------------------------------------------------+
| USER REQUEST / CYCLE CANDIDATE                                                 |
+--------------------------------------------------------------------------------+
        |
        v
+--------------------------------------------------------------------------------+
| PRE-CYCLE TERMINAL-WAIT GATE                                                   |
| - verified authority-settled current가 있으면 Text Flowchart 9의 selection-tick|
| - no_op|baseline_recorded: wait 유지 후 종료                                    |
| - recovery_required: pending publication forward recovery 후 gate 재실행        |
| - drift_blocked: committed-head/lineage drift를 명시적으로 수리 후 gate 재실행   |
| - selection_required: derive selection만 실행; successor publish 뒤에만 진행    |
| - verified current가 없으면 normal/bootstrap 경로로 진행                        |
+--------------------------------------------------------------------------------+
        | no current / activated successor only
        v
+--------------------------------------------------------------------------------+
| CONTEXT                                                                        |
| - README, task.md, .agent_goal, .agent_log, .task, .issue, .schema, .contract  |
+--------------------------------------------------------------------------------+
        |
        v
+----------------------------+     +---------------------------------------------+
| $maintain-cycle-ledger     | --> | .task/cycle/<cycle-id>/                    |
| ledger init                |     | initialization.json, current_stage.json,    |
|                             |     | packets/; stage.jsonl은 첫 append 때 생성  |
+----------------------------+     +---------------------------------------------+
        |
        v
+----------------------------+     +---------------------------------------------+
| reusable major-call gate   | --> | packet -> transition -> owning skill       |
| 각 주요 subskill 전/후 반복 |     | -> result-contract -> ledger append         |
| static target/rule registry|     | 다음 target까지 같은 envelope 반복          |
+----------------------------+     +---------------------------------------------+
        |
        v
+----------------------------+     +---------------------------------------------+
| authority mechanism route  | --> | grant+allowed: evaluate/reserve/pre_dispatch|
| from versioned operation   |     | packet -> initial pre_commit -> optional    |
|                            |     | PREPARE -> revalidate -> effect/settle      |
| manifest + exact subject   |     | typed-source/bound-lifecycle: owner verifier|
|                            |     | none: not_applicable; other decisions route |
+----------------------------+     +---------------------------------------------+
        |
        v
      +--------------------+
      | task.md exists ?   |
      +--------------------+
        | yes                                      | no
        v                                          v
+----------------------------+       +-------------------------------------------+
| continue active task       |       | bootstrap transaction                     |
| 기존 task.md로 진행        |       | initial_init -> schema reconcile          |
+----------------------------+       | task.md 생성 후 새 cycle의 context로 복귀 |
        |                            +-------------------------------------------+
        v
+----------------------------+     +---------------------------------------------+
| repo-adapter scan/handoff  | --> | manifest/map/component digests + declared   |
| metadata validation only  |     | phase/consumer/hook bindings                |
| adapter_loaded=false      |     | downstream owning consumer loads/runs hook |
|                            |     | missing quality policy -> metric not_eval   |
+----------------------------+     +---------------------------------------------+
        |
        v
+----------------------------+     +---------------------------------------------+
| $normalize-acceptance-and- | --> | python3 -m normalize_acceptance_and_demo    |
| demo                       |     | identity -> acceptance packet               |
| measurable target contract |     | verifier/scenario/freshness/hook contract  |
+----------------------------+     +---------------------------------------------+
        |
        v
+----------------------------+     +---------------------------------------------+
| $plan-validation-scope     | --> | python3 -m plan_validation_scope plan      |
| changed surfaces classify  |     | current_only / affected_chain / full_chain |
| current decision binding   |     | source/invariant/function separation       |
|                             |     | defect -> warn + affected_chain floor      |
+----------------------------+     +---------------------------------------------+
        |
        v
+----------------------------+     +---------------------------------------------+
| $build-validation-set-with-| --> | planning workflow mode                     |
| agents planning            |     | build 입력의 oracle/split/leakage 정책     |
+----------------------------+     +---------------------------------------------+
        |
        v
+----------------------------+     +---------------------------------------------+
| $task-md-agent-governance  | --> | implementation + audit + task_miss         |
| worker implementation      |     | worker outputs, repo audit, miss reports   |
+----------------------------+     +---------------------------------------------+
        |
        v
+----------------------------+     +---------------------------------------------+
| result contract + adapter  | --> | result_contract/api.py -> engine.py         |
| validation + structure     |     | -> validation_pipeline -> RuleRegistry      |
| field/origin/code audit    |     | -> rules/* + sibling _rule_checks/*         |
+----------------------------+     +---------------------------------------------+
        |
        v
+----------------------------+     +---------------------------------------------+
| $run-task-code-and-log     | --> | run result + content-bound .agent_log      |
| command execution          |     | success/running/partial/failed/not_run     |
| full body-free argv        |     | long_run_launch may only create handoff    |
+----------------------------+     +---------------------------------------------+
        |
        v
      +--------------------+
      | run is running ?   |
      +--------------------+
        | yes                                      | no
        v                                          v
+----------------------------+       +-------------------------------------------+
| $monitor-running-execution |       | $review-cycle-output-quality              |
| step=run long_run_* event  |       | single read-only quality reviewer          |
| PID/log/heartbeat/artifacts|       | hook result id+digest가 final decision에  |
| running/pending != success |       | 실제 소비됐을 때만 positive axis         |
|                             |       +-------------------------------------------+
+----------------------------+                         |
        |                                              v
        |                                +---------------------------------------+
        |                                | $audit-cycle-loopback                 |
        |                                | audit_cycle_loopback package packet    |
        |                                | semantic_progress / anti-loop gates    |
        |                                | pass/fail/not_evaluated gate meaning  |
        |                                | verifier debt + count-key hygiene      |
        |                                | target metric movement + gate compat   |
        |                                | failure stage + root-cause ledger      |
        |                                | chronic blocker debt visibility        |
        |                                | goal-axis/residual/global invariant    |
        |                                | Part P/Q feature/freshness/lineage     |
        |                                | self-resolvable input/provenance route |
        |                                | scoped retained change 재계산          |
        |                                | task/root/global stall reset 분리      |
        |                                +---------------------------------------+
        |                                              |
        |                                              v
        |                                +---------------------------------------+
        |                                | output accounting                     |
        |                                | validation set: build -> leakage      |
        |                                | -> run-oracles -> finalize -> validate|
        |                                | $record-visible-increment             |
        |                                | repo_skill_gap_analysis               |
        |                                | $profile-cycle-efficiency             |
        |                                +---------------------------------------+
        |                                              |
        |                                              v
        +----------------------+-----------------------+
                               |
                               v
+----------------------------+     +---------------------------------------------+
| validation scope finalize  | --> | actual changed files + current decision ref |
| + task-state index scan    |     | source/invariant/function separation gate   |
|                             |     | missing/stale/subject change/coupled=block |
|                             |     | profile floor + task-state index scan       |
+----------------------------+     +---------------------------------------------+
        |
        v
+----------------------------+     +---------------------------------------------+
| $validate-task-completion  | --> | validation_verdict + progress_verdict      |
| final completion gate      |     | complete/partial/failed + progress class   |
|                             |     | required verifier pass before full close    |
|                             |     | target metric movement required when mapped |
|                             |     | scenario/command/blocker/stochastic gates   |
|                             |     | policy debt visible, gate compat skipped    |
|                             |     | long-run pending blocks completion          |
|                             |     | global structure target not consumed local  |
|                             |     | freshness/feature/provenance/frozen gates   |
+----------------------------+     +---------------------------------------------+
        |
        v
+----------------------------+     +---------------------------------------------+
| ledger finalize            | --> | final_candidate -> immutable snapshot      |
| + verify-finalization      |     | CAS current_finalization.json + receipt    |
|                             |     | load_current_finalized_state projection    |
+----------------------------+     +---------------------------------------------+
        |
        v
+----------------------------+     +---------------------------------------------+
| $manage-implementation-    | --> | validated current task issue reconciliation |
| issues                     |     | issue_ids / blockers / evidence_paths       |
+----------------------------+     +---------------------------------------------+
        |
        v
      +----------------------+
      | long-run pending ?   |
      +----------------------+
        | no                                      | yes
        v                                         |
+----------------------------+                    |
| derive preparation         |                    |
| schema pre-derive + slice  |                    |
| validation/issue/profile   |                    |
| -> derive -> schema post   |                    |
| -> final task-state index  |                    |
+----------------------------+                    |
        |                                         |
        +---------------------+-------------------+
                              |
                              v
+----------------------------+     +---------------------------------------------+
| commit -> dashboard/report | --> | $repo-change-commit or explicit skip       |
| final workflow closeout    |     | pending은 partial handoff로만 보고         |
|                            |     | verified ledger -> dashboard -> report     |
|                            |     | closeout commit                            |
+----------------------------+     +---------------------------------------------+
        |
        v
+--------------------------------------------------------------------------------+
| USER REPORT                                                                    |
+--------------------------------------------------------------------------------+
```

### Text Flowchart 2: 목표/권한/인터뷰 계열

```text
+-------------------------------+
| raw user goal prompt          |
+-------------------------------+
              |
              v
+-------------------------------+      +----------------------------------------+
| $shape-agent-goal-prompt      | ---> | draft final_goal.md / conventions.md  |
| preserve raw prompt           |      | 3+ critics: intent/overreach/risk     |
+-------------------------------+      +----------------------------------------+
              |
              v
+-------------------------------+      +----------------------------------------+
| $manage-agent-goal            | ---> | .agent_goal/final_goal.md             |
| merge supported goal truth    |      | .agent_goal/conventions.md            |
+-------------------------------+      +----------------------------------------+
              |
              v
          +-------------------------------+
          | base goal files complete ?    |
          | final_goal + conventions      |
          +-------------------------------+
              | yes                                | no
              v                                    v
+-------------------------------+       +----------------------------------------+
| $deep-interview-goal-context  |       | return to $manage-agent-goal          |
| stateful one-question loop    |       | prerequisite objective/conventions    |
+-------------------------------+       +----------------------------------------+
              |
              v
+-------------------------------+      +----------------------------------------+
| .interview/questions/answers  | ---> | one pending question per invocation   |
| state.md tracks active batch  |      | answers become interview evidence     |
+-------------------------------+      +----------------------------------------+
              |
              v
+-------------------------------+      +----------------------------------------+
| .interview/drafts             | ---> | draft architecture/theory/schema/     |
| not final goal truth          |      | authority files                       |
+-------------------------------+      +----------------------------------------+
              |
              v
        +-----------------------------+
        | 3 evidence reviewers CONFIRM?|
        +-----------------------------+
              | yes                                | no
              v                                    v
        +-----------------------------+      +-------------------------------+
        | 3 critical auditors CONFIRM?|      | revise drafts or ask next     |
        +-----------------------------+      | targeted question             |
              | yes                         +-------------------------------+
              v
        +-----------------------------+
        | user final confirmation ?   |
        +-----------------------------+
              | yes                                | no
              v                                    v
        +-----------------------------+      +-------------------------------+
        | 3-6 final reviewers safe ?  |      | hold writes; ask/record       |
        +-----------------------------+      | missing confirmation          |
              | yes                         +-------------------------------+
              v
+-------------------------------+      +----------------------------------------+
| final .agent_goal writes      | ---> | goal_architecture.md                  |
| all-or-nothing after confirm  |      | goal_theory.md                        |
|                               |      | goal_schema_contract.md               |
|                               |      | agent_authority.md                    |
+-------------------------------+      +----------------------------------------+
              |
              v
+-------------------------------+      +----------------------------------------+
| $manage-schema-contracts      | ---> | .schema/.contract aligned to          |
| task-state index scan/link/   |      | python3 -m manage_task_state_index    |
| audit                         |      | index ...; goal/int IDs               |
+-------------------------------+      +----------------------------------------+

Authority policy/runtime side path:

+-------------------------------+      +----------------------------------------+
| agent_authority.md            | ---> | durable narrowing policy only          |
| versioned operation manifest  |      | operation + exact subject + mechanism  |
+-------------------------------+      +----------------------------------------+
                                                     |
                                                     v
                                       +-----------------------------+
                                       | authorization_mechanism     |
                                       +-----------------------------+
                                         |-- grant
                                         |     -> immutable decision
                                         |     -> allowed mutation only: reserve
                                         |        -> pre_dispatch -> authority-packet
                                         |        -> initial pre_commit -> optional PREPARE
                                         |        -> current/pre_commit revalidation
                                         |        -> effect -> settle
                                         |-- typed_source_approval
                                         |     -> exact source/rank/subset/lineage verifier
                                         |-- bound_lifecycle_artifact
                                         |     -> exact reservation/receipt/state-change verifier
                                         +-- none -> decision=not_applicable; owner contract only

Owner PREPARE/activation is inserted only when that operation's contract declares it.
Authority, local resolution, external input, risk/cost, and GT remain separate axes.

External advice side path:

+-------------------------------+      +----------------------------------------+
| external advice file/body     | ---> | $manage-external-advice               |
+-------------------------------+      | canonical directive + exact clause    |
                                       | disposition coverage                   |
                                       | prepare -> applied/log projections    |
                                       | -> canonical event last               |
                                       | commit receipt or forward recovery    |
                                       | never goal truth or authority          |
                                       +----------------------------------------+
                                                     |
                                                     v
                                       +----------------------------------------+
                                       | active advice packet                   |
                                       | not_goal_truth=true                    |
                                       | consumed by orchestrate/derive/        |
                                       | governance/validate only as non-GT     |
                                       +----------------------------------------+
```

### Text Flowchart 3: task 생성/수정/선택 계열

```text
+-------------------------------+
| next task / terminal-wait     |
| re-entry / task doctor input  |
+-------------------------------+
              |
              v
        +-----------------------------+
        | explicit doctor/pack/retarget?|
        +-----------------------------+
          | yes                                      | no
          v                                          v
+-------------------------------+        +---------------------------------------+
| $task-doctor                  |        | verified terminal-wait current?       |
| explicit direction wins before|        +---------------------------------------+
| autonomous selection tick     |          | yes                      | no
+-------------------------------+          v                          v
                                 +-------------------------+  +------------------+
                                 | Text Flowchart 9 tick   |  | bounded derive   |
                                 +-------------------------+  | selection        |
                                   | no_op/baseline_recorded|  +------------------+
                                   |   -> STOP; no fanout   |           |
                                   | recovery_required      |           |
                                   |   -> forward recovery  |           |
                                   |   -> re-run tick       |           |
                                   | drift_blocked          |           |
                                   |   -> explicit repair   |           |
                                   |   -> re-run tick       |           |
                                   | selection_required     |           |
                                   +-----------+------------+           |
                                               |                        |
                                               +-----------+------------+
                                                           |
                                                           v
                                                +------------------------+
                                                | $derive-improvement-task|
                                                | selection boundary only |
                                                +------------------------+
          |                                          |
          v                                          v
+-------------------------------+        +---------------------------------------+
| read direction sources        |        | load planning context                 |
| user instruction, task.md,    |        | .agent_goal, authority, advice,       |
| .agent_goal, named advice,    |        | .issue, task_miss, candidates,        |
| .task, .issue, schema         |        | task_pack, schema, review, loopback   |
+-------------------------------+        +---------------------------------------+
          |                                          |
          v                                          v
+-------------------------------+        +---------------------------------------+
| archive old task              |        | analysis fanout                       |
| $record-agent-work-log        |        | - goal/schema alignment audit         |
| past_task before overwrite    |        | - 2-4 task_miss agents                |
+-------------------------------+        | - candidate scan                      |
          |                              | - task_pack scan                      |
          v                              | - 1 issue-fit agent                   |
+-------------------------------+        | - 3 improvement agents                |
| write task.md or task_pack    |        | - 3 durable lens projections          |
| preserve scope_fidelity,      |        | - canonical synthesis decision        |
| envelope, verifier contract,  |        +---------------------------------------+
| terminal/global residuals,    |                         |
| G-axis/cost/P-Q/S7-S10 debt   |                         |
+-------------------------------+                         v
          |                              +---------------------------------------+
          v                              | apply hard selection gates            |
+-------------------------------+        | anti_loop effective dispositions,     |
| index / schema / issue /      |        | allowed_task_kinds, adapter defects,  |
| advice reconciliation         |        | chain stalls, sealed families,        |
+-------------------------------+        | verifier debt, count-key hygiene,     |
                                         | goal-axis, residual cost, global keys |
                                         | scoped task/root/global reset debt,   |
                                         | feature/freshness/frozen-input debt,  |
                                         | hook provenance + primary reason rank |
          |                              | no producer self-report truth         |
          |                              +---------------------------------------+
          v                                               |
+-------------------------------+                         v
| optional task-direction commit|        +---------------------------------------+
| $repo-change-commit           |        | synthesis decision                    |
+-------------------------------+        +---------------------------------------+
          |                                      |
          |                                      +------------------------------+
          |                                      | mutually exclusive outcome   |
          |                                      +------------------------------+
          |                                        | successor       | wait       | blocked/escalation
          |                                        v                 v            v
          |                         +-------------------------+ +----------------+ +------------------+
          |                         | owner archive/log/pack  | | B receipt ->   | | sealed family +  |
          |                         | commit first; candidate | | safe C ->      | | bounded report   |
          |                         | retained/applied/supers.| | authority-     | +------------------+
          |                         | bind owner projections;| | settled current|
          |                         | advice/index -> task.md | +----------------+
          |                         | last -> receipt         |          |
          |                         +-------------------------+          |            |
          |                                        |                 |            |
          +----------------------------------------+-----------------+------------+
                                                           |
                                                           v
                         +----------------------------------+
                         | $manage-task-state-index         |
                         | python3 -m manage_task_state_index|
                         | index scan + index link/audit    |
                         +----------------------------------+

Anti-loop and efficiency inputs into derive:

+-------------------------------+      +----------------------------------------+
| run + quality + output-delta  | ---> | orchestrate_task_cycle progress-loop  |
| failure autopsy + P/Q/S fields|      | progress/cli.py -> AnalysisContext    |
+-------------------------------+      | -> AnalysisPipeline six stages       |
                                       | evidence -> aggregation -> roots      |
                                       | -> gates -> findings -> result        |
                                       +----------------------------------------+
                                                     |
                                                     v
                                       +----------------------------------------+
                                       | $audit-cycle-loopback                  |
                                       | python3 -m audit_cycle_loopback        |
                                       | evaluate -> commands.py -> package     |
                                       | __init__ facade/cache -> cli.py        |
                                       | -> evaluator.py; api.py separate       |
                                       | semantic_progress, root family,        |
                                       | explicit quality/domain metrics,        |
                                       | effective dispositions                 |
                                       | evaluation_status pass/fail/not_eval   |
                                       | target movement + gate compatibility   |
                                       | failure_surface_stage_gate             |
                                       | root-cause ledger + sealed families    |
                                       | chronic blocker counters               |
                                       | verifier, count-key, residual, global  |
                                       | feature/freshness/frozen-input route   |
                                       | self-resolvable input/provenance route |
                                       +----------------------------------------+
                                                     |
                                                     v
                                       +----------------------------------------+
                                       | $optimize-task-slice                  |
                                       | state_transition / batch / evidence / |
                                       | verifier_completion / consolidation / |
                                       | stop advisory                         |
                                       +----------------------------------------+
                                                     |
                                                     v
                                       +----------------------------------------+
                                       | $profile-cycle-efficiency             |
                                       | duplicate evidence, metadata-only,    |
                                       | safety_only loops, sprawl budgets     |
                                       +----------------------------------------+
```

### Text Flowchart 4: 구현/실행/검증 계열

```text
+-------------------------------+
| active task.md                |
+-------------------------------+
              |
              v
+-------------------------------+      +----------------------------------------+
| $normalize-acceptance-and-demo| ---> | normalize_acceptance_and_demo identity |
| criteria / non-goals / demo   |      | acceptance packet + envelope           |
| measurable -> verifiable      |      | acceptance_verifier_contract           |
| target metric movement        |      | target_metric_delta warning/debt       |
| scenario coverage             |      | required hook completeness             |
| freshness/input condition     |      | producer execution residual scope      |
+-------------------------------+      +----------------------------------------+
              |
              v
+-------------------------------+      +----------------------------------------+
| $plan-validation-scope plan   | ---> | python3 -m plan_validation_scope plan  |
| changed surface classification|      | current_only / affected_chain / full   |
| artifact/gate compatibility   |      | incompatible gate skipped, not failed  |
+-------------------------------+      +----------------------------------------+
              |
              v
        +-----------------------------+
        | Python/env dependency need? |
        +-----------------------------+
          | yes                                      | no
          v                                          v
+-------------------------------+        +---------------------------------------+
| python3 -m                    |        | skip env discovery                    |
| find_local_python_envs        |        +---------------------------------------+
| inventory; rank commands      |                         |
+-------------------------------+                         |
          |                                                |
          v                                                |
        +-----------------------------+                    |
        | missing dependency/cache ?  |                    |
        +-----------------------------+                    |
          | yes               | no                         |
          v                   v                            |
+-------------------+   +-------------------+              |
| $install-deps-    |   | use ranked env    |              |
| with-agent        |   | no install        |              |
| one install agent |   |                   |              |
+-------------------+   +-------------------+              |
          |                   |                            |
          +---------+---------+----------------------------+
                    |
                    v
        +-----------------------------+
        | validation set needed ?     |
        +-----------------------------+
          | yes                                      | no
          v                                          v
+-------------------------------+        +---------------------------------------+
| python3 -m                    |        | continue to governance                |
| build_validation_set_with_    |        +---------------------------------------+
| agents module pipeline        |                         |
| build -> leakage ->           |                         |
| run-oracles -> finalize ->    |                         |
| validate                      |                         |
+-------------------------------+                         |
          |                                                |
          +--------------------------+---------------------+
                                     |
                                     v
+-------------------------------+      +----------------------------------------+
| $task-md-agent-governance     | ---> | implementation outputs                |
| read task/authority/advice/   |      | worker changes + integration          |
| schema/convention contract    |      | repo audit + .task/task_miss          |
+-------------------------------+      +----------------------------------------+
              |
              v
+-------------------------------+      +----------------------------------------+
| orchestrate_task_cycle        | ---> | code_structure_audit.py facade        |
| code-structure command        |      | -> code_structure/cli.py -> audit.py  |
| depth/fan-out with cohesion   |      | convention_conformance + Q5 debt      |
| reuse/dup/mechanical shards   |      | relocated_mechanical_shard if needed  |
+-------------------------------+      +----------------------------------------+
              |
              v
+-------------------------------+      +----------------------------------------+
| $run-task-code-and-log        | ---> | run evidence + content-bound log       |
| execute specified command     |      | status: success/running/partial/failed|
| preserve full argv            |      | shared integrity inspector before use |
|                               |      | baseline/reproduction/comparison      |
+-------------------------------+      +----------------------------------------+
              |
              v
        +-----------------------------+
        | failure or gate unsatisfiable?|
        +-----------------------------+
          | yes                                      | no
          v                                          v
+-------------------------------+        +---------------------------------------+
| python3 -m run_task_code_and_log|       | keep normal run evidence              |
| failure-autopsy               |        |                                       |
| execution stage ladder        |        +---------------------------------------+
| safe scalar diagnostics only  |                         |
| gate selfcheck defect class   |                         |
+-------------------------------+                         |
          |                                                |
          +--------------------------+---------------------+
                                     |
                                     v
        +-----------------------------+
        | long-running authorized ?  |
        +-----------------------------+
          | yes                                      | no
          v                                          v
+-------------------------------+        +---------------------------------------+
| $monitor-running-execution    |        | $review-cycle-output-quality          |
| step=run long_run_* event     |        | single read-only reviewer             |
| running/pending != success    |        | feature_presence_evidence body anchor |
+-------------------------------+        +---------------------------------------+
          |                                                |
          +--------------------------+---------------------+
                                     |
                                     v
+-------------------------------+      +----------------------------------------+
| $validate-task-completion     | ---> | validate_task_completion              |
| collect evidence + final gate |      | collect-evidence -> validation_verdict|
| final gate matrix             |      | complete / partial / failed           |
| env/run/repo/OOM/miss/issue/  |      | progress_verdict: advanced /          |
| advice/schema/acceptance/ID   |      | safety_only / no_progress / regressed |
| verifier/structure global     |      | not_evaluated verifier blocks         |
| target movement/policy/gate   |      | measurement-only complete is invalid  |
| scenario/argv/blocker/stoch   |      | complete; pending long-run blocks     |
| freshness/feature/provenance  |      | frozen input blocks advance/close     |
+-------------------------------+      +----------------------------------------+
```

### Text Flowchart 5: 진단/환경/의존성 지원 계열

```text
+-------------------------------+
| support / diagnostic need     |
+-------------------------------+
              |
              v
        +-----------------------------+
        | Python import/env problem ? |
        +-----------------------------+
          | yes                                      | no
          v                                          v
+-------------------------------+        +---------------------------------------+
| find_local_python_envs        |        | check OOM risk need                  |
| inventory module command      |        +---------------------------------------+
| output: ranked run commands   |                         |
+-------------------------------+                         v
          |                                  +-----------------------------+
          v                                  | OOM/memory risk surface ?   |
        +-----------------------------+      +-----------------------------+
        | existing env/cache enough ? |        | yes                  | no
        +-----------------------------+        v                      v
          | yes              | no      +--------------------+   +------------------+
          v                  v        | $inspect-oom-risk |   | repo audit need ?|
+-------------------+  +-------------------+                +------------------+
| return command    |  | install-deps-with |                         |
| no install        |  | one setup agent   |                         v
+-------------------+  +-------------------+              +---------------------+
          |                  |                             | $inspect-repo-with  |
          +---------+--------+                             | -agents             |
                    |                                      | 3-6 perspectives    |
                    |                                      +---------------------+
                    |                                               |
                    |                                               v
                    |                                    +----------------------+
                    |                                    | running run check ?  |
                    |                                    +----------------------+
                    |                                      | yes            | no
                    |                                      v                v
                    |                           +-------------------+  +------------------+
                    |                           | orchestrate_task |  | evidence reuse ? |
                    |                           | step=run event   |  +------------------+
                    |                           | pending != pass  |
                    |                           +-------------------+    | yes        | no
                    |                                      |             v            v
                    |                                      |  +-------------------+ +---------+
                    |                                      |  | orchestrate_task | | return  |
                    |                                      |  | _cycle evidence- | | support |
                    |                                      |  | reuse/stale only | | result  |
                    |                                      |  +-------------------+ +---------+
                    |                                      |             |
                    +--------------------------------------+-------------+
                                                   |
                                                   v
                                      +-----------------------------+
                                      | caller packet or user report|
                                      +-----------------------------+
```

### Text Flowchart 6: 상태/로그/이슈/커밋/보고 계열

```text
+-------------------------------+
| grant-authorized mutation     |
| exact operation + subject     |
+-------------------------------+
              |
              v
+-------------------------------+      +----------------------------------------+
| authority v2 grant boundary   | ---> | decision=allowed -> reserve            |
| closed owner artifacts        |      | -> pre_dispatch -> authority-packet    |
|                               |      | -> initial pre_commit verification     |
+-------------------------------+      +----------------------------------------+
              |
              v
+-------------------------------+      +----------------------------------------+
| optional owner PREPARE       | ---> | reopen/revalidate current packet,      |
| when contract declares it   |      | subject, and pre_commit -> exact effect|
|                               |      | -> execution-result -> consume/release |
|                               |      | or unknown-effect quarantine           |
+-------------------------------+      +----------------------------------------+
              |
              v
+-------------------------------+
| any skill creates evidence    |
| run/audit/validation/report   |
+-------------------------------+
              |
              +-- fingerprint lane
              |     -> evidence-cache: reuse / fresh_required / stale / unsafe
              |
              +-- work-log lane
              |     -> record_agent_work_log write
              |     -> .agent_log body/index content binding
              |     -> shared no-follow integrity gate
              |        * valid -> normal semantic consumption + index
              |        * legacy_unverified -> readable without integrity claim + index
              |        * unsafe/invalid -> metadata only; no semantic use/index
              |
              +-- result lane
              |     -> result-contract api/engine/pipeline/rules
              |     -> validated ledger append
              |     -> stage.jsonl/current_stage.json/packets + long_run_* events
              |     -> terminal_delta/chronic debt projections -> index
              |
              +-- visible lane
              |     -> record-visible-increment
              |     -> not_validation_evidence=true -> ledger append
              |
              +-- completion bundle lane
                    -> identity-bound final_candidate
                    -> ledger finalize: immutable snapshot + current CAS + receipt
                    -> ledger verify-finalization: authoritative projection

CAS/target-revision conflict side path:

  finalize -> state_commit_status=recovery_required
           -> immutable attempt_memory_disposition=pending_conflict
              (current state unchanged)
           -> ledger pending-finalizations
           -> one of:
              * rebase candidate + finalize retry
                -> successful publish auto-merges matching pending record
              * resolve-pending-finalization --disposition merged
                -> exact committed_finalization_token required -> verify current
              * resolve-pending-finalization --disposition retired
                -> committed token forbidden -> close pending; current unchanged

All valid/indexable log, ledger, and verified-finalization projections converge at:

+-------------------------------+      +----------------------------------------+
| $manage-task-state-index      | ---> | .task/index.jsonl + index.md          |
| index scan/link/audit         |      | task/log/run/audit/val/miss/issue/    |
| nested index command          |      | goal/adv/schema IDs                   |
+-------------------------------+      +----------------------------------------+
              |
              v
+-------------------------------+      +----------------------------------------+
| $manage-implementation-issues | ---> | GitHub issue or .issue/open|resolved  |
| issue open/update/resolve     |      | requires run/validation evidence      |
+-------------------------------+      +----------------------------------------+
              |
              v
+-------------------------------+      +----------------------------------------+
| $repo-change-commit           | ---> | commit hash or skip/block reason      |
| classify dirty worktree       |      | exact staging, validation context     |
| source/workflow/noise split   |      | safety_only/partial blockers in msg   |
+-------------------------------+      +----------------------------------------+
              |
              v
+-------------------------------+      +----------------------------------------+
| orchestrate_task_cycle        | ---> | dashboard/* consumes verified ledger |
| dashboard                     |      | malformed/running/partial visible     |
+-------------------------------+      +----------------------------------------+

The verified-finalization projection also feeds the dashboard directly; the
index/issue/commit lane is a separate convergence path.

              |
              v
+-------------------------------+      +----------------------------------------+
| orchestrate_task_cycle report | ---> | dashboard -> report canonical order  |
| + closeout commit             |      | final_report + ledger artifacts       |
+-------------------------------+      +----------------------------------------+
```

### Text Flowchart 7: anti-loop/progress detection 내부 구조

```text
+----------------------------------------+
| shared inputs                          |
| registry/artifacts/changed files       |
| run/output/failure/gate evidence       |
| scenario/argv/blocker/stochastic data  |
| long-run history + Part P/Q evidence   |
+----------------------------------------+
          |                                      |
          | anti-loop branch                     | progress branch
          v                                      v
+----------------------------------+   +----------------------------------+
| audit_cycle_loopback evaluate    |   | orchestrate_task_cycle           |
| -> commands.py static dispatch   |   | progress-loop -> progress/cli.py |
| -> package facade/cache bridge   |   | -> analysis.py compatibility    |
| -> cli.py -> evaluator.py        |   | -> AnalysisContext/Pipeline     |
| api.py = separate public exports |   +----------------------------------+
+----------------------------------+                 |
          |                                          v
          v                              +----------------------------------+
    +--------------------------+         | six ordered Strategy stages      |
    | explicit quality/domain  |         | 1 evidence collection           |
    | metric policy ?          |         | 2 progress aggregation          |
    +--------------------------+         | 3 root metrics                  |
      | yes              | no            | 4 gate evaluation               |
      v                  v               | 5 finding builder               |
+----------------+ +----------------+    | 6 result builder                |
| adapters facade| | generic only   |    +----------------------------------+
| -> load/select | | domain gates   |                 |
| -> compat/qual | | not_evaluated  |                 v
| quality facade | +----------------+    +----------------------------------+
| -> policy/value|                       | registry history is evidence     |
| -> gates       |                       | input; result prepares update    |
+----------------+                       +----------------------------------+
      |                  |                            |
      +---------+--------+                            |
                v                                     |
+----------------------------------+                  |
| ordered evaluation stages       |                  |
| setup -> failure -> progress     |                  |
| -> decision -> finalize         |                  |
| setup: scoped input/consumer    |                  |
|        probes                   |                  |
| failure/finalize: consumer      |                  |
|        receipt + identity checks|                  |
| progress: reachability -> scoped|                  |
|        assessment -> typed      |                  |
|        primary metric compare   |                  |
| decision/finalize: gates, root  |                  |
|        cause, registry services |                  |
+----------------------------------+                  |
                |                                     |
                v                                     |
+----------------------------------+                  |
| evaluator loopback packet       |                  |
| typed metric: scalar/set/vector |                  |
| ordered/predicate + basis       |                  |
| migration/separated high-water  |                  |
| scoped task/root/global permits |                  |
+----------------------------------+                  |
                |                                     |
                v                                     |
+----------------------------------+                  |
| CLI post-evaluator recurrence   |                  |
| stable basis + semantic delta   |                  |
| may downgrade returned packet   |                  |
+----------------------------------+                  |
                |                                     |
                v                                     |
+----------------------------------+                  |
| build durable mutation candidate|
| only after recurrence is bound  |
| registry/root-cause/seal rows + |
| recurrence; orchestrator finalizes|
+----------------------------------+                  |
                |                                     |
                +------------------+------------------+
                                   v
                      +-----------------------------+
                      | loop packet + durable       |
                      | candidate / progress packet |
                      +-----------------------------+

GT constraint side path:

+-------------------------------+
| explicit gt_constraint_policy?|
+-------------------------------+
  | yes                                      | no
  v                                          v
+-------------------------------+  +-------------------------------------------+
| gt-conflict command           |  | generic provider/credential checks only   |
| -> detector facade ->         |  | generalization inference disabled         |
| gt_constraint cli/analysis    |  +-------------------------------------------+
+-------------------------------+
  |                                          |
  +----------------------+-------------------+
                         |
                         v
               +-------------------------+
               | GT conflict packet      |
               +-------------------------+

Capability side path:

+-------------------------------+
| explicit capability_ladder ?  |
+-------------------------------+
  | yes                                      | no
  v                                          v
+-------------------------------+  +-------------------------------------------+
| adapter-owned domain rung     |  | no domain rung candidate                  |
| candidate for derive          |  | no global ladder fallback                 |
+-------------------------------+  +-------------------------------------------+
  |                                          |
  +----------------------+-------------------+
                         |
                         v
               +-----------------------------+
               | derive-improvement-task     |
               | consumes loop/progress/GT   |
               | and optional rung packets   |
               +-----------------------------+
```

### Text Flowchart 8: off-chain session observation, ModeSpec, bounded repair

```text
Capture and trust lane:

+-------------------------------+
| optional Codex/Claude Stop    |
| session_id + transcript_path  |
+-------------------------------+
              |
              v
+-------------------------------+
| audit_session_governance      |
| capture module command        |
| strict bounded JSON/no-follow |
| user/assistant text only      |
| no raw fallback               |
+-------------------------------+
              |
              v
+-------------------------------+
| repo-local off-chain log      |
| narrow-ignore only when the   |
| repository policy requires it |
+-------------------------------+
              |
              v
+-------------------------------+
| audit_session_governance      |
| audit inspect -> audit validate|
| body-free addressed packet    |
+-------------------------------+
              |
              v
+-------------------------------+      +----------------------------------------+
| result_contract/_session_audit| ---> | collection.py -> packet.py            |
| consumer source/schema/ref    |      | lazy producer validate_packet replay  |
| checks                        |      | parity check; not independent verifier|
+-------------------------------+      +----------------------------------------+
              |
              v
        +-----------------------------+
        | complete + bound +          |
        | evaluated integrity +       |
        | consumable + exact parity?  |
        +-----------------------------+
          | yes                                      | no
          v                                          v
+-------------------------------+        +---------------------------------------+
| non-GT advisory observation   |        | advisory/quarantine only              |
| required audit gate may pass  |        | required audit gate rejects it        |
| but no verdict is upgraded    |        +---------------------------------------+
+-------------------------------+
              |
              v
+-------------------------------+
| existing phases may consume   |
| no session-audit phase added  |
+-------------------------------+

Direct/result-owned packets remain advisory and cannot satisfy required audit.
Packet-owned canonical or cross-source claims also remain advisory. A comparator
that independently owns both inputs, relation code, scalars, binding, and version is
only an external/future contract; it is not implemented in this repository.

Mode and bounded-repair lane:

+-------------------------------+      +----------------------------------------+
| tracked mode-profiles.json    | <--- | default: non-privileged profiles only |
| capture/consume/reaction axes |      | user/caller/authority: required/repair|
|                               |      | reducing local override only          |
|                               |      | observation cannot self-activate      |
+-------------------------------+      +----------------------------------------+
              |
              v
+-------------------------------+
| orchestrate_task_cycle        |
| mode-profile resolve/verify   |
| normal|bootstrap unchanged    |
| no phase/authority/verdict or |
| semantic mutation             |
+-------------------------------+
              |
              v
        +-----------------------------+
        | exact repair allowlist and  |
        | non-default activation?     |
        +-----------------------------+
          | yes                                      | no
          v                                          v
+-------------------------------+        +---------------------------------------+
| audit auto-rebuild-index      |        | route semantic/source/task/goal/      |
| .task/session_audit/index.json|        | authority change to owning skill      |
| before/after hash receipt     |        +---------------------------------------+
| manual: audit rebuild-index   |
+-------------------------------+
```

### Text Flowchart 9: authority v2 settlement and terminal-wait selection

```text
Authority v2 lane:

+----------------------------------------+
| authority.operations.json              |
| exact operation/version/mechanism      |
| existing regular-file subject          |
+----------------------------------------+
                    |
                    v
          +-----------------------------+
          | authorization_mechanism     |
          +-----------------------------+
            |-- typed_source_approval
            |     -> exact source/rank/subset/lineage owner verifier
            |        and authority decision=not_applicable
            |-- bound_lifecycle_artifact
            |     -> exact reservation/receipt/state-change owner verifier
            |        and authority decision=not_applicable
            |-- none -> decision=not_applicable; owner contract only
            |
            +-- grant
                    |
                    v
          +-----------------------+
          | immutable grant       |
          | decision              |
          +-----------------------+
            | allowed mutation                 | other closed status
            v                                  -> exact status route; stop
+----------------------------------+
| reserve exact lineage uses       |
| -> verify pre_dispatch           |
| -> closed authority-packet       |
| -> result-contract block gate    |
| -> initial pre_commit verify     |
| -> optional owner PREPARE only   |
|    when its contract declares it |
| -> reopen/revalidate current     |
|    packet/subject/pre_commit     |
| -> exact effect + execution-result|
+----------------------------------+
            |
            v
          +-----------------------+
          | effect status         |
          +-----------------------+
            | known      | not_started or verified_no_effect   | unknown
            v            v                                      v
+------------------+ +------------------+ +-------------------------------+
| consume          | | release reserved | | quarantined_unknown_effect    |
| authority-use    | | use with exact   | | reserved budget is not        |
| receipt + CAS    | | no-effect proof  | | restored automatically        |
+------------------+ +------------------+ +-------------------------------+
          |
          v
+----------------------------------------+
| optional owner settlement after-image   |
| validation + expected-current CAS       |
| activation only when contract declares  |
+----------------------------------------+

All other grant decisions route by their exact closed status. Authority, local
resolution, external input, risk/cost, and goal truth stay independent.

Terminal-wait pre-cycle lane:

+----------------------------------------+
| .task/terminal_wait_baseline/current.json|
| pointer/activation/completion/snapshot  |
| authority settlement/source revalidation|
+----------------------------------------+
                    |
                    v
+----------------------------------------+      +--------------------------------+
| selection-tick                         | <--- | exact-subject-premise          |
| current baseline auto-discovery        |      | consumed artifact-verified v2 |
| sticky premise/effective-authority rows|      | raw/v1 alone cannot wake      |
+----------------------------------------+      +--------------------------------+
                    |
                    v
          +-----------------------+
          | tick status           |
          +-----------------------+
            | no_op/baseline_recorded
            |   -> preserve wait; no cycle init and no proposal fanout
            |
            | recovery_required
            |   -> pending selection-publication forward recovery -> re-run tick
            |
            | drift_blocked
            |   -> committed-head/lineage drift explicit repair -> re-run tick
            |
            | selection_required
            v
+----------------------------------------+
| existing derive selection only         |
| three durable lenses + canonical       |
| synthesis; no implementation cycle yet |
+----------------------------------------+
                    |
                    v
          +-----------------------+
          | selection outcome     |
          +-----------------------+
            | distinct successor               | terminal_wait again
            v                                  v
+----------------------------------+   +--------------------------------------+
| selection-publication            |   | trigger B receipt chain              |
| prepare exact before/after journal|   | lenses -> synthesis -> preliminary  |
| owner archive/log/task-pack      |   | decision -> selection receipt       |
| unchanged bind/verify            |   +--------------------------------------+
| publisher advice/index writes    |                  |
| task.md alias last                |                  v
| verify -> committed receipt       |   +--------------------------------------+
+----------------------------------+   | acknowledge/rebase                  |
            |                         | predecessor A -> material B        |
            v                         | -> input-stable safe baseline C    |
+----------------------------------+   +--------------------------------------+
| fresh normal cycle may start     |                  |
| from the activated successor     |                  |
+----------------------------------+                  |
                                                    v
                                      +--------------------------------------+
                                      | direct full final derive result      |
                                      | C + receipt + reopened analysis      |
                                      +--------------------------------------+
                                                    |
                                                    v
                                      +--------------------------------------+
                                      | terminal-wait-baseline               |
                                      | materialize non-active exact subject |
                                      | -> authority v2 publish settlement   |
                                      | -> immutable snapshot/completion     |
                                      | -> consume -> predecessor CAS        |
                                      | -> expose current pointer last       |
                                      +--------------------------------------+
                                                    |
                                                    +----> next selection-tick

Legacy task-pack settlement reuse:

  invalid but declared-closed pack + preserved raw bytes/findings
    -> exact per-pack retirement subject
    -> grant-authorized mutate_task_topology packet + initial pre_commit verification
    -> PREPARE -> current packet/pre_commit revalidation
    -> immutable raw snapshot/overlay -> completion
       (canonical pack remains unchanged; settlement is still pending)
    -> consume exact completion-bound use -> activate-legacy-retirement
    -> operational retired_legacy projection

The overlay does not prove historical completion, dependency satisfaction,
provenance repair, or historical authority. Pending mutation/publication/settlement
is recovered by exact forward replay; ambiguous state is never chosen by filename order.
```

### 스킬별 빠른 참조

```text
orchestrate-task-cycle
  terminal-wait current가 있으면 pre-cycle selection-tick -> no_op|baseline_recorded / recovery_required / drift_blocked / selection_required를 먼저 판정하고, distinct successor가 recoverable selection-publication으로 활성화된 뒤에만 context -> ledger init -> authority-mechanism routing -> task bootstrap when absent -> repo-adapter scan/handoff -> acceptance/verifier/scenario/freshness/target-movement contracts -> validation-scope plan -> validation-set planning workflow -> governance -> code-structure -> run or long-run branch -> review/loopback or monitor -> validation-set build/leakage/run-oracles/finalize/validate -> visible/gap/profile evidence -> validation-scope finalize + task-state index scan -> validate current task -> final_candidate -> ledger finalize/verify-finalization -> issue reconciliation -> schema/derive/index only when promotion is allowed -> commit -> verified dashboard -> report -> closeout; every major subskill call uses packet -> transition -> owning call -> result-contract -> ledger append, while ModeSpec/session observation remains an optional non-canonical sidecar

maintain-cycle-ledger
  cycle init creates initialization.json/current_stage.json/packets -> first canonical append creates stage.jsonl -> packet link -> preserve terminal_delta_record/unchanged_ref and S10 blocker persistence fields -> final_candidate -> immutable snapshot + expected-predecessor/target-revision CAS -> committed receipt or state_commit_status=recovery_required + immutable attempt_memory_disposition=pending_conflict -> rebased successful finalize auto-merges a matching pending record, explicit merged requires exact committed_finalization_token before verification, explicit retired forbids that token and leaves current unchanged -> verify-finalization/load_current_finalized_state -> dashboard/report

validate-subskill-result-contract
  subskill result -> orchestrate_task_cycle result-contract -> result_contract/api.py -> engine.py -> validation_pipeline -> SessionAuditRule + RuleRegistry -> rules/* with sibling _rule_checks/* -> required fields including long-run detail, command_argv, scenario/blocker/stochastic gates and collector origin -> warn/block -> ledger event

manage-agent-goal
  user goal/conventions -> preserve/merge -> final_goal.md + conventions.md

shape-agent-goal-prompt
  raw prompt -> draft goal/conventions -> 3+ critics -> reconciled draft -> optional manage-agent-goal write

deep-interview-goal-context
  base goal gate -> one-question interview -> drafts -> evidence review -> audit -> user confirm -> final review -> four .agent_goal files

manage-goal-architecture
  repo map -> component responsibilities -> goal relevance -> goal_architecture.md

manage-goal-theory
  technical evidence -> mechanisms/assumptions/tradeoffs/validation logic -> goal_theory.md

manage-agent-authority
  current ceiling + durable narrowing policy -> authority.operations.json exact operation/existing-file subject + authorization_mechanism -> grant+allowed mutation only: policy/source snapshots -> grant/delegation/composition -> immutable decision -> reserve -> pre_dispatch verification -> closed orchestrator authority-packet -> initial pre_commit verification -> optional owner PREPARE when declared -> reopen/revalidate current packet/subject/pre_commit -> exact effect -> consume with execution-result or not_started|verified_no_effect release / unknown-effect quarantine -> authority-use receipt and CAS state; typed_source_approval and bound_lifecycle_artifact use their exact owner verifiers, none returns not_applicable, and authority/local resolution/external input/risk/GT/design decisions remain separate

manage-schema-contracts
  goal schema contract + source/interfaces -> contract surfaces -> S8 policy_propagation_incomplete debt, Part P/Q `adapter_hook_debt`/`unenforced`, and code_convention_contract visibility when consumers attempted hooks -> versions/causal map -> .schema/.contract updates

manage-external-advice
  python3 -m manage_external_advice registry -> canonical directive parsing + exact clause disposition coverage -> prepare -> applied/log projections -> canonical event last -> committed receipt or exact forward recovery; active packets remain not_goal_truth and never grant authority

derive-improvement-task
  context + agents + gates -> respect allowed dispositions, verifier debt, target-metric movement debt, policy propagation debt, gate compatibility skip, chronic blocker debt, long-run pending state, scenario/argv/blocker/stochastic repair, count-key hygiene, goal-axis completeness, residual cost, global invariant keys, Part P/Q feature/freshness/frozen-input/provenance/primary-reason constraints, and explicit adapter capability ladder when supplied -> three durable lens projections + canonical synthesis -> one authoritative next-task/task-pack/terminal decision -> retain candidate files and transition selected IDs to applied/superseded -> bind/verify unchanged owner-committed archive/log/task-pack projections, publish advice/index roles, then recoverable selection-publication exposes task.md last; or terminal-wait B receipt/C rebase + authority-settled baseline; no global domain ladder fallback

task-doctor
  explicit doctor instruction -> read rules/task/advice -> archive old task -> rewrite task/task_pack while preserving verifier/hook/axis/cost/global residuals -> reconcile schema/index/issue -> optional commit

optimize-task-slice
  blockers/candidates/loop signals -> classify next slice including verifier_completion, hook_supply, axis_supply, scenario_supply, command_provenance_repair, blocker_contract_repair, feature/freshness/frozen-input repair, cost_disproportionate_residual -> advisory packet for derive

profile-cycle-efficiency
  ledger/logs/validation/issues -> detect repeated low-value cycles/sprawl and supply residual value-per-cycle-cost denominator -> recommended action for derive/report

task-md-agent-governance
  task.md -> repo map -> worker implementation -> integration -> multi-agent audit -> task_miss report

inspect-repo-with-agents
  repo map -> 3-6 read-only perspectives -> verify severe claims -> findings/coverage/gaps

inspect-oom-risk
  repo/config/scale hints -> memory growth tracing -> severity findings -> mitigation

find-local-python-envs
  imports/manifests/env inventory -> rank environments -> exact run commands

install-deps-with-agent
  requirement -> find-local-python-envs -> cache check -> one install agent only if needed -> verification

plan-validation-scope
  python3 -m plan_validation_scope plan -> changed surfaces + gate_artifact_compatibility -> current_only/affected_chain/full_chain with incompatible gates skipped/not_evaluated -> validation manifest; changed-surface and finalize remain separate root commands

normalize-acceptance-and-demo
  python3 -m normalize_acceptance_and_demo identity -> task context -> acceptance/non-goals/demo/validation packet -> envelope/verifier/scenario/hook contract, target_metric_delta movement evidence, evidence freshness, input-generation condition, and residual cost fields -> governance/validation scope

build-validation-set-with-agents
  planning is a workflow mode, not a root command -> python3 -m build_validation_set_with_agents build -> leakage -> run-oracles -> finalize -> validate -> .validation assets/result packet; optional frozen-root lane is freeze -> verify-root

run-task-code-and-log
  requested command -> execute/profile scope -> full body-free command_argv or command_provenance_missing -> safe_failure_autopsy if needed -> content-bound .agent_log v3 and run evidence, including long_run_launch handoff when authorized

monitor-running-execution
  running run evidence -> heartbeat/status/artifact check -> step=run long_run_monitor event -> running/completed_pending_validation/stale/missing_details/not_running without success promotion

review-cycle-output-quality
  output artifacts -> one read-only qualitative reviewer -> quality/output-delta/no-overclaim/goal-axis packet, landed_feature_inventory and feature_presence_evidence body checks when supplied

audit-cycle-loopback
  run/review/output-delta/failure-autopsy/explicit quality policy -> python3 -m audit_cycle_loopback evaluate -> commands.py dispatch -> package facade/runtime-cache bridge -> cli.py -> evaluator ordered setup/failure/progress/decision/finalize stages -> 3-state gates, adapter-owned metrics, root-cause and registry/root-cause/seal rows -> CLI recurrence binding/downgrade -> recurrence-bound durable_mutation_candidate assembly -> derive constraints; orchestrator finalizes the candidate, api.py is the separate stable explicit import surface, and missing quality policy leaves domain metric gates not_evaluated

audit-session-governance
  Stop-hook descriptor -> python3 -m audit_session_governance capture -> audit inspect -> audit validate -> result_contract/_session_audit/collection.py -> packet.py consumer checks + lazy producer validate_packet replay/parity -> complete/bound/evaluated-integrity/consumable projection may satisfy caller-required audit without upgrading a verdict; direct/result-owned claims stay advisory, the independent comparator is only a future/external contract, and verified ModeSpec may run audit auto-rebuild-index only for .task/session_audit/index.json with a before/after-hash receipt

python3 -m orchestrate_task_cycle mode-profile
  tracked capture/consume/reaction profile + default activation for non-privileged profiles or user/caller/authority activation for required/repair behavior + reducing local override -> resolve/verify content-derived ModeSpec -> preserve normal|bootstrap phases and authority/verdict ceilings -> allow only exact audit-index rebuild or route change to owning governed skill

validate-task-completion
  evidence bundle -> completion gates -> required verifier/hook pass + target_metric_delta movement + observed goal axes + scenario coverage + command provenance + blocker actionability + stochastic feasibility + policy/gate warnings + evidence freshness + landed feature inheritance + adapter hook provenance + frozen input lineage + long-run pending check + count-key hygiene + residual cost ratio + structure global effect -> validation_verdict + progress_verdict -> validation report

manage-evidence-cache
  fingerprints -> reuse/fresh_required/stale/unsafe_to_reuse -> owning validator decides

manage-task-state-index
  artifacts -> shared agent_log integrity inspection -> valid or legacy_unverified discovery only -> python3 -m manage_task_state_index index scan/link/audit -> append-only IDs/links -> .task/index.jsonl + index.md

record-agent-work-log
  python3 -m record_agent_work_log write -> write.py -> integrity/append.py preflight -> v3 body/index content binding -> shared no-follow integrity inspection -> valid or legacy_unverified consumers; tamper/symlink/duplicate/orphan/missing state blocks semantic consumption/indexing while collectors may expose integrity/file metadata

record-visible-increment
  before/after evidence -> visible delta artifact -> not validation evidence

manage-implementation-issues
  task/validation/blockers -> GitHub or .issue tracking -> issue lifecycle links

repo-change-commit
  dirty worktree + validation context -> classify/stage/commit coherent changes -> commit hash or blocker

render-cycle-dashboard
  python3 -m orchestrate_task_cycle dashboard -> render_cycle_dashboard.py facade -> dashboard package -> verified cycle ledger/finalization -> Korean dashboard with canonical tokens and blockers

python3 -m audit_cycle_loopback evaluate / audit_cycle_loopback/
  __main__ -> commands static registry -> package __init__ compatibility/cache bridge -> cli -> evaluator; adapters facade delegates loading/selection/compatibility/quality, quality facade delegates policy/values/gates, evaluation stages run setup -> failure -> progress -> decision -> finalize, registry services prepare mutation, and api.py separately owns explicit public exports

python3 -m orchestrate_task_cycle progress-loop / orchestrate_task_cycle.progress/
  static command -> progress/cli.py -> analysis.py compatibility facade -> AnalysisContext + AnalysisPipeline -> EvidenceCollectionStage -> ProgressAggregationStage -> RootMetricStage -> GateEvaluationStage -> FindingBuilderStage -> ResultBuilderStage; registry history is loaded during evidence collection and a registry update is prepared in the result

python3 -m orchestrate_task_cycle gt-conflict
  detect_gt_constraint_conflict.py facade -> gt_constraint/cli.py -> analysis.py + common.py -> generic provider/credential checks + optional repo-owned gt_constraint_policy; absent policy disables generalization inference without changing generic checks

python3 -m run_task_code_and_log failure-autopsy
  logs/adapters -> execution_stage_ladder + post_failure_diagnostics + gate_selfcheck -> failure class, next_failure_stage, safe scalar diagnostics
```
