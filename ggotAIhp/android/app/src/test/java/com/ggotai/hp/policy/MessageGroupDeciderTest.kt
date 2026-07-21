package com.ggotai.hp.policy

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * 카톡·문자는 통화의 "끊김" 같은 경계가 없다. 주문이 여러 메시지로 쪼개져 오므로
 * 마지막 메시지 이후 일정 시간 조용하면 그때까지를 한 건으로 확정한다.
 */
class MessageGroupDeciderTest {

    private val minute = 60_000L

    @Test
    fun `마지막 메시지 직후에는 아직 확정하지 않는다`() {
        val last = 1_000_000L
        assertFalse(MessageGroupDecider.shouldFlush(last, last))
        assertFalse(MessageGroupDecider.shouldFlush(last, last + minute))
    }

    @Test
    fun `디바운스 시간이 지나면 확정한다`() {
        val last = 1_000_000L
        assertTrue(MessageGroupDecider.shouldFlush(last, last + 3 * minute))
        assertTrue(MessageGroupDecider.shouldFlush(last, last + 10 * minute))
    }

    @Test
    fun `경계값은 포함한다`() {
        val last = 1_000_000L
        assertFalse(MessageGroupDecider.shouldFlush(last, last + MessageGroupDecider.DEBOUNCE_MILLIS - 1))
        assertTrue(MessageGroupDecider.shouldFlush(last, last + MessageGroupDecider.DEBOUNCE_MILLIS))
    }

    @Test
    fun `디바운스 시간은 주입할 수 있다`() {
        // 실사용 로그를 보고 조정할 수 있어야 한다.
        val last = 1_000_000L
        assertTrue(MessageGroupDecider.shouldFlush(last, last + 5 * minute, debounceMillis = 5 * minute))
        assertFalse(MessageGroupDecider.shouldFlush(last, last + 4 * minute, debounceMillis = 5 * minute))
    }

    @Test
    fun `기기 시각이 뒤로 돌아가도 확정하지 않는다`() {
        // 시간 동기화로 now 가 과거가 되면 음수 경과가 된다 — 성급한 확정을 막는다.
        val last = 1_000_000L
        assertFalse(MessageGroupDecider.shouldFlush(last, last - 10 * minute))
    }

    @Test
    fun `기본 디바운스는 3분이다`() {
        assertTrue(MessageGroupDecider.DEBOUNCE_MILLIS == 3 * minute)
    }
}
