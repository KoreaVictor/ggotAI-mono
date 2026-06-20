# 매장판매 음성수집 (가게음성) — 구현 계획 (Phase 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ggotAIhp에 "매장판매" 버튼을 추가해, 사장님이 음성으로 말한 주문을 인앱 녹음→`upload-call(channel_order='가게음성')`로 수집한다(STT/Gemini/RPA/상황판은 무변경).

**Architecture:** 핸드폰 채널의 `upload-call` 업로드 경로를 재사용하고 채널만 태깅한다(접근 ①). 안드로이드는 새 인앱 녹음 경로(`MediaRecorder`)를 추가하되, 산출물(오디오 파일 + `CallHistory`)을 만든 뒤부터는 기존 `UploadManager` 업로드/재전송을 그대로 쓴다. 서버 `upload-call`은 선택적 `channel_order`를 받아 채널별로 검증·INSERT한다.

**Tech Stack:** Kotlin/Android(Room, ViewBinding, MediaRecorder, Retrofit), Supabase Edge Function(Deno/TypeScript), 기존 백엔드 파이프라인(Python).

## Global Constraints

- Room 마이그레이션은 **데이터 보존**(파괴적 금지). 기존 통화 이력 무손상.
- `upload-call`의 `channel_order` 기본값은 `'핸드폰'`, 허용값 `핸드폰|가게음성`. 미전송/미허용 값이면 `'핸드폰'`로 폴백(기존 ggotAIhp 무손상).
- 매장판매: 발신번호 없음 → `customer_phone_number=''`. `customer_name='매장판매'`.
- 녹음 종료 임계값(상수): 무음 자동종료 5000ms, 최대 120000ms, 최소 유효 1500ms.
- 즉시 전송(확인 절차 없음). 성공 TTS "매장판매 주문이 접수되었습니다."
- 기존 통화녹음(삼성 파일 탐색) 흐름·`RecordingService`는 변경하지 않는다.
- 단일 매장·단일 작업자 전제(시스템 전반 가정과 동일): 같은 1초 내 서로 다른 매장판매 2건은 발생하지 않는다고 본다.
- Supabase 프로젝트 ref: `suylrznbctrkbxbleapb`. 토큰은 셸 env var `$SUPABASE_ACCESS_TOKEN`.

---

### Task 1: 서버 `upload-call`에 `channel_order` 지원

**Files:**
- Modify: `supabase/functions/upload-call/index.ts`

**Interfaces:**
- Produces: 멀티파트 입력에 `channel_order`(선택, `핸드폰|가게음성`, 기본 `핸드폰`). `가게음성`이면 `phone_number` 선택 허용, INSERT `channel_order='가게음성'`, `customer_phone_number=''`, `customer_name='매장판매'`(미전송 시).

- [ ] **Step 1: 채널 파싱 + 검증 분기 추가**

`index.ts`의 formData 파싱부(현재 line 18~25)를 아래로 교체한다. 기존 줄(`userPhoneNumber`~`audioFile`)은 유지하고 그 아래에 `channelOrder` 파싱을 추가한다.

```typescript
    const userPhoneNumber = formData.get("user_phone_number") as string;
    const phoneNumber = (formData.get("phone_number") as string) || "";
    const customerName = (formData.get("customer_name") as string) || "신규";
    const callDate = formData.get("call_date") as string;
    const callTime = formData.get("call_time") as string;
    const durationRaw = formData.get("duration_seconds");
    const durationSeconds = durationRaw ? parseInt(durationRaw as string) : null;
    const audioFile = formData.get("audio_file") as File | null;

    // 채널: 미전송/미허용 값이면 '핸드폰'(기존 ggotAIhp 무손상).
    const rawChannel = (formData.get("channel_order") as string) || "";
    const channelOrder = rawChannel === "가게음성" ? "가게음성" : "핸드폰";
    const isStoreSale = channelOrder === "가게음성";
```

- [ ] **Step 2: 필수 파라미터 검증을 채널별로 완화**

현재 검증(line 27)에서 `phoneNumber`를 무조건 요구한다. 매장판매는 발신번호가 없으므로, 핸드폰일 때만 요구하도록 교체한다.

```typescript
    // 핸드폰은 발신번호 필수, 매장판매(가게음성)는 발신번호 없음.
    const missingCore = !userPhoneNumber || !callDate || !callTime || !audioFile;
    if (missingCore || (!isStoreSale && !phoneNumber)) {
      return new Response(
        JSON.stringify({
          status: "error",
          error_code: "FILE_NOT_FOUND",
          message: "필수 파라미터가 누락됐습니다.",
        }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }
```

- [ ] **Step 3: INSERT에 채널 반영 + 매장판매 고객필드 처리**

INSERT 블록(현재 line 88~99)을 아래로 교체한다. 매장판매면 `customer_phone_number=''`, `customer_name`은 전송값 없으면 `'매장판매'`.

```typescript
    // 1단계: DB 먼저 적재 (Storage 업로드 전에 실행하여 고아 파일 방지)
    const insertCustomerName = isStoreSale
      ? ((formData.get("customer_name") as string) || "매장판매")
      : customerName;
    const { error: dbError } = await supabase.from("server_call_history").insert({
      channel_order: channelOrder,
      channel_classification: userPhoneNumber,
      shop_key: shop.shop_key,
      shop_name: shop.shop_name,
      customer_phone_number: phoneNumber, // 매장판매는 '' (빈값)
      customer_name: insertCustomerName,
      call_date: callDate,
      call_time: callTime,
      duration_seconds: durationSeconds,
      audio_file_name: fileName,
    });
```

> 참고: `fileName`(line 60)은 `${userPhoneNumber}_${phoneNumber}_${dateStr}_${timeStr}.wav`로, 매장판매면 `phoneNumber=''`라 `{user}__{date}_{time}.wav`가 된다(유효). 중복제거 pre-check(line 65~)도 `customer_phone_number=''`로 동작하며, 단일 작업자 전제에서 같은 1초 내 중복은 발생하지 않으므로 재전송 멱등성만 보장된다.

- [ ] **Step 4: 배포**

Run:
```bash
cd C:/ggotAI && supabase functions deploy upload-call --project-ref suylrznbctrkbxbleapb
```
Expected: `Deployed Function upload-call` 성공 메시지.

- [ ] **Step 5: 수동 검증(핸드폰 하위호환 + 매장판매)**

핸드폰(채널 미전송)은 기존대로 동작하고, 매장판매(가게음성)는 발신번호 없이 수집되는지 확인한다. 실제 기기번호(shop 19 = `01058921670`)와 작은 오디오 파일로 확인:

```bash
# (A) 매장판매: phone_number 없이, channel_order=가게음성
curl -i -X POST "https://suylrznbctrkbxbleapb.supabase.co/functions/v1/upload-call" \
  -H "Authorization: Bearer $SUPABASE_ACCESS_TOKEN" -H "apikey: $SUPABASE_ACCESS_TOKEN" \
  -F "user_phone_number=01058921670" -F "call_date=2026-06-20" -F "call_time=23:59:01" \
  -F "duration_seconds=7" -F "channel_order=가게음성" -F "audio_file=@/c/ggotAI/ggotAIya_settings_preview.png;type=audio/wav"
```
Expected: `HTTP/1.1 200` + `{"status":"success",...}`. 이후 Management API로 행 확인:
```bash
# server_call_history에 channel_order='가게음성', customer_phone_number='' 행 생성 확인 (zsh/bash)
# (mcp 또는 PowerShell Invoke-Sb 헬퍼로 SELECT) — 아래 SQL 사용
# select channel_order, customer_phone_number, customer_name from server_call_history
#   where shop_key=19 and call_time='23:59:01';
```
검증 후 만든 테스트 행은 삭제한다(`delete from server_call_history where shop_key=19 and call_time='23:59:01';`).

> 주의: edge function용 Deno 테스트 하니스가 저장소에 없어 자동 단위테스트 대신 위 수동 검증으로 대신한다.

---

### Task 2: `CallHistory.channelOrder` 컬럼 + Room v3→v4 마이그레이션

**Files:**
- Modify: `ggotAIhp/android/app/src/main/java/com/ggotai/hp/db/CallHistory.kt`
- Modify: `ggotAIhp/android/app/src/main/java/com/ggotai/hp/db/AppDatabase.kt`

**Interfaces:**
- Produces: `CallHistory.channelOrder: String`(컬럼 `channel_order`, 기본 `"핸드폰"`). DB 버전 4 + `MIGRATION_3_4`.

- [ ] **Step 1: 엔티티에 channelOrder 컬럼 추가**

`CallHistory.kt`의 `callType` 줄 바로 아래에 추가한다.

```kotlin
    // 통화 종류: Android CallLog.Calls.TYPE 값 (1=수신, 2=발신, 3=부재중 …). 레거시 행은 null.
    @ColumnInfo(name = "call_type") val callType: Int? = null,
    // 수집 채널: '핸드폰'(통화녹음, 기본) / '가게음성'(매장판매 인앱 녹음).
    @ColumnInfo(name = "channel_order") val channelOrder: String = "핸드폰",
```

- [ ] **Step 2: DB 버전 4 + 마이그레이션 등록**

`AppDatabase.kt`에서 (a) `version = 3` → `version = 4`, (b) `MIGRATION_2_3` 아래에 `MIGRATION_3_4` 추가, (c) `addMigrations(...)`에 등록.

```kotlin
@Database(entities = [CallHistory::class], version = 4, exportSchema = false)
```
```kotlin
        /** v3 → v4: channel_order 컬럼 추가 (매장판매=가게음성 구분, 기존 행은 '핸드폰'). */
        val MIGRATION_3_4 = object : Migration(3, 4) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("ALTER TABLE call_history ADD COLUMN channel_order TEXT NOT NULL DEFAULT '핸드폰'")
            }
        }
```
```kotlin
                    .addMigrations(MIGRATION_1_2, MIGRATION_2_3, MIGRATION_3_4)
```

- [ ] **Step 3: 빌드로 스키마 정합성 확인**

Run:
```bash
cd C:/ggotAI/ggotAIhp/android && ./gradlew.bat :app:assembleDebug
```
Expected: BUILD SUCCESSFUL (Room 스키마/엔티티 불일치 컴파일 에러 없음).

- [ ] **Step 4: Commit**

```bash
cd C:/ggotAI && git add ggotAIhp/android/app/src/main/java/com/ggotai/hp/db/CallHistory.kt ggotAIhp/android/app/src/main/java/com/ggotai/hp/db/AppDatabase.kt
git commit -m "feat(hp): CallHistory.channel_order 컬럼 + Room v3→v4 마이그레이션"
```

---

### Task 3: 업로드 경로에 `channel_order` 전달

**Files:**
- Modify: `ggotAIhp/android/app/src/main/java/com/ggotai/hp/api/ApiService.kt:56-66`
- Modify: `ggotAIhp/android/app/src/main/java/com/ggotai/hp/manager/UploadManager.kt:151-164`

**Interfaces:**
- Consumes: `CallHistory.channelOrder`(Task 2).
- Produces: `uploadCall(...)`에 `@Part("channel_order")` 추가. `uploadOnce`가 `history.channelOrder`를 전송.

- [ ] **Step 1: ApiService.uploadCall에 channel_order 파트 추가**

`uploadCall` 시그니처(현재 line 58~66)를 교체한다.

```kotlin
    @retrofit2.http.Multipart
    @retrofit2.http.POST("upload-call")
    suspend fun uploadCall(
        @retrofit2.http.Part("user_phone_number") userPhoneNumber: okhttp3.RequestBody,
        @retrofit2.http.Part("phone_number") phoneNumber: okhttp3.RequestBody,
        @retrofit2.http.Part("customer_name") customerName: okhttp3.RequestBody,
        @retrofit2.http.Part("call_date") callDate: okhttp3.RequestBody,
        @retrofit2.http.Part("call_time") callTime: okhttp3.RequestBody,
        @retrofit2.http.Part("duration_seconds") durationSeconds: okhttp3.RequestBody,
        @retrofit2.http.Part("channel_order") channelOrder: okhttp3.RequestBody,
        @retrofit2.http.Part audioFile: okhttp3.MultipartBody.Part
    ): Response<UploadCallResponse>
```

- [ ] **Step 2: UploadManager.uploadOnce에서 channel_order 전송**

`uploadOnce`의 멀티파트 구성부(현재 line 152~164)를 교체한다. `durationRb` 아래에 `channelRb`를 만들고 호출 인자에 추가한다.

```kotlin
            val userPhoneRb = history.userPhoneNumber.toRequestBody("text/plain".toMediaTypeOrNull())
            val phoneRb = history.phoneNumber.toRequestBody("text/plain".toMediaTypeOrNull())
            val nameRb = history.customerName.toRequestBody("text/plain".toMediaTypeOrNull())
            val dateRb = history.callDate.toRequestBody("text/plain".toMediaTypeOrNull())
            val timeRb = history.callTime.toRequestBody("text/plain".toMediaTypeOrNull())
            val durationRb = (history.durationSeconds?.toString() ?: "0").toRequestBody("text/plain".toMediaTypeOrNull())
            val channelRb = history.channelOrder.toRequestBody("text/plain".toMediaTypeOrNull())

            val reqFile = file.asRequestBody("audio/mpeg".toMediaTypeOrNull())
            val audioPart = MultipartBody.Part.createFormData("audio_file", file.name, reqFile)

            val response = RetrofitClient.instance.uploadCall(
                userPhoneRb, phoneRb, nameRb, dateRb, timeRb, durationRb, channelRb, audioPart
            )
```

- [ ] **Step 3: 빌드 확인**

Run:
```bash
cd C:/ggotAI/ggotAIhp/android && ./gradlew.bat :app:assembleDebug
```
Expected: BUILD SUCCESSFUL.

- [ ] **Step 4: Commit**

```bash
cd C:/ggotAI && git add ggotAIhp/android/app/src/main/java/com/ggotai/hp/api/ApiService.kt ggotAIhp/android/app/src/main/java/com/ggotai/hp/manager/UploadManager.kt
git commit -m "feat(hp): upload-call 멀티파트에 channel_order 전송"
```

---

### Task 4: `RecordingStopDecider` 순수 종료판정 + 단위테스트 (TDD)

**Files:**
- Create: `ggotAIhp/android/app/src/main/java/com/ggotai/hp/recorder/RecordingStopDecider.kt`
- Test: `ggotAIhp/android/app/src/test/java/com/ggotai/hp/recorder/RecordingStopDeciderTest.kt`

**Interfaces:**
- Produces: `RecordingStopDecider.decide(elapsedMs, silenceMs): StopReason?`, `isSendable(elapsedMs, hadSpeech): Boolean`, 상수 `SILENCE_TIMEOUT_MS=5000`, `MAX_DURATION_MS=120000`, `MIN_VALID_MS=1500`, `SILENCE_AMPLITUDE_THRESHOLD=1500`. `enum StopReason { MANUAL, SILENCE, MAX_DURATION }`.

- [ ] **Step 1: 실패하는 테스트 작성**

```kotlin
package com.ggotai.hp.recorder

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class RecordingStopDeciderTest {
    private val d = RecordingStopDecider

    @Test fun `진행중이면 종료하지 않는다`() {
        assertNull(d.decide(elapsedMs = 3000, silenceMs = 1000))
    }

    @Test fun `무음 5초면 SILENCE 종료`() {
        assertEquals(StopReason.SILENCE, d.decide(elapsedMs = 9000, silenceMs = 5000))
    }

    @Test fun `최대 2분이면 MAX_DURATION 종료`() {
        assertEquals(StopReason.MAX_DURATION, d.decide(elapsedMs = 120000, silenceMs = 0))
    }

    @Test fun `최대길이가 무음보다 우선한다`() {
        assertEquals(StopReason.MAX_DURATION, d.decide(elapsedMs = 120000, silenceMs = 5000))
    }

    @Test fun `짧거나 발화 없으면 전송 불가`() {
        assertFalse(d.isSendable(elapsedMs = 1000, hadSpeech = true))   // 너무 짧음
        assertFalse(d.isSendable(elapsedMs = 8000, hadSpeech = false))  // 발화 없음
    }

    @Test fun `충분히 길고 발화 있으면 전송 가능`() {
        assertTrue(d.isSendable(elapsedMs = 8000, hadSpeech = true))
    }
}
```

- [ ] **Step 2: 테스트 실패 확인**

Run:
```bash
cd C:/ggotAI/ggotAIhp/android && ./gradlew.bat :app:testDebugUnitTest --tests "com.ggotai.hp.recorder.RecordingStopDeciderTest"
```
Expected: FAIL (RecordingStopDecider/StopReason 미정의 컴파일 에러).

- [ ] **Step 3: 최소 구현 작성**

```kotlin
package com.ggotai.hp.recorder

/** 녹음 자동종료 사유. MANUAL은 사용자가 직접 종료(판정 대상 아님). */
enum class StopReason { MANUAL, SILENCE, MAX_DURATION }

/**
 * 녹음 종료/전송 가부를 시간·무음 정보만으로 판정하는 순수 로직.
 * 안드로이드 API에 의존하지 않아 JVM 단위테스트로 검증한다.
 */
object RecordingStopDecider {
    const val SILENCE_TIMEOUT_MS = 5000L      // 무음 지속 5초 → 자동종료
    const val MAX_DURATION_MS = 120000L       // 최대 2분 → 자동종료
    const val MIN_VALID_MS = 1500L            // 1.5초 미만은 전송 안 함
    const val SILENCE_AMPLITUDE_THRESHOLD = 1500 // getMaxAmplitude(0..32767) 무음 임계

    /** 지금 자동종료해야 하면 사유, 아니면 null. 최대길이가 무음보다 우선. */
    fun decide(elapsedMs: Long, silenceMs: Long): StopReason? = when {
        elapsedMs >= MAX_DURATION_MS -> StopReason.MAX_DURATION
        silenceMs >= SILENCE_TIMEOUT_MS -> StopReason.SILENCE
        else -> null
    }

    /** 녹음 결과를 서버로 보낼 가치가 있는지(너무 짧거나 발화 없으면 false). */
    fun isSendable(elapsedMs: Long, hadSpeech: Boolean): Boolean =
        elapsedMs >= MIN_VALID_MS && hadSpeech
}
```

- [ ] **Step 4: 테스트 통과 확인**

Run:
```bash
cd C:/ggotAI/ggotAIhp/android && ./gradlew.bat :app:testDebugUnitTest --tests "com.ggotai.hp.recorder.RecordingStopDeciderTest"
```
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
cd C:/ggotAI && git add ggotAIhp/android/app/src/main/java/com/ggotai/hp/recorder/RecordingStopDecider.kt ggotAIhp/android/app/src/test/java/com/ggotai/hp/recorder/RecordingStopDeciderTest.kt
git commit -m "feat(hp): 매장판매 녹음 종료판정 RecordingStopDecider + 단위테스트"
```

---

### Task 5: `StoreSaleRecorder` — MediaRecorder 래퍼

**Files:**
- Create: `ggotAIhp/android/app/src/main/java/com/ggotai/hp/recorder/StoreSaleRecorder.kt`

**Interfaces:**
- Consumes: `RecordingStopDecider`(Task 4).
- Produces: `StoreSaleRecorder(context)`; `start(onAutoStop: (StopReason) -> Unit): Boolean`(파일 생성·녹음 시작, 진폭 폴링으로 무음/최대길이 자동종료 콜백); `stop(): Result?` where `data class Result(val file: File, val elapsedMs: Long, val hadSpeech: Boolean)`; `cancel()`. 파일은 `context.filesDir/store_sale/store_{millis}.m4a`.

- [ ] **Step 1: 구현 작성**

```kotlin
package com.ggotai.hp.recorder

import android.content.Context
import android.media.MediaRecorder
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.util.Log
import java.io.File

/**
 * 매장판매 인앱 음성 녹음기. MediaRecorder(AAC/.m4a)로 녹음하며 200ms 주기로 진폭을 폴링해
 * 무음 지속/최대 길이에 도달하면 자동종료 콜백을 부른다. 종료 판정 자체는 RecordingStopDecider.
 */
class StoreSaleRecorder(private val context: Context) {

    data class Result(val file: File, val elapsedMs: Long, val hadSpeech: Boolean)

    companion object { private const val TAG = "StoreSaleRecorder"; private const val POLL_MS = 200L }

    private var recorder: MediaRecorder? = null
    private var outFile: File? = null
    private var startedAt = 0L
    private var lastSpeechAt = 0L
    private var hadSpeech = false
    private val handler = Handler(Looper.getMainLooper())
    private var onAutoStop: ((StopReason) -> Unit)? = null

    /** 녹음 시작. 성공 true. (호출 전 RECORD_AUDIO 권한이 있어야 함) */
    fun start(onAutoStop: (StopReason) -> Unit): Boolean {
        this.onAutoStop = onAutoStop
        val dir = File(context.filesDir, "store_sale").apply { mkdirs() }
        val file = File(dir, "store_${System.currentTimeMillis()}.m4a")
        outFile = file
        val rec = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) MediaRecorder(context) else @Suppress("DEPRECATION") MediaRecorder()
        return try {
            rec.setAudioSource(MediaRecorder.AudioSource.MIC)
            rec.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
            rec.setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
            rec.setAudioEncodingBitRate(96000)
            rec.setAudioSamplingRate(44100)
            rec.setOutputFile(file.absolutePath)
            rec.prepare()
            rec.start()
            recorder = rec
            startedAt = SystemClock.elapsedRealtime()
            lastSpeechAt = startedAt
            hadSpeech = false
            handler.postDelayed(pollRunnable, POLL_MS)
            true
        } catch (e: Exception) {
            Log.e(TAG, "녹음 시작 실패", e)
            runCatching { rec.release() }
            recorder = null
            false
        }
    }

    private val pollRunnable = object : Runnable {
        override fun run() {
            val rec = recorder ?: return
            val now = SystemClock.elapsedRealtime()
            val amp = runCatching { rec.maxAmplitude }.getOrDefault(0)
            if (amp >= RecordingStopDecider.SILENCE_AMPLITUDE_THRESHOLD) {
                hadSpeech = true
                lastSpeechAt = now
            }
            val elapsed = now - startedAt
            val silence = now - lastSpeechAt
            val reason = RecordingStopDecider.decide(elapsed, silence)
            if (reason != null) {
                onAutoStop?.invoke(reason)
                return
            }
            handler.postDelayed(this, POLL_MS)
        }
    }

    /** 녹음 종료. 결과(파일/경과/발화여부) 반환, 실패 시 null. */
    fun stop(): Result? {
        handler.removeCallbacks(pollRunnable)
        val rec = recorder ?: return null
        val file = outFile ?: return null
        val elapsed = SystemClock.elapsedRealtime() - startedAt
        recorder = null
        return try {
            rec.stop(); rec.release()
            Result(file, elapsed, hadSpeech)
        } catch (e: Exception) {
            Log.e(TAG, "녹음 종료 실패", e)
            runCatching { rec.release() }
            runCatching { file.delete() }
            null
        }
    }

    /** 취소: 녹음 폐기 + 파일 삭제. */
    fun cancel() {
        handler.removeCallbacks(pollRunnable)
        recorder?.let { runCatching { it.stop() }; runCatching { it.release() } }
        recorder = null
        outFile?.let { runCatching { it.delete() } }
    }
}
```

- [ ] **Step 2: 빌드 확인**

Run:
```bash
cd C:/ggotAI/ggotAIhp/android && ./gradlew.bat :app:assembleDebug
```
Expected: BUILD SUCCESSFUL.

- [ ] **Step 3: Commit**

```bash
cd C:/ggotAI && git add ggotAIhp/android/app/src/main/java/com/ggotai/hp/recorder/StoreSaleRecorder.kt
git commit -m "feat(hp): 매장판매 인앱 녹음기 StoreSaleRecorder(MediaRecorder)"
```

---

### Task 6: 녹음 화면 `StoreSaleActivity` + 권한 + 업로드 연결

**Files:**
- Create: `ggotAIhp/android/app/src/main/java/com/ggotai/hp/StoreSaleActivity.kt`
- Create: `ggotAIhp/android/app/src/main/res/layout/activity_store_sale.xml`
- Modify: `ggotAIhp/android/app/src/main/java/com/ggotai/hp/manager/UploadManager.kt` (성공 TTS 메시지 옵션)
- Modify: `ggotAIhp/android/app/src/main/AndroidManifest.xml` (액티비티 등록)

**Interfaces:**
- Consumes: `StoreSaleRecorder`(Task 5), `RecordingStopDecider.isSendable`(Task 4), `UploadManager.uploadCallHistory`(아래 확장), `CallHistory.channelOrder`(Task 2).
- Produces: `StoreSaleActivity`(매장판매 녹음→`CallHistory(channelOrder='가게음성')` insert→업로드). `UploadManager.uploadCallHistory(context, historyId, successMessage: String? = null)`.

- [ ] **Step 1: UploadManager.uploadCallHistory에 성공 TTS 옵션 추가**

성공 시 안내가 필요한 호출자(매장판매)를 위해 시그니처에 `successMessage`를 추가한다. 통화 경로 호출(`RecordingService`)은 기본값 null이라 무변경. `uploadCallHistory`의 시그니처와, 성공으로 끝나는 분기를 수정한다.

시그니처(현재 line 69):
```kotlin
    suspend fun uploadCallHistory(context: Context, historyId: Int, successMessage: String? = null) {
```
재시도 루프 직후, 실패 처리(`if (!success) { ... }`) 블록 **앞**에 성공 안내를 추가한다(현재 line 108~109 사이):
```kotlin
            if (success && successMessage != null) {
                speakOrQueue(successMessage, "StoreSaleSuccess")
            }

            if (!success) {
```

- [ ] **Step 2: 녹음 화면 레이아웃 작성**

`res/layout/activity_store_sale.xml`:
```xml
<?xml version="1.0" encoding="utf-8"?>
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="match_parent"
    android:layout_height="match_parent"
    android:orientation="vertical"
    android:gravity="center"
    android:padding="24dp">

    <TextView
        android:id="@+id/tvStatus"
        android:layout_width="wrap_content"
        android:layout_height="wrap_content"
        android:text="● 녹음 중"
        android:textColor="#D32F2F"
        android:textSize="28sp"
        android:textStyle="bold" />

    <TextView
        android:id="@+id/tvTimer"
        android:layout_width="wrap_content"
        android:layout_height="wrap_content"
        android:layout_marginTop="8dp"
        android:text="00:00"
        android:textSize="40sp" />

    <TextView
        android:layout_width="wrap_content"
        android:layout_height="wrap_content"
        android:layout_marginTop="16dp"
        android:text="주문 내용을 말씀하세요. 끝나면 '전송'을 누르세요.\n(말이 끝나고 잠시 기다리면 자동 전송됩니다)"
        android:gravity="center"
        android:textSize="16sp" />

    <Button
        android:id="@+id/btnStop"
        android:layout_width="match_parent"
        android:layout_height="64dp"
        android:layout_marginTop="32dp"
        android:text="■ 전송"
        android:textSize="20sp" />

    <Button
        android:id="@+id/btnCancel"
        android:layout_width="match_parent"
        android:layout_height="56dp"
        android:layout_marginTop="12dp"
        android:text="취소"
        android:textSize="18sp" />
</LinearLayout>
```

- [ ] **Step 3: StoreSaleActivity 작성**

`StoreSaleActivity.kt`:
```kotlin
package com.ggotai.hp

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.ggotai.hp.databinding.ActivityStoreSaleBinding
import com.ggotai.hp.db.AppDatabase
import com.ggotai.hp.db.CallHistory
import com.ggotai.hp.manager.UploadManager
import com.ggotai.hp.recorder.RecordingStopDecider
import com.ggotai.hp.recorder.StoreSaleRecorder
import com.ggotai.hp.recorder.StopReason
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** 매장판매: 사장님 음성 주문을 인앱 녹음 → 가게음성 채널로 업로드. */
class StoreSaleActivity : AppCompatActivity() {

    private lateinit var binding: ActivityStoreSaleBinding
    private val recorder by lazy { StoreSaleRecorder(applicationContext) }
    private val handler = Handler(Looper.getMainLooper())
    private var startedAt = 0L
    private var finished = false

    private val permLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted -> if (granted) beginRecording() else denyAndExit() }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityStoreSaleBinding.inflate(layoutInflater)
        setContentView(binding.root)
        UploadManager.initTts(applicationContext)

        binding.btnStop.setOnClickListener { finishRecording(StopReason.MANUAL) }
        binding.btnCancel.setOnClickListener { recorder.cancel(); finish() }

        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO)
            == PackageManager.PERMISSION_GRANTED) {
            beginRecording()
        } else {
            permLauncher.launch(Manifest.permission.RECORD_AUDIO)
        }
    }

    private fun denyAndExit() {
        Toast.makeText(this, "마이크 권한이 필요합니다.", Toast.LENGTH_LONG).show()
        finish()
    }

    private fun beginRecording() {
        val ok = recorder.start { reason -> runOnUiThread { finishRecording(reason) } }
        if (!ok) { Toast.makeText(this, "녹음을 시작하지 못했습니다.", Toast.LENGTH_LONG).show(); finish(); return }
        startedAt = SystemClock.elapsedRealtime()
        handler.post(tick)
    }

    private val tick = object : Runnable {
        override fun run() {
            val s = (SystemClock.elapsedRealtime() - startedAt) / 1000
            binding.tvTimer.text = String.format(Locale.getDefault(), "%02d:%02d", s / 60, s % 60)
            handler.postDelayed(this, 500)
        }
    }

    private fun finishRecording(reason: StopReason) {
        if (finished) return
        finished = true
        handler.removeCallbacks(tick)
        val result = recorder.stop()
        if (result == null) { Toast.makeText(this, "녹음 저장에 실패했습니다.", Toast.LENGTH_LONG).show(); finish(); return }

        if (!RecordingStopDecider.isSendable(result.elapsedMs, result.hadSpeech)) {
            UploadManager.speak("녹음이 짧아 취소되었습니다.")
            Toast.makeText(this, "녹음이 짧아 취소되었습니다.", Toast.LENGTH_SHORT).show()
            result.file.delete()
            finish(); return
        }

        val prefs = getSharedPreferences("app_prefs", Context.MODE_PRIVATE)
        val userPhone = prefs.getString("USER_PHONE_NUMBER", "Unknown") ?: "Unknown"
        val now = Date()
        val history = CallHistory(
            userPhoneNumber = userPhone,
            callDate = SimpleDateFormat("yyyy-MM-dd", Locale.getDefault()).format(now),
            callTime = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(now),
            phoneNumber = "",
            customerName = "매장판매",
            transferStatus = "전송중",
            audioFileName = result.file.name,
            audioFilePath = result.file.absolutePath,
            durationSeconds = (result.elapsedMs / 1000).toInt(),
            callType = null,
            channelOrder = "가게음성",
            syncStatus = 0
        )
        Toast.makeText(this, "매장판매 주문을 전송합니다.", Toast.LENGTH_SHORT).show()
        lifecycleScope.launch {
            val id = withContext(Dispatchers.IO) {
                AppDatabase.getDatabase(applicationContext).callHistoryDao().insert(history).toInt()
            }
            UploadManager.uploadCallHistory(applicationContext, id, successMessage = "매장판매 주문이 접수되었습니다.")
            finish()
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        handler.removeCallbacks(tick)
    }
}
```

- [ ] **Step 4: 매니페스트에 액티비티 등록**

`AndroidManifest.xml`의 `SettingsActivity` 등록(line 40~42) 아래에 추가:
```xml
        <activity
            android:name=".StoreSaleActivity"
            android:exported="false" />
```

- [ ] **Step 5: 빌드 확인**

Run:
```bash
cd C:/ggotAI/ggotAIhp/android && ./gradlew.bat :app:assembleDebug
```
Expected: BUILD SUCCESSFUL (ViewBinding `ActivityStoreSaleBinding` 생성됨).

- [ ] **Step 6: Commit**

```bash
cd C:/ggotAI && git add ggotAIhp/android/app/src/main/java/com/ggotai/hp/StoreSaleActivity.kt ggotAIhp/android/app/src/main/res/layout/activity_store_sale.xml ggotAIhp/android/app/src/main/java/com/ggotai/hp/manager/UploadManager.kt ggotAIhp/android/app/src/main/AndroidManifest.xml
git commit -m "feat(hp): 매장판매 녹음 화면 StoreSaleActivity + 성공 TTS 옵션"
```

---

### Task 7: MainActivity "매장판매" 버튼

**Files:**
- Modify: `ggotAIhp/android/app/src/main/res/layout/activity_main.xml`
- Modify: `ggotAIhp/android/app/src/main/java/com/ggotai/hp/MainActivity.kt`

**Interfaces:**
- Consumes: `StoreSaleActivity`(Task 6).
- Produces: 메인 화면 "매장판매" 버튼 → `StoreSaleActivity` 실행.

- [ ] **Step 1: 레이아웃에 버튼 추가**

`activity_main.xml`에서 기존 헤더 영역(상점명 `tvShopName`/설정 `btnSettings` 근처)에 매장판매 버튼을 추가한다. 아래 요소를 `tvShopName`이 속한 컨테이너 내 적절한 위치(설정 버튼 옆)에 넣는다. (정확한 부모 컨테이너 id는 `activity_main.xml`을 열어 확인 후 동일 컨테이너에 배치.)
```xml
    <Button
        android:id="@+id/btnStoreSale"
        android:layout_width="wrap_content"
        android:layout_height="wrap_content"
        android:text="매장판매" />
```

- [ ] **Step 2: MainActivity에서 버튼 연결**

`onCreate`의 `binding.btnSettings.setOnClickListener { ... }` 블록(line 81~83) 아래에 추가한다.
```kotlin
        binding.btnStoreSale.setOnClickListener {
            startActivity(Intent(this, StoreSaleActivity::class.java))
        }
```

- [ ] **Step 3: 빌드 확인**

Run:
```bash
cd C:/ggotAI/ggotAIhp/android && ./gradlew.bat :app:assembleDebug
```
Expected: BUILD SUCCESSFUL.

- [ ] **Step 4: Commit**

```bash
cd C:/ggotAI && git add ggotAIhp/android/app/src/main/res/layout/activity_main.xml ggotAIhp/android/app/src/main/java/com/ggotai/hp/MainActivity.kt
git commit -m "feat(hp): 메인 화면 매장판매 버튼 → StoreSaleActivity"
```

---

### Task 8: 실기기 E2E 검증

**Files:** (없음 — 검증)

- [ ] **Step 1: 디버그 APK 설치**

Run:
```bash
cd C:/ggotAI/ggotAIhp/android && ./gradlew.bat :app:assembleDebug
"C:/Users/SAMSUNG/AppData/Local/Android/Sdk/platform-tools/adb.exe" -s R3CM90GYTWR install -r app/build/outputs/apk/debug/app-debug.apk
```
Expected: `Success`.

- [ ] **Step 2: 매장판매 녹음 흐름 확인**

기기에서: 앱 실행 → "매장판매" 탭 → (최초) 마이크 권한 허용 → 주문 음성 말하기 → "전송" 탭(또는 5초 무음 자동종료) → "매장판매 주문이 접수되었습니다" TTS 확인.

- [ ] **Step 3: 서버·상황판·RPA 반영 확인**

- Management API SELECT로 `server_call_history`에 `channel_order='가게음성'` 행 생성 확인(`customer_phone_number=''`).
- 백엔드 로그(`backend/logs/ggotaiorder.log`)에서 해당 id의 STT→추출→order_details 처리 확인.
- ggotAIya 상황판 `가게음성` 카드/피드에 표시 확인.
- (auto_submit 상태에 따라) FlowerNT3 '매장' 채널 입력 또는 ready 상태 확인.

- [ ] **Step 4: 무음 자동종료 + 짧은녹음 취소 확인**

- 말한 뒤 버튼을 누르지 않고 5초 기다리면 자동 전송되는지 확인.
- 아주 짧게(1초 미만) 또는 무음으로 끝내면 "녹음이 짧아 취소되었습니다" 후 전송 안 됨 확인.

- [ ] **Step 5: 핸드폰 채널 회귀 확인**

실제 통화 1건으로 기존 통화녹음 수집이 그대로 `channel_order='핸드폰'`으로 동작하는지 확인(하위호환).

---

## 자기 점검 결과

- **스펙 커버리지:** 버튼 진입(T7), 인앱 녹음·종료규칙(T4·T5·T6), 즉시전송·성공TTS(T6), 채널 태깅 서버(T1)·앱(T2·T3), 짧은녹음 취소(T4·T6), 권한(T6), 하류 무변경(검증 T8), 음성호출 제외(Phase 2) — 모두 태스크에 매핑됨.
- **플레이스홀더:** 없음(모든 코드 단계에 실제 코드 포함). 단 T7 Step1은 `activity_main.xml`의 정확한 부모 컨테이너 id를 실행 시 확인해 배치(레이아웃 구조 의존).
- **타입 일관성:** `channelOrder`(컬럼 `channel_order`), `RecordingStopDecider.decide/isSendable/StopReason`, `StoreSaleRecorder.Result(file,elapsedMs,hadSpeech)`, `uploadCallHistory(context,historyId,successMessage)` — 태스크 간 시그니처 일치.
