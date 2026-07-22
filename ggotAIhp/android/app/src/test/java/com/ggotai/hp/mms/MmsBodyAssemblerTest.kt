package com.ggotai.hp.mms

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * MMS 한 건은 파트 여러 개다(글/사진/레이아웃). 사진은 읽을 수 없으므로 글만 쓴다.
 */
class MmsBodyAssemblerTest {

    private fun text(s: String) = MmsPart("text/plain", s)
    private val image = MmsPart("image/jpeg", null)
    private val smil = MmsPart("application/smil", "<smil/>")

    @Test
    fun `글 파트를 줄바꿈으로 잇는다`() {
        val body = MmsBodyAssembler.assemble(
            listOf(text("근조화환 하나"), text("10만원짜리로")), hasActiveConversation = false
        )
        assertEquals("근조화환 하나\n10만원짜리로", body)
    }

    @Test
    fun `사진이 섞여 있어도 글만 쓴다`() {
        val body = MmsBodyAssembler.assemble(
            listOf(smil, image, text("근조화환 하나")), hasActiveConversation = false
        )
        assertEquals("근조화환 하나", body)
    }

    @Test
    fun `사진만 왔고 주문 대화 중이면 표시를 남긴다`() {
        val body = MmsBodyAssembler.assemble(listOf(smil, image), hasActiveConversation = true)
        assertEquals("사진을 보냈습니다.", body)
    }

    @Test
    fun `사진만 왔고 주문과 무관하면 버린다`() {
        // 사장님 가족사진이 서버로 가면 안 된다.
        assertNull(MmsBodyAssembler.assemble(listOf(smil, image), hasActiveConversation = false))
    }

    @Test
    fun `레이아웃 파트만 있으면 사진으로 치지 않는다`() {
        // application/smil 은 모든 MMS 에 붙는 배치 정보라 내용이 아니다.
        assertNull(MmsBodyAssembler.assemble(listOf(smil), hasActiveConversation = true))
    }

    @Test
    fun `빈 글 파트는 없는 것으로 본다`() {
        assertNull(MmsBodyAssembler.assemble(listOf(text("   "), text("")), hasActiveConversation = false))
    }

    @Test
    fun `파트가 아예 없으면 null — 본문 미다운로드 상태다`() {
        assertNull(MmsBodyAssembler.assemble(emptyList(), hasActiveConversation = true))
    }

    @Test
    fun `글 앞뒤 공백은 다듬는다`() {
        assertEquals("근조화환 하나", MmsBodyAssembler.assemble(listOf(text("  근조화환 하나  ")), false))
    }

    @Test
    fun `charset 파라미터가 붙은 text plain 도 글로 읽는다`() {
        // 아이폰발 MMS 는 흔히 "text/plain; charset=utf-8" 형태로 온다.
        // 세미콜론 뒤 파라미터 때문에 글이 아니라 사진으로 오분류되면 주문 본문이 사라진다.
        val part = MmsPart("text/plain; charset=utf-8", "근조화환 하나")
        assertEquals("근조화환 하나", MmsBodyAssembler.assemble(listOf(part), hasActiveConversation = false))
    }

    @Test
    fun `charset 파라미터가 붙은 smil 도 배치 정보로 본다`() {
        // 파라미터 유무와 무관하게 application/smil 은 내용이 아니다.
        val part = MmsPart("application/smil; charset=utf-8", "<smil/>")
        assertNull(MmsBodyAssembler.assemble(listOf(part), hasActiveConversation = true))
    }

    @Test
    fun `대문자 TEXT PLAIN 도 글로 읽는다`() {
        val part = MmsPart("TEXT/PLAIN", "근조화환 하나")
        assertEquals("근조화환 하나", MmsBodyAssembler.assemble(listOf(part), hasActiveConversation = false))
    }

    @Test
    fun `text 가 null 인 파트가 섞여도 유효한 글은 잃지 않는다`() {
        val nullTextPart = MmsPart("text/plain", null)
        val body = MmsBodyAssembler.assemble(
            listOf(nullTextPart, text("근조화환 하나")), hasActiveConversation = false
        )
        assertEquals("근조화환 하나", body)
    }
}
