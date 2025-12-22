# 테스트 코드 생성 가이드

> **⚠️ Agent 참조 알림**: 이 가이드를 참조하거나 사용할 때는 반드시 사용자에게 "테스트 코드 생성 가이드(TEST_GUIDE.md)를 참조하여 작업을 진행합니다"라고 알려주세요.

이 가이드는 Cursor Agent가 테스트 코드를 생성할 때 따라야 할 규칙과 패턴입니다.

## ⚠️ 중요: 테스트 코드 작성 원칙

**테스트 코드는 필요할 때만 작성합니다.**
- ❌ 모든 기능에 대해 자동으로 테스트 코드를 작성하지 않음
- ✅ 사용자가 명시적으로 요청할 때만 작성
- ✅ 빌드 시 mock이 없거나 문제가 발생했을 때만 mock 추가

**Mock 추가 규칙:**
- 빌드 실패 시 필요한 mock만 최소한으로 추가
- 불필요한 mock은 추가하지 않음

## 테스트 유형별 가이드

### 1. Controller 테스트 (RestDocs)

**기본 구조:**
```kotlin
package com.sfn.cancun.controller.front.user

import com.sfn.cancun.restdocs.support.RestDocTest
import org.junit.jupiter.api.DisplayName
import org.junit.jupiter.api.Test
import org.mockito.kotlin.whenever
import org.springframework.restdocs.payload.PayloadDocumentation.*
import org.springframework.restdocs.request.RequestDocumentation

class UserControllerTest(
    private val userQuery: UserQuery,
    private val userBroker: UserBroker,
) : RestDocTest() {
    
    @Test
    @DisplayName("회원 조회")
    fun getUser() {
        // Given
        val userId = 1L
        val userResponse = UserResponse(...)
        whenever(userQuery.findById(userId)).thenReturn(userResponse)
        
        // When & Then
        get("/users/{id}", userId) {
            // RestDocs 문서화
        }.andExpect {
            status { isOk() }
        }.andDo(
            defaultDocument(
                RequestDocumentation.pathParameters(
                    RequestDocumentation.parameterWithName("id").description("회원 ID")
                ),
                responseFields(
                    fieldWithPath("id").description("회원 ID"),
                    fieldWithPath("name").description("이름")
                )
            )
        )
    }
}
```

**필수 사항:**
- `RestDocTest` 상속 필수
- `@DisplayName`으로 한글 테스트 설명 작성
- `defaultDocument()` 또는 `defaultSecurityDocument()` 사용하여 RestDocs 문서화
- Given-When-Then 패턴 사용
- `mockMvc` 대신 `get()`, `post()`, `put()`, `delete()`, `patch()` 헬퍼 메서드 사용
- Request/Response 필드 문서화 필수

**Mock 설정:**
- Controller의 의존성은 생성자 주입으로 받음
- `@MockBean`은 `restdoc.support` 패키지의 `@Profile("restdocs")` 설정 클래스에서 관리

### 2. Domain Service 테스트 (Query/Command)

**기본 구조:**
```kotlin
package com.sfn.cancun.user.domain.user.service

import org.junit.jupiter.api.DisplayName
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.extension.ExtendWith
import org.mockito.InjectMocks
import org.mockito.Mock
import org.mockito.junit.jupiter.MockitoExtension
import org.mockito.kotlin.whenever
import org.mockito.kotlin.verify

@ExtendWith(MockitoExtension::class)
internal class UserQueryTest {
    @InjectMocks
    lateinit var userQuery: UserQuery
    
    @Mock
    lateinit var userRepository: UserRepository
    
    @Mock
    lateinit var baseUserRepository: BaseUserRepository
    
    @Test
    @DisplayName("회원 ID로 회원을 조회할 수 있다")
    fun `회원 ID로 회원 상세 정보를 조회할 수 있다`() {
        // Given
        val userId = 1L
        val user = User.create(...)
        whenever(userRepository.findById(userId)).thenReturn(user)
        
        // When
        val result = userQuery.findById(userId)
        
        // Then
        result shouldBe user
        verify(userRepository).findById(userId)
    }
}
```

**필수 사항:**
- `@ExtendWith(MockitoExtension::class)` 사용
- `@InjectMocks`로 테스트 대상 주입
- `@Mock`으로 의존성 모킹
- Given-When-Then 패턴 사용
- `@DisplayName`으로 한글 테스트 설명 작성
- `verify()`로 메서드 호출 검증

### 3. Broker 테스트

**기본 구조:**
```kotlin
@ExtendWith(MockitoExtension::class)
internal class UserBrokerTest {
    @InjectMocks
    lateinit var userBroker: UserBroker
    
    @Mock
    lateinit var userQuery: UserQuery
    
    @Mock
    lateinit var orderQuery: OrderQuery
    
    @Test
    @DisplayName("회원과 주문 정보를 함께 조회할 수 있다")
    fun findUserWithOrders() {
        // Given
        val userId = 1L
        val user = UserResponse(...)
        val orders = listOf(OrderResponse(...))
        whenever(userQuery.findById(userId)).thenReturn(user)
        whenever(orderQuery.findByUserId(userId)).thenReturn(orders)
        
        // When
        val result = userBroker.findUserWithOrders(userId)
        
        // Then
        result.user shouldBe user
        result.orders shouldBe orders
    }
}
```

## 테스트 작성 규칙

### 네이밍
- 테스트 클래스: `{TargetClass}Test`
- 테스트 메서드: `@DisplayName`으로 한글 설명, 메서드명은 한글로 작성 가능 (백틱 사용)
- 예: `` `회원 ID로 회원을 조회할 수 있다`() ``

### 테스트 데이터
- 테스트 전용 DTO는 `TestDto` 객체 사용
- 예: `TestDto.userSignUpRequest`, `TestDto.withdrawalRequest`
- 실제 데이터와 유사한 의미있는 테스트 데이터 사용

### 검증
- **Controller**: HTTP 상태 코드, 응답 본문 검증
- **Service**: 반환값 검증, `verify()`로 메서드 호출 검증
- **예외**: `shouldThrow` 또는 `assertThrows` 사용

### RestDocs 문서화
- 모든 API 엔드포인트는 RestDocs로 문서화 필수
- Path Parameter, Query Parameter, Request Body, Response Body 모두 문서화
- Enum 값은 `enum()` 헬퍼 사용
- 필수 필드는 `requiredFieldWithPath()` 사용
- Pagination은 `paginationRequestParams()`, `paginationFields()` 헬퍼 사용

### 에러 코드 문서화
- 에러 응답은 `defaultDocument(errorCodes = listOf("ERROR_CODE"))` 사용
- 에러 코드 목록을 description에 포함

## 테스트 생성 시 체크리스트

1. ✅ 적절한 테스트 베이스 클래스 상속 (`RestDocTest` 또는 `@ExtendWith(MockitoExtension::class)`)
2. ✅ `@DisplayName`으로 한글 설명 추가
3. ✅ Given-When-Then 패턴 사용
4. ✅ 모든 의존성 Mock 설정
5. ✅ RestDocs 문서화 (Controller 테스트)
6. ✅ 검증 로직 포함
7. ✅ 테스트 데이터는 의미있는 값 사용
8. ✅ 예외 케이스도 테스트 (필요시)

## 예시: 완전한 Controller 테스트

```kotlin
class UserControllerTest(
    private val userQuery: UserQuery,
    private val userCommand: UserCommand,
) : RestDocTest() {
    
    @Test
    @DisplayName("회원 가입")
    fun createUser() {
        val request = SignUpRequest.User(
            username = "testuser",
            password = "password123!",
            mobilePhoneNo = "01012345678",
            // ... 기타 필드
        )
        
        whenever(userCommand.signUp(any())).thenReturn(1L)
        
        post("/users/signup") {
            content = jsonToString(request)
        }.andExpect {
            status { isCreated() }
        }.andDo(
            defaultDocument(
                requestFields(
                    requiredFieldWithPath("username").description("사용자명"),
                    requiredFieldWithPath("password").description("비밀번호"),
                    // ... 기타 필드
                ),
                responseFields(
                    fieldWithPath("id").description("생성된 회원 ID")
                )
            )
        )
    }
}
```

