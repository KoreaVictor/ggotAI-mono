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
