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
}
