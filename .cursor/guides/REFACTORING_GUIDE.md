# 리팩토링 가이드

> **⚠️ Agent 참조 알림**: 이 가이드를 참조하거나 사용할 때는 반드시 사용자에게 "리팩토링 가이드(REFACTORING_GUIDE.md)를 참조하여 작업을 진행합니다"라고 알려주세요.

이 가이드는 Cursor Agent가 코드 리팩토링을 수행할 때 따라야 할 규칙과 원칙입니다.

## ⚠️ 중요: 리팩토링 원칙

**개발 완료 후 항상 리팩토링을 수행합니다.**
- ✅ 기능 개발이 완료되면 반드시 리팩토링 단계 진행
- ✅ 코드 가독성, 유지보수성 향상에 집중
- ✅ 기능 변경 없이 구조만 개선

## 리팩토링 원칙

### 1. 기능 변경 없이 구조만 개선
- ❌ 리팩토링 중에 새로운 기능 추가 금지
- ❌ 기존 동작 변경 금지
- ✅ 코드 가독성, 유지보수성 향상에 집중

### 2. 아키텍처 준수
- **레이어 분리**: Controller → Broker → Domain Service → Repository
- **도메인 간 통신**: Broker를 통해서만 허용
- **의존성 방향**: 외부 → 내부 (Controller → Domain)

### 3. 점진적 리팩토링
- 큰 변경을 한 번에 하지 말고 작은 단위로 나눠서 진행
- 각 단계마다 테스트 통과 확인
- 커밋 단위를 작게 유지

## 리팩토링 패턴

### 1. 메서드 추출 (Extract Method)

**Before:**
```kotlin
fun processOrder(orderId: Long) {
    val order = orderRepository.findById(orderId) ?: throw OrderNotFoundException()
    if (order.status == OrderStatus.PENDING) {
        order.status = OrderStatus.PROCESSING
        orderRepository.save(order)
        notificationService.sendNotification(order.userId, "주문이 처리 중입니다")
    }
}
```

**After:**
```kotlin
fun processOrder(orderId: Long) {
    val order = findOrderOrThrow(orderId)
    if (isPendingOrder(order)) {
        updateOrderStatus(order, OrderStatus.PROCESSING)
        notifyOrderProcessing(order)
    }
}

private fun findOrderOrThrow(orderId: Long): Order {
    return orderRepository.findById(orderId) ?: throw OrderNotFoundException()
}

private fun isPendingOrder(order: Order): Boolean {
    return order.status == OrderStatus.PENDING
}

private fun updateOrderStatus(order: Order, status: OrderStatus) {
    order.status = status
    orderRepository.save(order)
}

private fun notifyOrderProcessing(order: Order) {
    notificationService.sendNotification(order.userId, "주문이 처리 중입니다")
}
```

### 2. 클래스 분리 (Extract Class)

**원칙:**
- 단일 책임 원칙 준수
- 하나의 클래스가 너무 많은 책임을 가지면 분리
- 도메인별로 명확히 구분

**예시:**
- `UserService` → `UserQuery` (조회), `UserCommand` (변경)
- 복잡한 비즈니스 로직 → 별도 Manager/Handler 클래스로 분리

### 3. 중복 제거 (DRY - Don't Repeat Yourself)

**Before:**
```kotlin
fun createUser(request: SignUpRequest) {
    if (request.username.isBlank()) {
        throw IllegalArgumentException("사용자명은 필수입니다")
    }
    if (request.password.isBlank()) {
        throw IllegalArgumentException("비밀번호는 필수입니다")
    }
    // ...
}

fun updateUser(userId: Long, request: UpdateRequest) {
    if (request.username.isBlank()) {
        throw IllegalArgumentException("사용자명은 필수입니다")
    }
    // ...
}
```

**After:**
```kotlin
fun createUser(request: SignUpRequest) {
    validateSignUpRequest(request)
    // ...
}

fun updateUser(userId: Long, request: UpdateRequest) {
    validateUpdateRequest(request)
    // ...
}

private fun validateSignUpRequest(request: SignUpRequest) {
    require(request.username.isNotBlank()) { "사용자명은 필수입니다" }
    require(request.password.isNotBlank()) { "비밀번호는 필수입니다" }
}
```

### 4. 매직 넘버/문자열 제거

**Before:**
```kotlin
if (order.status == "PENDING") {
    order.status = "PROCESSING"
}
```

**After:**
```kotlin
if (order.status == OrderStatus.PENDING) {
    order.status = OrderStatus.PROCESSING
}
```

### 5. 조건문 단순화

**Before:**
```kotlin
fun isEligible(user: User): Boolean {
    if (user.age >= 18) {
        if (user.status == UserStatus.ACTIVE) {
            if (user.hasVerifiedEmail) {
                return true
            }
        }
    }
    return false
}
```

**After:**
```kotlin
fun isEligible(user: User): Boolean {
    return user.age >= 18 
        && user.status == UserStatus.ACTIVE 
        && user.hasVerifiedEmail
}
```

### 6. 네이밍 개선

**원칙:**
- 의도를 명확히 표현
- 축약어 지양
- 한글 주석보다는 명확한 네이밍

**Before:**
```kotlin
fun proc(u: User): Boolean {
    // 사용자 활성화 여부 확인
    return u.st == "ACTIVE"
}
```

**After:**
```kotlin
fun isActiveUser(user: User): Boolean {
    return user.status == UserStatus.ACTIVE
}
```

## 리팩토링 체크리스트

### 리팩토링 전
1. ✅ 현재 코드의 문제점 파악
2. ✅ 리팩토링 목표 명확히 정의
3. ✅ 기존 테스트가 모두 통과하는지 확인
4. ✅ 리팩토링 범위 결정

### 리팩토링 중
1. ✅ 작은 단위로 나눠서 진행
2. ✅ 각 단계마다 테스트 실행
3. ✅ 아키텍처 규칙 준수
4. ✅ 코딩 컨벤션 준수 (Ktlint)
5. ✅ 기능 변경 없이 구조만 개선

### 리팩토링 후
1. ✅ 모든 테스트 통과 확인
2. ✅ Ktlint 검증 통과
3. ✅ 코드 리뷰 가능한 상태로 커밋
4. ✅ 변경 사항 문서화 (필요시)

## 주의사항

### ❌ 하지 말아야 할 것
- 리팩토링과 기능 추가를 동시에 진행
- 테스트 없이 리팩토링
- 한 번에 너무 많은 변경
- 아키텍처 규칙 위반
- 기존 동작 변경

### ✅ 해야 할 것
- 테스트 먼저 작성 (TDD)
- 작은 단위로 점진적 진행
- 각 단계마다 검증
- 명확한 커밋 메시지
- 코드 리뷰 요청

## 리팩토링 예시 시나리오

### 시나리오 1: 긴 메서드 분리

**문제:** 100줄이 넘는 복잡한 메서드

**해결:**
1. 메서드의 주요 단계 파악
2. 각 단계를 private 메서드로 추출
3. 메서드명으로 의도 명확히 표현
4. 테스트로 동작 검증

### 시나리오 2: 중복 코드 제거

**문제:** 여러 곳에서 동일한 로직 반복

**해결:**
1. 공통 로직 식별
2. 공통 메서드/유틸리티로 추출
3. 모든 사용처에서 새 메서드 사용
4. 기존 코드 제거

### 시나리오 3: 복잡한 조건문 단순화

**문제:** 중첩된 if-else, 복잡한 조건

**해결:**
1. Early return 패턴 사용
2. Guard clause 적용
3. 조건을 명확한 메서드로 추출
4. Boolean 로직으로 단순화

## 리팩토링 우선순위

1. **높음**: 버그 발생 가능성 있는 코드, 중복 코드
2. **중간**: 가독성 저해, 테스트 어려운 코드
3. **낮음**: 단순한 스타일 개선

리팩토링은 항상 비즈니스 가치를 고려하여 우선순위를 정하세요.

