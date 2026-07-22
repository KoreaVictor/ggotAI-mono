package com.ggotai.hp.util

/**
 * 발신번호를 한 형태(국내형)로 맞춘다.
 *
 * MMS 는 `+821049534339`, SMS 는 `01049534339` 로 같은 사람을 다르게 알려준다.
 * 이 값이 대화방 키(sender_key)가 되므로, 맞춰두지 않으면 한 주문이 두 대화로
 * 갈라져 스티키가 먹지 않는다.
 *
 * 해외 번호는 국내 규칙을 적용할 수 없어 그대로 둔다 — 꽃 주문이 올 리 없고,
 * 잘못 바꾸면 오히려 다른 사람과 합쳐진다.
 */
object PhoneNumberNormalizer {

    fun normalize(raw: String?): String {
        val cleaned = raw?.trim().orEmpty().filter { it.isDigit() || it == '+' }
        if (cleaned.isEmpty()) return ""

        if (!cleaned.startsWith("+")) return cleaned
        if (!cleaned.startsWith("+82")) return cleaned

        val national = cleaned.removePrefix("+82")
        if (national.isEmpty()) return ""
        // 국제형은 보통 국내 0 을 뗀 형태(+82 10 …)지만, 0 을 남겨 주는 곳도 있다.
        return if (national.startsWith("0")) national else "0$national"
    }
}
