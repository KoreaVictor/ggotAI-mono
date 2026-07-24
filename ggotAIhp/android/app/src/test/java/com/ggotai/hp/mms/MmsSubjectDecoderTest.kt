package com.ggotai.hp.mms

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * 실기기에서 MMS 제목이 깨져 주문 원문에 그대로 실려 올라갔다(2026-07-22).
 * sub_cs 는 UTF-8(106)인데 프로바이더가 Latin-1 로 읽어 돌려준 경우다.
 */
class MmsSubjectDecoderTest {

    /** 실측값: "사장님 안녕하세요 내일"이 이렇게 나왔다. */
    private val 깨진제목 = String(
        "사장님 안녕하세요 내일".toByteArray(Charsets.UTF_8), Charsets.ISO_8859_1
    )

    @Test
    fun `깨진 UTF-8 제목을 되살린다`() {
        assertEquals("사장님 안녕하세요 내일", MmsSubjectDecoder.decode(깨진제목, 106))
    }

    @Test
    fun `이미 제대로 읽힌 한글 제목은 건드리지 않는다`() {
        // 멀쩡한 제목을 Latin-1 로 되돌리려 하면 오히려 망가진다.
        assertEquals("근조화환 주문", MmsSubjectDecoder.decode("근조화환 주문", 106))
    }

    @Test
    fun `UTF-8 이 아닌 문자셋은 손대지 않는다`() {
        assertEquals(깨진제목, MmsSubjectDecoder.decode(깨진제목, 3))
    }

    @Test
    fun `영문 숫자만 있는 제목은 그대로 둔다`() {
        // 상위 영역 바이트가 없으니 깨진 모양이 아니다.
        assertEquals("MMS", MmsSubjectDecoder.decode("MMS", 106))
        assertEquals("IMG_1234.jpg", MmsSubjectDecoder.decode("IMG_1234.jpg", 106))
    }

    @Test
    fun `비어 있거나 null 이면 그대로 돌려준다`() {
        assertNull(MmsSubjectDecoder.decode(null, 106))
        assertEquals("", MmsSubjectDecoder.decode("", 106))
    }

    @Test
    fun `되돌렸는데 깨지면 원본을 유지한다`() {
        // 유효한 UTF-8 시퀀스가 아닌 상위 바이트 — 되돌리면 대체문자가 나온다.
        val 복구불가 = "ÿþ"
        assertEquals(복구불가, MmsSubjectDecoder.decode(복구불가, 106))
    }
}
