package com.ggotai.hp.policy

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * 폰 안에서 서버로 올릴 메시지를 1차로 거른다.
 *
 * 개인 카톡·문자에는 가족 대화, 광고, 인증번호가 섞여 있다. 전부 올리면 사장님
 * 사생활이 서버에 쌓이고 Gemini 호출 비용도 크게 늘어난다.
 */
class OrderTextFilterTest {

    @Test
    fun `꽃 주문 문구는 통과한다`() {
        val orders = listOf(
            "내일 오후 3시 근조화환 10만원짜리 부탁드려요",
            "축하화환 하나 보내주세요",
            "장미 꽃다발 5만원짜리 배달 가능한가요",
            "개업식에 화분 하나 부탁해요",
            "결혼식 부케 문의드립니다",
        )
        for (body in orders) {
            assertTrue(body, OrderTextFilter.isLikelyOrder("01012345678", body))
        }
    }

    @Test
    fun `주문과 무관한 일상 대화는 거른다`() {
        val chatter = listOf(
            "아빠 오늘 저녁에 들어와?",
            "내일 점심 같이 먹자",
            "회의 자료 확인 부탁드립니다",
        )
        for (body in chatter) {
            assertFalse(body, OrderTextFilter.isLikelyOrder("01012345678", body))
        }
    }

    @Test
    fun `인증번호 문자는 꽃 단어가 있어도 거른다`() {
        // 차단 단어가 주문 키워드보다 우선한다.
        assertFalse(
            OrderTextFilter.isLikelyOrder("01012345678", "[인증번호] 123456 꽃집 로그인"),
        )
        assertFalse(
            OrderTextFilter.isLikelyOrder("01012345678", "인증코드 998877 입력해주세요"),
        )
    }

    @Test
    fun `광고 문자는 거른다`() {
        assertFalse(
            OrderTextFilter.isLikelyOrder("01012345678", "(광고) 꽃 배달 최저가 이벤트 무료거부"),
        )
    }

    @Test
    fun `대표번호 대량발송은 거른다`() {
        // 15xx·16xx·18xx 8자리는 기업 대표번호 — 손님 주문이 올 수 없다.
        for (sender in listOf("15881234", "16001234", "18001234")) {
            assertFalse(
                sender,
                OrderTextFilter.isLikelyOrder(sender, "주문하신 화환이 배송 시작되었습니다"),
            )
        }
    }

    @Test
    fun `발신번호에 하이픈이 있어도 대표번호로 인식한다`() {
        assertFalse(OrderTextFilter.isLikelyOrder("1588-1234", "화환 배송 안내"))
    }

    @Test
    fun `카톡 표시명 발신자는 대표번호 규칙에 걸리지 않는다`() {
        // 카톡은 번호 대신 표시명이 온다.
        assertTrue(OrderTextFilter.isLikelyOrder("김철수", "근조화환 하나 부탁드려요"))
    }

    @Test
    fun `빈 본문은 거른다`() {
        assertFalse(OrderTextFilter.isLikelyOrder("01012345678", ""))
        assertFalse(OrderTextFilter.isLikelyOrder("01012345678", "   "))
    }

    @Test
    fun `진행 중인 주문 대화면 키워드가 없어도 수집한다`() {
        // 주문은 여러 통에 걸쳐 온다. 첫 통만 키워드가 있고 가격·주소·받는분은
        // 뒷 통에 담기므로, 뒷 통을 버리면 주문이 영원히 미완성으로 남는다.
        assertTrue(OrderTextFilter.shouldCollect("01012345678", "10만원짜리로요", hasActiveConversation = true))
        assertTrue(OrderTextFilter.shouldCollect("01012345678", "내일 오후 3시까지요", hasActiveConversation = true))
        assertTrue(OrderTextFilter.shouldCollect("01012345678", "네", hasActiveConversation = true))
    }

    @Test
    fun `진행 중인 대화가 아니면 기존 키워드 규칙 그대로다`() {
        assertTrue(OrderTextFilter.shouldCollect("01012345678", "근조화환 부탁해요", hasActiveConversation = false))
        assertFalse(OrderTextFilter.shouldCollect("01012345678", "10만원짜리로요", hasActiveConversation = false))
    }

    @Test
    fun `진행 중인 대화라도 대량발송 번호는 계속 거른다`() {
        // 스티키 수집이 광고 유입 통로가 되면 안 된다.
        assertFalse(OrderTextFilter.shouldCollect("15881234", "10만원짜리로요", hasActiveConversation = true))
    }

    @Test
    fun `진행 중인 대화라도 인증번호는 계속 거른다`() {
        assertFalse(OrderTextFilter.shouldCollect("01012345678", "인증번호 123456", hasActiveConversation = true))
    }

    @Test
    fun `진행 중인 대화라도 빈 본문은 거른다`() {
        assertFalse(OrderTextFilter.shouldCollect("01012345678", "   ", hasActiveConversation = true))
    }
}
