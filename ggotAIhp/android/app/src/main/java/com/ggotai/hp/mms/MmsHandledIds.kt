package com.ggotai.hp.mms

/**
 * 다음 스캔에 넘길 "처리 완료" MMS id 집합을 정한다.
 *
 * 예전에는 가장 큰 N개만 남기는 평평한 개수 상한이었다. 워터마크가 오래 보류된 채
 * 200통 넘는 MMS 가 쌓이면 가장 낮은(=가장 오래된, 이미 업로드까지 끝난) id부터
 * 밀려났고, 그 id는 다음 스캔에 다시 읽혀 countDuplicate 의 보호막(버퍼 행이 아직
 * 남아 있어야 작동)이 이미 사라진 상태라 재삽입 — 중복 주문(중복 배송)으로 이어졌다.
 *
 * 조회 구간(seenNow) 밖으로 나간 id는 그 구간이 다시 조회되지 않는 한 재조회될 수
 * 없으므로 기억해 둘 필요가 없다. 그래서 "이번에 조회된 적 있던 이전 처리완료 id"만
 * 남기고, cap 은 이 로직이 예상과 다르게 동작할 때를 대비한 방어선으로만 둔다.
 */
object MmsHandledIds {

    fun pruneHandledIds(
        previous: Set<Long>,
        seenNow: Set<Long>,
        handledNow: Set<Long>,
        cap: Int,
    ): Set<Long> {
        // 이번 조회 구간 밖으로 나간 이전 id는 다시 읽힐 일이 없으니 버린다.
        val stillReachable = previous.filter { it in seenNow }.toSet()
        val merged = stillReachable + handledNow
        if (merged.size <= cap) return merged
        // 방어선: 그래도 상한을 넘으면 _ID가 단조증가라는 성질을 이용해 최근 것만 남긴다.
        return merged.sortedDescending().take(cap).toSet()
    }
}
