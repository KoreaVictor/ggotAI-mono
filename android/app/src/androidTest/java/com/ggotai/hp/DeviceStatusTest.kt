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
