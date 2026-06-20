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
