# 승인 취소 기기 백그라운드 수집 중단 — 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 서버가 `upload-call`에서 401 AUTH_ERR로 거부하는(=승인 취소된) 기기는 백그라운드 녹음/전송을 완전히 멈추고, 사용자에게 1회 안내하며, 재로그인 시 자동 복구한다.

**Architecture:** `app_prefs`의 `DEVICE_REVOKED` 플래그를 중앙 헬퍼 `DeviceStatus`가 관리한다. `UploadManager.uploadOnce`가 401을 받으면 `markRevoked`로 플래그를 세우고(전이 시 1회 워커 취소+음성+알림), 4개 수집 진입점이 `isRevoked`를 확인해 차단한다. 로그인 검증 성공 시 `clearRevoked`로 복구한다.

**Tech Stack:** Kotlin, Android (SharedPreferences, WorkManager, NotificationCompat, TextToSpeech), JUnit + AndroidJUnit4 계측 테스트.

**환경 메모:** 모든 gradle 명령은 PowerShell에서 `$env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"` 설정 후 `android` 디렉터리에서 실행한다. 계측 테스트는 연결된 실기기(`R3CM90GYTWR`)에서 동작한다.

---

## 파일 구조

- **신규** `android/app/src/main/java/com/ggotai/hp/manager/DeviceStatus.kt` — 승인취소 상태 관리(조회/해제/전이 기록 + 워커취소 + 사용자 1회 안내). 단일 책임.
- **신규(테스트)** `android/app/src/androidTest/java/com/ggotai/hp/DeviceStatusTest.kt` — 플래그 set/clear/전이 가드 계측 테스트.
- **수정** `manager/UploadManager.kt` — 401 감지 → `markRevoked`; `uploadCallHistory` 재시도/음성 분기에 revoked 처리 추가.
- **수정** `worker/CallSyncWorker.kt` — `doWork` 시작부 revoked 차단.
- **수정** `worker/ResendWorker.kt` — `resend` 시작부 revoked 차단 + 주기 워커 취소.
- **수정** `receiver/CallReceiver.kt` — `scheduleCallSyncWork` revoked 차단.
- **수정** `LoginActivity.kt` — 검증 성공 시 `clearRevoked`.

---

## Task 1: DeviceStatus 헬퍼 + 계측 테스트

**Files:**
- Create: `android/app/src/main/java/com/ggotai/hp/manager/DeviceStatus.kt`
- Test: `android/app/src/androidTest/java/com/ggotai/hp/DeviceStatusTest.kt`

- [ ] **Step 1: 실패 테스트 작성**

`android/app/src/androidTest/java/com/ggotai/hp/DeviceStatusTest.kt`:

```kotlin
package com.ggotai.hp

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.ggotai.hp.manager.DeviceStatus
import org.junit.After
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class DeviceStatusTest {
    private val context = ApplicationProvider.getApplicationContext<Context>()

    // 실제 기기의 app_prefs를 사용하므로 테스트 전후로 반드시 초기화(앱 오염 방지).
    @Before
    fun setUp() { DeviceStatus.clearRevoked(context) }

    @After
    fun tearDown() { DeviceStatus.clearRevoked(context) }

    @Test
    fun default_isNotRevoked() {
        assertFalse(DeviceStatus.isRevoked(context))
    }

    @Test
    fun markRevoked_firstCall_transitionsTrue() {
        val firstTransition = DeviceStatus.markRevoked(context)
        assertTrue(firstTransition)
        assertTrue(DeviceStatus.isRevoked(context))
    }

    @Test
    fun markRevoked_secondCall_returnsFalse_idempotent() {
        DeviceStatus.markRevoked(context)
        val secondTransition = DeviceStatus.markRevoked(context)
        assertFalse(secondTransition)   // 이미 취소 → 반복 안내 방지
        assertTrue(DeviceStatus.isRevoked(context))
    }

    @Test
    fun clearRevoked_resetsFlag() {
        DeviceStatus.markRevoked(context)
        DeviceStatus.clearRevoked(context)
        assertFalse(DeviceStatus.isRevoked(context))
    }
}
```

- [ ] **Step 2: 테스트가 컴파일 실패하는지 확인**

PowerShell:
```
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"
Set-Location C:\ggotAIhp\android
& .\gradlew.bat compileDebugAndroidTestKotlin
```
Expected: FAIL — `unresolved reference: DeviceStatus`.

- [ ] **Step 3: DeviceStatus 구현**

`android/app/src/main/java/com/ggotai/hp/manager/DeviceStatus.kt`:

```kotlin
package com.ggotai.hp.manager

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.os.Build
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.work.WorkManager
import com.ggotai.hp.worker.ResendWorker

/**
 * 기기 승인취소(서버가 upload-call에서 401 AUTH_ERR 반환) 상태를 관리한다.
 * 승인취소가 확정되면 백그라운드 수집을 멈추고 사용자에게 1회 안내한다.
 */
object DeviceStatus {
    private const val TAG = "DeviceStatus"
    private const val PREFS = "app_prefs"
    private const val KEY_REVOKED = "DEVICE_REVOKED"
    private const val CHANNEL_ID = "DeviceRevokeChannel"
    private const val NOTIFICATION_ID = 2

    fun isRevoked(context: Context): Boolean =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getBoolean(KEY_REVOKED, false)

    fun clearRevoked(context: Context) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit().putBoolean(KEY_REVOKED, false).apply()
        Log.d(TAG, "revoked 플래그 해제")
    }

    /**
     * 승인취소를 기록한다. false→true 전이일 때만 주기 워커 취소 + 1회 안내를 수행한다.
     * @return 이번 호출로 새로 취소 상태가 된 경우 true, 이미 취소 상태였으면 false.
     */
    fun markRevoked(context: Context): Boolean {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        if (prefs.getBoolean(KEY_REVOKED, false)) return false  // 이미 취소 → 반복 안내 방지

        prefs.edit().putBoolean(KEY_REVOKED, true).apply()
        Log.d(TAG, "기기 승인취소 감지 → 수집 중단")

        // 주기 재전송 워커 취소
        WorkManager.getInstance(context).cancelUniqueWork(ResendWorker.UNIQUE_NAME)

        // use_notification=N이면 음성/알림 모두 생략 (playTtsError와 동일 정책)
        if (prefs.getString("USE_NOTIFICATION", "Y") != "N") {
            UploadManager.speak("이 기기는 승인이 취소되어 녹음 수집이 중단되었습니다.")
            notifyUser(context)
        }
        return true
    }

    private fun notifyUser(context: Context) {
        val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            nm.createNotificationChannel(
                NotificationChannel(CHANNEL_ID, "기기 승인 안내", NotificationManager.IMPORTANCE_HIGH)
            )
        }
        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setContentTitle("녹음 수집 중단")
            .setContentText("이 기기는 승인이 취소되어 녹음 수집이 중단되었습니다. 관리자에게 문의하세요.")
            .setSmallIcon(android.R.drawable.stat_sys_warning)
            .setAutoCancel(true)
            .build()
        nm.notify(NOTIFICATION_ID, notification)
    }
}
```

- [ ] **Step 4: 계측 테스트 실행 (연결된 기기)**

PowerShell:
```
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"
Set-Location C:\ggotAIhp\android
& .\gradlew.bat connectedDebugAndroidTest "-Pandroid.testInstrumentationRunnerArguments.class=com.ggotai.hp.DeviceStatusTest"
```
Expected: PASS — 4개 테스트 모두 통과. (`tearDown`이 플래그를 해제하므로 실기기 앱은 영향 없음.)

- [ ] **Step 5: 커밋**

```
git add android/app/src/main/java/com/ggotai/hp/manager/DeviceStatus.kt android/app/src/androidTest/java/com/ggotai/hp/DeviceStatusTest.kt
git commit -m "feat: 기기 승인취소 상태 관리 DeviceStatus 추가"
```

---

## Task 2: UploadManager 401 감지 + 업로드 흐름 revoked 처리

**Files:**
- Modify: `android/app/src/main/java/com/ggotai/hp/manager/UploadManager.kt`

- [ ] **Step 1: uploadOnce 실패 분기에 401 감지 추가**

`UploadManager.kt`의 `uploadOnce` 내 응답 실패 `else` 블록(현재 `history.errorCode = "SERVER_500"` 부분)을 아래로 교체:

```kotlin
            } else {
                if (response.code() == 401) {
                    // 서버가 명시적으로 거부(AUTH_ERR) → 승인취소 확정. 수집 중단 트리거.
                    DeviceStatus.markRevoked(context)
                    history.errorCode = "AUTH_ERR"
                    history.errorMessage = "승인이 취소된 단말기입니다."
                } else {
                    history.errorCode = "SERVER_500"
                    history.errorMessage = response.body()?.message ?: "서버 업로드 실패"
                }
                dao.update(history)
                Log.e(TAG, "Upload failed (uploadOnce) id=$historyId: ${history.errorMessage}")
                false
            }
```

- [ ] **Step 2: uploadCallHistory 재시도 루프에 revoked 조기중단 추가**

`UploadManager.kt`의 재시도 `while` 루프를 아래로 교체:

```kotlin
            var attempt = 0
            var success = false
            while (attempt < MAX_RETRIES && !success) {
                success = uploadOnce(context, historyId)
                if (!success) {
                    if (DeviceStatus.isRevoked(context)) {
                        Log.d(TAG, "승인취소 감지 — 재시도 중단 id=$historyId")
                        break  // 401은 재시도해도 동일 → 무의미
                    }
                    attempt++
                    if (attempt < MAX_RETRIES) delay(RETRY_DELAY_MS)
                }
            }
```

- [ ] **Step 3: uploadCallHistory 최종 실패 음성 분기에 revoked 분기 추가**

`UploadManager.kt`의 `if (!success) { ... }` 블록 내 음성 분기(현재 `if (NetworkUtil.isOnline(context)) { playTtsError(context) } else { ... }`)를 아래로 교체:

```kotlin
                when {
                    DeviceStatus.isRevoked(context) ->
                        // 승인취소 안내(markRevoked)가 이미 1회 처리됨 → 일반 실패음성 생략
                        Log.d(TAG, "승인취소 — 일반 실패음성 생략 id=$historyId")
                    NetworkUtil.isOnline(context) -> playTtsError(context)
                    else -> {
                        enqueueResendOnReconnect(context)
                        Log.d(TAG, "업로드 실패 후 오프라인 — 음성 생략, 자동 전송 예약 id=$historyId")
                    }
                }
```

- [ ] **Step 4: 컴파일 검증**

PowerShell:
```
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"
Set-Location C:\ggotAIhp\android
& .\gradlew.bat compileDebugKotlin
```
Expected: `BUILD SUCCESSFUL`. (`DeviceStatus`는 같은 `manager` 패키지라 import 불필요.)

- [ ] **Step 5: 커밋**

```
git add android/app/src/main/java/com/ggotai/hp/manager/UploadManager.kt
git commit -m "feat: 업로드 401(AUTH_ERR)에서 승인취소 감지 및 수집 중단 연동"
```

---

## Task 3: 수집 진입점 3곳 차단

**Files:**
- Modify: `android/app/src/main/java/com/ggotai/hp/worker/CallSyncWorker.kt`
- Modify: `android/app/src/main/java/com/ggotai/hp/worker/ResendWorker.kt`
- Modify: `android/app/src/main/java/com/ggotai/hp/receiver/CallReceiver.kt`

- [ ] **Step 1: CallSyncWorker.doWork 시작부 차단**

`CallSyncWorker.kt` 상단 import에 추가:
```kotlin
import com.ggotai.hp.manager.DeviceStatus
```
`doWork` 내 AUTO_SYNC 체크 블록(`if (!isAutoSyncEnabled) { ... }`) 바로 아래에 추가:
```kotlin
        if (DeviceStatus.isRevoked(context)) {
            Log.d(TAG, "기기 승인취소 — CallSyncWorker 수집 중단")
            return@withContext Result.success()
        }
```

- [ ] **Step 2: ResendWorker.resend 시작부 차단**

`ResendWorker.kt` 상단 import에 추가:
```kotlin
import androidx.work.WorkManager
import com.ggotai.hp.manager.DeviceStatus
```
`resend()` 내 AUTO_SYNC 체크 블록(`if (!prefs.getBoolean("AUTO_SYNC_ENABLED", true)) { ... }`) 바로 아래에 추가:
```kotlin
        if (DeviceStatus.isRevoked(applicationContext)) {
            Log.d(TAG, "기기 승인취소 — 재전송 워커 중단 + 주기 취소")
            WorkManager.getInstance(applicationContext).cancelUniqueWork(UNIQUE_NAME)
            return Result.success()
        }
```

- [ ] **Step 3: CallReceiver.scheduleCallSyncWork 차단**

`CallReceiver.kt` 상단 import에 추가:
```kotlin
import com.ggotai.hp.manager.DeviceStatus
```
`scheduleCallSyncWork` 함수 맨 앞에 추가:
```kotlin
        if (DeviceStatus.isRevoked(context)) {
            Log.d(TAG, "기기 승인취소 — 통화 동기화 예약 건너뜀")
            return
        }
```

- [ ] **Step 4: 컴파일 검증**

PowerShell:
```
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"
Set-Location C:\ggotAIhp\android
& .\gradlew.bat compileDebugKotlin
```
Expected: `BUILD SUCCESSFUL`.

- [ ] **Step 5: 커밋**

```
git add android/app/src/main/java/com/ggotai/hp/worker/CallSyncWorker.kt android/app/src/main/java/com/ggotai/hp/worker/ResendWorker.kt android/app/src/main/java/com/ggotai/hp/receiver/CallReceiver.kt
git commit -m "feat: 승인취소 시 CallReceiver/CallSyncWorker/ResendWorker 수집 차단"
```

---

## Task 4: 로그인 성공 시 자동 복구

**Files:**
- Modify: `android/app/src/main/java/com/ggotai/hp/LoginActivity.kt`

- [ ] **Step 1: verifyDeviceOnServer 성공 분기에 clearRevoked 추가**

`LoginActivity.kt` 상단 import에 추가:
```kotlin
import com.ggotai.hp.manager.DeviceStatus
```
`verifyDeviceOnServer`의 성공 분기(`if (response.isSuccessful && response.body()?.status == "success") {`) 첫 줄에 추가:
```kotlin
                    DeviceStatus.clearRevoked(this@LoginActivity)
```
(이후 MainActivity 진입이 주기 ResendWorker를 `KEEP` 정책으로 재등록한다.)

- [ ] **Step 2: 컴파일 검증**

PowerShell:
```
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"
Set-Location C:\ggotAIhp\android
& .\gradlew.bat compileDebugKotlin
```
Expected: `BUILD SUCCESSFUL`.

- [ ] **Step 3: 커밋**

```
git add android/app/src/main/java/com/ggotai/hp/LoginActivity.kt
git commit -m "feat: 로그인 검증 성공 시 승인취소 플래그 해제(자동 복구)"
```

---

## Task 5: 전체 빌드 + 기기 설치 + 수동 E2E 검증

**Files:** (없음 — 검증 전용)

- [ ] **Step 1: 기존 JVM 단위테스트 회귀 확인**

PowerShell:
```
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"
Set-Location C:\ggotAIhp\android
& .\gradlew.bat testDebugUnitTest
```
Expected: `BUILD SUCCESSFUL` (ResendPolicyTest, CustomerResolverTest 통과 유지).

- [ ] **Step 2: 디버그 빌드 + 기기 설치**

PowerShell:
```
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"
Set-Location C:\ggotAIhp\android
& .\gradlew.bat installDebug
```
Expected: `Installed on 1 device.`

- [ ] **Step 3: 수동 E2E — 승인취소 → 중단**

1. 서버(Supabase `member_info`)에서 해당 기기 번호의 `is_approved`를 `N`으로 변경(또는 행 삭제).
2. 기기에서 통화 1회 발신/수신 후 종료.
3. 확인: 음성 "이 기기는 승인이 취소되어 녹음 수집이 중단되었습니다." 1회 재생 + 상태바 알림 1건.
4. `adb logcat`에서 `DeviceStatus`/`CallSyncWorker`/`ResendWorker` 로그로 차단 확인.
5. 추가 통화 1회 더 → 음성/알림이 **다시 울리지 않음**(전이 가드) 확인.

로그 확인 명령:
```
& "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe" logcat -d -s DeviceStatus:* CallSyncWorker:* ResendWorker:* UploadManager:*
```

- [ ] **Step 4: 수동 E2E — 재승인 → 복구**

1. 서버에서 `is_approved`를 다시 `Y`로 변경.
2. 기기에서 앱을 열어 로그인 성공(환영 토스트 확인).
3. 통화 1회 후 종료 → 업로드 정상 동작(서버 `server_call_history` 적재) 확인.

- [ ] **Step 5: 최종 커밋 (필요 시)**

검증 중 수정이 없었다면 추가 커밋 불필요. 수정이 있었다면 해당 변경을 커밋한다.

---

## Self-Review 결과

- **스펙 커버리지**: 감지(Task 2) / 차단 4곳(Task 2 루프 + Task 3 세 곳) / 알림(Task 1 markRevoked) / 복구(Task 4) / 오판방지(401 한정 + 전이 가드) / 테스트(Task 1 + Task 5) — 스펙 §5~§10 모두 대응됨.
- **플레이스홀더**: 없음. 모든 코드 단계에 실제 코드 포함.
- **타입 일관성**: `isRevoked`/`clearRevoked`/`markRevoked(:Boolean)` 시그니처가 Task 1 정의와 Task 2~4 호출에서 일치. `ResendWorker.UNIQUE_NAME` 기존 상수 재사용.
