# 프롬프트 생성 가이드

> **⚠️ Agent 참조 알림**: 이 가이드를 참조하거나 사용할 때는 반드시 사용자에게 "프롬프트 생성 가이드(PROMPT_GUIDE.md)를 참조하여 작업을 진행합니다"라고 알려주세요.

이 가이드는 사용자의 요구사항을 Cursor Agent가 이해하기 쉽도록 구조화된 프롬프트로 변환하는 방법을 제공합니다.

## 요구사항 분석 프로세스

### 1. 요구사항 파악
사용자의 요구사항에서 다음을 추출:
- **목표**: 무엇을 만들거나 수정해야 하는가?
- **범위**: 어떤 파일/모듈에 영향을 미치는가?
- **제약사항**: 특별한 요구사항이나 제약이 있는가?
- **우선순위**: 어떤 작업부터 시작해야 하는가?

### 2. 작업 분해
큰 요구사항을 작은 작업 단위로 분해:
- 각 작업은 명확한 입력과 출력을 가져야 함
- 작업 간 의존성 파악
- 순차적 실행 순서 결정

### 3. 컨텍스트 수집
작업에 필요한 정보 수집:
- 관련 파일 위치
- 사용되는 패턴/아키텍처
- 참고할 기존 코드
- 프로젝트 규칙 및 컨벤션

## 프롬프트 구조화 템플릿

### 기본 구조
```
[목표] {요구사항의 핵심 목표}

[범위] 
- 파일: {관련 파일 경로}
- 모듈: {관련 모듈}
- 레이어: {Controller/Broker/Domain Service/Repository}

[작업 단계]
1. {첫 번째 작업}
2. {두 번째 작업}
3. {세 번째 작업}

[제약사항]
- {제약사항 1}
- {제약사항 2}

[참고]
- {참고할 파일/패턴}
```

## 요구사항 유형별 프롬프트 가이드

### 1. 새 기능 추가

**사용자 요구사항 예시:**
> "회원 등급 조회 API 만들어줘"

**구조화된 프롬프트:**
```
[목표] 회원 등급 조회 API 구현

[범위]
- Controller: api-rest/src/main/kotlin/com/sfn/cancun/controller/front/user/
- Broker: api-rest/src/main/kotlin/com/sfn/cancun/provider/front/user/
- Domain Service: user-domain/src/main/kotlin/com/sfn/cancun/user/domain/user/service/
- DTO: user-domain/src/main/kotlin/com/sfn/cancun/user/domain/user/dto/

[작업 단계]
1. UserGradeResponse DTO 생성
2. UserQuery에 findUserGrade(userId: Long) 메서드 추가
3. UserBroker에 findUserGrade(userId: Long) 메서드 추가
4. UserController에 GET /users/{id}/grade 엔드포인트 추가

[제약사항]
- 기존 아키텍처 패턴 준수 (Controller → Broker → Domain Service)
- 응답 타입만 반환 (자동 래핑)
- CancunCustomException 상속 예외 처리

[참고]
- UserController.kt의 기존 엔드포인트 패턴
- UserQuery.kt의 조회 메서드 패턴
```

### 2. 기존 기능 수정

**사용자 요구사항 예시:**
> "주문 조회 API에 필터링 기능 추가해줘"

**구조화된 프롬프트:**
```
[목표] 주문 조회 API에 필터링 기능 추가

[범위]
- Controller: api-rest/src/main/kotlin/com/sfn/cancun/controller/front/order/
- Domain Service: order-domain/src/main/kotlin/com/sfn/cancun/order/domain/order/service/
- Repository: order-domain/src/main/kotlin/com/sfn/cancun/order/domain/order/repository/

[작업 단계]
1. OrderQueryRequest에 필터 파라미터 추가 (status, dateRange 등)
2. OrderQuery의 findOrders 메서드에 필터 로직 추가
3. OrderRepository에 필터 조건을 포함한 쿼리 메서드 추가
4. Controller의 엔드포인트에 Query Parameter 추가

[제약사항]
- 기존 API 호환성 유지 (기본값으로 모든 주문 조회)
- QueryDSL 사용 (Jakarta 버전)
- 기존 테스트 코드 영향 최소화

[참고]
- OrderController.kt의 기존 엔드포인트
- OrderQuery.kt의 기존 조회 로직
```

### 3. 버그 수정

**사용자 요구사항 예시:**
> "회원 가입할 때 이메일 중복 체크가 안 돼"

**구조화된 프롬프트:**
```
[목표] 회원 가입 시 이메일 중복 체크 로직 수정

[범위]
- Domain Service: user-domain/src/main/kotlin/com/sfn/cancun/user/domain/user/service/UserCommand.kt
- Repository: user-domain/src/main/kotlin/com/sfn/cancun/user/domain/user/repository/

[작업 단계]
1. UserRepository에 findByEmail 메서드 확인/추가
2. UserCommand.signUp 메서드에서 이메일 중복 체크 로직 추가
3. 중복 시 적절한 예외 발생 (UserCustomException)

[제약사항]
- CancunCustomException 상속 예외 사용
- 기존 회원 가입 플로우 유지
- 에러 메시지는 한글로 명확하게

[참고]
- UserCommand.kt의 signUp 메서드
- 기존 예외 처리 패턴
```

### 4. 리팩토링

**사용자 요구사항 예시:**
> "이 메서드 너무 길어서 리팩토링해줘"

**구조화된 프롬프트:**
```
[목표] {파일명}.{메서드명} 리팩토링

[범위]
- 파일: {전체 경로}

[작업 단계]
1. 메서드의 주요 단계 파악
2. 각 단계를 private 메서드로 추출
3. 메서드명으로 의도 명확히 표현
4. 중복 코드 제거 (있는 경우)

[제약사항]
- 기능 변경 없이 구조만 개선
- 기존 테스트 통과 확인
- 아키텍처 규칙 준수

[참고]
- REFACTORING_GUIDE.md의 리팩토링 패턴
```

## 프롬프트 작성 체크리스트

### 요구사항 분석
- [ ] 목표가 명확한가?
- [ ] 범위가 구체적인가?
- [ ] 작업 단계가 순차적으로 정리되었는가?
- [ ] 제약사항이 모두 포함되었는가?

### 컨텍스트 제공
- [ ] 관련 파일 경로가 명시되었는가?
- [ ] 참고할 기존 코드가 지정되었는가?
- [ ] 프로젝트 규칙이 언급되었는가?

### 명확성
- [ ] 모호한 표현이 없는가?
- [ ] 기술 용어가 정확한가?
- [ ] 예상 결과가 명확한가?

## 요구사항 개선 가이드

### 모호한 요구사항 개선

**Before:**
> "API 만들어줘"

**After:**
```
[목표] 회원 프로필 수정 API 구현

[범위]
- Controller: api-rest/.../UserController.kt
- Domain Service: user-domain/.../UserCommand.kt

[작업 단계]
1. UserUpdateRequest DTO 생성
2. UserCommand.updateProfile 메서드 추가
3. UserController에 PUT /users/{id}/profile 엔드포인트 추가

[제약사항]
- 기존 아키텍처 패턴 준수
```

### 불완전한 요구사항 보완

**Before:**
> "에러 처리 추가"

**After:**
```
[목표] {특정 기능}에 에러 처리 추가

[범위]
- 파일: {구체적 파일 경로}
- 메서드: {구체적 메서드명}

[작업 단계]
1. 가능한 에러 케이스 파악
2. 각 에러에 대한 예외 클래스 확인/생성
3. 예외 처리 로직 추가
4. 에러 응답 형식 확인

[제약사항]
- CancunCustomException 상속 필수
- 에러 코드는 BaseError 사용
```

## 자동 프롬프트 생성 예시

사용자가 다음과 같이 요청하면:

> "주문 취소 기능 만들어줘"

다음과 같이 구조화:

```
[목표] 주문 취소 기능 구현

[범위]
- Controller: api-rest/.../OrderController.kt
- Broker: api-rest/.../OrderBroker.kt  
- Domain Service: order-domain/.../OrderCommand.kt
- Repository: order-domain/.../OrderRepository.kt

[작업 단계]
1. OrderCancelRequest DTO 생성
2. OrderCommand.cancelOrder 메서드 구현
   - 주문 상태 검증 (취소 가능한 상태인지)
   - 주문 상태 변경
   - 결제 취소 처리 (필요시)
3. OrderBroker.cancelOrder 메서드 추가
4. OrderController에 DELETE /orders/{id} 엔드포인트 추가

[제약사항]
- 기존 아키텍처 패턴 준수
- 주문 상태는 enum으로 관리
- 취소 불가능한 주문은 예외 발생
- CancunCustomException 상속 예외 사용

[참고]
- OrderController.kt의 기존 엔드포인트 패턴
- OrderCommand.kt의 기존 변경 메서드 패턴
- OrderStatus enum 정의
```

## 사용 팁

1. **구체적으로**: "API 만들어줘"보다 "회원 조회 API 만들어줘"가 좋음
2. **범위 명시**: 어떤 파일/모듈을 수정할지 명시
3. **단계별**: 큰 작업은 작은 단계로 나눠서 요청
4. **참고 제공**: 비슷한 기존 코드가 있으면 언급
5. **제약사항**: 특별한 요구사항이 있으면 명시

이 가이드를 따라 요구사항을 구조화하면 Agent가 더 정확하게 작업을 수행할 수 있습니다.

