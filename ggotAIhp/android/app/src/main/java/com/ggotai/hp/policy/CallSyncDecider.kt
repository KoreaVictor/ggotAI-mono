package com.ggotai.hp.policy

/**
 * 통화 녹음 수집(업로드) 가부를 CallLog/파일 메타데이터 값만으로 판정하는 순수 로직.
 * 안드로이드 프레임워크에 의존하지 않아 JVM 단위테스트로 검증한다.
 *
 * 배경(버그): 안 받은 발신통화도 신호 송출 순간 OFFHOOK이 되어 통화종료 수집이 예약된다.
 * 이때 새 녹음이 없으면 단말의 '직전 통화 녹음'(예: 어제 마지막 통화)이 현재 통화로
 * 잘못 업로드된다. 아래 두 판정으로 이중 방어한다.
 *  (1) [isConnectedCall]   : 미성사 통화(0초·부재중·거절·차단) 자체를 차단.
 *  (2,3) [isRecordingForCall]: 녹음 파일이 시간창 이내이고 통화 시작 이후인지 교차검증.
 */
object CallSyncDecider {
    /** 녹음 파일이 이 통화에 속한다고 인정하는 최대 시간창. 폴더 스캔·MediaStore 폴백 공통. */
    const val RECORDING_WINDOW_MS = 10 * 60 * 1000L

    /** 녹음 파일이 통화 시작보다 약간 이르게 기록돼도 허용하는 시계/기록 오차 여유. */
    const val RECORDING_START_SLACK_MS = 60 * 1000L

    // CallLog.Calls.TYPE 상수(프레임워크 비의존 단위테스트를 위해 로컬 정의).
    // INCOMING=1, OUTGOING=2, MISSED=3, VOICEMAIL=4, REJECTED=5, BLOCKED=6
    const val TYPE_MISSED = 3
    const val TYPE_REJECTED = 5
    const val TYPE_BLOCKED = 6

    /**
     * 통화가 실제로 성사됐는지(=녹음이 존재할 수 있는지) 판정한다.
     * 통화시간 0초이거나 부재중/거절/차단 타입이면 false → 수집을 건너뛴다.
     * callType이 null(미상)이면 통화시간만으로 판단한다.
     */
    fun isConnectedCall(callType: Int?, durationSec: Int): Boolean {
        if (durationSec <= 0) return false
        return when (callType) {
            TYPE_MISSED, TYPE_REJECTED, TYPE_BLOCKED -> false
            else -> true
        }
    }

    /**
     * 녹음 파일이 이번 통화의 것인지 판정한다.
     *  - 현재로부터 [windowMs] 이내여야 한다(오래된 파일 배제).
     *  - 통화 시작(callStartMs) 이후여야 한다([RECORDING_START_SLACK_MS] 여유) — 직전 통화 녹음 배제.
     * callStartMs <= 0(통화시각 미상)이면 시작 검증은 생략하고 시간창만 적용한다.
     *
     * @param fileLastModifiedMs 파일 lastModified 또는 MediaStore DATE_ADDED(밀리초 변환값)
     */
    fun isRecordingForCall(
        fileLastModifiedMs: Long,
        callStartMs: Long,
        nowMs: Long,
        windowMs: Long = RECORDING_WINDOW_MS,
    ): Boolean {
        if (fileLastModifiedMs <= 0L) return false
        if (fileLastModifiedMs <= nowMs - windowMs) return false
        if (callStartMs > 0L && fileLastModifiedMs < callStartMs - RECORDING_START_SLACK_MS) return false
        return true
    }
}
