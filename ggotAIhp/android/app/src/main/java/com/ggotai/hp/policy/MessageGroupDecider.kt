package com.ggotai.hp.policy

/**
 * 카톡·문자 메시지를 "주문 1건"으로 묶는 경계 판정.
 *
 * 통화는 끊기는 순간이 곧 경계지만 메시지는 그런 신호가 없다. 손님이 주문을 여러 줄로
 * 나눠 보내므로, 마지막 메시지 이후 일정 시간 조용하면 그때까지를 한 건으로 확정한다.
 *
 * 잘못 끊겨 두 건이 된 경우는 ggotAIya 의 "이전 건에 합치기"로 사후 보정한다.
 */
object MessageGroupDecider {

    /** 기본 디바운스 3분. 실사용 로그를 보고 조정한다. */
    const val DEBOUNCE_MILLIS = 3 * 60_000L

    /**
     * 대화 묶음을 확정(업로드)할 때가 됐는지 판단한다.
     *
     * now 가 lastReceivedAt 보다 과거면(시간 동기화로 시계가 뒤로 감) 확정하지 않는다 —
     * 아직 대화가 진행 중인데 성급히 잘라 올리는 것을 막는다.
     */
    fun shouldFlush(
        lastReceivedAt: Long,
        now: Long,
        debounceMillis: Long = DEBOUNCE_MILLIS,
    ): Boolean {
        val elapsed = now - lastReceivedAt
        return elapsed >= debounceMillis
    }
}
