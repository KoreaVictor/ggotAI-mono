# 승인 취소된 기기의 백그라운드 수집 완전 중단 — 설계

- 작성일: 2026-06-12
- 상태: 승인됨 (구현 대기)

## 1. 배경 / 문제

현재 앱의 로그인(`verify-device`)과 백그라운드 녹음/전송 파이프라인은 서로 분리되어 있다.
서버에서 가맹점 핸드폰 번호를 삭제하거나 승인을 취소(`is_approved != 'Y'`)해도:

- `CallReceiver`(매니페스트 등록 수신기)는 로그인 여부와 무관하게 통화 종료 시 항상 `CallSyncWorker`를 예약한다.
- `CallSyncWorker`는 `AUTO_SYNC_ENABLED`만 확인할 뿐 승인 상태를 확인하지 않는다.
- 주기 `ResendWorker`(15분)는 한 번 등록되면 계속 재시도한다.

그 결과 승인 취소된 기기도 **계속 녹음·업로드를 시도**하여 배터리/데이터를 소모하고, 실패 음성이 반복적으로 울릴 수 있다. 서버는 `upload-call`에서 401 `AUTH_ERR`로 거부하지만, 클라이언트는 이를 단순 실패로 취급해 멈추지 않는다.

## 2. 목표

승인 취소가 **명시적으로 확인된** 기기는 백그라운드 수집(녹음 감지·로컬 적재·업로드·재전송)을 완전히 멈춘다. 일시적 오류(네트워크/500)로는 절대 멈추지 않는다. 관리자가 재승인하면 사용자가 앱을 다시 열어 로그인 성공 시 자동 복구된다.

## 3. 비목표 (YAGNI)

- 서버 푸시/주기 폴링으로 비활성화 신호를 받는 메커니즘은 만들지 않는다.
- 승인 취소 기기에서 이미 로컬에 쌓인 데이터의 삭제/정리는 하지 않는다(상태만 보존).

## 4. 핵심 설계 결정

| 결정 | 선택 | 이유 |
|------|------|------|
| 감지 신호 | `upload-call`의 **401 AUTH_ERR만** | 서버가 명시적으로 거부한 경우만 → 오판 위험 최소. 500/네트워크 오류는 기존대로 재전송. |
| 복구 방식 | 앱 재실행 시 **로그인 성공으로 자동 복구** | 추가 조작 불필요. |
| 사용자 알림 | **음성 + 상태바 알림 1회** | 사용자가 "멈춘 사실"을 인지해야 함. `USE_NOTIFICATION=N`이면 생략. |
| 로직 위치 | **중앙화된 `DeviceStatus` 헬퍼** | 상태·차단·알림을 한 곳에서 관리, 경로 누락 방지. |

## 5. 아키텍처

### 5.1 상태 저장
- `SharedPreferences("app_prefs")`의 `DEVICE_REVOKED: Boolean` (기본 `false`).
- 영구 저장이라 재부팅/프로세스 종료에도 유지된다.

### 5.2 새 컴포넌트: `DeviceStatus` (object)
책임: "기기 승인취소 상태 관리" 하나.

- `isRevoked(context): Boolean` — 플래그 조회.
- `clearRevoked(context)` — 플래그 해제(복구 시).
- `markRevoked(context)` — **false→true 전이일 때만** 1회 수행:
  1. `DEVICE_REVOKED = true` 저장
  2. 주기 `ResendWorker` 취소: `WorkManager.cancelUniqueWork(ResendWorker.UNIQUE_NAME)`
  3. 사용자 1회 안내:
     - 음성: `UploadManager.speak("이 기기는 승인이 취소되어 녹음 수집이 중단되었습니다.")`
     - 상태바 알림 1건
     - `USE_NOTIFICATION=N`이면 음성/알림 모두 생략
  - 이미 `revoked`면 즉시 `return` → **반복 알림 방지**

의존성: `Context`, `WorkManager`, `UploadManager.speak`(음성), Android `NotificationManager`(알림).

## 6. 감지 (플래그 set)

`UploadManager.uploadOnce`:
- 서버 응답 코드가 **401**이면(`upload-call`은 AUTH_ERR에만 401 사용) `DeviceStatus.markRevoked(context)` 호출 후 `false` 반환.
- 그 외 실패(500/네트워크/타임아웃)는 기존대로 `errorCode/errorMessage`만 기록하고 `false`.

## 7. 차단 (플래그 check) — 4개 진입점

| 위치 | 동작 |
|------|------|
| `CallReceiver.scheduleCallSyncWork` | `isRevoked`면 워커 예약 자체를 건너뜀 |
| `CallSyncWorker.doWork` 시작부(AUTO_SYNC 체크 직후) | `isRevoked`면 즉시 `Result.success()` 반환(수집 skip) |
| `ResendWorker.resend` 시작부 | `isRevoked`면 주기 워커 취소 + 즉시 `Result.success()` 반환 |
| `UploadManager.uploadCallHistory` 재시도 루프 | 401로 revoked되면 남은 재시도 중단 + 일반 실패 음성(`playTtsError`) 생략(승인취소 안내가 대체) |

## 8. 복구

`LoginActivity.verifyDeviceOnServer`:
- 검증 **성공** 시 `DeviceStatus.clearRevoked(context)` 호출.
- 이후 정상 흐름으로 MainActivity 진입 → MainActivity가 주기 `ResendWorker`를 `ExistingPeriodicWorkPolicy.KEEP`로 등록(취소되어 없으므로 신규 생성).
- 추가 사용자 조작 불필요.

## 9. 엣지 케이스 / 오판 방지

- **일시적 오류**: 401(AUTH_ERR)에만 반응. 500/타임아웃/오프라인은 절대 revoke 처리하지 않는다.
- **반복 알림**: `markRevoked`의 전이 가드(`isRevoked`면 즉시 return)로 음성·알림은 정확히 1회.
- **직전 작업과의 충돌**: revoked 경로에서는 일반 실패 음성 및 영구실패 요약 음성("전송하지 못한 통화가 N건…")을 내지 않는다(승인취소 안내가 대체).
- **레이스**: 주기 ResendWorker가 이미 실행 중에 revoke되어도 `resend` 시작부 가드 + `markRevoked`의 워커 취소로 다음 주기는 뜨지 않는다.

## 10. 테스트 전략

- `DeviceStatus` 단위 테스트: `markRevoked` 전이 가드(연속 호출 시 1회만 동작), `clearRevoked` 후 `isRevoked=false`.
- `uploadOnce` 401 응답 → `DeviceStatus.isRevoked=true` 검증.
- `CallSyncWorker`/`ResendWorker` revoked 상태에서 skip 동작 검증.
- 수동 검증(연결된 기기): 서버에서 번호 승인 취소 → 통화 1회 → 음성/알림 1회 + 수집 중단 확인 → 재승인 + 앱 재로그인 → 수집 재개 확인.

## 11. 영향 받는 파일

- 신규: `manager/DeviceStatus.kt`
- 수정: `manager/UploadManager.kt`, `worker/CallSyncWorker.kt`, `worker/ResendWorker.kt`, `receiver/CallReceiver.kt`, `LoginActivity.kt`
