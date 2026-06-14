# ggotAIhp 병렬 개발 구현 계획 (Implementation Plan)

본 문서는 `ggotAIhp` 안드로이드 앱의 효율적인 병렬 개발을 위해 프론트엔드(안티그래비티)와 백엔드(클로드코드)의 역할을 명확히 분리하고, 두 에이전트가 동시에 작업할 때 충돌이나 연동 오류가 발생하지 않도록 기준을 제시합니다.

## User Review Required

> [!IMPORTANT]
> **앱 배포 방식 확인:** PRD에 명시된 바와 같이 구글 플레이 스토어 배포가 불가능하며 **APK 수동 설치(사이드로드)** 방식으로 진행됩니다. 이 점을 최종 확인해 주세요.
> **백엔드 기술 스택:** 클로드코드가 작업할 백엔드 프레임워크(예: Node.js, Python FastAPI, Spring Boot 등)에 대한 선호가 있는지 확인이 필요합니다. 지정되지 않으면 클로드코드가 가장 적합한 스택으로 구성합니다.

## Open Questions

> [!WARNING]
> 1. **서버 API 엔드포인트 주소:** 프론트엔드(안드로이드) 앱에 하드코딩될 기본 서버 주소(예: `https://api.ggotai.com` 또는 로컬 테스트 주소)가 필요합니다. 임시 주소라도 먼저 정해주시면 연동 준비에 도움이 됩니다.
> 2. **테스트 환경:** 단말기 유심 번호 추출 기능을 에뮬레이터에서 테스트하기 까다로울 수 있습니다. 안티그래비티가 제공하는 빌드(APK)를 사장님의 실제 공기계(유심 장착)에서 직접 테스트하실 수 있는지 확인 부탁드립니다.

---

## 병렬 개발 역할 분담 (Proposed Roles)

### 1. 프론트엔드 (담당: 안티그래비티)
안드로이드 네이티브 앱 개발 (Kotlin 기반). 화면 구현 및 단말기 제어에 집중합니다.

- **프로젝트 셋업:** Android SDK (API 29 타겟), Kotlin Coroutines, Retrofit2, Room DB, WorkManager 설정.
- **권한 관리:** `READ_PHONE_NUMBERS`, `READ_PHONE_STATE`, 오디오 녹음, 백그라운드 서비스 권한 요청 로직.
- **UI 구현:** `LoginActivity`(경고창 위주), `MainActivity`(현황 리스트), `SearchActivity`(필터 검색), `ResendActivity`(재전송 팝업), `SettingsActivity`.
- **핵심 로직:**
  - 기기 유심 번호 자동 추출 및 백엔드 인증 요청.
  - `BroadcastReceiver`를 활용한 통화 상태 감지 및 `MediaRecorder` 파일 녹음.
  - 앱 종료/대기 상태에서도 작동하는 Foreground Service 및 재시도 메커니즘.
  - TTS 실패 알림 연동.

### 2. 백엔드 (담당: 클로드코드)
RESTful API 서버 개발 및 데이터베이스 구축. 인증 검증과 데이터 저장에 집중합니다.

- **DB 구축:** PRD에 정의된 `member_info`, `server_call_history` 테이블 설계 및 생성.
- **기기 인증 API (`GET /api/v1/auth/verify-device`):** 앱에서 전달받은 단말기 번호가 `member_info`의 `mobile_1~5`에 존재하는지 검증.
- **오디오 및 통화 이력 수신 API (`POST /api/v1/calls/upload`):** `multipart/form-data`를 파싱하여 오디오 파일(.wav)을 스토리지에 저장하고, 통화 메타데이터를 `server_call_history`에 인서트.

---

## API 인터페이스 명세 (Interface Specifications)

> [!TIP]
> 두 에이전트가 동시에 작업하기 위해 **가장 중요하게 지켜야 할 약속**입니다. 이 명세대로 프론트엔드는 호출 코드를 작성하고, 백엔드는 수신 코드를 작성합니다.

### 1. 단말기 기기 인증 API
- **Endpoint:** `GET /api/v1/auth/verify-device`
- **Request Parameter:**
  - `phone` (String, Required): 하이픈 제외 숫자만 (예: `01012345678`)
- **Response (Success - 200 OK):**
  ```json
  {
    "status": "success",
    "data": {
      "shop_name": "서울플라워",
      "representative_name": "홍길동",
      "is_approved": "Y"
    }
  }
  ```
- **Response (Fail - 401 Unauthorized / 404 Not Found):**
  ```json
  {
    "status": "error",
    "error_code": "AUTH_ERR",
    "message": "등록되지 않거나 승인되지 않은 단말기입니다."
  }
  ```

### 2. 통화 이력 및 녹음 파일 업로드 API
- **Endpoint:** `POST /api/v1/calls/upload`
- **Content-Type:** `multipart/form-data`
- **Request Parameters (Form Data):**
  - `user_phone_number` (String): 기기 자체 번호
  - `phone_number` (String): 전화를 건 고객 번호
  - `customer_name` (String): 고객명 (기본값 '신규')
  - `call_date` (String): YYYY-MM-DD
  - `call_time` (String): HH:mm:ss
  - `duration_seconds` (Integer): 통화 시간(초)
  - `audio_file` (File): 실제 .wav 파일
- **Response (Success - 200 OK):**
  ```json
  {
    "status": "success",
    "message": "업로드 성공"
  }
  ```
- **Response (Fail - 500 등):**
  ```json
  {
    "status": "error",
    "error_code": "SERVER_500",
    "message": "내부 서버 오류"
  }
  ```

---

## Verification Plan

### 프론트엔드 (안티그래비티)
- 더미 API(Mock 웹서버)를 로컬에 띄워 인증, 에러 및 파일 전송 상태 UI가 기획대로 변경되는지 테스트.
- 실제 안드로이드 단말(API 29 이상) 빌드 후 백그라운드 통화 녹음 파일이 정상적으로 `WAV`로 남는지 확인.

### 백엔드 (클로드코드)
- Postman 또는 cURL을 이용해 API 엔드포인트에 더미 Multipart 데이터를 전송하여 정상적으로 DB에 꽂히고 파일이 저장되는지 검증.
- 유효하지 않은 폰 번호 입력 시 401/404 에러를 정확히 반환하는지 테스트.
