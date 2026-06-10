package com.ggotai.hp.policy

/** 자동 재전송 실패 시 다음 retry_count/sync_status 결정 로직 (순수 함수). */
object ResendPolicy {
    /** 자동 재시도 상한. 도달 시 영구실패(sync_status=2). */
    const val MAX_RETRY = 10

    /**
     * 1회 업로드 실패 후 새 상태를 계산한다.
     * @param currentRetryCount 현재 retry_count
     * @return (새 retry_count, 새 sync_status). sync_status 0=재시도대상, 2=영구실패.
     */
    fun afterFailure(currentRetryCount: Int): Pair<Int, Int> {
        val newCount = currentRetryCount + 1
        val syncStatus = if (newCount >= MAX_RETRY) 2 else 0
        return newCount to syncStatus
    }
}
