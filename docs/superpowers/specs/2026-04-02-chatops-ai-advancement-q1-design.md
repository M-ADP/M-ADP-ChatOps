# ChatOps AI 고도화 Q1 전략

## 목적

이 문서는 ChatOps의 다음 1분기 AI 고도화 방향을 기술 관점에서 확정하기 위한 내부 엔지니어링 전략 문서다.

이번 분기의 핵심 성공 기준은 다음 하나로 고정한다.

- `planner/verifier` 아키텍처를 도입한다.

단, 이번 분기의 목표는 단순한 planner 추가가 아니다. ChatOps를 `질문에 답하는 LLM UI`에서 `목표를 해석하고, 도메인별 specialist를 호출하고, 결과를 검증한 뒤 다음 행동을 결정하는 실행 시스템`으로 바꾸는 것이다.

## 이번 분기의 결정 사항

Q1에서는 다음 방향을 공식 채택한다.

- 공개 제품 경험은 계속 `chat-first`로 유지한다.
- 내부 AI runtime은 `orchestrator-controlled specialist multi-agent system`으로 전환한다.
- specialist는 Q1 동안 최대 3개 도메인으로 제한한다.
- 모든 specialist 실행 결과는 verifier를 통과해야 완료로 간주한다.
- 승인, 위험도, destructive action 제어는 별도 policy layer가 강제한다.

이번 분기에는 다음 방향을 채택하지 않는다.

- 완전 자유형 multi-agent conversation
- agent 간 직접 통신
- 장기 메모리 학습 시스템
- 범용 assistant 기능 확장
- 프론트엔드 전면 개편

## 현재 상태 요약

현재 ChatOps는 다음 기반을 이미 갖고 있다.

- `session + messages` 중심 공개 API
- 내부 `request` 기반 실행 단위와 상태 전이
- approval/reject/timeout 흐름
- task snapshot 기반의 구조화 응답
- domain downstream client와 dispatcher

즉, 채팅 UX와 실행 추적의 기본 토대는 이미 있다. 부족한 점은 `AI가 무엇을 왜 실행하는지`, `실행 결과가 정말 목표를 충족했는지`, `다음 행동을 어떻게 결정하는지`를 구조적으로 다루는 runtime 계층이다.

현재 구조의 한계는 다음과 같다.

- 라우팅과 실행이 사실상 단일 추론 흐름에 가깝다.
- 실행 전 계획과 실행 후 검증이 약하다.
- 도메인별 판단 로직이 명시적 specialist로 분리되어 있지 않다.
- 실패 시 recovery 전략이 명시적 loop가 아니라 예외 처리 수준에 머무른다.

## Q1 전략 방향

Q1의 목표 구조는 `단일 오케스트레이터 + 도메인 specialist + verifier`다.

핵심 원칙은 다음과 같다.

- 제어권은 항상 orchestrator가 가진다.
- planner는 목표와 실행 후보를 구조화하지만 직접 실행하지 않는다.
- specialist는 자기 도메인 지식과 tool schema에만 집중한다.
- verifier는 실행 결과를 평가해 다음 상태를 결정한다.
- policy layer는 AI 판단과 별도로 승인 및 안전 규칙을 강제한다.

이 구조를 택하는 이유는 다음과 같다.

- 현재 코드베이스의 graph, request lifecycle, task snapshot 구조 위에 가장 자연스럽게 얹을 수 있다.
- Q1 범위 안에서 multi-agent 특성을 확보하면서도 디버깅 가능성을 유지할 수 있다.
- specialist 수를 제한하면 평가와 운영 안정성을 함께 잡을 수 있다.

## 목표 아키텍처

### 1. Orchestrator

orchestrator는 세션 문맥, 현재 working task, 실행 상태를 관리하는 유일한 제어 지점이다.

주요 책임은 다음과 같다.

- 사용자 입력을 planner에 전달
- planner 결과를 실행 가능한 task graph로 정리
- 어떤 specialist를 호출할지 선택
- verifier 결과에 따라 `clarify`, `approve`, `execute`, `retry`, `stop`, `escalate` 중 하나로 상태 전이
- task snapshot과 session message를 최신 상태로 동기화

이번 분기에는 specialist끼리 직접 호출하지 않는다. 모든 specialist 결과는 orchestrator를 통해서만 다음 단계로 연결된다.

### 2. Planner Agent

planner는 사용자 발화를 다음 구조로 바꾸는 역할을 한다.

- `goal`
- `entities`
- `constraints`
- `candidate_steps`
- `risk_level`
- `required_clarifications`

planner는 실행 API를 직접 선택하지 않는다. 대신 어떤 specialist가 필요한지와 어떤 정보가 부족한지를 제시한다.

Q1 planner의 산출물은 문장이 아니라 구조화된 plan object여야 한다.

### 3. Domain Specialists

Q1 specialist는 세 개 이하로 제한한다.

- `Project Specialist`
- `Application Specialist`
- `Monitoring Specialist`

각 specialist의 책임은 다음과 같다.

- 자기 도메인 operation 후보를 고른다.
- 도메인 entity resolution을 수행한다.
- 필요한 slot을 식별한다.
- downstream tool 호출 인자를 생성한다.
- 호출 결과를 domain-normalized result로 정리한다.

specialist는 다른 도메인의 책임을 직접 다루지 않는다. 예를 들어 Monitoring Specialist는 앱 상태 변경 명령을 직접 결정하지 않는다.

### 4. Verifier Agent

verifier는 Q1 고도화의 핵심이다.

verifier는 실행 후 결과를 받아 다음 중 하나를 결정한다.

- `success`
- `retry`
- `clarify`
- `escalate`
- `stop`

검증 기준은 다음과 같다.

- 목표와 실제 결과가 일치하는가
- 실패가 일시적 오류인지 구조적 오류인지
- 사용자의 추가 입력이 필요한가
- 후속 action을 제안해야 하는가
- partial success를 그대로 완료 처리해도 되는가

verifier가 없으면 ChatOps는 여전히 tool-calling assistant에 머문다. verifier가 있어야 비로소 self-checking agent runtime이 된다.

### 5. Policy Layer

policy layer는 AI 판단과 분리된 결정 계층이다.

강제 규칙 예시는 다음과 같다.

- destructive action은 무조건 approval 필요
- role별 허용 operation 제한
- retry 횟수 상한
- timeout/circuit breaker 정책
- superseded request 승인 금지

이 레이어는 planner나 specialist의 판단을 신뢰하지 않고 독립적으로 적용되어야 한다.

## 런타임 루프

Q1 runtime loop는 다음 순서로 동작한다.

1. 사용자가 세션에 메시지를 보낸다.
2. orchestrator가 session context와 entity memory를 읽는다.
3. planner가 구조화된 plan object를 만든다.
4. policy layer가 위험도와 승인 필요 여부를 1차 판정한다.
5. orchestrator가 적절한 specialist를 선택한다.
6. specialist가 tool call 또는 clarification candidate를 생성한다.
7. tool 실행 결과를 verifier가 평가한다.
8. verifier 판단에 따라 상태를 전이한다.
9. 결과를 session message와 task snapshot으로 반영한다.

상태 전이는 다음 집합으로 단순화한다.

- `draft`
- `clarify`
- `awaiting_approval`
- `executing`
- `verifying`
- `completed`
- `failed`
- `escalated`

내부 request status는 계속 세부적으로 유지할 수 있지만, AI runtime의 상위 제어 상태는 위 집합으로 정리하는 것이 Q1 범위에서 적절하다.

## 데이터 및 메모리 전략

Q1의 AI 메모리는 세 종류로 나눈다.

### Session Summary Memory

세션 전체 요약이다.

- 현재 사용자의 운영 목표
- 최근 완료 작업
- 최근 실패/보류 작업
- 최근 참조한 주요 엔티티

이 메모리는 planner의 입력 축약과 세션 재개 품질 향상에 쓴다.

### Entity Memory

도메인 엔티티와 별칭을 저장한다.

- 프로젝트 이름과 id 매핑
- 앱 이름과 id 매핑
- 사용자 nickname과 user id 매핑

이 메모리는 specialist의 entity resolution 품질을 높인다.

### Working Memory

현재 진행 중인 task의 임시 상태다.

- 현재 plan object
- 현재 specialist 선택 결과
- 현재 verifier 판단
- pending clarification/approval 정보

Q1에서는 장기 벡터 메모리보다 구조화된 working memory의 안정성이 우선이다.

## 모델 전략

Q1에는 모든 단계를 하나의 큰 모델로 처리하지 않는다.

권장 분리는 다음과 같다.

- `Planner Model`
  - 구조화된 plan object 생성
- `Specialist Reasoning Model`
  - domain-specific slot resolution과 tool argument shaping
- `Verifier Model`
  - 결과 판정과 다음 상태 결정
- `Summary Model`
  - session summary 갱신

같은 모델을 재사용할 수는 있지만, 논리 역할은 코드에서 분리해야 한다. 그래야 이후 routing, 비용 최적화, 실험 제어가 가능하다.

## API 및 기존 구조와의 연결

이번 전략은 기존 `session + messages` 공개 API와 충돌하지 않는다.

- 프론트는 계속 세션 메시지와 task card를 소비한다.
- 내부적으로는 request가 실행/audit 단위로 유지된다.
- planner/verifier/specialist 결과는 request의 구조화 메타데이터로 저장된다.
- 세션 상세는 이 구조를 `message view model`로 투영한다.

즉 외부 계약은 계속 chat-first로 유지하고, 내부 AI runtime만 고도화한다.

## Q1 구현 범위

Q1에는 다음 항목만 완료 대상으로 잡는다.

- orchestrator에 planner/verifier 단계 추가
- specialist 3개 이하 도입
- plan object 스키마 도입
- verifier decision 스키마 도입
- policy layer 1차 버전 도입
- session summary memory 1차 버전 도입
- golden scenario 기반 eval harness 구축

이번 분기에는 다음을 완료 대상으로 잡지 않는다.

- specialist의 동적 생성
- 자기 반성형 장기 loop
- cross-session personalization
- multi-modal reasoning
- agent 간 직접 negotiation

## 단계별 로드맵

### Phase 1. Planner/Verifier Skeleton

- plan object와 verifier decision schema 정의
- orchestrator에 planner 단계와 verifier 단계 삽입
- task snapshot과 연결

완료 기준:

- 한 개 command, 한 개 query 시나리오가 planner/verifier 경로를 통과한다.

### Phase 2. Specialist Extraction

- project/application/monitoring specialist 분리
- 기존 tool selection과 entity resolution을 specialist로 이관

완료 기준:

- 주요 도메인 시나리오가 specialist별 테스트로 분리된다.

### Phase 3. Policy and Recovery

- approval/risk/retry 정책을 별도 계층으로 분리
- verifier 기반 retry/escalate 흐름 도입

완료 기준:

- 실패 시나리오에서 `retry`, `clarify`, `escalate`가 명시적으로 구분된다.

### Phase 4. Evaluation and Readiness

- golden task set 구축
- task success rate, clarification rate, verifier precision 측정
- 운영 로그와 trace 정리

완료 기준:

- Q1 종료 시점에 정량 지표로 baseline 대비 개선 여부를 비교할 수 있다.

## 평가 지표

Q1의 필수 지표는 다음과 같다.

- `task_success_rate`
- `unnecessary_clarification_rate`
- `approval_precision`
- `verifier_correction_rate`
- `retry_success_rate`
- `time_to_completion`

이 문서의 관점에서 가장 중요한 지표는 다음 두 개다.

- verifier가 잘못된 완료 판정을 얼마나 줄였는가
- planner가 불필요한 추가 질문을 얼마나 줄였는가

## 주요 리스크

### 리스크 1. 멀티에이전트 구조가 너무 빨리 복잡해짐

specialist를 많이 늘리면 실험과 디버깅이 급격히 어려워진다.

대응:

- Q1 specialist를 3개 이하로 제한
- orchestrator 외 direct communication 금지

### 리스크 2. verifier가 또 다른 free-form LLM 응답으로 흐름

verifier가 구조화된 판정 대신 자연어 요약만 내면 시스템이 불안정해진다.

대응:

- verifier는 enum 기반 decision만 반환
- rationale은 선택 필드로 제한

### 리스크 3. policy와 planner 책임이 섞임

위험도와 승인 규칙을 planner가 직접 판단하면 운영 규칙 drift가 생긴다.

대응:

- policy layer를 별도 모듈로 분리
- planner는 risk suggestion만 제공

### 리스크 4. eval 없이 체감 품질로만 판단함

이 경우 아키텍처는 복잡해졌는데 성과는 증명되지 않을 수 있다.

대응:

- Q1 안에 golden set과 baseline 측정을 반드시 포함

## 최종 권고

Q1의 ChatOps AI 고도화 방향은 `orchestrator-controlled specialist multi-agent system`으로 확정한다.

이 방향의 핵심은 기능 추가가 아니라 runtime 재구성이다.

- planner가 목표를 구조화한다.
- specialist가 도메인 실행 판단을 맡는다.
- verifier가 결과를 검증한다.
- policy layer가 안전성과 승인 규칙을 강제한다.
- 외부 제품 경험은 계속 chat-first로 유지한다.

이번 분기의 승패는 agent 개수를 늘리는 데 있지 않다. `planner -> specialist -> verifier` 루프를 작게라도 안정적으로 도입하고, 이를 정량 지표로 증명하는 데 있다.
