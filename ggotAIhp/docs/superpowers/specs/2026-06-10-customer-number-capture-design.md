# 고객 번호·이름 수집 수정 설계 (Customer Number/Name Capture)

- **날짜:** 2026-06-10
- **대상 모듈:** `android/app` (com.ggotai.hp)
- **상태:** 승인됨 (구현 대기)

## 1. 배경 / 문제

실기기 테스트에서 통화 1건이 자동 업로드됐으나, 화면·서버에 고객이 `Unknown / 신규`로 표시됐다. 실제로는 주소록에 저장된 "여현동"이다.

원인 사슬:
1. `CallReceiver`가 `TelephonyManager.EXTRA_INCOMING_NUMBER`로 통화 번호를 얻으려 한다.
2. **Android 10+(API 29)부터 일반 앱에는 이 값이 항상 null**이다(시스템 전용 `READ_PRIVILEGED_PHONE_STATE` 필요). 발신 통화엔 원래 없다. → 번호 `null` → `"Unknown"`.
3. `CallSyncWorker`가 번호로 주소록을 역조회(`getContactName`)하는데, 번호가 `"Unknown"`이라 매칭 실패 → 기본값 `"신규"`.

실기기 로그/CallLog 실측:
```
Permission Denial: ... CallReceiver requires android.permission.READ_CALL_LOG / READ_PRIVILEGED_PHONE_STATE
CallReceiver: Scheduling ... for number: null
content query call_log → number=01049534339, name=여현동, type=2(발신), duration=25
```
→ **CallLog에는 번호와 연락처명(`여현동`)이 정확히 들어 있다.** EXTRA_INCOMING_NUMBER 경로는 막다른 길이고, CallLog 조회가 올바른 해법.

## 2. 목표

통화 종료 후 **`CallLog` 조회**로 고객 번호와 이름을 확보하여, `server_call_history.customer_phone_number` / `customer_name`(및 로컬 `call_history`)에 정확히 적재한다. 수신/발신 모두 동작.

### 비목표 (YAGNI)
- 이미 `Unknown/신규`로 적재된 기존 로컬/서버 레코드 **백필 안 함**. 신규 통화부터만 적용.
- 녹음 파일명 파싱 폴백 **안 함**.
- 수발신 구분(`type`) 저장 **안 함**.
- LoginActivity 권한 요청 로직 변경 안 함(`READ_CALL_LOG`은 이미 요청 목록에 포함).

## 3. 컴포넌트

| 컴포넌트 | 종류 | 역할 |
|----------|------|------|
| `CallLogEntry` | 신규 data class | `(number, cachedName, type, dateMillis, durationSec)` |
| `CallLogReader` | 신규 object | `READ_CALL_LOG` 확인 → `CallLog.Calls` 최근 1건(최근 10분 이내) 조회 → `CallLogEntry?` 반환. ContentResolver 의존 → 디바이스 E2E 검증 |
| `CustomerResolver` | 신규 object (순수함수) | 번호/이름 결정 로직. JVM 단위테스트 |
| `CallSyncWorker` | 수정 | CallLog 조회 결과로 number/name 결정 후 기존 저장·업로드에 주입 |
| `CallReceiver` | 수정 | `EXTRA_INCOMING_NUMBER`/`savedNumber` 추출 제거, 통화종료 감지→워커 예약만 유지 |

### 3.1 `CustomerResolver` (순수 함수, 테스트 대상)
```
const UNKNOWN_NUMBER = "Unknown"
const DEFAULT_NAME = "신규"

resolveNumber(callLogNumber): String
    = callLogNumber가 공백 아님 → 그 값, 아니면 "Unknown"

resolveName(cachedName, contactName): String
    = cachedName(공백 아님) ?: contactName(공백 아님 && "신규" 아님) ?: "신규"
```

### 3.2 `CallLogReader` (디바이스 의존, E2E 검증)
- `READ_CALL_LOG` 미승인 시 즉시 `null`(graceful degrade).
- 쿼리: `CallLog.Calls.CONTENT_URI`, projection `[NUMBER, CACHED_NAME, TYPE, DATE, DURATION]`, sort `DATE DESC`, 첫 행.
- 첫 행의 `DATE`가 현재시각 기준 10분 초과면 `null`(오래된 통화 오인 방지 — `CallSyncWorker`의 녹음파일 스캔 윈도우와 일치).

## 4. 데이터 흐름

```
통화 종료 → CallReceiver: scheduleCallSyncWork(context)   // 번호 인자 제거
   → CallSyncWorker.doWork() (8초 후)
        ├ recordFilePath = findLatestCallRecordFile()           // 기존
        ├ entry = CallLogReader.latestCall(context)             // CallLogEntry?
        ├ number = CustomerResolver.resolveNumber(entry?.number)
        ├ contactName = if (number != "Unknown") getContactName(context, number) else null
        ├ name = CustomerResolver.resolveName(entry?.cachedName, contactName)
        ├ CallHistory(phoneNumber=number, customerName=name, ...) 저장
        └ UploadManager.uploadCallHistory(...)                   // 기존 경로
```

서버 적재는 기존 `upload-call`이 그대로 처리(앱이 `phone_number=number`, `customer_name=name` 전송 → 함수가 `customer_phone_number`/`customer_name`로 적재). **서버/Edge Function 변경 없음.**

## 5. 권한
- `READ_CALL_LOG`: 매니페스트 선언 + `LoginActivity.checkPermissions` 요청 목록에 **이미 포함** → 코드 변경 불필요.
- 테스트 기기는 현재 `granted=false` → 검증 전 승인(설정 또는 `adb shell pm grant com.ggotai.hp android.permission.READ_CALL_LOG`).
- 런타임에 권한이 없거나 회수돼도 `CallLogReader`가 `null` 반환 → `Unknown/신규`로 저장하고 업로드는 계속(앱 비차단).

## 6. 테스트 전략
- **`CustomerResolver` JVM 단위테스트:**
  - `resolveNumber`: 정상 번호 → 그대로 / 빈문자열·공백·null → `"Unknown"`.
  - `resolveName`: cachedName 우선 / cachedName 공백+contactName 있음 → contactName / 둘 다 없음 → `"신규"` / contactName이 `"신규"`면 무시하고 `"신규"`.
- **실기기 E2E:** `READ_CALL_LOG` 승인 → 통화 1건 → 로컬 `call_history` 최신 행과 서버 `server_call_history`(shop_key=19)에 `customer_phone_number=01049534339`, `customer_name=여현동` 적재 확인.
- (`CallLogReader`의 ContentResolver 쿼리는 디바이스 E2E로 커버.)

## 7. 영향 받는 파일
- `model/CallLogEntry.kt` — 신규
- `util/CallLogReader.kt` — 신규
- `util/CustomerResolver.kt` — 신규
- `worker/CallSyncWorker.kt` — number/name 결정 경로 교체
- `receiver/CallReceiver.kt` — EXTRA_INCOMING_NUMBER 추출 제거, 워커 예약 단순화
- `worker/CallSyncWorker.kt`의 `KEY_CUSTOMER_NUMBER` 입력은 더 이상 사용 안 함(제거)
- 테스트: `test/.../CustomerResolverTest.kt` — 신규
