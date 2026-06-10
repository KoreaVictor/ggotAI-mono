# 고객 번호·이름 수집 수정 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 통화 종료 후 `CallLog`를 조회해 고객 번호·연락처명을 확보, `customer_phone_number`/`customer_name`에 정확히 적재한다 (현재 `Unknown/신규` 버그 해결).

**Architecture:** 막다른 길인 `EXTRA_INCOMING_NUMBER`(Android 10+ 일반앱 null) 의존을 제거하고, `CallSyncWorker`가 `CallLogReader`로 최근 통화를 조회한다. 번호/이름 결정은 순수 함수 `CustomerResolver`(JVM 테스트)로 분리하고, ContentResolver 의존부(`CallLogReader`)는 실기기 E2E로 검증한다.

**Tech Stack:** Kotlin, Android `CallLog.Calls` ContentResolver, WorkManager, Room/Retrofit(기존). 빌드: `.\gradlew.bat` + Studio JBR.

---

## 환경 전제 (모든 명령 공통)

- 작업 디렉터리: `C:\ggotAIhp\android`. gradle 명령 전 `$env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"`.
- adb: `C:\Users\SAMSUNG\AppData\Local\Android\Sdk\platform-tools\adb.exe`. 기기: Galaxy Note 10(SM-N971N), SIM `01058921670`(shop_key=19).
- 온디바이스 DB 검증: WAL 포함 `run-as ... cp <db>[-wal] /sdcard/x` → `adb pull` → PC python sqlite3.
- 서버 조회: `.env`의 `SUPABASE_ACCESS_TOKEN`으로 Management API `POST https://api.supabase.com/v1/projects/suylrznbctrkbxbleapb/database/query`.

---

## File Structure

| 파일 | 책임 | 변경 |
|------|------|------|
| `app/src/main/java/com/ggotai/hp/model/CallLogEntry.kt` | CallLog 1건 표현 data class | **신규** |
| `app/src/main/java/com/ggotai/hp/util/CustomerResolver.kt` | 번호/이름 결정 순수함수 | **신규** |
| `app/src/main/java/com/ggotai/hp/util/CallLogReader.kt` | CallLog 최근통화 조회 | **신규** |
| `app/src/main/java/com/ggotai/hp/worker/CallSyncWorker.kt` | number/name 결정 경로 교체 | 수정 |
| `app/src/main/java/com/ggotai/hp/receiver/CallReceiver.kt` | EXTRA_INCOMING_NUMBER 제거, 예약 단순화 | 수정 |
| `app/src/test/java/com/ggotai/hp/util/CustomerResolverTest.kt` | 순수함수 단위테스트 | **신규** |

---

## Task 1: CustomerResolver — 번호/이름 결정 (순수 함수, TDD)

**Files:**
- Create: `android/app/src/main/java/com/ggotai/hp/util/CustomerResolver.kt`
- Test: `android/app/src/test/java/com/ggotai/hp/util/CustomerResolverTest.kt`

- [ ] **Step 1: 실패 테스트 작성**

Create `android/app/src/test/java/com/ggotai/hp/util/CustomerResolverTest.kt`:
```kotlin
package com.ggotai.hp.util

import org.junit.Assert.assertEquals
import org.junit.Test

class CustomerResolverTest {

    @Test
    fun resolveNumber_validNumber_returnsIt() {
        assertEquals("01049534339", CustomerResolver.resolveNumber("01049534339"))
    }

    @Test
    fun resolveNumber_blankOrNull_returnsUnknown() {
        assertEquals("Unknown", CustomerResolver.resolveNumber(null))
        assertEquals("Unknown", CustomerResolver.resolveNumber(""))
        assertEquals("Unknown", CustomerResolver.resolveNumber("   "))
    }

    @Test
    fun resolveName_prefersCachedName() {
        assertEquals("여현동", CustomerResolver.resolveName("여현동", "주소록이름"))
    }

    @Test
    fun resolveName_fallsBackToContactName_whenCachedBlank() {
        assertEquals("주소록이름", CustomerResolver.resolveName(null, "주소록이름"))
        assertEquals("주소록이름", CustomerResolver.resolveName("", "주소록이름"))
    }

    @Test
    fun resolveName_defaultWhenNoneOrContactIsDefault() {
        assertEquals("신규", CustomerResolver.resolveName(null, null))
        assertEquals("신규", CustomerResolver.resolveName("", ""))
        // contactName이 이미 기본값 "신규"면 무시하고 "신규"
        assertEquals("신규", CustomerResolver.resolveName(null, "신규"))
    }
}
```

- [ ] **Step 2: 테스트 실패 확인**

Run:
```powershell
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"
.\gradlew.bat testDebugUnitTest --tests "com.ggotai.hp.util.CustomerResolverTest" --console=plain
```
Expected: FAIL — `Unresolved reference: CustomerResolver`.

- [ ] **Step 3: 구현**

Create `android/app/src/main/java/com/ggotai/hp/util/CustomerResolver.kt`:
```kotlin
package com.ggotai.hp.util

/** 통화 고객의 번호/이름을 결정하는 순수 로직. */
object CustomerResolver {
    const val UNKNOWN_NUMBER = "Unknown"
    const val DEFAULT_NAME = "신규"

    /** CallLog 번호가 비어있으면 "Unknown". */
    fun resolveNumber(callLogNumber: String?): String =
        callLogNumber?.takeIf { it.isNotBlank() } ?: UNKNOWN_NUMBER

    /** CallLog 캐시명 → (번호로 조회한) 주소록명 → "신규" 순. */
    fun resolveName(cachedName: String?, contactName: String?): String =
        cachedName?.takeIf { it.isNotBlank() }
            ?: contactName?.takeIf { it.isNotBlank() && it != DEFAULT_NAME }
            ?: DEFAULT_NAME
}
```

- [ ] **Step 4: 테스트 통과 확인**

Run:
```powershell
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"
.\gradlew.bat testDebugUnitTest --tests "com.ggotai.hp.util.CustomerResolverTest" --console=plain
```
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```powershell
git add android/app/src/main/java/com/ggotai/hp/util/CustomerResolver.kt android/app/src/test/java/com/ggotai/hp/util/CustomerResolverTest.kt
git commit -m "feat: 고객 번호/이름 결정 순수로직 CustomerResolver 추가`n`nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: CallLogEntry + CallLogReader — 최근 통화 조회

**Files:**
- Create: `android/app/src/main/java/com/ggotai/hp/model/CallLogEntry.kt`
- Create: `android/app/src/main/java/com/ggotai/hp/util/CallLogReader.kt`

ContentResolver/CallLog 의존이라 JVM 단위테스트 불가 → 컴파일 확인 + Task 5 실기기 E2E로 검증.

- [ ] **Step 1: CallLogEntry 작성**

Create `android/app/src/main/java/com/ggotai/hp/model/CallLogEntry.kt`:
```kotlin
package com.ggotai.hp.model

/** CallLog.Calls 한 행의 필요한 필드. */
data class CallLogEntry(
    val number: String?,
    val cachedName: String?,
    val type: Int,
    val dateMillis: Long,
    val durationSec: Int
)
```

- [ ] **Step 2: CallLogReader 작성**

Create `android/app/src/main/java/com/ggotai/hp/util/CallLogReader.kt`:
```kotlin
package com.ggotai.hp.util

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.provider.CallLog
import android.util.Log
import androidx.core.content.ContextCompat
import com.ggotai.hp.model.CallLogEntry

/** 통화 종료 직후 가장 최근 통화기록을 조회한다. */
object CallLogReader {
    private const val TAG = "CallLogReader"
    private const val MAX_AGE_MS = 10 * 60 * 1000L // 최근 10분 이내만 유효

    /**
     * 최근 통화 1건을 반환한다.
     * 권한 없음 / 기록 없음 / 10분 초과(오래된 통화) → null.
     */
    fun latestCall(context: Context): CallLogEntry? {
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.READ_CALL_LOG)
            != PackageManager.PERMISSION_GRANTED
        ) {
            Log.w(TAG, "READ_CALL_LOG 미승인 — CallLog 조회 생략")
            return null
        }

        val projection = arrayOf(
            CallLog.Calls.NUMBER,
            CallLog.Calls.CACHED_NAME,
            CallLog.Calls.TYPE,
            CallLog.Calls.DATE,
            CallLog.Calls.DURATION
        )

        return try {
            context.contentResolver.query(
                CallLog.Calls.CONTENT_URI,
                projection,
                null,
                null,
                "${CallLog.Calls.DATE} DESC"
            )?.use { cursor ->
                if (!cursor.moveToFirst()) return null
                val number = cursor.getString(cursor.getColumnIndexOrThrow(CallLog.Calls.NUMBER))
                val cachedName = cursor.getString(cursor.getColumnIndexOrThrow(CallLog.Calls.CACHED_NAME))
                val type = cursor.getInt(cursor.getColumnIndexOrThrow(CallLog.Calls.TYPE))
                val dateMillis = cursor.getLong(cursor.getColumnIndexOrThrow(CallLog.Calls.DATE))
                val durationSec = cursor.getInt(cursor.getColumnIndexOrThrow(CallLog.Calls.DURATION))

                if (System.currentTimeMillis() - dateMillis > MAX_AGE_MS) {
                    Log.w(TAG, "최근 통화가 10분 초과 — 매칭 생략")
                    null
                } else {
                    Log.d(TAG, "CallLog 최근통화: number=$number name=$cachedName type=$type dur=$durationSec")
                    CallLogEntry(number, cachedName, type, dateMillis, durationSec)
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "CallLog 조회 실패", e)
            null
        }
    }
}
```

- [ ] **Step 3: 컴파일 확인**

Run:
```powershell
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"
.\gradlew.bat compileDebugKotlin --console=plain
```
Expected: `BUILD SUCCESSFUL`.

- [ ] **Step 4: Commit**

```powershell
git add android/app/src/main/java/com/ggotai/hp/model/CallLogEntry.kt android/app/src/main/java/com/ggotai/hp/util/CallLogReader.kt
git commit -m "feat: CallLog 최근통화 조회 CallLogReader/CallLogEntry 추가`n`nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: CallSyncWorker — number/name 결정 경로 교체

**Files:**
- Modify: `android/app/src/main/java/com/ggotai/hp/worker/CallSyncWorker.kt`

현재 `customerNumber`(워커 입력)와 `getContactName(customerNumber)`로 이름을 정한다. 이를 CallLog 기반으로 교체한다.

- [ ] **Step 1: import 추가**

`CallSyncWorker.kt` 상단 import 블록에 추가:
```kotlin
import com.ggotai.hp.util.CallLogReader
import com.ggotai.hp.util.CustomerResolver
```

- [ ] **Step 2: doWork 내 번호/이름 결정부 교체**

`doWork()`에서 현재 아래 블록:
```kotlin
        val customerNumber = inputData.getString(KEY_CUSTOMER_NUMBER) ?: "Unknown"
        Log.d(TAG, "CallSyncWorker 시작 - 대상 번호: $customerNumber")
```
을 다음으로 교체:
```kotlin
        // CallLog에서 가장 최근 통화 번호/연락처명 확보 (EXTRA_INCOMING_NUMBER는 Android 10+ 일반앱에 null)
        val callLog = CallLogReader.latestCall(context)
        val customerNumber = CustomerResolver.resolveNumber(callLog?.number)
        Log.d(TAG, "CallSyncWorker 시작 - 대상 번호: $customerNumber (CallLog name=${callLog?.cachedName})")
```

그리고 같은 함수 안의 이름 결정부:
```kotlin
            val matchedName = getContactName(context, customerNumber)
```
을 다음으로 교체:
```kotlin
            val contactName = if (customerNumber != CustomerResolver.UNKNOWN_NUMBER) {
                getContactName(context, customerNumber)
            } else null
            val matchedName = CustomerResolver.resolveName(callLog?.cachedName, contactName)
```

- [ ] **Step 3: 컴파일 확인**

Run:
```powershell
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"
.\gradlew.bat compileDebugKotlin --console=plain
```
Expected: `BUILD SUCCESSFUL`. (※ `getContactName`이 매칭 실패 시 `"신규"`를 반환하므로 `resolveName`의 contactName 인자로 `"신규"`가 들어올 수 있고, `resolveName`은 이를 무시하도록 이미 처리됨.)

- [ ] **Step 4: Commit**

```powershell
git add android/app/src/main/java/com/ggotai/hp/worker/CallSyncWorker.kt
git commit -m "feat: CallSyncWorker가 CallLog로 고객 번호/이름 확보`n`nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: CallReceiver — EXTRA_INCOMING_NUMBER 제거, 예약 단순화

**Files:**
- Modify: `android/app/src/main/java/com/ggotai/hp/receiver/CallReceiver.kt`

번호는 이제 워커가 CallLog로 확보하므로, 무용지물인 `savedNumber`/`EXTRA_INCOMING_NUMBER` 추출과 워커 입력 번호를 제거한다.

- [ ] **Step 1: onReceive에서 번호 추출 제거**

`onReceive`의 다음 블록:
```kotlin
            val stateStr = intent.extras?.getString(TelephonyManager.EXTRA_STATE)
            val number = intent.extras?.getString(TelephonyManager.EXTRA_INCOMING_NUMBER)
            
            if (number != null && number.isNotEmpty()) {
                savedNumber = number
            }

            var state = 0
```
을 다음으로 교체:
```kotlin
            val stateStr = intent.extras?.getString(TelephonyManager.EXTRA_STATE)

            var state = 0
```

- [ ] **Step 2: onCallStateChanged 시그니처/호출 단순화**

`onReceive` 끝의 호출:
```kotlin
            onCallStateChanged(context, state, savedNumber)
```
을:
```kotlin
            onCallStateChanged(context, state)
```

`onCallStateChanged` 함수를 다음으로 교체:
```kotlin
    private fun onCallStateChanged(context: Context, state: Int) {
        if (lastState == TelephonyManager.CALL_STATE_IDLE && state == TelephonyManager.CALL_STATE_RINGING) {
            // Incoming call ringing
        } else if (lastState == TelephonyManager.CALL_STATE_RINGING && state == TelephonyManager.CALL_STATE_OFFHOOK) {
            // Incoming call answered
        } else if (lastState == TelephonyManager.CALL_STATE_IDLE && state == TelephonyManager.CALL_STATE_OFFHOOK) {
            // Outgoing call started
        } else if (state == TelephonyManager.CALL_STATE_IDLE) {
            // Call ended (either incoming or outgoing)
            if (lastState == TelephonyManager.CALL_STATE_OFFHOOK) {
                // 통화가 방금 끝났으므로 파일 스캔 워커 예약 (번호는 워커가 CallLog로 확보)
                scheduleCallSyncWork(context)
            }
        }

        lastState = state
    }
```

- [ ] **Step 3: savedNumber 필드 제거 + scheduleCallSyncWork 단순화**

companion object에서 `private var savedNumber: String? = null` 줄을 삭제.

`scheduleCallSyncWork` 함수를 다음으로 교체:
```kotlin
    private fun scheduleCallSyncWork(context: Context) {
        Log.d(TAG, "Scheduling call sync work via WorkManager")

        val workRequest = OneTimeWorkRequestBuilder<CallSyncWorker>()
            .setInitialDelay(8, TimeUnit.SECONDS) // 파일 쓰기/CallLog 기록 시간을 고려
            .build()

        WorkManager.getInstance(context).enqueue(workRequest)
    }
```

(미사용이 되는 `import androidx.work.Data` 및 사용 안 하는 `stateStrToInt`/`stateIntToStr`는 그대로 둬도 무방하나, `Data` import는 제거 가능.)

- [ ] **Step 4: CallSyncWorker의 미사용 입력키 제거**

`CallSyncWorker.kt`에서 더 이상 쓰지 않는 입력키 상수와 참조를 제거한다. companion object의:
```kotlin
        const val KEY_CUSTOMER_NUMBER = "CUSTOMER_NUMBER"
```
줄을 삭제. (Task 3에서 `inputData.getString(KEY_CUSTOMER_NUMBER)` 참조는 이미 제거됨.)

- [ ] **Step 5: 컴파일 확인**

Run:
```powershell
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"
.\gradlew.bat compileDebugKotlin --console=plain
```
Expected: `BUILD SUCCESSFUL`.

- [ ] **Step 6: Commit**

```powershell
git add android/app/src/main/java/com/ggotai/hp/receiver/CallReceiver.kt android/app/src/main/java/com/ggotai/hp/worker/CallSyncWorker.kt
git commit -m "refactor: CallReceiver의 EXTRA_INCOMING_NUMBER 의존 제거`n`nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: 전체 테스트 + 실기기 E2E 검증

**Files:** 없음 (검증)

- [ ] **Step 1: 전체 단위테스트 + APK 빌드**

Run:
```powershell
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"
.\gradlew.bat testDebugUnitTest assembleDebug --console=plain
```
Expected: PASS (CustomerResolverTest 포함) + `BUILD SUCCESSFUL`.

- [ ] **Step 2: 설치 + READ_CALL_LOG 승인**

```powershell
$adb = "C:\Users\SAMSUNG\AppData\Local\Android\Sdk\platform-tools\adb.exe"
& $adb install -r C:\ggotAIhp\android\app\build\outputs\apk\debug\app-debug.apk
& $adb shell pm grant com.ggotai.hp android.permission.READ_CALL_LOG
& $adb shell dumpsys package com.ggotai.hp | Select-String "READ_CALL_LOG: granted"
```
Expected: `Success`, `READ_CALL_LOG: granted=true`.

- [ ] **Step 3: baseline 기록**

```powershell
$token = "***REMOVED***"
$uri = "https://api.supabase.com/v1/projects/suylrznbctrkbxbleapb/database/query"
$headers = @{ Authorization = "Bearer $token"; "Content-Type" = "application/json" }
$body = @{ query = "SELECT max(id) AS max_id FROM server_call_history WHERE shop_key=19;" } | ConvertTo-Json
(Invoke-RestMethod -Uri $uri -Method POST -Headers $headers -Body $body) | ConvertTo-Json
```
기록: baseline `max_id`.

- [ ] **Step 4: 실통화 1건 (협업)**

`adb logcat -c` 후, 저장된 연락처(예: 여현동)와 ~10초 통화 후 종료. 약 8초 뒤 워커 실행.
```powershell
$adb = "C:\Users\SAMSUNG\AppData\Local\Android\Sdk\platform-tools\adb.exe"
& $adb logcat -d | Select-String "CallReceiver|CallLogReader|CallSyncWorker|UploadManager" | Select-Object -Last 15
```
Expected: `CallLogReader: CallLog 최근통화: number=... name=여현동`, `CallSyncWorker ... 대상 번호: 0104...`, `DB 저장 완료`, `Upload success`.

- [ ] **Step 5: 로컬 + 서버 적재 검증**

```powershell
$adb = "C:\Users\SAMSUNG\AppData\Local\Android\Sdk\platform-tools\adb.exe"
& $adb shell "run-as com.ggotai.hp cp /data/data/com.ggotai.hp/databases/ggotai_database /sdcard/_d3; run-as com.ggotai.hp cp /data/data/com.ggotai.hp/databases/ggotai_database-wal /sdcard/_d3-wal"
& $adb pull /sdcard/_d3 C:\ggotAIhp\_d3.bin | Out-Null
& $adb pull /sdcard/_d3-wal C:\ggotAIhp\_d3.bin-wal | Out-Null
$code = @"
import sqlite3
c = sqlite3.connect(r'C:\ggotAIhp\_d3.bin')
print(c.execute('SELECT id, phone_number, customer_name, transfer_status FROM call_history ORDER BY id DESC LIMIT 1').fetchone())
"@
$code | python -
$token = "***REMOVED***"
$uri = "https://api.supabase.com/v1/projects/suylrznbctrkbxbleapb/database/query"
$headers = @{ Authorization = "Bearer $token"; "Content-Type" = "application/json" }
$body = @{ query = "SELECT id, customer_phone_number, customer_name, duration_seconds FROM server_call_history WHERE shop_key=19 ORDER BY id DESC LIMIT 1;" } | ConvertTo-Json
(Invoke-RestMethod -Uri $uri -Method POST -Headers $headers -Body $body) | ConvertTo-Json
```
Expected: 로컬 최신 행 `phone_number=01049534339, customer_name=여현동, 성공`; 서버 신규 행(id > baseline) `customer_phone_number=01049534339, customer_name=여현동`.

- [ ] **Step 6: 임시파일 정리 + Task_List/문서 갱신 + Commit**

`C:\ggotAIhp\_d3.bin*` 삭제. `Task_List.md`에 4단계 하위로 "고객 번호·이름 수집 수정(CallLog) — 실기기 E2E 검증 완료" 한 줄 추가 후 커밋:
```powershell
git add Task_List.md
git commit -m "docs: 고객 번호·이름 수집(CallLog) 수정 검증 완료 반영`n`nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review 결과

- **Spec 커버리지:** CallLogEntry/CallLogReader → T2 · CustomerResolver(순수+테스트) → T1 · CallSyncWorker CallLog 경로 → T3 · CallReceiver EXTRA_INCOMING_NUMBER 제거 → T4 · 권한(기존 요청 유지, 워커 방어적 확인) → T2(CallLogReader 권한체크)+T5(grant) · 신규통화만/백필없음/파일명파싱없음 → 설계대로 미포함 · 테스트(JVM+E2E) → T1,T5. 모든 spec 항목 대응.
- **타입 일관성:** `CallLogEntry(number,cachedName,type,dateMillis,durationSec)`, `CustomerResolver.resolveNumber/resolveName/UNKNOWN_NUMBER/DEFAULT_NAME`, `CallLogReader.latestCall(context)` 명칭이 모든 태스크에서 일치.
- **Placeholder:** 없음(모든 코드/명령 구체화).
- **주의(실행자용):** T3에서 `getContactName`은 매칭 실패 시 `"신규"`를 반환 → `resolveName`이 `"신규"` contactName을 무시하도록 설계됨(이중 기본값 방지).
