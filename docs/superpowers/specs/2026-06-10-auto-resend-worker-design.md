# 자동 재전송 워커 설계 (Auto-Resend Worker)

- **날짜:** 2026-06-10
- **대상 모듈:** `android/app` (com.ggotai.hp)
- **상태:** 승인됨 (구현 대기)

## 1. 배경 / 문제

현재 통화 업로드는 **이벤트 기반 단방향 push** 구조다. 통화 종료 시 `CallReceiver` → `CallSyncWorker`(OneTime) → `UploadManager.uploadCallHistory()`(즉시 3회 재시도)로 서버에 적재한다. 3회 즉시 재시도가 모두 실패하면 `transfer_status='실패'`, `sync_status=0`으로 로컬에 남고 **자동 재시도가 없다.** 일시적 네트워크 끊김으로 실패한 건은 사장님이 `ResendActivity`에서 직접 재전송을 눌러야만 올라간다 → 실무 안정성 약점.

## 2. 목표

일시적 장애로 업로드 실패한 건(`sync_status=0`, `transfer_status='실패'`)을 사용자 개입 없이 백그라운드에서 자동 재업로드한다. 영구 실패 건은 상한 도달 후 자동 재시도에서 제외한다.

### 비목표 (YAGNI)
- 서버→핸드폰 방향 동기화(pull/download)는 범위 밖. 단방향 push 모델 유지.
- 재시도 주기/상한의 런타임 설정 UI는 만들지 않음(상수 고정).
- 워커 재시도 실패 시 TTS 음성 알림은 울리지 않음(백그라운드 조용히 동작).

## 3. 데이터 모델 변경 (Room v1 → v2)

### 3.1 컬럼 추가
`CallHistory` 엔티티(`db/CallHistory.kt`)에 컬럼 1개 추가:

```kotlin
@ColumnInfo(name = "retry_count") var retryCount: Int = 0
```

### 3.2 `sync_status` 의미 확장
| 값 | 의미 |
|----|------|
| 0 | 미전송 (자동 재시도 대상) |
| 1 | 전송 성공 |
| **2** | **영구 실패** — 재시도 상한 도달. 자동 재시도 제외, 수동 재전송만 가능 |

### 3.3 마이그레이션
`AppDatabase`를 `version = 2`로 올리고 `Migration(1, 2)` 등록:

```sql
ALTER TABLE call_history ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0
```

기존 데이터는 보존된다(파괴적 마이그레이션 금지).

## 4. 컴포넌트

| 컴포넌트 | 종류 | 역할 |
|----------|------|------|
| `ResendWorker` | 신규 `CoroutineWorker` | 15분 주기. 재시도 대상 조회 후 1건씩 `uploadOnce` 호출 |
| `UploadManager.uploadOnce(context, historyId): Boolean` | 신규(추출) | 멀티파트 **1회** 전송. 성공→`성공`/`sync=1` 처리 후 `true`, 실패→`false` 반환 |
| `CallHistoryDao.getRetryable(max)` | 신규 쿼리 | `WHERE sync_status = 0 AND transfer_status = '실패' AND retry_count < :max` |
| `AppDatabase` | 수정 | version 2 + `Migration(1,2)` 등록 |
| `MainActivity`(또는 Application) | 수정 | 진입 시 `enqueueUniquePeriodicWork("auto-resend", KEEP, ...)` 1회 등록 |

### 4.1 `uploadOnce` 추출 방침
기존 `UploadManager.uploadCallHistory(context, historyId)`의 내부 3회 재시도 루프에서 **단일 전송 1회분**을 `uploadOnce`로 추출한다. 기존 `uploadCallHistory`(즉시 업로드 경로, 통화 직후 호출)는 `uploadOnce`를 3회 감싸는 형태로 리팩터링하여 동작을 보존한다. 워커는 `uploadOnce`를 **건당 1회만** 호출하고(15분 주기가 재시도 역할), 실패 시 `retry_count` 증가는 워커가 담당한다.

## 5. 워커 로직 (`ResendWorker.doWork`)

```
1. AUTO_SYNC_ENABLED == false  → Result.success() 즉시 종료 (기존 환경설정 존중)
2. items = dao.getRetryable(MAX_RETRY)
3. var changed = false
   for item in items:
     - 녹음파일(item.audioFilePath) 미존재 →
         item.sync_status = 2 (영구실패); dao.update; changed = true; continue
     - ok = UploadManager.uploadOnce(context, item.id)
         ok == true  → (uploadOnce 내부에서 성공/sync=1 처리됨); changed = true
         ok == false → item.retryCount++
                        if (item.retryCount >= MAX_RETRY) item.sync_status = 2 (영구실패)
                        dao.update(item); changed = true
4. if (changed) sendBroadcast(ACTION_UPDATE_HISTORY)  // MainActivity 목록 새로고침
5. Result.success()  // 다음 주기에 재시도
```

## 6. 제약 / 정책

- **WorkManager 제약:** `Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED)` — 네트워크 있을 때만 실행(배터리 절약).
- **주기:** `PeriodicWorkRequestBuilder<ResendWorker>(15, TimeUnit.MINUTES)`, 등록은 `ExistingPeriodicWorkPolicy.KEEP`(중복 등록 방지). WorkManager 시스템 최소 주기 = 15분.
- **상한:** `MAX_RETRY = 10` (약 2.5시간). 도달 시 `sync_status=2`(영구실패).
- **중복 업로드 방지:**
  - 워커 조회 조건이 `transfer_status='실패'`이므로 `전송중`(즉시 업로드 진행 중) 건은 건드리지 않음 → 즉시 업로드 경로와 분리.
  - 설령 동시 실행돼도 서버 `upload-call`의 멱등성 pre-check(`shop_key + customer_phone_number + call_date + call_time` 중복 검사)가 DB/스토리지 중복을 차단.
- **수동 재전송 연계:** `ResendActivity` 수동 재전송 시 해당 건을 `retry_count=0`, `sync_status=0`으로 리셋 → 영구실패(sync=2) 건도 사용자가 다시 살리면 자동 재시도 재개.
- **TTS 알림:** 워커 재시도 실패에는 TTS 미발생. 기존 `use_notification` 게이팅(즉시 업로드 경로의 `playTtsError`)과 무관하게 유지.

## 7. 테스트 전략

- **마이그레이션 테스트** (Room `MigrationTestHelper`): v1 스키마로 행 삽입 → v1→v2 마이그레이션 → 기존 행 보존 + `retry_count=0` 확인.
- **DAO 단위 테스트:** `getRetryable`가 상태(`sync_status`/`transfer_status`)와 상한(`retry_count < max`)으로 정확히 필터링하는지.
- **워커 로직 테스트** (`TestListenableWorkerBuilder`): 성공 / 실패 후 retry_count 증가 / 상한 도달 시 sync=2 / 녹음파일 없음 시 sync=2 / `AUTO_SYNC_ENABLED=false` 즉시 종료 경로.
- **실기기 검증:** 비행기모드로 업로드 실패 유도 → 해제 후 15분 내 자동 성공 및 목록 상태 갱신 확인.

## 8. 영향 받는 파일

- `db/CallHistory.kt` — 컬럼 추가
- `db/CallHistoryDao.kt` — `getRetryable` 추가
- `db/AppDatabase.kt` — version 2 + Migration(1,2)
- `manager/UploadManager.kt` — `uploadOnce` 추출, `uploadCallHistory` 리팩터링
- `worker/ResendWorker.kt` — 신규
- `MainActivity.kt` — periodic work 등록 (+ 수동 재전송 리셋이 `ResendActivity`에 있으면 함께 수정)
- `ResendActivity.kt` — 수동 재전송 시 retry_count/sync_status 리셋
- 테스트 소스(`androidTest`/`test`)
