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

    /** 15xx/16xx/18xx 대표번호는 국내에서도 0을 붙이지 않는 8자리 번호다. */
    private val REP_NUMBER_PREFIXES = listOf("15", "16", "18")
    private const val REP_NUMBER_LENGTH = 8

    fun normalize(raw: String?): String {
        // +는 맨 앞에 있을 때만 국가번호 표시로서 의미가 있다. 괄호 안에 국가번호를
        // 덧붙여 보내는 경우처럼 중간에 낀 +까지 살리면 대화방 키가 오염된다.
        val cleaned = raw?.trim().orEmpty()
            .filterIndexed { index, c -> c.isDigit() || (c == '+' && index == 0) }
        if (cleaned.isEmpty()) return ""

        // 국내 번호는 0으로 시작하거나(휴대폰) 15xx/16xx/18xx 같은 8자리 대표번호라
        // 82로 시작할 수 없다. 일부 통신사는 +를 떼고 82로 시작하는 형태로 그대로 주기도
        // 하므로, "82로 시작 + 국가번호가 붙은 길이(11자리 이상)"일 때만 국제형으로 본다.
        // 자리수 조건 없이 82 시작만으로 판단하면 우연히 82로 시작하는 다른 번호를
        // 잘못 건드릴 위험이 있어 방어적으로 길이를 함께 본다.
        val national = when {
            cleaned.startsWith("+82") -> cleaned.removePrefix("+82")
            !cleaned.startsWith("+") && cleaned.startsWith("82") && cleaned.length >= 11 ->
                cleaned.removePrefix("82")
            else -> return cleaned
        }

        if (national.isEmpty()) return ""
        return formatNational(national)
    }

    /**
     * 국가번호(82)를 뗀 국내 부분을 국내형으로 맞춘다.
     *
     * 0으로 시작하면(국제형에 국내 0을 남겨 주는 통신사) 이미 국내형이니 그대로 둔다.
     * 15xx/16xx/18xx 대표번호는 원래 국내에서도 0을 붙이지 않는 8자리라, 여기서 무조건
     * 0을 붙이면 9자리가 되어 OrderTextFilter.isMassSender 의 "8자리" 판정을 비켜가고
     * 대표번호발 광고 문자가 대량발송 차단을 뚫고 그대로 저장·업로드된다. 그 외
     * (휴대폰 10자리, 011 같은 옛 이동통신 9자리)는 국내형 0을 붙인다.
     */
    private fun formatNational(national: String): String {
        if (national.startsWith("0")) return national
        if (national.length == REP_NUMBER_LENGTH && REP_NUMBER_PREFIXES.any { national.startsWith(it) }) {
            return national
        }
        return "0$national"
    }
}
