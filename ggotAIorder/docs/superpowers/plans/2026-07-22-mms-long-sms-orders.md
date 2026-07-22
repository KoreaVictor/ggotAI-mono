# 긴 문자(LMS/MMS) 주문 수집 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 70자를 넘겨 LMS(MMS)로 도착하는 문자 주문을 수집한다 — 현재는 통째로, 조용히 유실되고 있다.

**Architecture:** MMS 도착 방송(`WAP_PUSH_RECEIVED`)을 받아 5초 뒤 스캐너를 돌린다. 스캐너는 워터마크 이후 수신 MMS를 `content://mms`에서 훑어 본문을 꺼내 기존 `message_buffer`에 담는다. 버퍼에 담긴 뒤부터는 문자·카톡과 완전히 같은 길(3분 디바운스 → `upload-text` → 서버)을 쓴다. 앱 시작 시에도 스캔을 1회 돌려 앱이 죽어 있던 공백을 메운다(최대 6시간).

**Tech Stack:** Kotlin, Android SDK(ContentResolver / Telephony), Room, WorkManager, JUnit4

## Global Constraints

- 설계서: `ggotAIorder/docs/superpowers/specs/2026-07-22-mms-long-sms-orders-design.md`
- 프로젝트 루트: `C:\ggotAI`, 안드로이드 모듈: `ggotAIhp/android`
- 빌드/테스트 명령은 `ggotAIhp/android`에서 실행하며 `JAVA_HOME`이 Android Studio JBR이어야 한다:
  `JAVA_HOME="/c/Program Files/Android/Android Studio/jbr" ./gradlew ...`
- 따라잡기 상한: **6시간**. 첫 설치 시 과거 메시지 **0건**.
- 사진만 온 메시지: **주문 대화 진행 중일 때만** `"사진을 보냈습니다."` 한 줄.
- 스티키 판정은 기존 `MessageGroupDecider.STICKY_WINDOW_MILLIS`(10분)와 `MessageBufferDao.countRecentBySender`를 그대로 쓴다. 새로 만들지 않는다.
- 고객명은 기존 `ContactLookup.nameFor()` + `CustomerResolver.resolveName()`을 쓴다. 없으면 `"신규"`.
- 필터는 기존 `OrderTextFilter.shouldCollect()`를 쓴다. 새 키워드 정책을 만들지 않는다.
- 프레임워크 없이 판단 가능한 로직은 순수 함수로 분리해 단위테스트한다(`ContentResolver`를 정책에 들이지 않는다). 기존 `KakaoNotificationPolicy` / `MessageGroupDecider`가 같은 규칙을 따른다.
- Room 스키마 변경 없음. `MessageBuffer`를 그대로 쓴다.
- 커밋 메시지는 한국어, 본문에 "왜"를 적는다. 끝에 `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- 브랜치: `feature/kakao-sms-orders`

## File Structure

| 파일 | 책임 |
|---|---|
| `util/PhoneNumberNormalizer.kt` (신규) | 발신번호를 한 형태로 맞춘다. 순수 |
| `mms/MmsScanWindow.kt` (신규) | 조회 범위·다음 워터마크 계산. 순수 |
| `mms/MmsBodyAssembler.kt` (신규) | 파트 목록 → 버퍼에 담을 본문. 순수 |
| `mms/MmsScanner.kt` (신규) | `ContentResolver` 조회 → 필터 → 버퍼 적재 → 워터마크 전진 |
| `worker/MmsScanWorker.kt` (신규) | 지연 실행·재시도. `MmsScanner`를 부르기만 한다 |
| `receiver/MmsReceiver.kt` (신규) | MMS 도착 방송 수신 → 스캔 예약. 판단하지 않는다 |
| `AndroidManifest.xml` (수정) | `RECEIVE_MMS` 권한 + 리시버 등록 |
| `LoginActivity.kt` (수정) | 런타임 권한 목록에 `RECEIVE_MMS` |
| `MainActivity.kt` (수정) | 앱 시작 시 스캔 1회 |

순수 로직 3개(Task 1~3)를 먼저 세우고, 그것들을 조립하는 스캐너(Task 4), 그다음 배선(Task 5) 순서다.

---

### Task 1: 발신번호 정규화

MMS는 발신번호를 `+821049534339`로 주고 SMS는 `01049534339`로 준다. 같은 사람인데 묶음 키(`senderKey`)가 갈라지면 스티키가 먹지 않고 주문이 두 건으로 쪼개진다.

**Files:**
- Create: `ggotAIhp/android/app/src/main/java/com/ggotai/hp/util/PhoneNumberNormalizer.kt`
- Test: `ggotAIhp/android/app/src/test/java/com/ggotai/hp/util/PhoneNumberNormalizerTest.kt`

**Interfaces:**
- Consumes: 없음
- Produces: `PhoneNumberNormalizer.normalize(raw: String?): String`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`ggotAIhp/android/app/src/test/java/com/ggotai/hp/util/PhoneNumberNormalizerTest.kt`:

```kotlin
package com.ggotai.hp.util

import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * MMS 는 국제형(+82)으로, SMS 는 국내형(0)으로 발신번호를 준다. 같은 사람이 두 형태로
 * 들어오면 대화방이 갈라져 주문이 두 건으로 쪼개진다.
 */
class PhoneNumberNormalizerTest {

    @Test
    fun `국제형 82를 국내형 0으로 바꾼다`() {
        assertEquals("01049534339", PhoneNumberNormalizer.normalize("+821049534339"))
    }

    @Test
    fun `이미 국내형이면 그대로 둔다`() {
        assertEquals("01049534339", PhoneNumberNormalizer.normalize("01049534339"))
    }

    @Test
    fun `하이픈과 공백을 제거한다`() {
        assertEquals("01049534339", PhoneNumberNormalizer.normalize("010-4953-4339"))
        assertEquals("01049534339", PhoneNumberNormalizer.normalize(" 010 4953 4339 "))
    }

    @Test
    fun `82 뒤에 이미 0이 있으면 0을 덧붙이지 않는다`() {
        // 일부 통신사가 국제형에 국내 0을 남긴 채로 준다.
        assertEquals("01049534339", PhoneNumberNormalizer.normalize("+8201049534339"))
    }

    @Test
    fun `해외 번호는 손대지 않는다`() {
        assertEquals("+14155551234", PhoneNumberNormalizer.normalize("+1-415-555-1234"))
    }

    @Test
    fun `비어 있으면 빈 문자열`() {
        assertEquals("", PhoneNumberNormalizer.normalize(null))
        assertEquals("", PhoneNumberNormalizer.normalize(""))
        assertEquals("", PhoneNumberNormalizer.normalize("   "))
    }

    @Test
    fun `대표번호 같은 짧은 번호도 그대로 둔다`() {
        // OrderTextFilter 의 대량발송 차단이 이 형태를 보고 판단한다.
        assertEquals("15881234", PhoneNumberNormalizer.normalize("1588-1234"))
    }
}
```

- [ ] **Step 2: 실패를 확인한다**

Run:
```bash
cd /c/ggotAI/ggotAIhp/android && JAVA_HOME="/c/Program Files/Android/Android Studio/jbr" ./gradlew :app:testDebugUnitTest --tests "com.ggotai.hp.util.PhoneNumberNormalizerTest"
```
Expected: FAIL — `Unresolved reference: PhoneNumberNormalizer`

- [ ] **Step 3: 구현한다**

`ggotAIhp/android/app/src/main/java/com/ggotai/hp/util/PhoneNumberNormalizer.kt`:

```kotlin
package com.ggotai.hp.util

/**
 * 발신번호를 한 형태(국내형)로 맞춘다.
 *
 * MMS 는 `+821049534339`, SMS 는 `01049534339` 로 같은 사람을 다르게 알려준다.
 * 이 값이 대화방 키(sender_key)가 되므로, 맞춰두지 않으면 한 주문이 두 대화로
 * 갈라져 스티키가 먹지 않는다.
 *
 * 해외 번호는 국내 규칙을 적용할 수 없어 그대로 둔다 — 꽃 주문이 올 리 없고,
 * 잘못 바꾸면 오히려 다른 사람과 합쳐진다.
 */
object PhoneNumberNormalizer {

    fun normalize(raw: String?): String {
        val cleaned = raw?.trim().orEmpty().filter { it.isDigit() || it == '+' }
        if (cleaned.isEmpty()) return ""

        if (!cleaned.startsWith("+")) return cleaned
        if (!cleaned.startsWith("+82")) return cleaned

        val national = cleaned.removePrefix("+82")
        if (national.isEmpty()) return ""
        // 국제형은 보통 국내 0 을 뗀 형태(+82 10 …)지만, 0 을 남겨 주는 곳도 있다.
        return if (national.startsWith("0")) national else "0$national"
    }
}
```

- [ ] **Step 4: 통과를 확인한다**

Run:
```bash
cd /c/ggotAI/ggotAIhp/android && JAVA_HOME="/c/Program Files/Android/Android Studio/jbr" ./gradlew :app:testDebugUnitTest --tests "com.ggotai.hp.util.PhoneNumberNormalizerTest"
```
Expected: PASS (7 tests)

- [ ] **Step 5: 커밋한다**

```bash
cd /c/ggotAI && git add ggotAIhp/android/app/src/main/java/com/ggotai/hp/util/PhoneNumberNormalizer.kt ggotAIhp/android/app/src/test/java/com/ggotai/hp/util/PhoneNumberNormalizerTest.kt
git commit -F - <<'EOF'
feat(hp): 발신번호 정규화(+82 → 0)

MMS 는 발신번호를 국제형(+821049534339)으로, SMS 는 국내형(01049534339)으로
준다. 이 값이 대화방 키가 되므로 맞춰두지 않으면 같은 사람의 주문이 두 대화로
갈라져 스티키가 먹지 않는다.

해외 번호는 그대로 둔다 — 국내 규칙을 잘못 적용하면 다른 사람과 합쳐진다.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
```

---

### Task 2: 조회 범위와 워터마크 계산

6시간은 조회 범위가 아니라 **상한선**이다. 평상시엔 몇 분치만 본다. 첫 설치 때 과거를 훑지 않는 것과, 본문이 안 내려온 메시지를 넘어가지 않는 것이 이 태스크의 핵심이다.

**Files:**
- Create: `ggotAIhp/android/app/src/main/java/com/ggotai/hp/mms/MmsScanWindow.kt`
- Test: `ggotAIhp/android/app/src/test/java/com/ggotai/hp/mms/MmsScanWindowTest.kt`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `MmsScanWindow.MAX_LOOKBACK_MILLIS: Long` (= 6시간)
  - `MmsScanWindow.startAt(watermark: Long?, now: Long, maxLookbackMillis: Long = MAX_LOOKBACK_MILLIS): Long`
  - `MmsScanWindow.nextWatermark(scanEndAt: Long, earliestIncompleteAt: Long?): Long`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`ggotAIhp/android/app/src/test/java/com/ggotai/hp/mms/MmsScanWindowTest.kt`:

```kotlin
package com.ggotai.hp.mms

import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * 6시간은 "매번 6시간을 훑는다"가 아니라 상한선이다. 평상시에는 마지막으로 본
 * 시점 이후만 본다.
 */
class MmsScanWindowTest {

    private val minute = 60_000L
    private val hour = 60 * minute
    private val now = 1_800_000_000_000L

    @Test
    fun `평상시에는 워터마크 이후만 본다`() {
        assertEquals(now - 5 * minute, MmsScanWindow.startAt(now - 5 * minute, now))
    }

    @Test
    fun `워터마크가 6시간보다 오래됐으면 6시간으로 자른다`() {
        assertEquals(now - 6 * hour, MmsScanWindow.startAt(now - 2 * 24 * hour, now))
    }

    @Test
    fun `첫 설치는 지금부터 — 과거를 건드리지 않는다`() {
        // 워터마크가 없을 때 6시간을 훑으면 앱을 깐 순간 사장님 폰의
        // 지난 6시간 메시지가 통째로 들어온다.
        assertEquals(now, MmsScanWindow.startAt(null, now))
    }

    @Test
    fun `경계값 — 정확히 6시간 전이면 그대로 쓴다`() {
        assertEquals(now - 6 * hour, MmsScanWindow.startAt(now - 6 * hour, now))
    }

    @Test
    fun `워터마크가 미래면 그대로 둬 조회가 0건이 되게 한다`() {
        // 시계가 뒤로 갔을 때 과거를 다시 훑어 중복 적재하는 것을 막는다.
        assertEquals(now + hour, MmsScanWindow.startAt(now + hour, now))
    }

    @Test
    fun `상한은 주입할 수 있다`() {
        assertEquals(now - 2 * hour, MmsScanWindow.startAt(now - 5 * hour, now, maxLookbackMillis = 2 * hour))
    }

    @Test
    fun `기본 상한은 6시간이다`() {
        assertEquals(6 * hour, MmsScanWindow.MAX_LOOKBACK_MILLIS)
    }

    @Test
    fun `전부 정상 처리되면 워터마크는 조회 끝점까지 전진한다`() {
        assertEquals(now, MmsScanWindow.nextWatermark(scanEndAt = now, earliestIncompleteAt = null))
    }

    @Test
    fun `본문이 안 내려온 메시지가 있으면 그 직전까지만 전진한다`() {
        // 넘어가 버리면 그 주문은 영영 못 본다. 다음 스캔에서 다시 잡히게 남긴다.
        val stuck = now - 3 * minute
        assertEquals(stuck - 1, MmsScanWindow.nextWatermark(scanEndAt = now, earliestIncompleteAt = stuck))
    }
}
```

- [ ] **Step 2: 실패를 확인한다**

Run:
```bash
cd /c/ggotAI/ggotAIhp/android && JAVA_HOME="/c/Program Files/Android/Android Studio/jbr" ./gradlew :app:testDebugUnitTest --tests "com.ggotai.hp.mms.MmsScanWindowTest"
```
Expected: FAIL — `Unresolved reference: MmsScanWindow`

- [ ] **Step 3: 구현한다**

`ggotAIhp/android/app/src/main/java/com/ggotai/hp/mms/MmsScanWindow.kt`:

```kotlin
package com.ggotai.hp.mms

/**
 * MMS 를 어디서부터 어디까지 볼지, 그리고 어디까지 봤다고 기록할지 계산한다.
 *
 * 6시간은 조회 범위가 아니라 **상한선**이다. 평상시에는 마지막으로 본 시점 이후만
 * 보므로 보통 몇 분치다. 폰이 오래 꺼져 있었을 때만 6시간으로 잘린다.
 */
object MmsScanWindow {

    /** 따라잡기 상한. 이보다 오래된 주문은 뒤늦게 자동 등록하지 않는다. */
    const val MAX_LOOKBACK_MILLIS = 6 * 60 * 60 * 1000L

    /**
     * 조회 시작 시각.
     *
     * 워터마크가 없으면(첫 설치) `now` 를 돌려 아무것도 가져오지 않는다 — 6시간을
     * 훑으면 앱을 깐 순간 사장님 폰의 지난 6시간 메시지가 통째로 들어온다.
     */
    fun startAt(
        watermark: Long?,
        now: Long,
        maxLookbackMillis: Long = MAX_LOOKBACK_MILLIS,
    ): Long {
        if (watermark == null) return now
        return maxOf(watermark, now - maxLookbackMillis)
    }

    /**
     * 다음 워터마크.
     *
     * 본문이 아직 안 내려온 메시지가 있으면 그 직전까지만 전진한다 — 넘어가면 그
     * 주문은 영영 못 본다. 그 메시지가 끝내 안 내려와도 [MAX_LOOKBACK_MILLIS] 상한이
     * 조회 시작점을 밀어 올려 결국 지나쳐 간다(최대 6시간 뒤 포기).
     */
    fun nextWatermark(scanEndAt: Long, earliestIncompleteAt: Long?): Long =
        if (earliestIncompleteAt == null) scanEndAt else earliestIncompleteAt - 1
}
```

- [ ] **Step 4: 통과를 확인한다**

Run:
```bash
cd /c/ggotAI/ggotAIhp/android && JAVA_HOME="/c/Program Files/Android/Android Studio/jbr" ./gradlew :app:testDebugUnitTest --tests "com.ggotai.hp.mms.MmsScanWindowTest"
```
Expected: PASS (9 tests)

- [ ] **Step 5: 커밋한다**

```bash
cd /c/ggotAI && git add ggotAIhp/android/app/src/main/java/com/ggotai/hp/mms/MmsScanWindow.kt ggotAIhp/android/app/src/test/java/com/ggotai/hp/mms/MmsScanWindowTest.kt
git commit -F - <<'EOF'
feat(hp): MMS 조회 범위·워터마크 계산

따라잡기 상한 6시간은 조회 범위가 아니라 상한선이다 — 평상시에는 마지막으로
본 시점 이후 몇 분치만 본다. 첫 설치에는 "지금"부터로 세워 사장님 폰에 쌓인
과거 메시지를 건드리지 않는다.

본문이 아직 안 내려온 메시지는 넘어가지 않는다(넘어가면 그 주문을 영영 못 본다).
그 메시지가 끝내 안 내려와도 6시간 상한이 조회 시작점을 밀어 올려 결국 지나간다.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
```

---

### Task 3: 파트 목록 → 본문 조합

MMS 한 건은 파트 여러 개로 이뤄진다(글/사진/레이아웃). 여기서 무엇을 본문으로 삼을지 정한다. 사진만 온 경우의 처리도 여기 있다.

**Files:**
- Create: `ggotAIhp/android/app/src/main/java/com/ggotai/hp/mms/MmsBodyAssembler.kt`
- Test: `ggotAIhp/android/app/src/test/java/com/ggotai/hp/mms/MmsBodyAssemblerTest.kt`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `data class MmsPart(val contentType: String, val text: String?)`
  - `MmsBodyAssembler.PHOTO_PLACEHOLDER: String` (= `"사진을 보냈습니다."`)
  - `MmsBodyAssembler.assemble(parts: List<MmsPart>, hasActiveConversation: Boolean): String?`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`ggotAIhp/android/app/src/test/java/com/ggotai/hp/mms/MmsBodyAssemblerTest.kt`:

```kotlin
package com.ggotai.hp.mms

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * MMS 한 건은 파트 여러 개다(글/사진/레이아웃). 사진은 읽을 수 없으므로 글만 쓴다.
 */
class MmsBodyAssemblerTest {

    private fun text(s: String) = MmsPart("text/plain", s)
    private val image = MmsPart("image/jpeg", null)
    private val smil = MmsPart("application/smil", "<smil/>")

    @Test
    fun `글 파트를 줄바꿈으로 잇는다`() {
        val body = MmsBodyAssembler.assemble(
            listOf(text("근조화환 하나"), text("10만원짜리로")), hasActiveConversation = false
        )
        assertEquals("근조화환 하나\n10만원짜리로", body)
    }

    @Test
    fun `사진이 섞여 있어도 글만 쓴다`() {
        val body = MmsBodyAssembler.assemble(
            listOf(smil, image, text("근조화환 하나")), hasActiveConversation = false
        )
        assertEquals("근조화환 하나", body)
    }

    @Test
    fun `사진만 왔고 주문 대화 중이면 표시를 남긴다`() {
        val body = MmsBodyAssembler.assemble(listOf(smil, image), hasActiveConversation = true)
        assertEquals("사진을 보냈습니다.", body)
    }

    @Test
    fun `사진만 왔고 주문과 무관하면 버린다`() {
        // 사장님 가족사진이 서버로 가면 안 된다.
        assertNull(MmsBodyAssembler.assemble(listOf(smil, image), hasActiveConversation = false))
    }

    @Test
    fun `레이아웃 파트만 있으면 사진으로 치지 않는다`() {
        // application/smil 은 모든 MMS 에 붙는 배치 정보라 내용이 아니다.
        assertNull(MmsBodyAssembler.assemble(listOf(smil), hasActiveConversation = true))
    }

    @Test
    fun `빈 글 파트는 없는 것으로 본다`() {
        assertNull(MmsBodyAssembler.assemble(listOf(text("   "), text("")), hasActiveConversation = false))
    }

    @Test
    fun `파트가 아예 없으면 null — 본문 미다운로드 상태다`() {
        assertNull(MmsBodyAssembler.assemble(emptyList(), hasActiveConversation = true))
    }

    @Test
    fun `글 앞뒤 공백은 다듬는다`() {
        assertEquals("근조화환 하나", MmsBodyAssembler.assemble(listOf(text("  근조화환 하나  ")), false))
    }
}
```

- [ ] **Step 2: 실패를 확인한다**

Run:
```bash
cd /c/ggotAI/ggotAIhp/android && JAVA_HOME="/c/Program Files/Android/Android Studio/jbr" ./gradlew :app:testDebugUnitTest --tests "com.ggotai.hp.mms.MmsBodyAssemblerTest"
```
Expected: FAIL — `Unresolved reference: MmsPart`

- [ ] **Step 3: 구현한다**

`ggotAIhp/android/app/src/main/java/com/ggotai/hp/mms/MmsBodyAssembler.kt`:

```kotlin
package com.ggotai.hp.mms

/** MMS 파트 하나. ContentResolver 를 정책에 들이지 않기 위한 값 객체. */
data class MmsPart(val contentType: String, val text: String?)

/**
 * MMS 파트들에서 버퍼에 담을 본문을 만든다.
 *
 * 사진은 읽을 수 없다(한계). 다만 주문 대화 중이라면 "사진이 하나 왔었다"는 사실
 * 자체가 사장님에게 단서가 되므로 한 줄을 남긴다 — 손님이 "이런 걸로 해주세요" 하고
 * 사진을 붙이는 경우가 있다. 주문과 무관한 사람의 사진은 남기지 않는다.
 */
object MmsBodyAssembler {

    const val PHOTO_PLACEHOLDER = "사진을 보냈습니다."

    private const val TEXT_TYPE = "text/plain"
    /** 모든 MMS 에 붙는 배치 정보. 내용이 아니므로 사진으로 치지 않는다. */
    private const val LAYOUT_TYPE = "application/smil"

    /**
     * @return 버퍼에 담을 본문. 담을 것이 없으면 null.
     *   파트가 아예 없으면(본문 미다운로드) 역시 null 이다 — 호출부가 이 경우를
     *   워터마크 전진 중단으로 따로 다룬다.
     */
    fun assemble(parts: List<MmsPart>, hasActiveConversation: Boolean): String? {
        val text = parts
            .filter { it.contentType.equals(TEXT_TYPE, ignoreCase = true) }
            .mapNotNull { it.text?.trim()?.takeIf { line -> line.isNotEmpty() } }
            .joinToString("\n")
        if (text.isNotEmpty()) return text

        val hasMedia = parts.any {
            !it.contentType.equals(TEXT_TYPE, ignoreCase = true) &&
                !it.contentType.equals(LAYOUT_TYPE, ignoreCase = true)
        }
        return if (hasMedia && hasActiveConversation) PHOTO_PLACEHOLDER else null
    }
}
```

- [ ] **Step 4: 통과를 확인한다**

Run:
```bash
cd /c/ggotAI/ggotAIhp/android && JAVA_HOME="/c/Program Files/Android/Android Studio/jbr" ./gradlew :app:testDebugUnitTest --tests "com.ggotai.hp.mms.MmsBodyAssemblerTest"
```
Expected: PASS (8 tests)

- [ ] **Step 5: 커밋한다**

```bash
cd /c/ggotAI && git add ggotAIhp/android/app/src/main/java/com/ggotai/hp/mms/MmsBodyAssembler.kt ggotAIhp/android/app/src/test/java/com/ggotai/hp/mms/MmsBodyAssemblerTest.kt
git commit -F - <<'EOF'
feat(hp): MMS 파트에서 본문 조합

MMS 한 건은 파트 여러 개(글/사진/레이아웃)다. 사진은 읽을 수 없으니 글만 쓴다.
application/smil 은 모든 MMS 에 붙는 배치 정보라 사진으로 치지 않는다.

사진만 온 경우, 주문 대화 중이면 "사진을 보냈습니다." 한 줄을 남긴다 — 손님이
사진으로 주문을 붙이는 경우 사장님이 문자앱을 열어볼 단서가 된다. 주문과 무관한
사람의 사진은 남기지 않는다(사생활).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
```

---

### Task 4: MMS 스캐너

앞의 순수 부품 셋을 조립해 실제로 `content://mms`를 읽고 버퍼에 담는다. `ContentResolver`를 타므로 단위테스트가 불가능하다 — 컴파일과 실기기로 확인한다.

**Files:**
- Create: `ggotAIhp/android/app/src/main/java/com/ggotai/hp/mms/MmsScanner.kt`

**Interfaces:**
- Consumes:
  - `PhoneNumberNormalizer.normalize(raw: String?): String` (Task 1)
  - `MmsScanWindow.startAt(...)`, `MmsScanWindow.nextWatermark(...)` (Task 2)
  - `MmsPart(contentType, text)`, `MmsBodyAssembler.assemble(parts, hasActiveConversation)` (Task 3)
  - 기존: `AppDatabase.getDatabase(context).messageBufferDao()`, `MessageBufferDao.countRecentBySender(channelOrder, senderKey, since)`, `MessageBufferDao.countDuplicate(channelOrder, senderKey, body, receivedAt)`, `MessageBufferDao.insert(MessageBuffer)`
  - 기존: `MessageGroupDecider.stickySince(now)`, `OrderTextFilter.shouldCollect(sender, body, hasActiveConversation)`, `ContactLookup.nameFor(context, phoneNumber)`, `CustomerResolver.resolveName(cachedName, contactName)`, `DeviceStatus.isRevoked(context)`, `MessageFlushWorker.schedule(context)`
  - 기존 상수: `SmsReceiver.CHANNEL_SMS` (= `"문자"`)
- Produces: `MmsScanner.scanOnce(context: Context): Boolean` (suspend) — 본문이 아직 안 내려온 메시지가 남아 있으면 `true`. 호출부가 재시도를 결정한다.

- [ ] **Step 1: 스캐너를 구현한다**

`ggotAIhp/android/app/src/main/java/com/ggotai/hp/mms/MmsScanner.kt`:

```kotlin
package com.ggotai.hp.mms

import android.content.ContentUris
import android.content.Context
import android.net.Uri
import android.provider.Telephony
import android.util.Log
import com.ggotai.hp.db.AppDatabase
import com.ggotai.hp.db.MessageBuffer
import com.ggotai.hp.manager.DeviceStatus
import com.ggotai.hp.policy.MessageGroupDecider
import com.ggotai.hp.policy.OrderTextFilter
import com.ggotai.hp.receiver.SmsReceiver
import com.ggotai.hp.util.ContactLookup
import com.ggotai.hp.util.CustomerResolver
import com.ggotai.hp.util.PhoneNumberNormalizer
import com.ggotai.hp.worker.MessageFlushWorker

/**
 * 긴 문자(LMS) 수집.
 *
 * 70자를 넘는 문자는 SMS 가 아니라 MMS 로 도착해 SmsReceiver 에 아예 들어오지 않는다
 * (2026-07-22 실기기 확인 — 로그조차 남지 않아 조용히 유실됐다). 시스템이 저장해 둔
 * MMS 를 읽어 기존 문자와 같은 버퍼에 담는다.
 *
 * 버퍼에 담긴 뒤부터는 새 코드가 없다 — 디바운스·묶음·업로드는 문자·카톡과 같다.
 */
object MmsScanner {

    private const val TAG = "MmsScanner"
    private const val PREFS = "app_prefs"
    private const val KEY_WATERMARK = "MMS_WATERMARK"

    /** MMS 주소 테이블에서 발신자를 뜻하는 값. */
    private const val ADDR_TYPE_FROM = 137

    /**
     * @return 본문이 아직 안 내려온 메시지가 남았으면 true. 호출부가 재시도를 정한다 —
     *   여기서 워커를 부르면 스캐너와 스케줄링이 서로를 부르는 고리가 된다.
     */
    suspend fun scanOnce(context: Context): Boolean {
        if (DeviceStatus.isRevoked(context)) {
            Log.d(TAG, "기기 승인취소 — MMS 스캔 중단")
            return false
        }

        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val stored = prefs.getLong(KEY_WATERMARK, -1L)
        val watermark = if (stored < 0) null else stored
        val now = System.currentTimeMillis()
        val startAt = MmsScanWindow.startAt(watermark, now)

        if (watermark == null) {
            // 첫 설치 — 과거는 건드리지 않고 기준점만 세운다.
            prefs.edit().putLong(KEY_WATERMARK, now).apply()
            Log.d(TAG, "첫 스캔 — 기준점만 세우고 과거는 건너뜀")
            return false
        }

        val dao = AppDatabase.getDatabase(context).messageBufferDao()
        var earliestIncompleteAt: Long? = null
        var collected = 0

        try {
            for (message in queryInbox(context, startAt, now)) {
                val parts = queryParts(context, message.id)
                if (parts.isEmpty()) {
                    // 본문이 아직 안 내려왔다. 넘어가면 이 주문을 영영 못 본다.
                    earliestIncompleteAt = minOf(
                        earliestIncompleteAt ?: message.receivedAt, message.receivedAt
                    )
                    Log.d(TAG, "본문 미다운로드 — 워터마크 보류 id=${message.id}")
                    continue
                }

                val sender = PhoneNumberNormalizer.normalize(queryFrom(context, message.id))
                if (sender.isEmpty()) continue

                val active = dao.countRecentBySender(
                    SmsReceiver.CHANNEL_SMS, sender, MessageGroupDecider.stickySince(now)
                ) > 0

                val body = MmsBodyAssembler.assemble(parts, active) ?: continue
                if (!OrderTextFilter.shouldCollect(sender, body, active)) {
                    Log.d(TAG, "주문 후보 아님 — 폐기 (서버 전송 안 함)")
                    continue
                }
                if (dao.countDuplicate(
                        SmsReceiver.CHANNEL_SMS, sender, body, message.receivedAt
                    ) > 0
                ) {
                    Log.d(TAG, "중복 MMS — 스킵")
                    continue
                }

                dao.insert(
                    MessageBuffer(
                        channelOrder = SmsReceiver.CHANNEL_SMS,
                        senderKey = sender,
                        senderName = CustomerResolver.resolveName(
                            null, ContactLookup.nameFor(context, sender)
                        ),
                        phoneNumber = sender,
                        body = body,
                        receivedAt = message.receivedAt
                    )
                )
                collected++
                Log.d(TAG, "버퍼 적재(MMS) sender=$sender bodyLen=${body.length} active=$active")
            }
        } catch (e: Exception) {
            // 권한 미허용도 여기로 온다. 조용히 실패하면 통째로 놓치는 걸 알 방법이 없다.
            Log.e(TAG, "MMS 스캔 실패: ${e.message}")
            return false
        }

        prefs.edit()
            .putLong(KEY_WATERMARK, MmsScanWindow.nextWatermark(now, earliestIncompleteAt))
            .apply()

        if (collected > 0) MessageFlushWorker.schedule(context)
        return earliestIncompleteAt != null
    }

    private data class MmsRow(val id: Long, val receivedAt: Long)

    /** 받은 메시지함에서 조회 구간에 들어오는 MMS. date 는 초 단위다. */
    private fun queryInbox(context: Context, startAt: Long, endAt: Long): List<MmsRow> {
        val rows = mutableListOf<MmsRow>()
        context.contentResolver.query(
            Telephony.Mms.Inbox.CONTENT_URI,
            arrayOf(Telephony.Mms._ID, Telephony.Mms.DATE),
            "${Telephony.Mms.DATE} >= ? AND ${Telephony.Mms.DATE} <= ?",
            arrayOf((startAt / 1000).toString(), (endAt / 1000).toString()),
            "${Telephony.Mms.DATE} ASC"
        )?.use { cursor ->
            val idIndex = cursor.getColumnIndexOrThrow(Telephony.Mms._ID)
            val dateIndex = cursor.getColumnIndexOrThrow(Telephony.Mms.DATE)
            while (cursor.moveToNext()) {
                rows.add(MmsRow(cursor.getLong(idIndex), cursor.getLong(dateIndex) * 1000))
            }
        }
        return rows
    }

    private fun queryParts(context: Context, mmsId: Long): List<MmsPart> {
        val parts = mutableListOf<MmsPart>()
        context.contentResolver.query(
            Uri.parse("content://mms/part"),
            arrayOf("ct", "text"),
            "mid = ?",
            arrayOf(mmsId.toString()),
            null
        )?.use { cursor ->
            val typeIndex = cursor.getColumnIndexOrThrow("ct")
            val textIndex = cursor.getColumnIndexOrThrow("text")
            while (cursor.moveToNext()) {
                parts.add(
                    MmsPart(
                        contentType = cursor.getString(typeIndex).orEmpty(),
                        text = cursor.getString(textIndex)
                    )
                )
            }
        }
        return parts
    }

    private fun queryFrom(context: Context, mmsId: Long): String? {
        val uri = ContentUris.withAppendedId(Telephony.Mms.CONTENT_URI, mmsId)
            .buildUpon().appendPath("addr").build()
        context.contentResolver.query(
            uri,
            arrayOf(Telephony.Mms.Addr.ADDRESS),
            "${Telephony.Mms.Addr.TYPE} = ?",
            arrayOf(ADDR_TYPE_FROM.toString()),
            null
        )?.use { cursor ->
            if (cursor.moveToFirst()) {
                return cursor.getString(cursor.getColumnIndexOrThrow(Telephony.Mms.Addr.ADDRESS))
            }
        }
        return null
    }
}
```

- [ ] **Step 2: 컴파일을 확인한다**

Run:
```bash
cd /c/ggotAI/ggotAIhp/android && JAVA_HOME="/c/Program Files/Android/Android Studio/jbr" ./gradlew :app:compileDebugKotlin
```
Expected: BUILD SUCCESSFUL

- [ ] **Step 3: 기존 테스트가 안 깨졌는지 확인한다**

Run:
```bash
cd /c/ggotAI/ggotAIhp/android && JAVA_HOME="/c/Program Files/Android/Android Studio/jbr" ./gradlew :app:testDebugUnitTest
```
Expected: BUILD SUCCESSFUL, 0 failures

- [ ] **Step 4: 커밋한다**

```bash
cd /c/ggotAI && git add ggotAIhp/android/app/src/main/java/com/ggotai/hp/mms/MmsScanner.kt
git commit -F - <<'EOF'
feat(hp): MMS 스캐너 — 워터마크 이후 긴 문자를 버퍼에 담는다

content://mms 에서 받은 메시지함을 워터마크 이후로 훑어, 발신번호(addr type=137)와
본문(part ct=text/plain)을 꺼내 기존 문자 버퍼에 담는다. MMS PDU 를 직접 해석하지
않고 시스템이 저장해 둔 것을 읽는다.

담긴 뒤부터는 새 코드가 없다 — 필터·스티키·중복방어·디바운스·업로드 전부 문자와
같은 것을 쓴다. 판단 로직(번호 정규화·조회 범위·본문 조합)은 앞선 순수 함수들이
맡고 여기서는 조회와 조립만 한다.

ContentResolver 를 타는 부분이라 단위테스트가 불가능하다. 실기기로 확인한다.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
```

---

### Task 5: 배선 — 권한·리시버·워커·앱 시작

스캐너를 실제로 돌리는 트리거를 붙인다. 이 태스크가 끝나야 기능이 동작한다.

**Files:**
- Create: `ggotAIhp/android/app/src/main/java/com/ggotai/hp/worker/MmsScanWorker.kt`
- Create: `ggotAIhp/android/app/src/main/java/com/ggotai/hp/receiver/MmsReceiver.kt`
- Modify: `ggotAIhp/android/app/src/main/AndroidManifest.xml` (권한 19번째 줄 부근, 리시버는 `SmsReceiver` 블록 뒤)
- Modify: `ggotAIhp/android/app/src/main/java/com/ggotai/hp/LoginActivity.kt:71-78`
- Modify: `ggotAIhp/android/app/src/main/java/com/ggotai/hp/MainActivity.kt:57` (`onCreate`)

**Interfaces:**
- Consumes: `MmsScanner.scanOnce(context)` (Task 4)
- Produces: `MmsScanWorker.schedule(context: Context, delayMillis: Long = SCAN_DELAY_MILLIS)`

- [ ] **Step 1: 스캔 워커를 만든다**

`ggotAIhp/android/app/src/main/java/com/ggotai/hp/worker/MmsScanWorker.kt`:

```kotlin
package com.ggotai.hp.worker

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.ggotai.hp.mms.MmsScanner
import java.util.concurrent.TimeUnit

/**
 * MMS 스캔을 지연 실행한다.
 *
 * MMS 는 도착 방송이 먼저 오고 본문이 뒤에 저장된다(실측 1.5초). 방송 직후에 읽으면
 * 빈 파트를 보게 되므로 조금 기다렸다 읽는다. 방송 안에서 잠들 수는 없어 워커로 뺀다.
 */
class MmsScanWorker(
    context: Context,
    params: WorkerParameters
) : CoroutineWorker(context, params) {

    companion object {
        private const val WORK_NAME = "mms-scan"

        /** 본문 저장을 기다리는 시간. 실측 1.5초에 여유를 뒀다. */
        const val SCAN_DELAY_MILLIS = 5_000L

        fun schedule(context: Context, delayMillis: Long = SCAN_DELAY_MILLIS) {
            val request = OneTimeWorkRequestBuilder<MmsScanWorker>()
                .setInitialDelay(delayMillis, TimeUnit.MILLISECONDS)
                .build()
            // 연달아 온 MMS 는 한 번의 스캔이 모두 처리한다(워터마크 기반이라 안전).
            // REPLACE 라 앱 시작 스캔(지연 0)이 리시버가 잡아둔 5초 스캔을 밀어낼 수 있다.
            // 그 경우 본문이 덜 내려온 채로 읽지만, doWork 의 재시도가 이어받는다.
            WorkManager.getInstance(context).enqueueUniqueWork(
                WORK_NAME, ExistingWorkPolicy.REPLACE, request
            )
        }
    }

    override suspend fun doWork(): Result {
        // 본문이 아직 안 내려온 메시지가 남았으면 WorkManager 백오프에 재시도를 맡긴다.
        // 이게 없으면 그 메시지를 다시 볼 트리거가 "다음 MMS 도착" 또는 "앱 재시작"뿐이라,
        // 조용한 폰에서는 영영 안 잡힌다. 6시간 상한이 무한 재시도를 자연히 끊는다.
        return if (MmsScanner.scanOnce(applicationContext)) Result.retry() else Result.success()
    }
}
```

- [ ] **Step 2: 리시버를 만든다**

`ggotAIhp/android/app/src/main/java/com/ggotai/hp/receiver/MmsReceiver.kt`:

```kotlin
package com.ggotai.hp.receiver

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.provider.Telephony
import android.util.Log
import com.ggotai.hp.worker.MmsScanWorker

/**
 * 긴 문자(LMS) 도착 감지.
 *
 * 70자를 넘는 문자는 MMS 로 오고, MMS 는 SMS_RECEIVED 가 아니라 WAP_PUSH_RECEIVED 로
 * 도착한다. 여기서는 아무 판단도 하지 않고 스캔만 예약한다 — 정책을 방송 안에 넣으면
 * 에뮬레이터 없이 테스트할 수 없다(KakaoMessageListenerService 와 같은 이유).
 */
class MmsReceiver : BroadcastReceiver() {

    companion object {
        private const val TAG = "MmsReceiver"
        private const val MMS_MIME = "application/vnd.wap.mms-message"
    }

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Telephony.Sms.Intents.WAP_PUSH_RECEIVED_ACTION) return
        if (intent.type != MMS_MIME) return

        Log.d(TAG, "MMS 도착 — 스캔 예약")
        MmsScanWorker.schedule(context)
    }
}
```

- [ ] **Step 3: 매니페스트에 권한과 리시버를 넣는다**

`ggotAIhp/android/app/src/main/AndroidManifest.xml` — `READ_SMS` 줄 바로 뒤에 추가:

```xml
    <uses-permission android:name="android.permission.READ_SMS" />
    <!-- 긴 문자(LMS)는 MMS 로 도착한다 — RECEIVE_SMS 만으로는 못 받는다. -->
    <uses-permission android:name="android.permission.RECEIVE_MMS" />
```

`SmsReceiver` 블록 바로 뒤(`</application>` 앞)에 추가:

```xml
        <!-- 긴 문자(LMS) 수집. MMS 는 WAP push 로 도착한다. -->
        <receiver android:name=".receiver.MmsReceiver"
            android:exported="true"
            android:permission="android.permission.BROADCAST_WAP_PUSH">
            <intent-filter android:priority="999">
                <action android:name="android.provider.Telephony.WAP_PUSH_RECEIVED" />
                <data android:mimeType="application/vnd.wap.mms-message" />
            </intent-filter>
        </receiver>
```

- [ ] **Step 4: 런타임 권한 목록에 넣는다**

`ggotAIhp/android/app/src/main/java/com/ggotai/hp/LoginActivity.kt` — `RECEIVE_SMS` 줄을 다음으로 교체:

```kotlin
            // 문자 주문 수집 — 없으면 SmsReceiver 가 아예 호출되지 않는다.
            Manifest.permission.RECEIVE_SMS,
            // 긴 문자(LMS)는 MMS 로 온다. 같은 SMS 권한 그룹이라 보통 함께 부여되지만,
            // 자동 부여가 안 되는 기기를 대비해 명시적으로 요청한다.
            Manifest.permission.RECEIVE_MMS
```

- [ ] **Step 5: 앱 시작 시 스캔을 건다**

`ggotAIhp/android/app/src/main/java/com/ggotai/hp/MainActivity.kt` — `onCreate` 안, `super.onCreate(savedInstanceState)` 다음 줄에 추가:

```kotlin
        // 앱이 죽어 있던 동안 온 긴 문자를 따라잡는다(최대 6시간).
        MmsScanWorker.schedule(this, delayMillis = 0)
```

같은 파일 import 블록에 추가:

```kotlin
import com.ggotai.hp.worker.MmsScanWorker
```

- [ ] **Step 6: 빌드하고 기존 테스트가 안 깨졌는지 확인한다**

Run:
```bash
cd /c/ggotAI/ggotAIhp/android && JAVA_HOME="/c/Program Files/Android/Android Studio/jbr" ./gradlew :app:testDebugUnitTest :app:assembleDebug
```
Expected: BUILD SUCCESSFUL, 0 failures

- [ ] **Step 7: 실기기에 설치하고 권한 부여를 확인한다**

Run:
```bash
ADB="/c/Users/SAMSUNG/AppData/Local/Android/Sdk/platform-tools/adb.exe"
$ADB install -r /c/ggotAI/ggotAIhp/android/app/build/outputs/apk/debug/app-debug.apk
$ADB shell dumpsys package com.ggotai.hp | grep -i RECEIVE_MMS
```
Expected: `Success` 그리고 `android.permission.RECEIVE_MMS: granted=true`

`granted=false`면 폰에서 앱을 한 번 실행해 권한 팝업을 허용한 뒤 다시 확인한다.

- [ ] **Step 8: 커밋한다**

```bash
cd /c/ggotAI && git add ggotAIhp/android/app/src/main/java/com/ggotai/hp/worker/MmsScanWorker.kt ggotAIhp/android/app/src/main/java/com/ggotai/hp/receiver/MmsReceiver.kt ggotAIhp/android/app/src/main/AndroidManifest.xml ggotAIhp/android/app/src/main/java/com/ggotai/hp/LoginActivity.kt ggotAIhp/android/app/src/main/java/com/ggotai/hp/MainActivity.kt
git commit -F - <<'EOF'
feat(hp): 긴 문자(MMS) 수집 배선 — 도착 방송·앱 시작 트리거

MMS 도착 방송(WAP_PUSH_RECEIVED)을 받아 5초 뒤 스캔한다. MMS 는 도착 알림이 먼저
오고 본문이 뒤에 저장되므로(실측 1.5초) 바로 읽으면 빈 파트를 본다. 방송 안에서
기다릴 수 없어 워커로 뺐다.

앱 시작 시에도 한 번 돌려 앱이 죽어 있던 공백을 메운다. 주기 작업(15분) 안전망은
넣지 않았다 — 최대 18분 지연이라 채널마다 속도가 어긋나고, 지금까지 잡은 결함이
대부분 트리거가 여럿이라 서로 안 맞는 자리에서 나왔다.

RECEIVE_MMS 는 SMS 권한 그룹이라 기존 RECEIVE_SMS 와 함께 부여될 것으로 보지만,
자동 부여가 안 되는 기기를 대비해 런타임 요청 목록에도 넣었다.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
```

---

### Task 6: 실기기 검증

단위테스트를 다 통과하고도 실기기에서만 결함이 드러난다는 것을 2026-07-21 에 겪었다(스티키 유실 등 4건). 이 태스크는 코드 변경 없이 확인만 한다.

**Files:** 없음(확인만)

**Interfaces:**
- Consumes: Task 5 까지 설치된 APK

- [ ] **Step 1: 로그 감시를 켠다**

```bash
ADB="/c/Users/SAMSUNG/AppData/Local/Android/Sdk/platform-tools/adb.exe"
$ADB logcat -c
$ADB logcat -v time | grep -E "MmsReceiver|MmsScanner|MessageFlushWorker|SmsReceiver"
```

- [ ] **Step 2: 검증 항목을 순서대로 수행한다**

각 항목마다 로그와 서버(`server_call_history`) 양쪽을 확인한다.

| # | 보낼 것 | 기대 |
|---|---|---|
| 1 | 긴 문자(70자 초과) 1통 | `MmsReceiver: MMS 도착` → `MmsScanner: 버퍼 적재(MMS)` → 3분 뒤 `묶음 업로드 성공` → 서버에 **원문 안 잘림** |
| 2 | 긴 문자 + 짧은 문자 연속 | 한 건으로 묶임(`문자/2건`) |
| 3 | 사진 1장(주문 대화 중) | 원문에 `사진을 보냈습니다.` 한 줄 |
| 4 | 사진 1장(주문 무관·10분 경과 후) | 서버에 안 올라감, `주문 후보 아님 — 폐기` |
| 5 | 주소록 등록 번호로 발송 | 서버 `customer_name` 이 이름(예: 여현동) |
| 6 | 앱 강제종료 → 긴 문자 → 앱 실행 | 시작 시 따라잡기로 수집됨 |

서버 확인:
```bash
cd /c/ggotAI && python -X utf8 -c "
import json,urllib.request,urllib.parse
env={}
for line in open('ggotAIorder/backend/.env',encoding='utf-8'):
    line=line.strip()
    if '=' in line and not line.startswith('#'):
        k,v=line.split('=',1); env[k]=v.strip().strip('\"')
base=env['SUPABASE_URL'].rstrip('/'); H={'apikey':env['SUPABASE_SERVICE_ROLE_KEY'],'Authorization':'Bearer '+env['SUPABASE_SERVICE_ROLE_KEY']}
u=base+'/rest/v1/server_call_history?'+urllib.parse.urlencode({'select':'id,channel_order,customer_name,customer_phone_number,stt_text,created_at','order':'id.desc','limit':'5'})
for r in json.loads(urllib.request.urlopen(urllib.request.Request(u,headers=H)).read()):
    print(r['id'], r['channel_order'], r['customer_name'], r['created_at'])
    print('   |', (r['stt_text'] or '')[:300].replace(chr(10),' / '))
"
```

- [ ] **Step 3: 결과를 인계 문서에 기록한다**

`개발진행/긴문자_MMS_접근법.txt` 끝에 검증 결과 절을 덧붙이고, 실패한 항목이 있으면 원인과 함께 남긴다. 자동 다운로드가 꺼진 기기 등 **고칠 수 없는 한계**도 여기 적는다.

```bash
cd /c/ggotAI && git add 개발진행/긴문자_MMS_접근법.txt
git commit -F - <<'EOF'
docs: 긴 문자(MMS) 수집 실기기 검증 결과

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
```

---

## 완료 기준

- 안드로이드 단위테스트 전체 통과(기존 59건 + 신규 24건 = 83건 예상)
- 긴 문자 주문이 원문 손실 없이 서버에 등록되고 FlowerNT 까지 간다
- 주문과 무관한 사진·메시지는 서버로 가지 않는다
- 앱 **프로세스 종료·재부팅** 공백에 온 긴 문자가 시작 시 복구된다
  (APK 재설치는 워터마크가 지워져 0건으로 시작한다 — 설계서 참조. 이를 "고치려고"
  첫 설치 조회창을 넓히지 말 것: 사생활 원칙 위반이다)
