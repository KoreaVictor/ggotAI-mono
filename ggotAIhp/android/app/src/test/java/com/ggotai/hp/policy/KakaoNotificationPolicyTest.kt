package com.ggotai.hp.policy

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * 카톡 알림에서 뽑아낸 값으로 "이걸 주문 후보로 수집할지"를 판정한다.
 *
 * 안드로이드 Notification/Bundle 을 직접 다루면 테스트가 불가능하므로, 서비스는 값만
 * 꺼내 [KakaoNotice] 로 넘기고 판단은 전부 여기서 한다.
 */
class KakaoNotificationPolicyTest {

    private fun notice(
        packageName: String = "com.kakao.talk",
        sender: String? = "김철수",
        body: String? = "근조화환 하나 부탁드려요",
        conversationTitle: String? = null,
        isGroupConversation: Boolean = false,
        postedAt: Long = 1_700_000_000_000L,
    ) = KakaoNotice(packageName, sender, body, conversationTitle, isGroupConversation, postedAt)

    @Test
    fun `1대1 주문 메시지는 수집한다`() {
        val candidate = KakaoNotificationPolicy.collectible(notice())

        assertNotNull(candidate)
        assertEquals("김철수", candidate!!.senderKey)
        assertEquals("김철수", candidate.senderName)
        assertEquals("근조화환 하나 부탁드려요", candidate.body)
        assertEquals(1_700_000_000_000L, candidate.receivedAt)
    }

    @Test
    fun `카톡이 아닌 앱 알림은 무시한다`() {
        assertNull(KakaoNotificationPolicy.collectible(notice(packageName = "com.nhn.android.search")))
        assertNull(KakaoNotificationPolicy.collectible(notice(packageName = "com.instagram.android")))
    }

    @Test
    fun `단톡방은 수집하지 않는다`() {
        // 단톡방엔 주문이 아니라 잡담이 오간다. 사생활 유출을 막는 1차 방어선.
        assertNull(KakaoNotificationPolicy.collectible(notice(isGroupConversation = true)))
    }

    @Test
    fun `대화방 제목이 발신자와 다르면 단톡방으로 본다`() {
        // 1:1은 방 제목 = 상대 이름. 다르면 여러 명이 있는 방이다.
        assertNull(
            KakaoNotificationPolicy.collectible(
                notice(sender = "김철수", conversationTitle = "꽃집 사장님 모임"),
            ),
        )
    }

    @Test
    fun `대화방 제목이 발신자와 같으면 1대1로 본다`() {
        assertNotNull(
            KakaoNotificationPolicy.collectible(
                notice(sender = "김철수", conversationTitle = "김철수"),
            ),
        )
    }

    @Test
    fun `안 읽은 메시지 요약 알림은 무시한다`() {
        // 카톡은 개별 메시지 외에 "3개의 안 읽은 메시지" 같은 요약을 따로 띄운다.
        assertNull(KakaoNotificationPolicy.collectible(notice(body = "3개의 안 읽은 메시지")))
        assertNull(KakaoNotificationPolicy.collectible(notice(body = "메시지 5개")))
    }

    @Test
    fun `발신자나 본문이 비면 무시한다`() {
        assertNull(KakaoNotificationPolicy.collectible(notice(sender = null)))
        assertNull(KakaoNotificationPolicy.collectible(notice(sender = "  ")))
        assertNull(KakaoNotificationPolicy.collectible(notice(body = null)))
        assertNull(KakaoNotificationPolicy.collectible(notice(body = "")))
    }

    @Test
    fun `주문과 무관한 대화는 수집하지 않는다`() {
        // OrderTextFilter 와 같은 기준을 쓴다.
        assertNull(KakaoNotificationPolicy.collectible(notice(body = "아빠 오늘 늦어?")))
    }

    @Test
    fun `본문 앞뒤 공백은 정리한다`() {
        val candidate = KakaoNotificationPolicy.collectible(notice(body = "  축하화환 부탁해요  "))

        assertEquals("축하화환 부탁해요", candidate!!.body)
    }

    @Test
    fun `진행 중인 주문 대화면 키워드 없는 후속 메시지도 수집한다`() {
        // 실기기에서 확인된 실패: "근조화환 부탁해요"만 수집되고 "10만원짜리로요",
        // "내일 3시 강남구…" 가 버려져 주문이 영원히 필수값 미달로 남았다.
        val follow = notice(body = "10만원짜리로요")

        assertNotNull(KakaoNotificationPolicy.collectible(follow, hasActiveConversation = true))
        assertNull(KakaoNotificationPolicy.collectible(follow, hasActiveConversation = false))
    }

    @Test
    fun `진행 중인 대화라도 단톡방은 계속 거른다`() {
        assertNull(
            KakaoNotificationPolicy.collectible(
                notice(isGroupConversation = true, body = "10만원짜리로요"),
                hasActiveConversation = true,
            ),
        )
    }

    @Test
    fun `진행 중인 대화라도 요약 알림은 계속 거른다`() {
        assertNull(
            KakaoNotificationPolicy.collectible(
                notice(body = "3개의 안 읽은 메시지"),
                hasActiveConversation = true,
            ),
        )
    }
}
