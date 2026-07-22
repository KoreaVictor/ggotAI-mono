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

    @Test
    fun `제목만 있고 글 파트가 없으면 제목을 본문으로 쓴다`() {
        // 삼성 메시지 등 일부 발신자(LMS·피처폰)는 본문을 파트가 아니라 MMS 제목에 담아
        // 보낸다. 파트만 보면 사진뿐인 메시지로 오분류되거나 그대로 버려진다.
        val body = MmsBodyAssembler.assemble(
            listOf(smil), hasActiveConversation = false, subject = "근조화환 하나"
        )
        assertEquals("근조화환 하나", body)
    }

    @Test
    fun `제목과 글 파트가 모두 있으면 제목을 앞에 붙인다`() {
        val body = MmsBodyAssembler.assemble(
            listOf(text("10만원짜리로")), hasActiveConversation = false, subject = "근조화환 주문"
        )
        assertEquals("근조화환 주문\n10만원짜리로", body)
    }

    @Test
    fun `제목이 공백뿐이면 없는 것으로 본다`() {
        val body = MmsBodyAssembler.assemble(
            listOf(text("근조화환 하나")), hasActiveConversation = false, subject = "   "
        )
        assertEquals("근조화환 하나", body)
    }

    @Test
    fun `제목도 글 파트도 없고 사진뿐이면 기존 규칙대로 처리한다`() {
        // subject 파라미터 추가가 기존 사진 전용 처리 로직에 영향을 주지 않는지 확인.
        val body = MmsBodyAssembler.assemble(
            listOf(smil, image), hasActiveConversation = true, subject = null
        )
        assertEquals("사진을 보냈습니다.", body)
    }

    @Test
    fun `인코딩된 제목은 무시하고 사진 자리표시를 그대로 쓴다`() {
        // RFC 2047 인코딩 단어(=?EUC-KR?B?...?=)가 제목 자리를 대신 차지하면 안 된다.
        val body = MmsBodyAssembler.assemble(
            listOf(smil, image),
            hasActiveConversation = true,
            subject = "=?EUC-KR?B?7ZWY7Yq47KO87IS4?="
        )
        assertEquals("사진을 보냈습니다.", body)
    }

    @Test
    fun `인코딩된 제목이면 비활성 대화에서도 새어나가지 않는다`() {
        // 예전 버그: 글 파트가 없어도 media 체크 전에 제목을 그대로 돌려줘,
        // 비활성 대화의 쓰레기 제목이 그대로 서버로 샐 수 있었다.
        val body = MmsBodyAssembler.assemble(
            listOf(smil, image),
            hasActiveConversation = false,
            subject = "=?EUC-KR?B?7ZWY7Yq47KO87IS4?="
        )
        assertNull(body)
    }

    @Test
    fun `사진뿐이고 쓸만한 제목이 있으면 제목 다음 줄에 자리표시를 붙인다`() {
        val body = MmsBodyAssembler.assemble(
            listOf(smil, image), hasActiveConversation = true, subject = "사진 제목"
        )
        assertEquals("사진 제목\n사진을 보냈습니다.", body)
    }
}
