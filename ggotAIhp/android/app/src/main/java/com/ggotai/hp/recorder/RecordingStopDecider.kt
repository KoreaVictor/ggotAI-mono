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
