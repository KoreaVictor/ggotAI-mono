package com.ggotai.hp.policy

/**
 * 서버로 올릴 메시지를 폰 안에서 1차로 거른다.
 *
 * 사장님 개인 카톡·문자에는 가족 대화, 광고, 인증번호가 섞여 있다. 전부 올리면
 * 사생활이 서버에 쌓이고 Gemini 호출 비용도 크게 늘어난다. 여기서 걸러진 메시지는
 * 서버로 아예 전송되지 않는다.
 *
 * 놓치는 주문(false negative)이 생길 수 있으므로 키워드는 실사용 로그를 보고 넓힌다.
 */
object OrderTextFilter {

    /** 꽃 주문에서 흔히 등장하는 단어. 하나라도 걸리면 후보로 본다. */
    private val ORDER_KEYWORDS = listOf(
        "꽃", "화환", "화분", "근조", "조화", "축하", "개업", "다발", "바구니",
        "부케", "동양란", "서양란", "호접란", "리본", "근조기", "화훼",
        "배달", "배송", "주문", "결혼", "장례", "발인", "돌잔치", "생신", "프러포즈",
    )

    /**
     * 주문일 수 없는 메시지 표식. 주문 키워드보다 우선한다 —
     * "꽃집 로그인 인증번호" 같은 문구가 주문으로 새는 것을 막는다.
     */
    private val BLOCK_KEYWORDS = listOf(
        "인증번호", "인증코드", "광고", "무료거부", "수신거부", "스팸",
        "대출", "보험", "카드승인", "출금", "입금", "잔액", "이벤트",
    )

    /** 기업 대표번호 접두(8자리) — 손님 주문이 올 수 없는 대량발송 회선. */
    private val MASS_SENDER_PREFIXES = listOf("15", "16", "18")

    /**
     * 이 메시지를 서버로 올릴 가치가 있는지 판단한다.
     *
     * @param sender 문자는 발신번호, 카톡은 표시명.
     * @param body 메시지 본문.
     */
    fun isLikelyOrder(sender: String, body: String): Boolean {
        val text = body.trim()
        if (text.isEmpty()) return false
        if (isMassSender(sender)) return false
        if (BLOCK_KEYWORDS.any { text.contains(it) }) return false
        return ORDER_KEYWORDS.any { text.contains(it) }
    }

    /**
     * 이 메시지를 버퍼에 담을지 최종 판정한다.
     *
     * 주문은 한 통으로 끝나지 않는다 — 첫 통에만 "화환" 같은 키워드가 있고 가격·배송일·
     * 주소·받는분은 뒷 통에 담겨 온다. 키워드를 매 통에 요구하면 그 뒷 통들이 버려져
     * 주문이 영원히 필수값 미달로 남는다(실기기에서 확인된 실패).
     *
     * 그래서 같은 대화방에 이미 주문 메시지가 쌓여 있으면 후속 메시지는 키워드 없이도
     * 받는다. 대화 묶음이 확정(업로드)되면 버퍼가 비어 이 상태는 자연히 풀린다.
     * 단, 대량발송·인증번호·빈 본문은 진행 중이더라도 계속 거른다.
     */
    fun shouldCollect(sender: String, body: String, hasActiveConversation: Boolean): Boolean {
        val text = body.trim()
        if (text.isEmpty()) return false
        if (isMassSender(sender)) return false
        if (BLOCK_KEYWORDS.any { text.contains(it) }) return false
        return hasActiveConversation || ORDER_KEYWORDS.any { text.contains(it) }
    }

    /** 1588-1234 처럼 하이픈이 섞여 와도 대표번호로 인식한다. */
    private fun isMassSender(sender: String): Boolean {
        val digits = sender.filter { it.isDigit() }
        if (digits.length != 8) return false
        return MASS_SENDER_PREFIXES.any { digits.startsWith(it) }
    }
}
