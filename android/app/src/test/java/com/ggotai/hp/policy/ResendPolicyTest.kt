package com.ggotai.hp.policy

import org.junit.Assert.assertEquals
import org.junit.Test

class ResendPolicyTest {

    @Test
    fun afterFailure_belowCap_staysRetryable() {
        // retryCount 0 → (1, sync 0)
        assertEquals(1 to 0, ResendPolicy.afterFailure(0))
        // retryCount 8 → (9, sync 0)
        assertEquals(9 to 0, ResendPolicy.afterFailure(8))
    }

    @Test
    fun afterFailure_reachingCap_marksPermanent() {
        // retryCount 9 → (10, sync 2) : 상한 도달
        assertEquals(10 to 2, ResendPolicy.afterFailure(9))
    }

    @Test
    fun afterFailure_beyondCap_staysPermanent() {
        // 방어적: 상한 초과도 영구실패(2)
        assertEquals(11 to 2, ResendPolicy.afterFailure(10))
    }
}
