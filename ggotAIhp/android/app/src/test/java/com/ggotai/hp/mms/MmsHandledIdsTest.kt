package com.ggotai.hp.mms

import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * 처리 완료 id 가지치기는 "조회 구간 밖으로 나간 id는 다시 안 읽히니 잊어도 된다"가
 * 핵심이다. 평평한 개수 상한만 쓰면 가장 오래된(이미 업로드까지 끝난) id부터 밀려나
 * 재조회 때 재삽입되는 중복 주문 버그가 생긴다.
 */
class MmsHandledIdsTest {

    @Test
    fun `조회 구간 밖으로 나간 이전 id는 잊는다`() {
        // id 1은 예전에 처리했지만 이번 조회 구간(seenNow)에는 없다 — 다시 안 읽히니 버려도 된다.
        val result = MmsHandledIds.pruneHandledIds(
            previous = setOf(1L, 2L),
            seenNow = setOf(2L, 3L),
            handledNow = setOf(3L),
            cap = 200
        )
        assertEquals(setOf(2L, 3L), result)
    }

    @Test
    fun `이번에 처리한 id는 항상 남는다`() {
        val result = MmsHandledIds.pruneHandledIds(
            previous = emptySet(),
            seenNow = setOf(5L),
            handledNow = setOf(5L),
            cap = 200
        )
        assertEquals(setOf(5L), result)
    }

    @Test
    fun `이전에 처리했고 이번에도 조회됐으면(아직 미처리) 계속 남는다`() {
        // 본문 미다운로드 등으로 아직 처리 못 한 id는 그대로 두고, 이미 처리해 둔 다른 id만
        // 판단 대상이다 — handled 이면서 seenNow 에도 있으면 남아야 한다.
        val result = MmsHandledIds.pruneHandledIds(
            previous = setOf(10L),
            seenNow = setOf(10L, 11L),
            handledNow = emptySet(),
            cap = 200
        )
        assertEquals(setOf(10L), result)
    }

    @Test
    fun `상한을 넘지 않으면 cap이 아무것도 자르지 않는다`() {
        val previous = (1L..150L).toSet()
        val result = MmsHandledIds.pruneHandledIds(
            previous = previous,
            seenNow = previous,
            handledNow = emptySet(),
            cap = 200
        )
        assertEquals(previous, result)
    }

    @Test
    fun `가지치기 뒤에도 상한을 넘으면 cap이 방어선으로 낮은 id부터 자른다`() {
        // 예전 버그 재현 방지: 가지치기(조회 구간 필터) 자체가 200개 밑으로 줄여 주지
        // 못하는 극단적 상황에서도, 남는다면 최신(가장 큰) id들이어야 한다.
        val previous = (1L..250L).toSet()
        val seenNow = previous // 전부 이번 구간에도 다시 조회됐다고 가정
        val result = MmsHandledIds.pruneHandledIds(
            previous = previous,
            seenNow = seenNow,
            handledNow = emptySet(),
            cap = 200
        )
        assertEquals(200, result.size)
        // 가장 오래된(낮은) id가 아니라 가장 최신(높은) id들이 남아야 한다.
        assertEquals((51L..250L).toSet(), result)
    }

    @Test
    fun `eviction 경계 — cap을 정확히 하나 넘는 경우 가장 낮은 id 하나만 잘린다`() {
        val previous = (1L..200L).toSet()
        val result = MmsHandledIds.pruneHandledIds(
            previous = previous,
            seenNow = previous + 201L,
            handledNow = setOf(201L),
            cap = 200
        )
        assertEquals(200, result.size)
        assertEquals(false, result.contains(1L))
        assertEquals(true, result.contains(201L))
        assertEquals((2L..201L).toSet(), result)
    }

    @Test
    fun `previous와 seenNow와 handledNow가 모두 비어 있으면 빈 집합`() {
        assertEquals(emptySet<Long>(), MmsHandledIds.pruneHandledIds(emptySet(), emptySet(), emptySet(), 200))
    }
}
