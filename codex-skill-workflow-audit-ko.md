# Codex 스킬 워크플로우 구성 감사 보고서

- 작성일: 2026-07-29
- 감사 대상: 현재 디렉터리의 Codex 스킬·실행 코드·계약·테스트·문서
- 실사용 검증: 대규모 소설 작업 저장소의 워크플로우 메타데이터와 읽기 전용 명령
- 원칙: Ponytail — 새 계층 추가보다 삭제, 통합, 기존 기능 재사용, 기본 경로 축소를 우선

> 개인정보·내용 보호: 실사용 저장소의 소설 본문, 프롬프트, 작업명, task ID, 산출물 원문,
> 프로젝트 고유 코드나 파일명은 이 문서에 기재하지 않았다. 아래의 실사용 근거는 파일 수,
> 크기, 명령 출력량, 실행 시간, 계약 존재 여부 같은 집계 정보만 사용한다.

## 1. 결론

현재 구성은 권한, 증거 결속, 완료 판정, 재개 가능성 같은 안전 속성이 강하다. 전체 테스트
2,460개도 현재 상태에서 모두 통과했다. 문제는 안전 장치 자체보다, 장치를 연결하는 제어면이
실제 작업보다 빠르게 커졌다는 점이다.

가장 먼저 고쳐야 할 것은 다음 두 가지다.

1. **task-index의 durable audit가 성숙한 실사용 저장소에서 고정 파일 수 한도를 초과해
   완료 증거를 만들 수 없다.** 읽기 전용 감사는 되지만 `--write-report`용 입력
   매니페스트 생성은 4,096개 한도에서 중단됐다. 이는 미관이나 코드 스타일 문제가 아니라
   현재 일반화 한계를 실제 사용이 넘어선 경우다.
2. **보존·회전 정책이 문서 계약에만 있고 실행 경로가 없다.** 실사용 수명주기 트리는
   일반 파일 33,395개, 약 1.50GB까지 누적됐다. 단순 삭제가 아니라, 이미 있는 종료·ledger
   경로에 안전한 보존 실행을 연결해야 한다.

그 다음 병목은 31단계 기본 cycle, 일상적인 후속 작업에도 요구되는 고정 agent fan-out,
여러 스킬에 복제된 판정 필드와 receipt, 500줄 상한이 유도한 기계적 모듈 분할, 문서와 CLI
registry의 drift다.

권장 방향은 전면 재작성이나 새로운 workflow engine이 아니다.

- 기존 result-contract를 단일 receipt 소유자로 삼는다.
- model/operator 표면은 8~12단계로 줄이고, 내부 안전 단계는 compiler가 처리한다.
- 전체 historical audit는 종료·삭제·교체 경계에 남기고, 평상시에는 current-surface 검사를 쓴다.
- 보존, cache, provenance를 이미 있는 lifecycle에 연결한다.
- legacy reader와 mutation 권한 경계는 이관 증거 없이 삭제하지 않는다.

## 2. 핵심 수치

### 2.1 현재 스킬 저장소

| 항목 | 확인값 | 의미 |
|---|---:|---|
| `SKILL.md` | 36개 | 기능 경계가 이미 넓다. |
| authority manifest | 36개 | 모든 스킬에 권한 표면이 있다. |
| manifest operation | 112개 | 그중 56개는 authorization이 `none`이다. |
| canonical cycle phase | 31개 | 작은 변경에도 긴 직렬 제어면을 제공한다. |
| production Python | 1,011모듈 / 211,668 LOC | 제어 코드 자체가 대형 제품 규모다. |
| orchestrator Python | 558모듈 / 122,799 LOC | production Python의 약 58%가 한 스킬에 집중됐다. |
| 400줄 이상 production 모듈 | 152개 / 69,299 LOC | 500줄 상한 바로 아래의 파일이 많이 형성됐다. |
| 450줄 이상 production 모듈 | 86개 / 41,108 LOC | 응집도보다 상한 회피가 구조를 좌우할 가능성이 높다. |
| test 파일 | 117개 / 85,952 LOC | 테스트 표면도 production의 약 41% 규모다. |
| 전체 테스트 | 2,460개, 전부 통과 | 현재 동작은 안정적이며 축소 시 회귀 기준이 충분하다. |
| 전체 테스트 시간 | 384.78초 | 로컬 단일 실행도 약 6분 25초다. |
| README | 2,060줄 | 흐름도와 명령 표를 사람이 중복 유지한다. |

현재 Git 이력이 시작된 2026-06-28의 root commit과 HEAD를 비교하면 순증가량은 약
301,697줄이다. 빠른 개발 자체가 결함이라는 뜻은 아니다. 다만 한 달 동안 이 정도의
제어면이 추가됐으므로, 이제는 기능 추가보다 계약 통합과 삭제 예산이 필요하다는 신호다.

### 2.2 실사용 저장소에서 확인한 구조적 압력

| 항목 | 집계 결과 | 현재 workflow에 주는 신호 |
|---|---:|---|
| 수명주기 트리 | 33,395파일 / 약 1.50GB | 보존 정책이 실행되지 않으면 제어 산출물이 계속 누적된다. |
| cycle 하위 | 22,546파일 / 446 cycle / 약 631MB | 장기 사용 시 cycle당 산출물 비용이 누적된다. |
| packet | 16,797개 / 약 437.5MB | 반복 hand-off가 저장 공간의 큰 부분을 차지한다. |
| task-index raw row | 21,836개 | 고정 4,096파일 snapshot 가정이 맞지 않는다. |
| 정규화된 legacy row | 13,541개 | legacy reader는 즉시 삭제하면 안 된다. |
| 전역 audit 출력 | 106,579줄 / 3,235,789바이트 | 그대로 model context에 넣기 어렵다. |
| summary audit 출력 | 272줄 / 6,668바이트 | 동일 감사도 요약 표면이면 약 99.8% 작아진다. |
| compact context 출력 | 92,755바이트 / 최대 RSS 약 196MB | 기본 context도 이미 가볍지 않다. |

compact context의 essential projected payload는 65,445바이트로 해당 projection의
64KiB 예산보다 91바이트만 작았다. 이것만으로 semantic context 전체가 실패한다는 뜻은
아니지만, 실사용 규모에서 기본 context가 확장 여유를 거의 남기지 않는다는 신호다.

## 3. 감사 방법과 범위

다음 네 종류의 근거를 교차 확인했다.

1. **구성 전수 조사**
   - README, 36개 스킬, 36개 authority manifest, CLI registry, CI 설정을 확인했다.
   - production/test Python 파일 수와 LOC, 대형 모듈 분포, 중복 계약을 집계했다.
2. **핵심 경로 심층 추적**
   - orchestrate, loopback, completion validation, derive, task-index, ledger,
     result-contract, authority, adapter 경계를 따라갔다.
3. **실행 검증**
   - 현재 저장소의 전체 pytest를 실행해 2,460개 통과를 확인했다.
   - 공개 CLI의 두 invocation 경로를 비교했다.
4. **실사용 저장소 읽기 전용 검증**
   - 파일·크기·index 메타데이터를 집계했다.
   - context, task-index scan/audit를 변경 없이 실행했다.
   - dry-run이 발견한 변경은 적용하지 않았다.

실사용 저장소에는 파일 추가·수정·삭제를 하지 않았다. corpus와 산출물 본문도 보고서
근거로 사용하지 않았다.

## 4. 현재 workflow의 실제 구조

`orchestrate-task-cycle/SKILL.md:214-224`의 정상 cycle은 다음 31개 canonical phase를
직렬로 정의한다.

```text
context → authority → adapter scan → acceptance → route/validation planning
→ governance → result contract → adapter validation → ledger
→ code audit → run → qualitative review → loopback
→ validation-set build → visible increment → gap/efficiency analysis
→ validation finalization → index pre-validation → validate → issue
→ schema pre-derive → derive → schema post-derive → index
→ commit → dashboard → report → closeout commit
```

각 major subskill 호출은 대체로 다음 제어 절차를 반복한다.

```text
packet 작성 → stage transition → owner 실행 → result-contract 검증 → ledger append
```

이 구조는 장기 실행, 외부 effect, terminal 판정, successor publication에는 적절하다.
그러나 작은 R0/R1 변경에도 같은 operator/model 표면을 제공하면 실제 구현보다 packet,
receipt, index, schema 동기화가 임계 경로를 지배한다.

## 5. 우선순위별 상세 발견사항

### F-01. Compiler-first task-index prevalidation이 실제 규모의 unrelated history에 막힌다

- **우선순위:** P0
- **심각도 / 확신:** 높음 / 높음
- **Ponytail 태그:** `[shrink] [root-cause]`

`manage-task-state-index/scripts/manage_task_state_index/state/audit_snapshot.py:19-22`는
audit input을 다음처럼 고정 제한한다.

- 최대 입력 파일: 4,096
- 최대 총 바이트: 64MiB
- 최대 discovery 후보: 8,192

`audit_snapshot.py:343-358,395-405`는 이 한도를 넘으면 prevalidation input manifest
생성을 실패시킨다. 실사용 저장소에서는 `audit_input_manifest(...)`가 실제로
`Task-index audit input file-count budget exceeded`로 종료됐다.

반면 `validate-task-completion/SKILL.md:68-73`는 task-index가 존재할 때 전체 감사를
요구하고, 종료 시에는 `audit --write-report`를 completion evidence에 포함하도록 한다.
전체 감사 계산과 `audit --write-report`는 이 snapshot cap을 사용하지 않는다. 실패한
경계는 compiler-first prevalidation이 current decision surface와 무관한 historical
artifact까지 한 input manifest에 담으려 한 경로다.

또한 같은 전역 감사의 기본 출력은 106,579줄, 약 3.24MB였다. `--summary-only` 표면은
272줄, 약 6.7KB로 충분히 작았다. 계산보다 출력 계약이 model 소비에 더 큰 병목이다.

**근본 개선안**

1. compiler-first prevalidation manifest는 current task와 직접 연결된 exact artifact
   closure만 봉인한다.
2. unrelated historical artifact 수가 4,096개를 넘어도 current-surface prevalidation을
   막지 않게 한다.
3. 전체 historical audit 계산과 `audit --write-report`는 기존 경로에서 유지한다.
4. CLI/model 기본 출력은 summary로 바꾸고, 전체 issue 목록은 paginated artifact로
   저장한다.
5. destructive immutable consumer가 full-history input snapshot을 실제로 요구할 때만
   기존 hash 규칙을 재사용한 shard manifest를 추가한다.

**유지해야 할 안전선**

- 전체 감사 자체를 삭제하지 않는다.
- current-surface prevalidation의 입력 hash와 full audit report 재현 가능성을 각각 유지한다.
- current-surface 검사는 close/delete 권한을 대신하지 않는다.

### F-02. 보존·회전 정책은 문서 계약이고 실행 기능이 아니다

- **우선순위:** P0
- **심각도 / 확신:** 높음 / 높음
- **Ponytail 태그:** `[yagni] [shrink]`

`maintain-cycle-ledger/SKILL.md:20,52,71`은 `record_retention_policy`, rotation과
retention metadata를 요구한다. 그러나 production code 전수 검색에서는 retention class를
기록하는 메타데이터는 확인됐지만, 정책을 실제로 평가하고 packet/log/report를 회전하거나
archive하는 executor는 확인되지 않았다.

실사용 수명주기 트리는 33,395파일, 약 1.50GB이며 packet만 16,797개, 약 437.5MB다.
이는 “저장소가 크다”는 일반론이 아니라, 문서에 존재하는 수명주기 정책이 실제 lifecycle에
연결되지 않았음을 보여준다.

**근본 개선안**

1. 새 retention subsystem을 만들지 말고, 기존 closeout/ledger 경로에 한 개의
   `retention plan`과 `apply`를 연결한다.
2. 첫 단계는 항상 dry-run이어야 하며 다음만 출력한다.
   - 보존 대상
   - content hash가 동일한 중복 packet
   - archive 후보
   - 삭제 후보와 필요한 authority
3. immutable decision receipt, authority settlement, final validation evidence는
   보존한다.
4. 재생성 가능한 intermediate packet과 중복 projection부터 content-addressed
   dedup 또는 archive한다.
5. 저장량, 파일 수, age의 기본 예산을 제공하되 repo adapter가 상향할 수 있게 한다.

자동 삭제를 기본값으로 두는 것은 불필요하고 위험하다. 먼저 inventory와 archive를
실행 가능하게 만들고, 삭제는 기존 destructive authority를 재사용하면 충분하다.

### F-03. 31단계 기본 cycle과 반복 전역 검사가 임계 경로를 늘린다

- **우선순위:** P1
- **심각도 / 확신:** 높음 / 높음
- **Ponytail 태그:** `[shrink]`

정상 cycle에는 `index_pre_validate`와 마지막 `index`가 모두 있다. completion validator는
index가 있으면 global audit를 요구하고, derive도 scan/audit를 수행한다. 결과적으로 같은
cycle에서 전역 index 처리가 2~3회 일어날 수 있다.

각 주요 단계의 packet, transition, result-contract, ledger는 독립적으로는 합리적이다.
문제는 이 내부 제어 단계가 모두 operator/model의 직렬 hand-off로 노출되는 점이다.

**개선안**

- operator가 보는 기본 경로를 다음 8~12개 stage로 묶는다.

```text
context → plan/governance → run → review → validate
→ finalize → derive/close → report
```

- 기존 31개 phase는 삭제하지 않고 compiler의 내부 substage로 유지한다.
- authority, destructive effect, terminal wait, successor publication, long-running process만
  명시적 slow path로 승격한다.
- 같은 cycle의 index snapshot은 한 번 만들고 pre-validation, completion, derive가
  동일 snapshot hash를 재사용한다.

이 방식은 검증을 줄이는 것이 아니라 hand-off와 재계산을 줄인다.

### F-04. 일상적인 후속 task 선택에도 고정 agent quorum을 요구한다

- **우선순위:** P1
- **심각도 / 확신:** 높음 / 높음
- **Ponytail 태그:** `[yagni] [shrink]`

`derive-improvement-task/SKILL.md:14,63-72,176-185`는 agent-heavy 동작과 정확히
3개 lens, 별도 issue 분석, synthesis를 요구한다. `inspect-repo-with-agents`도 최소
3개 agent를 요구한다. 이 조합은 보통의 successor 선택에도 대략 8개의 agent action을
임계 경로에 놓을 수 있다. capacity가 모자라면 publication 자체가 멈춘다.

상충 evidence, terminal disposition, R3/irreversible effect에는 다중 관점이 가치가 있다.
그러나 deterministic 후보가 하나이고 acceptance가 명확한 일상 경로까지 같은 quorum을
요구하는 것은 일반화가 아니라 고정 비용이다.

**개선안**

1. 기본값: deterministic candidate screening + 단일 synthesis.
2. 다음 조건에서만 3-lens fan-out:
   - 후보 점수가 근접하거나 근거가 상충함
   - goal/theory/authority가 충돌함
   - terminal 또는 destructive disposition
   - 새로운 외부 effect나 R3 변경
3. escalation 이유를 receipt에 남긴다.

예상되는 routine delegation은 약 8개 action에서 1~3개로 줄어든다. 고위험 최종 owner는
그대로 유지해야 한다.

### F-05. progress·close·next-task predicate와 receipt 소유권이 중복된다

- **우선순위:** P1
- **심각도 / 확신:** 높음 / 높음
- **Ponytail 태그:** `[reuse] [shrink]`

loopback은 semantic progress와 terminal 후보를 만들고, completion validator는 acceptance,
freshness, scenario, progress를 다시 판정한다. derive는 같은 결과를 selection 제약으로
다시 해석하며, result-contract가 hand-off 형식과 origin을 또 검증한다.

“후보는 최종 진실이 아니다”라는 원칙은 맞다. 문제는 같은 predicate와 field bundle이
네 owner에 복제되어 규칙 하나를 추가할 때 producer, consumer, ledger, derive를 함께
수정해야 한다는 점이다.

구현에서도 `consumer_receipt_contract.py`가 loopback 351줄과 orchestrator 354줄로
사실상 포크돼 있다. 다만 `tests/test_consumer_receipt_conformance.py`는 양 경로의
binding, hash, validator signature와 주요 변조 거부 결과가 동일함을 교차 검증한다.
따라서 현재 위험은 무검증 drift가 아니라 같은 계약을 두 독립 실행 경계에서 계속
동기화해야 하는 유지 비용이다.

**개선안**

- 새로운 추상 계층을 추가하지 않는다.
- 기존 orchestrator result-contract의 receipt schema를 canonical 판정 소유자로 정한다.
- loopback은 진단·랭킹, validator는 close 판정, derive는 successor 선택만 소유한다.
- 독립 `scripts/` root 실행 계약이 유지되는 동안 두 물리 구현은 보존하고 기존
  differential test를 compatibility gate로 유지한다.
- 공통 dependency root가 canonical public invocation으로 정착한 뒤에만 다른 스킬을
  얇은 wrapper로 줄인다.

독립 실행 경계를 해소한 뒤의 예상 절감은 250~400 LOC이며, 더 중요한 이득은 판정
drift 제거다.

### F-06. “generic adapter”가 대형 공유 dict ABI로 변했다

- **우선순위:** P1
- **심각도 / 확신:** 높음 / 높음
- **Ponytail 태그:** `[shrink]`

K~Q/S 계열 field bundle이 loopback, validator, derive, validation scope, schema contract에
반복된다. 새로운 edge case가 생기면 “Part X” 필드와 guardrail을 여러 스킬에 동시에
추가하는 패턴이다. 이 구조에서는 adapter가 domain boundary라기보다 전역 field-name
schema가 된다.

실사용 저장소의 adapter는 이미 33개 Python 파일, 3,878 LOC, 35개 manifest component,
29개 hook contract를 갖고 있었다. 그럼에도 다음의 일반 운영 의미는 명시적 공통 계약으로
완전히 흡수되지 않았다.

- retention 실행 정책
- resource budget
- failure/recovery 상태
- external blocker의 재개 조건

이는 특정 프로젝트가 adapter를 덜 작성해서 생긴 문제가 아니라, adapter 확장만으로
generic workflow의 공통 운영 계약이 안정되지 않는다는 신호다.

**개선안**

- generic workflow가 이해하는 최소 필드를 다음으로 제한한다.
  - receipt status
  - scope와 evidence reference
  - decision owner
  - execution health
  - retention class
- domain-specific K~Q/S bundle은 adapter 내부 schema로 격리한다.
- 위 의미에 기본값을 제공하고, 실제로 다른 동작이 필요한 repo만 override한다.
- 현 consumer와 fixture를 자동 inventory한 뒤 이동한다. 필드를 한 번에 삭제하지 않는다.

### F-07. Evidence cache가 존재하지만 canonical 실행 경로에서 사용되지 않는다

- **우선순위:** P1
- **심각도 / 확신:** 중간~높음 / 높음
- **Ponytail 태그:** `[reuse]`

evidence-cache 관련 CLI, 문서, packet 필드는 존재한다. 그러나 31개 canonical phase에는
cache query/store가 없고, packet도 cache가 “있을 때”만 참조한다. 실사용 저장소에서도
기본 evidence-cache index가 생성되지 않았다.

따라서 현재 cache는 기능으로 존재하지만 정상 workflow가 재사용하지 않는 선택적 도구다.
장기 저장소에서는 같은 scan, validation input, context projection을 다시 계산하게 된다.

**개선안**

- 새 cache를 만들지 말고 기존 evidence-cache를 run/validate 경계에서 자동 조회·저장한다.
- key는 immutable input hash, schema version, runner version, relevant source revision으로
  한정한다.
- cache hit는 재계산을 생략할 수 있지만, completion을 자동 통과시키면 안 된다.
- freshness와 evidence binding이 불명확하면 miss로 처리한다.

### F-08. 역사 snapshot과 현재 상태의 연결이 명시적이지 않다

- **우선순위:** P2
- **심각도 / 확신:** 중간 / 중간
- **Ponytail 태그:** `[shrink]`

실사용 저장소에는 여러 시점의 생성 snapshot이 공존했다. 오래된 파일의 존재 자체는
결함이 아니며, 실제로 stale 상태가 소비된 증거도 없었다. 다만 일부 생성물 family에서
소비자가 역사 snapshot과 현재 상태를 구별할 `current selector`, `source revision`,
또는 currentness manifest를 정적으로 확인하기 어려웠다.

**개선안**

- 모든 snapshot에 새 상태 시스템을 만들 필요는 없다.
- 기존 manifest에 `source_revision`, `generated_at`, `supersedes`, `current_selector`
  중 필요한 최소 필드만 둔다.
- 소비자는 mtime이 아니라 immutable revision과 selector로 현재성을 판단한다.

### F-09. 500줄 모듈 상한이 응집도보다 기계적 분할을 유도한다

- **우선순위:** P1
- **심각도 / 확신:** 중간 / 높음
- **Ponytail 태그:** `[shrink]`

`tests/test_skill_module_architecture.py:13-14,77-100`은 production 모듈을 500줄 이하로
강제한다. 현재 400줄 이상이 152개, 450줄 이상이 86개다. orchestrator 하나에 558개
모듈이 있고, `result_contract` 145개, `task_pack` 47개, `stage` 38개처럼 한 개념이 많은
파일로 쪼개져 있다.

동시에 `orchestrate-task-cycle/references/code-structure-audit.md`는 파일 수와 깊이만으로
구조 품질을 판정하면 안 되며 mechanical sharding이 나쁘다고 설명한다. 정책과 구현
테스트가 서로 다른 행동을 유도한다.

**개선안**

- 500줄 hard fail을 제거하거나 advisory로 낮춘다.
- 대신 이미 있는 AST 검사를 이용해 다음을 hard gate로 삼는다.
  - 함수 길이와 복잡한 branch
  - public API 수
  - 순환 의존성
  - wildcard import와 production `sys.path` mutation
- 동일 변경 단위의 private shard는 합치되, 단순히 파일 수를 줄이기 위한 대규모 merge는
  하지 않는다.

예상 절감은 import/export/forwarding 중심 200~400 LOC다. 주된 이득은 탐색 비용 감소다.

### F-10. 공개 CLI와 문서가 이미 drift했다

- **우선순위:** P1
- **심각도 / 확신:** 중간 / 높음
- **Ponytail 태그:** `[delete] [shrink]`

README는 root command를 27개로 설명하지만 실제 static registry에는 33개가 있다.
문서에는 `python3 -m`과 `python3 -P -m` 예제가 혼재한다.

실제로 orchestrator의 `scripts` 디렉터리만 `PYTHONPATH`로 둔 문서식 직접 호출은
`ModuleNotFoundError`로 실패했지만, 상위 `workflow cycle ...` launcher는 성공했다.
즉, 개별 skill module 호출을 public surface로 문서화하면서 실제 의존성은 상위 launcher에
기대고 있다.

README는 2,060줄이며 Mermaid 흐름도 9개와 같은 의미의 text mirror 9개를 사람이 함께
관리한다. command drift가 이미 발생한 상태에서 이중 문서는 유지비만 늘린다.

**개선안**

1. 사람이 쓰는 public entrypoint는 `workflow` 하나로 고정한다.
2. stage, selection, closure command는 internal/recovery 문서로 분리한다.
3. command 표와 help 예제는 `COMMANDS` registry에서 생성한다.
4. Mermaid와 접근성용 text flow도 동일한 structured source에서 생성한다.

text mirror 약 1,175줄을 hand-maintained source에서 제거할 수 있다. 생성 결과를
배포 문서에 남기는 것은 무방하다.

### F-11. Authority manifest가 pure/read-only operation까지 절반을 차지한다

- **우선순위:** P2
- **심각도 / 확신:** 중간 / 높음
- **Ponytail 태그:** `[yagni] [shrink]`

36개 manifest의 112개 operation 중 정확히 56개가 authorization mechanism `none`이다.
read-only compile, snapshot, status까지 versioned authority operation lifecycle로
모델링하면 실제 mutation 권한보다 목록과 settlement 인지 비용이 커진다.

**개선안**

- effectful mutation과 lifecycle settlement는 현재 authority manifest에 남긴다.
- pure/read-only command는 CLI registry의 declarative `read_only` capability로 묶는다.
- `none` operation의 실제 consumer와 감사 요구를 먼저 집계하고, 사용되지 않는 개별
  operation부터 제거한다.

grant, reserve/consume, destructive effect 경계는 줄이면 안 된다. 목표는 보안을 없애는
것이 아니라 “권한이 필요 없는 것”을 권한 모델에서 빼는 것이다.

### F-12. 전체 테스트는 건강하지만 기본 feedback loop가 무겁다

- **우선순위:** P2
- **심각도 / 확신:** 중간 / 높음
- **Ponytail 태그:** `[shrink]`

전체 2,460개 테스트는 모두 통과했다. 이는 좋은 회귀 기준이다. 동시에 단일 로컬 실행이
384.78초 걸렸고, CI는 Python 3.10과 3.13에서 모든 push/PR마다 전체 pytest를 실행한다.
현재 설정에는 빠른 contract lane과 process/filesystem integration lane의 구분이 없다.

`pyproject.toml`과 CI에는 coverage/static-analysis gate도 없다. 이것이 곧 미테스트를
의미하지는 않는다. 다만 211K LOC의 production과 86K LOC의 tests 사이에서 어떤 위험이
어떤 테스트로 보호되는지 정량적으로 보이지 않는다.

**개선안**

- 새 test framework를 추가하지 않는다.
- 기존 pytest 파일/marker를 이용해 다음 두 lane으로 나눈다.
  1. PR fast lane: schema, receipt, pure compiler, AST architecture
  2. full lane: subprocess, filesystem, end-to-end, Python version matrix
- full lane은 merge/nightly 또는 영향 경로에 맞춰 실행한다.
- 중복 contract 통합 시 differential test 한 개를 먼저 둔다.
- coverage 도구 추가는 실제 blind spot이 확인될 때 결정한다.

### F-13. 국소 중복과 독립 skill 표면을 더 줄일 수 있다

- **우선순위:** P2
- **심각도 / 확신:** 중간 / 높음
- **Ponytail 태그:** `[delete] [reuse] [shrink]`

다음은 큰 재설계 없이 제거 가능한 항목이다.

1. **Selection receipt sealing 중복**
   - v2 core의 render/from-values/validate가 여러 경로에 반복된다.
   - 즉시 50~90 LOC를 단일 함수로 줄일 수 있다.
   - v1/v2 reader 삭제는 실사용의 13,541 legacy row 이관 후에만 가능하다.
2. **CLI forwarding wrapper**
   - 30개 이상의 함수가 import 후 `main(list(argv))`만 전달한다.
   - 직접 handler registry 또는 제한된 allow-list loader로 100~140 LOC를 줄일 수 있다.
3. **`task-doctor`의 경계 예외**
   - wildcard facade와 여러 production `sys.path` mutation이 공통 구조 검사 밖에 있다.
   - installable package 또는 한 개 bootstrap으로 50~100 LOC와 실행 환경 차이를 줄인다.
4. **`optimize-task-slice` 독립 호출면**
   - 유일한 직접 소비자가 derive이고 advisory 단계다.
   - derive 내부 ranking으로 흡수하면 최소 SKILL+manifest 115줄과 별도 hand-off를 없앨 수 있다.
5. **작은 SHA/path helper 복제**
   - 별도 공통 패키지를 만들 이유는 없다.
   - F-05의 canonical receipt core를 만들 때 자연스럽게 공유되는 것만 이동한다.

## 6. 병목의 원인 관계

개별 문제는 다음처럼 연결돼 있다.

```text
31단계 기본 경로
  ├─ packet/receipt/index 산출물 증가
  │    └─ 실행 retention 부재 → 파일·용량 누적
  ├─ 같은 predicate의 다중 owner
  │    └─ field ABI·adapter hook·compatibility code 증가
  ├─ 반복 global audit
  │    └─ 고정 4,096파일 snapshot 한도 초과
  └─ 고정 agent fan-out
       └─ 일상 task도 높은 latency/capacity 요구

500줄 hard cap
  └─ mechanical shard 증가
       └─ import/forwarder/registry/문서 표면 증가
```

따라서 “상수 한도만 올리기”, “cache를 하나 더 만들기”, “adapter hook을 더 추가하기”는
증상을 늦출 뿐이다. 단일 snapshot 가정, 중복 owner, 무조건적인 slow path를 먼저 줄여야
한다.

## 7. 권장 개선 순서

### 단계 A — 실제 scale blocker 해소

1. task-index prevalidation manifest를 exact current-surface closure로 제한한다.
2. model/console 기본 출력은 summary로 제한한다.
3. current-surface validation과 full historical audit를 분리한다.
4. close/delete/replacement에서는 full durable audit를 계속 요구한다.

**완료 기준**

- 현재 실사용 규모에서 `audit --write-report`가 성공한다.
- unrelated history가 4,096개를 넘어도 current-surface prevalidation이 성공한다.
- prevalidation manifest hash로 exact current closure를 재현할 수 있다.
- 기본 출력은 bounded하고, 상세 issue는 artifact로 접근 가능하다.

### 단계 B — 누적 비용 제어

1. closeout에 retention dry-run을 연결한다.
2. duplicate packet과 재생성 가능한 intermediate를 먼저 식별한다.
3. 일반 cycle archive/delete는 archive-aware reader와 정확한 destructive authority가
   생길 때까지 dry-run으로 제한하고, 기존 selection-CAS archive/apply만 보존한다.
4. 기존 evidence-cache를 run/validate에 연결한다.

**완료 기준**

- 새 cycle이 끝날 때 보존 예산과 초과량이 보인다.
- 같은 immutable 입력의 반복 scan이 cache hit로 줄어든다.
- receipt, authority, final evidence는 손실되지 않는다.
- generic archive/apply는 `not_implemented`로 남고 자동 삭제가 일어나지 않는다.

### 단계 C — source of truth 통합

1. result-contract receipt를 canonical contract로 지정한다.
2. loopback·validator·derive의 owner 책임을 분리한다.
3. selection sealing을 통합하고, consumer receipt 물리 포크는 독립 `scripts/` root
   경계가 해소된 뒤 얇은 wrapper로 전환한다.
4. CLI/README/flowchart를 registry에서 생성한다.

**완료 기준**

- 같은 predicate 변경이 한 owner와 한 schema만 수정한다.
- README command 수와 runtime registry가 자동으로 일치한다.
- 문서식 public invocation이 clean environment에서 성공한다.

### 단계 D — 정상 경로 축소

1. 31개 내부 phase를 8~12개 operator-visible stage로 묶는다.
2. index snapshot을 cycle 내에서 재사용한다.
3. routine derive는 1~3 agent action으로 시작한다.
4. conflict, terminal, R3, destructive effect에서만 full fan-out한다.

**완료 기준**

- 검증·권한 semantics는 기존과 동일하다.
- 작은 R0/R1 cycle의 packet 수, agent action, global scan 수가 감소한다.
- slow path 승격 이유가 receipt에 남는다.

### 단계 E — 구조 부채 회수

1. 500줄 hard gate를 semantic architecture gate로 바꾼다.
2. 같은 변경 단위의 private shard만 선택적으로 합친다.
3. `task-doctor`를 공통 package 규칙에 포함한다.
4. fast/full pytest lane을 분리한다.
5. migration evidence가 생긴 뒤에만 v1/v2 reader를 retire한다.

## 8. 삭제·축소 예상

중복 항목을 이중 계산하지 않은 보수적 추정이다.

| 구분 | 예상 축소 |
|---|---:|
| consumer receipt(독립 실행 경계 해소 후), selection sealing, CLI forwarding, path shim | production code 500~700 LOC |
| README text mirror 생성화 | hand-maintained docs 약 1,175줄 |
| `optimize-task-slice` 흡수 | SKILL+manifest 약 115줄과 호출면 1개 |
| legacy migration 완료 후 v1/v2 receipt retire | 추가 600~800 LOC |
| operator-visible phase | 31개 → 약 8~12개 |
| routine derive delegation | 약 8 action → 1~3 action |
| 외부 dependency | 안전하게 제거 가능한 항목 확인 안 됨 |

K~Q/S field ABI와 compatibility matrix는 consumer inventory가 끝나기 전 LOC 절감량을
제시하지 않는다. 구조상 30% 이상 축소 여지는 보이지만, 숫자를 목표로 먼저 삭제하면
evidence binding을 손상시킬 수 있다.

## 9. 유지해야 할 요소

다음은 비대해 보여도 증거 없이 줄이면 안 된다.

- mutation과 destructive action의 authority grant/reserve/consume
- successor publication의 atomic/CAS 경계
- terminal 판정의 독립 completion validator
- immutable decision receipt와 final validation evidence
- legacy artifact reader — migration 및 retention proof 전까지
- trust boundary의 입력 검증과 path confinement
- long-running process의 재개·settlement 정보

즉, 삭제 대상은 안전 semantics가 아니라 그 semantics를 여러 번 표현하는 wrapper,
중복 schema, 반복 scan, 사람 손으로 유지하는 mirror다.

## 10. 검증 계획

개선 작업은 다음의 최소 검증으로 충분하다.

1. 기존 2,460개 테스트를 baseline으로 보존한다.
2. task-index prevalidation에 다음 focused test를 추가한다.
   - unrelated history가 4,096개보다 많아도 exact current-surface closure 생성
   - manifest 순서와 hash의 결정성 및 full audit 계산 유지 확인
3. 기존 consumer conformance differential test를 유지하고 집중 실행한다.
4. retention은 dry-run golden summary와 protected receipt 제외 검사를 추가한다.
5. fast path와 slow path가 같은 final validation 결과를 만드는 equivalence scenario를
   한 개 둔다.
6. public `workflow` help와 generated README command 목록의 일치 검사를 추가한다.

새 framework나 service는 필요 없다. 기존 pytest, JSON canonicalization, hash helper,
authority 경계를 재사용하면 된다.

## 11. 제한사항

- 실제 cycle별 wall time, retry율, cache hit율, agent 대기시간 telemetry는 없었다.
  따라서 phase/agent 축소 효과는 구조 기반 추정이다.
- mutation, publication, retention의 end-to-end write 실행은 하지 않았다.
- 실사용 저장소의 오래된 생성물이 실제로 stale 상태로 소비된다는 증거는 없다.
  이 문서는 현재성 연결의 명시성 부족만 지적한다.
- corpus 내용과 프로젝트 고유 구현은 조사 결과에 포함하지 않았다.
- 전체 테스트 시간은 현재 호스트의 단일 측정값이며 CI 시간과 동일하다고 가정하지 않는다.

## 12. 최종 판정

현재 workflow의 주된 결함은 “검증이 너무 많다”가 아니다. **같은 안전 의미를 여러
skill, packet, receipt, index, 문서가 중복 소유하고, 전체 저장소를 매번 한 덩어리로
처리한다는 것**이다.

가장 작은 올바른 개선은 다음 한 문장으로 요약된다.

> 기존 안전 경계는 유지하고, receipt의 source of truth를 하나로 만들며, current-surface와
> historical closure를 분리하고, 보존·cache를 기존 lifecycle에 실제로 연결한다.

이 순서라면 전면 재작성 없이도 실제 scale blocker를 제거하고, 즉시 500~700 LOC의
production 중복과 약 1,175줄의 수동 문서 유지비를 줄일 수 있다.
