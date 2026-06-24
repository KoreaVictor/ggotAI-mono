package com.ggotai.hp.policy

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CallSyncDeciderTest {
    private val d = CallSyncDecider

    // ── isConnectedCall: 미성사 통화 차단(수정1) ──

    @Test fun `통화시간 0초면 미성사`() {
        assertFalse(d.isConnectedCall(callType = 2 /*OUTGOING*/, durationSec = 0))
    }

    @Test fun `안 받은 발신통화(0초)는 미성사`() {
        // 안 받은 발신: type=OUTGOING 이지만 duration=0 → 차단되어야 한다.
        assertFalse(d.isConnectedCall(callType = 2, durationSec = 0))
    }

    @Test fun `부재중·거절·차단 타입은 미성사`() {
        assertFalse(d.isConnectedCall(CallSyncDecider.TYPE_MISSED, durationSec = 5))
        assertFalse(d.isConnectedCall(CallSyncDecider.TYPE_REJECTED, durationSec = 5))
        assertFalse(d.isConnectedCall(CallSyncDecider.TYPE_BLOCKED, durationSec = 5))
    }

    @Test fun `통화시간 있는 발신·수신은 성사`() {
        assertTrue(d.isConnectedCall(callType = 1 /*INCOMING*/, durationSec = 12))
        assertTrue(d.isConnectedCall(callType = 2 /*OUTGOING*/, durationSec = 12))
    }

    @Test fun `타입 미상이어도 통화시간 있으면 성사`() {
        assertTrue(d.isConnectedCall(callType = null, durationSec = 12))
    }

    // ── isRecordingForCall: 시간창·통화시작 교차검증(수정2,3) ──

    private val now = 1_000_000_000_000L

    @Test fun `시간창 밖 오래된 파일은 거부`() {
        // 어제 녹음(시간창 10분 초과) → MediaStore 폴백이 반환해도 배제
        val yesterday = now - 24 * 60 * 60 * 1000L
        assertFalse(d.isRecordingForCall(yesterday, callStartMs = now - 5_000, nowMs = now))
    }

    @Test fun `시간창 안이지만 통화 시작 전 파일은 거부`() {
        // 9분 전 직전 통화 녹음(창 안)이지만 이번 통화 시작보다 앞섬 → 배제
        val callStart = now - 30_000
        val prevRecording = now - 9 * 60 * 1000L
        assertFalse(d.isRecordingForCall(prevRecording, callStartMs = callStart, nowMs = now))
    }

    @Test fun `통화 시작 이후·시간창 안 파일은 채택`() {
        val callStart = now - 30_000
        val thisRecording = now - 2_000 // 통화 끝나고 방금 기록됨
        assertTrue(d.isRecordingForCall(thisRecording, callStartMs = callStart, nowMs = now))
    }

    @Test fun `통화시각 미상이면 시간창만으로 판정`() {
        assertTrue(d.isRecordingForCall(now - 60_000, callStartMs = 0, nowMs = now))
        assertFalse(d.isRecordingForCall(now - 11 * 60 * 1000L, callStartMs = 0, nowMs = now))
    }

    @Test fun `유효하지 않은 타임스탬프는 거부`() {
        assertFalse(d.isRecordingForCall(0L, callStartMs = now - 5_000, nowMs = now))
    }
}
