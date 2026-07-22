package com.ggotai.hp.util

import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * MMS 는 국제형(+82)으로, SMS 는 국내형(0)으로 발신번호를 준다. 같은 사람이 두 형태로
 * 들어오면 대화방이 갈라져 주문이 두 건으로 쪼개진다.
 */
class PhoneNumberNormalizerTest {

    @Test
    fun `국제형 82를 국내형 0으로 바꾼다`() {
        assertEquals("01049534339", PhoneNumberNormalizer.normalize("+821049534339"))
    }

    @Test
    fun `이미 국내형이면 그대로 둔다`() {
        assertEquals("01049534339", PhoneNumberNormalizer.normalize("01049534339"))
    }

    @Test
    fun `하이픈과 공백을 제거한다`() {
        assertEquals("01049534339", PhoneNumberNormalizer.normalize("010-4953-4339"))
        assertEquals("01049534339", PhoneNumberNormalizer.normalize(" 010 4953 4339 "))
    }

    @Test
    fun `82 뒤에 이미 0이 있으면 0을 덧붙이지 않는다`() {
        // 일부 통신사가 국제형에 국내 0을 남긴 채로 준다.
        assertEquals("01049534339", PhoneNumberNormalizer.normalize("+8201049534339"))
    }

    @Test
    fun `해외 번호는 손대지 않는다`() {
        assertEquals("+14155551234", PhoneNumberNormalizer.normalize("+1-415-555-1234"))
    }

    @Test
    fun `비어 있으면 빈 문자열`() {
        assertEquals("", PhoneNumberNormalizer.normalize(null))
        assertEquals("", PhoneNumberNormalizer.normalize(""))
        assertEquals("", PhoneNumberNormalizer.normalize("   "))
    }

    @Test
    fun `대표번호 같은 짧은 번호도 그대로 둔다`() {
        // OrderTextFilter 의 대량발송 차단이 이 형태를 보고 판단한다.
        assertEquals("15881234", PhoneNumberNormalizer.normalize("1588-1234"))
    }

    @Test
    fun `국제형 대표번호는 0을 붙이지 않는다`() {
        // +8215881234 를 기계적으로 0을 붙이면 9자리(015881234)가 되어
        // OrderTextFilter.isMassSender 의 8자리 판정을 피해가 대량발송 차단이 뚫린다.
        assertEquals("15881234", PhoneNumberNormalizer.normalize("+8215881234"))
    }

    @Test
    fun `국제형 011 같은 옛 이동통신 9자리는 0을 붙인다`() {
        // 011은 대표번호(15/16/18 로 시작)가 아니므로 일반 규칙대로 0을 붙인다.
        assertEquals("0112345678", PhoneNumberNormalizer.normalize("+82112345678"))
    }

    @Test
    fun `plus 없이 82로 시작하는 국제형도 국내형으로 바꾼다`() {
        // 통신사에 따라 +를 떼고 82로 시작하는 형태로 주는 경우가 있다.
        assertEquals("01049534339", PhoneNumberNormalizer.normalize("821049534339"))
    }

    @Test
    fun `82로 시작해도 국제형이라 보기엔 짧으면 손대지 않는다`() {
        // 국내 번호는 82로 시작하지 않지만, 방어적으로 자리수가 짧으면(11자리 미만) 건드리지 않는다.
        assertEquals("821234", PhoneNumberNormalizer.normalize("82-1234"))
    }

    @Test
    fun `맨 앞이 아닌 플러스는 버린다`() {
        // 괄호 안에 국가번호를 덧붙여 보내는 등, 중간에 낀 + 가 키를 오염시키면 안 된다.
        assertEquals("0104953433982", PhoneNumberNormalizer.normalize("010-4953-4339(+82)"))
    }

    @Test
    fun `plus 없는 82 대표번호도 국내형으로 바꾼다`() {
        // 버그: 예전에는 11자리 미만이라는 이유로 8215881234 가 그대로 새어나가
        // isMassSender(정확히 8자리) 판정을 비켜갔다. +82 경로와 같은 결과가 나와야 한다.
        assertEquals("15881234", PhoneNumberNormalizer.normalize("8215881234"))
    }

    @Test
    fun `plus 없는 82 011 9자리도 0을 붙인다`() {
        assertEquals("0112345678", PhoneNumberNormalizer.normalize("82112345678"))
    }

    @Test
    fun `016 처럼 10자리 국내부분은 8자리 대표번호로 오인하지 않는다`() {
        // 016으로 시작하는 10자리 휴대폰 번호를 8자리 대표번호(REP_NUMBER_LENGTH) 규칙으로
        // 잘못 판단하면 0이 안 붙는다 — 길이가 정확히 8일 때만 대표번호 규칙을 적용해야 한다.
        assertEquals("01612345678", PhoneNumberNormalizer.normalize("+821612345678"))
    }

    @Test
    fun `국내부분이 너무 짧으면 82로 시작해도 대표번호로 보지 않는다`() {
        // 8자리 미만은 국내 부분일 수 없으니 82로 시작하는 다른 번호로 보고 손대지 않는다.
        assertEquals("8212345", PhoneNumberNormalizer.normalize("8212345"))
    }
}
