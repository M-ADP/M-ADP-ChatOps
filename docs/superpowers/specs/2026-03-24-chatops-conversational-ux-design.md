# ChatOps 대화형 UX 설계

## 목적

현재 ChatOps는 내부적으로 `request` 상태를 잘 관리하지만, 사용자에게는 여전히 상태값 중심의 API처럼 보인다.  
목표는 이 구조를 유지하면서도, 사용자가 실제 LLM과 대화하는 것처럼 느끼도록 응답 계약과 대화 흐름을 바꾸는 것이다.

핵심 원칙은 다음과 같다.

- 사용자는 항상 자연어로만 요청한다.
- 내부 API 이름, 내부 operation id, 내부 ID는 절대 노출하지 않는다.
- 정보가 부족하면 한 번에 필요한 항목을 자연어로 묻는다.
- 값이 모두 모이면 실행 계획을 자연어로 설명하고 승인 여부를 묻는다.
- 승인 후에만 실제 실행한다.
- 내부적으로는 기존 `request` 상태 머신과 LangGraph 오케스트레이션을 유지한다.

## 현재 문제

현재 구현은 다음 한계가 있다.

- `input_required`, `pending_approval` 같은 내부 상태가 그대로 노출된다.
- `missing_inputs`는 기계적 보조 정보에 가깝고, 진짜 대화형 질문처럼 보이지 않는다.
- 사용자가 값을 이어서 답해도, 프론트와 서버 모두 이를 “대화 메시지”보다는 “상태가 바뀐 요청”으로 다루는 느낌이 강하다.
- 사용자가 보는 응답이 “assistant의 한 턴 답변”으로 정리되지 않는다.

즉 상태 관리는 충분하지만, 사용자 경험은 아직 API 중심이다.

## 설계 방향

추천 방향은 `상태 머신 유지 + assistant_message 중심 응답`이다.

- 기존 `request` 단위 API는 유지한다.
- 기존 `input_required`, `pending_approval`, `completed`, `failed` 상태도 유지한다.
- 하지만 사용자에게 보여줄 주 응답 필드는 항상 `assistant_message` 하나로 통일한다.
- 프론트는 내부 상태를 해석하지 않고, `assistant_message`를 그대로 채팅 말풍선처럼 렌더링한다.

이 방식의 장점은 명확하다.

- LangGraph, 승인, checkpoint, SSE 구조를 다시 짤 필요가 없다.
- API 계약은 크게 흔들지 않고도 UX를 바꿀 수 있다.
- 이후 웹 채팅 UI, Slack, CLI 같은 다른 채널에도 같은 응답 계약을 재사용할 수 있다.

## 사용자 대화 원칙

### 문의

- 추가 정보 없이 즉시 답변한다.
- 답변은 설명형 자연어다.
- 내부 capability 이름은 숨긴다.

예:

- 사용자: `프로젝트 생성 방법 알려줘`
- 응답: `프로젝트를 만들려면 프로젝트 이름, CPU, 메모리, 디스크 정보를 알려주시면 됩니다.`

### 조회

- 바로 처리 가능한 경우 즉시 답한다.
- 결과는 요약형 자연어로 반환한다.
- 필요하면 목록형 포맷을 사용한다.

예:

- 사용자: `demo 프로젝트 멤버 목록 보여줘`
- 응답: `demo 프로젝트 멤버 목록은 다음과 같습니다. 1. alice (OWNER) 2. bob (MEMBER)`

### 명령

- 필요한 정보가 부족하면 한 번에 모두 묻는다.
- 한 턴에 하나씩 묻지 않는다.
- 값이 모두 모이면 실행 계획을 자연어로 설명하고 승인 여부를 묻는다.

예:

- 사용자: `프로젝트 하나 만들어줘`
- 응답: `프로젝트를 만들려면 프로젝트 이름, CPU, 메모리, 디스크를 알려주세요.`

- 사용자: `이름은 demo고 cpu는 1, 메모리는 1, 디스크는 10이야`
- 응답: `프로젝트 이름 demo, CPU 1, 메모리 1GB, 디스크 10GB로 생성할게요. 실행할까요?`

## 응답 계약

현재 응답 스키마는 유지하되, 사용자 표시 기준 필드를 명확히 추가한다.

권장 필드:

- `assistant_message`
  - 사용자에게 그대로 보여줄 자연어 응답
- `status`
  - 내부 상태
- `requires_approval`
  - 승인 버튼 노출 여부
- `missing_inputs`
  - 프론트가 힌트나 입력 UI를 구성할 때만 참고

즉 프론트는 다음처럼 동작하면 된다.

- `assistant_message`는 항상 렌더링
- `status=input_required`이면 입력창 유지
- `status=pending_approval`이고 `requires_approval=true`이면 승인/거절 UI 표시
- 나머지는 일반 assistant 응답처럼 처리

## 상태 전이

내부 상태 전이는 기존 구조를 유지한다.

- `processing`
- `input_required`
- `pending_approval`
- `approved`
- `executing`
- `completed`
- `failed`
- `rejected`

바뀌는 것은 상태가 아니라, 각 상태에서 생성하는 `assistant_message` 규칙이다.

### `input_required`

- 사용자에게 부족한 정보를 한 번에 모두 묻는다.
- 내부 필드명 대신 사용자 표현을 쓴다.

예:

- `name`, `max_cpu`, `max_memory`, `max_disk`
- 표시:
  - `프로젝트 이름`
  - `CPU`
  - `메모리`
  - `디스크`

### `pending_approval`

- 사용자에게 실제 실행 계획을 자연어로 설명한다.
- 절대 내부 API 이름을 포함하지 않는다.

### `completed`

- 결과를 사용자 관점으로 요약한다.
- 성공 사실, 변경된 대상, 핵심 결과만 보여준다.

### `failed`

- 실패 원인을 자연어로 설명한다.
- 입력값 오류인지, 권한 문제인지, 다운스트림 실패인지 구분해서 말한다.

## 대화 문맥 처리

기존 세션 문맥 누적은 유지한다.

- 사용자가 이전 턴에 준 값을 다음 턴에서 계속 사용
- `그거`, `아까 만든 프로젝트`, `그 앱` 같은 표현은 최근 문맥으로 해석
- 사용자는 내부 ID를 몰라도 된다

이 설계에서는 `assistant_message`도 문맥 일부로 취급할 수 있지만, 우선순위는 여전히 사용자 발화와 구조화된 해석 결과다.

## SSE와의 관계

SSE도 유지한다.

- 내부 이벤트는 그대로 저장
- 프론트는 `response.completed`, `approval.required`, `execution.completed` 등을 받을 수 있다
- 다만 사용자에게 보이는 메시지는 이벤트 타입이 아니라 `assistant_message` 기준으로 렌더링한다

즉 SSE는 전송 수단이고, UX 계약은 `assistant_message`가 책임진다.

## 구현 범위

이번 변경 범위는 다음으로 제한한다.

- `RequestResponse`에 `assistant_message` 추가 또는 `final_response`를 그 역할로 명확히 재정의
- `input_required` 문구를 대화형 질문으로 통일
- `pending_approval` 문구를 승인 질문형 자연어로 통일
- `completed`, `failed` 응답도 사용자 친화 문구로 정리
- query/command/inquiry 공통으로 내부 API 이름 미노출 보장

이번 변경에서 제외한다.

- session 전체 message 모델로 전환
- request 중심 구조 제거
- 프론트 전용 채팅 SDK
- 멀티메시지 assistant streaming UX 재설계

## 성공 기준

다음이 되면 성공이다.

- 사용자가 상태값을 몰라도 자연어 대화만으로 요청을 이어갈 수 있다.
- 정보가 부족하면 한 번에 필요한 항목을 모두 물어본다.
- 값이 다 모이면 자연어 계획과 승인 질문을 보여준다.
- 사용자는 내부 API 이름, 내부 ID를 보지 않는다.
- 현재 request/LangGraph/checkpoint 구조를 깨지 않고 UX만 대화형으로 바뀐다.
