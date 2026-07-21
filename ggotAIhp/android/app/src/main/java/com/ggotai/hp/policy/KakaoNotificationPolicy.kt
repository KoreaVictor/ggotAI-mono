package com.ggotai.hp.policy

/**
 * 카톡 알림에서 뽑아낸 값. 안드로이드 Notification/Bundle 을 여기까지 들이지 않는다 —
 * 판정 로직을 프레임워크 없이 테스트하기 위해서다.
 */
data class KakaoNotice(
    val packageName: String,
    val sender: String?,
    val body: String?,
    /** MessagingStyle 의 대화방 제목. 1:1 이면 보통 상대 이름이거나 없다. */
    val conversationTitle: String?,
    val isGroupConversation: Boolean,
    val postedAt: Long
)

/** 수집하기로 결정된 메시지 한 건. */
data class MessageCandidate(
    val senderKey: String,
    val senderName: String,
    val body: String,
    val receivedAt: Long
)

/**
 * 카톡 알림을 수집할지 판정한다.
 *
 * 개인 카톡은 공식 API가 없어 알림을 읽는 것이 유일한 경로다. 단톡방·요약 알림·주문과
 * 무관한 대화를 여기서 걸러, 사장님 사생활이 앱 DB 에도 서버에도 쌓이지 않게 한다.
 */
object KakaoNotificationPolicy {

    const val KAKAO_PACKAGE = "com.kakao.talk"

    /** "3개의 안 읽은 메시지", "메시지 5개" 같은 묶음 요약 알림. 개별 메시지가 아니다. */
    private val SUMMARY_PATTERNS = listOf(
        Regex("""^\d+개의\s*(안\s*읽은\s*)?메시지"""),
        Regex("""^메시지\s*\d+개""")
    )

    /**
     * 수집 대상이면 [MessageCandidate], 아니면 null.
     *
     * 카톡은 발신자 전화번호를 알려주지 않으므로 표시명을 대화방 키로 쓴다.
     */
    fun collectible(
        notice: KakaoNotice,
        hasActiveConversation: Boolean = false
    ): MessageCandidate? {
        if (notice.packageName != KAKAO_PACKAGE) return null

        val sender = notice.sender?.trim().orEmpty()
        val body = notice.body?.trim().orEmpty()
        if (sender.isEmpty() || body.isEmpty()) return null

        if (isGroupChat(notice, sender)) return null
        if (SUMMARY_PATTERNS.any { it.containsMatchIn(body) }) return null
        if (!OrderTextFilter.shouldCollect(sender, body, hasActiveConversation)) return null

        return MessageCandidate(
            senderKey = sender,
            senderName = sender,
            body = body,
            receivedAt = notice.postedAt
        )
    }

    /** 1:1 대화방은 제목이 상대 이름과 같거나 아예 없다. 다르면 여러 명이 있는 방이다. */
    private fun isGroupChat(notice: KakaoNotice, sender: String): Boolean {
        if (notice.isGroupConversation) return true
        val title = notice.conversationTitle?.trim().orEmpty()
        return title.isNotEmpty() && title != sender
    }
}
