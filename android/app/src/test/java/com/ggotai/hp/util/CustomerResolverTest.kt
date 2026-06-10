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
}
