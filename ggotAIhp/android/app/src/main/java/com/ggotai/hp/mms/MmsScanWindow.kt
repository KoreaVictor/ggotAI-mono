package com.ggotai.hp.mms

/**
 * MMS 를 어디서부터 어디까지 볼지, 그리고 어디까지 봤다고 기록할지 계산한다.
 *
 * 6시간은 조회 범위가 아니라 **상한선**이다. 평상시에는 마지막으로 본 시점 이후만
 * 보므로 보통 몇 분치다. 폰이 오래 꺼져 있었을 때만 6시간으로 잘린다.
 */
object MmsScanWindow {

    /** 따라잡기 상한. 이보다 오래된 주문은 뒤늦게 자동 등록하지 않는다. */
    const val MAX_LOOKBACK_MILLIS = 6 * 60 * 60 * 1000L

    /**
     * 조회 시작 시각.
     *
     * 워터마크가 없으면(첫 설치) `now` 를 돌려 아무것도 가져오지 않는다 — 6시간을
     * 훑으면 앱을 깐 순간 사장님 폰의 지난 6시간 메시지가 통째로 들어온다.
     */
    fun startAt(
        watermark: Long?,
        now: Long,
        maxLookbackMillis: Long = MAX_LOOKBACK_MILLIS,
    ): Long {
        if (watermark == null) return now
        return maxOf(watermark, now - maxLookbackMillis)
    }

    /**
     * 다음 워터마크.
     *
     * 본문이 아직 안 내려온 메시지가 있으면 그 직전까지만 전진한다 — 넘어가면 그
     * 주문은 영영 못 본다. 그 메시지가 끝내 안 내려와도 [MAX_LOOKBACK_MILLIS] 상한이
     * 조회 시작점을 밀어 올려 결국 지나쳐 간다(최대 6시간 뒤 포기).
     */
    fun nextWatermark(scanEndAt: Long, earliestIncompleteAt: Long?): Long =
        if (earliestIncompleteAt == null) scanEndAt else earliestIncompleteAt - 1
}
