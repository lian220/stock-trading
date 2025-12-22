# 리뷰 통계 Feign 클라이언트 추가 프롬프트

## [목표] 리뷰 통계 조회 Feign 클라이언트 구현 및 연동

리뷰 서비스 API를 호출하는 Feign 클라이언트를 추가하고, `LedgerBroker.getReviewStats` 메서드에서 실제 데이터를 조회하도록 구현합니다.

## [범위]

- **Feign Client**: `dashboard-domain/src/main/kotlin/com/sfn/cancun/dashboard/feign/DashboardLedgerFeignClient.kt`
- **Response DTO**: `dashboard-domain/src/main/kotlin/com/sfn/cancun/dashboard/feign/response/DashboardLedgerResponse.kt`
- **Broker**: `api-rest/src/main/kotlin/com/sfn/cancun/provider/front/user/LedgerBroker.kt`
- **Response DTO**: `user-domain/src/main/kotlin/com/sfn/cancun/user/domain/ledger/dto/NoteReviewResponse.kt`

## [작업 단계]

### 1. DashboardLedgerResponse에 ReviewStatistics 응답 DTO 추가
- `DashboardLedgerResponse` sealed interface에 `ReviewStatistics` data class 추가
- 응답 구조:
  ```kotlin
  data class ReviewStatistics(
      @JsonProperty("resultCode")
      override val resultCode: Long,
      @JsonProperty("resultMessage")
      override val resultMessage: String,
      @JsonProperty("data")
      val data: List<ReviewStatisticsItem>
  ) : DashboardLedgerResponse
  
  data class ReviewStatisticsItem(
      @JsonProperty("requestDate")
      val requestDate: String,
      @JsonProperty("cumulativeReviewCount")
      val cumulativeReviewCount: Int,
      @JsonProperty("cumulativeReplyCount")
      val cumulativeReplyCount: Int,
      @JsonProperty("manualReplyCount")
      val manualReplyCount: Int,
      @JsonProperty("batchReplyCount")
      val batchReplyCount: Int
  )
  ```

### 2. DashboardLedgerFeignClient에 리뷰 통계 조회 메서드 추가
- `getReviewStatistics` 메서드 3개 추가 (day, week, month)
- 기존 `LedgerAdminApiClient.getIndicatorDay/Week/Month` 패턴 참고
- 엔드포인트: `/adm/review/statistics/{periodType}`
  - `day`: `@RequestParam startDate: String, @RequestParam endDate: String`
  - `week`: `@RequestParam startYear: Int, @RequestParam startWeek: Int, @RequestParam endYear: Int, @RequestParam endWeek: Int`
  - `month`: `@RequestParam startYear: Int, @RequestParam startMonth: Int, @RequestParam endYear: Int, @RequestParam endMonth: Int`

### 3. LedgerBroker에 DashboardLedgerFeignClient 의존성 추가
- 생성자에 `DashboardLedgerFeignClient` 파라미터 추가
- `getReviewStats` 메서드에서 Feign 클라이언트 호출 로직 구현
- `DashboardParam.periodType`에 따라 day/week/month 메서드 분기 호출
- 응답 데이터를 `NoteReviewResponse`에 매핑

### 4. LedgerBroker.getReviewStats 메서드 수정
- TODO 주석 제거
- `dashboardMembershipQuery.getStat` 결과와 Feign 응답 데이터를 결합
- `periodDate`를 기준으로 매핑 (`associateBy` 사용)
- `NoteReviewResponse`의 null 필드들을 실제 Feign 데이터로 채우기:
  - `accumulatedReviewCount` ← `cumulativeReviewCount`
  - `accumulatedReplyCount` ← `cumulativeReplyCount`
  - `batchReplyCount` ← `batchReplyCount`
  - `autoReplyCount` ← `manualReplyCount` (필드명 확인 필요)

## [제약사항]

- 기존 아키텍처 패턴 준수 (Feign Client → Broker → Controller)
- `DashboardParam.periodType`에 따라 적절한 Feign 메서드 호출
- 기존 `getReviewStats` 메서드의 반환 타입 유지 (`List<NoteReviewResponse>`)
- Feign 응답이 실패하거나 데이터가 없을 경우 null 유지 (기존 동작 유지)
- `LedgerAdminApiClient.getIndicator*` 메서드의 파라미터 형식 참고:
  - day: `yyyyMMdd` 형식의 String
  - week/month: Int 타입의 year, week/month 값

## [참고]

- `user-domain/src/main/kotlin/com/sfn/cancun/user/support/LedgerAdminApiClient.kt` - 기존 indicator 메서드 패턴
- `api-rest/src/main/kotlin/com/sfn/cancun/provider/front/user/LedgerBroker.kt` - `getIndicator` 메서드의 periodType 분기 로직
- `dashboard-domain/src/main/kotlin/com/sfn/cancun/dashboard/feign/DashboardLedgerFeignClient.kt` - 기존 Feign 클라이언트 구조
- `dashboard-domain/src/main/kotlin/com/sfn/cancun/dashboard/feign/response/DashboardLedgerResponse.kt` - 응답 DTO 구조
- `dashboard-domain/src/main/kotlin/com/sfn/cancun/dashboard/shared/model/DashboardParam.kt` - periodType 정의

## [API 스펙]

**요청:**
```
GET /adm/review/statistics/day?startDate=2025-01-01&endDate=2025-12-01
GET /adm/review/statistics/week?startYear=2025&startWeek=1&endYear=2025&endWeek=52
GET /adm/review/statistics/month?startYear=2025&startMonth=1&endYear=2025&endMonth=12
```

**응답:**
```json
{
  "resultCode": 0,
  "resultMessage": "string",
  "data": [
    {
      "requestDate": "2025-12-22",
      "cumulativeReviewCount": 0,
      "cumulativeReplyCount": 0,
      "manualReplyCount": 0,
      "batchReplyCount": 0
    }
  ]
}
```

## [매핑 규칙]

- `requestDate` → `periodDate`와 매칭하여 데이터 결합
- `cumulativeReviewCount` → `accumulatedReviewCount`
- `cumulativeReplyCount` → `accumulatedReplyCount`
- `batchReplyCount` → `batchReplyCount`
- `manualReplyCount` → `autoReplyCount` (필드명 확인 필요, 요구사항에 autoReplyCount가 없음)

