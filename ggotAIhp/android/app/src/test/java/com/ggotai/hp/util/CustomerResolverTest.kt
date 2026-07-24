package com.ggotai.hp.util

import org.junit.Assert.assertEquals
import org.junit.Test

class CustomerResolverTest {

    @Test
    fun resolveNumber_validNumber_returnsIt() {
        assertEquals("01049534339", CustomerResolver.resolveNumber("01049534339"))
    }

    @Test
    fun resolveNumber_blankOrNull_returnsUnknown() {
        assertEquals("Unknown", CustomerResolver.resolveNumber(null))
        assertEquals("Unknown", CustomerResolver.resolveNumber(""))
        assertEquals("Unknown", CustomerResolver.resolveNumber("   "))
    }

    @Test
    fun resolveName_prefersCachedName() {
        assertEquals("여현동", CustomerResolver.resolveName("여현동", "주소록이름"))
    }

    @Test
    fun resolveName_fallsBackToContactName_whenCachedBlank() {
        assertEquals("주소록이름", CustomerResolver.resolveName(null, "주소록이름"))
        assertEquals("주소록이름", CustomerResolver.resolveName("", "주소록이름"))
    }

    @Test
    fun resolveName_defaultWhenNoneOrContactIsDefault() {
        assertEquals("신규", CustomerResolver.resolveName(null, null))
        assertEquals("신규", CustomerResolver.resolveName("", ""))
        // contactName이 이미 기본값 "신규"면 무시하고 "신규"
        assertEquals("신규", CustomerResolver.resolveName(null, "신규"))
    }

    @Test
    fun resolveName_문자는_주소록이름만으로_결정된다() {
        // 문자에는 통화의 CallLog 캐시명 같은 게 없다(발신번호만 온다).
        // 주소록에 있으면 그 이름, 없으면 통화와 같은 기본값이어야 한다 —
        // 예전엔 여기가 비어 고객명 자리에 번호가 그대로 들어갔다.
        assertEquals("여현동", CustomerResolver.resolveName(null, "여현동"))
        assertEquals("신규", CustomerResolver.resolveName(null, null))
    }
}
